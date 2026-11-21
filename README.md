# SecureRole — RBAC Simulator

SecureRole is a university PBL project using Python, Flask, Flask-SQLAlchemy,
Flask-Login, SQLite, Werkzeug and python-dotenv. Phase 3 implements the database
foundation. Login routes, authorization rules, dashboards and CRUD pages belong
to later phases; visiting `/` currently returns 404.

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

# Start the application (database foundation only):
python run.py
```

Both initialization commands preserve existing data. The configured relative
SQLite URI resolves through Flask's instance directory to
`instance/securerole.db`, regardless of the shell's working directory. SQLite
foreign-key enforcement is enabled on every SQLAlchemy connection. Flask-Login
has a user loader; the login endpoint will be added in a later phase.

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

```bash
python -m pytest -q
```

Tests use a separate temporary SQLite file for each test and a test-only secret.
They do not alter `instance/securerole.db` or store demonstration passwords in
files. Coverage includes initialization, seed counts and repeatability, seed
rollback, password verification, relationships, invalid assignments and ownership,
role changes, foreign keys on multiple connections, unique/required constraints,
marks bounds, log decisions and UTC timestamp round trips. Raw SQL tests verify
SQLite constraints independently of Python validation.

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
