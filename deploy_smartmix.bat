
@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo       SMARTMIX LAB DEPLOYMENT
echo ========================================
echo.

echo [1/4] Running project tests...
call run_tests.bat
if errorlevel 1 (
    echo ERROR: Tests failed. Fix them before deploying.
    pause
    exit /b 1
)

echo.
echo [2/4] Checking Git repository...
git status --short
if errorlevel 1 (
    echo ERROR: Git check failed.
    pause
    exit /b 1
)

echo.
echo [3/4] Uploading committed code to GitHub...
git push origin main
if errorlevel 1 (
    echo ERROR: Git push failed.
    pause
    exit /b 1
)

echo.
echo [4/4] Opening Streamlit Community Cloud...
start "" "https://share.streamlit.io/"

echo.
echo SUCCESS: Tests passed and Git push completed.
echo If the app is already deployed, Streamlit will update it.
echo For first deployment, create the app in the browser.
pause
