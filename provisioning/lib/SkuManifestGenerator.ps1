<#
.SYNOPSIS
    SkuManifestGenerator - Dynamically generates manifests/product_sku.json
    for provisioned OffGridUSB target media.

.DESCRIPTION
    Reads product definitions from manifests/products.json, tailors active/hidden
    feature flags, model rosters, and ZIM archives for the selected SKU, and outputs
    a clean descriptor used by the customer Command Center to adapt its UI.
#>

[CmdletBinding()]
param()

function New-ProductSkuManifest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProductSku,

        [Parameter(Mandatory = $false)]
        [string]$ProductsJsonPath = "",

        [Parameter(Mandatory = $false)]
        [string]$TargetDriveLetter = "D:",

        [Parameter(Mandatory = $false)]
        [string]$Filesystem = "exFAT",

        [Parameter(Mandatory = $false)]
        [int]$ClusterSizeBytes = 131072,

        [Parameter(Mandatory = $false)]
        [string]$ProfileName = "Auto",

        [Parameter(Mandatory = $false)]
        [string]$OutputPath = ""
    )

    if (-not $ProductsJsonPath) {
        $repoRoot = Split-Path -Parent $PSScriptRoot
        $candidate = Join-Path $repoRoot "manifests\products.json"
        if (Test-Path $candidate) {
            $ProductsJsonPath = $candidate
        } else {
            $ProductsJsonPath = "manifests\products.json"
        }
    }

    if (-not (Test-Path $ProductsJsonPath)) {
        throw "products.json not found at: $ProductsJsonPath"
    }

    $catalog = Get-Content -Raw -Path $ProductsJsonPath | ConvertFrom-Json
    $matched = $null
    foreach ($p in $catalog.products) {
        if ($p.sku -eq $ProductSku -or $p.product_id -eq $ProductSku -or $p.name -like "*$ProductSku*") {
            $matched = $p
            break
        }
    }

    if (-not $matched) {
        throw "Product SKU '$ProductSku' not found in $ProductsJsonPath"
    }

    # Resolve profile
    $chosenProfile = $ProfileName
    if ($chosenProfile -eq "Auto") {
        if ($matched.payload_profiles.PSObject.Properties["lean"]) {
            $chosenProfile = "lean"
        } else {
            $chosenProfile = "full"
        }
    }

    $profileData = $matched.payload_profiles.$chosenProfile
    if (-not $profileData) {
        $chosenProfile = "full"
        $profileData = $matched.payload_profiles.full
    }

    $activeModels = @()
    if ($profileData.models) {
        $activeModels = @($profileData.models)
    }

    $activeZims = @()
    if ($profileData.zim_archives) {
        $activeZims = @($profileData.zim_archives)
    }

    $cleanDrive = ($TargetDriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $nowUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

    $manifest = [ordered]@{
        "schema_version"          = "1.0"
        "sku"                     = $matched.sku
        "product_id"              = $matched.product_id
        "name"                    = $matched.name
        "tagline"                 = $matched.tagline
        "tiers"                   = $matched.tiers
        "target_drive_size_gb"    = $matched.target_drive_size_gb
        "min_drive_capacity_bytes"= $matched.min_drive_capacity_bytes
        "features"                = $matched.active_features
        "hidden_features"         = $matched.hidden_features
        "active_models"           = $activeModels
        "active_zim_archives"     = $activeZims
        "default_model"           = $matched.default_model
        "services"                = [ordered]@{
            "command_center_port" = 8000
            "kiwix_port"          = 8081
            "llama_port"          = 8082
        }
        "provisioning"            = [ordered]@{
            "provisioned_at"      = $nowUtc
            "provisioner_version" = "1.0.0"
            "filesystem"          = $Filesystem
            "cluster_size_bytes"  = $ClusterSizeBytes
            "target_drive_letter" = "${cleanDrive}:"
        }
    }

    $jsonStr = $manifest | ConvertTo-Json -Depth 10

    if ($OutputPath) {
        $outDir = [System.IO.Path]::GetDirectoryName($OutputPath)
        if ($outDir -and -not (Test-Path $outDir)) {
            New-Item -ItemType Directory -Path $outDir -Force | Out-Null
        }
        [System.IO.File]::WriteAllText($OutputPath, $jsonStr, [System.Text.Encoding]::UTF8)
    }

    return [PSCustomObject]@{
        ManifestData = $manifest
        JsonString   = $jsonStr
        OutputPath   = $OutputPath
    }
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function New-ProductSkuManifest -ErrorAction SilentlyContinue
}
