<#
.SYNOPSIS
    provision_product3_civilizationark.ps1 - Dedicated 1-Command Provisioner for Product 3 (CivilizationArk).

.DESCRIPTION
    Provisions OffGridUSB Product 3 (CivilizationArk, Tiers 0, 1 & 2) targeting 256 GB portable SSDs
    (~181.9 GB full payload: complete English Wikipedia + 3B..32B model ladder + exo LAN swarm).
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
    [string]$CacheDir = "",

    [Parameter(Mandatory = $false)]
    [string]$SourceRoot = "",

    [Parameter(Mandatory = $false)]
    [switch]$NoDownload,

    [Parameter(Mandatory = $false)]
    [string]$Profile = "full",

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, [int]::MaxValue)]
    [int]$BwLimitKBps = 0,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$engine = Join-Path $PSScriptRoot "provision_usb.ps1"
if (-not (Test-Path $engine)) {
    $engine = Join-Path (Split-Path -Parent $PSScriptRoot) "provision_usb.ps1"
}

& $engine -Product "Product3" -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -SourceRoot $SourceRoot -NoDownload:$NoDownload -Profile $Profile -BwLimitKBps $BwLimitKBps @RemainingArgs
