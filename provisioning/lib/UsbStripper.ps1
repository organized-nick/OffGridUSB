<#
.SYNOPSIS
    UsbStripper - Whitelist-only staging engine and customer USB hygiene verification.

.DESCRIPTION
    Ensures that customer USB drives contain strictly runtime files and ZERO
    developer documentation, build scripts, formatting utilities, or cloning tools.
#>

[CmdletBinding()]
param()

$script:ForbiddenDirectories = @(
    "provisioning",
    "scripts",
    "docs",
    "tests",
    "tmp_dl",
    ".git",
    ".github",
    ".agents",
    ".venv",
    ".pytest_cache",
    "__pycache__"
)

$script:ForbiddenRootFiles = @(
    "CONTRIBUTING.md",
    "TEST_READY.md",
    "PITCH_CHEATSHEET.md",
    "README.md",
    "DOWNLOAD_INTERNET_IN_A_BOX.bat",
    "FORMAT_AND_SETUP_USB.bat",
    "MAKE_USB_DRIVES.bat",
    "START_EMYRGE_WINDOWS.bat",
    "START_EMYRGE_LINUX.sh",
    "START_EMYRGE_MAC.command",
    "audit_offgrid_usb.py",
    "fetch_assets.py"
)

$script:ForbiddenPatterns = @(
    "*download*",
    "*format*",
    "*make_usb*",
    "*clone*",
    "*provision*",
    "fetch_assets*",
    "*.pyc",
    "*.pyo",
    ".DS_Store"
)

$script:MandatoryCustomerFiles = @(
    "START_OFFGRIDUSB_WINDOWS.bat",
    "START_OFFGRIDUSB_LINUX.sh",
    "START_OFFGRIDUSB_MAC.command",
    "USER_GUIDE.md",
    "manifests\product_sku.json"
)

function Get-WhitelistedStagingPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,

        [Parameter(Mandatory = $true)]
        [string]$ProductSku,

        [Parameter(Mandatory = $false)]
        [string]$TargetDriveLetter = "D:",

        [Parameter(Mandatory = $false)]
        [string]$CustomCacheDir = "",

        [Parameter(Mandatory = $false)]
        [string]$ProfileName = "Auto"
    )

    $cleanDrive = ($TargetDriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $targetRoot = "${cleanDrive}:\"

    # Resolve active asset inventory
    $inventoryModule = Join-Path $PSScriptRoot "AssetCacheManager.ps1"
    if (Test-Path $inventoryModule) {
        . $inventoryModule
    }

    $productsJson = Join-Path $SourceRoot "manifests\products.json"
    $inv = Get-ProductAssetInventory -ProductSku $ProductSku -ProductsJsonPath $productsJson -CustomCacheDirs @($CustomCacheDir) -Profile $ProfileName

    $stagedItems = @()

    # 1. Root Launchers & Docs
    $rootFiles = @(
        "START_OFFGRIDUSB_WINDOWS.bat",
        "START_OFFGRIDUSB_LINUX.sh",
        "START_OFFGRIDUSB_MAC.command",
        "run_windows.bat",
        "run_linux.sh",
        "run_macos.command",
        "USER_GUIDE.md"
    )

    foreach ($rf in $rootFiles) {
        $srcPath = Join-Path $SourceRoot $rf
        if (Test-Path $srcPath) {
            $fi = Get-Item $srcPath
            $stagedItems += [PSCustomObject]@{
                RelativePath = $rf
                SourcePath   = $fi.FullName
                TargetPath   = Join-Path $targetRoot $rf
                SizeBytes    = $fi.Length
                Category     = "Root Launcher/Doc"
            }
        }
    }

    # 2. Runtime Directories (bin, src, web, manifests)
    $runtimeDirs = @("bin", "src", "web", "manifests")
    foreach ($rd in $runtimeDirs) {
        $dirPath = Join-Path $SourceRoot $rd
        if (Test-Path $dirPath) {
            Get-ChildItem -Path $dirPath -Recurse -File | ForEach-Object {
                $file = $_
                $rel = $file.FullName.Substring($SourceRoot.Length).TrimStart("\", "/")

                # Deny checks
                if ($rel -like "*fetch_assets.py*" -or
                    $rel -like "*__pycache__*" -or
                    $rel -like "*.pyc" -or
                    $rel -like "*.pyo" -or
                    $rel -like "*.DS_Store*") {
                    return
                }

                $stagedItems += [PSCustomObject]@{
                    RelativePath = $rel
                    SourcePath   = $file.FullName
                    TargetPath   = Join-Path $targetRoot $rel
                    SizeBytes    = $file.Length
                    Category     = "Runtime ($rd)"
                }
            }
        }
    }

    # 3. Dynamic product_sku.json
    $stagedItems += [PSCustomObject]@{
        RelativePath = "manifests\product_sku.json"
        SourcePath   = "[Dynamically Generated]"
        TargetPath   = Join-Path $targetRoot "manifests\product_sku.json"
        SizeBytes    = 1500L
        Category     = "Manifest"
    }

    # 4. Dynamic library.xml
    $stagedItems += [PSCustomObject]@{
        RelativePath = "data\library.xml"
        SourcePath   = "[Dynamically Generated]"
        TargetPath   = Join-Path $targetRoot "data\library.xml"
        SizeBytes    = 18000L
        Category     = "Library Metadata"
    }

    # 5. Selected SKU Models and ZIMs
    foreach ($a in $inv.Assets) {
        $destSub = if ($a.Type -like "*ZIM*") { "data\zim\" } else { "data\models\" }
        $rel = Join-Path $destSub $a.FileName
        if ($a.Status -eq "AVAILABLE" -and $a.LocalPath) {
            $fi = Get-Item $a.LocalPath
            $stagedItems += [PSCustomObject]@{
                RelativePath = $rel
                SourcePath   = $fi.FullName
                TargetPath   = Join-Path $targetRoot $rel
                SizeBytes    = $fi.Length
                Category     = $a.Type
            }
        } else {
            $stagedItems += [PSCustomObject]@{
                RelativePath = $rel
                SourcePath   = ""
                TargetPath   = Join-Path $targetRoot $rel
                SizeBytes    = $a.SizeBytes
                Category     = "$($a.Type) [MISSING]"
            }
        }
    }

    # 6. Initialize empty data/vault and data/uploads dirs
    $stagedItems += [PSCustomObject]@{
        RelativePath = "data\vault\"
        SourcePath   = "[Directory Placeholder]"
        TargetPath   = Join-Path $targetRoot "data\vault\"
        SizeBytes    = 0L
        Category     = "Data Directory"
    }
    $stagedItems += [PSCustomObject]@{
        RelativePath = "data\uploads\"
        SourcePath   = "[Directory Placeholder]"
        TargetPath   = Join-Path $targetRoot "data\uploads\"
        SizeBytes    = 0L
        Category     = "Data Directory"
    }

    $totalBytes = 0L
    foreach ($item in $stagedItems) {
        $totalBytes += $item.SizeBytes
    }

    return [PSCustomObject]@{
        ProductSku       = $ProductSku
        TargetDrive      = $cleanDrive
        TotalFiles       = $stagedItems.Count
        TotalStagedBytes = $totalBytes
        TotalStagedGB    = [math]::Round($totalBytes / 1e9, 2)
        TotalStagedGiB   = [math]::Round($totalBytes / 1GB, 2)
        Items            = $stagedItems
    }
}

function Enforce-LfLineEndings {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetRoot
    )

    $shellScripts = Get-ChildItem -Path $TargetRoot -Include "*.sh", "*.command" -Recurse -File -ErrorAction SilentlyContinue
    $fixedCount = 0

    foreach ($file in $shellScripts) {
        $raw = [System.IO.File]::ReadAllBytes($file.FullName)
        if ($raw -contains 13) { # 0x0D carriage return found
            $text = [System.Text.Encoding]::UTF8.GetString($raw)
            $lfText = $text -replace "`r`n", "`n" -replace "`r", "`n"
            [System.IO.File]::WriteAllBytes($file.FullName, [System.Text.Encoding]::UTF8.GetBytes($lfText))
            $fixedCount++
        }
    }

    return $fixedCount
}

function Assert-CustomerUsbHygiene {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetDrive
    )

    $clean = ($TargetDrive.Trim().ToUpper() -replace "[:\\/\s]", "")
    $root = "${clean}:\"
    $violations = @()

    if (-not (Test-Path $root)) {
        throw "Target drive '${clean}:\' does not exist or is not accessible!"
    }

    # 1. Assert forbidden directories do not exist
    foreach ($d in $script:ForbiddenDirectories) {
        $chk = Join-Path $root $d
        if (Test-Path $chk) {
            $violations += "Forbidden directory found on customer USB: $d"
        }
    }

    # 2. Assert forbidden root files do not exist
    foreach ($f in $script:ForbiddenRootFiles) {
        $chk = Join-Path $root $f
        if (Test-Path $chk) {
            $violations += "Forbidden root file found on customer USB: $f"
        }
    }

    # 3. Assert wildcard patterns do not match any file
    $allFiles = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue
    foreach ($file in $allFiles) {
        $name = $file.Name.ToLowerInvariant()
        foreach ($pat in $script:ForbiddenPatterns) {
            $wildcard = $pat.ToLowerInvariant()
            if ($name -like $wildcard) {
                # Allow .py files that are part of application runtime (not fetch_assets)
                if ($name -eq "fetch_assets.py" -or $name -notlike "*.py") {
                    $violations += "Forbidden file matching hygiene pattern '$pat': $($file.FullName)"
                }
            }
        }
    }

    # 4. Assert mandatory customer files DO exist
    foreach ($req in $script:MandatoryCustomerFiles) {
        $chk = Join-Path $root $req
        if (-not (Test-Path $chk)) {
            $violations += "Missing mandatory customer file: $req"
        }
    }

    # 5. Assert strict LF line endings on shell scripts
    foreach ($sh in @("START_OFFGRIDUSB_LINUX.sh", "START_OFFGRIDUSB_MAC.command", "run_linux.sh", "run_macos.command")) {
        $p = Join-Path $root $sh
        if (Test-Path $p) {
            $bytes = [System.IO.File]::ReadAllBytes($p)
            if ($bytes -contains 13) {
                $violations += "Carriage return (0x0D) detected in POSIX launcher: $sh (Must be strict LF)"
            }
        }
    }

    if ($violations.Count -gt 0) {
        $errMsg = "CUSTOMER USB HYGIENE AUDIT FAILED with $($violations.Count) violation(s):`n"
        $errMsg += ($violations -join "`n")
        throw $errMsg
    }

    return [PSCustomObject]@{
        TargetDrive = $clean
        Passed      = $true
        CheckedRoot = $root
    }
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function Get-WhitelistedStagingPlan, Enforce-LfLineEndings, Assert-CustomerUsbHygiene -ErrorAction SilentlyContinue
}
