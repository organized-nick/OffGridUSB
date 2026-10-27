@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: OffGridUSB (offgridusb.com) — Portable Single-Click Windows Launcher (F-01)
:: Zero-install, container-free air-gapped knowledge and adaptive AI harness
:: ============================================================================

set "SCRIPT_DIR=%~dp0"
if not exist "%SCRIPT_DIR%src\emyrge" (
    if exist "%SCRIPT_DIR%..\src\emyrge" (
        pushd "%SCRIPT_DIR%.."
        set "SCRIPT_DIR=!CD!\"
        popd
    )
)
cd /d "%SCRIPT_DIR%"

:: 1. Validate 64-bit Operating System Architecture (AMD64 or ARM64)
set "IS_64BIT=0"
if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" set "IS_64BIT=1"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "IS_64BIT=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="AMD64" set "IS_64BIT=1"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "IS_64BIT=1"

if "%IS_64BIT%" neq "1" (
    echo [ERROR] OffGridUSB requires a 64-bit operating system [AMD64 or ARM64].
    echo Legacy 32-bit x86 architectures are unsupported.
    exit /b 2
)

:: 2. Parse Command Line Arguments
set "PORT=8000"
if defined EMYRGE_PORT set "PORT=%EMYRGE_PORT%"
set "HOST=127.0.0.1"
set "HEADLESS=0"
set "CHROMEBOOK=0"
set "TIER_OVERRIDE="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h" goto show_help
if /i "%~1"=="--port" (
    set "PORT=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--host" (
    set "HOST=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--headless" (
    set "HEADLESS=1"
    shift
    goto parse_args
)
if /i "%~1"=="--chromebook" (
    set "CHROMEBOOK=1"
    shift
    goto parse_args
)
if /i "%~1"=="--tier" (
    set "TIER_OVERRIDE=%~2"
    shift
    shift
    goto parse_args
)
shift
goto parse_args

:show_help
echo ============================================================================
echo OffGridUSB (offgridusb.com) Windows Launcher
echo ============================================================================
echo Usage: run_windows.bat [OPTIONS]
echo.
echo Options:
echo   --port PORT       Set backend server port (default: 8000)
echo   --host HOST       Set bind address (default: 127.0.0.1, 0.0.0.0 for LAN)
echo   --headless        Do not automatically open default web browser
echo   --chromebook      Open pure-browser Wasm fallback shell directly
echo   --tier TIER       Force hardware tier override (-1 to 4)
echo   --help, -h        Display this help message
echo ============================================================================
exit /b 0

:args_done

:: 3. Pure Chromebook Browser Wasm Fallback Request
if "%CHROMEBOOK%"=="1" (
    echo [INFO] Launching pure-browser Wasm fallback shell...
    start "" "%SCRIPT_DIR%web\static\wasm\chromebook.html"
    exit /b 0
)

:: 4. Python Discovery Hierarchy (Bundled -> VirtualEnv -> System)
set "PYTHON_CMD="

if exist "%SCRIPT_DIR%bin\windows_x86_64\python\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%bin\windows_x86_64\python\python.exe"
) else if exist "%SCRIPT_DIR%bin\python\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%bin\python\python.exe"
) else if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_CMD=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_CMD=py -3"
    ) else (
        where python >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_CMD=python"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Compatible Python 3 runtime not found.
    echo Please install Python 3.10+ or place a portable distribution in bin\python.
    echo Opening fallback browser shell...
    start "" "%SCRIPT_DIR%web\static\wasm\chromebook.html"
    exit /b 3
)

:: Verify Python version >= 3.10
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python version must be >= 3.10. Current installation is incompatible.
    exit /b 3
)

:: 5. Configure Isolated Environment
set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"
set "EMYRGE_PORT=%PORT%"
set "EMYRGE_HOST=%HOST%"
if defined TIER_OVERRIDE set "EMYRGE_TIER=%TIER_OVERRIDE%"

:: 6. Launch Application or Fallback Shell
echo ============================================================================
echo OffGridUSB (offgridusb.com) — Offline Knowledge ^& Adaptive AI Harness
echo Host: %HOST%  Port: %PORT%
echo ============================================================================

if exist "%SCRIPT_DIR%src\emyrge\web\app.py" (
    set "EXTRA_ARGS="
    if "%HEADLESS%"=="1" set "EXTRA_ARGS=--headless"
    if defined TIER_OVERRIDE set "EXTRA_ARGS=!EXTRA_ARGS! --tier %TIER_OVERRIDE%"
    %PYTHON_CMD% -m emyrge.web.app --host %HOST% --port %PORT% !EXTRA_ARGS!
) else (
    echo [INFO] Core Skeleton initialized. Launching browser interface...
    if "%HEADLESS%"=="0" (
        start "" "%SCRIPT_DIR%web\static\wasm\chromebook.html"
    )
)

exit /b %errorlevel%
