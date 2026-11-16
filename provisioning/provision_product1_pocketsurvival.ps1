<#
.SYNOPSIS
    provision_product1_pocketsurvival.ps1 - Dedicated 1-Command Provisioner for Product 1 (PocketSurvival).

.DESCRIPTION
    Provisions OffGridUSB Product 1 (PocketSurvival, Tier 0) targeting 64 GB USB flash drives
    AI-free edition: full survival/medical/wiki ZIM payload (~54.0 GB, lean profile: ~1.4 GB). No models.
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

& $engine -Product "Product1" -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -SourceRoot $SourceRoot -NoDownload:$NoDownload -Profile $Profile -BwLimitKBps $BwLimitKBps @RemainingArgs
