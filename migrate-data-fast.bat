@echo off
REM ============================================================
REM  Faster Render PostgreSQL loader for SchoolSoft data.json.
REM  Use this if Django loaddata is too slow over the internet.
REM ============================================================
setlocal
cd /d "%~dp0"

set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

if not exist data.json (
    echo data.json nahi mila. Pehle migrate-data.bat ka export step chalaiye.
    goto :fail
)

echo Render ka "External Database URL" paste kijiye.
echo URL screen/chat me share mat kijiye; sirf yahan paste karke Enter dabaiye.
set /p DATABASE_URL=URL:
if "%DATABASE_URL%"=="" goto :fail

echo.
echo PostgreSQL driver check ho raha hai...
"%PYTHON_EXE%" -c "import psycopg2" 2>nul || "%PYTHON_EXE%" -m pip install psycopg2-binary --quiet
if errorlevel 1 goto :fail

echo.
echo Fast bulk load start ho raha hai...
"%PYTHON_EXE%" fast_load_data.py data.json
if errorlevel 1 goto :fail

echo.
echo FAST LOAD OK. Website refresh karke counts check kijiye.
pause
exit /b 0

:fail
echo.
echo FAST LOAD FAILED - upar ka message dekhiye.
pause
exit /b 1
