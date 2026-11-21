# SecureRole design system

SecureRole uses light surfaces, clear typography and a restrained blue accent.
The application stylesheet defines the shared tokens and components in
[`style.css`](../app/static/css/style.css).

## Locked palette

| Token | Value | Use |
| --- | --- | --- |
| `--background` | `#F5F5F7` | Page backdrop and quiet hover surfaces |
| `--surface` | `#FFFFFF` | Cards, sidebar, controls and primary button text |
| `--text-primary` | `#1D1D1F` | Main copy and labels |
| `--text-secondary` | `#6E6E73` | Supporting copy and secondary labels |
| `--border` | `#D2D2D7` | Separators and card boundaries |
| `--accent` | `#0071E3` | Primary action and keyboard focus |
| `--accent-hover` | `#005BB5` | Primary hover and blue text on tinted surfaces |
| `--accent-background` | `#E8F1FD` | Active navigation, role badges and notices |
| `--success` | `#248A3D` | Success indicator |
| `--error` | `#D70015` | Errors and invalid fields |
| `--warning` | `#A15C00` | Warning indicator |

Use a text label with each status indicator. Use stronger input borders than
card borders so users can locate fields on white surfaces.

## Typography

Inter is the primary font, with `-apple-system`, `BlinkMacSystemFont`,
`"Segoe UI"` and `sans-serif` as fallbacks. Use IBM Plex Mono for technical
values, identifiers and code, with a monospace fallback. Latin WOFF2 assets
and their SIL Open Font Licenses are in [`app/static/fonts`](../app/static/fonts).
System fonts provide fallback glyphs.

| Element | Size | Weight |
| --- | --- | --- |
| Brand | 24 px | 700 |
| Page heading | 32 px | 600 |
| Section heading | 20 px | 600 |
| Metric value | 32 px | 600 |
| Body | 14 px | 400 |
| Navigation | 14 px | 500 |
| Table heading | 13 px | 500 |
| Secondary label | 12 px | 400 |

## Components and spacing

Use the 8 px spacing scale for gaps and padding, with larger multiples for
page gutters and groups. Cards use a 16 px radius with a light border and
shadow. Buttons and inputs use a 10 px radius. Primary buttons use blue,
secondary buttons use a bordered white surface, and the active navigation link
uses the blue tint with `aria-current="page"`. Transitions use 180 ms and are
disabled for reduced motion.

Keep a visible label on each form field and associate field errors using
`aria-describedby`. Use `role="alert"` for submitted form errors and
`role="status"` for informational notices. Keyboard focus uses a blue outline.
Use the shared card and empty state for unavailable content. Wrap wide data
tables in `.table-scroll` so they can scroll within their container.

Outline icons use a consistent 24 × 24 view box, rounded strokes and inherited
color. The shared Jinja icon macro hides decorative SVGs from assistive
technology. Icon-only buttons need their own accessible names. The password
toggle switches between “Show password” and “Hide password”.

## Interface copy

| Screen | Heading | Supporting text |
| --- | --- | --- |
| Login | Welcome to SecureRole | Sign in to your account to continue. |
| Admin | Overview | Manage users, student records and access activity. |
| Teacher | My students | View and manage your assigned students. |
| Student | My academic record | View your course details and academic performance. |

Use “Sign in” and “Sign out” for the authentication actions. Each dashboard
shows the signed-in profile and highlights the active section. The Admin
sidebar links to Overview, Student records, Users and Access logs. Teachers and
students have a single dashboard destination.

Use metric cards as description lists, a shared profile card for the academic
record, readable empty states and green status notices for successful saves.
Access decisions pair a green or red indicator with the text “Allowed” or
“Denied.” The record deletion dialog starts on **Cancel** and supports Escape.
The confirmation route provides the equivalent flow when dialogs are unavailable.

## Responsive layout

Center the login card with a maximum width of 480 px and allow it to shrink
within the viewport. The desktop dashboard has a sticky 240 px sidebar with a
bottom account area and a fluid content column. At 768 px and below, the
sidebar becomes a compact header with a disclosure button and current-page
text. The disclosure exposes the same navigation and profile controls. Let
names and labels wrap, and keep controls large enough for touch.

## Phase 7.3 components

Use labeled GET filter forms and a consistent **Apply filters** and
**Clear filters** toolbar. Display the result count above the table and keep
pagination inside the same card. Use row headers for account and student
identity. Wide tables stay in separately focusable scroll regions so the
page itself can reflow at narrow widths.

Permission cards pair the scope text with restrained status indicators.
The Student profile uses a native marks meter alongside the visible numeric
score. Keep the score and permission meaning readable without interpreting
color. For real form submissions, use a polite status message and suppress
duplicate submits while navigation is pending.

See the [accessibility review](accessibility-review.md) for the checks
performed and their limits.

## Final visual baseline

Page headers pair a title and short description with the primary action.
Nested record and account pages add breadcrumbs. Return links keep recognized
search, filter and page selections for the expected listing. The mobile menu
starts collapsed when scripting is available. Enter opens it, Tab continues
to the current navigation group, and Escape returns focus to the menu button.

Metric cards keep decorative outline icons outside the definition list for
their label and value. Numeric table cells align to the right and retain
tabular numerals. Taller desktop lists use focusable scroll regions with
sticky column headers. At 1440 px and wider, the Admin overview gives
recent records the wider column and puts the activity feed alongside.
Compact widths stack the sections, with table scrolling contained in each card.

Student and Teacher identities use decorative initials alongside visible names.
The score and native meter share the Student profile. The permission cards
summarize actual policy scopes with concise text. The sign-in password control
sits inside the input area and keeps its Show password and Hide password names.

Related form controls share fieldsets and legends. Password guidance stays
visible beside the field, and errors add a separate announcement and focusable
field association. The audit status card describes local verification of the
full journal. The visible Allowed and Denied totals describe the selected
filters, and the CSV continues to report those matching recorded events.
