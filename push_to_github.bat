@echo off
cd /d "D:\Projects\Projects\Expenses"

echo Setting git identity...
git config --global user.email "benariel@gmail.com"
git config --global user.name "DRbenariel"

echo Cleaning up old git state...
if exist ".git" rmdir /s /q .git

echo Initializing fresh repo...
git init
git branch -M main

echo Adding files...
git add app.py processor.py downloader.py sheets_handler.py setup_credentials.py requirements.txt CLAUDE.md .gitignore

echo Committing...
git commit -m "Initial commit: expenses dashboard"

echo Adding remote...
git remote add origin https://github.com/DRbenariel/Expenses.git

echo Pushing to GitHub...
git push -u origin main

echo.
echo Done!
pause
