<#
.SYNOPSIS
    provision_product2_fieldready.ps1 - Dedicated 1-Command Provisioner for Product 2 (FieldReady).

.DESCRIPTION
    Provisions OffGridUSB Product 2 (FieldReady, Tiers 0 & 1) targeting 64 GB USB flash drives
    with ~58.9 GB full payload (44 ZIMs + 5 GGUFs + 14 engines) or 256 GB edition (-Edition 256 -> Product2-256).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Drive,

    [Parameter(Mandatory = $false)]
    [ValidateSet("64", "256")]
    [string]$Edition = "64",

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

$sku = if ($Edition -eq "256") { "Product2-256" } else { "Product2" }
& $engine -Product $sku -Drive $Drive -DryRun:$DryRun -Info:$Info -NonInteractive:$NonInteractive -FilesystemAction $FilesystemAction -CacheDir $CacheDir -SourceRoot $SourceRoot -NoDownload:$NoDownload -Profile $Profile -BwLimitKBps $BwLimitKBps @RemainingArgs
