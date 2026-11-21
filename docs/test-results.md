# Phase 7 test results

**Execution date:** 2026-11-21 UTC

**Command:** `.venv/bin/python -m pytest -v`

**Environment:** Linux x86_64, CPython 3.14.4, SQLite 3.46.1, pytest 9.2.0.

| Dependency | Version | Dependency | Version |
| --- | --- | --- | --- |
| Flask | 3.1.3 | Flask-Login | 0.6.3 |
| Flask-SQLAlchemy | 3.1.1 | Flask-WTF | 1.3.0 |
| SQLAlchemy | 2.1.9 | Werkzeug | 3.1.9 |
| WTForms | 3.3.2 | Jinja2 | 3.1.6 |
| itsdangerous | 2.2.0 | python-dotenv | 1.2.4 |

| Executed | Passed | Failed | Skipped | Pass rate | Duration |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 142 | 142 | 0 | 0 | 100% (142 ÷ 142) | 41.95 s |

The run included all 119 existing tests, 11 independent acceptance cases,
and 12 new security regression cases. Tests and browser verification used
isolated SQLite databases populated with fictional accounts.

## T1–T11 acceptance results

Each row has an independently executed case in
[`tests/test_acceptance.py`](../tests/test_acceptance.py), named
`test_acceptance[Tn]`. Each case checks the HTTP outcome and corresponding
audit entry, including actor, action, resource, decision and UTC timestamp.
Write cases additionally check the stored result or that the denied change
did not take effect. The regression column identifies existing supporting
tests and the centralized policy action.

| ID | Acceptance criterion | Expected | Observed | Result | Existing regression and policy |
| --- | --- | --- | --- | --- | --- |
| T1 | Admin views student records | Allowed | HTTP 200, both records shown, Allowed audit | Pass | `test_dashboard_metrics_and_record_privacy` and `test_query_scopes`. `LIST_RECORDS` with `VIEW_RECORD` scope. |
| T2 | Admin deletes an academic record | Allowed | HTTP 303, record removed, Allowed audit | Pass | `test_admin_record_lifecycle`. `DELETE_RECORD`. |
| T3 | Teacher creates an assigned student's record | Allowed | HTTP 303, record and submitted marks stored, Allowed audit | Pass | `test_teacher_scope_and_student_write_denials` and `test_record_scope_and_creation_target`. `CREATE_RECORD`. |
| T4 | Teacher deletes an academic record | Denied | HTTP 403, record retained, Denied audit | Pass | `test_teacher_scope_and_student_write_denials` and `test_permission_matrix`. `DELETE_RECORD`. |
| T5 | Student views their own record | Allowed | HTTP 200, own record shown, Allowed audit | Pass | `test_dashboard_metrics_and_record_privacy` and `test_query_scopes`. `VIEW_RECORD`. |
| T6 | Student views another student's record | Denied | HTTP 403, Denied audit | Pass | `test_dashboard_metrics_and_record_privacy` and `test_record_scope_and_creation_target`. `VIEW_RECORD`. |
| T7 | Student edits an academic record | Denied | HTTP 403, course and marks unchanged, Denied audit | Pass | `test_teacher_scope_and_student_write_denials` and `test_permission_matrix`. `EDIT_RECORD`. |
| T8 | Anonymous dashboard access | Denied | HTTP 302 to sign-in, Denied audit with NULL actor | Pass | `test_anonymous_access_is_protected` and `test_dashboard_guard_403_and_audit`. `VIEW_DASHBOARD`. |
| T9 | Student accesses administrative functionality | Denied | HTTP 403 on Users, Denied audit | Pass | `test_permission_matrix` and `test_admin_pages_deny_non_admin` (Teacher route coverage). `MANAGE_USERS`. |
| T10 | Teacher assigns a role | Denied | HTTP 403 on account update, role unchanged, Denied audit. Direct role-assignment policy also denied. | Pass | `test_permission_matrix` and `test_admin_pages_deny_non_admin`. Route `MANAGE_USERS`, direct policy `ASSIGN_ROLES`. |
| T11 | Teacher views an unassigned student's record | Denied | HTTP 403 for a student with no assigned teacher, Denied audit | Pass | `test_dashboard_metrics_and_record_privacy` and `test_record_scope_and_creation_target`. `VIEW_RECORD`. |

No criterion remained without an independent check. The supporting regressions
are in [test_auth.py](../tests/test_auth.py), [test_features.py](../tests/test_features.py)
and [test_rbac.py](../tests/test_rbac.py). See also
[the authorization policy](../app/rbac.py).

## Browser and data checks

Chromium exercised Admin record navigation, the delete confirmation and its
Escape behavior, the activity filter, a Student denial and credential
revocation after a reset in another browser context, and a Teacher record
edit. Sign-in, sign-out, the password visibility control, local Inter
loading, and the locked light palette worked. The tested desktop, tablet and
mobile views (1440, 768 and 320 px) had no horizontal overflow. No screenshots
were collected in this phase.

The existing demonstration database had an identical SHA-256 digest before
and after verification. Read-only inspection showed 3 roles, 6 users, 2
academic records, 0 access logs and no foreign-key violations. Installed
dependencies passed `pip check`, which checks installation consistency.
