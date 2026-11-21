"""Serialize and verify the version 1 HMAC-linked authorization journal."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest, digest

from flask import current_app
from sqlalchemy import event, select, text

from app.models import AccessLog, AuditHead, Role, User

GENESIS = "0" * 64
KEY_CONTEXT = b"securerole:audit-key-check:v1"
FIELDS = ("id", "actor_user_id", "actor_role", "action", "resource",
          "decision", "timestamp", "previous_mac")


class AuditIntegrityError(RuntimeError):
    """The app cannot safely append to the configured audit journal."""


def audit_key():
    return current_app.config["AUDIT_INTEGRITY_KEY"].encode("utf-8")


def key_tag(key):
    return digest(key, KEY_CONTEXT, "sha256").hex()


def entry_mac(key, entry):
    stamp = entry["timestamp"]
    if isinstance(stamp, str):
        stamp = datetime.fromisoformat(stamp)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)  # SQLite stores UTC without an offset.
    values = [entry[name] if name != "timestamp" else
              stamp.astimezone(timezone.utc).isoformat(timespec="microseconds") for name in FIELDS]
    payload = json.dumps(["securerole:audit:v1", *values], ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return digest(key, payload, "sha256").hex()


def stored_role(connection, actor_id):
    if actor_id is None:
        return None
    return connection.scalar(select(Role.name).join(User, User.role_id == Role.id).where(User.id == actor_id))


def head(connection):
    return connection.execute(select(AuditHead.__table__).where(AuditHead.id == 1)).mappings().one_or_none()


def valid_mac(left, right):
    return isinstance(left, str) and left.isascii() and compare_digest(left, right)


@event.listens_for(AccessLog, "before_insert")
def sign_entry(mapper, connection, log):
    if log.timestamp is None:
        log.timestamp = datetime.now(timezone.utc)
    if log.timestamp.utcoffset() is None:
        return  # The model's datetime binder rejects naive datetimes.
    # Take SQLite's writer lock before reading the head, including standalone read audits.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    state = head(connection)
    key = audit_key()
    if state is None or not valid_mac(state["key_tag"], key_tag(key)):
        raise AuditIntegrityError("Audit state or configured key is invalid.")
    tail = connection.execute(text("SELECT * FROM access_logs ORDER BY id DESC LIMIT 1")).mappings().first()
    if tail is None:
        if state["head_id"] != 0 or state["head_mac"] != GENESIS:
            raise AuditIntegrityError("The audit head does not match the journal.")
    else:
        try:
            calculated = entry_mac(key, tail)
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            raise AuditIntegrityError("The audit tail has invalid fields.") from error
        if (tail["id"] != state["head_id"] or not valid_mac(tail["entry_mac"], state["head_mac"])
                or not valid_mac(tail["entry_mac"], calculated)):
            raise AuditIntegrityError("The audit head does not match the journal.")
    log.id = state["head_id"] + 1
    log.previous_mac = state["head_mac"]
    if log.actor_user_id is not None and log.actor_role is None:
        log.actor_role = stored_role(connection, log.actor_user_id)
    log.entry_mac = entry_mac(key, {name: getattr(log, name) for name in FIELDS})


@dataclass(frozen=True)
class Verification:
    valid: bool
    message: str
    count: int = 0
    head_id: int = 0
    head_mac: str = GENESIS


def verify_chain(connection, key, checkpoint=None):
    """Read a single snapshot, optionally corroborated by an external (ID, MAC)."""
    state = head(connection)
    if state is None or not valid_mac(state["key_tag"], key_tag(key)):
        return Verification(False, "Audit state or configured key is invalid.")

    last_id, previous, count = 0, GENESIS, 0
    anchored = checkpoint is None
    # Read the original SQLite timestamp representation so malformed data
    # becomes a failed verification instead of a date converter exception.
    rows = connection.execute(text("SELECT * FROM access_logs ORDER BY id")).mappings()
    for row in rows:
        try:
            calculated = entry_mac(key, row)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return Verification(False, f"Invalid audit fields at entry {row['id']}.", count)
        if (row["id"] <= last_id or not valid_mac(row["previous_mac"], previous)
                or not valid_mac(row["entry_mac"], calculated)):
            return Verification(False, f"Integrity mismatch at entry {row['id']}.", count)
        last_id, previous, count = row["id"], calculated, count + 1
        if checkpoint is not None and last_id == checkpoint[0]:
            anchored = valid_mac(checkpoint[1], previous)

    if state["head_id"] != last_id or not valid_mac(state["head_mac"], previous):
        return Verification(False, "The audit head does not match the journal.", count)
    if not anchored:
        return Verification(False, "The trusted checkpoint does not match the journal.", count)
    return Verification(True, "Audit chain verified.", count, last_id, previous)


def inspect_audit(engine, key, checkpoint=None):
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN")
        return verify_chain(connection, key, checkpoint)
