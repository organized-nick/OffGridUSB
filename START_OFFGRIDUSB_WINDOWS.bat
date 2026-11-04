@echo off
setlocal EnableDelayedExpansion
title OffGridUSB (offgridusb.com) // Universal Offline Knowledge ^& Adaptive AI Harness

set "SCRIPT_DIR=%~dp0"
set "DIR_ARG=%SCRIPT_DIR%"
if "%DIR_ARG:~-1%"=="\" set "DIR_ARG=%DIR_ARG:~0,-1%"
cd /d "%SCRIPT_DIR%"
set "PYTHONDONTWRITEBYTECODE=1"

cls
echo ================================================================================
echo     ____   __  __  _____      _     _ _    _  _____ ____      _______
echo    / __ \ / _^|/ _^|/ ____^|    (_)   ^| ^| ^|  ^| ^|/ ____^|  _ \    ^|  ___  ^|===+
echo   ^| ^|  ^| ^| ^|_  ^|_^| ^|  __ _ __ _  __^| ^| ^|  ^| ^| (___ ^| ^|_) ^|   ^| ^[AI+^] ^|:::^|
echo   ^| ^|  ^| ^|  _^|  _^| ^| ^|_ ^| '__^| ^|/ _` ^| ^|  ^| ^|\___ \^|  _ ^<    ^| ^[ZIM^] ^|:::^|
echo   ^| ^|__^| ^| ^| ^| ^| ^| ^|__^| ^| ^|  ^| ^| (_^| ^| ^|__^| ^|____) ^| ^|_) ^|   ^|_______^|===+
echo    \____/^|_^| ^|_^|  \_____^|_^|  ^|_^|\__,_^|\____/^|_____/^|____/   OFFGRIDUSB.COM
echo --------------------------------------------------------------------------------
echo   Universal Portable USB Edition  ^|  Zero Docker  ^|  Zero Cloud  ^|  Air-Gapped
echo   Signed: @TheBlindHacker  *  @johndikeman  *  @organized-nick  *  OffGridUSB Team
echo   [*] 100% Air-Gapped Offline Operation: Zero External Network Access Required
echo ================================================================================
echo   Active USB Drive     : %SCRIPT_DIR%
echo   Offline ZIM Library  : http://127.0.0.1:8081  ^(Kiwix Server^)
echo ================================================================================
echo   [1/2] Verifying flash media integrity...

:: ============================================================================
:: Pre-Flight Storage Integrity Check: Detect Counterfeit Phantom Sectors (<0.5s)
:: ============================================================================
set "CORRUPT_DETECTED=0"
set "CHECK_PERFORMED=0"

:: 1. Try fast portable Python inline (< 0.15s, samples canary + 1 ZIM + 1 GGUF)
set "PY_EXE="
if exist "%SCRIPT_DIR%bin\windows_x86_64\python\python.exe" (
    set "PY_EXE=%SCRIPT_DIR%bin\windows_x86_64\python\python.exe"
) else if exist "%SCRIPT_DIR%bin\python\python.exe" (
    set "PY_EXE=%SCRIPT_DIR%bin\python\python.exe"
)

if defined PY_EXE (
    "!PY_EXE!" -B -c "import sys, os, glob; d=sys.argv[1]; ts=[]; c=os.path.join(d,'data','.integrity_canary'); (ts.append(c) if os.path.isfile(c) else None); zs=sorted(glob.glob(os.path.join(d,'data','zim','*.zim'))); ms=sorted(glob.glob(os.path.join(d,'data','models','*.gguf'))); ts.extend(zs[:1]+ms[:1]); ts = ts or glob.glob(os.path.join(d,'bin','*','*.exe'))[:2]; [sys.exit(10) for f in ts if os.path.isfile(f) and ((open(f,'rb').read(512).count(b'\x00')==min(512,os.path.getsize(f))>0) or (os.path.getsize(f)>10485760 and (lambda s: (s.seek(os.path.getsize(f)-512), s.read(512).count(b'\x00')==512)[1])(open(f,'rb'))))]; sys.exit(0)" "%DIR_ARG%" >nul 2>&1
    if !errorlevel! equ 10 set "CORRUPT_DETECTED=1"
    set "CHECK_PERFORMED=1"
)

:: 2. Inline PowerShell fallback (< 0.8s)
if "!CHECK_PERFORMED!"=="0" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$d=$args[0]; $ts=@(); if(Test-Path \"$d\data\.integrity_canary\"){$ts+=\"$d\data\.integrity_canary\"}; $ts+=Get-ChildItem -Path \"$d\data\zim\*.zim\" -File -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object {$_.FullName}; $ts+=Get-ChildItem -Path \"$d\data\models\*.gguf\" -File -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object {$_.FullName}; if(-not $ts){$ts+=Get-ChildItem -Path \"$d\bin\" -Include *.exe,*.tar.gz -Recurse -File -EA SilentlyContinue | Select-Object -First 2 | ForEach-Object {$_.FullName}}; foreach($f in $ts){try{$len=(Get-Item -LiteralPath $f).Length; if($len -gt 0){$fs=[System.IO.File]::OpenRead($f); $b=New-Object byte[] ([Math]::Min(512L,$len)); $r=$fs.Read($b,0,$b.Length); $n=$true; for($i=0;$i -lt $r;$i++){if($b[$i] -ne 0){$n=$false;break}}; if($r -gt 0 -and $n){$fs.Close(); exit 10}; if($len -gt 10485760){$fs.Seek($len-512,[System.IO.SeekOrigin]::Begin)|Out-Null; $r2=$fs.Read($b,0,512); $n2=$true; for($i=0;$i -lt $r2;$i++){if($b[$i] -ne 0){$n2=$false;break}}; if($r2 -gt 0 -and $n2){$fs.Close(); exit 10}}; $fs.Close()}}catch{}}; exit 0" "%DIR_ARG%" >nul 2>&1
    if !errorlevel! equ 10 set "CORRUPT_DETECTED=1"
)

if "!CORRUPT_DETECTED!"=="1" (
    echo.
    echo ================================================================================
    echo [ERROR] Counterfeit flash media corruption detected^^! Unbacked phantom sectors found on drive.
    echo.
    echo Storage hardware reports capacity that exceeds real physical silicon.
    echo Critical data files sit in unbacked sectors and read back as blank null bytes ^(\x00^).
    echo Launch aborted to prevent silent data loss and runtime crashes.
    echo Please re-provision this bundle onto a genuine, verified flash drive or SSD.
    echo ================================================================================
    echo.
    pause
    exit /b 1
)

echo   [2/2] Starting OffGridUSB Engine... Default browser will open automatically.
echo         ^(Keep this window open while using OffGridUSB. Press Ctrl+C to stop.^)
echo.

:: Locate the portable runner (check root and bin\)
set "RUNNER="
if exist "%SCRIPT_DIR%run_windows.bat" (
    set "RUNNER=%SCRIPT_DIR%run_windows.bat"
) else if exist "%SCRIPT_DIR%bin\run_windows.bat" (
    set "RUNNER=%SCRIPT_DIR%bin\run_windows.bat"
)

if not defined RUNNER (
    echo [ERROR] Runner script run_windows.bat not found on drive %SCRIPT_DIR%.
    echo Please ensure the drive contains bin\run_windows.bat or run_windows.bat.
    echo.
    pause
    exit /b 1
)

:: Delegate to runner bound strictly to loopback localhost 127.0.0.1 (zero firewall prompts)
call "!RUNNER!" --host 127.0.0.1 %*
set "EXIT_CODE=%errorlevel%"

echo.
echo ================================================================================
if !EXIT_CODE! equ 0 (
    echo   OffGridUSB session ended cleanly.
) else (
    echo   [WARN] OffGridUSB exited with code !EXIT_CODE!.
    if !EXIT_CODE! equ 3 (
        echo   Exit code 3 = Python runtime discovery or version check failed in run_windows.bat.
        echo   Re-run with verbosity to see the exact failing step:
        echo     "!RUNNER!" --host 127.0.0.1 --debug
        echo   ^(or set environment variable OFFGRIDUSB_DEBUG=1 before launching^)
    )
)
echo ================================================================================
echo   Press any key to close this window...
pause >nul
exit /b !EXIT_CODE!
