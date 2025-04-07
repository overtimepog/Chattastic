@echo off
title CHATTASTIC WEB UI CONSOLE, DONT CLOSE
echo Checking for Chattastic...

:: Check for Python installation
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. installing Python...
    :: run python installer
    python-3.11.0-amd64.exe /passive PrependPath=1
)

:: Install dependencies
echo Installing dependencies...
python -m pip install -r requirements.txt

:: Run the application using Uvicorn
echo Starting Chattastic Web UI with FastAPI...
echo Access the web interface at http://localhost:8000
python run.py

echo Chattastic Web UI has stopped.
pause
