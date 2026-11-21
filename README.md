# SecureRole — RBAC Simulator

SecureRole is a university PBL project using Python, Flask, Flask-SQLAlchemy,
Flask-Login, SQLite, Werkzeug and python-dotenv. Phase 3 implements the database
foundation. Phase 4 adds session authentication and temporary dashboards for
Admin, Teacher and Student accounts. Phase 5 adds centralized authorization
and audit logging using the existing database schema. Phase 6 adds the
role dashboards, academic record management, account management and access logs.
Phase 7 strengthens session and input security and verifies the PBL acceptance criteria.
Phase 7.1 adds persistent throttling, server-side sessions, historical audit roles,
database triggers and a verifiable audit chain. Phase 7.2 adds a reproducible classroom demo roster.

## Setup and database initialization

Run these commands from the project root (Linux/macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
test -e .env || cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
```

Put the generated value in `.env` as `SECRET_KEY`. Run the generator again
and set the different value as `AUDIT_INTEGRITY_KEY`. Keep both independent
random values private. Existing shell environment variables take precedence
over `.env`. The factory rejects missing or placeholder keys. Git ignores
`.env`, `.venv`, `instance/`, and SQLite database files.

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

### Upgrading an existing database

Stop the running application before upgrading. Back up the database and retain
the audit key separately in protected storage. The backup destination must be
a new file.

```bash
flask --app run backup-db instance/securerole.phase7-backup.db
flask --app run migrate-db
flask --app run verify-audit
```

The first migration moves the Phase 7 schema from SQLite `user_version` 0 to
1, preserves original rows, installs integrity triggers and signs existing
audit rows as a migration baseline. Re-running it is safe with the matching
key. `init-db` and `seed-db` use the same migration path. If an upgrade fails,
keep the backup and resolve the reported issue before retrying. To roll back
after a successful upgrade, stop the app and restore the backup together with
the corresponding app version. Store backups in a protected location and
exclude them from Git.

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

### Expanded classroom demo

Start from a database initialized with `init-db` or from the original six-account
demo. For an existing version 0 database, back it up with the server stopped and
apply the migration above first. Then expand the roster.

```bash
flask --app run seed-demo
flask --app run verify-audit
python run.py
```

The expanded dataset contains **2 Admins, 12 Teachers and 120 Students** across
six subjects, with exactly 10 students per teacher. There are **110 academic
records** and **10 students awaiting records**. The original six accounts
retain their passwords, assignments, and existing records. Missing email
addresses are filled with fictional institutional addresses.

`seed-demo` saves credentials for new accounts only to
`instance/securerole.demo-credentials.csv` with owner-only permissions. Keep
that Git-ignored file private. Use the saved `seed-db` password for an original
account. A fresh expanded installation includes credentials for its six
newly created starter accounts as well. Running the command again preserves the
credentials file and existing records. The command reports a conflict rather
than replacing data if a database contains incompatible or unrelated accounts.

See [the demo dataset guide](docs/demo-dataset.md) for recommended usernames,
subject groups, and a walkthrough that creates genuine audit activity using
the normal application forms.

## Signing in and out

Sign in with a demo username and its saved password from `seed-db` or the private
`seed-demo` credentials file. An existing account keeps its password when reseeded. If the
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

Sessions expire eight hours after sign-in. **Active sessions** lets you sign out
a single session or all sessions for your account. A password reset revokes all
prior sessions, and the Phase 7.1 upgrade requires a fresh sign-in. Demo
accounts and passwords are preserved. The session cookie holds a random
token and SQLite stores a SHA-256 digest rather than the token itself.

Valid sign-in form submissions reserve a slot before password checking. The
default fixed window is 60 seconds, with 10 attempts per source address and
5 attempts per source-address-and-username pair. Set positive integers in
`LOGIN_WINDOW_SECONDS`, `LOGIN_SOURCE_LIMIT`, and `LOGIN_ACCOUNT_LIMIT` to tune
these defaults. Both successful and failed attempts count. A blocked attempt
receives HTTP 429 and `Retry-After` and does not extend the window. Counters
survive restarts on the same database and signing key. Expired counters are
removed during later sign-in attempts.

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

The app retains account and audit history without an account deletion workflow.
Activity shows historical roles for new entries, **Unknown** for legacy
authenticated entries, and **Anonymous** when there is no actor. The admin
activity page checks the local audit chain. Store a verified checkpoint
reported by `verify-audit` in trusted storage outside the database and use
`flask --app run verify-audit --checkpoint ID:MAC` to detect rollback past it.
Local verification depends on the dedicated audit key and trusted integrity
state. There is no email or self-service reset. SQLite is intended for the
scale of this simulator.

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

SQLite enforces required columns, uniqueness, foreign keys and marks bounds.
Version 1 triggers enforce Student record ownership, Teacher assignments,
dependent role changes, last-Admin preservation after bootstrap, password
reset revocation and append-only audit writes. ORM validation remains in
place for friendly errors. External SQLite clients should enable foreign
keys and preserve the installed schema and triggers.

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
