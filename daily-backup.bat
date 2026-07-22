@echo off
REM ============================================================
REM SchoolSoft Daily Backup
REM
REM Source:
REM   %LOCALAPPDATA%\SchoolSoft\db.sqlite3
REM
REM Destination:
REM   E:\SchoolSoft-Daily-Backups\YYYYMMDD-HHMMSS\
REM
REM Run this after daily work is complete.
REM Keep SchoolSoft EXE closed while taking backup.
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"
title SchoolSoft Daily Backup

set "SOURCE_DIR=%LOCALAPPDATA%\SchoolSoft"
set "SOURCE_DB=%SOURCE_DIR%\db.sqlite3"
set "BACKUP_ROOT=E:\SchoolSoft-Daily-Backups"

echo ============================================================
echo SchoolSoft Daily Backup
echo ============================================================
echo.
echo Source DB:
echo   %SOURCE_DB%
echo.
echo Backup root:
echo   %BACKUP_ROOT%
echo.

if not exist "%SOURCE_DB%" (
    echo ERROR: Desktop database nahi mila.
    echo SchoolSoft EXE ek baar chala kar band kijiye, phir backup dobara chalaiye.
    echo.
    pause
    exit /b 1
)

tasklist /FI "IMAGENAME eq SchoolSoft.exe" 2>nul | find /I "SchoolSoft.exe" >nul
if not errorlevel 1 (
    echo WARNING: SchoolSoft.exe abhi running lag raha hai.
    echo Best practice: EXE band karke backup lena chahiye.
    echo.
    choice /C YN /M "Kya phir bhi backup continue karna hai"
    if errorlevel 2 (
        echo Backup cancel kar diya gaya.
        pause
        exit /b 1
    )
)

if not exist "%BACKUP_ROOT%" (
    mkdir "%BACKUP_ROOT%"
    if errorlevel 1 (
        echo ERROR: Backup root folder create nahi hua:
        echo   %BACKUP_ROOT%
        pause
        exit /b 1
    )
)

for /f %%A in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%A"
set "BACKUP_DIR=%BACKUP_ROOT%\%STAMP%"

mkdir "%BACKUP_DIR%"
if errorlevel 1 (
    echo ERROR: Backup folder create nahi hua:
    echo   %BACKUP_DIR%
    pause
    exit /b 1
)

echo [1/3] Database copy ho raha hai...
copy "%SOURCE_DB%" "%BACKUP_DIR%\db.sqlite3" >nul
if errorlevel 1 (
    echo ERROR: Database copy fail hua.
    pause
    exit /b 1
)

echo [2/3] Media folder copy ho raha hai, agar available hai...
if exist "%SOURCE_DIR%\media" (
    robocopy "%SOURCE_DIR%\media" "%BACKUP_DIR%\media" /E /R:2 /W:2 >nul
    if errorlevel 8 (
        echo ERROR: Media folder copy fail hua.
        pause
        exit /b 1
    )
) else (
    echo     Media folder nahi mila, skip.
)

echo [3/3] Restore note ban raha hai...
>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo SchoolSoft daily backup
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo Created: %DATE% %TIME%
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo Source DB: %SOURCE_DB%
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo.
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo Restore rule:
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo Before replacing any live db.sqlite3, first make a dated backup of the current live folder.
>>"%BACKUP_DIR%\RESTORE-NOTE.txt" echo Live folder: %SOURCE_DIR%

echo.
echo BACKUP COMPLETE.
echo Folder:
echo   %BACKUP_DIR%
echo.
echo Is folder ko external drive/cloud me copy kar sakte hain.
pause
exit /b 0
