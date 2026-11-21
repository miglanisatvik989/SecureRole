"""Administrator access activity and dashboard summaries."""

import csv
import io
import unicodedata

from flask import Blueprint, Response, request
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.audit_integrity import audit_key, inspect_audit
from app.models import AccessLog, User, db
from app.rbac import Action, require_permission
from app.workspace import render_workspace

activity = Blueprint("activity", __name__)
PAGE_SIZE = 20


def recent_activity():
    return db.session.scalars(db.select(AccessLog).options(joinedload(AccessLog.actor))
                              .order_by(AccessLog.timestamp.desc(), AccessLog.id.desc()).limit(5)).all()


def authorized_snapshot():
    # Freeze the result set before recording this view or export decision.
    latest = db.session.scalar(db.select(db.func.max(AccessLog.id))) or 0
    snapshot = min(latest, max(0, request.args.get("snapshot", latest, type=int)))
    require_permission(Action.VIEW_ACCESS_LOGS)
    return snapshot, inspect_audit(db.engine, audit_key())


def filtered_activity(snapshot):
    decision = request.args.get("decision", "")
    if decision not in ("Allowed", "Denied"):
        decision = ""
    actions = db.session.scalars(db.select(AccessLog.action).where(AccessLog.id <= snapshot)
                                 .distinct().order_by(AccessLog.action)).all()
    action = request.args.get("action", "")
    if action not in actions:
        action = ""
    search = request.args.get("q", "").strip()[:100]
    statement = db.select(AccessLog).where(AccessLog.id <= snapshot)
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
    return statement, actions, dict(decision=decision, action=action, q=search, snapshot=snapshot)


def newest_first(statement):
    return statement.order_by(AccessLog.timestamp.desc(), AccessLog.id.desc())


@activity.get("/access-logs")
def index():
    snapshot, integrity = authorized_snapshot()
    if not integrity.valid:
        return render_workspace("activity.html", integrity=integrity, active="activity", status=503)
    statement, actions, filters = filtered_activity(snapshot)
    page = max(1, request.args.get("page", 1, type=int))
    # Bound the offset by the actual count, including for arbitrary page numbers.
    total = db.session.scalar(db.select(db.func.count()).select_from(statement.subquery()))
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, last_page)
    logs = db.session.scalars(newest_first(statement).options(joinedload(AccessLog.actor))
                              .limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)).all()
    return render_workspace("activity.html", logs=logs, actions=actions, decision=filters["decision"],
                            action=filters["action"], search=filters["q"], page=page, last_page=last_page,
                            total=total, snapshot=snapshot, active="activity", integrity=integrity)


def spreadsheet_text(value):
    """Keep report text literal if opened in a spreadsheet."""
    # Some importers skip leading whitespace or invisible format characters.
    leading = next((char for char in value if not char.isspace()
                    and unicodedata.category(char) not in {"Cc", "Cf"}), "")
    if (leading and leading in "=+-@＝＋－＠") or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


@activity.get("/access-logs/export.csv")
def export():
    snapshot, integrity = authorized_snapshot()
    if not integrity.valid:
        return render_workspace("activity.html", integrity=integrity, active="activity", status=503)
    statement, _, _ = filtered_activity(snapshot)
    report_rows = newest_first(statement.with_only_columns(
        AccessLog.id, AccessLog.timestamp, AccessLog.actor_user_id, User.display_name, AccessLog.actor_role,
        AccessLog.action, AccessLog.resource, AccessLog.decision
    ).outerjoin(AccessLog.actor))
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(("Audit entry ID", "UTC timestamp", "Actor name", "Historical actor role",
                     "Requested action", "Resource", "Authorization decision"))
    for identity, occurred, actor_id, name, role, action, resource, decision in db.session.execute(report_rows):
        writer.writerow((identity, occurred.isoformat(),
                         spreadsheet_text(name or ("Anonymous" if actor_id is None else "Unknown")),
                         spreadsheet_text(role or ("" if actor_id is None else "Unknown")),
                         spreadsheet_text(action), spreadsheet_text(resource), decision))
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="recorded-audit-events.csv"'})
