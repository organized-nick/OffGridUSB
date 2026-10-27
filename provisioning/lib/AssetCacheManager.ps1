<#
.SYNOPSIS
    AssetCacheManager - Host asset cache management, magic header validation,
    and SKU payload verification for OffGridUSB.

.DESCRIPTION
    Validates binary magic headers (ZIM\x04 and GGUF), tracks host asset cache availability
    across local staging locations, and computes SHA-256 hashes.
#>

[CmdletBinding()]
param()

$script:DefaultCacheLocations = @(
    "C:\Users\ndoki\Desktop\offgridusb\cache",
    "C:\Users\ndoki\Desktop\offgridusb\OffGridUSB\data",
    "C:\Users\ndoki\Desktop\offgridusb\OFFGRIDUSB_CONSUMER_READY\data",
    "C:\Users\ndoki\Desktop\offgridusb\offgridUSB.com\data",
    "C:\Users\ndoki\Desktop\offgridusb\models_staging",
    "C:\Users\ndoki\Desktop\offgridusb\zim_Builds"
)

function Test-AssetMagicHeader {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $false)]
        [ValidateSet("Auto", "ZIM", "GGUF")]
        [string]$ExpectedType = "Auto"
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        return [PSCustomObject]@{
            IsValid      = $false
            DetectedType = "FileNotFound"
            MagicString  = ""
            ErrorMessage = "File does not exist: $FilePath"
        }
    }

    $ext = [System.IO.Path]::GetExtension($FilePath).ToLowerInvariant()
    $resolvedType = $ExpectedType
    if ($resolvedType -eq "Auto") {
        if ($ext -eq ".zim") {
            $resolvedType = "ZIM"
        } elseif ($ext -eq ".gguf") {
            $resolvedType = "GGUF"
        } else {
            $resolvedType = "Unknown"
        }
    }

    $bytes = New-Object byte[] 4
    try {
        $stream = [System.IO.File]::OpenRead($FilePath)
        $readCount = $stream.Read($bytes, 0, 4)
        $stream.Close()

        if ($readCount -lt 4) {
            return [PSCustomObject]@{
                IsValid      = $false
                DetectedType = "Truncated"
                MagicString  = ""
                ErrorMessage = "File has fewer than 4 bytes"
            }
        }
    } catch {
        return [PSCustomObject]@{
            IsValid      = $false
            DetectedType = "Error"
            MagicString  = ""
            ErrorMessage = $_.Exception.Message
        }
    }

    # ZIM magic check: 0x5A 0x49 0x4D 0x04 ('ZIM\x04')
    $isZim = ($bytes[0] -eq 0x5A -and $bytes[1] -eq 0x49 -and $bytes[2] -eq 0x4D -and $bytes[3] -eq 0x04)

    # GGUF magic check: 0x47 0x47 0x55 0x46 ('GGUF')
    $isGguf = ($bytes[0] -eq 0x47 -and $bytes[1] -eq 0x47 -and $bytes[2] -eq 0x55 -and $bytes[3] -eq 0x46)

    $detected = if ($isZim) { "ZIM\x04" } elseif ($isGguf) { "GGUF" } else { "Unknown" }
    $hex = ($bytes | ForEach-Object { "{0:X2}" -f $_ }) -join " "

    $isValid = switch ($resolvedType) {
        "ZIM"  { $isZim }
        "GGUF" { $isGguf }
        default { $isZim -or $isGguf }
    }

    return [PSCustomObject]@{
        IsValid      = $isValid
        ExpectedType = $resolvedType
        DetectedType = $detected
        MagicHex     = $hex
        MagicString  = if ($isGguf) { "GGUF" } elseif ($isZim) { "ZIM\x04" } else { $hex }
        ErrorMessage = if (-not $isValid) { "Expected $resolvedType header, found $detected ($hex)" } else { "" }
    }
}

function Find-AssetInCache {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$FileName,

        [Parameter(Mandatory = $false)]
        [string[]]$CustomCacheDirs = @()
    )

    $searchLocations = @()
    if ($CustomCacheDirs) {
        $searchLocations += $CustomCacheDirs
    }
    $searchLocations += $script:DefaultCacheLocations

    foreach ($loc in $searchLocations) {
        if (-not (Test-Path $loc)) { continue }

        # Check direct path
        $candidate = Join-Path $loc $FileName
        if (Test-Path $candidate) {
            $magic = Test-AssetMagicHeader -FilePath $candidate
            if ($magic.IsValid) {
                return (Get-Item $candidate)
            }
        }

        # Check subdirectories (zim/, models/)
        $subdirs = @("zim", "models", "content")
        foreach ($sub in $subdirs) {
            $candidateSub = Join-Path (Join-Path $loc $sub) $FileName
            if (Test-Path $candidateSub) {
                $magic = Test-AssetMagicHeader -FilePath $candidateSub
                if ($magic.IsValid) {
                    return (Get-Item $candidateSub)
                }
            }
        }
    }

    return $null
}

function Get-ProductAssetInventory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProductSku,

        [Parameter(Mandatory = $false)]
        [string]$ProductsJsonPath = "",

        [Parameter(Mandatory = $false)]
        [string[]]$CustomCacheDirs = @(),

        [Parameter(Mandatory = $false)]
        [ValidateSet("Auto", "lean", "full")]
        [string]$Profile = "Auto"
    )

    if (-not $ProductsJsonPath) {
        $manifestCandidate = "C:\Users\ndoki\Desktop\offgridusb\OffGridUSB\manifests\products.json"
        if (Test-Path $manifestCandidate) {
            $ProductsJsonPath = $manifestCandidate
        }
    }

    if (-not (Test-Path $ProductsJsonPath)) {
        throw "products.json not found at: $ProductsJsonPath"
    }

    $json = Get-Content -Raw -Path $ProductsJsonPath | ConvertFrom-Json
    $matchedProduct = $null
    foreach ($p in $json.products) {
        if ($p.sku -eq $ProductSku -or $p.product_id -eq $ProductSku -or $p.name -like "*$ProductSku*") {
            $matchedProduct = $p
            break
        }
    }

    if (-not $matchedProduct) {
        throw "Product SKU '$ProductSku' not found in $ProductsJsonPath"
    }

    # Resolve payload profile
    $chosenProfileName = $Profile
    if ($chosenProfileName -eq "Auto") {
        if ($matchedProduct.payload_profiles.PSObject.Properties["lean"]) {
            $chosenProfileName = "lean"
        } else {
            $chosenProfileName = "full"
        }
    }

    $profileObj = $matchedProduct.payload_profiles.$chosenProfileName
    if (-not $profileObj) {
        $chosenProfileName = "full"
        $profileObj = $matchedProduct.payload_profiles.full
    }

    $items = @()
    $allPresent = $true
    $totalStagedBytes = 0L

    # Models
    if ($profileObj.models) {
        foreach ($m in $profileObj.models) {
            $found = Find-AssetInCache -FileName $m -CustomCacheDirs $CustomCacheDirs
            if ($found) {
                $items += [PSCustomObject]@{
                    FileName     = $m
                    Type         = "Model (GGUF)"
                    SizeBytes    = $found.Length
                    SizeMB       = [math]::Round($found.Length / 1MB, 1)
                    Status       = "AVAILABLE"
                    Magic        = "GGUF"
                    LocalPath    = $found.FullName
                }
                $totalStagedBytes += $found.Length
            } else {
                $allPresent = $false
                $items += [PSCustomObject]@{
                    FileName     = $m
                    Type         = "Model (GGUF)"
                    SizeBytes    = 0L
                    SizeMB       = 0.0
                    Status       = "MISSING"
                    Magic        = "None"
                    LocalPath    = ""
                }
            }
        }
    }

    # ZIM Archives
    if ($profileObj.zim_archives) {
        foreach ($z in $profileObj.zim_archives) {
            $found = Find-AssetInCache -FileName $z -CustomCacheDirs $CustomCacheDirs
            if ($found) {
                $items += [PSCustomObject]@{
                    FileName     = $z
                    Type         = "ZIM Archive"
                    SizeBytes    = $found.Length
                    SizeMB       = [math]::Round($found.Length / 1MB, 1)
                    Status       = "AVAILABLE"
                    Magic        = "ZIM\x04"
                    LocalPath    = $found.FullName
                }
                $totalStagedBytes += $found.Length
            } else {
                $allPresent = $false
                $items += [PSCustomObject]@{
                    FileName     = $z
                    Type         = "ZIM Archive"
                    SizeBytes    = 0L
                    SizeMB       = 0.0
                    Status       = "MISSING"
                    Magic        = "None"
                    LocalPath    = ""
                }
            }
        }
    }

    return [PSCustomObject]@{
        ProductSku           = $matchedProduct.sku
        ProductName          = $matchedProduct.name
        ProfileName          = $chosenProfileName
        ProfileDescription   = $profileObj.description
        AllRequiredAvailable = $allPresent
        TotalStagedBytes     = $totalStagedBytes
        TotalStagedGB        = [math]::Round($totalStagedBytes / 1e9, 2)
        TotalStagedGiB       = [math]::Round($totalStagedBytes / 1GB, 2)
        TargetDriveSizeGB    = $matchedProduct.target_drive_size_gb
        Assets               = $items
    }
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function Test-AssetMagicHeader, Find-AssetInCache, Get-ProductAssetInventory -ErrorAction SilentlyContinue
}
