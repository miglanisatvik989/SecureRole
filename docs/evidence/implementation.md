# SecureRole implementation evidence

These excerpts come from the final application. They follow a request from sign-in through authorization, persistence and audit verification. The [evidence index](screenshot-index.md) links the corresponding browser views.

## Password hashing and verification

Werkzeug stores a salted password hash. At sign-in, Werkzeug checks the submitted password against that hash.

**Security concept** · One-way password storage.

**Source** · `User.set_password and User.check_password` in [app/models.py](../../app/models.py#L127).

```python
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
```

## Authentication and session creation

The app looks up the username, does hash work even for a missing account, and establishes a server-side session before setting the Flask-Login identity. The session row stores the token digest and expiry.

**Security concept** · Credential verification and session establishment.

**Source** · `login` in [app/auth.py](../../app/auth.py#L32).

```python
        user = db.session.scalar(db.select(User).filter_by(username=form.username.data))
        if user is None:
            check_password_hash(_missing_user_hash, form.password.data)
        elif user.check_password(form.password.data):
            session.clear()
            if not bind_session(user):
                return render_template("login.html", form=LoginForm(formdata=None),
                                       error="Invalid username or password."), 401
            login_user(user)
            destination = dashboard_url(user)
```

[Session binding and expiry](../../app/session_security.py#L34) · [Figure 1](../screenshots/authentication/01-login.png).

## Centralized RBAC policy

One policy maps operations and stored roles to their possible record scope. Missing grants produce no scope.

**Security concept** · Least privilege and default deny.

**Source** · `permission_scope and _RECORD_SCOPES` in [app/rbac.py](../../app/rbac.py#L26).

```python
_RECORD_SCOPES = {
    Action.VIEW_RECORD: {"Admin": "all", "Teacher": "assigned", "Student": "own"},
    Action.CREATE_RECORD: {"Admin": "all", "Teacher": "assigned"},
    Action.EDIT_RECORD: {"Admin": "all", "Teacher": "assigned"},
    Action.DELETE_RECORD: {"Admin": "all"},
}
_ADMIN_RESOURCES = {
    Action.LIST_RECORDS: "student_records",
    Action.MANAGE_USERS: "users",
    Action.ASSIGN_ROLES: "roles",
    Action.ASSIGN_TEACHERS: "teacher_assignments",
    Action.VIEW_ACCESS_LOGS: "access_logs",
}


def permission_scope(role, action):
    """Describe role-level access from the same rules used by route guards."""
    if action in _RECORD_SCOPES:
        return _RECORD_SCOPES[action].get(role)
    if action in _ADMIN_RESOURCES and role == "Admin":
        return "allowed"
    return None
```

## Record ownership and teacher assignment

The query first limits candidates to Student accounts. It then verifies the actor's stored role and applies the corresponding ownership or assignment check.

**Security concept** · Object-level authorization.

**Source** · `_student_ids` in [app/rbac.py](../../app/rbac.py#L54).

```python
def _student_ids(actor_id, action):
    """Select eligible Student IDs using the stored role and assignment in SQL."""
    statement = db.select(User.id).where(User.role.has(Role.name == "Student"))
    if not _valid_id(actor_id) or not isinstance(action, str) or action not in _RECORD_SCOPES:
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
```

## Permission-scoped queries

The same restriction applies when fetching Student accounts and existing records. Unsupported record-query actions return an empty query.

**Security concept** · Database-side data isolation.

**Source** · `scoped_students and scoped_records` in [app/rbac.py](../../app/rbac.py#L78).

```python
def scoped_students(actor_id, action=Action.VIEW_RECORD):
    """Select student accounts in scope, including students without a record."""
    return db.select(User).where(User.id.in_(_student_ids(actor_id, action)))


def scoped_records(actor_id, action=Action.VIEW_RECORD):
    """Build a selectable for existing records. Execute it in the operation's transaction."""
    statement = db.select(StudentRecord)
    if action not in (Action.VIEW_RECORD, Action.EDIT_RECORD, Action.DELETE_RECORD):
        return statement.where(false())
    return statement.where(StudentRecord.student_user_id.in_(_student_ids(actor_id, action)))
```

## CSRF protection

The application factory installs CSRF protection globally. The form supplies a token that Flask-WTF checks on submission.

**Security concept** · Cross-site request forgery prevention.

**Source** · `create_app` in [app/__init__.py](../../app/__init__.py#L40).

```python
    login_manager.init_app(app)
    app.before_request(validate_request_session)
    csrf.init_app(app)
```

The [login template](../../app/templates/login.html#L14) includes the token with `{{ form.hidden_tag() }}`. Workspace forms render the same hidden token. The [sign-out form](../../app/templates/dashboard.html#L40) renders the CSRF field explicitly.

## Authorized database transactions

The write callback checks permission against the intended Student and stages the Allowed event before adding the record. The transaction helper reserves the writer, revalidates the session and commits both changes together or rolls them back.

**Security concept** · Atomicity and authorization at write time.

**Source** · `create` in [app/records.py](../../app/records.py#L78).

```python
        def change():
            require_permission(Action.CREATE_RECORD, student_id=student_id, atomic=True)
            student = db.session.get(User, student_id, populate_existing=True)
            if student.student_record is not None:
                raise ValueError("This student already has an academic record.")
            db.session.add(StudentRecord(student=student, course=form.course.data, marks=form.marks.data))
```

[Transaction helper](../../app/workspace.py#L21) · [Figure 21](../screenshots/security/21-operation-success.png).

## Session revocation

Only the signed-in account's active session rows can be revoked. Later requests check the row's status before authorization.

**Security concept** · Server-side session invalidation.

**Source** · `revoke` in [app/session_security.py](../../app/session_security.py#L92).

```python
def revoke(*, identity=None, all_sessions=False):
    """Revoke only sessions belonging to the signed-in account."""
    if identity is not None and not 0 < identity <= 2**63 - 1:
        abort(404)
    with db.engine.begin() as connection:
        now = int(time())
        conditions = [AuthSession.user_id == current_user.id, AuthSession.revoked_at.is_(None),
                      AuthSession.expires_at > now]
        if identity is not None:
            conditions.append(AuthSession.id == identity)
        elif not all_sessions:
            conditions.append(AuthSession.token_digest == token_digest())
        revoked = connection.execute(update(TABLE).where(*conditions).values(revoked_at=now)
                                     .returning(AuthSession.token_digest)).scalars().all()
    if identity is not None and not revoked:
        abort(404)
    return all_sessions or token_digest() in revoked
```

## Login throttling

The app counts attempts by source and by source plus account. One SQLite writer reservation prevents concurrent requests from consuming the same quota slot. A blocked attempt receives a retry interval.

**Security concept** · Persistent rate limiting.

**Source** · `reserve_attempt` in [app/login_limits.py](../../app/login_limits.py#L34).

```python
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
```

## Database-level integrity rules

SQLite triggers use these predicates to reject an ineligible record owner or teacher assignment, including direct database writes outside the ORM.

**Security concept** · Defense in depth and relational integrity.

**Source** · `install_rules, ASSIGNMENT_INVALID and OWNER_INVALID` in [app/schema_rules.py](../../app/schema_rules.py#L72).

```python
ASSIGNMENT_INVALID = """NEW.assigned_teacher_id IS NOT NULL AND (
    NEW.assigned_teacher_id=NEW.id
    OR (SELECT name FROM roles WHERE id=NEW.role_id) IS NOT 'Student'
    OR (SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id
        WHERE u.id=NEW.assigned_teacher_id) IS NOT 'Teacher'
)"""

OWNER_INVALID = """(SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id
                    WHERE u.id=NEW.student_user_id) IS NOT 'Student'"""
```

## Audit logging

An authorization check records who acted, what action and resource were evaluated, the historical role and the decision. The model supplies a UTC timestamp.

**Security concept** · Accountability and data minimization.

**Source** · `stage_access_log` in [app/audit.py](../../app/audit.py#L8).

```python
def stage_access_log(session, *, actor_id, action, resource, allowed, actor_role=None):
    """Stage an event in the caller's transaction. Use policy-defined labels."""
    session.add(AccessLog(
        actor_user_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource=resource,
        decision="Allowed" if allowed else "Denied",
    ))
```

## Audit integrity calculation

The function normalizes the timestamp and signs the ordered fields, including the previous MAC, with a separate audit key.

**Security concept** · HMAC-SHA256 and chained authentication.

**Source** · `entry_mac` in [app/audit_integrity.py](../../app/audit_integrity.py#L31).

```python
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
```

## Audit integrity verification

Verification recomputes MACs in ID order and checks the stored head. An optional independently stored checkpoint ties the journal to an earlier trusted state.

**Security concept** · Detection of changes to recorded history.

**Source** · `verify_chain` in [app/audit_integrity.py](../../app/audit_integrity.py#L109).

```python
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
```

## Final architecture diagrams

| Diagram | Editable Mermaid | Vector image |
| --- | --- | --- |
| System architecture | [Source](../diagrams/system-architecture.mmd) | [SVG](../diagrams/system-architecture.svg) |
| Authentication workflow | [Source](../diagrams/authentication-workflow.mmd) | [SVG](../diagrams/authentication-workflow.svg) |
| Authorization workflow | [Source](../diagrams/authorization-workflow.mmd) | [SVG](../diagrams/authorization-workflow.svg) |
| Seven-table database ERD | [Source](../diagrams/database-erd.mmd) | [SVG](../diagrams/database-erd.svg) |
| HMAC-SHA256 audit chain | [Source](../diagrams/audit-chain.mmd) | [SVG](../diagrams/audit-chain.svg) |

See the [database schema reference](../diagrams/database-schema.md) for detailed column constraints, relationships and trigger behavior.
