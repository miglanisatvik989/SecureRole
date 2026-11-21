"""Write authorization decisions to the existing access log."""

from sqlalchemy.orm import Session

from app.models import AccessLog, db


def stage_access_log(session, *, actor_id, action, resource, allowed):
    """Stage an event in the caller's transaction. Use policy-defined labels."""
    session.add(AccessLog(
        actor_user_id=actor_id,
        action=action,
        resource=resource,
        decision="Allowed" if allowed else "Denied",
    ))


def commit_access_log(**event):
    """Persist a standalone decision without committing the caller's changes."""
    with Session(db.engine) as session, session.begin():
        stage_access_log(session, **event)
