<#
.SYNOPSIS
    provision_product1_pocketsurvival.ps1 - Dedicated 1-Command Provisioner for Product 1 (PocketSurvival).

.DESCRIPTION
    Provisions OffGridUSB Product 1 (PocketSurvival, Tier 0) targeting 8 GB USB flash drives
    with a payload <= 6.5 GB (lean local payload: 1.39 GB).
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
    [string]$CacheDir = "",  # Resolved by provision_usb.ps1: %LOCALAPPDATA%\offgridusb\cache

    [Parameter(Mandatory = $false)]
    [string]$Profile = "Auto"
)

$engine = Join-Path $PSScriptRoot "provision_usb.ps1"
if (-not (Test-Path $engine)) {
    $engine = Join-Path (Split-Path -Parent $PSScriptRoot) "provision_usb.ps1"
}

& $engine -Product "Product1" -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -Profile $Profile @args
