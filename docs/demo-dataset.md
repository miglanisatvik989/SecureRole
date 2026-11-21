# Phase 7.2 demonstration dataset

The expanded roster represents a fictional Indian college. Names are generated
from a fixed seed and may coincidentally match real names. All contact addresses
use the reserved `securerole.example` domain. Passwords are generated separately
with a cryptographically secure random source.

## Dataset composition

The roster has **134 accounts**. There are 2 Admins, 12 Teachers and 120 Students.
Every Student has a teacher, and every Teacher has exactly 10 assigned Students.
The default distribution leaves 10 Students awaiting records and includes 110
academic records.

| Subject | Teacher accounts | Students | Records | Awaiting |
| --- | --- | ---: | ---: | ---: |
| Cryptography and Network Security | `teacher1`, `teacher2` | 20 | 18 | 2 |
| Data Structures and Algorithms | `devika.nair`, `rohan.sen` | 20 | 18 | 2 |
| Database Management Systems | `rudra.chandra`, `aniket.saha` | 20 | 18 | 2 |
| Operating Systems | `manav.kulkarni`, `jaya.agarwal` | 20 | 18 | 2 |
| Computer Networks | `riya.bhat`, `naina.shah` | 20 | 18 | 2 |
| Artificial Intelligence | `gaurav.patil`, `radhika.kapoor` | 20 | 20 | 0 |
| **Total** | **12** | **120** | **110** | **10** |

The subject grouping comes from the seed plan and teacher assignment. Students
awaiting a record have no stored course yet. Most generated marks fall in the
middle and upper bands, with some lower and high marks and half-point values.
Existing marks are preserved, so an already populated compatible database can
have a different per-subject record split.

The six starter accounts remain. `student1` and `student2` are assigned to
`teacher1`. `student3` is assigned to `teacher2`. The starter Cryptography
records and marks, 85 and 78, remain. The seed keeps `student2` awaiting a
record when no record exists, and preserves one if an authorized user has
already added it. Existing passwords, roster-compatible assignments, records,
and nonblank institutional emails are preserved. Blank email fields are filled.

## Setup and credentials

For an existing database, stop the application and follow
[the backup and migration instructions](../README.md#upgrading-an-existing-database).
For a fresh database, run `flask --app run init-db`. Then run these commands.

```bash
flask --app run seed-demo
flask --app run verify-audit
python run.py
```

Use the project virtual environment. The seed runs inside one SQLite write
transaction. It verifies the existing audit chain, reports conflicts before
replacing any data, and rolls back on a write failure. Repeating the command
preserves rows and credentials when the target roster and record count are
already present. An interrupted process can leave a credentials file ahead of
the database commit. If that happens, verify the roster and retain the file
privately before moving it aside and retrying.

New credentials are written only to the database's matching
`*.demo-credentials.csv` file. The default is
`instance/securerole.demo-credentials.csv`. The file is Git-ignored, created
with mode `0600`, and never overwritten. It contains plaintext so sign-in is
possible during the demonstration. Restrict access and keep it out of captures,
reports and shared folders. Existing-account passwords come from their original
`seed-db` output or the operator who set them.

| Username | Role | Suggested use |
| --- | --- | --- |
| `admin` | Admin | Original Admin, using the previously saved password |
| `ananya.rao` | Admin | Overview, accounts, records and access logs |
| `devika.nair` | Teacher | 10 assigned Students, including an account awaiting marks |
| `rohan.sen` | Teacher | A second cohort in the same subject |
| `varun.kulkarni` | Student | Data Structures and Algorithms, 71/100 |
| `aditya.bhat` | Student | Data Structures and Algorithms, 82/100 |
| `diksha.kapoor` | Student | Data Structures and Algorithms, 89/100 |
| `lakshmi.gowda` | Student | Assigned to Devika Nair, awaiting a record |

## Generate genuine activity

`seed-demo` does not create audit events. The application records them when
the selected fictional users perform ordinary operations.

1. Sign in as `devika.nair`. Visit **My students** and view existing records.
2. Add a temporary **Data Structures and Algorithms** record for
   `lakshmi.gowda`, then edit its marks through the record form.
3. Sign in as `ananya.rao`, open the temporary record and confirm its deletion.
   This returns the roster to 110 records and 10 students awaiting records.
   The authorization decisions remain in the audit trail.
4. Visit the three recorded-student dashboards and the waiting-student
   dashboard. Open **Access logs** as the Admin. Search by actor
   or action and use **Next** when there is more than one page.
5. Run `flask --app run verify-audit`. Keep a trusted checkpoint outside the
   database if later rollback detection is needed.

Avoid rapidly cycling through many logins on one address. The normal sign-in
throttling rules still apply to the demo.

## Measured verification

On 2026-11-21 UTC, the live demo database was backed up and migrated from
schema 0 to 1 with the server stopped. The expansion added 128 accounts and
108 records. A second run added nothing. The six original account IDs,
password hashes, teacher assignments, and academic records matched the
verified backup. The 110 final marks ranged from 37 to 97.5, with 65 distinct
values and a mean of 76.3.

Chromium verified the Admin dashboard and user listing, both selected Teacher
cohorts, three recorded Student profiles and one waiting Student. The walkthrough
used the normal authenticated record forms, searched and paged through the
journal, and generated 43 audit entries. After removal of the temporary record,
the final counts remained 110 records and 10 students awaiting records. The
read-only audit verification, SQLite integrity check, and foreign-key check
all passed.

The complete pytest suite passed **170 tests in 62.25 seconds**, including
all 163 prior tests and T1–T11.
