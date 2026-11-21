"""Transactional expansion of the demo roster without replacing existing data."""

import csv
from dataclasses import dataclass
import io
import os
from pathlib import Path
import secrets
from tempfile import NamedTemporaryFile

import click
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.audit_integrity import audit_key, verify_chain
from app.demo_data import EMAIL_DOMAIN, RECORD_TOTAL, SUBJECTS, TEAM_ACCOUNTS, plan_demo
from app.forms import PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH
from app.migrations import SCHEMA_VERSION, initialize_or_error
from app.models import Role, StudentRecord, SUPPORTED_ROLES, User, db
from app.workspace import reserve_write


@dataclass
class SeedSummary:
    accounts_created: int = 0
    records_created: int = 0
    emails_filled: int = 0
    credentials_path: Path | None = None
    admins: int = 0
    teachers: int = 0
    students: int = 0
    records: int = 0
    awaiting: int = 0
    audit_entries: int = 0


def expand_demo(*, unified=False):
    """Seed new rows atomically. Unified setup preserves data outside the demo roster."""
    fictional = plan_demo()
    planned = fictional + TEAM_ACCOUNTS if unified else fictional
    specs = {item.username: item for item in fictional + TEAM_ACCOUNTS}
    summary = SeedSummary()
    new_credentials = []
    credential_undo = None

    try:
        reserve_write()
        connection = db.session.connection()
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version != SCHEMA_VERSION:
            raise ValueError(f"Expected schema version {SCHEMA_VERSION}. Initialize a fresh database or back up and migrate the existing one.")
        audit = verify_chain(connection, audit_key())
        if not audit.valid:
            raise ValueError("The audit chain did not verify. Resolve that before expanding the dataset.")
        summary.audit_entries = audit.count

        users = {user.username: user for user in db.session.scalars(
            db.select(User).options(joinedload(User.role), joinedload(User.assigned_teacher), joinedload(User.student_record))
        )}
        records = validate_existing(users, specs, preserve_extras=unified)
        fictional_records = sum(1 for item in fictional if item.username in records)
        check_email_plan(users, planned, preserve_extras=unified)
        if fictional_records > RECORD_TOTAL and not unified:
            raise ValueError(f"Existing records exceed the target of {RECORD_TOTAL}. No data was replaced.")

        database_path = Path(db.engine.url.database)
        credentials_path = database_path.with_suffix(".demo-credentials.csv")
        adding_accounts = any(item.username not in users for item in planned)
        if adding_accounts and os.path.lexists(credentials_path) and not unified:
            raise ValueError("A credentials file already exists for this database. Keep it in a private location before adding more accounts.")

        roles = {role.name: role for role in db.session.scalars(db.select(Role))}
        for name in SUPPORTED_ROLES:
            if name not in roles:
                roles[name] = Role(name=name)
                db.session.add(roles[name])

        for item in planned:
            user = users.get(item.username)
            if user is None:
                password = team_password(item) if item in TEAM_ACCOUNTS else secrets.token_urlsafe(24)
                user = User(username=item.username, display_name=item.name, email=item.email,
                            role=roles[item.role], assigned_teacher=users.get(item.teacher))
                user.set_password(password)
                db.session.add(user)
                users[item.username] = user
                new_credentials.append((item.username, item.role, item.name, password))
            elif user.email is None:
                user.email = item.email
                summary.emails_filled += 1

        candidates = [item for item in fictional if item.role == "Student" and item.username not in records]
        # Keep the original waiting account empty if it has no record yet.
        candidates.sort(key=lambda item: (item.username == "student2", item.prefers_waiting))
        new_records = candidates[:max(0, RECORD_TOTAL - fictional_records)]
        if unified:
            new_records += [item for item in TEAM_ACCOUNTS
                            if item.marks is not None and item.username not in records]
        for item in new_records:
            db.session.add(StudentRecord(student=users[item.username], course=item.subject, marks=item.marks))
        summary.records_created = len(new_records)
        summary.accounts_created = len(new_credentials)

        db.session.flush()
        verify_database(connection, summary)
        if new_credentials:
            credential_undo = publish_credentials(credentials_path, new_credentials, extend=unified)
            summary.credentials_path = credentials_path
        db.session.commit()
        return summary
    except BaseException:
        try:
            db.session.rollback()
        finally:
            if credential_undo is not None:
                credential_undo()
        raise


def team_password(item):
    password = os.environ.get(f"DEMO_{item.username.upper()}_PASSWORD")
    if not password:
        return secrets.token_urlsafe(24)
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH or not password.strip():
        raise ValueError(
            f"A configured team password for {item.name} must have "
            f"{PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} characters and contain non-whitespace."
        )
    return password


def validate_existing(users, specs, *, preserve_extras=False):
    records = {}
    for username, user in users.items():
        item = specs.get(username)
        if item is None:
            if preserve_extras:
                continue
            raise ValueError(f"Existing account {username!r} is outside the demonstration roster.")
        teacher = user.assigned_teacher.username if user.assigned_teacher else None
        if user.role.name != item.role or teacher != item.teacher:
            raise ValueError(f"Existing role or teacher assignment conflicts with the roster for {username!r}.")
        if user.student_record is not None:
            if item.subject is not None and user.student_record.course != item.subject:
                raise ValueError(f"Existing academic course conflicts with the roster for {username!r}.")
            records[username] = user.student_record
    return records


def check_email_plan(users, planned, *, preserve_extras=False):
    planned_names = {item.username for item in planned}
    seen = {user.email.casefold() for user in users.values()
            if user.username not in planned_names and user.email is not None}
    for item in planned:
        user = users.get(item.username)
        if preserve_extras and user is not None and user.email is not None:
            # Reserve existing addresses without rewriting them.
            seen.add(user.email.casefold())
    for item in planned:
        user = users.get(item.username)
        if preserve_extras and user is not None and user.email is not None:
            continue
        email = user.email if user is not None and user.email is not None else item.email
        if not email.casefold().endswith("@" + EMAIL_DOMAIN):
            raise ValueError(f"Existing email for {item.username!r} does not use the reserved demonstration domain.")
        if email.casefold() in seen:
            raise ValueError(f"Duplicate demonstration email for {item.username!r}.")
        seen.add(email.casefold())


def verify_database(connection, summary):
    if connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() != ["ok"]:
        raise ValueError("SQLite integrity verification failed.")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise ValueError("SQLite foreign-key verification failed.")
    roles = dict(connection.execute(db.select(Role.name, db.func.count(User.id))
                                    .join(User, User.role_id == Role.id).group_by(Role.name)).all())
    summary.admins = roles.get("Admin", 0)
    summary.teachers = roles.get("Teacher", 0)
    summary.students = roles.get("Student", 0)
    summary.records = connection.scalar(db.select(db.func.count(StudentRecord.id)))
    summary.awaiting = summary.students - summary.records


def atomic_write_private(path, content):
    with NamedTemporaryFile(dir=path.parent, suffix=".demo-credentials.csv", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def publish_credentials(path, credentials, *, extend):
    if not extend or not os.path.lexists(path):
        write_credentials(path, credentials)
        return path.unlink
    if path.is_symlink() or not path.is_file():
        raise ValueError("The private credentials path must be a regular file.")
    original = path.read_bytes()
    csv_reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig"), newline=""))
    if csv_reader.fieldnames != ["username", "role", "name", "password"]:
        raise ValueError("The existing credentials file does not have the expected header.")
    prior_names = {row["username"] for row in csv_reader}
    if any(row[0] in prior_names for row in credentials):
        raise ValueError("Existing credentials refer to an account missing from the database. Reconcile the two before retrying.")
    addition = io.StringIO(newline="")
    csv.writer(addition).writerows(credentials)
    separator = b"" if original.endswith((b"\n", b"\r")) else b"\n"
    atomic_write_private(path, original + separator + addition.getvalue().encode("utf-8"))
    return lambda: atomic_write_private(path, original)


def write_credentials(path, credentials):
    # Exclusive creation protects existing credentials and avoids following symlinks.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("username", "role", "name", "password"))
            writer.writerows(credentials)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink()
        raise
    return path


def register_demo_command(app):
    @app.cli.command("seed-demo")
    def seed_demo():
        """Expand a migrated demo database without replacing existing data."""
        try:
            summary = expand_demo()
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        except (OSError, SQLAlchemyError) as error:
            raise click.ClickException("The demo transaction could not be saved. Existing data and credentials were preserved.") from error
        click.echo("Demo roster: 2 administrators, 12 teachers, 120 students (134 accounts).")
        click.echo("Academic records: 110. Awaiting records: 10. Assigned students per teacher: 10.")
        click.echo(f"Added {summary.accounts_created} accounts and {summary.records_created} records. Filled {summary.emails_filled} blank email fields.")
        click.echo("Subject distribution: 2 teachers and 20 students in each of:")
        for subject in SUBJECTS:
            click.echo(f"  {subject}")
        if summary.credentials_path:
            click.echo(f"New credentials saved privately to {summary.credentials_path}.")
        else:
            click.echo("Existing passwords and credentials file were preserved.")


    @app.cli.command("setup-demo")
    def setup_demo():
        """Initialize, migrate and verify the unified SecureRole demonstration database."""
        initialize_or_error()
        try:
            summary = expand_demo(unified=True)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        except (OSError, SQLAlchemyError) as error:
            raise click.ClickException("The demo transaction could not be saved. Check database and credential file permissions.") from error
        total = summary.admins + summary.teachers + summary.students
        click.echo(f"Accounts: {total} ({summary.admins} Admins, {summary.teachers} Teachers, {summary.students} Students).")
        click.echo(f"Academic records: {summary.records}. Awaiting records: {summary.awaiting}.")
        click.echo(f"Added {summary.accounts_created} accounts and {summary.records_created} records.")
        click.echo(f"SQLite integrity and foreign keys passed. HMAC audit chain verified ({summary.audit_entries} entries).")
        if summary.credentials_path:
            click.echo(f"New credentials saved privately to {summary.credentials_path}.")
        else:
            click.echo("Existing passwords and private credentials were preserved.")
