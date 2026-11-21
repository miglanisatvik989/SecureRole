# Phase 7 security analysis

This source review covers authentication, input validation, route authorization,
SQLite writes, the audit trail and browser controls. Phase 7 closes the
password reset session gap, bounds session age and request sizes, and adds
browser response protections. The schema, demonstration data and Phase 6
interface are preserved. See [measured results](test-results.md).

## Source findings and remediation

| ID and priority | Finding and impact | Implemented change and evidence |
| --- | --- | --- |
| 01 · High · FLASK-SESS-002 | The signed session previously identified only the user. A password reset changed the stored hash while leaving existing sessions usable. | Sign-in sets a keyed HMAC tag derived from the account ID and current stored hash, plus an absolute eight-hour deadline. The cookie carries neither the password nor the hash. Every authenticated request checks the tag, and writes recheck it after acquiring the SQLite reservation. See [session security](../app/session_security.py#L21), [transaction code](../app/workspace.py#L21), and the reset and expiry tests in [test_security.py](../tests/test_security.py). |
| 02 · Medium · FLASK-HEADERS-001 | The app did not send a browser policy for scripts, frames or form destinations. | Central response handling restricts resources and forms to the same origin, blocks framing and plugins, disables MIME sniffing, and sets a same-origin referrer policy compatible with Flask-WTF's HTTPS Referer check. Authenticated pages retain `no-store`. See [response headers](../app/__init__.py#L49) and `test_headers_and_request_limit`. |
| 03 · Medium · FLASK-CONFIG-001 / FLASK-HOST-001 | Startup rejected a missing signing key but accepted the example key. Host rules were unspecified. | Reject the example key. Retain the environment-supplied random secret and add an optional explicit host allowlist for hosted use. Keep host-only, HTTP-only, SameSite=Lax cookies and enable Secure when serving HTTPS. See [factory](../app/__init__.py#L18), [configuration](../config.py#L14), and the example-key, host and HTTPS cookie tests. |
| 04 · Low · FLASK-LIMITS-001 | The login form lacked application field lengths, and the app lacked a request body cap. Account and course text could include control characters. | Bound login to the existing account limits, cap form bodies at 64 KiB and multipart submissions at 32 fields, reject non-printing account and course text, and reject all-whitespace new passwords. Preserve printable Unicode and meaningful password whitespace. See [forms](../app/forms.py#L10), [configuration](../config.py#L14), and validation tests in [test_security.py](../tests/test_security.py). |
| 05 · Low · Error handling | SQLAlchemy's default diagnostics can show bound values when a statement fails. Invalid session identities also needed a SQLite integer range check. | Hide statement parameters in SQLAlchemy diagnostics and reject out-of-range user IDs before querying. Mutation errors retain controlled messages and roll back. See [configuration](../config.py#L12), [user loader](../app/__init__.py#L63), and [transaction code](../app/workspace.py#L21). |

## Controls reviewed and evidence

- **Credentials and redirects.** The installed Werkzeug default generates salted
  scrypt hashes for new and reset passwords. Existing hashes are validated
  with Werkzeug and are preserved. Existing and unknown usernames receive the
  same credential error. The missing-user path also performs a password hash
  check. A successful login clears previous session state and only honors the
  app's own dashboard dispatcher as a return destination. Existing tests cover
  password storage, invalid credentials and redirects. See [models](../app/models.py#L127),
  [authentication](../app/auth.py#L20), and the [Werkzeug security helpers](https://werkzeug.palletsprojects.com/en/stable/utils/#module-werkzeug.security).
- **CSRF and rendering.** Flask-WTF protects form submissions globally, including
  sign-in, sign-out and all management writes. Existing tests verify invalid,
  missing and cross-session tokens. Jinja autoescapes stored values, and the
  frontend uses local scripts without writing untrusted HTML into the DOM. The
  browser walkthrough verified local styles, fonts, password visibility and
  the confirmation dialog under CSP. See [Flask security guidance](https://flask.palletsprojects.com/en/stable/web-security/).
- **RBAC and inputs.** The backend checks stored roles and filters record scope
  by owner or teacher assignment in SQL. The app uses SQLAlchemy expressions
  with bound values, including escaped literal search terms in the audit view.
  The only transaction SQL added by the workspace is fixed `BEGIN IMMEDIATE`.
  Model and form validations cover required data, field lengths, finite marks
  from 0 to 100, eligible roles and teachers, unique records and preservation of
  at least one Admin. See [policy](../app/rbac.py#L44),
  [model validation](../app/models.py#L210), [account checks](../app/accounts.py#L59),
  and the database, feature and acceptance tests.
- **Audit.** Decisions record actor ID or NULL for anonymous access, fixed action
  and resource labels, Allowed or Denied, and UTC time. The guarded write and
  its success entry share a transaction. Denials persist separately and failed
  writes leave no successful mutation entry. Audit labels exclude passwords,
  secrets, session contents and query strings. See [audit module](../app/audit.py#L8),
  [policy guard](../app/rbac.py#L137), [reset regression](../tests/test_security.py),
  and [T1–T11](test-results.md).

## Remaining limits and proposed improvements

- **Audit integrity and history.** SQLite audit rows can be changed by operators
  with database write access. The actor column stores an ID, so the UI shows
  their current role. For stronger evidence, add event-time role snapshots and
  a protected append-only audit destination or integrity verification.
- **Database invariants.** Cross-table role consistency depends on ORM
  validation. Direct SQL bypasses it. Restrict writes to the application and
  consider enforced database invariants if the schema can change.
- **Session boundaries.** Password reset revocation is implemented with a
  credential check. The app still uses signed client-side cookies. Sign-out
  clears the current browser's cookie. There is no server-side list of
  individual sessions to revoke, and a read already authorized before a reset
  can finish. A future server-side session store could support per-session
  revocation and device management.
- **Hosting.** The local simulator has no login rate limiter, MFA or self-service
  recovery. Before exposing it beyond a trusted classroom environment, add
  edge or shared login throttling, HTTPS with Secure cookies, and an explicit
  trusted host list. Keep the random signing key outside version control and
  rotate it if disclosed. Use a production WSGI server for hosted deployments.

This review and its tests assess source controls and documented behavior.
Infrastructure settings and third-party dependency advisories were outside
the measured test run.

## Phase 7.1 advanced hardening

| Phase 7 limitation | Phase 7.1 status |
| --- | --- |
| No login limiter | SQLite-backed fixed windows apply before password verification. The default caps are 10 per source and 5 per source and username over 60 seconds. SQLite serializes reservations, and denied reservations do not extend expiry. |
| No server-side or individual revocation | Random session tokens map to database rows through SHA-256 digests. Each row records its account, creation, expiration and revocation time. The user can revoke an owned session or all sessions. Password hash changes revoke all sessions in the same database transaction. |
| Actor role reflected current role | New logs store the role at authorization. Legacy authenticated rows remain unknown, even when the account still exists. Anonymous events carry a NULL actor and role. |
| Cross-table rules enforced only by ORM | Version 1 triggers protect ownership, teacher assignments, dependent role changes, fixed role definitions and last-Admin preservation. ORM checks still produce friendly errors. |
| SQLite audit trail lacked tamper evidence | Appended entries are linked with HMAC-SHA256. SQLite rejects journal updates, deletes and structurally invalid appends. Local verification remains conditional on trusted state and a protected audit key. |

### Audit design and key custody

Werkzeug password hashing is a slow, salted password verification mechanism.
Audit HMAC instead authenticates stored data and its position in a sequence.
The audit key must be independent of Flask's signing key. Store it separately
in protected secret storage and retain it with the backup recovery plan.
Generate it with a cryptographically secure random generator. Do not replace
it in place. Key rotation and continuity across key versions would require a
planned migration.

[The serializer](../app/audit_integrity.py) uses a fixed ordered JSON array
with a version marker, ID, actor ID, role snapshot, action, resource, decision,
normalized UTC timestamp with microseconds, and prior hexadecimal MAC.
The UTF-8 bytes are authenticated with HMAC-SHA256. The genesis link is
64 zeros. SQLite serializes appends and maintains the singleton audit head
in the same transaction. The signer checks the tail before appending.
The verifier reads a single snapshot and checks every link, MAC and the
recorded head. The CLI opens the database read-only and returns a nonzero
status on verification failure. The admin activity view shows the local
verification result. See [Python's HMAC documentation](https://docs.python.org/3/library/hmac.html)
and [SQLite trigger behavior](https://www.sqlite.org/lang_createtrigger.html).

The migration preserves legacy entries and signs their current contents as
a baseline. A valid baseline establishes continuity from migration, without
evidence of changes that may have occurred before migration. SQLite triggers
are application-level protection against ordinary writes and do not stop an
operator with unrestricted file or schema access. Local checks alone cannot
distinguish an authentic older backup from the current database if both the
journal and its head were rolled back together. Save a verified `ID:MAC`
checkpoint externally and supply it to `verify-audit --checkpoint` to require
continuity through that entry. A key compromise defeats the HMAC assurance.

### Session and limiter boundaries

The browser token is a bearer credential carried in the signed, HTTP-only
cookie. The database holds a digest, and the UI exposes a scoped revocation
reference and timestamps without showing either token or digest. The existing
eight-hour deadline and credential binding remain checked. Protected writes
recheck the session inside the database writer reservation. Requests already
authorized before revocation can finish reading. Expired and revoked session
rows are retained and need a retention policy for long-term deployment.

Counters store keyed buckets rather than raw addresses or usernames. They are
shared by workers using the same SQLite database and Flask signing key. Changing
that key changes bucket identifiers. The limiter uses the server's peer address
and does not trust forwarded headers from a client. Shared addresses may share
quota, and a per-source limiter does not provide global account lockout across
many independent sources. Hosted deployments can add a trusted proxy, shared
edge throttling, MFA and a retention policy.
