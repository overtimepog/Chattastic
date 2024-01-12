@echo off
echo Checking for Chattastic installation...

:: Check for Python installation
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python 3.x first.
    exit /b
)

:: Check if Chattastic directory exists
if exist Chattastic (
    echo Chattastic directory already exists. Skipping cloning.
    goto InstallDependencies
) else (
    echo Cloning Chattastic repository...
    git clone https://github.com/overtimepog/Chattastic.git
)

:InstallDependencies
:: Navigate to the Chattastic directory
cd Chattastic

:: Install dependencies
echo Installing dependencies...
python -m pip install dearpygui pyaudio gtts playsound@git+https://github.com/taconi/playsound requests sounddevice flask

:: Run the application
echo Starting Chattastic...
python main.py

echo Chattastic installation and launch script has completed.
pause
