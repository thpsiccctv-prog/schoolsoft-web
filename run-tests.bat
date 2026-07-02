@echo off
cd /d "%~dp0"
set PYTHON_EXE=%cd%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" manage.py test > test-out.txt 2>&1
echo exitcode=%errorlevel% >> test-out.txt
