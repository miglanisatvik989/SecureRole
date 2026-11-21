"""Non-destructive demonstration data for the Phase 3 database."""

import secrets

import click

from app.models import db, Role, User, StudentRecord, SUPPORTED_ROLES


DEMO_ACCOUNTS = (
    ("admin", "Administrator", "Admin", None),
    ("teacher1", "Teacher One", "Teacher", None),
    ("teacher2", "Teacher Two", "Teacher", None),
    ("student1", "Student One", "Student", "teacher1"),
    ("student2", "Student Two", "Student", "teacher1"),
    ("student3", "Student Three", "Student", "teacher2"),
)


def seed_demonstration_data():
    """Add missing demo data atomically; return passwords for new accounts only."""
    credentials = {}
    roles = {}
    accounts = {}
    for name in SUPPORTED_ROLES:
        role = db.session.scalar(db.select(Role).filter_by(name=name))
        if role is None:
            role = Role(name=name)
            db.session.add(role)
        roles[name] = role
    db.session.flush()

    for username, display_name, role_name, teacher_name in DEMO_ACCOUNTS:
        user = db.session.scalar(db.select(User).filter_by(username=username))
        if user is None:
            password = secrets.token_urlsafe(16)
            user = User(
                username=username, display_name=display_name, role=roles[role_name]
            )
            user.set_password(password)
            if teacher_name is not None:
                user.assigned_teacher = accounts[teacher_name]
            db.session.add(user)
            credentials[username] = password
        elif user.role.name != role_name:
            raise ValueError(
                f"Existing account {username!r} does not have the demo role "
                f"{role_name}. No existing data was changed."
            )
        accounts[username] = user

    for username, marks in (("student1", 85), ("student3", 78)):
        student = accounts[username]
        if student.student_record is None:
            db.session.add(StudentRecord(
                student=student,
                course="Cryptography and Network Security",
                marks=marks,
            ))
    db.session.commit()
    return credentials


def register_seed_command(app):
    @app.cli.command("seed-db")
    def seed_db():
        """Create tables and add missing fictional demonstration accounts."""
        db.create_all()
        try:
            credentials = seed_demonstration_data()
        except Exception as error:
            db.session.rollback()
            raise click.ClickException(f"Seeding failed: {error}") from error

        if credentials:
            click.echo("Database seeded successfully. New demo credentials:")
            click.echo("Save these passwords now; only hashes are stored.")
            for username, password in credentials.items():
                click.echo(f"{username}: {password}")
        else:
            click.echo("Demo data checked; existing accounts and passwords preserved.")
