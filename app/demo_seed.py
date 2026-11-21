"""Transactional expansion of the demo roster without replacing existing data."""

import csv
from dataclasses import dataclass
import os
from pathlib import Path
import secrets

import click
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.audit_integrity import audit_key, verify_chain
from app.demo_data import EMAIL_DOMAIN, RECORD_TOTAL, SUBJECTS, plan_demo
from app.migrations import SCHEMA_VERSION
from app.models import Role, StudentRecord, SUPPORTED_ROLES, User, db
from app.workspace import reserve_write


@dataclass
class SeedSummary:
    accounts_created: int = 0
    records_created: int = 0
    emails_filled: int = 0
    credentials_path: Path | None = None


def expand_demo():
    """Write the full roster in one SQLite transaction and retain existing credentials."""
    planned = plan_demo()
    specs = {item.username: item for item in planned}
    summary = SeedSummary()
    new_credentials = []
    private_path = None

    try:
        reserve_write()
        connection = db.session.connection()
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version != SCHEMA_VERSION:
            raise ValueError(f"Expected schema version {SCHEMA_VERSION}. Initialize a fresh database or back up and migrate the existing one.")
        if not verify_chain(connection, audit_key()).valid:
            raise ValueError("The audit chain did not verify. Resolve that before expanding the dataset.")

        users = {user.username: user for user in db.session.scalars(
            db.select(User).options(joinedload(User.role), joinedload(User.assigned_teacher), joinedload(User.student_record))
        )}
        records = validate_existing(users, specs)
        check_email_plan(users, planned)
        if len(records) > RECORD_TOTAL:
            raise ValueError(f"Existing records exceed the target of {RECORD_TOTAL}. No data was replaced.")

        database_path = Path(db.engine.url.database)
        credentials_path = database_path.with_suffix(".demo-credentials.csv")
        if len(users) < len(specs) and os.path.lexists(credentials_path):
            raise ValueError("A credentials file already exists for this database. Keep it in a private location before adding more accounts.")

        roles = {role.name: role for role in db.session.scalars(db.select(Role))}
        for name in SUPPORTED_ROLES:
            if name not in roles:
                roles[name] = Role(name=name)
                db.session.add(roles[name])

        for item in planned:
            user = users.get(item.username)
            if user is None:
                password = secrets.token_urlsafe(24)
                user = User(username=item.username, display_name=item.name, email=item.email,
                            role=roles[item.role], assigned_teacher=users.get(item.teacher))
                user.set_password(password)
                db.session.add(user)
                users[item.username] = user
                new_credentials.append((item.username, item.role, item.name, password))
            elif user.email is None:
                user.email = item.email
                summary.emails_filled += 1

        candidates = [item for item in planned if item.role == "Student" and item.username not in records]
        # If a preferred waiting student already has a record, preserve it and
        # leave the next eligible account empty to keep the total unchanged.
        candidates.sort(key=lambda item: (item.username == "student2", item.prefers_waiting))
        for item in candidates[:RECORD_TOTAL - len(records)]:
            db.session.add(StudentRecord(student=users[item.username], course=item.subject, marks=item.marks))
            summary.records_created += 1

        db.session.flush()
        if not valid_totals():
            raise ValueError("The expanded roster did not match the target distribution.")
        if new_credentials:
            private_path = write_credentials(credentials_path, new_credentials)
            summary.credentials_path = private_path
        db.session.commit()
        summary.accounts_created = len(new_credentials)
        return summary
    except BaseException:
        db.session.rollback()
        if private_path is not None:
            private_path.unlink()
        raise


def validate_existing(users, specs):
    records = {}
    for username, user in users.items():
        item = specs.get(username)
        if item is None:
            raise ValueError(f"Existing account {username!r} is outside the demonstration roster.")
        teacher = user.assigned_teacher.username if user.assigned_teacher else None
        if user.role.name != item.role or teacher != item.teacher:
            raise ValueError(f"Existing role or teacher assignment conflicts with the roster for {username!r}.")
        if user.student_record is not None:
            if user.student_record.course != item.subject:
                raise ValueError(f"Existing academic course conflicts with the roster for {username!r}.")
            records[username] = user.student_record
    return records


def check_email_plan(users, planned):
    seen = set()
    for item in planned:
        user = users.get(item.username)
        email = user.email if user is not None and user.email is not None else item.email
        if not email.casefold().endswith("@" + EMAIL_DOMAIN):
            raise ValueError(f"Existing email for {item.username!r} does not use the reserved demonstration domain.")
        if email.casefold() in seen:
            raise ValueError(f"Duplicate demonstration email for {item.username!r}.")
        seen.add(email.casefold())


def valid_totals():
    roles = dict(db.session.execute(db.select(Role.name, db.func.count(User.id))
                                   .join(User, User.role_id == Role.id).group_by(Role.name)).all())
    assigned = db.session.scalars(db.select(db.func.count(User.id)).where(User.assigned_teacher_id.is_not(None))
                                 .group_by(User.assigned_teacher_id)).all()
    records = db.session.scalar(db.select(db.func.count(StudentRecord.id)))
    return roles == {"Admin": 2, "Teacher": 12, "Student": 120} and assigned == [10] * 12 and records == RECORD_TOTAL


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
