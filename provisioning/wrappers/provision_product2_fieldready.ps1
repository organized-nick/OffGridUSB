<#
.SYNOPSIS
    provision_product2_fieldready.ps1 - Dedicated 1-Command Provisioner for Product 2 (FieldReady).

.DESCRIPTION
    Provisions OffGridUSB Product 2 (FieldReady, Tiers 0 & 1) targeting 32 GB USB flash drives
    with payload ~16-20 GB (lean local payload: 4.69 GB, designed for attached drive D:).
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

& $engine -Product "Product2" -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -Profile $Profile @args
