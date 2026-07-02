@echo off
cd /d "%~dp0"
set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo Render ka External Database URL paste kijiye (right-click = paste):
set /p DATABASE_URL=URL:
"%PYTHON_EXE%" count_rows.py
pause
