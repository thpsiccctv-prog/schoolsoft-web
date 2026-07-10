# SchoolSoft Project — Status Handoff (July 2, 2026)

You are joining an in-progress project. Read this fully before changing anything.
Everything below was completed and verified today. Do not redo finished work.

## Project overview

Legacy "SchoolSoft" school management system (old Access/VB) modernized into a
Django 6 app at `D:\english medium\schoolsoft_web`. Two delivery targets:

1. **Windows desktop EXE** (primary, daily school use) — PyInstaller + pywebview + waitress + SQLite. DONE and verified.
2. **Online deployment** (secondary, view/reports) — Render.com + PostgreSQL. DEPLOYED and live today.

Modules (all working): Students (596), Fees/Receipts (667), Fee Structure,
Marks (10,036 rows), Staff (19), Transport, School Profile, PDF generation
(ReportLab: receipts, due reports, admission forms, TC, marksheets).
Tests: 21/21 pass (`manage.py test`).

## Desktop EXE — final architecture (do not regress these)

- `desktop.py` (launcher):
  - User data lives in `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` — NEVER beside the EXE. Rebuilds/updates can never touch user data.
  - On start: adopts legacy db beside EXE if found, else copies bundled `db.seed.sqlite3`; makes a dated backup (`db.backup-YYYYMMDD.sqlite3`, keeps 7); runs `migrate --noinput`; sets `PRAGMA journal_mode=WAL`.
  - Single-instance lock = bind on port 47391. If taken: **shows a MessageBox** ("already running") then `os._exit(0)` — never a silent exit.
  - `webview.settings["ALLOW_DOWNLOADS"] = True` — REQUIRED, otherwise all PDF downloads silently do nothing in pywebview.
  - `webview.create_window(..., zoomable=True, text_select=True)`.
  - `webview.start(_force_foreground)` — helper uses ctypes FindWindowW + SetForegroundWindow because the window otherwise opens BEHIND other windows without focus (observed on Win 11).
  - Do NOT pass `gui="edgechromium"` to `webview.start()` — it produced a live process with no visible window on this machine. Default auto-detect works.
  - `finally: logging.shutdown(); os._exit(0)` after webview.start returns — REQUIRED: without it a zombie SchoolSoft.exe survives window close, holds the lock, and every future launch dies silently. This exact bug cost hours today.
  - Errors + breadcrumbs log to `%LOCALAPPDATA%\SchoolSoft\SchoolSoft-error.log` (settings.py LOGGING routes django.request errors there too via SCHOOLSOFT_LOG_FILE env).

- `SchoolSoft.spec`:
  - datas: templates, static, `staticfiles` (collectstatic output — WhiteNoise serves it in the EXE), `db.seed.sqlite3`, `collect_data_files` for django (admin templates/static), tzdata (Asia/Kolkata zoneinfo), reportlab (fonts).
  - hiddenimports: whitenoise, waitress, dotenv, tzdata, static names `webview.platforms.winforms` + `webview.platforms.edgechromium`, `collect_submodules` for core/schoolsoft/django/reportlab.
  - WARNING: do NOT use `collect_submodules('webview')` — it imports pywebview (.NET) at build time and hangs/slows Analysis badly.
  - `upx=False` (antivirus false positives), `console=False`, excludes psycopg2/pyodbc/gunicorn.

- `build-desktop.bat`: uses project `.venv`, checks deps, collectstatic, creates fresh `db.seed.sqlite3` (migrate + superuser admin/admin12345), runs PyInstaller. Build takes ~12–15 min on this machine. Output: `dist\SchoolSoft\SchoolSoft.exe`.

- EXE was GUI-tested end to end today (dashboard, students, receipts, dues, marks, back button, PDF downloads all verified working).

- School logo/icon update:
  - Source logo came from `D:\2025-2026 board exam\SCHOOL PHOTO\logo.jpeg`.
  - App assets generated: `static/core/school_logo.png` and `static/core/schoolsoft.ico`.
  - Sidebar brand mark uses the real THPS logo image instead of the old text-only `TH` mark.
  - `SchoolSoft.spec` sets `icon='static/core/schoolsoft.ico'`, so rebuilt EXEs and shortcuts can show the school logo.

## settings.py key points

- SQLite path via `SCHOOLSOFT_SQLITE_PATH` env (desktop sets it); `OPTIONS: {timeout: 20}` (waitress is multithreaded; prevents "database is locked").
- `DATABASE_URL` env switches to Postgres (Render) via dj-database-url.
- DEBUG defaults True locally; Render sets `SCHOOLSOFT_DEBUG=False`.
- WhiteNoise middleware serves static in both desktop and Render; RENDER_EXTERNAL_HOSTNAME auto-added to ALLOWED_HOSTS.
- `pyodbc` was REMOVED from requirements.txt (unused, breaks Render Linux build).

## Git / GitHub (done today)

- Repo: `https://github.com/thpsicdudahi-jk1/schoolsoft-web` (PRIVATE). Branch `main`, initial commit `adc5b23` (65 files).
- `git config --global safe.directory` was added for this folder (folder owner is a different Windows user).
- `.gitignore` covers: `*.sqlite3`, `.env`, `*.log`, `staticfiles/`, `build/`, `dist/`, `.venv/`, `debug-scripts/`, `data.json`, `git-out.txt`. NEVER commit databases — they contain real student data.
- `debug-scripts/` folder = throwaway diagnostic bats from today's debugging; ignore it.

## Render deployment (done today, LIVE)

- Blueprint "schoolsoft" from `render.yaml` (repo root), branch main.
- Web service: **schoolsoft-english-medium** (free plan, Oregon), URL:
  `https://schoolsoft-english-medium.onrender.com` — LIVE, verified serving the app with styling. Free instance sleeps after 15 min idle (~50 s cold start).
- Postgres: **schoolsoft-db** (free plan) — ⚠️ **expires August 1, 2026** (Render deletes free DBs after ~30 days). Desktop SQLite remains the source of truth; online DB can be recreated + reloaded any time via `migrate-data.bat`.
- Env vars per render.yaml: SECRET_KEY generated, DEBUG=False, DATABASE_URL from schoolsoft-db, ALLOWED_HOSTS/CSRF for `english-medium.thpsic.com` (custom domain NOT yet configured — planned CNAME from Netlify DNS later).
- Build command: pip install + collectstatic + migrate. Auto-deploys on push to main.

## Data migration (COMPLETE)

- Initial `migrate-data.bat` / Django `loaddata` was too slow over the internet
  and was stopped before commit. The live site still showed zero records at that
  point.
- Added faster loader:
  - `fast_load_data.py`
  - `migrate-data-fast.bat`
- Fast loader exported local SQLite and bulk-loaded Render PostgreSQL in
  batches.
- Render PostgreSQL verification after load:
  - `core.AcademicSession`: 2
  - `core.SchoolClass`: 15
  - `core.Section`: 30
  - `core.SchoolProfile`: 1
  - `core.Student`: 596
  - `core.FeeHead`: 27
  - `core.FeeStructure`: 152
  - `core.FeeReceipt`: 667
  - `core.FeeReceiptLine`: 2,419
  - `core.Subject`: 16
  - `core.ExamTerm`: 2
  - `core.ExamTest`: 184
  - `core.ExamMark`: 10,036
  - `core.Staff`: 19
  - `core.TransportBus`: 1
  - `core.TransportRoute`: 28
  - `core.StudentTransport`: 2
  - `core.LegacyImportBatch`: 7
  - `auth.User`: 1
  - total loaded objects: 14,205
- Live dashboard verified at `https://schoolsoft-english-medium.onrender.com`:
  Students 596, Classes 15, Fee heads 27, Receipts 667, Sessions 2.
- `data.json` was deleted after successful load because it contained full
  student data.

## Pending / next steps

1. Change the admin password (default admin/admin12345 is in build scripts — must be changed on both desktop db and Render db via /admin/).
2. Rotate the Render DB credential (Database page → Credentials → New default credential) — the external URL with password was pasted in chat/screenshot.
3. Custom domain: CNAME `english-medium.thpsic.com` → Render service, then add as Custom Domain on the service.
4. Plan for DB expiry (Aug 1, 2026): either paid Postgres (~$7/mo) or recreate free DB monthly + rerun `migrate-data-fast.bat`.
5. Optional cleanup: remove `git-out.txt` and `setup-git.bat` from the repo (committed accidentally, harmless).

## 🚨 URGENT NEXT TASK — Student data is STALE, re-import from fresh SCHOOL7.mdb

**Discovered July 2 evening. This is the top-priority job. Read carefully.**

### The problem (verified with evidence)

The legacy SchoolSOFT app shows: **TOTAL 1213 / BLOCKED 849 / UNBLOCKED (active) 364**.
Our app shows 596 students, all active. Investigation proved BOTH numbers come from
the same table, but our import used a **stale CSV export**:

1. `migration_audit/exports/ADDMISSION.csv` (the file our importer used) has only
   **592 rows** and its `TC_ISSUE` column says NO for 587 rows — it is an OLD export.
2. The user opened the LIVE `SCHOOL7.mdb` in Access: `ADDMISSION` there has
   **1213 rows** (v_no 1..1213, sid up to 2613, includes 2026-27 admissions
   with `adm_year = 26`, e.g. SHIVAM KUMAR sid 2589 … ARABAJ sid 2613), and
   **TC_ISSUE = YES on a large share of rows** (with TC_NO / TC_DATE filled).
3. So: blocked = `TC_ISSUE = YES` (≈849), active = rest (≈364). Our DB is missing
   ~617 students INCLUDING all new 2026-27 admissions, and marks everyone active.
4. Other imported tables (StuFee = receipts 667, Marks, DUES, CLASS, FEE) came from
   the SAME stale export folder — they are probably missing recent rows too.

### Fresh data location (ready and waiting)

The user copied the LIVE database to: **`D:\english medium\9\SCHOOL7.mdb`**
(1.37 GB, copied 02/07/2026 20:07; ignore the .ldb lock file). Treat it as
read-only source. NEVER commit it or any export of it to git.

### Already done by Claude (do not redo)

- `core/management/commands/import_legacy_students.py` fixed:
  - `is_active` is now `NOT (tc == YES or TC_ISSUE == YES)` (was `tc` only).
  - `read_csv` now tries utf-8-sig then cp1252 (Access text exports are cp1252).
- `resync-students.bat` created: backs up the LIVE db
  (`%LOCALAPPDATA%\SchoolSoft\db.sqlite3`), re-runs `import_legacy_students`
  against `migration_audit/exports/`, then prints counts via `active_count.py`.
- `active_count.py` created: prints TOTAL / ACTIVE / INACTIVE students.

### What YOU must do (in order)

1. **Re-export fresh CSVs** from `D:\english medium\9\SCHOOL7.mdb` into
   `D:\english medium\migration_audit\exports\` (replace the stale files).
   Easiest: reuse `migration_audit/export_mdb_tables.ps1` pointed at the new mdb
   path (it exports via ADO/PowerShell; python has no pyodbc anymore).
   Minimum tables: ADDMISSION, CLASS, StuFee, FEE, DUES, Marks, TEST,
   Testmark1, Testmark2, Busmaster, RouteMaster, BUS_APPLICABLE, Emp_Mast.
   Verify: fresh ADDMISSION.csv must have **1213 rows**.
2. Run `resync-students.bat` → expect `TOTAL ≈ 1213, ACTIVE ≈ 364`.
   If ACTIVE ≈ 364 matches the legacy toolbar, the mapping is proven correct.
3. Re-run the other importers (import_legacy_fees, import_legacy_marks,
   import_legacy_transport, import_legacy_staff, import_legacy_fee_structure,
   import_legacy_school_profile) against the fresh exports — same
   `SCHOOLSOFT_SQLITE_PATH=%LOCALAPPDATA%\SchoolSoft\db.sqlite3` env so the
   EXE's live db gets the data. Check row deltas (receipts were 667 — live may
   have more).
4. **UI follow-ups:** student list should default to Active students with an
   All/Active/Inactive filter; dashboard Active Students already filters
   `is_active=True` so it will show ~364 automatically. Total-students tile
   should say "1213 (364 active)" or similar — avoid the old confusion.
5. `manage.py test` (21 tests) must stay green. Then push (push.bat) and
   rebuild EXE (build-desktop.bat).
6. **Render re-load:** Postgres still has the stale 596-student data. After
   local resync: empty the Render DB (e.g. `manage.py flush` with DATABASE_URL
   set to the External URL, or ask user to recreate the free db) and re-run
   `fast-load.bat` (it refuses to load into a non-empty DB by design).
7. Update this handoff file when done.

### Key numbers to verify success

| Metric | Legacy app | After resync |
| --- | --- | --- |
| Total students | 1213 | 1213 |
| Active (unblocked) | 364 | ~364 |
| Blocked/TC | 849 | ~849 |

## Rules for any future work

- Never bundle or commit real databases. Seed db only.
- User data dir `%LOCALAPPDATA%\SchoolSoft\` is sacred — nothing in the repo/build may overwrite it.
- Desktop EXE is the primary system; online is read/report convenience.
- `D:\english medium\9\SCHOOL7.mdb` (fresh legacy copy) is read-only source data — never commit it or its exports.
- Test with `manage.py test` (21 tests) before any EXE rebuild; rebuild via `build-desktop.bat` only.

## ✅ Fresh SCHOOL7 local resync completed (July 2, 2026 evening)

- Fresh CSV exports were generated from `D:\english medium\9\SCHOOL7.mdb`.
- `ADDMISSION.csv` now has 1213 rows:
  - `TC_ISSUE=NO`: 364
  - `TC_ISSUE=YES`: 849
- `import_legacy_students.py` was corrected so `TC_ISSUE` is authoritative;
  the older `tc` field is used only when `TC_ISSUE` is blank.
- Desktop live SQLite was backed up before resync:
  `C:\Users\Admin\AppData\Local\SchoolSoft\db.before-fresh-school7-20260702-202613.sqlite3`
- Four stale fee-only placeholder students from the old import were removed:
  `1913`, `1914`, `1915`, `1916`.
- Local desktop DB now matches the legacy toolbar:
  - Total students: 1213
  - Active/unblocked: 364
  - Inactive/TC: 849
- Re-ran fresh importers:
  - fee structure from `Cfee.csv`
  - fee receipts from `StuFee.csv`
  - staff from `Emp_Mast.csv`
  - transport from `Busmaster`, `RouteMaster`, `BUS_APPLICABLE`
- Marks were **not** re-imported because fresh `Testmark2.csv` exported 0 rows.
  Existing 10,036 marks remain until the correct current marks source/mapping is
  confirmed.
- UI follow-up done:
  - Students page defaults to Active
  - Active / Inactive / All filter added
  - dashboard student tile shows total and active count
- Verification:
  - `manage.py test`: 21/21 passed
  - `/students/` renders 364 active records
  - `/students/?status=all` renders 1213 records
  - dashboard renders 1213 total / 364 active

Still pending:
- Rebuild EXE after this section if not already done in the latest session.
- Push/deploy and reload Render PostgreSQL with the fresh data. Render reload
  requires the current External Database URL or a recreated empty database.

## Recent Updates
Fee Collection Workflow Improvements completed:
- Month chips
- Duplicate overlap warning
- Custom student dropdown
- Save & Print autoprint
- Tests 21/21 passed
- Desktop DB counts still 1213/364/849

## Goal 3: Mobile Phase 1 (PWA)
- Added manifest.webmanifest with theme color #004d40 and standalone display.
- Added service-worker.js with static-cache-first and network-first strategies.
- Updated core/urls.py and base.html to serve PWA components at root scope.
- Verified mobile responsiveness for main pages.

## Session — July 4, 2026 (Users & Permissions + auth roles + UI fixes)

**All committed and pushed to `origin/main`. EXE rebuilt (BUILD OK). Role testing PASSED.**
Commits this session (in order): `925200d` (styles.css clean baseline restore) -> `ac1f36b`
(users & permissions backend + read-only write-block) -> `eb93c7e` (sidebar menu links +
users-page styling + footer stack) -> `1d15f53` (sidebar nav scroll + service-worker
network-first) -> `cab40ad` (Users & Permissions table polish). Latest = **`cab40ad`**.

### What was built (role-based access control, all in-app, no new model)
- `core/access.py` — `module_required(module)` decorator, `write_required`/write guards,
  `access_context` context processor (injects `access.*` booleans + `can_manage_users`),
  `MODULE_PERMISSIONS` map, `READONLY_GROUP`, `manage_users_required`.
- Permissions live on a `managed=False` `ModuleAccess` model (migration
  `core/0008_module_access_permissions.py`) — codenames like `access_fee_collection`,
  `access_all_modules`, `access_dashboard`. "View/print only" = membership of the
  **Read Only** group (blocks all create/edit/delete via write guards).
- `core/user_admin.py` — in-app Users & Permissions screen (admin-only). Role presets:
  `admin` (all), `fee` (students, fee_collection, receipts, dues, collection, fee_setup,
  school_profile), `admission` (students, school_profile), `exam` (students, marks,
  school_profile), `staff` (staff, transport, school_profile), `viewer` (all modules +
  view-only), `custom`. Views: user_list/create/edit/reset_password/toggle_active.
- Templates: `core/users_list.html`, `user_form.html`, `password_change.html`,
  `password_change_done.html`, `permission_denied.html` (two states: "Permission Required"
  for missing module, "View / print only" for readonly write attempts).
- `core/urls.py` routes: `user_list`, `user_create`, `user_edit`, `user_reset_password`,
  `user_toggle_active`, `password_change`, `password_change_done`; `write=True` guards on
  create/edit/delete/receipt/salary/tc views.
- `base.html`: sidebar nav items wrapped in `{% if access.<module> %}`; Users & Permissions
  link under `{% if can_manage_users %}`; footer has Change password + Logout.

### UI fixes this session
- Sidebar footer (Logout) was clipping when nav got long. Fix in `static/core/styles.css`
  (end of file): `.side-foot{flex-direction:column; ...}` (stack buttons full-width) +
  `.sidebar{overflow:hidden}` + `.side-nav{overflow-y:auto; min-height:0}` +
  `.side-foot{flex-shrink:0}` (nav scrolls internally, footer pinned).
- **Service worker was cache-first for all `/static/`, so CSS edits never showed even after
  Ctrl+F5.** Fixed `templates/core/service-worker.js`: bumped `CACHE_NAME` v2→v3; `.css`/`.js`
  now **network-first** (cache = offline fallback only); images stay cache-first. `base.html`
  styles.css cache-buster is `?v=20260704-users-3`. If future CSS edits "don't show", it's the
  SW/cache — bump the `?v=` and/or CACHE_NAME, or DevTools → Application → unregister SW.
- CRITICAL LESSON (carried from prior session): never append to styles.css via bash `cat >>`
  — it truncated the file. Use the file editor only.

### Role testing — PASSED (dev server 127.0.0.1:8000, 5 test users)
Created feetest/admtest/examtest/stafftest/viewtest via the Users & Permissions page (they
live only in the local dev `db.sqlite3`, NOT the sacred LOCALAPPDATA db, NOT git). Verified:
- Each role's sidebar shows only its allowed modules.
- **Direct-URL module block works server-side** (e.g. stafftest → `/receipts/new/` →
  "Fee Collection access nahi hai — Permission Required"), not just hidden links.
- **Viewer**: can VIEW all lists (marks, staff open) but every create/edit/delete
  (`/students/new/`, `/staff/salary/new/`, `/receipts/new/`) → "View / print only" denied.

### PENDING (this is where to pick up)
1. **Verify Render online deploy** of `1d15f53` at
   `https://schoolsoft-english-medium.onrender.com` — confirm the footer/Logout fix and
   service-worker fix are live (hard reload once). Free instance sleeps (~50 s cold start);
   online DB is separate Postgres (won't have the 1213 desktop students — expected).
   Auto-deploy triggers on push, but confirm it actually completed on the Render dashboard.
2. Marks source still unresolved (fresh `Testmark2.csv` exported 0 rows earlier; existing
   10,036 marks retained). Confirm correct current-marks mapping when needed.
3. Older pending items above still stand: change default admin password on both DBs, rotate
   Render DB credential, custom domain CNAME, Render free-DB expiry plan (Aug 1, 2026).
4. Optional: deactivate/delete the 5 test users from the dev DB (harmless; not shipped).

## PDF polish plan — Claude's review (July 4, 2026) — READ before executing the "Design Polish" plan

A "PDF Generation Design Polish (Premium SaaS Look)" plan exists for `core/pdf.py`
(unified `_school_header`, brand colors, watermark, cleaner tables for Marksheet / TC /
Character Certificate). The cosmetic parts are fine and low-risk, BUT the plan is
**visual-only and misses the more important content gap.** Apply these corrections:

**1. CONTENT before cosmetics — the Transfer Certificate is missing legally-required fields.**
Compare our current app TC to the legacy VB app's official bilingual TC
(स्थानान्तरण प्रमाण-पत्र / TRANSFER CERTIFICATE, 23 numbered fields). Our TC lacks, at minimum:
UDISE Code (09591200129), **PEN** (Permanent Education Number), **Book No. / S.R. No.**,
Nationality, **SC/ST/OBC category**, **DOB in words** (not just figures), Subjects offered,
"class last studied — in words", whether failed, fee concession nature, NCC/Scout, struck-off
date, School category (Govt/Independent), Prepared-by / Checked-by / Principal + seal, and the
bilingual Hindi/English labels + officiating-principal note. Decide with the user whether to
**replicate the official government format** (recommended if TCs are used officially) and pin
the exact field list FIRST. A pretty-but-incomplete TC is worse than a plain complete one.

**2. Hindi/bilingual text needs an embedded Unicode font.** ReportLab default fonts do NOT
render Devanagari. Must bundle + `pdfmetrics.registerFont` a Devanagari font (e.g. Noto Sans
Devanagari) and add it to `SchoolSoft.spec` datas so the EXE ships it. Non-trivial — plan for it.

**3. Do NOT put the "SCHOOLSOFT" watermark on TC or Marksheet.** Fine on internal receipts, but
a watermark on an official Transfer Certificate / Marksheet looks unprofessional and can make it
look invalid. The plan proposes adding it to the marksheet — skip that for official docs.

**4. Prefer the official/authoritative look over "premium SaaS" for the TC.** Alternating fancy
row colors on a legal certificate reduce credibility for board/inspection. Keep the TC close to
the government format; reserve the premium styling for Marksheet + receipts.

**5. Marksheet "AB" (absent) handling:** current sample shows "AB" for a subject yet still totals
568/900 — verify absent subjects are handled correctly in total/percentage/grade logic, not just
visually.

**Recommended split:** (A, priority) TC content completeness + Devanagari font; (B, low-risk)
cosmetic polish for Marksheet + receipts. `manage.py test` must stay green; PDF tests should
assert content, not just 200 OK. Keep A4 sizes as-is. Logo embed in letterhead is good.

## Latest checkpoint - July 4, 2026 evening (after `b7dbeee`)

Latest commit: `b7dbeee fix(ui): scope student quick actions to permissions`.

What changed after the previous handoff:
- Students module has been polished for premium UI and fast data entry.
- `student_detail.html`: Transformed into a premium dashboard with a "Quick Actions" panel (Pay Fee, Marksheet, TC, etc.). Write actions are hidden for read-only users; Pay Fee is shown only to users with Fee Collection access; Marksheet is shown only to users with Marks access.
- `student_list.html`: Polished with a new premium filterbar and table design. Row click opens the profile; Edit is hidden for read-only users; Marks action is shown only to users with Marks access.
- `student_form.html`: Compacted using scoped `.student-entry` CSS for a denser, more readable layout (34-36px input heights).
- `core/views.py`: `receipt_create` view updated to support `?student=<id>` pre-selection for the "Pay Fee" quick action.
- `static/core/styles.css`: Scoped CSS added for `.student-profile-page`, `.student-list-page`, and `.student-entry`.
- Verification done before commit:
  - `manage.py check`: pass
  - `manage.py test`: 22/22 pass for all three phases and the final permission-scope correction.
  
Important database reminder:
- Local browser/dev DB, desktop EXE DB, and Render PostgreSQL are separate.
- Test users created on local dev do not automatically appear online or in the EXE.
- Online and EXE currently showing only `admin` is expected unless users are created there.
- Active student counts can differ by DB. Do not guess or "fix" counts blindly.
  Active means the current app/model status, originally mapped from legacy `TC_ISSUE=NO`;
  inactive/TC means `TC_ISSUE=YES`. Always verify current DB counts before editing.

Recommended next manual work:
1. In Render and EXE, login as admin and create real users using `+ New user`.
2. Suggested users/roles:
   - fee clerk: Students & Admissions, Fee Collection, Receipts, Dues, Collection Report,
     Fee Setup, School Profile
   - admission clerk: Students & Admissions, School Profile
   - exam clerk: Students & Admissions, Marks & Marksheets, School Profile
   - staff clerk: Staff & Salary, Transport, School Profile
   - viewer: View only + required modules
3. Login as each user and verify:
   - sidebar only shows permitted modules
   - direct URL access is blocked server-side
   - view-only users can view/print but cannot create/edit/delete
4. If any source CSS/template changes are made, remember:
   - run `python manage.py collectstatic --noinput`
   - rebuild EXE with `build-desktop.bat` before shipping desktop
   - close and reopen the EXE fully
   - for browser/PWA cache, bump the CSS `?v=` cache-buster and service-worker cache name

## Antigravity handoff prompt

Copy/paste this into Antigravity before asking it to continue:

```text
You are joining the SchoolSoft modernization project.

Workspace root:
D:\english medium

Main Django project:
D:\english medium\schoolsoft_web

First read:
1. D:\english medium\schoolsoft_web\CODEX-HANDOFF.md
2. git log --oneline -8
3. git status --short --branch

Current latest commit:
2b46809 fix(ui): prevent horizontal overflow on smaller screens

Project summary:
- SchoolSoft is a Django + vanilla CSS School ERP.
- It runs as:
  1. local dev browser
  2. Windows desktop EXE via PyInstaller ONEDIR
  3. online Render website with PostgreSQL
- These three environments can have different databases. Never assume users/data created in
  one are present in another.

Current stable features:
- Login is required before using the app.
- Dashboard, Students, Fee Collection, Receipts, Dues, Collection, Marks, Staff, Transport,
  School Profile are styled and working.
- PWA support exists; Android/iPhone can add the site to home screen.
- Fee collection improvements exist: month chips, duplicate warning, custom student dropdown,
  Save & Print flow.
- Users & Permissions feature exists inside the app:
  - `/users/`
  - admin-only
  - create/edit/toggle users
  - role presets for fee, admission, exam, staff, viewer, custom
  - view-only users are blocked from create/edit/delete
  - direct URL module access is protected server-side
- Latest Users & Permissions table polish is in `cab40ad`.
- Confirmed role matrix is documented in `8b605ce`.
- Students module polish is complete through `b7dbeee`:
  - profile quick-action dashboard
  - student list/filter/table polish
  - compact admission/edit form polish
  - quick actions scoped to user permissions

Critical rules:
- Do not bulk append CSS with shell commands. A previous append truncated styles.css.
- Edit source files only, review diffs, and keep changes scoped.
- Source CSS: `static/core/styles.css`
- Source templates: `templates/...`
- The EXE reads bundled files under `dist/SchoolSoft/_internal/`; source edits do not appear
  in EXE until collectstatic + rebuild.
- After CSS/template changes:
  1. run `python manage.py collectstatic --noinput`
  2. run tests
  3. rebuild EXE with `build-desktop.bat` if desktop needs the change
  4. close/reopen EXE fully
  5. bump CSS cache-buster/service worker cache if browser/PWA does not refresh

Data rules:
- Do not change student active/inactive counts blindly.
- Active student logic must respect the app/model status and legacy mapping from
  `TC_ISSUE=NO`; inactive/TC from `TC_ISSUE=YES`.
- If counts differ between local, EXE, and Render, first identify which DB is being used.

Suggested next task:
- Phase 2: Fees Module (Fee Collection form, Receipts List, Dues Report, Collection Report) UI polish.
- Update the Fee Collection form to use the dense `.student-entry` style layout, and polish the Receipts List and Reports to match the premium `.premium-table` look.

Before making changes:
- Run `git status --short --branch`.
- If dirty, inspect diffs and do not overwrite user changes.
- Prefer small commits with clear verification notes.
```

## Role Matrix (Confirmed July 4, 2026)

The following role presets are available and have been verified across both Render and Desktop EXE:

| Role Name | Access Type | Granted Modules | Blocked Modules |
| --- | --- | --- | --- |
| **admin** | Full Write | All | None |
| **fee** | Full Write | Students, Fee Collection, Receipts, Dues, Collection, Fee Setup, School Profile | Marks, Staff, Transport |
| **admission** | Full Write | Students, School Profile | Fees, Marks, Staff, Transport |
| **exam** | Full Write | Students, Marks, School Profile | Fees, Staff, Transport |
| **staff** | Full Write | Staff, Transport, School Profile | Students, Fees, Marks |
| **viewer** | Read Only | All (can view lists and print reports) | Cannot create, edit, or delete anything |

*Note: All roles implicitly have access to the Dashboard.*

## Fees Module — Review Guardrails (Claude review, July 4, 2026)

**Fees module is HIGH-RISK — this is where the original fee-head overlap and the
styles.css corruption first started. Read these guardrails and follow the phasing
BEFORE writing any code.**

Do NOT start coding until you inspect: `templates/core/receipt_form.html`,
`static/core/receipt-form.js`, the `FeeReceipt` model in `core/models.py`, and the
current CSS around `.fee-desk` / `.classic-fee-heads` in `static/core/styles.css`.

Confirmed decisions (from owner, July 4):
1. Month chips stay as individual rounded chips — only polish active/hover/focus
   state (no segmented toggle).
2. Desktop fee form stays dense / two-column; stack only on mobile.
3. Keep **Save & Print (F9)** as the primary action.
4. Minimum DOM/JS touch: do NOT change `receipt_form.html` DOM unless absolutely
   necessary. `receipt-form.js` relies on element IDs / names / data-attributes —
   keep them safe. If DOM changes, update `receipt-form.js` in lockstep and test a
   real receipt cycle.
5. Scope all CSS under `.fee-desk` or `.fee-desk-page` only. Do NOT add broad global
   `.premium-table` / `.premium-filterbar` rules.
6. Never use shell append / `cat >>` for `styles.css` — use the file editor /
   apply_patch only. (styles.css was corrupted this way before; baseline safe
   commit = `925200d`.)
7. Verify whether `FeeReceipt` has a cancelled/status field BEFORE styling cancelled
   receipts. If the field does not exist, that part cannot be built.
8. Run `manage.py check` and `manage.py test` (keep green).
9. Manual verification (mandatory, on dev-server AND the EXE): student select →
   month chips → duplicate-overlap warning → totals → Save & Print →
   receipt detail / PDF / print; and 1366×768 with no horizontal overflow.
10. Update CODEX-HANDOFF.md after completion.

Phasing (owner direction): **Phase 1 = Fee Collection form polish ONLY.** Receipts
List, Dues Report, and Collection Report come in a later phase.

Exact prompt to give Antigravity/Codex:
~~~
Add a "Fees Module Review Guardrails" section to CODEX-HANDOFF.md before implementing.

Important: Fees module is high-risk. Do not start coding until you inspect
receipt_form.html, receipt-form.js, FeeReceipt model, and current CSS around
.fee-desk/.classic-fee-heads.

Use these decisions:
1. Keep month chips as individual rounded chips; only polish active/hover/focus state.
2. Keep desktop fee form dense/two-column. Stack only on mobile.
3. Keep Save & Print (F9) as the primary action.
4. Avoid DOM changes in receipt_form.html unless absolutely necessary. If DOM changes,
   update receipt-form.js and test a real receipt cycle.
5. Scope CSS under .fee-desk or .fee-desk-page only. Do not add broad global
   .premium-table/.premium-filterbar rules.
6. Do not use shell append/cat >> for styles.css. Use file editor/apply_patch only.
7. Verify whether FeeReceipt has a cancelled/status field before styling cancelled receipts.
8. Run manage.py check and manage.py test.
9. Manual verification: student select, month chips, duplicate warning, totals,
   Save & Print, PDF/print, 1366x768 no horizontal overflow.
10. Update CODEX-HANDOFF.md after completion.
~~~

## 2026-07-05 Checkpoint - Fees, Receipt PDF, and Local Test Cleanup

Latest confirmed commit before this handoff update:

- `2d6b64a fix(pdf): keep dense fee receipts on one page`

Current repo health at checkpoint:

- `git status --short --branch` is clean against `origin/main`.
- `static/core/styles.css` integrity check passed:
  - line count around 4949
  - braces 824/824
  - `.student-entry` present
  - `.fee-desk` present
  - no truncated `.fee-desk .classic-fee-he` selector
- Continue running `git diff HEAD --stat` and `git diff HEAD --ignore-all-space --stat`
  after every commit because Antigravity previously reverted local working-tree
  files to stale copies after successful commits.

### Completed Since The Previous Checkpoint

Fees module UI:

- `35000a7` polished the Fee Collection page with the high-density `.fee-desk`
  layout, rounded month chips, two-column desktop layout, sticky payable rail, and
  primary `Save & Print (F9)` workflow.
- `d37e366` reused existing premium components for Receipts List, Dues Report, and
  Collection Report. This phase intentionally did not edit `styles.css`.

Receipt PDF:

- `core/pdf.py` receipt generation was compacted so dense receipts fit on one A4
  page.
- A regression test was added in `core/tests.py` to create a receipt with many fee
  heads and assert the generated PDF stays at one page.
- `.gitignore` now ignores local `tmp/` verification artifacts.
- `manage.py test` passed 23/23 after the PDF fix.
- Verified with Poppler `pdfinfo.exe`:
  - old dense `SF-101` before fix: 2 pages
  - fixed `SF-101`: 1 page
  - desktop DB test receipt `MR-20260705090215`: 1 page
- User verified visually in EXE and Adobe Reader that
  `MR-20260705090215 (1).pdf` shows `1 / 1` and the signature/footer remain on the
  same page.

Local desktop test cleanup:

- `MR-20260705090215` was a false/test receipt created only for checking the
  one-page PDF behavior.
- User deleted it through Django admin:
  `Admin -> Core -> Fee receipts -> MR-20260705090215 -> Delete`.
- Delete confirmation showed 1 `FeeReceipt` and 11 related `FeeReceiptLine` rows.
- After deletion the desktop dashboard showed:
  - receipts today: 0
  - total dues: Rs. 3,27,350
  - active students: 364
  - total receipts: 664
- This cleanup was local desktop DB work. Do not assume the same receipt existed on
  Render/PostgreSQL unless separately verified.

### Important Accounting Note

For real receipts, prefer a future Cancel/Void workflow instead of hard delete.
Hard delete is acceptable only for deliberate test/false entries while the system
is still being tested. A production accounting system should preserve receipt
history with cancelled status, cancellation reason, cancelled time, and cancelled
by user.

### Recommended Next Plan

1. Add a proper `Cancel / Void Receipt` workflow before adding more fee-accounting
   features.
   - Add fields such as `is_cancelled`, `cancelled_at`, `cancelled_by`, and
     `cancel_reason`.
   - Show cancelled receipts clearly in the receipt register.
   - Exclude or separately report cancelled receipts in dues, collection totals,
     and dashboard KPIs.
   - Keep an audit trail; do not delete real receipts.
2. Improve the receipt detail/register actions:
   - View
   - PDF
   - Print
   - Void/Cancel, permission guarded
3. Re-test role permissions after the void workflow:
   - `fee_clerk` can create receipts and cancel only if allowed.
   - `viewer` can view/print but cannot create, edit, delete, or cancel.
4. Then continue modules in the agreed order:
   - School Profile
   - Fee Structure
   - Marks
   - Staff
   - Transport
5. Before building desktop EXE after any source/template/static change:
   - verify git clean
   - run tests
   - run `collectstatic`
   - run `build-desktop.bat`
   - fully close and reopen the EXE

### Prompt For Antigravity / Other AI

```text
You are joining the SchoolSoft modernization project at:
D:\english medium\schoolsoft_web

First read CODEX-HANDOFF.md completely. The latest important checkpoint is
2026-07-05, with commit `2d6b64a fix(pdf): keep dense fee receipts on one page`.

Current stable facts:
- Desktop, web, PWA, users/permissions, Students module polish, Fees module polish,
  and one-page receipt PDF fixes are already in place.
- Active students are 364, total students are 1,213. Do not recalculate active
  students as 596; active comes from TC/inactive status.
- The false local test receipt `MR-20260705090215` was deleted from the desktop DB
  through Django admin. This was a test cleanup, not a new feature.
- Real receipts should not be hard-deleted in production. The next recommended
  feature is a proper Cancel/Void Receipt workflow with audit trail.

Before editing anything:
1. Run `git status --short --branch`.
2. Run `git diff HEAD --stat`.
3. Run `git diff HEAD --ignore-all-space --stat`.
4. Verify CSS integrity:
   - `.student-entry` exists
   - `.fee-desk` exists
   - braces are balanced
   - no truncated `.fee-desk .classic-fee-he` selector

Critical rules:
- Do not use shell append/cat >> for styles.css. Use file editor or apply_patch.
- Do not touch `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` unless explicitly asked.
- Do not edit generated staticfiles/dist copies as source of truth.
- Source files are under `templates/`, `static/core/`, and `core/`.
- After CSS/template/source changes: run tests, collectstatic, rebuild EXE, close
  and reopen the desktop app.
- After every commit, verify `git status` and both diff commands again because the
  local working tree has previously reverted to stale copies after successful commits.

Recommended next task:
Implement a safe Cancel/Void Receipt workflow, not a delete button, unless the user
explicitly asks for test-data cleanup through Django admin.
```

## 2026-07-05 Checkpoint - Cancel/Void Receipt Workflow Completed

Completed commits:

- `540b63d feat(fees): implement audit-trailed receipt cancellation with PDF watermark and UI updates`
- `827d1fe fix(fees): include receipt cancellation backend and migration`

Important correction:

- Antigravity first committed only the UI/PDF/tests portion of the cancellation
  work. The actual backend files (`core/models.py`, `core/views.py`, `core/urls.py`,
  migration `0010_feereceipt_cancellation.py`, and
  `templates/core/receipt_cancel_confirm.html`) were still uncommitted.
- Codex verified this with `git status`, inspected the diffs, ran checks/tests, then
  committed the missing backend/migration work separately in `827d1fe`.

What the completed feature does:

- Adds audit fields to `FeeReceipt`:
  - `is_cancelled`
  - `cancelled_at`
  - `cancelled_by`
  - `cancel_reason`
- Adds route:
  - `/receipts/<pk>/cancel/`
- Adds cancellation confirmation screen requiring a reason.
- Shows `Cancel / Void Receipt` on receipt detail only for write-capable receipt
  users and only when the receipt is not already cancelled.
- Shows a cancelled banner on receipt detail with reason, timestamp, and user.
- Shows cancelled badge / muted row styling in receipt register.
- Excludes cancelled receipts from:
  - dashboard receipt/dues totals
  - receipt register aggregate totals
  - dues report source query
  - collection report source query
- Keeps cancelled receipts visible for audit instead of hard deleting.
- Adds a large diagonal `CANCELLED` watermark to cancelled receipt PDFs.

Verification:

- `manage.py check` passed.
- `manage.py makemigrations --check` passed with no new changes.
- `manage.py test` passed 25/25.
- Final post-push checks passed:
  - `git status --short --branch` clean against `origin/main`
  - `git diff HEAD --stat` empty
  - `git diff HEAD --ignore-all-space --stat` empty
  - CSS integrity: `.student-entry` present, `.fee-desk` present, braces balanced,
    no truncated fee selector.

Next manual verification before EXE rebuild:

1. Run migrations on the target DB if needed.
2. Create a small test receipt.
3. Cancel it from receipt detail with a clear reason.
4. Confirm receipt detail shows cancelled banner.
5. Confirm receipt register shows cancelled badge.
6. Download/open PDF and confirm `CANCELLED` watermark.
7. Confirm Collection Report excludes the cancelled receipt.
8. Confirm Dues/Dashboard totals behave as expected.

Do not rebuild the desktop EXE until the user confirms this browser/manual flow is
correct. After approval: run tests, `collectstatic`, `build-desktop.bat`, then fully
close and reopen the EXE.

## 2026-07-05 Checkpoint - Audited Receipt Correction Workflow Phase 1

Completed commits:

- `c5c6087 feat: audited receipt correction workflow (Phase 1)`
- `f791306 fix(pdf): adjust footer margin for edited receipt PDF`

What the completed feature does:

- Adds correction/audit fields to `FeeReceipt`:
  - `is_edited`
  - `edited_at`
  - `edited_by`
  - `edit_reason`
  - `edit_count`
- Adds `FeeReceiptAuditLog` with:
  - `action`
  - `changed_by`
  - `reason`
  - `before_snapshot`
  - `after_snapshot`
  - `changes`
- Adds route:
  - `/receipts/<pk>/edit/`
- Adds a receipt correction form based on the fee receipt form.
- Requires a correction reason before saving edits.
- Blocks edits on cancelled receipts.
- Recalculates receipt totals server-side after correction.
- Shows `Edit / Correct` action on receipt detail for write-capable users.
- Shows amber edited/corrected banner and audit history on receipt detail.
- Shows an `EDITED` badge on the receipt register. Cancelled status takes priority
  visually if a receipt is later cancelled.
- Adds an amber diagonal `EDITED` watermark to corrected receipt PDFs, plus a footer
  note with edit date/user/reason. Cancelled watermark takes priority.
- Registers receipt audit logs as read-only in Django admin.

Important implementation note:

- Antigravity reported 34 tests passing, but Codex independently verified the actual
  current test suite count is 26. Treat 26/26 as the known-good verification number
  for this checkpoint unless new tests are added later.

Independent verification by Codex:

- `manage.py makemigrations --check` passed with no new changes.
- `manage.py check` passed.
- `manage.py test` passed 26/26.
- `showmigrations core` shows:
  - `[X] 0010_feereceipt_cancellation`
  - `[X] 0011_feereceipt_edit_count_feereceipt_edit_reason_and_more`
- Post-check working tree was clean:
  - `git status --short --branch` clean against `origin/main`
  - `git diff HEAD --stat` empty
  - `git diff HEAD --ignore-all-space --stat` empty
- CSS integrity remained good:
  - 4949 lines
  - 824 opening braces / 824 closing braces
  - `.student-entry` present
  - `.fee-desk` present
  - no truncated `.fee-desk .classic-fee-he {` selector

Next manual verification before EXE rebuild:

1. Create a test receipt.
2. Open receipt detail and click `Edit / Correct`.
3. Change one fee amount or received amount.
4. Enter a clear reason such as `wrong amount corrected`.
5. Save and confirm:
   - receipt detail shows edited/corrected banner
   - audit history shows before/after/change details
   - receipt register shows `EDITED` badge
   - downloaded PDF has `EDITED` watermark and footer note
6. Cancel the corrected receipt and confirm:
   - edit action disappears
   - cancelled banner appears
   - cancelled PDF watermark takes priority over edited watermark

Do not rebuild the desktop EXE until the user confirms the browser/manual correction
flow is correct. After approval: run tests, `collectstatic`, `build-desktop.bat`,
then fully close and reopen the EXE.

## Yearly Legacy Fee Import Planning - Snapshot + Dry-Run Checkpoint (2026-07-05)

User clarified that legacy data is split across yearly folders:

- `D:\english medium\1` through `D:\english medium\9`
- each yearly folder contains a `SCHOOL7.mdb`
- subfolders inside those yearly folders should be ignored
- exported CSVs are under `D:\english medium\migration_audit\yearly_exports`

Important: do not import or delete production/local data until the user explicitly
approves after reviewing the dry-run reports.

Implemented source changes:

- Added `FeeReceipt` snapshot fields:
  - `student_name_snapshot`
  - `father_name_snapshot`
  - `class_snapshot`
  - `section_snapshot`
- Added display fallback properties on `FeeReceipt`:
  - `display_student_name`
  - `display_father_name`
  - `display_class_name`
  - `display_section_name`
  - `display_class_section`
- Receipt create/edit now stores snapshots from the current student.
- Receipt detail/list/recent receipts/collection report/PDF now prefer snapshot
  values and fall back to the live student relation.
- Created migration:
  - `core/migrations/0012_feereceipt_class_snapshot_and_more.py`
- Improved `core/management/commands/import_yearly_fees.py`:
  - keeps receipt snapshots from legacy CSV rows
  - reports unique missing SIDs, not only per-receipt misses
  - reports SID/name collisions
  - reports generated receipt number collisions
  - reports session-wise receipts/lines/paid/net/due
  - writes CSV audit reports to:
    `D:\english medium\migration_audit\yearly_import_reports`

Local dev schema status:

- Migration `0012` has been applied to local dev SQLite only.
- No yearly import has been performed.
- No cleanup/delete of existing receipts has been performed.

Validation:

- `manage.py makemigrations --check` passed.
- `manage.py check` passed.
- `manage.py test` passed 26/26.
- Dry-run command completed:
  - `.\.venv\Scripts\python.exe manage.py import_yearly_fees --dry-run`

Dry-run summary:

- `receipts_seen`: 11,162
- `receipts_imported`: 11,161
- `receipts_skipped`: 1
- `missing_students`: 5,966 per receipt references
- `missing_students_unique`: 596 distinct legacy SIDs
- `placeholder_students_created`: 5,966 in dry-run accounting
- `placeholder_students_unique`: 596 distinct placeholders
- `lines_imported`: 32,760
- `sum_paid`: Rs. 1,95,05,735.00
- `sum_net`: Rs. 2,91,25,720.00
- `sum_due`: Rs. 96,22,915.00
- `duplicates_found`: 0
- `sid_name_collisions`: 93

Session-wise dry-run stats:

| Session | Receipts | Lines | Missing unique SIDs | Paid | Net | Due |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018-19 | 1413 | 3928 | 1 | 2613000.00 | 2964370.00 | 351370.00 |
| 2019-20 | 1395 | 5252 | 133 | 3167250.00 | 4243250.00 | 1076000.00 |
| 2020-21 | 396 | 752 | 46 | 584650.00 | 1050250.00 | 468450.00 |
| 2021-22 | 1491 | 3481 | 136 | 1362920.00 | 1965475.00 | 602555.00 |
| 2022-23 | 2155 | 5754 | 214 | 3060115.00 | 4470520.00 | 1410405.00 |
| 2023-24 | 1681 | 5009 | 258 | 2545730.00 | 3697175.00 | 1151475.00 |
| 2024-25 | 1394 | 4488 | 280 | 2897800.00 | 4705250.00 | 1807500.00 |
| 2025-26 | 1135 | 3787 | 276 | 2913020.00 | 5452480.00 | 2539460.00 |
| 2026-27 | 101 | 309 | 90 | 361250.00 | 576950.00 | 215700.00 |

Generated dry-run reports:

- `D:\english medium\migration_audit\yearly_import_reports\session_stats.csv`
- `D:\english medium\migration_audit\yearly_import_reports\missing_student_sids.csv`
- `D:\english medium\migration_audit\yearly_import_reports\sid_name_collisions.csv`
- `D:\english medium\migration_audit\yearly_import_reports\receipt_no_collisions.csv`

Next steps, only after user approval:

1. Review the four dry-run CSV reports, especially SID/name collisions. (DONE)
2. Back up local dev database. (DONE)
3. Clean only the previous botched legacy receipt import if approved. Do not touch
   `MR-*` receipts, edited/cancelled test receipts, or current manual entries. (DONE - 667 deleted)
4. Run actual yearly import on local dev only. (DONE - 11,161 imported)
5. Verify dashboard, receipt register, dues, collection report, and old receipt
   PDFs using snapshot fields. (DONE - Smart Default Filters implemented)
6. Only after local verification, repeat the approved process for desktop DB and
   then Render production. (PENDING)

## 2026-07-05 Checkpoint - Smart Default Filters & Local Dev Yearly Import Verified

Completed commits (Pushed to main):
- `Smart default filters added to Dashboard, Receipt Register, Dues Report, Collection Report.`
- `FeeReceiptEntryForm hardened to restrict sessions to is_active=True.`

What the completed feature does:
- Isolates active session data (`2026-27`) by default on all metrics, lists, and forms.
- Permits querying old/imported legacy receipts (from 2018 onwards) via explicit dropdown filters without cluttering the UI.
- All totals strictly exclude cancelled receipts (`is_cancelled=False`).

Verification:
- `manage.py test` passed 26/26.
- Manual browser verification confirmed by user: Dashboard, Collections, Dues, Receipts, and PDFs function flawlessly and respect the isolation of active data.

Next Steps for Codex (URGENT):
The local dev environment has been successfully imported, filtered, and verified. Now you must perform the exact same Yearly Import onto the Desktop EXE database and Render Production database.
1. Backup the Desktop Database: `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` (DONE)
   - Backup Path: `C:\Users\Admin\AppData\Local\SchoolSoft\db.before_yearly_import_20260705_170828.sqlite3`
2. Run cleanup script on Desktop DB to remove previous botched legacy `SF-*` receipts (DO NOT touch `MR-*`). (DONE - 2507 deleted)
3. Run `import_yearly_fees` on Desktop DB using the same CSVs from `yearly_exports`. (DONE)
   - Receipts imported: 11,161
   - Duplicates found: 0
   - Lines imported: 32,760
4. Verify the Desktop App (EXE) runs and shows the correct filtered data. (PENDING USER VERIFICATION)
5. Finally, apply the exact same process to the Render PostgreSQL DB (Production). (PENDING)

## 2026-07-05 Checkpoint - Desktop and Render Data Mirror Verified

Current verified state:

- Desktop EXE database remains the primary source of truth:
  `C:\Users\Admin\AppData\Local\SchoolSoft\db.sqlite3`
- Render production PostgreSQL has now been refreshed from the real Desktop EXE
  database, not the local development `db.sqlite3`.
- The online dashboard at `https://schoolsoft-english-medium.onrender.com`
  was verified by screenshot after refresh.

Verified dashboard numbers after Render sync:

- Active Students: 364
- Total Students: 1,215
- Current Session Receipts: 101
- Total Dues: Rs. 2,15,700
- Today's Collection: Rs. 0
- Receipts Today: 0

Important operational rule:

- Daily real entries must be made in the Desktop EXE only.
- The Render website is secondary: mobile/report viewing and online backup.
- There is no automatic two-way sync between Desktop and Render.
- To update Render later, repeat the safe desktop-to-Render sync process from the
  Desktop EXE database.

Render sync notes:

- A previous attempt accidentally used the local development database export.
- This was corrected by exporting/loading from the Desktop EXE database under
  `%LOCALAPPDATA%\SchoolSoft\db.sqlite3`.
- After correction, Desktop and Render dashboards matched.

Pending cleanup:

- Generated local data dump files are present in the working tree and should not
  be committed unless deliberately needed:
  - `core_data.json`
  - `desktop_data.json`
  - `full_data.json`
  - `legacy_data.json`
  - `scratch_css_matches.txt`
## Latest Daily Update - 06 July 2026

Before continuing Accounts/Cash Book work, read:

- `WORK-UPDATE-2026-07-06.md`

This new daily update summarizes:
- Desktop-to-Online sync BAT fix.
- Accounts/Cash Book Phase 1 MVP.
- Daily Expense, Voucher Register, Voucher Cancel, Cash Book, Ledger Master.
- Staff Advance dropdown behavior in Daily Expense.
- Tests run and current pending commit/build steps.



## 2026-07-06 Checkpoint - Accounts/Cash Book Phase 1 & Staff Migration

Completed today:

1. **Staff Data Migration**: Migrated 21 active staff members from legacy Access SUBGROUP.csv (where they were stored under the SALARY group) into the Django Staff model. The staff dropdown now correctly shows real names like VIVEK SIR, RAVINDRAJI DRIVER, etc.
2. **Staff Advance Logic**: Implemented dynamic JavaScript toggle on both New Daily Expense and New Other Receipt forms. When Staff Advance is selected as the Debit/Credit head, the Paid To text input is hidden and replaced by a dropdown of active staff members.
3. **Receipts Update**: Modified VoucherForm in core/forms.py to allow Advance Ledgers (like Staff Advance) in the credit_account dropdown for receipts. A staff member returning an advance in cash is properly handled as a Receipt.
4. **EXE Rebuilt**:  uild-desktop.bat was run successfully. The new EXE is at dist/SchoolSoft/SchoolSoft.exe.

### Open Question for Codex / User
The user noticed that opening the New Daily Expense form still shows a text box by default. This is the **correct behavior**: the form defaults to Select expense / advance head. The staff dropdown *only* appears if the user explicitly changes the dropdown to Staff Advance.
Please verify with the user if they actually selected Staff Advance in the dropdown before taking the screenshot, or if they expected the Staff Dropdown to appear by default regardless of the expense head.

## 2026-07-06 Checkpoint - Salary Module Phase 2 Finalized

Completed today:
1. Salary Payment creation with live JS calculations for Gross and Net.
2. Negative Net Pay blocked and duplicate valid salary blocked per staff/month.
3. Salary Register implemented and added to sidebar.
4. Salary detail page with PDF payslip generation (Rs. mojibake fixed).
5. Edit and Cancel workflows added with full audit logs to `SalaryPaymentAuditLog`. Snapshot logic captures true DB old values.
6. Cancelled salaries appear distinctly with strikethrough/badges and are excluded from Cash Book and top-level KPIs.
7. Cancelled salary allows recreation of a new valid salary for the same staff/month using a conditional UniqueConstraint on `is_cancelled=False`.

TEST STATUS:
- `python manage.py test core` passed 30/30.
- Manual workflow verified by user (Create, Duplicate block, Edit, Cancel, Recreate, Cash Book check).
- Collectstatic and EXE build successful.

## 2026-07-08 Checkpoint - Legacy Data Import & Cash Book T-Shape UI Redesign

Completed today:
1. **Legacy Data Import**: 
   - `sync_recent_staff.py` and `sync_recent_vouchers.py` successfully imported Staff and Salary payments from old CSV exports into Django models.
   - Handled UniqueConstraint conflicts on Salaries by merging multiple legacy voucher rows (e.g., April and May salaries) into a single `SalaryPayment` slip per staff per month, combining their net pay and remarks.
2. **Cash Book Balance Fix**:
   - Fixed `FeeReceipt` sum calculation in cash book view from `total_amount` to `received_amount`.
   - Set the correct `opening_balance_date` in the local SQLite DB for the `Cash in Hand` ledger so past balances carry over correctly. The resulting negative balances accurately reflect the legacy software's credit balance.
3. **Cash Book T-Shape Redesign**:
   - Redesigned the Cash Book UI to completely mimic the legacy software's Double-Entry "T-Shape" Ledger format.
   - Replaced single `target_date` with `from_date` and `to_date` range filtering.
   - Grouped transactions by day, displaying Receipts on the Left and Payments on the Right.
   - Displayed Opening Balance and Closing Balance to mathematically balance (tally) each day's totals.
   - Fixed print UI in landscape mode using `<colgroup>` and strict `word-break: break-word` to ensure long remarks (like salary details) fit cleanly without breaking the split layout.

TEST STATUS:
- Verified all visual elements with the user, confirming pixel-perfect match to their legacy expectations.
- Ready for Final Deployment/Sync to online server.

## 2026-07-08 Checkpoint - End of Day Sync & Pending Action Items

Completed today:
1. **Desktop-to-Online Sync Fixed**: The legacy Salaries and Vouchers were initially missed because the import script was run on the local dev DB instead of the Desktop EXE DB. Ran the imports on the Desktop DB, fixed the `SalaryPayment.remarks` 255-character length limit issue (PostgreSQL restriction) by truncating strings during import, and successfully synced 55,000+ records to Render.
2. **Salary Register Date Range Filter**: Replaced the single "Month" filter with a "From Date" and "To Date" filter (filtering on `payment_date`). Added a "Payment Date" column to the table. Deployed to Render.

### Priority Action Items for Next Session / Developer

1. **URGENT SECURITY FIXES**:
   - [x] The default admin passwords (`admin`/`admin12345`) MUST be changed on both Desktop and Render immediately. (User confirmed changed on 2026-07-08).
   - [ ] The Render PostgreSQL Database credentials (`DATABASE_URL`) were accidentally pasted in chat screenshots. The database password must be rotated on Render immediately to prevent unauthorized access.
2. **Render Postgres Expiry**:
   - The Render free PostgreSQL database will expire on 1 August (in 3 weeks). The school must decide whether to upgrade to a paid plan (~$7/month) or commit to recreating and reloading the free DB every month.
3. **Transfer Certificate (TC) Content Gaps** — RESOLVED 2026-07-08 (owner decision: English-only TC):
   - Code audit found `category` (SC/ST/OBC) and DOB-in-words were already wired into `build_transfer_certificate_pdf`; only `pen_number` had no input field anywhere in the UI. `udise_code` lives on `SchoolProfile` and is editable via `/admin/` (admin-only, one-time setup — no in-app form needed for a single-record settings field).
   - Owner decided: TC stays **English-only**. ReportLab does not shape Devanagari matras correctly (a known ReportLab limitation, not a missing-font issue — `NotoSansDevanagari` font files/registration were already in place), so replicating the bilingual government format would have required swapping the whole PDF engine (ReportLab -> WeasyPrint/HTML-to-PDF). Not worth it for an English-medium school; skip unless a board/inspection explicitly demands Hindi labels later.
   - Changes made:
     - `core/forms.py` `StudentForm`: added `pen_number` field (label "PEN Number").
     - `templates/core/student_form.html`: added PEN Number input in the "Identity & Enrollment" card.
     - `core/pdf.py` `build_transfer_certificate_pdf`: removed all Devanagari labels/subtitle/`hindi_style`, switched `field_style` and the top meta table from `NotoSansDevanagari` to `Helvetica`. All 23 fields remain, English-only.
   - Not touched: `_premium_header` (used by Character Certificate/Marksheet) still has its optional Devanagari title path — this decision was scoped to the TC only, per the owner's answer.
   - TODO before considered fully closed: run `manage.py test core`, then re-issue/re-check one real student's TC PDF in browser to confirm PEN/UDISE now print when filled in.
4. **Current Session (2026-27) Marks Data** — RESOLVED 2026-07-08 (owner confirmed):
   - Owner confirmed no exams/marks entry has happened yet in the legacy software for 2026-27. `Testmark2.csv` correctly exporting 0 rows for this session is expected, not a bug. No code change needed. Re-export/re-import `Testmark2` once real exams for this session are conducted and entered in the legacy app.
5. **Custom Domain Setup**:
   - Setup `english-medium.thpsic.com` CNAME on Render when convenient (low risk).
6. **Deferred Polish Items**:
   - Accounts UI polish, Staff Advance FK constraints, Library module, native mobile app wrappers (PWA is sufficient for now).

## 2026-07-08 Checkpoint - Category/Caste Data Bug + Full Admission Form Parity

Trigger: owner compared the new-app TC PDF against the legacy TC (screenshots) and spotted
`"5. Whether belongs to SC/ST/OBC"` printing `KOIRI` (a caste name) for one student instead of
`OBC`/`SC`/`ST`/`General`. Owner also supplied the school's real, current official admission
form: `EbenEzer_Admission_Form_English_2026-27.docx` (uploaded + read via Word) as ground truth,
which is more authoritative than the legacy VB software's screen layout.

**Root cause of the Category/Caste bug**: `import_legacy_students.py` line ~175 does
`"category": self.clean(row.get("CATE")) or self.clean(row.get("cast"))`. Whenever the legacy
`CATE` column was blank for a student, the caste name (`cast` column, e.g. KOIRI, YADAV,
MUSLMAN) silently became the stored `category` value. This is a data problem, not something a
code fix alone can safely repair (a caste name cannot be auto-mapped to General/OBC/SC/ST).

**Fix shipped**:
- New read-only audit command `core/management/commands/audit_student_categories.py` — lists
  every student whose `category` is blank or doesn't look like General/OBC/SC/ST/GEN, writes
  `migration_audit/category_audit.csv`. Run with:
  `.\.venv\Scripts\python.exe manage.py audit_student_categories`
  Office staff must review this list and correct each student's Category via the edit form
  before their TC/admission paperwork is finalized. `category` was deliberately kept as a free
  CharField (not a strict choices/enum) rather than force-converting it, since ~1213 live
  student records may have legacy spelling variants (e.g. `GEN` vs `General`) that would
  otherwise silently show as "unset" in a strict dropdown — safer to flag via CSV and let a
  human confirm each one on a live production system.

**Full admission-form field parity added to `Student` model** (owner chose "add everything at
once" after reviewing the real form), all in migration to be created via
`manage.py makemigrations`:
- `apaar_id`, `caste` (separate from `category`), `guardian_name`, `mother_aadhaar_no`,
  `father_aadhaar_no`, `is_minority`, `disability` (choices: None/Visually Impaired/Hearing
  Impaired/Physically Disabled), `email`, `blood_group` (A+/A-/B+/B-/AB+/AB-/O+/O-),
  `weight_kg`, `height_cm`, `village_locality`, `post`, `block`, `district`, `pin_code`.
- Previous-school block (for transfer admissions): `previous_board_name`,
  `previous_passing_year`, `previous_roll_no`, `previous_school_name`,
  `previous_marks_obtained`, `previous_total_marks`, `previous_percentage`.
- Documents Received checklist (admission desk): `doc_tc_received`, `doc_aadhar_received`,
  `doc_marksheet_received`, `doc_birth_certificate_received`,
  `doc_character_certificate_received`, `doc_photo_received`.
- `core/forms.py` `StudentForm`: all new fields added to `Meta.fields`; checkbox fields now
  correctly skip the `form-control` CSS class (loop changed from `field_name != "is_active"` to
  `not isinstance(field.widget, forms.CheckboxInput)`).
- `templates/core/student_form.html`: reorganized into new cards — Social Category (caste,
  category, religion, disability, minority toggle), Health, Previous School (if admitted by
  transfer), Documents Received — using the existing `.entry-card`/`.entry-grid-four` system,
  no new CSS needed.

**Not yet done / next session must**:
1. Run `manage.py makemigrations core` then `manage.py migrate` (new migration not yet created
   or applied — this was written by Claude/Opus without shell access; a human must run it).
2. Run `manage.py test core` — should still be the same test count since no existing test posts
   to the student form directly.
3. Run `manage.py audit_student_categories` and review `migration_audit/category_audit.csv`.
4. Manually open the student edit form in browser to confirm all new cards render correctly and
   save/reload works, then `collectstatic` + `build-desktop.bat` before shipping desktop.
5. TC PDF/print still only uses `category` (unchanged) for the SC/ST/OBC line — `caste` is not
   printed anywhere yet (matches the legacy TC format, which also has no caste line).

## 2026-07-08 Checkpoint - Roll No + Section-by-Class Filter (same review pass)

Owner (via another AI session's review) also found: `roll_no` exists on `Student` but was never
in `StudentForm`, and `current_section` showed ALL sections from every class (A/B/C/D x every
grade) instead of just the ones under the selected class.

Fixed:
- `core/forms.py`: added `roll_no` to `StudentForm.Meta.fields`. Added a `SectionSelect(forms.Select)`
  widget that stamps each `<option data-class="{school_class_id}">` so the browser can filter
  client-side with no extra request. Set as the widget for `current_section`.
- `templates/core/student_form.html`: added a Roll No field next to Current Section. Added JS in
  the existing `DOMContentLoaded` block — on `current_class` change, hides `current_section`
  options whose `data-class` doesn't match, resets the selection if it becomes hidden. Runs once
  on page load too, so the edit form pre-filters correctly for an existing student.

**Owner decision (same session)**: build Photo upload now; skip Bank Details (not needed for
real operations right now — revisit only if the school starts doing scholarship/RTE
reimbursement by bank transfer).

## 2026-07-08 Checkpoint - Student Photo Upload

- `core/models.py`: `Student.photo = models.ImageField(upload_to="student_photos/", null=True, blank=True)`.
- `schoolsoft/settings.py`: added `MEDIA_URL = 'media/'` and
  `MEDIA_ROOT = Path(os.environ.get("SCHOOLSOFT_MEDIA_ROOT", local_data_dir() / "media"))` —
  same env-var-with-fallback pattern already used for `SCHOOLSOFT_SQLITE_PATH`.
- `desktop.py` `configure_desktop_environment()`: now also creates
  `%LOCALAPPDATA%\SchoolSoft\media\` and sets `SCHOOLSOFT_MEDIA_ROOT` to it, so uploaded photos
  survive EXE rebuilds exactly like the sqlite db does.
- `schoolsoft/urls.py`: added an explicit route serving `MEDIA_URL` via
  `django.views.static.serve`, unconditionally (not just when `DEBUG=True`). WhiteNoise only
  serves `STATIC_URL`, not `MEDIA_URL`. This is fine for a single small school's traffic — no
  nginx/object-storage layer needed. **On Render this storage is NOT persistent across
  redeploys/restarts** (ephemeral disk on the free plan) — acceptable since the Desktop EXE
  remains the source of truth; revisit with S3/Cloudinary only if online photo uploads need to
  survive redeploys.
- `core/forms.py` `StudentForm`: added `photo` to `Meta.fields`.
- `core/views.py`: `student_create`/`student_update` now pass `request.FILES` into `StudentForm`
  (required for file uploads — was missing before, would have silently dropped any uploaded
  file).
- `templates/core/student_form.html`: `<form>` tag now has `enctype="multipart/form-data"`
  (REQUIRED for file uploads to reach the server at all — easy to forget). Photo box shows the
  existing photo if set, plus the file input below it.
- `templates/core/student_detail.html`: profile avatar circle shows the real photo when present,
  falls back to the placeholder icon otherwise.
- `static/core/styles.css`: `.student-entry .student-photo-box` gained `overflow: hidden`; added
  `.student-photo-preview { width/height:100%; object-fit:cover }`.
- `.gitignore`: added `media/` — uploaded photos (real student data) must never be committed.
- `SchoolSoft.spec`: NOT changed — `media/` must stay a runtime-only per-user folder, never
  bundled into the EXE build (same rule as the sqlite db). Pillow is not in `hiddenimports`
  explicitly; PyInstaller has a built-in hook for Pillow so this is normally fine, but if the EXE
  rebuild fails to find `PIL`, add `collect_submodules('PIL')` to `hiddenimports` as a fallback.

**Not yet done / next session must**:
1. Run `manage.py makemigrations core` + `manage.py migrate` (adds the `photo` column — bundled
   with the same migration as the admission-form-parity fields above, or its own, whichever
   `makemigrations` generates).
2. Run `manage.py test core`.
3. Manually test: open a student, upload a photo, save, confirm it shows on the edit form photo
   box AND the student profile page avatar. Confirm the image file actually lands under
   `%LOCALAPPDATA%\SchoolSoft\media\student_photos\` (desktop) — not next to the EXE.
4. `collectstatic` + `build-desktop.bat`, then fully close/reopen the EXE and re-test the same
   upload flow inside the packaged app (PyInstaller ONEDIR sometimes behaves differently than
   `runserver` for file writes — verify for real, don't assume).

## 2026-07-08 Checkpoint - Photo Instant Preview + House System + Discipline Record

Note: `core/forms.py`'s `SectionSelect` widget was rewritten by another session between the
previous checkpoint and this one (now uses `optgroups()` + a `_temp_map` dict with defensive
`int(str(value))` handling for `ModelChoiceIteratorValue`, and `current_section.label_from_instance`
was overridden to show just the section letter). Everything below was built on top of that
current version — re-read `core/forms.py` fresh before editing it further, don't assume it still
matches older checkpoints in this file.

**1. Photo instant preview** (owner reported: picked a file, nothing appeared until they
imagined it needed a Save click). Added to `templates/core/student_form.html`: a `change`
listener on the photo `<input>` that reads the picked file with `FileReader` and swaps it into
`#student-photo-box` immediately, client-side only. Actual upload still only persists on submit
(unchanged) - this was a display-only gap, not a save bug.

**2. House System** (owner decisions: auto-suggest + manual override; 4 standard houses
Red/Blue/Green/Yellow, renamable later; not linked to TC General Conduct - separate feature):
- `core/models.py`: new `House(TimeStampedModel)` model (name, color_code, display_order,
  is_active) - a real master-data model, not a hardcoded enum, so it can be renamed/recolored via
  Django admin without a code change. `Student.house` FK added (`on_delete=SET_NULL`, nullable).
- `core/management/commands/seed_houses.py`: creates the 4 default houses if missing (idempotent,
  same pattern as `seed_accounts.py`). Run once: `manage.py seed_houses`.
- `core/forms.py` `StudentForm.__init__`: for NEW students only, auto-suggests the least-populated
  *active* house (`House.objects.filter(is_active=True).annotate(student_count=Count("students")).order_by("student_count", "display_order").first()`)
  as the initial value - staff can still override before saving. Same pattern already used for
  `legacy_sid` auto-suggest.
- `core/admin.py`: `HouseAdmin` registered; `StudentAdmin.list_display`/`list_filter` now include
  `house`.
- `templates/core/student_form.html`: House dropdown added next to Roll No.
- `templates/core/student_detail.html`: House shown in the Student Details card.
- Tests: `HouseAssignmentTests` (2 tests) confirm the least-populated-active-house suggestion
  logic, including that inactive houses are never suggested.

**3. Discipline Record** (owner decisions: Admin/Principal only - not a MODULE_PERMISSIONS entry
assignable to other roles; PTM PDF summary needed; deliberately NOT linked to TC General
Conduct):
- `core/models.py`: new `DisciplineRecord(TimeStampedModel)` - `student` FK, `incident_date`,
  `category` (Late Coming / Attendance / Misconduct / Bullying-Ragging / Property Damage /
  Academic Dishonesty / Uniform-Grooming / Other), `severity` (Minor/Major/Severe),
  `description`, `action_taken`, `parent_notified`, `reported_by` (auto-set to the logged-in
  admin on create).
- `core/access.py`: new `admin_only_required(module_name)` decorator - reuses the existing
  `user_can_manage_users()` check (superuser or `access_all_modules` perm), same gate as the
  Users & Permissions screen. Deliberately NOT added to `MODULE_PERMISSIONS`, so no role preset
  (fee/admission/exam/staff/viewer) can ever be granted this - only a true admin.
- `core/urls.py`: `students/<pk>/discipline/`, `.../discipline/new/`, `.../discipline/pdf/`, all
  wrapped in `admin_only_required("Discipline Records")`.
- `core/views.py`: `discipline_list`, `discipline_create`, `discipline_pdf` (undecorated - the
  urls.py wrapper is where every other view in this app gets its permission gate, matched that
  convention).
- `core/pdf.py`: `build_discipline_summary_pdf(student, records, school_profile)` - PTM handout:
  student info block, severity-count summary line, full records table, teacher/principal
  signature line. Uses the existing `_school_header()` (same as receipts/TC), not the "premium"
  certificate header.
- `core/admin.py`: `DisciplineRecordAdmin` registered (normal CRUD, not read-only - admins may
  need to correct a typo; the record itself is still fully audit-visible via `created_at`/
  `updated_at` on every row from `TimeStampedModel`).
- Templates: `templates/core/discipline_list.html` (table + Add/PDF buttons),
  `templates/core/discipline_form.html` (plain `.form-panel`/`.form-grid`, same pattern as
  `salary_payment_form.html`).
- `templates/core/student_detail.html`: "Discipline Record" quick-action button added, wrapped in
  `{% if can_manage_users %}` (already in the context processor - no new context plumbing
  needed).
- Tests: `DisciplineRecordTests` (2 tests) - confirms a non-admin gets a 403 with "Discipline
  Records" in the response, and that an admin can create a record, see it in the list, and
  download the PDF (200 + `application/pdf`).

**Not yet done / next session must**:
1. Run `manage.py makemigrations core` + `manage.py migrate` (adds `House`, `Student.house`,
   `DisciplineRecord` - likely bundled with the still-unrun photo/admission-form-parity migration
   from the earlier checkpoint above, since none of that has been migrated yet either).
2. Run `manage.py seed_houses` once to create the 4 default houses.
3. Run `manage.py test core` - expect the existing count plus 4 new tests (2 House, 2 Discipline)
   to pass.
4. Manually verify in browser: new student form shows a pre-selected House (and it's the
   least-populated one); Discipline Record button only appears for an admin login, a non-admin
   hitting `/students/<id>/discipline/` directly gets the Hindi permission-denied page; PTM PDF
   downloads and lists incidents correctly.
5. `collectstatic` + `build-desktop.bat` before shipping desktop, same as always.
6. Consider (not done): showing House as a column/filter on `student_list.html` - skipped this
   pass for time, low risk to add later.

## 2026-07-08/09 Checkpoint - ID Card Generator

Owner's "Grand Plan" review offered 5 village-school features (Attendance+WhatsApp alerts, ID
Card Generator, Inventory, Hindi/Bilingual UI, Family Ledger). Owner picked **ID Card Generator
first** (fastest win given Photo upload already exists) and chose to keep working rather than
stop for the night. The other 4 ideas are NOT built - see "Ideas not yet started" below before
picking one up.

What was built:
- `core/pdf.py`: `_id_card_flowable(student, school_profile)` builds one CR80-sized
  (85.6mm x 54mm) card - green header strip with school name, photo (falls back to "No Photo"
  text if the file is missing/unset - wrapped in try/except, never crashes the PDF), name, class-
  section, roll no, **house** (reuses the House feature from the earlier checkpoint), DOB,
  father's name, mobile, footer strip with admission no + session.
  - `build_id_card_pdf(student, school_profile)` - ONE card centered on an A4 page (print, cut,
    laminate individually).
  - `build_id_card_batch_pdf(students, school_profile)` - a 2-column grid of cards across as many
    A4 pages as needed, for printing a whole class/section at once. Handles an empty result set
    without crashing (shows "No students matched the current filter." instead of a blank/broken
    PDF).
- `core/views.py`: `id_card_pdf(request, pk)` (single) and `id_card_batch_pdf(request)` (batch -
  reuses the existing `_get_filtered_students(request)` helper, so it respects whatever
  q/class/section/status filters are currently applied on the Students list - filter to one
  class/section first, then print just that class).
- `core/urls.py`: `students/<pk>/id-card/pdf/` and `students/id-cards/pdf/`, both gated by
  `module_required("students")` (read-only action, no `write=True` needed - same as Admission
  Form/Character Certificate PDFs).
- `templates/core/student_detail.html`: "ID Card" quick-action button (visible to anyone with
  Students access, not admin-only - unlike Discipline Records).
- `templates/core/student_list.html`: "Print ID Cards" button next to "Print Register"/"Export
  Excel", carries `{{ request.GET.urlencode }}` so it prints exactly the currently filtered/
  searched set of students.
- Tests: `IdCardTests` (3 tests) - single card PDF, batch respects class filter, batch with zero
  matching students doesn't error.

Not done / worth knowing:
- Card design is single-sided only (no back side with rules/emergency-contact text) - owner did
  not ask for a back side; add one later if wanted (would need a second `_id_card_flowable`-style
  function and either a second batch grid pass or manual duplex printing).
- No barcode/QR code on the card (would need `reportlab.graphics.barcode` module or a QR library -
  not added, wasn't requested).
- Batch PDF is NOT capped - if run with "All classes" and no filter (1200+ students), it will
  generate a very large PDF and may be slow. Not artificially limited, but the realistic workflow
  (and what the UI nudges toward) is to filter to one class/section first, matching how a school
  actually prints ID cards in batches.

**Update (same day):** migrations `0017_student_apaar_id_...`, `0018_student_photo`, and
`0019_house_disciplinerecord_student_house` have been created and applied, `seed_houses` has been
run (4 default houses exist), and `manage.py test core` passes all 37 tests (House, Discipline,
ID Card, plus the full prior suite). The "run migrations" pending item from every earlier
checkpoint in this file is now DONE - no schema changes are outstanding as of this checkpoint.

## 2026-07-09 Checkpoint - WhatsApp Alerts (free wa.me links)

Owner picked **WhatsApp Alerts** next from the Grand Plan, and explicitly chose the free `wa.me`
deep-link approach over a paid WhatsApp Business API (no signup/business verification/monthly
cost, but every message needs a manual tap-to-send by a staff member - not true bulk-blast).

What was built:
- `core/whatsapp.py` (new) - `normalize_indian_mobile(raw)` turns any stored mobile format
  (10-digit bare, leading-0 11-digit, already-91-prefixed 12-digit) into the digits-only form
  `wa.me` needs, returning `None` for anything too short/garbled rather than guessing.
  `build_wa_link(mobile, message)` returns a `https://wa.me/<number>?text=<urlencoded message>`
  URL or `None`. Plus three message-builders: `fee_due_message`, `ptm_message`,
  `discipline_message`, `general_message` - all plain-string-in/string-out (no model coupling),
  Hinglish wording matching how the school actually talks to parents.
- `core/templatetags/schoolsoft_extras.py` - four new `simple_tag`s (`wa_fee_link`, `wa_ptm_link`,
  `wa_discipline_link`, `wa_general_link`) so templates can build a link in one line:
  `{% wa_fee_link mobile father_name full_name class_name section_name admission_no due_amount school_name as wa_url %}`.
- **Due Report** (`due_report.html` + `due_report` view): new "WhatsApp" column, one link per
  defaulter row with the fee-due amount already filled into the message. `get_due_report_rows`
  now also selects `student__admission_no` (was missing) so the message can include it.
- **Student Profile** (`student_detail.html` + `student_detail` view): a "WhatsApp Fee Reminder"
  quick-action button (only shown if the student has a due balance > 0 - view now computes
  `due_total` via `FeeReceipt` aggregate), plus a general-purpose "Send WhatsApp Message" card
  with a mobile-number dropdown (primary/secondary) and an editable textarea pre-filled with a
  greeting - "Open in WhatsApp" builds the link **client-side in JS** (mirrors
  `normalize_indian_mobile` in JS) so staff can freely edit the message before it's sent, e.g. for
  PTM reminders, general notices, TC-ready notices - anything that doesn't have its own template.
- **Discipline Record list** (`discipline_list.html` + `discipline_list` view): new "WhatsApp"
  column with a "Notify" link per record (pairs with the existing `parent_notified` field - this
  gives staff a one-click way to actually send that notification, doesn't change the field itself).
- Tests: `WhatsAppLinkTests` (8 unit tests on `core/whatsapp.py` directly - number normalization
  edge cases, link building, message content) + `WhatsAppViewIntegrationTests` (3 tests - Due
  Report page contains a `wa.me` link for a student with dues, Student Profile contains one when
  due > 0, Student Profile doesn't crash when the student has no mobile number at all).

Design notes / things to know:
- **Nothing is ever sent automatically.** Every link just opens WhatsApp with text pre-filled;
  the staff member still has to look at it and press Send inside WhatsApp themselves. This was
  the whole point of choosing the free approach - it's a convenience/time-saver, not automation.
- Numbers that don't normalize to something wa.me-shaped (too short, blank, garbled legacy data)
  quietly show "No mobile" instead of a broken link - never guesses or 500s.
- The message-builder functions in `core/whatsapp.py` take plain strings/numbers, not model
  instances, on purpose - keeps them usable from both a `.values()` dict (Due Report rows) and a
  real `Student` object (Profile page, Discipline list) without needing two code paths.

Not done / worth knowing:
- No dedicated PTM or "TC ready" button anywhere yet - the general free-text WhatsApp card on the
  Student Profile page covers those use cases today (staff types/edits the message there). Could
  add dedicated one-click buttons later if a specific message gets used often enough to be worth
  hardcoding.
- No bulk multi-select-and-send-all - by design, this is the free/manual tier. A real bulk-blast
  would need the paid WhatsApp Business API (still not decided/started).
- No migrations needed for this checkpoint - no model changes, just a new plain Python module +
  template tags + view/template edits.
- Next session should still run `manage.py test core` after this checkpoint to confirm the 11 new
  WhatsApp tests pass alongside everything else.

## 2026-07-09 Checkpoint - Inventory (Uniform/Books)

Owner picked **Inventory** next from the Grand Plan (after WhatsApp Alerts). Scope: track what
uniform/shoes/books/stationery is issued to which student, at what price, with support for
concessions/free issues - not a stock-in/purchasing system (no supplier-side "stock on hand"
tracking was requested or built).

What was built:
- `core/models.py` - two new models after `DisciplineRecord`:
  - `InventoryItem` - master catalog: `name`, `category` (uniform/shoes/book/stationery/other),
    `unit_price`, `is_active`.
  - `InventoryIssue` - one row per issue: `student` FK, `item` FK (PROTECT - can't delete an item
    that's been issued), `issue_date`, `quantity`, `unit_price` (**snapshotted** from the item at
    issue time so a later price change doesn't rewrite history), `amount_charged` (what was
    actually collected - the single source of truth for concessions, not a separate flag),
    `remarks`, `issued_by`. Properties: `is_free` (`amount_charged == 0`), `full_price`
    (`unit_price * quantity`), `concession_amount` (`full_price - amount_charged`, floored at 0).
  - New custom permission `access_inventory` added to the existing `ModuleAccess` Meta.permissions
    list (same mechanism as every other module) - **needs a migration**, see below.
- `core/access.py` - `"inventory": "access_inventory"` added to `MODULE_PERMISSIONS`. This is a
  normal module (unlike Discipline Records) - assignable to any role via Users & Permissions, not
  admin-only. No role preset grants it by default except Administrator and Viewer (both use
  `ALL_KEYS`); Fee/Admission/Exam/Staff/Accounts desks don't get it automatically - owner can add
  it to a user via the "Custom" role checkboxes in Users & Permissions if a specific staff member
  (e.g. store clerk) needs it.
- `core/user_admin.py` - `("inventory", "Inventory (Uniform/Books)")` added to `MODULES_UI` so it
  shows as a checkbox on the Users & Permissions screen.
- `core/forms.py` - `InventoryItemForm` (name/category/unit_price/is_active) and
  `InventoryIssueForm` (item/issue_date/quantity/amount_charged/remarks - `unit_price` is NOT a
  form field, it's set server-side from the item at save time so it can't be spoofed/mistyped).
  `InventoryIssueForm.__init__` restricts the item dropdown to `is_active=True` items only.
- `core/views.py` - `inventory_item_list`, `inventory_item_create`, `inventory_item_toggle_active`
  (POST-only, mirrors `user_toggle_active`), `inventory_report` (global filterable list - q/class/
  item/date range, with quantity + amount-collected totals), `inventory_issue_list` (per-student,
  same shape as `discipline_list`), `inventory_issue_create` (sets `unit_price` from the item,
  `issued_by` from `request.user`).
- `core/urls.py` - `inventory/items/`, `inventory/items/new/`, `inventory/items/<pk>/toggle-active/`,
  `inventory/report/`, `students/<pk>/inventory/`, `students/<pk>/inventory/new/` - all gated by
  `module_required("inventory", ...)` (read vs write split same as every other module).
- Templates (new): `inventory_item_list.html`, `inventory_item_form.html`,
  `inventory_issue_list.html` (shows per-row concession amount, "Free" badge when
  `amount_charged` is 0), `inventory_issue_form.html` (JS auto-fills `amount_charged` as
  `item.unit_price * quantity` when the item or quantity changes - staff can still edit it down
  for a concession/free issue afterward), `inventory_report.html` (Due-Report-style filter bar +
  table + totals).
- `templates/base.html` - new "Inventory" nav link, gated by `access.inventory`, placed after
  Transport.
- `templates/core/student_detail.html` - new "Inventory" quick-action button, gated by
  `access.inventory` (visible to anyone with the module, not admin-only).
- `core/admin.py` - `InventoryItemAdmin`, `InventoryIssueAdmin` registered.
- Tests: `InventoryTests` (6 tests) - item create + appears in catalog, toggle active, issue with
  a concession (checks `unit_price` snapshot, `concession_amount`, `is_free`, `issued_by`), a
  fully-free issue shows "Free" in the list, report filters correctly by item, report doesn't
  crash on an empty result.

**Update (same day):** migrations applied, `manage.py test core` passes all **54 tests** (6 new
`InventoryTests` + prior 48). One small bug was caught and fixed during this pass:
`inventory_issue_list.html` rendered `issue.issued_by.get_full_name|default:issue.issued_by.username`
directly, which is unsafe when `issued_by` is `NULL` (e.g. an issue created without a logged-in
user, or after a user account is deleted - the FK is `on_delete=SET_NULL`); it's now wrapped in an
explicit `{% if issue.issued_by %}...{% else %}-{% endif %}`. Migrations item below is DONE.

Not done / next session must:
1. ~~Run migrations~~ - DONE, applied.
2. ~~Run `manage.py test core`~~ - DONE, 54/54 pass.
3. Manually verify in browser: add an item on the Items page, toggle it inactive and confirm it
   disappears from the issue-form dropdown, issue an item to a student (check the JS auto-fills
   the amount and that editing it down for a concession sticks), confirm the Distribution Report
   filters work, and grant a non-admin test user the "Inventory" checkbox via Users & Permissions
   to confirm normal (non-superuser) access works end to end.
4. No supplier-side "stock on hand" / purchase-in tracking exists - if the school later wants to
   know "how many uniform sets are left in the store room", that would need a separate
   stock-transaction model (`StockIn`) and is out of scope for this checkpoint.
5. `collectstatic` + `build-desktop.bat` - owner has now asked for this rebuild (after stacking ID
   Card, House, Discipline, WhatsApp, Inventory across several checkpoints without rebuilding).
   **Next action: run the rebuild**, then fully close and reopen the desktop EXE (not just
   refresh) and spot-check all five features there, since the desktop build is the real
   source-of-truth environment, not the dev server.

## 2026-07-10 Checkpoint - Family Ledger (last of the 5 Grand Plan ideas)

Owner explicitly ruled out Hindi/Bilingual UI for this session ("filhal nahi chahiye") and picked
**Family Ledger** - the last of the original 5 Grand Plan ideas. Two design decisions were
confirmed with the owner up front (both matter for a real 1213-student production database):
matching should be **suggest-then-manually-confirm, never auto-link**, and the family page should
show **combined due + a combined WhatsApp reminder**, not just a plain list.

What was built:
- `core/models.py` - new `Family` model (`name`, `primary_mobile`, `secondary_mobile`, `address`,
  `notes`) placed just before `Student` so `Student.family` (new FK, `SET_NULL`, `related_name=
  "members"`) can reference it. Deliberately a separate concept from the existing
  `Student.guardian_name` free-text field (that's an admission-form field for a legal guardian
  when parents aren't available; `Family` is a pure office-side grouping of siblings for fee
  tracking). New `access_family` permission added to `ModuleAccess` - **needs a migration**.
- `core/access.py` / `core/user_admin.py` - `"family": "access_family"` added to
  `MODULE_PERMISSIONS` and `MODULES_UI` (normal assignable module, not admin-only). Added to the
  **Fee Desk** role preset by default (`fee` in `ROLE_PRESETS`) since combined family dues is
  fee-desk work - existing users with the Fee Desk role won't get it retroactively, only new/
  re-saved assignments will, same as every other permission change this session.
- `core/whatsapp.py` - new `family_due_message(family_name, members, total_due, school_name)`
  where `members` is a list of `(student_name, class_label, due_amount)` tuples; lists only the
  children who actually have a due balance, then a total line.
- `core/views.py` - `family_list` (search by name/mobile), `family_create`, `family_detail`
  (computes each member's due individually via `_student_due_total()`, sums for the family total,
  builds the combined WhatsApp link server-side since the message needs a list of tuples - not
  done via a template `simple_tag` like the per-student WhatsApp links), `family_add_student`,
  `family_remove_student`, `family_suggestions`, `family_create_from_suggestion`.
- **Matching logic** (`family_suggestions`): groups students with `family__isnull=True`,
  `is_active=True`, non-blank `father_name` AND non-blank `mobile_primary`, keyed by
  `(father_name.strip().lower(), mobile_primary.strip())` - only **exact** matches on both fields
  count as a suggestion (deliberately not fuzzy - legacy data has spelling variants, like the
  Category/Caste bug found earlier this session, so a loose match would risk grouping unrelated
  families). Groups of 2+ are shown with every student pre-checked as a table the admin can
  uncheck before saving - nothing is linked until the admin submits the form. This will likely
  miss real siblings whose father's name was typed slightly differently between the two
  admissions (common with legacy data) - those need manual linking via the search box on the
  Family Detail page instead.
- Templates (new): `family_list.html`, `family_form.html`, `family_detail.html` (member table
  with per-child due + individual WhatsApp "Remind" link + "Remove" button, a "Send Family
  WhatsApp Reminder" button when the family has a due total > 0, and an inline search-and-add box
  to link more children), `family_suggestions.html` (one review form per suggested sibling group).
- `templates/base.html` - "Family Ledger" nav link, gated by `access.family`.
- `templates/core/student_detail.html` - new quick-action button: shows the family name and links
  to the Family Detail page if linked, or "Add to Family" (goes to the Family list) if not.
- `core/admin.py` - `FamilyAdmin` registered.
- Tests: `FamilyLedgerTests` (6 tests) - create family + add student, remove student, combined due
  + WhatsApp link appears on the detail page, suggestions correctly group matching students and
  exclude non-matching ones, create-from-suggestion links the checked students, empty family list
  doesn't crash.

Not done / next session must:
1. **Run migrations** - `manage.py makemigrations core` then `migrate`. Adds the `Family` model,
   `Student.family` FK, and the `access_family` permission - nothing applied yet.
2. Run `manage.py test core` - expect the 6 new `FamilyLedgerTests` on top of the prior 54 (60
   total).
3. Manually verify in browser: open "Family Ledger" > "Suggested Families" and confirm it finds
   at least some real sibling groups in the live 1213-student data (exact father-name+mobile
   matches only, so don't be surprised if it finds fewer than the true number of sibling sets);
   create one family from a suggestion; open its detail page and confirm the combined due total
   and the "Send Family WhatsApp Reminder" button/message look right; try the manual search-and-
   add box to link an additional child; try removing a child and confirm they go back to
   "unlinked" (not deleted).
4. No fuzzy/typo-tolerant matching was built (see "Matching logic" above) - if the owner later
   finds too many real sibling sets are being missed by the suggestions page, a second pass using
   a similarity match on father_name (e.g. difflib) could be added, but that raises the false-
   positive risk and would need its own confirmation UI.
5. This is the last of the original 5 Grand Plan ideas (WhatsApp Alerts, ID Card Generator was
   built earlier, Inventory, Family Ledger, and Hindi UI is the only one still not started/wanted
   yet). `collectstatic` + `build-desktop.bat` still pending for this checkpoint specifically.

Ideas from the Grand Plan NOT yet started (still on the table for a future session):
1. **Hindi/Bilingual UI** - explicitly deferred by the owner this session ("filhal nahi chahiye").
   Large scope (every template, ~50+ files use `{% trans %}` / `django.utils.translation`, plus
   locale files). NOT the same problem as the TC's Devanagari-in-ReportLab issue (that was PDF-
   specific) - a web UI in Hindi is technically straightforward for Django (`USE_I18N`,
   `LocaleMiddleware`, `.po` files), just very high volume of translation work. Plan for multiple
   sessions if picked up.
2. **Paid WhatsApp Business API** (real automatic bulk send) - only worth revisiting if the free
   `wa.me` approach turns out to be too slow/manual in daily use; needs a business verification +
   ongoing cost decision from the owner first.
3. **Inventory stock-in / purchasing** - only if the owner wants supplier-side stock levels, not
   just distribution tracking (see the Inventory checkpoint's "Not done" item 4).
4. **Fuzzy sibling matching** - only if the exact-match Family suggestions above turn out to miss
   too many real sibling sets due to father-name spelling variants (see item 4 above).

Still outstanding from earlier in the project (not part of the Grand Plan, not touched this
session): Render free Postgres DB expiry decision (paid plan vs. monthly recreate, due ~Aug 1
2026), custom domain CNAME setup (`english-medium.thpsic.com`), rotating the exposed Render DB
credential.

## ✅ Feature Sprint & Bugfixes (July 9, 2026)

Following the implementation of the House System, Discipline Records, ID Cards, WhatsApp buttons, and Inventory modules, several crucial bug fixes and improvements were made during the final EXE rebuild phase:

1. **Section Dropdown Fixes & Seeding (`core/forms.py`)**:
   - The `SectionSelect` widget was causing `OperationalError` during fresh database migrations because its `__init__` method queried `Section.objects` before the table existed. This was fixed by deferring the query to `optgroups()` which runs at render time.
   - The JavaScript filter in `student_form.html` was incorrectly showing all sections (A, B, A, B...) when no class was selected. The condition was updated to `classId && opt.dataset.class === classId` to keep the dropdown empty until a class is selected.
   - The `create_option` method was failing silently to add `data-class` attributes because `value` was a `ModelChoiceIteratorValue` and `int(value)` raised a `TypeError`. This was fixed by casting to string first: `int(str(value))`.
   - The labels for the options were customized to show just the section name (e.g., "A", "B") instead of the `__str__` representation ("I - A").
   - A one-time seed script was run against both the development and local Desktop (`%LOCALAPPDATA%`) SQLite databases to add sections **C, D, E, F, G** to all classes, as the legacy database only had A and B for most classes.

2. **Photo Preview Implementation (`student_form.html`)**:
   - The photo upload functionality was augmented with client-side JavaScript using `FileReader` to instantly preview the selected image file before form submission. The "No Photo" SVG placeholder is now dynamically hidden, and an `<img>` tag is injected to display the chosen file immediately.

3. **Desktop EXE Rebuild Sequence**:
   - The `build-desktop.bat` script encountered `PermissionError: [WinError 5] Access is denied` because the legacy `SchoolSoft.exe` process was still running in the background and holding locks on DLLs.
   - The issue was resolved by explicitly killing the background processes before triggering the final build. The new EXE is now fully packed and verified to work locally.
