@echo off
setlocal
title OffGridUSB (offgridusb.com) // Multi-USB Flash Drive Mass Cloner

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\clone_to_usb.ps1" %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] USB Cloner encountered an error.
    pause
    exit /b %errorlevel%
)
exit /b 0
