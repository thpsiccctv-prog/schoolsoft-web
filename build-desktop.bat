@echo off
REM ============================================================
REM  SchoolSoft desktop EXE build script
REM  Run from the project root: build-desktop.bat
REM  Output: dist\SchoolSoft\SchoolSoft.exe
REM ============================================================
setlocal
cd /d "%~dp0"

set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [1/4] Checking desktop requirements...
"%PYTHON_EXE%" -c "import django, webview, waitress, PyInstaller, whitenoise, reportlab, tzdata, dotenv"
if errorlevel 1 (
    echo Missing packages found; installing desktop requirements...
    "%PYTHON_EXE%" -m pip install -r requirements-desktop.txt --quiet
    if errorlevel 1 goto :fail
) else (
    echo Desktop requirements already installed.
)

echo [2/4] Collecting static files (WhiteNoise serves these in the EXE)...
"%PYTHON_EXE%" manage.py collectstatic --noinput --clear
if errorlevel 1 goto :fail

echo [3/4] Creating clean seed database (db.seed.sqlite3)...
if exist db.seed.sqlite3 del db.seed.sqlite3
set SCHOOLSOFT_SQLITE_PATH=%cd%\db.seed.sqlite3
"%PYTHON_EXE%" manage.py migrate --noinput
if errorlevel 1 goto :fail
REM Default admin user for first login - CHANGE THE PASSWORD after install!
set DJANGO_SUPERUSER_PASSWORD=admin12345
"%PYTHON_EXE%" manage.py createsuperuser --noinput --username admin --email admin@example.com
set DJANGO_SUPERUSER_PASSWORD=
set SCHOOLSOFT_SQLITE_PATH=

echo [4/4] Building EXE with PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --noconfirm SchoolSoft.spec
if errorlevel 1 goto :fail

REM Workaround for PyInstaller with Python 3.14+ failing to bundle the base Python DLL
"%PYTHON_EXE%" -c "import sys, os, shutil; dll=f'python{sys.version_info.major}{sys.version_info.minor}.dll'; src=os.path.join(sys.base_prefix, dll); dst=os.path.join('dist', 'SchoolSoft', '_internal', dll); shutil.copy(src, dst) if os.path.exists(src) and not os.path.exists(dst) else None"

echo.
echo BUILD OK: dist\SchoolSoft\SchoolSoft.exe
echo User data lives in %%LOCALAPPDATA%%\SchoolSoft\ (never overwritten by rebuilds).
echo First login: admin / admin12345  (change it in /admin/ immediately)
exit /b 0

:fail
echo.
echo BUILD FAILED - see messages above.
exit /b 1
