@echo off
setlocal EnableDelayedExpansion

title OffGridUSB Factory Provisioning Suite (Host Only)
cls

echo ================================================================================
echo   OFFGRIDUSB -- FACTORY PROVISIONING SUITE (HOST ONLY)
echo   Universal Air-Gapped Offline Survival, Knowledge ^& Local AI USB Drives
echo ================================================================================
echo.
echo   [1] Provision Product 1: PocketSurvival  (Tier 0,    8 GB USB,  ^<= 6.5 GB payload)
echo   [2] Provision Product 2: FieldReady      (Tiers 0-1, 32 GB USB,  ~16-20 GB / 4.7 GB lean)
echo   [3] Provision Product 3: CivilizationArk (Tiers 0-2, 128 GB USB, ~65-72 GB payload)
echo   ----------------------------------------------------------------------------
echo   [4] Custom Technical Tier Provisioning (Tier 0, 1, 2, 3, or 4)
echo   [5] View Product Catalog ^& Hardware Specifications (-Info)
echo   [6] Run Simulation / Safety Check (-DryRun)
echo   [Q] Quit
echo.
echo ================================================================================

set /p "CHOICE=Select an option [1-6, Q]: "

if /i "%CHOICE%"=="Q" goto :EOF
if "%CHOICE%"=="5" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0provision_usb.ps1" -Info
    echo.
    pause
    goto :EOF
)

if "%CHOICE%"=="6" (
    set /p "DRIVE_LETTER=Enter Target USB Drive Letter to simulate (e.g. D): "
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0provision_usb.ps1" -Product Product2 -Drive !DRIVE_LETTER! -DryRun
    echo.
    pause
    goto :EOF
)

set "SELECTED_PRODUCT="
if "%CHOICE%"=="1" set "SELECTED_PRODUCT=Product1"
if "%CHOICE%"=="2" set "SELECTED_PRODUCT=Product2"
if "%CHOICE%"=="3" set "SELECTED_PRODUCT=Product3"
if "%CHOICE%"=="4" (
    set /p "TIER_NUM=Enter Technical Tier Number [0, 1, 2, 3, 4]: "
    if "!TIER_NUM!"=="0" set "SELECTED_PRODUCT=Product1"
    if "!TIER_NUM!"=="1" set "SELECTED_PRODUCT=Product2"
    if "!TIER_NUM!"=="2" set "SELECTED_PRODUCT=Product3"
    if "!TIER_NUM!"=="3" set "SELECTED_PRODUCT=Tier3"
    if "!TIER_NUM!"=="4" set "SELECTED_PRODUCT=Tier4"
)

if "%SELECTED_PRODUCT%"=="" (
    echo Invalid choice.
    pause
    goto :EOF
)

echo.
set /p "TARGET_DRIVE=Enter Target USB Drive Letter (e.g. D or E): "
if "%TARGET_DRIVE%"=="" (
    echo Drive letter cannot be empty.
    pause
    goto :EOF
)

echo.
echo ================================================================================
echo   Launching Provisioning Engine for %SELECTED_PRODUCT% on Drive %TARGET_DRIVE%:
echo ================================================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0provision_usb.ps1" -Product %SELECTED_PRODUCT% -Drive %TARGET_DRIVE%

set "PROVISION_STATUS=%ERRORLEVEL%"
echo.
if %PROVISION_STATUS% EQU 0 (
    echo Provisioning completed successfully!
) else (
    echo Provisioning exited with code %PROVISION_STATUS%.
)

echo.
pause
exit /b %PROVISION_STATUS%
