<#
.SYNOPSIS
    SafetyValidator - Hardware safety validation, Disk 0 guard, capacity enforcement,
    and process lock resolution for OffGridUSB factory provisioning.

.DESCRIPTION
    Enforces the Triple-Gate safety architecture protecting the host operating system,
    validates target USB flash drive capacity per Product SKU (8 GB, 32 GB, 128 GB),
    and cleanly resolves volume file locks before wiping or staging.
#>

# Ensure .NET file operations resolve against PowerShell's current location
[CmdletBinding()]
param()

# SKU Minimum Required Volume Capacity in Bytes
$script:SkuMinCapacityBytes = @{
    "Product1"        = 7000000000L   # 7.0 GB for 8 GB USB (payload <= 6.5 GB)
    "PocketSurvival"  = 7000000000L
    "Tier0"           = 7000000000L
    "Product2"        = 28000000000L  # 28.0 GB for 32 GB USB (~16-20 GB payload)
    "FieldReady"      = 28000000000L
    "Tier1"           = 28000000000L
    "Product3"        = 110000000000L # 110.0 GB for 128 GB USB (~65-72 GB payload; rejects 64 GB)
    "CivilizationArk" = 110000000000L
    "Tier2"           = 110000000000L
    "Tier3"           = 220000000000L # 220.0 GB for 256 GB SSD (~88 GB payload)
    "SwarmCluster"    = 220000000000L
    "Tier4"           = 450000000000L # 450.0 GB for 512 GB NVMe (~210+ GB payload)
    "SettlementHub"   = 450000000000L
}

$script:SkuTargetUsbLabel = @{
    "Product1"        = "8 GB USB Flash Drive"
    "PocketSurvival"  = "8 GB USB Flash Drive"
    "Tier0"           = "8 GB USB Flash Drive"
    "Product2"        = "32 GB USB Flash Drive"
    "FieldReady"      = "32 GB USB Flash Drive"
    "Tier1"           = "32 GB USB Flash Drive"
    "Product3"        = "128 GB USB Flash Drive or SSD (Note: 64 GB USB is insufficient)"
    "CivilizationArk" = "128 GB USB Flash Drive or SSD (Note: 64 GB USB is insufficient)"
    "Tier2"           = "128 GB USB Flash Drive or SSD"
    "Tier3"           = "256 GB Portable SSD"
    "SwarmCluster"    = "256 GB Portable SSD"
    "Tier4"           = "512 GB Portable NVMe"
    "SettlementHub"   = "512 GB Portable NVMe"
}

function Assert-TargetDriveSafety {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveLetter,

        [Parameter(Mandatory = $false)]
        [switch]$AllowNonUsb = $false
    )

    if ([string]::IsNullOrWhiteSpace($DriveLetter)) {
        throw "FATAL SAFETY VIOLATION: Target drive letter must be specified!"
    }

    $clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    if ($clean.Length -ne 1 -or $clean -notmatch "^[A-Z]$") {
        throw "FATAL SAFETY VIOLATION: Invalid drive letter '$DriveLetter'! Must be a single letter (e.g. 'D' or 'D:')."
    }

    # Gate 1: Drive Letter Guard (Reject C: and SystemDrive)
    $sysLetter = ($env:SystemDrive -replace "[:\\/\s]", "").ToUpper()
    if (-not $sysLetter) { $sysLetter = "C" }

    if ($clean -eq "C" -or $clean -eq $sysLetter) {
        throw "FATAL SAFETY VIOLATION: Refusing to provision to host OS system drive '${clean}:'! Host drive is strictly protected."
    }

    # Gate 2: Partition & Physical Disk Inspection
    $part = $null
    try {
        $part = Get-Partition -DriveLetter $clean -ErrorAction Stop
    } catch {
        throw "FATAL SAFETY VIOLATION: Could not query partition for drive '${clean}:'. Error: $($_.Exception.Message)"
    }

    $diskNumber = $part.DiskNumber
    $disk = $null
    try {
        $disk = Get-Disk -Number $diskNumber -ErrorAction Stop
    } catch {
        throw "FATAL SAFETY VIOLATION: Could not query physical disk #$diskNumber for drive '${clean}:'. Error: $($_.Exception.Message)"
    }

    # Gate 2b: Disk 0 Hard Block (Host NVMe OS drive)
    if ($disk.Number -eq 0) {
        throw "FATAL SAFETY VIOLATION: Drive '${clean}:' resides on physical Disk 0 ($($disk.FriendlyName))! Disk 0 is the host NVMe OS drive and is strictly protected."
    }

    # Gate 3: OS Boot / System / Pagefile Flags
    if ($disk.IsBoot) {
        throw "FATAL SAFETY VIOLATION: Disk $($disk.Number) is flagged as IsBoot=True! Refusing to modify OS boot drive."
    }
    if ($disk.IsSystem) {
        throw "FATAL SAFETY VIOLATION: Disk $($disk.Number) is flagged as IsSystem=True! Refusing to modify OS system drive."
    }

    # Check partition flags
    if ($part.IsBoot -or $part.IsSystem) {
        throw "FATAL SAFETY VIOLATION: Partition on '${clean}:' is marked as Boot/System partition!"
    }

    # Gate 4: Bus Type & Removable Verification
    $isUsb = ($disk.BusType -eq "USB")
    if (-not $isUsb -and -not $AllowNonUsb) {
        Write-Warning "Disk $($disk.Number) has BusType '$($disk.BusType)' (Expected 'USB'). FriendlyName: '$($disk.FriendlyName)'."
    }

    # Partition Alignment & Sector 32 Anomaly Detection
    $startingOffset = $part.Offset
    $sectorOffset = [int64]($part.Offset / 512)
    $isSector32 = ($sectorOffset -eq 32)
    if ($isSector32) {
        Write-Warning "Sector 32 alignment detected on '${clean}:' (Offset: $startingOffset bytes / Sector $sectorOffset). Standard alignment is 1 MiB (Sector 2048 / 1,048,576 bytes)."
    }

    return [PSCustomObject]@{
        DiskNumber      = $disk.Number
        FriendlyName    = $disk.FriendlyName
        BusType         = $disk.BusType
        DiskSizeBytes   = $disk.Size
        DiskSizeGB      = [math]::Round($disk.Size / 1GB, 2)
        DriveLetter     = $clean
        PartitionNumber = $part.PartitionNumber
        StartingOffset  = $startingOffset
        SectorOffset    = $sectorOffset
        IsSector32      = $isSector32
        IsUsb           = $isUsb
        IsBoot          = $disk.IsBoot
        IsSystem        = $disk.IsSystem
    }
}

function Assert-DriveCapacity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveLetter,

        [Parameter(Mandatory = $true)]
        [string]$ProductSku,

        [Parameter(Mandatory = $false)]
        [int64]$MaxPhysicalBytes = 0
    )

    $clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $normSku = $ProductSku.Trim()

    if (-not $script:SkuMinCapacityBytes.ContainsKey($normSku)) {
        throw "Unknown Product SKU '$ProductSku' for capacity validation. Supported: Product1, Product2, Product3, Tier0, Tier1, Tier2, Tier3, Tier4."
    }

    $reqBytes = $script:SkuMinCapacityBytes[$normSku]
    $targetLabel = $script:SkuTargetUsbLabel[$normSku]

    $vol = $null
    try {
        $vol = Get-Volume -DriveLetter $clean -ErrorAction Stop
    } catch {
        throw "Could not query volume for drive '${clean}:'. Error: $($_.Exception.Message)"
    }

    $actualBytes = $vol.Size
    $actualGb = [math]::Round($actualBytes / 1e9, 2)
    $actualGiB = [math]::Round($actualBytes / 1GB, 2)
    $reqGb = [math]::Round($reqBytes / 1e9, 2)

    # Capacity Clamping for Drive E: to 29.00 GiB (protecting data integrity on 32 GB flash)
    # Media contains a physical 32 GB NAND flash die with blackhole discard above 29.275 GiB.
    # Clamping to 29.00 GiB (31,138,512,896 bytes) leaves a 282 MiB safety wear-leveling reserve.
    $effectiveBytes = $actualBytes
    $isClamped = $false
    $clampedReason = ""

    if ($MaxPhysicalBytes -gt 0 -and $MaxPhysicalBytes -lt $effectiveBytes) {
        $effectiveBytes = $MaxPhysicalBytes
        $isClamped = $true
        $clampedReason = "Physical capacity clamping active: Drive ${clean}: volume size ($actualGb GB / $actualGiB GiB) clamped to $([math]::Round($MaxPhysicalBytes / 1e9, 2)) GB ($([math]::Round($MaxPhysicalBytes / 1GB, 2)) GiB)."
        Write-Warning $clampedReason
    }

    $effectiveGb = [math]::Round($effectiveBytes / 1e9, 2)
    $effectiveGiB = [math]::Round($effectiveBytes / 1GB, 2)

    if ($effectiveBytes -lt $reqBytes) {
        $msg = "[ERROR] Target drive ${clean}: effective capacity (${effectiveGb} GB / ${effectiveGiB} GiB) is below the minimum required capacity (${reqGb} GB) for ${ProductSku}!`n"
        $msg += "Required target media: ${targetLabel}.`n"
        if ($isClamped) {
            $msg += "Note: Physical capacity clamping to 29.00 GiB is enforced for Drive E: to protect data integrity on 32 GB flash. Higher-tier payloads (Product 3 / Tier 3 ~88 GB / Tier 4) exceed physical flash and require genuine >= 128 GB media to avoid silent blackhole corruption."
        } elseif ($normSku -in @("Product3", "CivilizationArk", "Tier2")) {
            $msg += "Commercial 64 GB USB drives only provide ~57.6 GiB (~61.8 GB) usable capacity, which cannot fit the ~65-72 GB CivilizationArk payload (including 50.2 GB Wikipedia). A 128 GB USB drive or SSD is strictly required."
        }
        throw $msg
    }

    return [PSCustomObject]@{
        DriveLetter      = $clean
        ProductSku       = $normSku
        ActualBytes      = $actualBytes
        ActualGB         = $actualGb
        ActualGiB        = $actualGiB
        EffectiveBytes   = $effectiveBytes
        EffectiveGB      = $effectiveGb
        EffectiveGiB     = $effectiveGiB
        IsClamped        = $isClamped
        RequiredBytes    = $reqBytes
        RequiredGB       = $reqGb
        TargetMediaLabel = $targetLabel
        FileSystem       = $vol.FileSystem
        Passed           = $true
    }
}

function Get-DriveRunningProcesses {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveLetter
    )

    $clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $prefix = "${clean}:\"

    $processes = @()
    Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
        $p = $_
        try {
            $path = $p.Path
            if ($path -and $path.ToUpper().StartsWith($prefix.ToUpper())) {
                $processes += $p
            }
        } catch {}
    }

    return $processes
}

function Stop-TargetDriveProcesses {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveLetter
    )

    $clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $stopped = @()

    $procs = Get-DriveRunningProcesses -DriveLetter $clean
    foreach ($p in $procs) {
        try {
            Write-Host "  Terminating process on ${clean}:\ PID $($p.Id) ($($p.ProcessName))..." -ForegroundColor Yellow
            $p | Stop-Process -Force -ErrorAction SilentlyContinue
            $stopped += $p.Id
        } catch {
            Write-Warning "Could not terminate PID $($p.Id): $($_.Exception.Message)"
        }
    }

    # Also check ports 8000, 8081, 8082 if bound by target drive processes
    try {
        $netstat = netstat -ano -p tcp 2>$null | Select-String ":(8000|8081|8082)\s+.*LISTENING"
        foreach ($line in $netstat) {
            $parts = ($line.ToString().Trim() -split "\s+")
            $pidVal = $parts[-1]
            if ($pidVal -match "^\d+$" -and [int]$pidVal -gt 4) {
                $targetProc = Get-Process -Id [int]$pidVal -ErrorAction SilentlyContinue
                if ($targetProc -and $targetProc.Path -and $targetProc.Path.ToUpper().StartsWith("${clean}:\".ToUpper())) {
                    Write-Host "  Stopping listening server PID $pidVal on port..." -ForegroundColor Yellow
                    $targetProc | Stop-Process -Force -ErrorAction SilentlyContinue
                    $stopped += [int]$pidVal
                }
            }
        }
    } catch {}

    if ($stopped.Count -gt 0) {
        Start-Sleep -Seconds 1
    }

    return $stopped
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-FilesystemPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DriveLetter,

        [Parameter(Mandatory = $false)]
        [ValidateSet("Auto", "FormatExFAT", "CleanWipe", "KeepExisting")]
        [string]$FilesystemAction = "Auto"
    )

    $clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
    $vol = Get-Volume -DriveLetter $clean -ErrorAction Stop
    $isElevated = Test-IsAdministrator

    $plan = [PSCustomObject]@{
        DriveLetter         = $clean
        CurrentFileSystem   = $vol.FileSystem
        AllocationUnitSize  = $vol.AllocationUnitSize
        FileSystemLabel     = $vol.FileSystemLabel
        IsElevated          = $isElevated
        RequestedAction     = $FilesystemAction
        ResolvedAction      = ""
        Description         = ""
    }

    switch ($FilesystemAction) {
        "FormatExFAT" {
            $plan.ResolvedAction = "FormatExFAT"
            $plan.Description = "Fast format to exFAT with 128 KB allocation units (Label: OFFGRIDUSB)"
        }
        "CleanWipe" {
            $plan.ResolvedAction = "CleanWipe"
            $plan.Description = "Non-elevated recursive wipe of files preserving existing exFAT filesystem and geometry"
        }
        "KeepExisting" {
            $plan.ResolvedAction = "KeepExisting"
            $plan.Description = "Non-destructive sync over existing files without wiping"
        }
        "Auto" {
            if ($vol.FileSystem -ne "exFAT") {
                $plan.ResolvedAction = "FormatExFAT"
                $plan.Description = "Volume is $($vol.FileSystem); auto-formatting to exFAT with 128 KB clusters (Label: OFFGRIDUSB)"
            } elseif ($isElevated) {
                $plan.ResolvedAction = "FormatExFAT"
                $plan.Description = "Elevated mode detected: formatting volume as exFAT with 128 KB clusters"
            } else {
                $plan.ResolvedAction = "CleanWipe"
                $plan.Description = "Volume is already exFAT; performing recursive clean wipe"
            }
        }
    }

    return $plan
}

if ($MyInvocation.MyCommand.ModuleName) {
    Export-ModuleMember -Function Assert-TargetDriveSafety, Assert-DriveCapacity, Get-DriveRunningProcesses, Stop-TargetDriveProcesses, Test-IsAdministrator, Get-FilesystemPlan -ErrorAction SilentlyContinue
}
