# Authorization architecture and workflow

Flask-Login resolves the session's user ID. Each dashboard or management route passes that
identity to `require_permission` with a policy action and target. The policy
queries the stored role and, for records, the owning student's ID and teacher
assignment. Authorization reads use the database transaction's view of the
rows. The audit module writes the decision before the route returns a response.

```mermaid
flowchart TD
    A[Dashboard request] --> B[Resolve user identity with Flask-Login]
    B --> C[Check permission against SQLite]
    C --> D[Append access log]
    D --> E{Decision}
    E -->|Allowed| F[Render dashboard or redirect to own page]
    E -->|Denied, signed in| G[Access Restricted page with HTTP 403]
    E -->|Denied, anonymous| H[Redirect to sign-in]
```

## Using the policy from a route

| API | Purpose |
| --- | --- |
| `is_allowed(actor_id, action, ...)` | Evaluate a single permission without logging |
| `scoped_students(actor_id, action)` | Build a select for student accounts, including those without records |
| `scoped_records(actor_id, action)` | Build a SQLAlchemy select for view, edit or delete scope |
| `require_permission(action, ...)` | Evaluate and log the decision, then stop the request on denial |
| `stage_access_log(session, ...)` | Stage an audit row in the caller's transaction |

Use a constant from `Action` and derive the actor identity from Flask-Login.
Pass `student_id` for creation, `record_id` for view, edit or deletion, and
`dashboard_role` for a specific dashboard. The dispatcher uses the dashboard
action with no role target. Unrecognized actions and malformed targets are
denied. They cannot add unchecked values to audit labels.

For a record list, execute `scoped_records` as the data query and further filter
it as needed. It evaluates scope at query execution. For a single object, use
the corresponding guard before reading or changing the object. Authorization
answers whether the actor may perform the action. Model validation and database
constraints still handle input and invariants such as one record per Student.

## Transaction boundaries and limits

Call guards before staging business changes. Ordinary guards persist the audit
entry in a separate transaction, including denials. The audit entry records
authorization, so an allowed read can still fail later while rendering.
For create, edit and delete routes, pass `atomic=True` to the guard. An allowed
entry is then staged in the same session as the write. Commit both together, or
roll back both if validation or the database rejects the write. A denied write
still commits its audit row independently, before the response.

Phase 6 mutations that pass form validation use `BEGIN IMMEDIATE` before their
authorization and invariant checks. Phase 7 also rechecks the session's
credential binding inside this reservation, so a reset that committed first
blocks the mutation. SQLite holds the reservation through the record or account
change and audit commit. An atomic denial releases that
reservation before persisting its denial independently. The same reservation
serializes the last-Admin check. Invalid submissions and failed commits leave
no successful mutation audit row. Opening an authorized form can still add a
separate Allowed decision.

If a standalone audit insert fails, the request fails before it serves the
protected page. Audit rows live in the same SQLite database as application data
and are not tamper-evident. Logged actor references restrict hard deletion, and
role labels in the activity view reflect current roles because the schema stores
actor IDs rather than an event-time role snapshot.
