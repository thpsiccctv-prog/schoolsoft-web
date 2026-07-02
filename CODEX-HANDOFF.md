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

## Rules for any future work

- Never bundle or commit real databases. Seed db only.
- User data dir `%LOCALAPPDATA%\SchoolSoft\` is sacred — nothing in the repo/build may overwrite it.
- Desktop EXE is the primary system; online is read/report convenience.
- Test with `manage.py test` (21 tests) before any EXE rebuild; rebuild via `build-desktop.bat` only.
