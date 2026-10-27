@echo off
setlocal
title OffGridUSB (offgridusb.com) // Safe USB Formatter (exFAT/FAT32) ^& Setup Wizard

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\format_and_setup_usb.ps1" %*
if %errorlevel% neq 0 (
    echo.
    echo [WARN] USB Formatter / Setup Wizard exited with code %errorlevel%.
    pause
    exit /b %errorlevel%
)
exit /b 0
