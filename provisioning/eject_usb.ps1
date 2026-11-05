<#
.SYNOPSIS
    eject_usb.ps1 - Reusable 5-Step Safe USB Flush, Dismount & Hardware Eject Script.

.DESCRIPTION
    Safely flushes, dismounts, and ejects an attached OffGridUSB flash drive:
    1. Hardware Safety Gate (Find-CandidateUsbDrives + Assert-TargetDriveSafety; never C: or Disk 0).
    2. Releases open file handles on the USB drive (Stop-TargetDriveProcesses).
    3. Flushes OS file cache to physical NAND flash (Write-VolumeCache).
    4. Invokes Explorer Shell Eject + Win32 Kernel Volume Lock/Dismount/Eject (IOCTL_STORAGE_EJECT_MEDIA).
    5. Verifies the volume is dismounted (Test-Path returns False).

.PARAMETER Drive
    Optional target USB drive letter (e.g. 'D' or 'D:'). Auto-detects if omitted.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Drive = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$SafetyLib = Join-Path $ScriptDir "lib\SafetyValidator.ps1"
if (-not (Test-Path $SafetyLib)) {
    throw "SafetyValidator.ps1 not found at: $SafetyLib"
}
. $SafetyLib

$result = Invoke-SafeUsbEject -Drive $Drive
exit $(if ($result.Ejected) { 0 } else { 1 })
