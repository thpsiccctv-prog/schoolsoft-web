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
Commits this session (in order): `925200d` (styles.css clean baseline restore) → `ac1f36b`
(users & permissions backend + read-only write-block) → `eb93c7e` (sidebar menu links +
users-page styling + footer stack) → `1d15f53` (sidebar nav scroll + service-worker
network-first). Latest = **`1d15f53`**.

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
