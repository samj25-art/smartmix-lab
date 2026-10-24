@echo off
REM One-time setup for Windows (needs Python 3.10+ installed with "Add Python to PATH" ticked)
py -m venv venv
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Setup finished. Now double-click run_app.bat
pause
