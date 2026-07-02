@echo off
cd /d "%~dp0"
echo === safe.directory fix === > git-out.txt
git config --global --add safe.directory "D:/english medium/schoolsoft_web" >> git-out.txt 2>&1
echo === git config === >> git-out.txt
git config user.name "Jitendra" >> git-out.txt 2>&1
git config user.email "thpsicdudahi@gmail.com" >> git-out.txt 2>&1
echo === staging files === >> git-out.txt
git add -A >> git-out.txt 2>&1
echo === sensitive check (khali hona chahiye) === >> git-out.txt
git status --short | findstr /i "sqlite .env debug-scripts .venv dist build" >> git-out.txt
echo === staged file count === >> git-out.txt
git diff --cached --name-only | find /c /v "" >> git-out.txt
echo === commit === >> git-out.txt
git commit -m "SchoolSoft web + desktop: initial commit" >> git-out.txt 2>&1
echo === log === >> git-out.txt
git log --oneline >> git-out.txt 2>&1
echo === done === >> git-out.txt
