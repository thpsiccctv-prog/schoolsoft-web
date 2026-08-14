@echo off
REM Fast data transfer: local SQLite -> Render PostgreSQL (batched, ~2-3 min)
setlocal
cd /d "%~dp0"
set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [1/3] Local database se fresh export (bina natural keys ke)...
set SCHOOLSOFT_SQLITE_PATH=%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3
if not exist "%SCHOOLSOFT_SQLITE_PATH%" set SCHOOLSOFT_SQLITE_PATH=%cd%\db.sqlite3
echo     (source: %SCHOOLSOFT_SQLITE_PATH%)
"%PYTHON_EXE%" manage.py dumpdata -e contenttypes -e auth.permission -e sessions -e admin.logentry -o data.json
if errorlevel 1 goto :fail
set SCHOOLSOFT_SQLITE_PATH=

echo.
echo [2/3] Render ka External Database URL paste kijiye (right-click = paste):
set /p DATABASE_URL=URL:
if "%DATABASE_URL%"=="" goto :fail

echo.
echo [3/3] Fast batch load...
"%PYTHON_EXE%" fast_load.py
if errorlevel 1 goto :fail
pause
exit /b 0

:fail
echo.
echo KOI DIKKAT AAYI - upar ka message Claude ko bhej dijiye.
pause
exit /b 1
