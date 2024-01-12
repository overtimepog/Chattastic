@echo off
echo Checking for Chattastic...

:: Check for Python installation
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. installing Python...
    :: run python installer
    python-3.11.0-amd64.exe /passive PrependPath=1
)

:: Check if main.py exists
if exist main.py (
    echo main.py found. Chattastic is already cloned.
    goto InstallDependencies
) else (
    echo main.py not found. Cloning Chattastic repository...
    git clone https://github.com/overtimepog/Chattastic.git
)

:InstallDependencies
:: Navigate to the Chattastic directory
cd Chattastic

:: Install dependencies
echo Installing dependencies...
python -m pip install dearpygui pyaudio gtts playsound@git+https://github.com/taconi/playsound requests sounddevice flask numpy

:: Run the application
echo Starting Chattastic...
python main.py

echo Chattastic installation and launch script has completed.
pause
