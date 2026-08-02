@echo off
title BhavAI Installer
color 0A
setlocal EnableDelayedExpansion

echo ==========================================
echo         BhavAI One-Click Installer
echo ==========================================
echo.

:: ---------------------------------------
:: Check Administrator
:: ---------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Not running as Administrator.
    echo Some features may fail.
    echo.
)

:: ---------------------------------------
:: Check Internet
:: ---------------------------------------
echo Checking Internet...

ping google.com -n 1 >nul

if errorlevel 1 (
    echo No Internet Connection.
    pause
    exit /b
)

:: ---------------------------------------
:: Check Python
:: ---------------------------------------
python --version >nul 2>&1

if %errorlevel%==0 (
    echo Python Found.
    goto INSTALL
)

echo.
echo Python not found.
echo Downloading Python...

powershell -Command ^
"Invoke-WebRequest https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe -OutFile python-installer.exe"

if not exist python-installer.exe (
    echo Failed to download Python.
    pause
    exit /b
)

echo Installing Python...

python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1

echo Waiting for installation...

timeout /t 20 >nul

:: Refresh PATH
set PATH=%PATH%;C:\Program Files\Python312\;C:\Program Files\Python312\Scripts\

:: ---------------------------------------
:: Verify Python
:: ---------------------------------------
python --version >nul 2>&1

if errorlevel 1 (
    echo Python installation failed.
    pause
    exit /b
)

:INSTALL

echo.
echo Installing BhavAI...

python -m pip install --upgrade pip

python -m pip install wheel setuptools

python -m pip install -e .

if errorlevel 1 (
    echo.
    echo Installation Failed.
    pause
    exit /b
)

echo.
echo ==========================================
echo      BhavAI Installed Successfully!
echo ==========================================
echo.

echo Launch using:
echo.
echo     bhav wake up
echo.

pause