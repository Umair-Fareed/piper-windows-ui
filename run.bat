@echo off
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python .\piper_ui.py


timeout 10 >nul
exit /B
