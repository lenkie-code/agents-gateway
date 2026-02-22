---
title: "feat: Redesign dashboard for modern SaaS UX"
type: feat
status: completed
date: 2026-02-22
---

# Redesign Dashboard for Modern SaaS UX

## Overview

Full redesign of the Agent Gateway dashboard to achieve a sleek, professional look inspired by Linear/Vercel. The dashboard currently has functional UX issues (charts expanding/contracting on period toggle) and an overall design that lacks the polish of modern SaaS products. This redesign touches all pages — agents, executions, analytics, chat, schedules — plus the layout shell (sidebar, topbar).

The redesign stays within the current tech stack: Jinja2 + HTMX + Chart.js + vanilla CSS with design tokens. Users can still customize themes via `DashboardThemeConfig`.

## Problem Statement

1. **Charts resize erratically** when toggling 7d/30d/90d — the `#analytics-content` container is swapped via HTMX `outerHTML`, which destroys and recreates the chart containers with potentially different content heights, causing visible layout shifts
2. **Visual design feels dated** — lacks the crispness and restraint of Linear/Vercel-style dashboards
3. **No mobile responsiveness** — sidebar is fixed with no collapse mechanism
4. **Chart theme toggle is broken** — toggling dark/light mode calls `applyChartDefaults()` but doesn't destroy/recreate chart instances, so grids and tooltips don't update
5. **Inconsistent spacing and visual hierarchy** — stat cards, chart cards, and page headers could be more cohesive

## Proposed Solution

A phased redesign that preserves the existing architecture and theming system while modernizing every visual surface.

## Acceptance Criteria

- [x] Charts maintain stable height when toggling date periods (no expand/contract)
- [x] All pages (agents, executions, analytics, chat, schedules, login) look cohesive and polished
- [x] Dark mode works correctly including chart color updates on theme toggle
- [x] Sidebar collapses on mobile (<768px) with hamburger toggle
- [x] User-configured theme colors (`DashboardThemeConfig`) still work correctly
- [x] No new JS/CSS dependencies added (stay with Chart.js, HTMX, vanilla CSS)
- [x] Reduced motion respected for all animations (`prefers-reduced-motion`)
- [x] Both full-page loads and HTMX partial swaps render correctly on every page
- [x] Example project (`examples/test-project/`) updated to demonstrate the redesign

---

## Key Decisions (resolved from SpecFlow analysis)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| HTMX swap strategy for analytics | **`innerHTML`** on a stable `#analytics-content` wrapper | Keeps the container in the DOM during swap, preventing height collapse. HTMX 2.x processes inline `<script>` tags in `innerHTML` swaps correctly. |
| Chart theme toggle approach | **`chart.update()`** — iterate existing instances, update colors/options, call `.update()` | Avoids needing to re-supply chart data (which is baked into the Jinja2 closure). Simpler than storing data globally or re-fetching. |
| Theme toggle button location | **Keep in topbar** | Moving to sidebar footer makes it inaccessible on mobile when sidebar is collapsed. Topbar keeps it always visible. |
| Mobile sidebar overlay click | **Closes sidebar** | Standard UX pattern. Click overlay or press Escape to close. |
| Loading skeleton states | **Out of scope** | Tracked as follow-up. Adds significant template complexity for marginal gain. |
| Copy-on-click for execution IDs | **`navigator.clipboard.writeText()`** with brief "Copied!" tooltip | Modern browser support is universal. No fallback needed. |

---

## Implementation Plan

### Phase 1: Fix Chart Layout Stability + Theme Toggle (core bugs)

**Problem**: HTMX `outerHTML` swap destroys the `#analytics-content` container, causing layout shift. Theme toggle doesn't update chart colors.

#### `analytics.html`
- Change the period toggle buttons from `hx-swap="outerHTML"` to `hx-swap="innerHTML"` and keep `hx-target="#analytics-content"`
- The `#analytics-content` div stays in the DOM; only its children are replaced

#### `_analytics_charts.html`
- Remove the outer `<div id="analytics-content">` wrapper (since the target div now persists in `analytics.html`)
- The inline `<script>` IIFE continues to work — HTMX 2.x executes scripts in `innerHTML` swaps

#### `app.css`
```css
.chart-container {
  position: relative;
  height: 18rem;      /* bump from 16rem for better readability */
  min-height: 18rem;  /* prevent collapse during transitions */
}

#analytics-content {
  min-height: 24rem;  /* prevent total collapse during innerHTML swap */
}
```

#### `charts.js`
- Add `updateChartTheme()` function that iterates all chart instances via `Chart.getChart(id)`, updates their grid colors, tooltip styles, and dataset colors from current CSS variables, then calls `.update()`
- Replace the theme toggle listener (currently `setTimeout(applyChartDefaults, 50)`) with `updateChartTheme()`

**Files**: `_analytics_charts.html`, `analytics.html`, `charts.js`, `app.css`

**Verification**: Toggle 7d/30d/90d rapidly — no height jump. Toggle dark/light mode — chart colors update smoothly.

---

### Phase 2: Design Token Refresh + Layout Shell (Sidebar + Topbar)

Combine token changes and layout shell redesign to avoid double-editing `tokens.css`.

#### `tokens.css` changes:

| Token | Current | New | Rationale |
|-------|---------|-----|-----------|
| `--sidebar-width` | 14.5rem | 13.5rem | Slightly narrower, more Linear-like |
| `--radius-sm` | 4px | 6px | Slightly softer, more modern |
| `--radius-md` | 6px | 8px | Consistent step-up |
| `--radius-lg` | 6px | 10px | Was same as md (bug) |
| `--radius-xl` | 8px | 12px | Cards feel more refined |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` | `0 1px 2px rgba(0,0,0,0.03)` | Subtler |
| `--shadow-md` | `0 1px 3px rgba(0,0,0,0.08)` | `0 2px 4px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)` | Layered, more depth |
| `--shadow-lg` | `0 2px 6px rgba(0,0,0,0.06)` | `0 4px 12px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.03)` | Vercel-style layered |
| `--transition-slow` | 150ms | 200ms | Was same as base (fix) |
| `--color-border` (light) | `rgba(0,0,0,0.06)` | `rgba(0,0,0,0.08)` | Slightly more defined |
| `--space-5` | 1.125rem | 1.25rem | More regular spacing scale |

- Add `--color-surface-hover` token: `color-mix(in srgb, var(--color-accent) 4%, var(--color-surface))` (derives from user's accent color)
- Dark mode surfaces: slightly less blue-tinted — change `#141b2d` to `#151921`, `#1a2236` to `#1c2029`
- **Apply dark mode token changes in BOTH** `@media (prefers-color-scheme: dark)` block AND `html.dark` block to prevent divergence

#### Sidebar (`base.html`, `app.css`)

Linear-style sidebar:
- Remove `border-left` active indicator, use subtle background tint + left accent bar (3px, rounded)
- Nav items: `border-radius: var(--radius-md)`, remove `border-left: 2px solid transparent`
- Section labels: lighter weight, `margin-top: var(--space-6)` for more breathing room
- Logo area: cleaner spacing

#### Topbar (`base.html`, `app.css`)

- Thinner: `3.5rem` -> `3rem`
- Keep minimal: app title on left, theme toggle on right
- Add hamburger button (hidden on desktop, visible on mobile)

#### Mobile Sidebar (`base.html`, `app.css`, `app.js`)

```html
<!-- In topbar, before the title -->
<button class="sidebar-toggle" id="sidebar-toggle" aria-label="Toggle navigation" aria-expanded="false">
  <svg><!-- hamburger icon --></svg>
</button>

<!-- After sidebar, before main -->
<div class="sidebar-overlay" id="sidebar-overlay"></div>
```

CSS:
```css
.sidebar-toggle { display: none; }
.sidebar-overlay { display: none; }

@media (max-width: 768px) {
  .sidebar {
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }
  .sidebar.open { transform: translateX(0); }
  .main { margin-left: 0; }
  .sidebar-toggle { display: flex; }
  .sidebar-overlay {
    display: none;
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.4);
    -webkit-backdrop-filter: blur(2px);
    backdrop-filter: blur(2px);
    z-index: calc(var(--z-sidebar) - 1);
  }
  .sidebar.open ~ .sidebar-overlay { display: block; }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar { transition: none; }
}
```

JS (`app.js`):
```javascript
// Mobile sidebar toggle
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.querySelector('.sidebar');
const overlay = document.getElementById('sidebar-overlay');

if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    sidebarToggle.setAttribute('aria-expanded', sidebar.classList.contains('open'));
  });
  overlay?.addEventListener('click', () => {
    sidebar.classList.remove('open');
    sidebarToggle.setAttribute('aria-expanded', 'false');
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sidebar.classList.contains('open')) {
      sidebar.classList.remove('open');
      sidebarToggle.setAttribute('aria-expanded', 'false');
    }
  });
}
```

**Files**: `tokens.css`, `base.html`, `app.css`, `app.js`

**Verification**: Full page loads + HTMX partial swaps still render correctly. Mobile sidebar opens/closes. Theme toggle still works. Custom `DashboardThemeConfig` colors still apply.

---

### Phase 3: Analytics Page Redesign

#### Stat Cards (`_analytics_charts.html`, `app.css`)

- Remove the gradient `::before` top-bar hover effect (too flashy for Linear/Vercel style)
- Replace with subtle border-left accent on hover (or no decoration at all)
- Tighter padding, more contrast between label and value
- Slightly smaller `stat-value` font size for restraint

#### Charts (`charts.js`, `app.css`, `_analytics_charts.html`)

- **Cleaner chart styling**: thinner lines (`borderWidth: 2` -> `1.5`), less gradient opacity (0.18 -> 0.10), more whitespace
- **Chart card redesign**: remove the colored dot `::before` on chart titles, use text-only titles with `font-weight: 500` instead of `600`
- **Tooltip redesign**: smaller padding, more compact
- **Legend**: move to top-right of chart card as inline pills, not below the chart

#### Date Range Selector

- Restyle tab group: tighter padding, `font-size: var(--text-xs)`, pill-shaped active state with smooth transition

**Files**: `_analytics_charts.html`, `analytics.html`, `charts.js`, `app.css`

---

### Phase 4: Agents Page Redesign

#### Agent Cards (`_agent_cards.html`, `app.css`)

- Remove header/body/footer border separators — single continuous padding zone
- Agent avatar: subtle gradient background derived from accent color
- Model badge: top-right as a small muted pill
- Description: single line with ellipsis (change from 2-line clamp)
- Tags: smaller, more muted styling
- Footer actions: ghost-style icon buttons
- Hover: subtle `box-shadow` lift (no `transform: scale` — too flashy)

**Files**: `_agent_cards.html`, `agents.html`, `app.css`

---

### Phase 5: Executions Page Redesign

#### Table (`_exec_rows.html`, `executions.html`, `app.css`)

- Cleaner table: remove `tbody tr:hover` background, use only bottom borders
- Status badges: pill-shaped with muted colors
- Execution ID: monospace, truncated, copy-on-click via `navigator.clipboard.writeText()` with brief "Copied!" tooltip
- Duration/cost columns: right-aligned
- Pagination: simpler, smaller controls
- Filter bar: tighter spacing, inline with page header

**Files**: `_exec_rows.html`, `executions.html`, `app.css`, `app.js` (for copy-on-click)

---

### Phase 6: Chat Page Polish

#### Chat UI (`chat.html`, `app.css`)

- Message bubbles: `border-radius: 12px`, more padding
- Assistant messages: remove border, use subtle background only
- User messages: keep accent color, `border-radius: 12px` with bottom-right `4px`
- Input area: larger, subtle shadow, rounded corners
- Agent selector: cleaner dropdown
- Typing indicator: smoother animation

**Files**: `chat.html`, `app.css`

---

### Phase 7: Remaining Pages + Cross-Cutting Polish

#### Schedules (`schedules.html`)
- Apply same table styling as executions redesign

#### Login (`login.html`, `app.css`)
- Cleaner form inputs with modern border radius
- Subtle background gradient
- No theme toggle on login page (acceptable — follows system preference)

#### Execution Detail (`execution_detail.html`, `app.css`)
- Cleaner trace timeline nodes
- Better contrast between step types (LLM/tool_call/tool_result)
- Smoother collapsible section animations

#### Cross-cutting polish
- Consistent focus rings: `outline: 2px solid var(--color-accent); outline-offset: 2px`
- Smooth HTMX swap animations via `htmx-added` class
- Add `@media (prefers-reduced-motion: reduce)` block to disable all transitions and animations globally
- Ensure `-webkit-backdrop-filter` prefix for Safari on mobile overlay

#### HTMX partial swap regression check
- Verify both full-page load and HTMX partial swap for: analytics (period toggle), executions (status filter, agent dropdown, pagination, auto-refresh), agent cards

**Files**: `schedules.html`, `login.html`, `execution_detail.html`, `app.css`

---

### Phase 8: Example Project Update

Update `examples/test-project/` to exercise the redesigned dashboard:
- Ensure dashboard is enabled in the example config
- Verify existing sample agents/data populate all dashboard pages
- Test theme customization with custom accent/sidebar colors
- Test mobile responsive behavior at 768px breakpoint
- Verify dark mode toggle works end-to-end including charts
- Cross-browser spot check: Chrome, Firefox, Safari

**Files**: `examples/test-project/`

---

## Technical Considerations

### Chart.js Layout Stability
Switch from `outerHTML` to `innerHTML` HTMX swap. The `#analytics-content` wrapper persists in the DOM, its children are replaced. Combined with `min-height` on the wrapper, this eliminates the height collapse during swap. HTMX 2.x correctly executes inline `<script>` tags in `innerHTML` swaps.

### Chart Theme Toggle
Use `chart.update()` on existing instances rather than destroy/recreate. Iterate `Chart.getChart(canvasId)` for each chart, update dataset colors, scale grid colors, and tooltip styles from current CSS variables, then call `.update()`. This avoids needing to re-supply the Jinja2-rendered data.

### Theme Customization Compatibility
All design changes must work with user-configured `DashboardThemeConfig.colors`:
- Keep using `var(--color-cfg-*)` pattern for config-injected colors
- New `--color-surface-hover` derives from user's accent via `color-mix()`, so it adapts automatically
- Test with non-default accent colors to ensure contrast
- Dark mode overrides applied in BOTH `@media (prefers-color-scheme: dark)` and `html.dark` blocks

### Accessibility
- Focus rings on all interactive elements
- `aria-label` and `aria-expanded` on mobile hamburger button
- Escape key closes mobile sidebar
- `@media (prefers-reduced-motion: reduce)` disables all transitions/animations
- Chart.js canvases remain inaccessible to screen readers (pre-existing limitation, out of scope for this redesign)

### No New Dependencies
- No Tailwind, no icon libraries, no new chart libraries
- Continue with inline SVGs (Heroicons style)
- Continue with Google Fonts for Inter
- Continue with Chart.js 4.4.4 and HTMX 2.0.4

### Browser Support
- `color-mix()` is well-supported in modern browsers
- `backdrop-filter` needs `-webkit-` prefix for Safari
- All other CSS used is broadly supported

## References

### Internal
- Config system: `src/agent_gateway/config.py:216-259`
- Color injection: `src/agent_gateway/dashboard/router.py:44-64`
- Dashboard templates: `src/agent_gateway/dashboard/templates/dashboard/`
- Chart helpers: `src/agent_gateway/dashboard/static/dashboard/charts.js`
- Design tokens: `src/agent_gateway/dashboard/static/dashboard/tokens.css`
- Component styles: `src/agent_gateway/dashboard/static/dashboard/app.css`
- Client JS: `src/agent_gateway/dashboard/static/dashboard/app.js`

### External Inspiration
- [Linear App](https://linear.app) — sidebar, typography, card design
- [Vercel Dashboard](https://vercel.com/dashboard) — charts, stat cards, overall layout
