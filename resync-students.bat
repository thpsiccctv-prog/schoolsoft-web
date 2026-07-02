@echo off
REM ============================================================
REM  Fresh ADDMISSION.csv se students dobara import karta hai
REM  (TC_ISSUE wale inactive marked honge) - EXE ke live db par.
REM  Pehle: Access me ADDMISSION table ko export karke
REM  D:\english medium\migration_audit\exports\ADDMISSION.csv
REM  ko REPLACE kar dijiye.
REM ============================================================
setlocal
cd /d "%~dp0"
set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

set SCHOOLSOFT_SQLITE_PATH=%LOCALAPPDATA%\SchoolSoft\db.sqlite3
if not exist "%SCHOOLSOFT_SQLITE_PATH%" set SCHOOLSOFT_SQLITE_PATH=%cd%\db.sqlite3
echo Target database: %SCHOOLSOFT_SQLITE_PATH%

echo [1/3] Database ka backup...
copy /y "%SCHOOLSOFT_SQLITE_PATH%" "%SCHOOLSOFT_SQLITE_PATH%.before-resync" > nul

echo [2/3] Students import (TC_ISSUE = blocked mapping ke saath)...
"%PYTHON_EXE%" manage.py import_legacy_students
if errorlevel 1 goto :fail

echo [3/3] Active/inactive ginti:
"%PYTHON_EXE%" active_count.py
if errorlevel 1 goto :fail

echo.
echo HO GAYA! Agar ACTIVE ~364 dikha to bilkul sahi hai.
echo (Project db ke liye bhi chalana ho to is file ko dobara chalaiye
echo  jab LOCALAPPDATA wala db na mile - ya Claude ko boliye.)
pause
exit /b 0

:fail
echo.
echo KOI DIKKAT AAYI - upar ka message Claude ko bhejiye.
pause
exit /b 1
