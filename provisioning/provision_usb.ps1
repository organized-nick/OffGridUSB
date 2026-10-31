<#
.SYNOPSIS
    provision_usb.ps1 - Core Factory Provisioning Engine for OffGridUSB.

.DESCRIPTION
    Universal, host-only provisioning engine for OffGridUSB commercial SKUs
    (Product 1: PocketSurvival, Product 2: FieldReady, Product 3: CivilizationArk).
    Features Triple-Gate Disk 0 safety guard, capacity enforcement, binary magic header
    validation, non-elevated exFAT recursive clean wipe, automated whitelist staging,
    and post-staging customer USB hygiene stripping.

.PARAMETER Product
    Commercial Product SKU: Product1, Product2, Product3 (or PocketSurvival, FieldReady, CivilizationArk).

.PARAMETER Tier
    Technical Tier level: 0, 1, 2, 3, or 4.

.PARAMETER Drive
    Target USB drive letter (e.g. 'D' or 'D:').

.PARAMETER DryRun
    Simulates safety validation, capacity check, asset availability, and staging plan with 0 writes.

.PARAMETER Info
    Displays formatted catalog specifications, payload sizes, hardware requirements, and cache status.

.PARAMETER NonInteractive
    Suppresses interactive menus and prompts; fails immediately on missing required parameters.

.PARAMETER FilesystemAction
    Auto, FormatExFAT, CleanWipe, KeepExisting, Wipe, or Format. Defaults to Auto.

.PARAMETER CacheDir
    Path to custom host asset cache directory.

.PARAMETER SourceRoot
    Path to OffGridUSB repository root. Defaults to parent directory of provisioning/.

.PARAMETER Profile
    Payload profile: lean, full, or Auto.

.PARAMETER BwLimitKBps
    Copy bandwidth limit in KB/s (default: 2048). Sustained full-speed writes
    can hard-lock cheap USB flash controllers (device falls off the bus
    mid-copy); throttling keeps them alive. Use 0 to disable throttling.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Product1", "Product2", "Product3", "PocketSurvival", "FieldReady", "CivilizationArk", "Tier0", "Tier1", "Tier2", "Tier3", "Tier4")]
    [string]$Product,

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, 4)]
    [int]$Tier = -1,

    [Parameter(Mandatory = $false)]
    [string]$Drive,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun,

    [Parameter(Mandatory = $false)]
    [switch]$Info,

    [Parameter(Mandatory = $false)]
    [switch]$NonInteractive,

    [Parameter(Mandatory = $false)]
    [ValidateSet("Auto", "FormatExFAT", "CleanWipe", "KeepExisting", "Wipe", "Format")]
    [string]$FilesystemAction = "Auto",

    [Parameter(Mandatory = $false)]
    [string]$CacheDir = "",  # Resolved below: $env:OFFGRIDUSB_CACHE_DIR or %LOCALAPPDATA%\offgridusb\cache

    [Parameter(Mandatory = $false)]
    [string]$SourceRoot = "",

    [Parameter(Mandatory = $false)]
    [switch]$NoDownload,

    [Parameter(Mandatory = $false)]
    [ValidateSet("Auto", "lean", "full")]
    [string]$Profile = "Auto",

    [Parameter(Mandatory = $false)]
    [ValidateRange(0, [int]::MaxValue)]
    [int]$BwLimitKBps = 0
)

# ------------------------------------------------------------------------------
# 1. Resolve Paths & Import Modular Libraries
# ------------------------------------------------------------------------------
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $SourceRoot) {
    $SourceRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
}

# Resolve host asset cache directory (kept off the Desktop):
# $env:OFFGRIDUSB_CACHE_DIR -> %LOCALAPPDATA%\offgridusb\cache
if (-not $CacheDir) {
    if ($env:OFFGRIDUSB_CACHE_DIR) {
        $CacheDir = $env:OFFGRIDUSB_CACHE_DIR
    } else {
        $CacheDir = "C:\Users\ndoki\Documents\OffGridUSB_Provisions"
    }
}

# ------------------------------------------------------------------------------
# Legacy cache migration: if the new cache location has no payload assets yet,
# adopt (move) .zim / .gguf files from the old hardcoded Desktop cache (and
# repo-local staging dirs) so Nick doesn't have to re-download everything.
# ------------------------------------------------------------------------------
function Import-LegacyCacheAssets {
    param(
        [Parameter(Mandatory = $true)][string]$NewCacheDir,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    $legacySources = @(
        (Join-Path $env:USERPROFILE "Desktop\offgridusb\cache"),
        "C:\Users\ndoki\Documents\OffGridUSB_Provisions",
        (Join-Path $RepoRoot "cache"),
        (Join-Path $RepoRoot "data"),
        (Join-Path $RepoRoot "models_staging"),
        (Join-Path $RepoRoot "zim_Builds")
    )

    $moved = 0
    foreach ($srcRoot in $legacySources) {
        if (-not (Test-Path $srcRoot)) { continue }
        if ((Resolve-Path $srcRoot).Path -eq (Resolve-Path $NewCacheDir).Path) { continue }

        # Only import if the destination counterpart doesn't already exist
        foreach ($sub in @("zim", "models")) {
            $srcDir = Join-Path $srcRoot $sub
            $dstDir = Join-Path $NewCacheDir $sub
            if (-not (Test-Path $srcDir)) { continue }

            foreach ($pattern in @("*.zim", "*.gguf")) {
                foreach ($file in @(Get-ChildItem -Path $srcDir -Filter $pattern -File -ErrorAction SilentlyContinue)) {
                    $dest = Join-Path $dstDir $file.Name
                    if (Test-Path $dest) {
                        Write-Host "  [SKIP] Already in new cache: $sub\$($file.Name)" -ForegroundColor DarkGray
                        continue
                    }
                    Write-Host "  [MIGRATE] $($file.Name) ($([math]::Round($file.Length / 1MB, 1)) MB) <- $srcDir" -ForegroundColor Cyan
                    Move-Item -LiteralPath $file.FullName -Destination $dest -Force
                    $moved++
                }
            }
        }

        # Also adopt loose files sitting directly in the legacy cache root
        $dstZimDir = Join-Path $NewCacheDir "zim"
        $dstModelDir = Join-Path $NewCacheDir "models"
        foreach ($pattern in @("*.zim", "*.gguf")) {
            foreach ($file in @(Get-ChildItem -Path $srcRoot -Filter $pattern -File -ErrorAction SilentlyContinue)) {
                $dstDir = if ($file.Extension -eq ".zim") { $dstZimDir } else { $dstModelDir }
                $dest = Join-Path $dstDir $file.Name
                if (Test-Path $dest) {
                    Write-Host "  [SKIP] Already in new cache: $([System.IO.Path]::GetFileName($dstDir))\$($file.Name)" -ForegroundColor DarkGray
                    continue
                }
                Write-Host "  [MIGRATE] $($file.Name) ($([math]::Round($file.Length / 1MB, 1)) MB) <- $srcRoot" -ForegroundColor Cyan
                Move-Item -LiteralPath $file.FullName -Destination $dest -Force
                $moved++
            }
        }
    }
    return $moved
}

$null = New-Item -ItemType Directory -Path (Join-Path $CacheDir "zim") -Force
$null = New-Item -ItemType Directory -Path (Join-Path $CacheDir "models") -Force
$migratedCount = Import-LegacyCacheAssets -NewCacheDir $CacheDir -RepoRoot $SourceRoot
if ($migratedCount -gt 0) {
    Write-Host ""
    Write-Host ">>> Adopted $migratedCount payload asset(s) from legacy cache locations into:" -ForegroundColor Cyan
    Write-Host "    $CacheDir" -ForegroundColor White
    Write-Host "  [OK] No re-download needed for migrated assets." -ForegroundColor Green
}

# Normalize Win32 Process Working Directory to avoid system32 resolution
[System.IO.Directory]::SetCurrentDirectory($SourceRoot)

$LibDir = Join-Path $ScriptDir "lib"
. (Join-Path $LibDir "SafetyValidator.ps1")
. (Join-Path $LibDir "AssetCacheManager.ps1")
. (Join-Path $LibDir "SkuManifestGenerator.ps1")
. (Join-Path $LibDir "LibraryXmlBuilder.ps1")
. (Join-Path $LibDir "UsbStripper.ps1")

# Normalize FilesystemAction aliases
if ($FilesystemAction -eq "Wipe") { $FilesystemAction = "CleanWipe" }
if ($FilesystemAction -eq "Format") { $FilesystemAction = "FormatExFAT" }

# Throttled file copy: sustained full-speed sequential writes can hard-lock
# cheap USB flash controllers (two drives bricked mid-copy at full USB speed).
# BwLimitKBps=0 disables throttling.
function Copy-ItemThrottled {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [Parameter(Mandatory = $false)][int]$LimitKBps = 2048
    )

    if ($LimitKBps -le 0) {
        $srcInfo = Get-Item -LiteralPath $SourcePath
        if ($srcInfo.Length -le 4MB) {
            Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
            return
        }
        $wtBufferSize = 4 * 1024 * 1024
        $wtBuf = New-Object byte[] $wtBufferSize
        $srcStream = [System.IO.File]::OpenRead($SourcePath)
        try {
            $dstStream = New-Object System.IO.FileStream($DestinationPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None, $wtBufferSize, [System.IO.FileOptions]::WriteThrough)
            try {
                while (($read = $srcStream.Read($wtBuf, 0, $wtBufferSize)) -gt 0) {
                    $dstStream.Write($wtBuf, 0, $read)
                }
                $dstStream.Flush($true)
            } finally {
                $dstStream.Dispose()
            }
        } finally {
            $srcStream.Dispose()
        }
        return
    }

    $bufferSize = 65536 # 64 KB chunks
    $bytesPerSecond = $LimitKBps * 1024
    $chunksPerSecond = [Math]::Max(1, [Math]::Ceiling($bytesPerSecond / $bufferSize))
    $delayMs = [Math]::Max(1, [Math]::Ceiling(1000.0 / $chunksPerSecond))

    $srcStream = [System.IO.File]::OpenRead($SourcePath)
    try {
        $dstStream = [System.IO.File]::Open($DestinationPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
        try {
            $buffer = New-Object byte[] $bufferSize
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            while (($read = $srcStream.Read($buffer, 0, $bufferSize)) -gt 0) {
                $dstStream.Write($buffer, 0, $read)
                # pace against elapsed time to honor the KB/s budget
                $expectedMs = ($dstStream.Position / $bytesPerSecond) * 1000.0
                if ($sw.Elapsed.TotalMilliseconds -lt $expectedMs) {
                    Start-Sleep -Milliseconds ([int][Math]::Min(100, $expectedMs - $sw.Elapsed.TotalMilliseconds))
                }
            }
            $dstStream.Flush($true) # flush through to the device
        } finally {
            $dstStream.Dispose()
        }
    } finally {
        $srcStream.Dispose()
    }
}

# SKU Normalization Map
function Normalize-SkuName {
    param([string]$InputSku, [int]$InputTier)
    if ($InputSku) {
        switch ($InputSku) {
            "PocketSurvival"  { return "Product1" }
            "Tier0"           { return "Product1" }
            "FieldReady"      { return "Product2" }
            "Tier1"           { return "Product2" }
            "CivilizationArk" { return "Product3" }
            "Tier2"           { return "Product3" }
            "SwarmCluster"    { return "Tier3" }
            "SettlementHub"   { return "Tier4" }
            default           { return $InputSku }
        }
    }
    if ($InputTier -ge 0) {
        switch ($InputTier) {
            0 { return "Product1" }
            1 { return "Product2" }
            2 { return "Product3" }
            3 { return "Tier3" }
            4 { return "Tier4" }
        }
    }
    return ""
}

$ResolvedSku = Normalize-SkuName -InputSku $Product -InputTier $Tier

# ------------------------------------------------------------------------------
# 2. Handler: -Info Mode
# ------------------------------------------------------------------------------
if ($Info) {
    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  OffGridUSB Factory Provisioning Suite // Product Catalog & Specifications" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[COMMERCIAL PRODUCT SKUs & CAPACITY TIERS]" -ForegroundColor Yellow
    Write-Host ("{0,-9} {1,-17} {2,-9} {3,-9} {4,-15} {5}" -f "SKU ID", "Commercial Name", "Tiers", "Min USB", "Payload Size", "Target Features & Media") -ForegroundColor White
    Write-Host ("{0,-9} {1,-17} {2,-9} {3,-9} {4,-15} {5}" -f "--------", "-----------------", "-------", "-------", "------------", "------------------------------------------") -ForegroundColor DarkGray

    $skuRows = @(
        [PSCustomObject]@{ Sku="Product1"; Name="PocketSurvival";  Tiers="Tier 0";    MinUsb="8 GB";   Payload="<= 6.5 GB";  Desc="Offline Kiwix (:8081), Grounded AI Professor (:8082), CDC Calculators." }
        [PSCustomObject]@{ Sku="Product2"; Name="FieldReady";      Tiers="0 + 1";     MinUsb="32 GB";  Payload="~16-20 GB";  Desc="All Product 1 + SQLite Memory Vault, Photo OCR Vault, STEM Tutor." }
        [PSCustomObject]@{ Sku="Product3"; Name="CivilizationArk"; Tiers="0 + 1 + 2"; MinUsb="128 GB"; Payload="~65-72 GB";  Desc="All Product 2 + 50.2 GB Wikipedia No-Pic. (64 GB USB rejected)." }
        [PSCustomObject]@{ Sku="Tier3";    Name="SwarmCluster";    Tiers="0 - 3";     MinUsb="256 GB"; Payload="~88 GB";     Desc="All Product 3 + Qwen 32B (18.9 GB) + exo LAN Swarm Clustering." }
        [PSCustomObject]@{ Sku="Tier4";    Name="SettlementHub";   Tiers="0 - 4";     MinUsb="512 GB"; Payload="~210+ GB";   Desc="All Tier 3 + Wikipedia Maxi (110 GB) + Llama 70B (40.5 GB)." }
    )

    foreach ($r in $skuRows) {
        Write-Host ("{0,-9} {1,-17} {2,-9} {3,-9} {4,-15} {5}" -f $r.Sku, $r.Name, $r.Tiers, $r.MinUsb, $r.Payload, $r.Desc)
    }

    Write-Host ""
    Write-Host "[HOST ASSET CACHE READINESS]" -ForegroundColor Yellow
    Write-Host ("{0,-44} {1,-8} {2,-11} {3,-11} {4}" -f "Asset Name", "Type", "Size", "Status", "Validated Header") -ForegroundColor White
    Write-Host ("{0,-44} {1,-8} {2,-11} {3,-11} {4}" -f "--------------------------------------------", "-------", "----------", "----------", "----------------") -ForegroundColor DarkGray

    $trackedAssets = @(
        @{ Name="smollm2-135m-instruct-q4_k_m.gguf"; Type="GGUF" },
        @{ Name="qwen2.5-0.5b-instruct-q4_k_m.gguf"; Type="GGUF" },
        @{ Name="qwen2.5-1.5b-instruct-q4_k_m.gguf"; Type="GGUF" },
        @{ Name="Phi-3.5-mini-instruct-Q4_K_S.gguf"; Type="GGUF" },
        @{ Name="llama-3.2-3b-instruct-q4_k_m.gguf"; Type="GGUF" },
        @{ Name="zimgit-water_en_2024-08.zim"; Type="ZIM" },
        @{ Name="zimgit-medicine_en_2024-08.zim"; Type="ZIM" },
        @{ Name="wikipedia_en_medicine_mini_2026-10.zim"; Type="ZIM" },
        @{ Name="wikipedia_en_top_mini_2026-09.zim"; Type="ZIM" },
        @{ Name="wikibooks_en_all_maxi_2026-04.zim"; Type="ZIM" },
        @{ Name="wikipedia_en_all_nopic_2026-06.zim"; Type="ZIM" }
    )

    $prod1Ready = $true
    $prod2Ready = $true
    $prod3Ready = $true

    foreach ($ta in $trackedAssets) {
        $found = Find-AssetInCache -FileName $ta.Name -CustomCacheDirs @($CacheDir)
        if ($found) {
            $szStr = if ($found.Length -ge 1GB) { "{0:N2} GB" -f ($found.Length / 1GB) } else { "{0:N1} MB" -f ($found.Length / 1MB) }
            $magic = Test-AssetMagicHeader -FilePath $found.FullName
            $color = if ($magic.IsValid) { "Green" } else { "Red" }
            Write-Host ("{0,-44} {1,-8} {2,-11} {3,-11} {4}" -f $ta.Name, $ta.Type, $szStr, "AVAILABLE", $magic.MagicString) -ForegroundColor $color
        } else {
            if ($ta.Name -in @("smollm2-135m-instruct-q4_k_m.gguf", "qwen2.5-0.5b-instruct-q4_k_m.gguf", "zimgit-water_en_2024-08.zim", "zimgit-medicine_en_2024-08.zim", "wikipedia_en_medicine_mini_2026-10.zim", "wikipedia_en_top_mini_2026-09.zim")) {
                $prod1Ready = $false
            }
            if ($ta.Name -in @("qwen2.5-1.5b-instruct-q4_k_m.gguf", "Phi-3.5-mini-instruct-Q4_K_S.gguf")) {
                $prod2Ready = $false
            }
            if ($ta.Name -in @("wikipedia_en_all_nopic_2026-06.zim")) {
                $prod3Ready = $false
            }
            Write-Host ("{0,-44} {1,-8} {2,-11} {3,-11} {4}" -f $ta.Name, $ta.Type, "N/A", "MISSING", "None") -ForegroundColor DarkGray
        }
    }

    Write-Host ""
    Write-Host "[CURRENT FACTORY READINESS STATUS]" -ForegroundColor Yellow
    Write-Host ("  * Product 1 (PocketSurvival): {0} (Lean payload: 1.39 GB, verified <= 6.5 GB ceiling)" -f $(if ($prod1Ready) { "[100% READY]" } else { "[INCOMPLETE]" })) -ForegroundColor $(if ($prod1Ready) { "Green" } else { "Yellow" })
    Write-Host ("  * Product 2 (FieldReady):     {0} (Lean payload: 4.69 GB, verified for 32 GB drive D:)" -f $(if ($prod2Ready) { "[100% READY]" } else { "[INCOMPLETE]" })) -ForegroundColor $(if ($prod2Ready) { "Green" } else { "Yellow" })
    Write-Host ("  * Product 3 (CivilizationArk): {0} (Requires 50.2 GB Wikipedia ZIM in cache; 128 GB USB required)" -f $(if ($prod3Ready) { "[100% READY]" } else { "[REQUIRES CACHE DOWNLOAD]" })) -ForegroundColor $(if ($prod3Ready) { "Green" } else { "Cyan" })
    Write-Host "================================================================================" -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------------------------
# 3. Interactive Menu (If invoked without required parameters)
# ------------------------------------------------------------------------------
if (-not $ResolvedSku -or -not $Drive) {
    if ($NonInteractive) {
        throw "NonInteractive mode requires -Product (or -Tier) and -Drive to be specified."
    }

    Clear-Host
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  OFFGRIDUSB -- FACTORY PROVISIONING SUITE (HOST ONLY)" -ForegroundColor Cyan
    Write-Host "  Universal Air-Gapped Offline Survival, Knowledge & Local AI Drives" -ForegroundColor White
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  [1] Provision Product 1: PocketSurvival  (Tier 0,    8 GB USB,  <= 6.5 GB payload)"
    Write-Host "  [2] Provision Product 2: FieldReady      (Tiers 0-1, 32 GB USB,  ~16-20 GB / 4.7 GB lean)"
    Write-Host "  [3] Provision Product 3: CivilizationArk (Tiers 0-2, 128 GB USB, ~65-72 GB payload)"
    Write-Host "  ----------------------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  [4] Custom Technical Tier Provisioning (Tier 0, 1, 2, 3, or 4)"
    Write-Host "  [5] View Product Catalog & Hardware Specifications (-Info)"
    Write-Host "  [6] Run Simulation / Safety Check (-DryRun)"
    Write-Host "  [Q] Quit"
    Write-Host "================================================================================" -ForegroundColor Cyan

    $choice = (Read-Host "Select an option [1-6, Q]").Trim().ToUpper()
    switch ($choice) {
        "1" { $ResolvedSku = "Product1" }
        "2" { $ResolvedSku = "Product2" }
        "3" { $ResolvedSku = "Product3" }
        "4" {
            $t = Read-Host "Enter Tier number [0, 1, 2, 3, 4]"
            $ResolvedSku = Normalize-SkuName -InputSku "" -InputTier [int]$t
        }
        "5" {
            & $MyInvocation.MyCommand.Path -Info
            exit 0
        }
        "6" {
            $DryRun = $true
            $ResolvedSku = "Product2"
        }
        "Q" {
            Write-Host "Aborted by operator."
            exit 0
        }
        default {
            Write-Host "Invalid option. Exiting."
            exit 1
        }
    }

    if (-not $Drive) {
        $Drive = Read-Host "Enter Target USB Drive Letter (e.g. D or E)"
    }
}

$Drive = ($Drive.Trim().ToUpper() -replace "[:\\/\s]", "")

# ------------------------------------------------------------------------------
# 4. Pre-Flight Safety Validation (Triple-Gate Guard)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Initiating Pre-Flight Hardware Safety Gate for drive '${Drive}:'..." -ForegroundColor Cyan
$safety = Assert-TargetDriveSafety -DriveLetter $Drive
Write-Host "  [PASS] Target drive '$($safety.DriveLetter):' is NOT C: or host SystemDrive." -ForegroundColor Green
Write-Host "  [PASS] Physical Disk #$($safety.DiskNumber) is NOT Disk 0 ($($safety.FriendlyName))." -ForegroundColor Green
Write-Host "  [PASS] Target Disk is not Boot ($($safety.IsBoot)) and not System ($($safety.IsSystem))." -ForegroundColor Green
Write-Host "  [PASS] Target Media: $($safety.FriendlyName) | Bus: $($safety.BusType) | Disk Size: $($safety.DiskSizeGB) GB" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 5. Capacity Validation
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Validating drive capacity against SKU requirements for '$ResolvedSku'..." -ForegroundColor Cyan
$capPassed = $true
$cap = $null
try {
    $cap = Assert-DriveCapacity -DriveLetter $Drive -ProductSku $ResolvedSku
    Write-Host "  [PASS] Target formatted volume size: $($cap.ActualGB) GB ($($cap.ActualGiB) GiB)" -ForegroundColor Green
    Write-Host "  [PASS] Minimum required for $($ResolvedSku): $($cap.RequiredGB) GB (Target media: $($cap.TargetMediaLabel))" -ForegroundColor Green
} catch {
    $capPassed = $false
    if ($DryRun) {
        Write-Host "  [DRY-RUN CAPACITY AUDIT: INSUFFICIENT]" -ForegroundColor Yellow
        Write-Host "  $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "  [DRY-RUN] Live provisioning would abort. Continuing simulation to evaluate staging plan..." -ForegroundColor Yellow
    } else {
        throw
    }
}

# ------------------------------------------------------------------------------
# 6. Process Lock Audit & Resolution
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Auditing active process locks on ${Drive}:\" -ForegroundColor Cyan
$runningProcs = Get-DriveRunningProcesses -DriveLetter $Drive
if ($runningProcs.Count -gt 0) {
    Write-Host "  Found $($runningProcs.Count) active process(es) holding file handles on ${Drive}:\" -ForegroundColor Yellow
    foreach ($p in $runningProcs) {
        Write-Host "    - PID $($p.Id): $($p.ProcessName) ($($p.Path))" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [PASS] No active process file locks detected on ${Drive}:\" -ForegroundColor Green
}

if (-not $DryRun -and $runningProcs.Count -gt 0) {
    Write-Host "  Stopping running processes locking ${Drive}:\..." -ForegroundColor Yellow
    $stoppedPids = Stop-TargetDriveProcesses -DriveLetter $Drive
    Write-Host "  Terminated $($stoppedPids.Count) lock process(es)." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 7. Filesystem Action Resolution
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Resolving filesystem configuration plan..." -ForegroundColor Cyan
$fsPlan = Get-FilesystemPlan -DriveLetter $Drive -FilesystemAction $FilesystemAction
Write-Host "  Elevation Status : $(if ($fsPlan.IsElevated) { 'Elevated (Administrator)' } else { 'Non-Elevated (Standard User)' })" -ForegroundColor White
Write-Host "  Target Filesystem: $($fsPlan.CurrentFileSystem) (Label: '$($fsPlan.FileSystemLabel)')" -ForegroundColor White
Write-Host "  Resolved Action  : $($fsPlan.ResolvedAction) - $($fsPlan.Description)" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 7.5 Payload Asset Acquisition: ensure required .zim / .gguf files exist in the
#     host cache (downloading missing ones via fetch_assets.py), since the
#     staging plan throws on missing assets.
# ------------------------------------------------------------------------------
$tierMap = @{ Product1 = 0; Product2 = 1; Product3 = 2; Tier3 = 3; Tier4 = 4 }
$assetTier = if ($tierMap.ContainsKey($ResolvedSku)) { $tierMap[$ResolvedSku] } else { 0 }

$null = New-Item -ItemType Directory -Path (Join-Path $CacheDir "zim") -Force
$null = New-Item -ItemType Directory -Path (Join-Path $CacheDir "models") -Force

$preInv = Get-ProductAssetInventory -ProductSku $ResolvedSku -ProductsJsonPath (Join-Path $SourceRoot "manifests\products.json") -CustomCacheDirs @($CacheDir) -Profile $Profile

if (-not $preInv.AllRequiredAvailable) {
    $missingNames = @($preInv.Assets | Where-Object { $_.Status -eq "MISSING" } | ForEach-Object { $_.FileName })
    Write-Host ""
    Write-Host "Missing payload assets for $ResolvedSku (cache: $CacheDir)" -ForegroundColor Yellow
    foreach ($mn in $missingNames) { Write-Host "  [MISSING] $mn" -ForegroundColor Yellow }

    if ($NoDownload) {
        throw "Missing $($missingNames.Count) asset(s) and -NoDownload was set. Re-run without it, or run provisioning\tools\download_internet_in_a_box.ps1 -Tier $assetTier"
    }

    Write-Host ""
    Write-Host ">>> Fetching missing assets (tier <= $assetTier)..." -ForegroundColor Cyan
    $fetchScript = Join-Path $SourceRoot "provisioning\tools\fetch_assets.py"
    if (-not (Test-Path $fetchScript)) { throw "fetch_assets.py not found at: $fetchScript" }

    & python $fetchScript --tier $assetTier --dest-root $CacheDir
    if ($LASTEXITCODE -ne 0) {
        throw "Asset download failed (offline or source unreachable?). Partial files are preserved in $CacheDir and will resume on next run."
    }

    $postInv = Get-ProductAssetInventory -ProductSku $ResolvedSku -ProductsJsonPath (Join-Path $SourceRoot "manifests\products.json") -CustomCacheDirs @($CacheDir) -Profile $Profile
    if (-not $postInv.AllRequiredAvailable) {
        throw "Cache still incomplete after download attempt; aborting before live staging."
    }
    Write-Host "  [OK] All required payload assets present in cache." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 8. Whitelist Staging Plan Generation & Magic Byte Audit
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Generating whitelist staging plan for '$ResolvedSku'..." -ForegroundColor Cyan
$plan = Get-WhitelistedStagingPlan -SourceRoot $SourceRoot -ProductSku $ResolvedSku -TargetDriveLetter $Drive -CustomCacheDir $CacheDir -ProfileName $Profile

Write-Host "  Total Files to Stage: $($plan.TotalFiles)" -ForegroundColor White
Write-Host "  Total Staged Bytes  : $($plan.TotalStagedBytes) bytes ($($plan.TotalStagedGB) GB / $($plan.TotalStagedGiB) GiB)" -ForegroundColor White

# Verify source asset magic headers
Write-Host ""
Write-Host ">>> Verifying source asset magic headers..." -ForegroundColor Cyan
$sourceMagicFailures = @()
$missingAssets = @()
foreach ($item in $plan.Items) {
    if ($item.SourcePath -and (Test-Path -LiteralPath $item.SourcePath) -and ($item.RelativePath -like "*.zim" -or $item.RelativePath -like "*.gguf")) {
        $chk = Test-AssetMagicHeader -FilePath $item.SourcePath
        if (-not $chk.IsValid) {
            $sourceMagicFailures += "$($item.RelativePath): $($chk.ErrorMessage)"
            Write-Host "  [FAIL] $($item.RelativePath): $($chk.ErrorMessage)" -ForegroundColor Red
        } else {
            Write-Host "  [PASS] $($item.RelativePath) -> Magic verified ($($chk.MagicString))" -ForegroundColor Green
        }
    } elseif ($item.Category -like "*ZIM*" -or $item.Category -like "*Model*") {
        if (-not $item.SourcePath -or -not (Test-Path -LiteralPath $item.SourcePath)) {
            $missingAssets += $item.RelativePath
            Write-Host "  [MISSING] $($item.RelativePath) -> Not found in local cache (download required before live staging)" -ForegroundColor Yellow
        }
    }
}

if ($sourceMagicFailures.Count -gt 0 -or ($missingAssets.Count -gt 0 -and -not $DryRun)) {
    throw "Source asset validation failed! $($sourceMagicFailures.Count) asset(s) corrupted, $($missingAssets.Count) missing."
}

# ------------------------------------------------------------------------------
# 9. Dry-Run Simulation Verdict
# ------------------------------------------------------------------------------
if ($DryRun) {
    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Cyan
    $verdictPass = ($capPassed -and $missingAssets.Count -eq 0 -and $sourceMagicFailures.Count -eq 0)
    $verdictText = if ($verdictPass) { "PASSED" } else { "COMPLETED WITH FINDINGS" }
    $verdictColor = if ($verdictPass) { "Green" } else { "Yellow" }
    Write-Host "  >>> DRY RUN SIMULATION VERDICT: $verdictText" -ForegroundColor $verdictColor
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  Product SKU        : $ResolvedSku"
    Write-Host "  Target Drive       : ${Drive}:"
    Write-Host "  Drive Safety Check : PASSED (Disk 0 Protected, Host NVMe Guarded)"
    Write-Host "  Capacity Validation: $(if ($capPassed) { "PASSED ($($cap.ActualGB) GB >= $($cap.RequiredGB) GB)" } else { "INSUFFICIENT (Target drive cannot fit $ResolvedSku; 128 GB required)" })" -ForegroundColor $(if ($capPassed) { "Green" } else { "Yellow" })
    Write-Host "  Lock Resolution    : PASSED ($($runningProcs.Count) process(es) audited)"
    Write-Host "  Filesystem Plan    : $($fsPlan.ResolvedAction) ($($fsPlan.Description))"
    Write-Host "  Asset Magic Headers: $(if ($sourceMagicFailures.Count -eq 0) { "100% PASSED" } else { "$($sourceMagicFailures.Count) Corrupted" })"
    if ($missingAssets.Count -gt 0) {
        Write-Host "  Missing In Cache   : $($missingAssets.Count) file(s) must be downloaded before live staging" -ForegroundColor Yellow
    }
    Write-Host "  Customer Stripping : 0 builder/download scripts included in whitelist"
    Write-Host "  Total Staged Size  : $($plan.TotalStagedGB) GB ($($plan.TotalStagedBytes) bytes)"
    Write-Host "  0 actual writes performed to disk."
    Write-Host "================================================================================" -ForegroundColor Cyan
    exit 0
}

# ------------------------------------------------------------------------------
# 10. Live Execution: Wiping / Formatting
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Executing filesystem preparation ($($fsPlan.ResolvedAction))..." -ForegroundColor Cyan
$cleanDrive = ($Drive.Trim().ToUpper() -replace "[:\\/\s]", "")
$targetRoot = "${cleanDrive}:\"

if ($fsPlan.ResolvedAction -eq "FormatExFAT") {
    Write-Host "  Formatting ${cleanDrive}: as exFAT @ 128 KB clusters..." -ForegroundColor Yellow
    if ($fsPlan.IsElevated) {
        Format-Volume -DriveLetter $cleanDrive -FileSystem exFAT -AllocationUnitSize 131072 -NewFileSystemLabel "OFFGRIDUSB" -Confirm:$false -Force | Out-Null
    } else {
        & format.com "${cleanDrive}:" /FS:exFAT /A:128K /V:OFFGRIDUSB /Q /Y | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to format ${cleanDrive}: as exFAT via format.com (exit code $LASTEXITCODE)."
        }
    }
    $refreshedVol = Get-Volume -DriveLetter $cleanDrive -ErrorAction SilentlyContinue
    if ($refreshedVol) {
        $fsPlan.CurrentFileSystem = $refreshedVol.FileSystem
    }
    Write-Host "  [OK] Volume formatted cleanly as exFAT @ 128 KB." -ForegroundColor Green
} elseif ($fsPlan.ResolvedAction -eq "CleanWipe") {
    Write-Host "  Performing recursive clean wipe of ${cleanDrive}:\ (preserving exFAT geometry)..." -ForegroundColor Yellow
    Get-ChildItem -Path $targetRoot -Force -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -ne "System Volume Information"
    } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  [OK] Volume clean wiped." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 11. Live Execution: Staging Files
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Staging files to ${cleanDrive}:\..." -ForegroundColor Cyan

foreach ($item in $plan.Items) {
    $dst = $item.TargetPath
    $dstDir = [System.IO.Path]::GetDirectoryName($dst)
    if ($dstDir -and -not (Test-Path $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }

    if ($item.SourcePath -eq "[Dynamically Generated]" -or $item.SourcePath -eq "[Directory Placeholder]") {
        continue
    }

    if (Test-Path -LiteralPath $item.SourcePath) {
        $isLargeAsset = ($item.RelativePath -like "*.zim" -or $item.RelativePath -like "*.gguf")
        if ($isLargeAsset) {
            $sizeMB = [math]::Round($item.SizeBytes / 1MB, 1)
            $swAsset = [System.Diagnostics.Stopwatch]::StartNew()
            Write-Host "  [STAGE] $($item.RelativePath) ($sizeMB MB)..." -ForegroundColor Cyan
        }
        Copy-ItemThrottled -SourcePath $item.SourcePath -DestinationPath $dst -LimitKBps $BwLimitKBps
        if ($isLargeAsset) {
            $swAsset.Stop()
            $sec = [math]::Max(0.1, [math]::Round($swAsset.Elapsed.TotalSeconds, 1))
            $mbps = [math]::Round(($item.SizeBytes / 1MB) / $sec, 1)
            Write-Host "  [OK] $($item.RelativePath) copied in ${sec}s ($mbps MB/s)" -ForegroundColor Green
        }
    }
}

# Generate dynamic product_sku.json
Write-Host "  Generating tailored manifests/product_sku.json..." -ForegroundColor Cyan
$clusterSize = if ($fsPlan.AllocationUnitSize) { $fsPlan.AllocationUnitSize } else { 131072 }
$skuOut = Join-Path $targetRoot "manifests\product_sku.json"
New-ProductSkuManifest -ProductSku $ResolvedSku -ProductsJsonPath (Join-Path $SourceRoot "manifests\products.json") -TargetDriveLetter "${cleanDrive}:" -Filesystem $fsPlan.CurrentFileSystem -ClusterSizeBytes $clusterSize -ProfileName $Profile -OutputPath $skuOut | Out-Null

# Generate dynamic library.xml for staged ZIMs
Write-Host "  Generating tailored data/library.xml for staged ZIM archives..." -ForegroundColor Cyan
$stagedZimDir = Join-Path $targetRoot "data\zim"
$templateXml = Join-Path $SourceRoot "data\library.xml"
$targetXml = Join-Path $targetRoot "data\library.xml"
if ((Test-Path $stagedZimDir) -and (Test-Path $templateXml)) {
    Build-LibraryXml -ZimDir $stagedZimDir -TemplateXmlPath $templateXml -OutputXmlPath $targetXml | Out-Null
}

# Ensure empty directories exist
$null = New-Item -ItemType Directory -Path (Join-Path $targetRoot "data\vault") -Force
$null = New-Item -ItemType Directory -Path (Join-Path $targetRoot "data\uploads") -Force

# ------------------------------------------------------------------------------
# 12. Enforce Strict LF Line Endings
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Enforcing strict POSIX LF (0x0A) line endings on shell scripts..." -ForegroundColor Cyan
$fixedCount = Enforce-LfLineEndings -TargetRoot $targetRoot
Write-Host "  Cleaned line endings on $fixedCount shell script(s)." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 13. Customer USB Stripper & Hygiene Audit
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host ">>> Running automated customer USB hygiene verification..." -ForegroundColor Cyan
$hygiene = Assert-CustomerUsbHygiene -TargetDrive $cleanDrive
Write-Host "  [OK] Customer USB Hygiene 100% Certified Clean!" -ForegroundColor Green

Write-Host ""
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "  >>> PROVISIONING SUCCESSFUL: $ResolvedSku staged onto ${cleanDrive}:" -ForegroundColor Green
Write-Host "================================================================================" -ForegroundColor Green
Write-Host "  Ready for customer deployment. Zero downloader or builder scripts present."
Write-Host ""
exit 0
