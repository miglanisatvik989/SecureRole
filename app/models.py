from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlite3 import Connection

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeDecorator, DateTime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
SUPPORTED_ROLES = ("Admin", "Teacher", "Student")


class UTCDateTime(TypeDecorator):
    """SQLite stores naive datetimes; always return timezone-aware UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


def effective_related(instance, relationship, foreign_key, model, session):
    """Resolve pending relationship OR FK edits before SQLAlchemy synchronizes them."""
    state = inspect(instance)
    if state.attrs[relationship].history.has_changes():
        return getattr(instance, relationship)
    if state.attrs[foreign_key].history.has_changes():
        identity = getattr(instance, foreign_key)
        return session.get(model, identity) if identity is not None else None
    return getattr(instance, relationship)


@event.listens_for(Engine, "connect")
def enable_foreign_keys(connection, record):
    if isinstance(connection, Connection):
        connection.execute("PRAGMA foreign_keys = ON")


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    users = db.relationship("User", back_populates="role")

    __table_args__ = (
        db.CheckConstraint(
            "name IN ('Admin', 'Teacher', 'Student')"
        ),
    )


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True)

    role_id = db.Column(
        db.Integer,
        db.ForeignKey("roles.id"),
        nullable=False
    )

    assigned_teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    role = db.relationship("Role", back_populates="users")

    assigned_teacher = db.relationship(
        "User",
        remote_side=[id],
        back_populates="assigned_students"
    )

    assigned_students = db.relationship(
        "User", back_populates="assigned_teacher", passive_deletes="all"
    )

    student_record = db.relationship(
        "StudentRecord",
        back_populates="student",
        uselist=False,
        passive_deletes="all"
    )

    def validate_consistency(self, session):
        """Validate both direct FK edits and relationship-based assignments."""
        role = effective_related(self, "role", "role_id", Role, session)
        if role is None or role.name not in SUPPORTED_ROLES:
            raise ValueError("Each user must have one supported role.")
        teacher = effective_related(
            self, "assigned_teacher", "assigned_teacher_id", User, session
        )
        if teacher is None:
            if self.assigned_teacher_id is not None and not inspect(
                self
            ).attrs.assigned_teacher.history.has_changes():
                raise ValueError("Assigned teacher does not exist.")
            return
        if role.name != "Student":
            raise ValueError("Only Student accounts can receive teacher assignments.")
        teacher_role = effective_related(teacher, "role", "role_id", Role, session)
        if teacher_role is None or teacher_role.name != "Teacher":
            raise ValueError("Assigned teachers must have the Teacher role.")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class StudentRecord(db.Model):
    __tablename__ = "student_records"

    id = db.Column(db.Integer, primary_key=True)

    student_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    course = db.Column(db.String(100), nullable=False)
    marks = db.Column(db.Float, nullable=False)

    student = db.relationship(
        "User",
        back_populates="student_record"
    )

    __table_args__ = (
        db.CheckConstraint(
            "marks >= 0 AND marks <= 100",
            name="valid_marks"
        ),
    )

    def validate_consistency(self, session):
        student = effective_related(
            self, "student", "student_user_id", User, session
        )
        role = (
            effective_related(student, "role", "role_id", Role, session)
            if student is not None else None
        )
        if role is None or role.name != "Student":
            raise ValueError("Only Student accounts can own academic records.")
        try:
            marks = Decimal(str(self.marks))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("Marks must be a number between 0 and 100.") from error
        if not marks.is_finite() or not 0 <= marks <= 100:
            raise ValueError("Marks must be a number between 0 and 100.")


class AccessLog(db.Model):
    __tablename__ = "access_logs"
    __mapper_args__ = {"batch": False}  # Each insert advances the audit head immediately.

    id = db.Column(db.Integer, primary_key=True)

    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    action = db.Column(db.String(100), nullable=False)
    resource = db.Column(db.String(200), nullable=False)
    decision = db.Column(db.String(10), nullable=False)

    timestamp = db.Column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    actor_role = db.Column(db.String(30))
    previous_mac = db.Column(db.String(64), nullable=False)
    entry_mac = db.Column(db.String(64), nullable=False)

    actor = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "decision IN ('Allowed', 'Denied')"
        ),
    )


class AuthSession(db.Model):
    __tablename__ = "auth_sessions"

    id = db.Column(db.Integer, primary_key=True)
    token_digest = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    created_at = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.Integer, nullable=False)
    revoked_at = db.Column(db.Integer)

    __table_args__ = (db.CheckConstraint("expires_at > created_at"),)


class LoginWindow(db.Model):
    __tablename__ = "login_windows"

    bucket = db.Column(db.String(64), primary_key=True)
    attempts = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.Integer, nullable=False, index=True)


class AuditHead(db.Model):
    __tablename__ = "audit_chain_state"

    id = db.Column(db.Integer, primary_key=True)
    head_id = db.Column(db.Integer, nullable=False)
    head_mac = db.Column(db.String(64), nullable=False)
    key_tag = db.Column(db.String(64), nullable=False)

    __table_args__ = (db.CheckConstraint("id = 1"),)


@event.listens_for(Session, "before_flush")
def validate_role_consistency(session, flush_context, instances):
    """Recheck dependents too: changing a teacher's role can invalidate students.

    This small simulator checks the complete graph on ORM flush. SQL constraints
    additionally enforce foreign keys, uniqueness, required values and ranges.
    Bulk SQL bypasses this hook; use ORM objects for application writes.
    """
    changed = session.new.union(session.dirty).union(session.deleted)
    if not any(isinstance(item, (Role, User, StudentRecord)) for item in changed):
        return
    with session.no_autoflush:
        users = set(session.scalars(db.select(User))).union(
            item for item in session.new if isinstance(item, User)
        )
        records = set(session.scalars(db.select(StudentRecord))).union(
            item for item in session.new if isinstance(item, StudentRecord)
        )
        for item in users.union(records).difference(session.deleted):
            item.validate_consistency(session)
