<#
.SYNOPSIS
    OffGridUSB (offgridusb.com) -- Safe USB Drive Formatter (exFAT / FAT32) & Provisioner
.DESCRIPTION
    Formats a removable USB flash drive or USB SSD (with hard safety blocks preventing
    any operation on C: or OS boot/system disks) and provisions the full OffGridUSB
    portable runtime, cross-OS launchers, Internet-in-a-Box (.zim), and AI models (.gguf).
.EXAMPLE
    .\scripts\format_and_setup_usb.ps1
    .\scripts\format_and_setup_usb.ps1 -DriveLetter E -FileSystem exFAT -VolumeLabel OFFGRIDUSB
    .\scripts\format_and_setup_usb.ps1 -DriveLetter E -SkipFormat
#>

param(
    [string]$DriveLetter = "",
    [ValidateSet("exFAT", "FAT32", "KeepExisting")]
    [string]$FileSystem = "",
    [string]$VolumeLabel = "OFFGRIDUSB",
    [switch]$SkipFormat,
    [switch]$SkipCopy
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SystemDriveLetter = ($env:SystemDrive -replace ":", "").ToUpper()
if (-not $SystemDriveLetter) { $SystemDriveLetter = "C" }

function Test-IsAdmin {
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-MaxStagedFileSizeBytes {
    $maxBytes = [int64]0
    foreach ($sub in @("data\zim", "data\models", "bin")) {
        $p = Join-Path $SourceRoot $sub
        if (Test-Path $p) {
            $largest = Get-ChildItem -Path $p -Recurse -File -ErrorAction SilentlyContinue |
                Sort-Object Length -Descending |
                Select-Object -First 1
            if ($largest -and $largest.Length -gt $maxBytes) {
                $maxBytes = [int64]$largest.Length
            }
        }
    }
    return $maxBytes
}

function Get-CandidateUsbVolumes {
    $vols = Get-Volume | Where-Object {
        $null -ne $_.DriveLetter -and
        $_.DriveLetter.ToString().ToUpper() -ne "C" -and
        $_.DriveLetter.ToString().ToUpper() -ne $SystemDriveLetter
    } | Sort-Object DriveLetter

    $results = @()
    foreach ($v in $vols) {
        $dl = $v.DriveLetter.ToString().ToUpper()
        $busType = "Unknown"
        $friendlyModel = ""
        $isBootOrSys = $false
        try {
            $part = Get-Partition -DriveLetter $dl -ErrorAction SilentlyContinue
            if ($part) {
                $disk = Get-Disk -Number $part.DiskNumber -ErrorAction SilentlyContinue
                if ($disk) {
                    $busType = [string]$disk.BusType
                    $friendlyModel = [string]$disk.FriendlyName
                    if ($disk.IsBoot -or $disk.IsSystem) {
                        $isBootOrSys = $true
                    }
                }
            }
        } catch {}

        if (-not $isBootOrSys) {
            $results += [PSCustomObject]@{
                DriveLetter = $dl
                Label       = if ($v.FileSystemLabel) { $v.FileSystemLabel } else { "NO_LABEL" }
                FileSystem  = if ($v.FileSystem) { $v.FileSystem } else { "RAW" }
                FreeGB      = [math]::Round(($v.SizeRemaining / 1GB), 2)
                TotalGB     = [math]::Round(($v.Size / 1GB), 2)
                DriveType   = [string]$v.DriveType
                BusType     = $busType
                Model       = $friendlyModel
            }
        }
    }
    return $results
}

function Show-DriveTable {
    $candidates = Get-CandidateUsbVolumes
    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  OffGridUSB (offgridusb.com) // USB Drive Formatter & Setup Wizard" -ForegroundColor Cyan
    Write-Host "  Source Workspace: $SourceRoot" -ForegroundColor Gray
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Detected External / Removable Drives (System drive ${SystemDriveLetter}: is hard-blocked):" -ForegroundColor Yellow

    if (-not $candidates -or $candidates.Count -eq 0) {
        Write-Host "    [!] No external USB drives detected. Plug in a USB stick and press [R]!" -ForegroundColor DarkYellow
    } else {
        foreach ($c in $candidates) {
            $col = if ($c.BusType -eq "USB" -or $c.DriveType -eq "Removable") { "Green" } else { "Cyan" }
            $modelSuffix = if ($c.Model) { " ($($c.Model))" } else { "" }
            Write-Host ("    [{0}:]  {1,-14} | {2,-6} | {3,6} GB free / {4,6} GB | Bus: {5}{6}" -f `
                $c.DriveLetter, $c.Label, $c.FileSystem, $c.FreeGB, $c.TotalGB, $c.BusType, $modelSuffix) -ForegroundColor $col
        }
    }
    Write-Host ""
}

# 1. Select Target USB Drive Letter
$targetLetter = ""
if ($DriveLetter) {
    $targetLetter = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
} else {
    while ($true) {
        Show-DriveTable
        $raw = Read-Host "  Enter Target USB Drive Letter (e.g. D or E), [R] to refresh, or [Q] to quit"
        if ($null -eq $raw) { exit 0 }
        $clean = $raw.Trim().ToUpper() -replace "[:\\/\s]", ""
        if ($clean -in @("Q", "EXIT")) { exit 0 }
        if ($clean -in @("R", "")) { continue }
        if ($clean.Length -ne 1 -or $clean -notmatch "^[A-Z]$") {
            Write-Host "  [ERROR] Please enter a single drive letter (e.g. D or E)." -ForegroundColor Red
            continue
        }
        $targetLetter = $clean
        break
    }
}

# HARD SAFETY BLOCKS
if ($targetLetter -eq "C" -or $targetLetter -eq $SystemDriveLetter) {
    Write-Host "  [SAFETY BLOCK] Refusing to touch system drive ${targetLetter}:!" -ForegroundColor Red
    exit 1
}

try {
    $checkPart = Get-Partition -DriveLetter $targetLetter -ErrorAction SilentlyContinue
    if ($checkPart) {
        $checkDisk = Get-Disk -Number $checkPart.DiskNumber -ErrorAction SilentlyContinue
        if ($checkDisk -and ($checkDisk.IsBoot -or $checkDisk.IsSystem)) {
            Write-Host "  [SAFETY BLOCK] Disk $($checkPart.DiskNumber) (${targetLetter}:) is an OS Boot/System disk. Aborting!" -ForegroundColor Red
            exit 1
        }
    }
} catch {}

if (-not (Test-Path "${targetLetter}:\")) {
    Write-Host "  [ERROR] Drive ${targetLetter}:\ is not mounted or accessible." -ForegroundColor Red
    exit 1
}

# 2. Choose Formatting Mode
$maxFileBytes = Get-MaxStagedFileSizeBytes
$hasLargeFiles = ($maxFileBytes -ge 4294967295)

if ($SkipFormat) {
    $FileSystem = "KeepExisting"
}

if (-not $FileSystem) {
    Write-Host ""
    Write-Host "  Filesystem Recommendation for OffGridUSB:" -ForegroundColor Yellow
    Write-Host "    * [1] Format as exFAT (RECOMMENDED) -- Works natively on Windows, macOS, Linux," -ForegroundColor Green
    Write-Host "          Raspberry Pi & ChromeOS, and supports >4GB Wikipedia .zim & .gguf models." -ForegroundColor Green
    Write-Host "    * [2] Format as FAT32 -- Only for <=32GB drives with Tier 0 files (<4GB each)." -ForegroundColor Cyan
    Write-Host "    * [3] Keep Existing Filesystem (Non-Destructive) -- Copy OffGridUSB without erasing." -ForegroundColor White
    Write-Host ""

    $fsChoice = Read-Host "  Select [1] Format exFAT, [2] Format FAT32, or [3] Keep Existing (Enter = 3 Safe Copy)"
    $fc = if ($null -eq $fsChoice) { "3" } else { $fsChoice.Trim() }
    if ($fc -eq "1") { $FileSystem = "exFAT" }
    elseif ($fc -eq "2") { $FileSystem = "FAT32" }
    else { $FileSystem = "KeepExisting" }
}

if ($FileSystem -eq "FAT32" -and $hasLargeFiles) {
    $largestGb = [math]::Round($maxFileBytes / 1GB, 2)
    Write-Host ""
    Write-Host "  [WARN] Your staged assets include a file of ${largestGb} GB (> 4.0 GB FAT32 limit)!" -ForegroundColor Red
    Write-Host "         Switching target filesystem recommendation to exFAT so copy succeeds." -ForegroundColor Yellow
    $FileSystem = "exFAT"
}

# 3. Perform Safe Formatting (if requested)
if ($FileSystem -in @("exFAT", "FAT32")) {
    $volNow = Get-Volume -DriveLetter $targetLetter -ErrorAction SilentlyContinue
    $totalGbNow = if ($volNow) { [math]::Round($volNow.Size / 1GB, 2) } else { 0 }

    if ($FileSystem -eq "FAT32" -and $totalGbNow -gt 32.5) {
        Write-Host "  [WARN] Windows native Format-Volume restricts FAT32 to <=32GB partitions (${totalGbNow} GB detected)." -ForegroundColor Yellow
        Write-Host "         Using exFAT instead for full capacity and cross-OS compatibility." -ForegroundColor Yellow
        $FileSystem = "exFAT"
    }

    if (-not (Test-IsAdmin)) {
        Write-Host ""
        Write-Host "  [ADMIN REQUIRED] Formatting a volume in Windows requires Administrator privileges." -ForegroundColor Yellow
        $elevate = Read-Host "  Re-launch this wizard as Administrator now? [Y/N]"
        if ($elevate.Trim().ToUpper() -eq "Y") {
            $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -DriveLetter $targetLetter -FileSystem $FileSystem -VolumeLabel `"$VolumeLabel`""
            if ($SkipCopy) { $argList += " -SkipCopy" }
            Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait
            exit 0
        } else {
            Write-Host "  [ABORTED] Format cancelled. Run without formatting ([3]) or run as Administrator." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "  ============================================================================" -ForegroundColor Red
    Write-Host "  [DESTRUCTIVE ACTION WARNING]" -ForegroundColor Red
    Write-Host "  ALL EXISTING DATA ON DRIVE ${targetLetter}: ($($volNow.FileSystemLabel), ${totalGbNow} GB) WILL BE ERASED!" -ForegroundColor Red
    Write-Host "  New Filesystem: $FileSystem   |   New Label: $VolumeLabel" -ForegroundColor Yellow
    Write-Host "  ============================================================================" -ForegroundColor Red
    $confirmPhrase = "FORMAT $targetLetter"
    $typed = Read-Host "  Type '$confirmPhrase' (all caps) to permanently erase and format ${targetLetter}:"
    if ($typed -cne $confirmPhrase) {
        Write-Host "  [CANCELLED] Confirmation phrase did not match '$confirmPhrase'. Drive untouched." -ForegroundColor Yellow
        exit 0
    }

    Write-Host ""
    Write-Host "  >>> Formatting ${targetLetter}: as $FileSystem (Label: $VolumeLabel)..." -ForegroundColor Cyan
    if ($FileSystem -eq "exFAT") {
        # 128 KB allocation unit optimizes sequential .gguf mmap & .zim archive throughput on flash NAND
        Format-Volume -DriveLetter $targetLetter -FileSystem exFAT -AllocationUnitSize 131072 -NewFileSystemLabel $VolumeLabel -Confirm:$false -Force | Out-Null
    } else {
        Format-Volume -DriveLetter $targetLetter -FileSystem FAT32 -NewFileSystemLabel $VolumeLabel -Confirm:$false -Force | Out-Null
    }
    Start-Sleep -Seconds 1
    Write-Host "  [OK] Formatted ${targetLetter}: as $FileSystem ($VolumeLabel)." -ForegroundColor Green
}

# 4. Provision OffGridUSB Runtime, Launchers, Binaries, ZIMs & Models
if (-not $SkipCopy) {
    $existingVol = Get-Volume -DriveLetter $targetLetter -ErrorAction SilentlyContinue
    if ($existingVol -and $existingVol.FileSystem -eq "FAT32" -and $hasLargeFiles) {
        Write-Host "  [ERROR] Target drive ${targetLetter}: is formatted as FAT32, which cannot store >4GB .zim/.gguf files." -ForegroundColor Red
        Write-Host "          Re-run and select [1] Format as exFAT." -ForegroundColor Yellow
        exit 1
    }

    & (Join-Path $PSScriptRoot "clone_to_usb.ps1") -TargetDriveLetter $targetLetter -SingleShot
}
