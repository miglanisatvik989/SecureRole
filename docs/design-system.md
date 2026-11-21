# SecureRole design system

Phase 4.1 uses light surfaces, clear typography and a restrained blue accent.
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
shows the signed-in profile and one active navigation link for its implemented
page. The preview explains when dashboard tools are planned.

## Responsive layout

Center the login card with a maximum width of 480 px and allow it to shrink
within the viewport. The desktop dashboard has a 240 px sidebar and a fluid
content column. At 768 px and below, the sidebar becomes a stacked navigation
and profile bar above the page content. Let names and labels wrap, and keep
controls large enough for touch. Templates preserve the same navigation and
forms at every viewport size.
