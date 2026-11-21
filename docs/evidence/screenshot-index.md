# SecureRole screenshot index

Figures 1–30 come from the finalized application running against an isolated SQLite backup with the five fictional team accounts. Desktop captures used a 1440 × 1000 CSS-pixel viewport and mobile captures used 390 × 844, both at 2× pixel density. Full-page captures include content below the fold. Figure 13 is a browser crop of the actual audit status card.

Figures 31–33 show verbatim excerpts from the current command output rendered in a browser for legibility. See the [verification summary](verification-summary.md) for methodology and results.

| Figure | Filename and relative path | Account role | Feature | Suggested caption | Report section |
| ---: | --- | --- | --- | --- | --- |
| 1 | [`01-login.png`](../screenshots/authentication/01-login.png) | Anonymous | Sign-in | SecureRole sign-in form with the password visibility control. | Authentication |
| 2 | [`02-invalid-credentials.png`](../screenshots/authentication/02-invalid-credentials.png) | Anonymous | Generic error | The sign-in page returns the same credentials error for an unknown account or a wrong password. | Authentication |
| 3 | [`03-admin-overview.png`](../screenshots/admin/03-admin-overview.png) | Admin · Satvik | Overview | The Admin overview summarizes student records, access decisions and the Admin's permissions. | Admin dashboard |
| 4 | [`04-student-records.png`](../screenshots/admin/04-student-records.png) | Admin · Satvik | Record list | The Admin record list shows course, marks and teacher assignment with access to view and edit records. | Record management |
| 5 | [`05-record-filters.png`](../screenshots/admin/05-record-filters.png) | Admin · Satvik | Search and filters | Searching for Raj and filtering by course narrows the result to his academic record. | Record management |
| 6 | [`06-create-record.png`](../screenshots/admin/06-create-record.png) | Admin · Satvik | Create form | The creation form identifies Kunal as the record owner before any data is saved. | Record management |
| 7 | [`07-edit-record.png`](../screenshots/admin/07-edit-record.png) | Admin · Satvik | Edit form | The edit form shows Raj's original course and mark of 88 on the copied dataset. | Record management |
| 8 | [`08-delete-confirmation.png`](../screenshots/admin/08-delete-confirmation.png) | Admin · Satvik | Delete confirmation | The destructive-action dialog asks for confirmation before deleting Raj's record. The demo dismissed it. | Record management |
| 9 | [`09-user-management.png`](../screenshots/admin/09-user-management.png) | Admin · Satvik | Account listing | The account list, filtered to Teachers, shows role badges and available administration actions. | User administration |
| 10 | [`10-user-role-assignment.png`](../screenshots/admin/10-user-role-assignment.png) | Admin · Satvik | Role and teacher fields | Kunal's account form shows the Student role and Maulik as the assigned Teacher. | User administration |
| 11 | [`11-access-activity.png`](../screenshots/admin/11-access-activity.png) | Admin · Satvik | Audit journal | The audit view shows stored actor roles, decisions, resources and UTC timestamps. | Audit logging |
| 12 | [`12-audit-filters.png`](../screenshots/admin/12-audit-filters.png) | Admin · Satvik | Audit filters and CSV | Filters restrict the view to Allowed dashboard decisions. The CSV download uses those filters. | Audit logging |
| 13 | [`13-audit-integrity.png`](../screenshots/admin/13-audit-integrity.png) | Admin · Satvik | Verification status | A browser crop shows the successful local audit verification status and the number of entries verified at capture. | Audit integrity |
| 14 | [`14-shubham-dashboard.png`](../screenshots/teacher/14-shubham-dashboard.png) | Teacher · Shubham | Assigned students and scope | Raj appears in Shubham's assigned-student list, and the permission panel explains Teacher scope. | Teacher dashboard |
| 15 | [`15-teacher-edit-record.png`](../screenshots/teacher/15-teacher-edit-record.png) | Teacher · Shubham | Authorized edit | Shubham opens the authorized edit form for Raj's record before updating the mark to 90. | Record authorization |
| 16 | [`16-maulik-dashboard.png`](../screenshots/teacher/16-maulik-dashboard.png) | Teacher · Maulik | Awaiting record | Kunal appears in Maulik's assigned-student list as awaiting a record. | Teacher dashboard |
| 17 | [`17-teacher-create-record.png`](../screenshots/teacher/17-teacher-create-record.png) | Teacher · Maulik | Authorized create | Maulik can open the creation form for Kunal because Kunal is assigned to him. | Record authorization |
| 18 | [`18-raj-dashboard.png`](../screenshots/student/18-raj-dashboard.png) | Student · Raj | Personal profile | Raj sees his own course, updated mark of 90, assigned teacher Shubham and Student permissions. | Student dashboard |
| 19 | [`19-kunal-empty-state.png`](../screenshots/student/19-kunal-empty-state.png) | Student · Kunal | Empty record state | The personal dashboard explains that there is no record yet and identifies Maulik as the assigned teacher. | Student dashboard |
| 20 | [`20-kunal-academic-record.png`](../screenshots/student/20-kunal-academic-record.png) | Student · Kunal | Created record | After Maulik's authorized creation, Kunal sees his course and mark of 79. | Student dashboard |
| 21 | [`21-operation-success.png`](../screenshots/security/21-operation-success.png) | Teacher · Maulik | Success feedback | The Teacher workspace confirms that the academic record was created. | Record authorization |
| 22 | [`22-access-restricted.png`](../screenshots/security/22-access-restricted.png) | Teacher · Shubham | Access Restricted | The application returns HTTP 403 when a Teacher requests the Admin Users page. | Authorization |
| 23 | [`23-denied-audit-entry.png`](../screenshots/security/23-denied-audit-entry.png) | Admin · Satvik | Denied event | The activity filter surfaces Shubham's Denied Users decision with the historical Teacher role. | Audit logging |
| 24 | [`24-active-sessions.png`](../screenshots/security/24-active-sessions.png) | Admin · Satvik | Session list | Two browser contexts appear as current and other sessions in the account's active-session list. | Session management |
| 25 | [`25-session-revocation.png`](../screenshots/security/25-session-revocation.png) | Admin · Satvik | Session revocation | The remaining session receives confirmation after revoking the other session. | Session management |
| 26 | [`26-rate-limit-feedback.png`](../screenshots/security/26-rate-limit-feedback.png) | Anonymous | HTTP 429 | The live rate limiter returns HTTP 429 with a retry interval after ordinary failed sign-in attempts. | Login throttling |
| 27 | [`27-mobile-login.png`](../screenshots/authentication/27-mobile-login.png) | Anonymous | Mobile sign-in | The sign-in form fits a 390 CSS-pixel viewport. | Responsive design |
| 28 | [`28-mobile-admin.png`](../screenshots/admin/28-mobile-admin.png) | Admin · Satvik | Mobile Admin | The Admin overview stacks metrics and content at mobile width. | Responsive design |
| 29 | [`29-mobile-teacher.png`](../screenshots/teacher/29-mobile-teacher.png) | Teacher · Shubham | Mobile Teacher | The Teacher workspace stacks metrics and filters in a single mobile content column. | Responsive design |
| 30 | [`30-mobile-student.png`](../screenshots/student/30-mobile-student.png) | Student · Raj | Mobile Student | The Student profile and permissions stack without page-level horizontal overflow. | Responsive design |
| 31 | [`31-pytest-results.png`](../screenshots/testing/31-pytest-results.png) | Test runner | Complete suite | Browser-rendered excerpt of the complete pytest run and its final measured result. | Test execution |
| 32 | [`32-acceptance-results.png`](../screenshots/testing/32-acceptance-results.png) | Test runner | T1–T11 | Browser-rendered pytest output confirms T1 through T11 individually. | Acceptance verification |
| 33 | [`33-audit-verification.png`](../screenshots/testing/33-audit-verification.png) | Read-only CLI | Audit CLI | Browser-rendered CLI output shows the canonical and isolated journal checks. | Audit integrity |

All 33 requested figures are available.
