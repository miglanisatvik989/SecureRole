# Unified demonstration dataset

The canonical SQLite database is `instance/securerole.db`. [Setup instructions](../README.md#installation-and-setup)
initialize or migrate it, expand the fictional college roster, and create the
five team accounts. The six original fictional accounts are included once.

| Dataset | Admins | Teachers | Students | Academic records | Awaiting records |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fictional starting roster | 2 | 12 | 120 | 110 | 10 |
| Team additions | 1 | 2 | 2 | 1 | 1 |
| Unified fresh setup | **3** | **14** | **122** | **111** | **11** |

The fictional roster has two Teachers and 20 Students per subject. Each of
the 12 original Teachers keeps 10 assigned Students. Academic records use
fictional marks and reserved institutional email addresses.

| Subject | Fictional Teachers | Fictional Students | Fictional records |
| --- | ---: | ---: | ---: |
| Cryptography and Network Security | 2 | 20 | 18 |
| Data Structures and Algorithms | 2 | 20 | 18 |
| Database Management Systems | 2 | 20 | 18 |
| Operating Systems | 2 | 20 | 18 |
| Computer Networks | 2 | 20 | 18 |
| Artificial Intelligence | 2 | 20 | 20 |

Raj is assigned to Shubham and starts with 88 marks in Cryptography and
Network Security. Kunal is assigned to Maulik and initially awaits a record.
The team additions do not shift the fictional cohorts. Compatible records
and additional accounts already in a database remain, so live totals can
differ from a fresh installation.

## Setup and demonstration

Run `python -m flask --app run setup-demo` from the project root. Find
new credentials in `instance/securerole.demo-credentials.csv`. The file is
Git-ignored and created with owner-only permissions where supported. If the
file already exists, setup retains its contents and appends rows for new
accounts. An older account may use credentials saved separately. Setup does
not recover or reset that password.

Use your team's private credential rows for the guided demonstration. An
Admin can show the account and record lists, and the two Teachers can show
the recorded and waiting profiles. Normal authorized operations produce
genuine audit activity. Setup itself does not synthesize access decisions.
To validate continuity run `python -m flask --app run verify-audit`.

If an account was reset in the app, its older CSV entry may be stale. Store
the new value privately and use the Admin reset workflow when needed. If
setup finds a credential row for a missing account or a roster identity
with an incompatible role, assignment or course, it stops before changing
data. If setup is interrupted during credential publication, reconcile the
private file with the database before retrying. An SQLite commit and a CSV
file replacement cannot share one transaction.
