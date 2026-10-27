# ==============================================================================
# OffGridUSB (offgridusb.com) -- Multi-USB Flash Drive Mass Cloner
# Copies the air-gapped portable runtime + Internet-in-a-Box + GGUF AI models
# to 1, 2, 3+ USB flash drives using 16-thread Robocopy in < 45 seconds/stick.
# ==============================================================================

param(
    [string]$TargetDriveLetter = "",
    [switch]$SingleShot
)

$ErrorActionPreference = "Continue"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SystemDriveLetter = ($env:SystemDrive -replace ":", "").ToUpper()
if (-not $SystemDriveLetter) { $SystemDriveLetter = "C" }

$RootFiles = @(
    "START_OFFGRIDUSB_WINDOWS.bat",
    "START_OFFGRIDUSB_MAC.command",
    "START_OFFGRIDUSB_LINUX.sh",
    "START_EMYRGE_WINDOWS.bat",
    "START_EMYRGE_MAC.command",
    "START_EMYRGE_LINUX.sh",
    "MAKE_USB_DRIVES.bat",
    "FORMAT_AND_SETUP_USB.bat",
    "DOWNLOAD_INTERNET_IN_A_BOX.bat",
    "run_windows.bat",
    "run_linux.sh",
    "run_macos.command",
    "README.md",
    "CONTRIBUTING.md",
    "PITCH_CHEATSHEET.md"
)

$RuntimeDirs = @(
    "docs",
    "manifests",
    "src",
    "web",
    "bin",
    "data",
    "scripts"
)

$ExcludedDirs = @(
    "__pycache__",
    ".pytest_cache",
    ".agents",
    "tests",
    "tmp_dl",
    ".git",
    ".venv"
)

$ExcludedFiles = @(
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*-DESKTOP-*",
    "*-JoeWorkTop*"
)

function Show-DetectedDrives {
    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  OffGridUSB (offgridusb.com) // Multi-USB Flash Drive Cloner (16-Thread Copy)" -ForegroundColor Cyan
    Write-Host "  Source Package: $SourceRoot" -ForegroundColor Gray
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Detected External / Removable USB Drives:" -ForegroundColor Yellow

    $volumes = Get-Volume | Where-Object {
        $_.DriveLetter -ne $null -and
        $_.DriveLetter.ToString().ToUpper() -ne "C" -and
        $_.DriveLetter.ToString().ToUpper() -ne $SystemDriveLetter
    } | Sort-Object DriveLetter

    if (-not $volumes -or $volumes.Count -eq 0) {
        Write-Host "    [!] No external USB drives detected yet. Plug in a USB flash drive!" -ForegroundColor DarkYellow
    } else {
        foreach ($v in $volumes) {
            $dl = $v.DriveLetter.ToString().ToUpper()
            $label = if ($v.FileSystemLabel) { $v.FileSystemLabel } else { "NO_LABEL" }
            $fs = if ($v.FileSystem) { $v.FileSystem } else { "RAW" }
            $freeGB = [math]::Round(($v.SizeRemaining / 1GB), 2)
            $totalGB = [math]::Round(($v.Size / 1GB), 2)
            $dtype = $v.DriveType
            $color = if ($dtype -eq "Removable") { "Green" } else { "Cyan" }
            Write-Host ("    [{0}:]  {1,-18} | {2,-6} | {3,6} GB free / {4,6} GB total | Type: {5}" -f $dl, $label, $fs, $freeGB, $totalGB, $dtype) -ForegroundColor $color
        }
    }
    Write-Host ""
}

$CloneCount = 0

while ($true) {
    if ($TargetDriveLetter) {
        $clean = ($TargetDriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
        $TargetDriveLetter = ""
    } else {
        Show-DetectedDrives
        $rawInput = Read-Host "  Enter Target USB Drive Letter (e.g. D or E), [R] to refresh, or [Q] to quit"
        if ($null -eq $rawInput) { break }
        $clean = $rawInput.Trim().ToUpper() -replace "[:\\/\s]", ""
    }

    if ($clean -eq "Q" -or $clean -eq "N" -or $clean -eq "EXIT") {
        break
    }
    if ($clean -eq "R" -or $clean -eq "") {
        if ($SingleShot) { break }
        continue
    }

    if ($clean.Length -ne 1 -or $clean -notmatch "^[A-Z]$") {
        Write-Host "  [ERROR] Please enter a single drive letter (e.g., D or E)." -ForegroundColor Red
        if ($SingleShot) { exit 1 }
        continue
    }

    # HARD SAFETY BLOCK FOR C: AND OS SYSTEM DRIVE
    if ($clean -eq "C" -or $clean -eq $SystemDriveLetter) {
        Write-Host ""
        Write-Host "  [SAFETY BLOCK] Refusing to write to system drive ${clean}:! Please choose a USB flash drive." -ForegroundColor Red
        Write-Host ""
        if ($SingleShot) { exit 1 }
        continue
    }

    $targetRoot = "${clean}:\"
    if (-not (Test-Path $targetRoot)) {
        Write-Host "  [ERROR] Drive ${targetRoot} was not found or is not mounted. Plug it in and press [R]." -ForegroundColor Red
        if ($SingleShot) { exit 1 }
        continue
    }

    $volInfo = Get-Volume -DriveLetter $clean -ErrorAction SilentlyContinue
    if ($volInfo -and $volInfo.DriveType -ne "Removable" -and -not $SingleShot) {
        $confirmFixed = Read-Host "  [NOTE] Drive ${clean}: reports DriveType '$($volInfo.DriveType)' (e.g. USB SSD/enclosure). Continue? [Y/N]"
        if ($confirmFixed.Trim().ToUpper() -ne "Y") {
            continue
        }
    }

    # Guard against >4GB .zim/.gguf copy failure onto FAT32 sticks
    if ($volInfo -and $volInfo.FileSystem -eq "FAT32") {
        $oversize = Get-ChildItem -Path (Join-Path $SourceRoot "data") -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -ge 4294967295 } |
            Select-Object -First 1
        if ($oversize) {
            $ovGb = [math]::Round($oversize.Length / 1GB, 2)
            Write-Host ""
            Write-Host "  [FAT32 4GB LIMIT] File '$($oversize.Name)' (${ovGb} GB) exceeds FAT32's 4.0 GB limit!" -ForegroundColor Red
            Write-Host "                    Format ${clean}: as exFAT first using FORMAT_AND_SETUP_USB.bat." -ForegroundColor Yellow
            if ($SingleShot) { exit 1 }
            continue
        }
    }

    Write-Host ""
    Write-Host "  >>> Cloning Portable OffGridUSB + Internet-in-a-Box to ${targetRoot} ..." -ForegroundColor Green
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    # 1. Copy root launcher & guide files (non-destructive: never deletes existing user files on USB)
    $existingRootFiles = @()
    foreach ($f in $RootFiles) {
        if (Test-Path (Join-Path $SourceRoot $f)) {
            $existingRootFiles += $f
        }
    }
    if ($existingRootFiles.Count -gt 0) {
        Write-Host "    [1/2] Copying 1-Click Cross-OS Launchers & Guides..." -ForegroundColor Cyan
        $rcArgsRoot = @($SourceRoot, $targetRoot) + $existingRootFiles + @("/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
        & robocopy @rcArgsRoot | Out-Null
    }

    # 2. Copy runtime directories using 16-thread Robocopy
    $dirIndex = 0
    $validDirs = $RuntimeDirs | Where-Object { Test-Path (Join-Path $SourceRoot $_) }
    $totalDirs = $validDirs.Count

    foreach ($dirName in $validDirs) {
        $dirIndex++
        $srcDir = Join-Path $SourceRoot $dirName
        $dstDir = Join-Path $targetRoot $dirName
        Write-Host ("    [2/2] ({0}/{1}) Syncing /{2} ..." -f $dirIndex, $totalDirs, $dirName) -ForegroundColor Cyan

        $rcArgs = @(
            $srcDir,
            $dstDir,
            "/E",
            "/MT:4",
            "/R:2",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/NP",
            "/XD"
        ) + $ExcludedDirs + @("/XF") + $ExcludedFiles

        & robocopy @rcArgs | Out-Null
    }

    # Ensure standard runtime folders exist on target USB even if not yet populated
    foreach ($reqSub in @("data\vault", "data\uploads", "data\models", "data\zim")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $targetRoot $reqSub) | Out-Null
    }

    $sw.Stop()
    $CloneCount++
    $secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)

    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Green
    Write-Host "  [OK] OffGridUSB Drive ${clean}: READY in ${secs}s! (Total cloned this session: $CloneCount)" -ForegroundColor Green
    Write-Host "       * Windows Launch   : ${clean}:\START_EMYRGE_WINDOWS.bat" -ForegroundColor White
    Write-Host "       * macOS Launch     : ${clean}:/START_EMYRGE_MAC.command" -ForegroundColor White
    Write-Host "       * Linux/Pi Launch  : ${clean}:/START_EMYRGE_LINUX.sh" -ForegroundColor White
    Write-Host "       * Chromebook Mode  : ${clean}:/web/static/wasm/chromebook.html" -ForegroundColor White
    Write-Host "================================================================================" -ForegroundColor Green
    Write-Host ""

    if ($SingleShot) {
        break
    }

    $next = Read-Host "  USB Drive Ready! Swap in your next flash drive and press [Y] to clone another copy, or [N] to finish"
    if ($next.Trim().ToUpper() -eq "N" -or $next.Trim().ToUpper() -eq "Q") {
        break
    }
}

if (-not $SingleShot) {
    Write-Host ""
    Write-Host "  All done! Cloned $CloneCount portable OffGridUSB drive(s)." -ForegroundColor Green
    Write-Host ""
}
