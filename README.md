# SecureRole — Role-Based Access Control (RBAC) Simulator

SecureRole is a Cryptography and Network Security PBL project. It demonstrates
how authentication, least privilege, record ownership and audit logging work
together in a college records application. Admins manage accounts and records,
Teachers work with their assigned Students, and Students view their own
academic profile. The app also demonstrates login throttling, session
revocation and audit integrity verification.

SecureRole uses Python, Flask, Flask-Login, Flask-WTF, SQLAlchemy, SQLite,
Werkzeug, Jinja, HTML/CSS/JavaScript and pytest.

## Team members

| Team member | Role |
|-------------|---------|
| Satvik      | Admin   |
| Shubham     | Teacher |
| Maulik      | Teacher |
| Raj         | Student |
| Kunal       | Student |

All other seeded accounts are fictional demonstration data.

## Prerequisites

- Python 3.14 with SQLite 3.38 or later and the `venv` module.
- Git and a modern browser.
- Linux, macOS or Windows PowerShell.

## Installation and setup

These commands are for a new clone. For an existing working copy, keep its
`.env` so its signing keys still match the database.

### Linux and macOS

```bash
git clone https://github.com/miglanisatvik989/SecureRole.git
cd SecureRole
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "from pathlib import Path; from secrets import token_hex; p=Path('.env'); s=p.read_text(); p.write_text(s.replace('replace-with-a-random-secret', token_hex(32)).replace('replace-with-an-independent-audit-secret', token_hex(32)), encoding='utf-8')"
chmod 600 .env
python -m flask --app run setup-demo
python run.py
```

### Windows PowerShell

```powershell
git clone https://github.com/miglanisatvik989/SecureRole.git
Set-Location SecureRole
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from pathlib import Path; from secrets import token_hex; p=Path('.env'); s=p.read_text(); p.write_text(s.replace('replace-with-a-random-secret', token_hex(32)).replace('replace-with-an-independent-audit-secret', token_hex(32)), encoding='utf-8')"
python -m flask --app run setup-demo
python run.py
```

After setup, find newly generated sign-in details in the private
`instance/securerole.demo-credentials.csv` file. Keep it out of shared folders,
reports and version control. Open [http://127.0.0.1:5000](http://127.0.0.1:5000)
and sign in with an account from that file. An account created before unified
setup still uses its existing password, even if it was saved separately.

The generator fills `SECRET_KEY` for Flask sessions and the independent
`AUDIT_INTEGRITY_KEY` for audit HMACs. Keep both values private. For first-time
team account creation, operators can optionally set
`DEMO_<UPPERCASE_USERNAME>_PASSWORD` in the private `.env`. These inputs must
meet the same 12–128 character policy as the account forms. An unset value
generates a random password. Setup ignores overrides for existing accounts.

Local HTTP uses HTTP-only, SameSite=Lax cookies. A hosted HTTPS instance should
set `SESSION_COOKIE_SECURE=1` and a comma-separated `TRUSTED_HOSTS` list in
`.env`, and use a production WSGI server. Setting Secure cookies on a local HTTP
instance prevents normal sign-in.

## Database

SecureRole uses one SQLite database at `instance/securerole.db`. A fresh
`setup-demo` creates **139 accounts** with 3 Admins, 14 Teachers and 122 Students.
It creates **111 academic records**, leaving **11 Students awaiting records**.
It preserves compatible existing data and reports actual totals when there are
additional accounts or records. See the [demo guide](docs/demo-dataset.md) and
[database schema](docs/diagrams/database-schema.md).

| Table | Purpose |
| --- | --- |
| `roles` | Supported account roles and their IDs |
| `users` | Profiles, salted password hashes, roles and Student-to-Teacher assignments |
| `student_records` | Course and marks, with at most one record per Student |
| `access_logs` | UTC decisions, historical roles and linked audit MACs |
| `auth_sessions` | Session token digests, expiry and revocation status |
| `login_windows` | Persistent, expiring login throttle counters |
| `audit_chain_state` | Current audit head and key binding |

`python -m flask --app run setup-demo` is the primary initializer. It applies
versioned migrations, seeds the roster, and checks SQLite, foreign-key and audit
integrity. Repeat runs do not reset passwords, overwrite records or duplicate
accounts. The older `init-db`, `migrate-db`, `seed-db` and `seed-demo` commands
remain available for their narrower workflows against the same database.

For an upgrade, stop the server first, retain the existing signing keys, and
use `python -m flask --app run backup-db <new-private-path>` to take a verified
temporary backup outside the checkout. Run `setup-demo` against the original
canonical path and verify the result before removing the temporary backup.
If setup reports a conflict, resolve it before restarting the app. Setup does
not merge independent audit chains.

## Application usage

- **Admin.** Overview shows counts and activity. Open **Student records** to
  add, view, edit or delete records. Open **Users** to manage accounts, roles,
  Teacher assignments and password resets. The last Admin cannot be demoted.
- **Teacher.** In **My students**, add records for assigned Students awaiting
  a record, or view and edit existing ones. Deletion and account administration
  are restricted to Admins. Search, filter by record availability and sort the
  assigned roster within your assignment scope.
- **Student.** **My academic record** shows the Student's own course, marks
  and assigned Teacher, with a marks meter on a scale of 100. An empty state
  appears before a record is added. All three dashboards include **My permissions**,
  a summary drawn from the role policy.
- **Search and filters.** Admins can look up records by student name, username
  or course, and filter by Teacher, course or availability. The **Users**
  list supports name, username or email search and role and Teacher filters.
  Sort and filter choices carry across pages. **Clear filters** restores the
  default list. Record and account forms retain the listing context in their
  breadcrumbs and return links. On mobile, open **Menu** to reach navigation,
  profile and sign-out controls.
- **Access activity.** Admins can search, filter and page through **Access logs**.
  **Download CSV report** exports all matching recorded events from the
  current snapshot. The export excludes authentication material.
  Run `python -m flask --app run verify-audit` for a read-only chain check.
  Use `--checkpoint ID:MAC` with a trusted, separately stored checkpoint to
  detect rollback past that entry.
- **Sessions.** Use **Sign out** for the current session. Use **Active sessions**
  to revoke another session or sign out everywhere.

## Security architecture

Werkzeug uses salted password hashes. Server-side RBAC checks the stored role,
Student ownership, and Teacher assignment before granting access. Forms use
CSRF protection. Server-side sessions store token digests and expire eight
hours after sign-in. Sign-out and password changes revoke associated sessions.

Login throttling uses persistent SQLite windows. Defaults are 10 attempts per
source and 5 per source and account in 60 seconds. The settings are
`LOGIN_SOURCE_LIMIT`, `LOGIN_ACCOUNT_LIMIT` and `LOGIN_WINDOW_SECONDS`.
SQLite foreign keys, constraints and triggers protect data relationships.
Audit entries are linked with HMAC-SHA256 using a separate key. Verification
depends on protecting that key and maintaining trusted integrity state.
See [authorization](docs/authorization.md) and [security analysis](docs/security-analysis.md).

## Testing

```bash
python -m pytest -q
```

The latest run passed **187 tests in 78.78 seconds**, including all
**T1–T11** authorization acceptance cases. Tests use isolated temporary
databases. See [test results](docs/test-results.md) for the measured
environment, fresh-install checks and individual acceptance outcomes.

## Project structure

| Path | Purpose |
| --- | --- |
| `app/` | Application factory, routes, models, migrations and security controls |
| `app/templates/` | Shared layouts, dashboards and forms |
| `app/static/` | Existing design system styles, scripts and local fonts |
| `tests/` | Unit, acceptance and functional regression tests |
| `docs/` | Design, security, schema and verification documentation |
| `instance/` | Ignored local database and private credentials |

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Flask or another dependency is missing | Activate the virtual environment and run `python -m pip install -r requirements.txt`. |
| PowerShell blocks activation | For that terminal only, run `Set-ExecutionPolicy -Scope Process RemoteSigned`, then activate again. |
| A key is missing or still a placeholder | Configure both independent keys in `.env`. Keep the original audit key when reusing an existing database. |
| Database initialization or migration fails | Stop the server, confirm the canonical path and write permissions, and follow the upgrade instructions. Investigate conflicts before retrying. |
| A demo password is forgotten | Check your private saved credentials. If another Admin can sign in, ask them to use **Users → Reset password** and save the new value privately. If all Admin credentials are lost, preserve the canonical database and arrange local recovery. Repeating setup does not reset an account. |
| Port 5000 is already in use | Stop the other process or run `python -m flask --app run run --port 5001` and open `http://127.0.0.1:5001`. |
