@echo off
setlocal
title OffGridUSB (offgridusb.com) // Internet-in-a-Box ^& AI Model Downloader

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\download_internet_in_a_box.ps1" %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Asset downloader exited with code %errorlevel%.
    pause
    exit /b %errorlevel%
)
echo.
pause
exit /b 0
