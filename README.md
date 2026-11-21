# SecureRole — RBAC Simulator

SecureRole is a university PBL project using Python, Flask, Flask-SQLAlchemy,
Flask-Login, SQLite, Werkzeug and python-dotenv. Phase 3 implements the database
foundation. Phase 4 adds session authentication and temporary dashboards for
Admin, Teacher and Student accounts. Phase 5 adds centralized authorization
and audit logging using the existing database schema. Phase 6 adds the
role dashboards, academic record management, account management and access logs.
Phase 7 strengthens session and input security and verifies the PBL acceptance criteria.

## Setup and database initialization

Run these commands from the project root (Linux/macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
```

Put the generated value in `.env` as `SECRET_KEY=your-generated-value`. Existing
shell environment variables take precedence over `.env`. The factory reports a
clear error if no secret is configured. `.env`, `.venv`, `instance/`, and SQLite
database files are ignored by Git; `.env.example` contains no real secret.

```bash
# Create the four tables without adding demonstration data:
flask --app run init-db

# Create tables if needed, then add the fictional demonstration data:
flask --app run seed-db

# Start the local development server:
python run.py
```

Both initialization commands preserve existing data. The configured relative
SQLite URI resolves through Flask's instance directory to
`instance/securerole.db`, regardless of the shell's working directory. SQLite
foreign-key enforcement is enabled on every SQLAlchemy connection. Open
`http://127.0.0.1:5000/` to reach the sign-in page.

`create_all()` creates missing tables; it does **not** migrate old schemas. If a
previous database has a different schema, retain a backup and migrate it before
using this implementation. Do not delete an existing database to initialize it.

## Demonstration data

On a fresh database, `seed-db` creates 3 roles, 6 users, 2 academic records and
0 access logs:

| Username | Role | Assigned teacher | Academic record |
| --- | --- | --- | --- |
| admin | Admin | — | — |
| teacher1 | Teacher | — | — |
| teacher2 | Teacher | — | — |
| student1 | Student | teacher1 | Cryptography and Network Security: 85 |
| student2 | Student | teacher1 | — |
| student3 | Student | teacher2 | Cryptography and Network Security: 78 |

Each new account receives an independently generated random password, printed
**only when that account is created**. Save the CLI output when first seeding;
passwords cannot be recovered from their hashes. Werkzeug hashes are the only
password values stored in the database. Application code should use
`user.set_password(value)` and `user.check_password(value)`.

Reseeding adds missing roles, accounts and demonstration records, while preserving
existing passwords, names, emails, assignments, marks and logs. It never truncates
or deletes data. An existing demo username with a different role causes the seed
transaction to roll back rather than changing that account. Credentials are
printed only after a successful commit. Other accounts and records are retained.

## Signing in and out

Sign in with one of the usernames above and its password from the original
`seed-db` output. An existing account keeps its password when reseeded. If the
original output is unavailable, use a freshly seeded, separate demo database
for the walkthrough.

Flask-WTF validates the required fields and the CSRF token. The login route
looks up the username and calls `User.check_password`, which uses Werkzeug
to compare the submitted password with the stored hash. Invalid credentials
receive the same error regardless of whether the username exists.

Flask-Login stores the user ID in the signed session and loads the account
from SQLite on subsequent requests. The stored role selects the dashboard.
Requests to another role's dashboard return 403. Only the app's own
dashboard entry point is honored as a return destination after sign-in.
The dashboard displays the signed-in user's name and role. Its **Sign out**
button submits a CSRF-protected POST and clears the login session.

Session cookies use HTTP-only and SameSite=Lax settings. Local HTTP works by
default. Set `SESSION_COOKIE_SECURE=1` in the environment or `.env` when
serving over HTTPS so the browser sends the session cookie only over HTTPS.
For a hosted instance, also set `TRUSTED_HOSTS` to its allowed hostnames, separated
by commas. Use a unique random secret and a production WSGI server for hosted use.

Sessions expire eight hours after sign-in. Password resets invalidate the
account's previous sessions when they are next checked. Existing browser
sessions from before Phase 7 require a fresh sign-in. The demo accounts
and their passwords are unchanged.

## Authorization and access logs

`app/rbac.py` checks permissions against roles and assignments stored in SQLite.
A missing actor, unknown action, or invalid target is denied. The dashboard guard
redirects anonymous visitors to sign-in and returns the Access Restricted page
with HTTP 403 when a signed-in user requests another role's dashboard.

| Operation | Admin | Teacher | Student |
| --- | --- | --- | --- |
| View records | All | Assigned only | Own only |
| Create records | All | Assigned only | Denied |
| Edit records | All | Assigned only | Denied |
| Delete records | All | Denied | Denied |
| Manage users | Allowed | Denied | Denied |
| Assign roles | Allowed | Denied | Denied |
| Assign teachers | Allowed | Denied | Denied |
| View access logs | Allowed | Denied | Denied |

Record view, edit and delete checks identify the owner through
`student_records.student_user_id`. To create a record, the target must be a
Student account. A Teacher can create, view or edit only when the student's
`assigned_teacher_id` matches the teacher's user ID. Students can view only
their own record. The scoped query applies these rules in SQL, before results
reach a route.

The dashboard and management routes record authorization decisions in UTC.
Entries include an actor ID (or NULL for anonymous visitors), a fixed action and
a resource label. They exclude passwords, session data and query strings.
Successful changes and their audit rows commit together. The authorization
decision to open a form is logged separately from the decision to submit it.
See the [authorization architecture and workflow](docs/authorization.md).

## Application workflows

- **Admin.** Overview shows live account, record and access counts, recent
  records and recent activity. Open **Student records** to view all records.
  **Add record** lists students who do not have one. Open an existing record
  to edit its course and marks or confirm deletion. Record ownership stays
  linked to the selected account.
- **Admin accounts.** Open **Users** to create an account, edit its details,
  assign a role or an eligible teacher, or reset its password. Choose an initial
  or replacement password of 12–128 characters and share it securely with the
  account owner. A student must lose their record before changing to a
  non-Student role. Reassign a teacher's students before changing their role.
  The last Admin cannot be demoted.
- **Teacher.** Open **My students** to see only assigned students. Use **Add
  record** for a student awaiting a record, or **View** and **Edit** for an
  existing one. Teacher accounts cannot delete records or manage accounts.
- **Student.** Open **My academic record** to see your course, marks and
  teacher, or a message that your record has yet to be added.
- **Admin activity.** Open **Access logs** to filter by decision, action, or
  search term. Search matches actor names, usernames, actions and resources.
  Each page shows up to 20 decisions. Pagination holds the results steady while
  new audit entries arrive. Reapply a filter to refresh the results.

The app retains account and audit history and provides no account deletion
workflow. Log roles reflect the actor's current account role. Audit rows are
not tamper-evident. Admin password resets revoke previous authentications.
There is no email or self-service reset. SQLite serializes writes and is
intended for the scale of this simulator.

## Database design

The [finalized schema and ERD](docs/diagrams/database-schema.md) lists every column,
constraint and relationship. The four model classes are in `app/models.py`:

- `Role`: one supported role per user; supported names are Admin, Teacher and Student.
- `User`: password hash, profile fields, role and optional teacher assignment.
- `StudentRecord`: at most one academic record per Student; numeric marks from 0 to 100.
- `AccessLog`: optional actor, action, resource, Allowed/Denied decision and UTC timestamp.

Reusable `validate_consistency(session)` methods run automatically before ORM
flushes. They check both relationship assignments and direct foreign-key edits,
including changes to a user's role that would invalidate existing students or
records. The full graph is checked because this is a small teaching simulator.
Validation raises `ValueError`; database constraints raise `IntegrityError`.
Call `db.session.rollback()` after either kind of failed write.

SQLite itself enforces required columns, unique values, foreign keys, supported
role names, marks bounds and log decisions. Cross-table role rules are enforced
by the ORM validation hook: use model instances for application writes. Bulk SQL
and external SQLite tools bypass that hook and must not be used to change roles,
record ownership or teacher assignments. Referenced rows cannot be deleted until
their references are explicitly handled; no delete cascades are configured.

Timestamps default to the current UTC time. The custom `UTCDateTime` type stores
UTC in SQLite and restores an aware UTC datetime when reading it; explicit
naive timestamps are rejected. Marks use `Float`, matching the original database,
with an explicit inclusive 0–100 check. Fractional marks are supported.

## Verification

See the [T1–T11 acceptance results](docs/test-results.md) and the
[Phase 7 security analysis](docs/security-analysis.md).

```bash
python -m pytest -q
```

Tests use a separate temporary SQLite file for each test and a test-only secret.
They do not alter `instance/securerole.db` or store demonstration passwords in
files. Coverage includes initialization, seed counts and repeatability, seed
rollback, password verification, relationships, invalid assignments and ownership,
role changes, foreign keys on multiple connections, unique/required constraints,
marks bounds, log decisions and UTC timestamp round trips. Raw SQL tests verify
SQLite constraints independently of Python validation. Authentication tests
cover login, form validation, role routing, safe redirects, access protection,
session persistence, logout and CSRF.

To inspect the local demonstration database without printing passwords:

```bash
flask --app run shell
```

```python
from app.models import db, Role, User, StudentRecord, AccessLog
from sqlalchemy import inspect, text
inspect(db.engine).get_table_names()
{model.__tablename__: db.session.scalar(db.select(db.func.count()).select_from(model))
 for model in (Role, User, StudentRecord, AccessLog)}
db.session.scalar(text("PRAGMA foreign_keys"))  # 1
db.session.execute(text("PRAGMA foreign_key_check")).all()  # []
```
