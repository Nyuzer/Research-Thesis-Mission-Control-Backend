@echo off
echo 🚀 Mission Control Backend - Windows Network Mode
echo ================================================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip is not installed
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📚 Installing dependencies...
pip install -r requirements.txt

REM Create maps directory
if not exist "maps" mkdir maps

REM Get local IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4 Address"') do (
    set IP=%%a
    goto :found_ip
)
:found_ip
set IP=%IP: =%

echo 🌐 Your laptop's IP address: %IP%
echo 🎯 Starting Mission Control Backend on network...
echo URL: http://%IP%:8000
echo API Documentation: http://%IP%:8000/docs
echo.
echo ⚠️  Make sure your firewall allows connections on port 8000
echo.

REM Start the backend on all interfaces
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause 