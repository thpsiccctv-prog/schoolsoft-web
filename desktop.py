r"""THPSIC SchoolSoft desktop launcher (PyInstaller + waitress + pywebview).

Data layout:
  %LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3
  %LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.backup-*.sqlite3
  %LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\THPSIC-SchoolSoft-error.log
  %LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\media\
The EXE bundle only ships a clean seed database (db.seed.sqlite3); user data
is never inside the install folder, so updates can never overwrite it.
"""

import logging
import os
import shutil
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

APP_TITLE = "THPSIC SchoolSoft"
APP_DATA_DIR_NAME = "THPSIC-InterCollege-SchoolSoft"
DEFAULT_BACKUP_ROOT = r"E:\THPSIC-INTER-COLLEGE\04-backups\daily-db"
SINGLE_INSTANCE_PORT = 47491  # separate from THPS English Medium SchoolSoft
_lock_socket = None  # must stay referenced for the lifetime of the process


def data_dir() -> Path:
    """Writable per-user folder (works even if the EXE sits in Program Files)."""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_DATA_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


APP_DATA = data_dir()
DB_PATH = APP_DATA / "db.sqlite3"
LOG_FILE = APP_DATA / "THPSIC-SchoolSoft-error.log"
SERVER_ERROR = None


def configure_desktop_environment():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
    os.environ["SCHOOLSOFT_SQLITE_PATH"] = str(DB_PATH)
    os.environ["SCHOOLSOFT_LOG_FILE"] = str(LOG_FILE)
    os.environ["SCHOOLSOFT_APP_TITLE"] = APP_TITLE
    os.environ["SCHOOLSOFT_APP_DATA_DIR_NAME"] = APP_DATA_DIR_NAME
    os.environ.setdefault("SCHOOLSOFT_BACKUP_ROOT", DEFAULT_BACKUP_ROOT)
    os.environ.setdefault("SCHOOLSOFT_ONLINE_SYNC_ENABLED", "0")
    # Student photos and other uploads: same reasoning as the sqlite db above -
    # must live under the per-school LOCALAPPDATA folder, never beside the EXE.
    media_dir = APP_DATA / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SCHOOLSOFT_MEDIA_ROOT"] = str(media_dir)

    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if DB_PATH.exists():
        return

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bundle_dir = Path(getattr(sys, "_MEIPASS", exe_dir))
        # Older builds kept the live db beside the EXE - adopt it, don't lose it.
        legacy_db = exe_dir / "db.sqlite3"
        seed_db = bundle_dir / "db.seed.sqlite3"
        if legacy_db.exists():
            shutil.copy2(legacy_db, DB_PATH)
        elif seed_db.exists():
            shutil.copy2(seed_db, DB_PATH)
    # Non-frozen (development) runs: migrate below creates the db if missing.


def single_instance_or_exit():
    """Show a message and exit if this app is already running for this user."""
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
    except OSError:
        # Don't die silently - tell the user what is going on.
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                f"{APP_TITLE} is already running (perhaps in the background).\n\n"
                f"Close the other {APP_TITLE} window, or end the EXE "
                "process in Task Manager, and try again.",
                APP_TITLE,
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        os._exit(0)


def migrate_with_backup():
    """Apply migrations on every start; back the db up first."""
    import django

    django.setup()

    if DB_PATH.exists():
        backup = APP_DATA / f"db.backup-{time.strftime('%Y%m%d')}.sqlite3"
        if not backup.exists():
            shutil.copy2(DB_PATH, backup)
        _prune_backups(keep=7)

    from django.core.management import call_command

    call_command("migrate", "--noinput", verbosity=0)

    # WAL journal survives abrupt shutdown (window close kills the daemon
    # server thread) far better than the default rollback journal.
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")


def _prune_backups(keep):
    backups = sorted(APP_DATA.glob("db.backup-*.sqlite3"))
    for old in backups[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port):
    global SERVER_ERROR
    try:
        from waitress import serve

        from schoolsoft.wsgi import application

        serve(application, host="127.0.0.1", port=port, threads=6, _quiet=True)
    except Exception:
        SERVER_ERROR = traceback.format_exc()
        logging.error("Waitress server failed to start:\n%s", SERVER_ERROR)


def wait_for_server(port, timeout_seconds=30):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if SERVER_ERROR:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    import webview

    configure_desktop_environment()
    single_instance_or_exit()
    migrate_with_backup()

    port = get_free_port()
    threading.Thread(target=start_server, args=(port,), daemon=True).start()

    window_kwargs = dict(width=1200, height=800, min_size=(1024, 768))

    server_ok = wait_for_server(port)
    logging.warning("%s launch: port=%s server_ok=%s", APP_TITLE, port, server_ok)

    if server_ok:
        # Allow PDF receipt/report downloads (blocked by pywebview default).
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window(
            APP_TITLE,
            f"http://127.0.0.1:{port}/",
            zoomable=True,       # Ctrl+scroll zoom for readability
            text_select=True,    # allow copying receipt numbers etc.
            **window_kwargs,
        )
    else:
        message = (
            f"<h2>{APP_TITLE} server could not start</h2>"
            f"<p>Please send this file for checking:<br>{LOG_FILE}</p>"
        )
        webview.create_window(APP_TITLE, html=message, **window_kwargs)

    def _force_foreground():
        # The window can open BEHIND other maximized windows without focus
        # (observed on Windows 11). Nudge it to the front once it exists.
        try:
            import ctypes

            user32 = ctypes.windll.user32
            for _ in range(20):
                handle = user32.FindWindowW(None, APP_TITLE)
                if handle:
                    user32.ShowWindow(handle, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(handle)
                    break
                time.sleep(0.5)
        except Exception:
            pass

    try:
        # Let pywebview pick the best Windows backend itself (it prefers
        # WebView2/Edge when the runtime is installed). Forcing
        # gui="edgechromium" was observed to hang with no window on some
        # machines, so we do not force it.
        webview.start(_force_foreground)
        logging.warning("%s window closed normally", APP_TITLE)
    except Exception:
        logging.exception("webview failed to start")
        raise
    finally:
        # webview.start() has returned: the window is closed. Force the
        # process to end even if WebView2/waitress threads are hanging -
        # otherwise a zombie EXE keeps holding the single-instance
        # lock and every future launch dies silently.
        logging.shutdown()
        os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Last-resort trace for failures before logging was configured.
        try:
            LOG_FILE.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        raise
