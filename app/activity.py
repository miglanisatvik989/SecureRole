"""Administrator access activity and dashboard summaries."""

from flask import Blueprint, request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.models import AccessLog, User, db
from app.rbac import Action, require_permission
from app.workspace import render_workspace

activity = Blueprint("activity", __name__)
PAGE_SIZE = 20


def recent_activity():
    return db.session.scalars(db.select(AccessLog).options(joinedload(AccessLog.actor).joinedload(User.role))
                              .order_by(AccessLog.timestamp.desc(), AccessLog.id.desc()).limit(5)).all()


@activity.get("/access-logs")
def index():
    # Freeze the result set before auditing this request so navigation doesn't shift pages.
    latest = db.session.scalar(db.select(db.func.max(AccessLog.id))) or 0
    snapshot = min(latest, max(0, request.args.get("snapshot", latest, type=int)))
    require_permission(Action.VIEW_ACCESS_LOGS)
    decision = request.args.get("decision", "")
    if decision not in ("Allowed", "Denied"):
        decision = ""
    actions = db.session.scalars(db.select(AccessLog.action).where(AccessLog.id <= snapshot)
                                 .distinct().order_by(AccessLog.action)).all()
    action = request.args.get("action", "")
    if action not in actions:
        action = ""
    search = request.args.get("q", "").strip()[:100]
    statement = db.select(AccessLog).where(AccessLog.id <= snapshot).options(
        joinedload(AccessLog.actor).joinedload(User.role)
    )
    if decision:
        statement = statement.where(AccessLog.decision == decision)
    if action:
        statement = statement.where(AccessLog.action == action)
    if search:
        statement = statement.where(or_(
            AccessLog.action.icontains(search, autoescape=True),
            AccessLog.resource.icontains(search, autoescape=True),
            AccessLog.actor.has(or_(User.username.icontains(search, autoescape=True),
                                    User.display_name.icontains(search, autoescape=True))),
        ))
    page = max(1, request.args.get("page", 1, type=int))
    # Bound the offset by the actual count, including for arbitrary page numbers.
    total = db.session.scalar(db.select(db.func.count()).select_from(statement.subquery()))
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, last_page)
    logs = db.session.scalars(statement.order_by(AccessLog.timestamp.desc(), AccessLog.id.desc())
                              .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).all()
    return render_workspace("activity.html", logs=logs, actions=actions, decision=decision,
                            action=action, search=search, page=page, last_page=last_page,
                            total=total, snapshot=snapshot, active="activity")
