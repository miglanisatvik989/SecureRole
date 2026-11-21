"""Transactional forward migrations for local SQLite installations."""

from contextlib import closing
from pathlib import Path
import sqlite3

import click
from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.audit_integrity import GENESIS, audit_key, entry_mac, head, inspect_audit, key_tag, valid_mac
from app.models import db
from app.schema_rules import install_rules

SCHEMA_VERSION = 1
LEGACY_TABLES = {"roles", "users", "student_records", "access_logs"}


def migrate_database():
    """Initialize a fresh database or upgrade a Phase 7 database in place."""
    with db.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        version = connection.exec_driver_sql("PRAGMA user_version").scalar_one()
        if version == SCHEMA_VERSION:
            state = head(connection)
            if state is None or not valid_mac(state["key_tag"], key_tag(audit_key())):
                raise ValueError("The configured audit key does not match this database.")
            connection.rollback()
            return False
        if version != 0:
            raise ValueError(f"Unsupported database version {version}.")
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if tables and tables != LEGACY_TABLES:
            raise ValueError("The database does not match the Phase 7 schema. Restore a compatible backup.")
        if tables:
            validate_legacy(connection)
            connection.exec_driver_sql("ALTER TABLE access_logs ADD COLUMN actor_role VARCHAR(30)")
            connection.exec_driver_sql("ALTER TABLE access_logs ADD COLUMN previous_mac VARCHAR(64)")
            connection.exec_driver_sql("ALTER TABLE access_logs ADD COLUMN entry_mac VARCHAR(64)")
        db.metadata.create_all(connection)

        key = audit_key()
        previous, last_id = GENESIS, 0
        for row in connection.execute(text("SELECT * FROM access_logs ORDER BY id")).mappings().all():
            entry = dict(row, previous_mac=previous)
            mac = entry_mac(key, entry)
            connection.execute(text("UPDATE access_logs SET previous_mac=:previous, entry_mac=:mac WHERE id=:id"),
                               {"previous": previous, "mac": mac, "id": row["id"]})
            previous, last_id = mac, row["id"]
        connection.execute(text("""
            INSERT INTO audit_chain_state(id, head_id, head_mac, key_tag) VALUES (1, :id, :mac, :tag)
        """), {"id": last_id, "mac": previous, "tag": key_tag(key)})
        install_rules(connection)
        connection.exec_driver_sql("PRAGMA user_version = 1")
        connection.commit()
        return True


def validate_legacy(connection):
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise ValueError("Resolve existing foreign-key violations before migrating.")
    invalid = connection.exec_driver_sql("""
        SELECT 1 FROM users u JOIN roles r ON r.id=u.role_id
        LEFT JOIN users teacher ON teacher.id=u.assigned_teacher_id
        LEFT JOIN roles tr ON tr.id=teacher.role_id
        WHERE u.assigned_teacher_id IS NOT NULL
          AND (r.name!='Student' OR tr.name IS NOT 'Teacher' OR u.id=teacher.id)
        UNION ALL
        SELECT 1 FROM student_records s JOIN users u ON u.id=s.student_user_id
        JOIN roles r ON r.id=u.role_id WHERE r.name!='Student'
        LIMIT 1
    """).first()
    if invalid:
        raise ValueError("Resolve existing role or assignment violations before migrating.")


def initialize_or_error():
    try:
        return migrate_database()
    except (ValueError, SQLAlchemyError) as error:
        message = str(error) if isinstance(error, ValueError) else "SQLite rejected the migration."
        raise click.ClickException(message) from error


def register_database_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Initialize or upgrade the configured SQLite database."""
        initialize_or_error()
        click.echo(f"Database initialized at schema version {SCHEMA_VERSION}.")

    @app.cli.command("migrate-db")
    def migrate_db():
        """Upgrade the SQLite database without dropping existing rows."""
        changed = initialize_or_error()
        click.echo(f"Schema version {SCHEMA_VERSION}: {'applied' if changed else 'already current'}.")

    @app.cli.command("backup-db")
    @click.argument("destination", type=click.Path(path_type=Path))
    def backup_db(destination):
        """Write a consistent SQLite backup to a new file."""
        source = Path(db.engine.url.database).resolve()
        if not source.is_file():
            raise click.ClickException("No database exists to back up.")
        try:
            destination.touch(mode=0o600, exist_ok=False)
        except OSError as error:
            raise click.ClickException("The backup destination must be a new writable file.") from error
        try:
            with (
                closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original,
                closing(sqlite3.connect(destination)) as copy,
            ):
                original.backup(copy)
        except sqlite3.Error as error:
            destination.unlink()
            raise click.ClickException("The database backup failed.") from error
        click.echo("SQLite backup created.")

    @app.cli.command("verify-audit")
    @click.option("--checkpoint", help="Previously trusted entry ID and MAC, in ID:MAC format.")
    def verify_audit(checkpoint):
        """Verify the journal from a read-only transaction."""
        expected = None
        if checkpoint is not None:
            identity, _, mac = checkpoint.partition(":")
            try:
                identity = int(identity)
                if identity <= 0 or len(mac) != 64 or any(c not in "0123456789abcdef" for c in mac):
                    raise ValueError
            except ValueError as error:
                raise click.ClickException("Use a positive ID and a 64-character lowercase hex MAC.") from error
            expected = (identity, mac)
        database = Path(db.engine.url.database).resolve()
        if not database.is_file():
            raise click.ClickException("No database exists to verify.")
        # mode=ro prevents even a mistaken write or creation of a database.
        from sqlalchemy import create_engine

        engine = create_engine(f"sqlite:///{database.as_uri()}?mode=ro&uri=true")
        try:
            result = inspect_audit(engine, audit_key(), expected)
        except SQLAlchemyError as error:
            raise click.ClickException("Audit verification failed. Check the database schema and file.") from error
        finally:
            engine.dispose()
        if not result.valid:
            raise click.ClickException(result.message)
        click.echo(f"{result.message} Entries checked: {result.count}.")
        if result.head_id:
            click.echo(f"Checkpoint: {result.head_id}:{result.head_mac}")
