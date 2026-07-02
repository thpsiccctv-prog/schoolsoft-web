@echo off
REM ============================================================
REM  Local SQLite data ko Render PostgreSQL me bhejta hai.
REM  Chalane se pehle Render me: schoolsoft-db -> Connect ->
REM  "External Database URL" copy kar lijiye.
REM ============================================================
setlocal
cd /d "%~dp0"

set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [1/3] Local database se data export ho raha hai...
set SCHOOLSOFT_SQLITE_PATH=%LOCALAPPDATA%\SchoolSoft\db.sqlite3
if not exist "%SCHOOLSOFT_SQLITE_PATH%" set SCHOOLSOFT_SQLITE_PATH=%cd%\db.sqlite3
echo     (source: %SCHOOLSOFT_SQLITE_PATH%)
"%PYTHON_EXE%" manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -e admin.logentry -o data.json
if errorlevel 1 goto :fail
set SCHOOLSOFT_SQLITE_PATH=

echo.
echo [2/3] Ab Render ka "External Database URL" paste kijiye
echo     (Render dashboard -> schoolsoft-db -> Connect -> External Database URL)
set /p DATABASE_URL=URL yahan paste karke Enter dabaiye:
if "%DATABASE_URL%"=="" goto :fail

echo.
echo [3/3] PostgreSQL driver check + data load ho raha hai (2-5 minute)...
"%PYTHON_EXE%" -c "import psycopg2" 2>nul || "%PYTHON_EXE%" -m pip install psycopg2-binary --quiet
if errorlevel 1 goto :fail
"%PYTHON_EXE%" manage.py migrate --noinput
if errorlevel 1 goto :fail
"%PYTHON_EXE%" manage.py loaddata data.json
if errorlevel 1 goto :fail

echo.
echo SAB HO GAYA! Ab website refresh karke dekhiye - students/receipts dikhne chahiye.
echo (data.json file ab delete kar sakte hain)
pause
exit /b 0

:fail
echo.
echo KOI DIKKAT AAYI - upar ka message dekhiye ya Claude ko screenshot bhejiye.
pause
exit /b 1
