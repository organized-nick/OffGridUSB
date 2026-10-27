@echo off
setlocal
set "ENGINE=%~dp0provision_usb.ps1"
if not exist "%ENGINE%" set "ENGINE=%~dp0..\provision_usb.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ENGINE%" -Product Product1 %*
exit /b %ERRORLEVEL%
