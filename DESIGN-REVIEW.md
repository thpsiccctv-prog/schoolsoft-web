# SchoolSoft — Design Review & UX Roadmap
Reviewer role: senior product designer / UX architect / Django frontend reviewer
Date: July 2, 2026 · Screens reviewed: Dashboard (EXE screenshot), Students list, Receipt list, Fee Collection desk
Targets: 1280×720 and 1366×768, mouse-first clerks, zero horizontal scroll.

---

## 1. Overall Design Direction

**What is working**
- The app-shell is right: dark sidebar + light workspace is the correct ERP pattern and instantly reads as "software", not a website.
- Real school logo in the brand block earns trust with school staff and parents standing at the counter.
- One accent family (teal) used consistently; tiles, active pill, and buttons all agree.
- Information scent is good — a clerk can find every module from anywhere in one click.

**What still looks average or weak**
- **The same numbers appear three times on the dashboard** (hero KPI cards, tile corner counts, stat pills). Repetition reads as decoration, not information. Premium ERPs never repeat a number on one screen.
- "THPS COMMAND CENTER" kicker + "Welcome back" + "operational desk" is *marketing voice*. Operators see this 40× a day; it should greet them with **today's work**, not a slogan.
- The topbar repeats "Dudahi, Kushinagar" which is already in the sidebar — chips without a job.
- Sidebar bullet dots are decorative noise. Either real 18px icons or nothing.
- The Admin tile has a one-off gradient bottom border. One-off styles erode the feeling of a *system*. Every exception must be earned (e.g., a red border only for "Dues overdue").
- Counts use proportional digits. Money software must use **tabular figures** (`font-variant-numeric: tabular-nums`) so columns of numbers align — this one CSS line is half of "premium".

**How to make it feel premium**
Premium in an ERP = *density + rhythm + restraint*: an 8px spacing grid everywhere, one accent, semantic colors only where they mean something (green = money in, red = due, amber = warning), aligned numerals, instant hover feedback (<150ms transitions only), and every screen opening with the **primary action already visible**. Delete anything that has no job.

---

## 2. Dashboard Improvements

**Hierarchy (top → bottom):** what needs action today → shortcuts to modules → everything else folded.

1. **Replace the hero with an "ops header" (72–88px tall):**
   - Left: `Wednesday, 2 July 2026 · Session 2026-27` (small, muted) + page title `Dashboard`.
   - Right: one **primary green button: `+ New Fee Receipt`** — the #1 daily task must be one click from launch. Secondary ghost button: `Due Report`.
   - Kill "THPS COMMAND CENTER" / "operational desk" copy.
2. **Make KPI cards mean *today*, not totals:** `Today's Collection ₹`, `Receipts Today`, `Total Dues ₹ (red)`, `Active Students`. Static totals (596/667) already live on the tiles — don't duplicate. (Needs 3 small queries in the dashboard view; worth it.)
3. **Tiles:** compact them to ~110–120px min-height so all 10 fit above the fold at 1366×768 (2 rows of 5 at ≥1280px: `repeat(auto-fill, minmax(196px, 1fr))`). Keep icon + count + label; drop the sub-line to a `title=` tooltip if space is tight.
4. **Remove the stat-pill strip entirely** (fully redundant now).
5. Keep the audit `<details>` fold exactly as is — good pattern for technical content.
6. "Wow" that stays useful: a thin **collection sparkline for the last 14 days** in the Today's Collection card (pure inline SVG polyline from a small list in context — no JS library).

---

## 3. Fee Collection Screen (daily-use critical)

Target: **student → months → save+print in under 20 seconds, mouse-only.**

**Three-zone layout (grid `1.1fr / 1.6fr / 0.9fr`):**

- **Zone A — Student (left):**
  - Search box auto-focused on page load; type-ahead after 2 chars (name/SID/mobile); results as rows with class + a red `₹ due` badge; click or Enter selects.
  - After selection: compact student card (name, class-section, father, mobile, photo placeholder) with a `Change` link — collapse the search away, don't leave it fighting for attention.
  - **Month chips** below: 12 clickable chips (Apr–Mar). States: `paid` (green tick, disabled), `due` (white), `selected` (teal fill). Clicking a chip = clicking a checkbox — no dropdowns.
- **Zone B — Fee heads (center):** grid of head rows: name, default amount (from FeeStructure), editable amount input (right-aligned, tabular-nums), per-row checkbox. Selecting months auto-ticks the matching heads. A muted `+ Add other head` link for exceptions.
- **Zone C — Payable (right, sticky):** running summary — Fee total, Concession (editable), Late fee, **NET PAYABLE in 28px bold**, payment mode (Cash default, radio chips not dropdown), then **one primary button: `Save & Print (F9)`** full-width 52px, with a small ghost `Save only` beneath. Never two equally-weighted buttons.

**Guard rails & flow:**
- If a selected month already has a receipt → amber inline warning with a link to that receipt ("SF-670 exists for JULY — open?"). Prevents the most common clerk error.
- After save: success panel with three big buttons — `Print receipt`, `New receipt (same class)`, `Next student` (refocuses search). The clerk's hands never leave the mouse.
- **Recent receipts** (last 5, self-made) belong *under Zone A*, not across the bottom — glanceable while working.

---

## 4. Students Page / Admission Workflow

**List: modern split-panel, not old-VB dense and not airy-modern.**
- ≥1280px: **master-detail** — table left (~62%), preview panel right (~38%). Single click on a row loads a read-only preview (photo, guardian, dues badge, document buttons) via plain link + query param (`?preview=<id>`) rendering the panel server-side — no JS framework needed. Double-click / "Open" goes to the full detail page.
- Row height 40px, no zebra stripes (hover highlight only), SID + Class + Roll columns narrow and right-aligned, name column bold — everything else muted.
- Filters stay as the current single filter bar; add class **tabs/chips above the table** (Nursery … VIII) for one-click filtering — clerks think in classes.
- Below 1280px the preview panel collapses and row-click opens the detail page (current behavior).

**Admission / detail:**
- Keep the current grouped panels (Student / Parents & Contact / Address / Documents) — the grouping is right.
- Make it a **two-column form with a sticky footer bar**: `Save` (primary) + `Save & New Admission` (for admission season bulk entry) + `Cancel` (ghost). Sticky footer = no scrolling back up to save.
- Document buttons (Admission Form / Character Cert / TC / Marksheet) as a compact button row with a printer glyph each — they already work; just standardize sizes.

---

## 5. Visual System

- **Palette (final, stop iterating):** keep current tokens; add semantic money colors: `--success: #067647` + `--success-soft: #e6f4ea` (collections/paid), keep `--danger` for dues, `--amber` for warnings, `--blue` only for informational chips. Rule: **teal = interactive, green = money in, red = money owed.** Nothing else colored.
- **Typography:** Segoe UI stack is correct (offline EXE — never add webfonts). Lock a scale: 12 (labels) / 13.5 (secondary) / 15 (body) / 17 (card titles) / 22 (page titles) / 28 (net payable, KPI). Add globally: `font-variant-numeric: tabular-nums` on `td, .t-count, .stat, .kpi`.
- **Sidebar:** replace bullet dots with the existing 24px tile SVGs at 18px, `opacity:.85`. Active = white pill (keep). Collapse group order to workflow order: Dashboard, **Fee Collection**, Receipts, Dues, Students, Marks, Collection, Fee Setup, Staff, Transport, School Profile.
- **Cards:** one radius (12px) and one shadow token everywhere; borders `--line`, hover border `--accent`. Remove the Admin tile gradient.
- **Tables:** sticky header (done), right-align all numeric columns, `white-space: nowrap` only on numeric/SID columns and let names wrap — this is what actually kills horizontal scroll on 1280px.
- **Buttons:** four variants only — primary (teal), success (green, Save & Print), secondary (white/border), danger (red, delete/TC). 44px height, 8px radius, visible `:focus-visible` ring.
- **Form fields:** 44px, 12px uppercase labels (current), red border + 12px message on error, `:focus` teal ring (done). Date inputs always `type=date`.
- **Empty states:** icon (reuse tile SVG, 40px, muted) + one line + one primary action, e.g. "No receipts match these filters — `Reset filters`". Never a bare empty table.
- **Hover/active:** rows tint `#f6fbfa` (done); tiles lift 2px (done); buttons darken one step; disabled = 45% opacity, no cursor change games.

---

## 6. Desktop App (pywebview) Specific UX

- **Keyboard for the mouse-first clerk (cheap, huge):** global keydown handler in `base.html`: `Esc` → `history.back()` (mirrors the Back button), `F9` → submit fee form when present, `/` → focus first search input. Show the hint inside the buttons: `← Back (Esc)`, `Save & Print (F9)`.
- **Back button:** keep top-left (muscle memory now), add the Esc hint. Disable it on Dashboard (`if path == '/' hide`) so it never dead-ends.
- **Status bar:** a 28px muted footer strip on desktop only: `SchoolSoft v1.x · Data: LOCALAPPDATA\SchoolSoft · Backup: 02-Jul-2026`. Trust feature for the operator — they can see their data is backed up. (Values can be injected later; start static with version.)
- **Print/PDF:** current Save-As download works; next step is `window.print()` buttons on receipt/report pages (pywebview supports the print dialog) so the counter printer is two clicks: `Print → Enter`.
- **Window title:** set per page via the existing `{% block title %}` — already correct; keep titles short (`Receipt SF-670 — SchoolSoft`) since it shows in the Windows taskbar.
- **Zoom:** `zoomable=True` is enabled; put "Ctrl + scroll = zoom" in the status bar once, not as a popup.

---

## 7. Implementation Priority (2 weeks)

**Week 1 — Quick wins (CSS/template only, hours each)**
1. Delete stat-pill strip + topbar location chips; single source per number.
2. Compact ops header with date/session + **`+ New Fee Receipt` primary button**; remove Command Center copy.
3. `tabular-nums` global; right-align numeric columns; name columns allowed to wrap.
4. Sidebar icons (reuse tile SVGs), remove dots; reorder nav to workflow order.
5. Compact tiles → all modules above the fold at 1366×768; remove Admin gradient.
6. `Esc` back + `/` search-focus + button hints.
7. Indian number formatting for ₹ everywhere (`humanize` + custom Indian-grouping filter).

**Week 2 — Medium effort (template + small view changes)**
8. Dashboard KPIs become *today's* numbers (3 queries) + 14-day sparkline.
9. Fee Collection three-zone refactor: month chips, sticky payable, single primary Save & Print, duplicate-month guard, post-save success panel with `Next student`.
10. Students master-detail preview panel (`?preview=` server-rendered) + class chips above the table.
11. Empty states + error states pass across all list pages.

**Later — high-impact redesigns (plan, don't rush)**
12. Receipt print preview modal with thermal/A5 layout choice.
13. Dues drill-down: class tabs → student rows → one-click "collect now" jump into Fee Collection pre-filled.
14. Session switcher (2026-27 ▾) in the topbar once multi-session workflows begin.
15. Status bar with live backup timestamp from desktop.py.

**Definition of done for every item:** zero horizontal scroll at 1280×720 · all 21 tests green · print/PDF untouched · works identically in EXE and on Render.
