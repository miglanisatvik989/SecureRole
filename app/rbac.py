"""Default-deny authorization for dashboards, academic records and administration."""

from flask import abort, current_app
from flask_login import current_user
from sqlalchemy import and_, false, or_
from sqlalchemy.orm import aliased

from app.audit import commit_access_log, stage_access_log
from app.models import Role, StudentRecord, SUPPORTED_ROLES, User, db


class Action:
    VIEW_DASHBOARD = "dashboard.view"
    VIEW_RECORD = "record.view"
    CREATE_RECORD = "record.create"
    EDIT_RECORD = "record.edit"
    DELETE_RECORD = "record.delete"
    MANAGE_USERS = "users.manage"
    ASSIGN_ROLES = "roles.assign"
    ASSIGN_TEACHERS = "teachers.assign"
    VIEW_ACCESS_LOGS = "access_logs.view"


_RECORD_SCOPES = {
    Action.VIEW_RECORD: {"Admin": "all", "Teacher": "assigned", "Student": "own"},
    Action.CREATE_RECORD: {"Admin": "all", "Teacher": "assigned"},
    Action.EDIT_RECORD: {"Admin": "all", "Teacher": "assigned"},
    Action.DELETE_RECORD: {"Admin": "all"},
}
_ADMIN_RESOURCES = {
    Action.MANAGE_USERS: "users",
    Action.ASSIGN_ROLES: "roles",
    Action.ASSIGN_TEACHERS: "teacher_assignments",
    Action.VIEW_ACCESS_LOGS: "access_logs",
}


def _valid_id(value):
    return type(value) is int and 0 < value <= 2**63 - 1


def _student_ids(actor_id, action):
    """Select eligible Student IDs using the stored role and assignment in SQL."""
    statement = db.select(User.id).where(User.role.has(Role.name == "Student"))
    if not _valid_id(actor_id) or action not in _RECORD_SCOPES:
        return statement.where(false())

    actor = aliased(User)
    scope_conditions = {
        "all": True,
        "assigned": User.assigned_teacher_id == actor_id,
        "own": User.id == actor_id,
    }
    conditions = [
        and_(
            db.select(actor.id).where(
                actor.id == actor_id, actor.role.has(Role.name == role)
            ).exists(),
            scope_conditions[scope],
        )
        for role, scope in _RECORD_SCOPES[action].items()
    ]
    return statement.where(or_(*conditions))


def scoped_records(actor_id, action=Action.VIEW_RECORD):
    """Build a selectable for existing records. Execute it in the operation's transaction."""
    statement = db.select(StudentRecord)
    if action not in (Action.VIEW_RECORD, Action.EDIT_RECORD, Action.DELETE_RECORD):
        return statement.where(false())
    return statement.where(StudentRecord.student_user_id.in_(_student_ids(actor_id, action)))


def is_allowed(actor_id, action, *, record_id=None, student_id=None, dashboard_role=None):
    """Check stored state. Creation takes a student ID and other record actions take a record ID."""
    if not _valid_id(actor_id) or not isinstance(action, str):
        return False

    # Pending edits cannot change the role or assignment used for the decision.
    with db.session.no_autoflush:
        if action == Action.CREATE_RECORD:
            if not _valid_id(student_id) or record_id is not None or dashboard_role is not None:
                return False
            statement = _student_ids(actor_id, action).where(User.id == student_id)
            return bool(db.session.scalar(db.select(statement.exists())))

        if action in _RECORD_SCOPES:
            if not _valid_id(record_id) or student_id is not None or dashboard_role is not None:
                return False
            statement = scoped_records(actor_id, action).where(StudentRecord.id == record_id)
            return bool(db.session.scalar(db.select(statement.exists())))

        if record_id is not None or student_id is not None:
            return False
        if action == Action.VIEW_DASHBOARD:
            if dashboard_role is None:
                roles = SUPPORTED_ROLES  # The dispatcher redirects to the user's own page.
            elif dashboard_role in SUPPORTED_ROLES:
                roles = (dashboard_role,)
            else:
                return False
        elif action in _ADMIN_RESOURCES and dashboard_role is None:
            roles = ("Admin",)
        else:
            return False

        statement = db.select(User.id).join(User.role).where(
            User.id == actor_id, Role.name.in_(roles)
        )
        return bool(db.session.scalar(db.select(statement.exists())))


def _audit_labels(action, *, record_id=None, student_id=None, dashboard_role=None):
    """Use fixed resource labels, with optional validated identifiers."""
    if not isinstance(action, str):
        return "unknown", "unknown"
    if action == Action.VIEW_DASHBOARD:
        resource = f"dashboard:{dashboard_role.lower()}" if dashboard_role in SUPPORTED_ROLES else "dashboard"
    elif action == Action.CREATE_RECORD:
        resource = f"student:{student_id}" if _valid_id(student_id) else "student_records"
    elif action in _RECORD_SCOPES:
        resource = f"student_record:{record_id}" if _valid_id(record_id) else "student_records"
    elif action in _ADMIN_RESOURCES:
        resource = _ADMIN_RESOURCES[action]
    else:
        return "unknown", "unknown"
    return action, resource


def require_permission(action, *, atomic=False, **target):
    """Guard a route before writes. When atomic, stage the allowed event for the caller to commit."""
    actor_id = current_user.id if current_user.is_authenticated else None
    allowed = is_allowed(actor_id, action, **target)
    action_label, resource = _audit_labels(action, **target)
    event = dict(actor_id=actor_id, action=action_label, resource=resource, allowed=allowed)

    if allowed and atomic:
        stage_access_log(db.session, **event)
    else:
        commit_access_log(**event)

    if actor_id is None:
        abort(current_app.login_manager.unauthorized())
    if not allowed:
        abort(403)
