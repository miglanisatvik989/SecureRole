# SecureRole verification summary

Phase 8 evidence was collected on **2026-11-21 UTC** from
commit `848de27`, the final application baseline. The evidence
collection used isolated SQLite databases for tests and browser writes.

## Final permission matrix

| Operation | Admin | Teacher | Student |
| --- | --- | --- | --- |
| View academic records | All | Assigned Students only | Own record only |
| Create academic records | All eligible Students | Assigned Students only | Denied |
| Edit academic records | All | Assigned Students only | Denied |
| Delete academic records | All | Denied | Denied |
| Manage users | Allowed | Denied | Denied |
| Assign roles | Allowed | Denied | Denied |
| Assign teachers | Allowed | Denied | Denied |
| View and export access logs | Allowed | Denied | Denied |

Every account has one stored role. Creation checks the intended Student
account, which may have no record. SQLite enforces at most one record per
Student. Dashboard guards use the signed-in account's stored role. Unrecognized
actions deny by default. See the [central policy](../../app/rbac.py) and
[authorization documentation](../authorization.md).

## Test execution

Command from the project directory: `.venv/bin/python -m pytest -v --basetemp <temporary-directory>`.

| Executed | Passed | Failed | Skipped | Pass rate | Duration |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 187 | 187 | 0 | 0 | 100% (187 ÷ 187) | 77.96 s |

Linux x86_64 with CPython 3.14.4, SQLite 3.46.1 and pytest 9.2.0.

| Dependency | Version | Dependency | Version |
| --- | --- | --- | --- |
| Flask | 3.1.3 | Flask-Login | 0.6.3 |
| Flask-SQLAlchemy | 3.1.1 | Flask-WTF | 1.3.0 |
| SQLAlchemy | 2.1.9 | Werkzeug | 3.1.9 |
| WTForms | 3.3.2 | Jinja2 | 3.1.6 |
| itsdangerous | 2.2.0 | python-dotenv | 1.2.4 |

[Test output screenshot](../screenshots/testing/31-pytest-results.png) ·
[Earlier phase results](../test-results.md).

## T1–T11 acceptance outcomes

All 11 acceptance cases passed in the complete pytest run. Each checks the HTTP
response and its corresponding audit event. Write cases check the resulting
stored state where applicable.

| ID | Acceptance criterion | Expected | Observed |
| --- | --- | --- | --- |
| T1 | Admin lists Student records | Allow | HTTP 200, both fixture records visible, Allowed logged |
| T2 | Admin deletes a record | Allow | HTTP 303, record removed, Allowed logged |
| T3 | Teacher creates an assigned Student record | Allow | HTTP 303, submitted record stored, Allowed logged |
| T4 | Teacher deletes a record | Deny | HTTP 403, record retained, Denied logged |
| T5 | Student reads their own record | Allow | HTTP 200, own record visible, Allowed logged |
| T6 | Student reads another Student's record | Deny | HTTP 403, Denied logged |
| T7 | Student edits a record | Deny | HTTP 403, values unchanged, Denied logged |
| T8 | Anonymous visitor opens dashboard | Deny and redirect | HTTP 302 to sign-in, Denied logged with no actor ID |
| T9 | Student opens administrative functionality | Deny | HTTP 403 on Users, Denied logged |
| T10 | Teacher assigns a role | Deny | HTTP 403, role unchanged, Denied logged, direct policy denies |
| T11 | Teacher reads an unassigned Student's record | Deny | HTTP 403 for Student without an assigned teacher, Denied logged |

[Acceptance test source](../../tests/test_acceptance.py) ·
[Acceptance output screenshot](../screenshots/testing/32-acceptance-results.png).

## Dataset and database integrity

| Measurement | Canonical | Browser copy after walkthrough |
| --- | ---: | ---: |
| Accounts | 139 | 139 |
| Admins | 3 | 3 |
| Teachers | 14 | 14 |
| Students | 122 | 122 |
| Academic records | 111 | 112 |
| Students awaiting a record | 11 | 10 |
| Audit entries verified | 79 | 119 |
| SQLite integrity check | `ok` | `ok` |
| Foreign-key violations | 0 | 0 |

The canonical database has all seven schema version 1 tables. The app was
launched on a SQLite backup made from a read-only connection. Shubham updated
Raj's mark from 88 to 90 and Maulik created Kunal's record with 79 in the copy.
The canonical file kept the same SHA-256 digest before and after evidence
collection.

```text
e97ea9bf6a4a0ffd2944f6ec9606ce6d4ca9c40c20e135737849150e3d4cd377
```

The application's read-only `verify-audit` command exited successfully against
each database. Verification of the copy also passed against the canonical
entry-79 checkpoint. The UI verifies the journal at page load, so its earlier count
can differ from the end-of-run CLI count. See the [ERD](../diagrams/database-erd.svg),
[UI status](../screenshots/admin/13-audit-integrity.png) and
[CLI evidence](../screenshots/testing/33-audit-verification.png).

## Browser and accessibility verification

Playwright drove Chrome for Testing 150.0.7871.24 at desktop 1440 × 1000 and
mobile 390 × 844 CSS pixels. The walkthrough used all five team accounts,
checked local font loading and horizontal overflow, and verified keyboard
activation of the password toggle, Escape dismissal of the delete dialog,
the audit filter and CSV download, the 403 and 429 responses, cross-browser
session revocation and sign-out. The 429 response included `Retry-After`.

Eight fresh axe-core 4.14.1 scans covered sign-in and each role dashboard at
both widths. The selected WCAG 2.0, 2.1 and 2.2 A/AA rules returned **0
violations and 0 incomplete findings** across those scans. The earlier
[Phase 7.4 review](../accessibility-review.md#phase-74-visual-baseline) covered
27 scans. Phase 8 uses automated browser and accessibility checks with a visual
review of the screenshots. Independent manual verification by Satvik,
Shubham, Raj, Maulik or Kunal was not supplied.

## Controls and documented limits

- Werkzeug salted hashes, generic authentication errors and persistent
  login quotas protect sign-in. The limiter uses the connection source
  and source-account pairs. Users on a shared source share quota.
- Flask-WTF validates CSRF tokens. Server-side session rows store a token
  digest, expire after eight hours, and support individual revocation.
  Reads already authorized before revocation can finish.
- RBAC applies role, ownership and assignment checks before accessing
  protected resources. Successful writes commit with their Allowed event,
  and SQLite enforces record and assignment invariants.
- The append-only audit journal retains event-time role snapshots. Imported
  entries from before that capture began may have an unknown role.
  HMAC verification depends on custody of the independent key. Detecting
  rollback to an authentic database snapshot requires an external trusted
  checkpoint. The Phase 8 comparison used the canonical checkpoint to
  verify the copy's continuity through entry 79.
- The application remains a local simulator. Hosting, MFA, retention policy
  and key rotation remain outside the documented implementation. Automated
  accessibility results cover the pages and rules exercised. At 390 px,
  long course strings can wrap across many lines in the Admin and Teacher
  tables even though the page itself fits the viewport.

[Final security analysis](../security-analysis.md#phase-71-advanced-hardening) ·
[Implementation excerpts](implementation.md) · [Screenshot index](screenshot-index.md) ·
[Team demonstration](demo-walkthrough.md).
