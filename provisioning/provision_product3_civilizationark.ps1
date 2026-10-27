<#
.SYNOPSIS
    provision_product3_civilizationark.ps1 - Dedicated 1-Command Provisioner for Product 3 (CivilizationArk).

.DESCRIPTION
    Provisions OffGridUSB Product 3 (CivilizationArk, Tiers 0, 1 & 2) targeting 128 GB USB flash drives
    with payload ~65-72 GB (including 50.2 GB Wikipedia). Rejects 64 GB USB drives.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Drive,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun,

    [Parameter(Mandatory = $false)]
    [switch]$Info,

    [Parameter(Mandatory = $false)]
    [switch]$NonInteractive,

    [Parameter(Mandatory = $false)]
    [string]$FilesystemAction = "Auto",

    [Parameter(Mandatory = $false)]
    [string]$CacheDir = "C:\Users\ndoki\Desktop\offgridusb\cache",

    [Parameter(Mandatory = $false)]
    [string]$Profile = "Auto"
)

$engine = Join-Path $PSScriptRoot "provision_usb.ps1"
if (-not (Test-Path $engine)) {
    $engine = Join-Path (Split-Path -Parent $PSScriptRoot) "provision_usb.ps1"
}

& $engine -Product "Product3" -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -Profile $Profile @args
