# Phase 7.3 accessibility review

The review used Chromium and axe-core 4.14.1 against isolated demonstration
data. It sampled the login page, all three dashboards at 1440, 768 and 320 CSS
pixels, the filtered Student records, Users and Access logs pages, the
delete dialog, record form errors, Access restricted, the rate-limit page
and the Student empty state. The checks used relevant
[WCAG 2.2](https://www.w3.org/TR/WCAG22/) A and AA criteria.

| Check | Observed result |
| --- | --- |
| Text and focus contrast | The secondary text color measured 5.07:1 against white and 4.66:1 against the page background. White text on the primary button measured 4.70:1. Dark blue text on the blue tint measured 5.83:1. The blue focus outline measured 4.31:1 against the page background. |
| Keyboard navigation and visible focus | Tab reached the visible skip link, and Enter moved focus to the main content. The password toggle worked by keyboard under its Show password and Hide password names. At 320 px, the focusable records table scrolled horizontally with an arrow key while the page stayed within the viewport. |
| Labels, errors and messages | Search and select controls had visible labels. An invalid marks submission exposed its error alert and `aria-invalid`. The browser check intercepted one valid submit to inspect its polite pending message, then submitted normally and checked the success notice. |
| Table semantics and touch targets | Lists expose column headers and row headers for student or account identity. The checked mobile row action measured at least 24 by 24 CSS pixels. Table and section actions now have a minimum height of 32 px and width of 24 px. |
| Dialog focus | Keyboard activation opened the dialog on Cancel, Tab moved within it, and Escape closed it and returned focus to the triggering link. |
| Reflow, motion and color | All nine role and viewport combinations had no page-level horizontal overflow. The reduced-motion check returned zero transition duration. Permission scopes, record availability and decision badges expose text, and the marks meter has an accessible name plus the visible score. |

Axe reported **zero violations in 18 scans**. It marked three mobile table
headers as needing manual color-contrast review because they were outside
the scroll viewport. The tables use the shared header text and white card
surface. The mobile records check confirmed those computed colors at
5.07:1, and the other flagged headers use the same table rule.

Phase 7.3 added labeled filters, row headers, larger list action targets,
named table scroll regions, textual permission and waiting states, and a
labeled native marks meter. The changes retain the locked palette and the
existing keyboard patterns for sign-in and destructive actions.

This is a targeted review of the sampled screens. It does not establish
full WCAG conformance. Screen reader announcements were checked through
markup and browser accessibility roles. A live screen reader session,
physical touch devices, other browsers, and forced-colors testing were
outside this run.

## Phase 7.4 visual baseline

Chromium and axe-core 4.14.1 checked all three role dashboards at 1920,
1440, 1024, 768, 390 and 320 CSS pixels. The sample also covered narrow
sign-in, the expanded mobile menu, the record editor and its error state,
the deletion dialog, password reset, desktop audit activity, Access
restricted, and the Student waiting state.

The first run found metric-card icons inside the definition list structure.
The icons now sit outside each label/value list. The final run reported
**zero violations in 27 scans**. Axe requested contrast review for elements
outside four scroll viewports. Calculated contrast using the computed
foreground and background colors checked all 81 flagged observations.
The lowest ratio was **5.07:1**.

Manual browser interaction checked the mobile menu's collapsed state, Enter
and Tab navigation, Escape and focus return, and access to the sign-out
control. The menu and password control measured at least 24 by 24 CSS
pixels. The password toggle remained within the input area and kept its
accessible name. Native dialog focus entered on Cancel, remained inside
the dialog during Tab navigation, and returned to the trigger on Escape.
The browser also checked field errors, submission and success feedback,
horizontal scrolling of a focused mobile table, sticky desktop headers and
sidebar, zero page-level horizontal overflow, and reduced motion.

This remains a sampled review. Live screen readers, physical touch devices,
browser engines other than Chromium, and forced-colors mode were outside
the verification run.
