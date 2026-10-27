$ErrorActionPreference = 'Stop'
$scriptDir = $args[0]
if (-not $scriptDir) { $scriptDir = $PSScriptRoot }
if (-not $scriptDir) { $scriptDir = "." }

$sampleFiles = [System.Collections.Generic.List[string]]::new()

# 1. High-LBA Canary file
$canary = Join-Path $scriptDir "data\.integrity_canary"
if (Test-Path $canary) { $sampleFiles.Add($canary) }

# 2. Large assets (ZIM and GGUF)
$zimDir = Join-Path $scriptDir "data\zim"
if (Test-Path $zimDir) {
    Get-ChildItem -Path $zimDir -Filter "*.zim" -File -ErrorAction SilentlyContinue | ForEach-Object { $sampleFiles.Add($_.FullName) }
}
$modelsDir = Join-Path $scriptDir "data\models"
if (Test-Path $modelsDir) {
    Get-ChildItem -Path $modelsDir -Filter "*.gguf" -File -ErrorAction SilentlyContinue | ForEach-Object { $sampleFiles.Add($_.FullName) }
}

# 3. Core runtime binaries fallback
if ($sampleFiles.Count -eq 0) {
    $binDir = Join-Path $scriptDir "bin"
    if (Test-Path $binDir) {
        Get-ChildItem -Path $binDir -Include "*.exe","*.dll","*.tar.gz" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 5 | ForEach-Object { $sampleFiles.Add($_.FullName) }
    }
}

# 4. Launcher baseline
$launcher = Join-Path $scriptDir "START_OFFGRIDUSB_WINDOWS.bat"
if (Test-Path $launcher) { $sampleFiles.Add($launcher) }

$corrupt = $false
$corruptFile = ""

foreach ($f in $sampleFiles) {
    try {
        $info = New-Object System.IO.FileInfo($f)
        if ($info.Length -eq 0) { continue }
        
        $fs = [System.IO.File]::OpenRead($f)
        
        # Check Head (first 512 bytes)
        $headLen = [Math]::Min(512L, $info.Length)
        $buf = New-Object byte[] $headLen
        $read = $fs.Read($buf, 0, $headLen)
        
        $headAllNull = $true
        for ($i = 0; $i -lt $read; $i++) {
            if ($buf[$i] -ne 0) { $headAllNull = $false; break }
        }
        
        if ($read -gt 0 -and $headAllNull) {
            $corrupt = $true
            $corruptFile = $f
            $fs.Close()
            break
        }
        
        # Check Tail if file > 10MB
        if ($info.Length -gt 10485760) {
            $fs.Seek($info.Length - 512, [System.IO.SeekOrigin]::Begin) | Out-Null
            $tailBuf = New-Object byte[] 512
            $readTail = $fs.Read($tailBuf, 0, 512)
            $tailAllNull = $true
            for ($i = 0; $i -lt $readTail; $i++) {
                if ($tailBuf[$i] -ne 0) { $tailAllNull = $false; break }
            }
            if ($readTail -gt 0 -and $tailAllNull) {
                $corrupt = $true
                $corruptFile = $f + " (tail)"
                $fs.Close()
                break
            }
        }
        
        $fs.Close()
    } catch {
        # Continue checking other files
    }
}

if ($corrupt) {
    Write-Output "CORRUPT: $corruptFile"
    exit 10
} else {
    Write-Output "CLEAN"
    exit 0
}
