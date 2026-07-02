@echo off
cd /d "%~dp0"
echo === commit + push === > push-out.txt
git rm --cached External >> push-out.txt 2>&1
git add -A >> push-out.txt 2>&1
git commit -m "Week 1 ops polish: today KPIs, ops header, shortcuts, status bar, school logo" >> push-out.txt 2>&1
git push origin main >> push-out.txt 2>&1
echo exitcode=%errorlevel% >> push-out.txt
