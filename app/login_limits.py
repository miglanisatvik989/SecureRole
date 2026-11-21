"""Persistent fixed-window login throttling using SQLite writer serialization."""

from hmac import digest
import ipaddress
from time import time

from flask import current_app, request
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert

from app.models import LoginWindow, db


def bucket_key(scope, *parts):
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode()
    data = "\0".join(("securerole:login:v1", scope, *parts)).encode()
    return digest(secret, data, "sha256").hex()


def source_address():
    # Do not read forwarded client-address headers directly.
    source = request.remote_addr
    try:
        address = ipaddress.ip_address(source)
    except ValueError:
        return source or "unknown"
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped.compressed
    return address.compressed


def reserve_attempt(username):
    """Return retry seconds if throttled, otherwise reserve a slot before hashing."""
    address = source_address()
    limits = {
        bucket_key("source", address): current_app.config["LOGIN_SOURCE_LIMIT"],
        bucket_key("source-account", address, username): current_app.config["LOGIN_ACCOUNT_LIMIT"],
    }
    duration = current_app.config["LOGIN_WINDOW_SECONDS"]
    with db.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        now = int(time())
        connection.execute(delete(LoginWindow).where(LoginWindow.expires_at <= now))
        current = connection.execute(select(LoginWindow.__table__).where(
            LoginWindow.bucket.in_(limits)
        )).mappings().all()
        retry = max((row["expires_at"] - now for row in current
                     if row["attempts"] >= limits[row["bucket"]]), default=0)
        if not retry:
            for bucket in limits:
                statement = insert(LoginWindow).values(bucket=bucket, attempts=1, expires_at=now + duration)
                connection.execute(statement.on_conflict_do_update(
                    index_elements=[LoginWindow.bucket], set_={"attempts": LoginWindow.attempts + 1}
                ))
        connection.commit()
    return retry
