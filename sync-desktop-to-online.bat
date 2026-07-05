@echo off
REM ============================================================
REM SchoolSoft: Desktop EXE database -> Online Render sync
REM
REM Source of truth:
REM   %LOCALAPPDATA%\SchoolSoft\db.sqlite3
REM
REM Destination:
REM   Render PostgreSQL from render-db-url.txt
REM
REM WARNING:
REM   This replaces the online database with the desktop database
REM   export. Use only after daily desktop work is complete and
REM   after taking a backup.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title SchoolSoft Desktop to Online Sync

if not exist "sync-backups" mkdir "sync-backups"
set "SYNC_LOG=sync-backups\sync-last.log"
>"%SYNC_LOG%" echo SchoolSoft sync started at %DATE% %TIME%

set "PYTHON_EXE=%cd%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "SOURCE_DB=%LOCALAPPDATA%\SchoolSoft\db.sqlite3"
if not exist "%SOURCE_DB%" (
    echo.
    echo ERROR: Desktop database nahi mila:
    echo   %SOURCE_DB%
    echo.
    echo SchoolSoft EXE ek baar chala kar band kijiye, phir sync dobara chalaiye.
    goto :fail
)

echo ============================================================
echo SchoolSoft Desktop to Online Sync
echo ============================================================
echo.
echo Source Desktop DB:
echo   %SOURCE_DB%
echo.
echo WARNING:
echo   Online Render database ko Desktop DB ki fresh copy se replace kiya jayega.
echo   Daily entry hamesha Desktop EXE me honi chahiye.
echo   Sync ke dauran SchoolSoft EXE band rakhiye.
echo.
choice /C YN /M "Kya aap online database ko Desktop data se update karna chahte hain"
if errorlevel 2 goto :cancel

if not exist "render-db-url.txt" (
    echo.
    echo Render ka External Database URL paste kijiye.
    echo URL render-db-url.txt me local machine par save hoga.
    echo Ye file .gitignore me hai, GitHub par upload nahi hogi.
    set /p "DATABASE_URL=URL: "
    for /f "tokens=* delims= " %%A in ("%DATABASE_URL%") do set "DATABASE_URL=%%A"
    if "%DATABASE_URL%"=="" goto :fail
    >"render-db-url.txt" echo %DATABASE_URL%
) else (
    for /f "usebackq delims=" %%A in ("render-db-url.txt") do set "DATABASE_URL=%%A"
    for /f "tokens=* delims= " %%A in ("%DATABASE_URL%") do set "DATABASE_URL=%%A"
)

if "%DATABASE_URL%"=="" (
    echo ERROR: DATABASE_URL blank hai.
    >>"%SYNC_LOG%" echo ERROR: DATABASE_URL blank hai.
    goto :fail
)
echo "%DATABASE_URL%" | findstr /B /I /C:"postgresql://" /C:"postgres://" >nul
if errorlevel 1 (
    echo ERROR: URL postgresql:// ya postgres:// se start nahi ho raha.
    echo render-db-url.txt delete karke sahi External Database URL paste kijiye.
    >>"%SYNC_LOG%" echo ERROR: invalid database URL prefix.
    goto :fail
)
set "RENDER_DATABASE_URL=%DATABASE_URL%"

echo.
echo [1/5] Desktop DB backup ban raha hai...
set "BACKUP_FILE=sync-backups\db.before_online_sync_%DATE:/=-%_%TIME::=-%.sqlite3"
set "BACKUP_FILE=%BACKUP_FILE: =0%"
copy "%SOURCE_DB%" "%BACKUP_FILE%" >nul
if errorlevel 1 (
    >>"%SYNC_LOG%" echo ERROR: Desktop DB backup failed.
    goto :fail
)
echo     Backup: %BACKUP_FILE%
>>"%SYNC_LOG%" echo Backup: %BACKUP_FILE%

echo.
echo [2/5] Desktop DB se fresh export ho raha hai...
set "DATABASE_URL="
set "SCHOOLSOFT_SQLITE_PATH=%SOURCE_DB%"
"%PYTHON_EXE%" manage.py dumpdata -e contenttypes -e auth.permission -e sessions -e admin.logentry -e core.moduleaccess -o data.json >>"%SYNC_LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: Desktop DB export fail hua. Details: %SYNC_LOG%
    goto :fail
)
set "SCHOOLSOFT_SQLITE_PATH="

echo.
echo [3/5] PostgreSQL driver check ho raha hai...
"%PYTHON_EXE%" -c "import psycopg2" >>"%SYNC_LOG%" 2>&1 || "%PYTHON_EXE%" -m pip install psycopg2-binary --quiet >>"%SYNC_LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: PostgreSQL driver install/check fail hua. Details: %SYNC_LOG%
    goto :fail
)

echo.
echo [4/5] Online Render DB me fast batch load ho raha hai...
set "DATABASE_URL=%RENDER_DATABASE_URL%"
"%PYTHON_EXE%" fast_load_data.py data.json >>"%SYNC_LOG%" 2>&1
if errorlevel 1 (
    echo ERROR: Online DB load fail hua. Details: %SYNC_LOG%
    goto :fail
)

echo.
echo [5/5] Sync complete.
>>"%SYNC_LOG%" echo Sync complete at %DATE% %TIME%
echo Online website refresh karke dashboard verify kijiye:
echo   https://schoolsoft-english-medium.onrender.com
echo.
echo Expected: Online dashboard Desktop dashboard se match kare.
pause
exit /b 0

:cancel
echo.
echo Sync cancel kar diya gaya.
pause
exit /b 0

:fail
echo.
echo SYNC FAILED - upar ka error message dekhiye.
echo Log file:
echo   %cd%\%SYNC_LOG%
echo Agar online data half-sync lage to backup aur log ke saath developer/Codex ko batayein.
pause
exit /b 1
