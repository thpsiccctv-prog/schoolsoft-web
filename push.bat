@echo off
cd /d "%~dp0"
echo === commit + push === > push-out.txt
git add -A >> push-out.txt 2>&1
git commit -m "Mobile polish: receipts list + collection report as touch cards, compact filters" >> push-out.txt 2>&1
git push origin main >> push-out.txt 2>&1
echo exitcode=%errorlevel% >> push-out.txt
