# ------------------------------------------------------------------------------
# EngineStager - Shared portable runtime engine fetch/verify library.
#
# Downloads and verifies the zero-install cross-platform engines that live in
# bin/ (Git-ignored by design):
#   - Windows x86_64: Python 3.12.8 Embeddable + kiwix-serve.exe + llama-server.exe
#   - Windows ARM64:  native llama-server.exe
#   - Linux x86_64 / ARM64 (Raspberry Pi): static kiwix-serve + llama .tar.gz bundles
#   - macOS ARM64 / x86_64: kiwix-serve + llama .tar.gz bundles
#   - Polyglot: Mozilla llamafile Cosmopolitan universal binary
#
# POSIX bundles stay staged as .tar.gz so .so/.dylib symlinks survive exFAT/FAT32;
# KiwixRunner/ModelRunner extract them into RAM at runtime on POSIX hosts.
#
# Pure PowerShell (uses curl.exe when available, Invoke-WebRequest fallback).
# Consumed by both provisioning\provision_usb.ps1 and
# provisioning\tools\download_internet_in_a_box.ps1 so that a factory provision
# run always yields a drive that boots on every supported host OS.
# ------------------------------------------------------------------------------

$script:EnginesApiBase = "https://"

function Test-FileMagicHeader {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [ValidateSet("ZIM", "GGUF", "TAR_GZ", "ZIP", "EXE", "ANY")]
        [string]$Expected = "ANY"
    )
    if (-not (Test-Path $FilePath)) { return $false }
    $item = Get-Item $FilePath
    if ($item.Length -lt 16) { return $false }

    $fs = [System.IO.File]::OpenRead($item.FullName)
    try {
        $buf = New-Object byte[] 4
        $read = $fs.Read($buf, 0, 4)
        if ($read -lt 4) { return $false }
        # Disallow zero-filled corrupted sectors from uncommitted writes
        if ($buf[0] -eq 0 -and $buf[1] -eq 0 -and $buf[2] -eq 0 -and $buf[3] -eq 0) {
            return $false
        }
        if ($Expected -eq "GGUF") {
            return ($buf[0] -eq 0x47 -and $buf[1] -eq 0x47 -and $buf[2] -eq 0x55 -and $buf[3] -eq 0x46)
        }
        if ($Expected -eq "ZIM") {
            # Little-endian ZIM\x04: 0x5A 0x49 0x4D 0x04
            return ($buf[0] -eq 0x5A -and $buf[1] -eq 0x49 -and $buf[2] -eq 0x4D -and $buf[3] -eq 0x04)
        }
        if ($Expected -eq "TAR_GZ") {
            # GZIP magic: 0x1F 0x8B
            return ($buf[0] -eq 0x1F -and $buf[1] -eq 0x8B)
        }
        if ($Expected -eq "ZIP") {
            # PKzip magic: 0x50 0x4B
            return ($buf[0] -eq 0x50 -and $buf[1] -eq 0x4B)
        }
        if ($Expected -eq "EXE") {
            # DOS PE / MZ magic: 0x4D 0x5A
            return ($buf[0] -eq 0x4D -and $buf[1] -eq 0x5A)
        }
        return $true
    } finally {
        $fs.Close()
    }
}

function Invoke-ResumableDownload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Dest,
        [ValidateSet("ZIM", "GGUF", "TAR_GZ", "ZIP", "EXE", "ANY")]
        [string]$MagicCheck = "ANY",
        [long]$MinBytes = 65536
    )

    $parentDir = Split-Path -Parent $Dest
    if ($parentDir -and -not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
    }

    if (Test-Path $Dest) {
        $existingLen = (Get-Item $Dest).Length
        if ($existingLen -ge $MinBytes -and (Test-FileMagicHeader -FilePath $Dest -Expected $MagicCheck)) {
            $mb = [math]::Round($existingLen / 1MB, 1)
            Write-Host "  [SKIP] Verified & staged: $Dest ($mb MB)" -ForegroundColor DarkGreen
            return
        }
    }

    $partFile = "$Dest.part"
    Write-Host "  [DL]   Fetching: $Url" -ForegroundColor Cyan
    Write-Host "         Target  : $Dest" -ForegroundColor Gray

    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        $curlArgs = @(
            "-L", "-f",
            "--retry", "5",
            "--retry-connrefused",
            "--retry-delay", "2",
            "--connect-timeout", "30",
            "-A", "OffGridUSB-Provisioner/0.1"
        )
        if (Test-Path $partFile) {
            $curlArgs += @("-C", "-")
        }
        $curlArgs += @("-o", $partFile, $Url)
        & curl.exe @curlArgs
        if ($LASTEXITCODE -ne 0) {
            # Only remove partFile if server rejected byte-range resume (curl exit code 33 = HTTP 416 Range Not Satisfiable)
            if ($LASTEXITCODE -eq 33) {
                Write-Warning "Server rejected byte-range resume (curl exit code 33 / HTTP 416). Retrying clean download..."
                Remove-Item $partFile -Force -ErrorAction SilentlyContinue
                & curl.exe -L -f --retry 5 --retry-connrefused --retry-delay 2 --connect-timeout 30 -A "OffGridUSB-Provisioner/0.1" -o $partFile $Url
            }
            if ($LASTEXITCODE -ne 0) {
                throw "Download failed for $Url (curl exit code $LASTEXITCODE). Partial file preserved at $partFile for resumption."
            }
        }
    } else {
        Invoke-WebRequest -Uri $Url -OutFile $partFile -UseBasicParsing -UserAgent "OffGridUSB-Provisioner/0.1"
    }

    Move-Item -Path $partFile -Destination $Dest -Force
    $finalLen = (Get-Item $Dest).Length
    if ($finalLen -lt $MinBytes -or -not (Test-FileMagicHeader -FilePath $Dest -Expected $MagicCheck)) {
        throw "Integrity check failed for $Dest ($finalLen bytes, expected header: $MagicCheck)"
    }
    $finalMb = [math]::Round($finalLen / 1MB, 1)
    Write-Host "  [OK]   Ready: $Dest ($finalMb MB)" -ForegroundColor Green
}

function Get-EngineManifest {
    <#
    Returns the canonical engine payload list. Every entry:
      Name, Path (relative to Root), Url, Magic (header check), Kind
    Kind = "extract-zip" (archive expanded flat into dir) or "file" (staged as-is).
    Windows x86_64 entries are marked BootCritical because run_windows.bat
    cannot launch anything without them.
    #>
    @(
        @{ Name = "Windows x64 Portable Python 3.12"; Path = "bin\windows_x86_64\python\python.exe"; Probe = "bin\windows_x86_64\python\python.exe"; Url = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip"; Archive = "py_embed.zip"; Kind = "extract-python"; Magic = "ZIP"; BootCritical = $true },
        @{ Name = "Windows x64 Kiwix ZIM Server";     Path = "bin\windows_x86_64\kiwix\kiwix-serve.exe"; Probe = "bin\windows_x86_64\kiwix\kiwix-serve.exe"; Url = "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_win-x86_64-3.8.1.zip"; Archive = "kiwix_win.zip"; Kind = "extract-zip"; Magic = "ZIP"; BootCritical = $true },
        @{ Name = "Windows x64 llama-server";         Path = "bin\windows_x86_64\llama\llama-server.exe"; Probe = "bin\windows_x86_64\llama\llama-server.exe"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-x64.zip"; Archive = "llama_win_x64.zip"; Kind = "extract-zip"; Magic = "ZIP"; BootCritical = $false },
        @{ Name = "Windows ARM64 llama-server";       Path = "bin\windows_arm64\llama\llama-server.exe"; Probe = "bin\windows_arm64\llama\llama-server.exe"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-arm64.zip"; Archive = "llama_win_arm64.zip"; Kind = "extract-zip"; Magic = "ZIP"; BootCritical = $false },
        @{ Name = "Windows x64 ggml-rpc-server";      Path = "bin\windows_x86_64\llama\ggml-rpc-server.exe"; Probe = "bin\windows_x86_64\llama\ggml-rpc-server.exe"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-win-cpu-x64.zip"; Archive = "llama_win_x64.zip"; Kind = "extract-zip"; Magic = "ZIP"; BootCritical = $false },
        @{ Name = "Linux x64 Kiwix Bundle";           Path = "bin\linux_x86_64\kiwix-tools_linux-x86_64.tar.gz"; Url = "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-x86_64-3.8.1.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "Linux x64 llama-server Bundle";    Path = "bin\linux_x86_64\llama-ubuntu-x64.tar.gz"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-ubuntu-x64.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "Linux ARM64 (Pi) Kiwix Bundle";    Path = "bin\linux_arm64\kiwix-tools_linux-aarch64.tar.gz"; Url = "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_linux-aarch64-3.8.1.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "Linux ARM64 (Pi) llama Bundle";    Path = "bin\linux_arm64\llama-ubuntu-arm64.tar.gz"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-ubuntu-arm64.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "macOS Apple Silicon Kiwix Bundle"; Path = "bin\macos_arm64\kiwix-tools_macos.tar.gz"; Url = "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_macos-arm64-3.8.1.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "macOS Apple Silicon llama Bundle"; Path = "bin\macos_arm64\llama-macos-arm64.tar.gz"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-macos-arm64.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "macOS Intel Kiwix Bundle";         Path = "bin\macos_x86_64\kiwix-tools_macos-x86_64.tar.gz"; Url = "https://download.kiwix.org/release/kiwix-tools/kiwix-tools_macos-x86_64-3.8.1.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "macOS Intel llama Bundle";         Path = "bin\macos_x86_64\llama-macos-x64.tar.gz"; Url = "https://github.com/ggml-org/llama.cpp/releases/download/b11913/llama-b11913-bin-macos-x64.tar.gz"; Kind = "file"; Magic = "TAR_GZ"; BootCritical = $false },
        @{ Name = "Polyglot Cosmopolitan llamafile";  Path = "bin\polyglot\llamafile.exe"; Url = "https://github.com/mozilla-ai/llamafile/releases/download/0.10.6/llamafile-0.10.6-thin"; Kind = "file"; Magic = "EXE"; BootCritical = $false }
    )
}

function Test-EngineReadiness {
    <# Returns a list of missing/invalid engines relative to -Root. #>
    param([Parameter(Mandatory = $true)][string]$Root)

    $missing = @()
    foreach ($e in Get-EngineManifest) {
        $probe = Join-Path $Root $e.Path
        $expectedMagic = if ($e.Path -like "*.tar.gz") { "TAR_GZ" } elseif ($e.Path -like "*.exe") { "EXE" } else { "ANY" }
        if (-not (Test-Path $probe)) {
            $missing += $e
        } elseif (-not (Test-FileMagicHeader -FilePath $probe -Expected $expectedMagic)) {
            $missing += $e
        }
    }
    return $missing
}

function Invoke-EngineStaging {
    <#
    Downloads, verifies and stages all portable runtime engines into <Root>\bin.
    Set -DryRun to audit without downloading anything (returns missing list).
    Set -CurrentOsOnly to skip cross-platform payloads (not recommended for
    factory provisioning: a universal drive needs all of them).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [switch]$DryRun,
        [switch]$CurrentOsOnly
    )

    $tmpDl = Join-Path $Root "tmp_dl"
    $bins = @(
        "bin\windows_x86_64\python",
        "bin\windows_x86_64\kiwix",
        "bin\windows_x86_64\llama",
        "bin\windows_arm64\llama",
        "bin\linux_x86_64",
        "bin\linux_arm64",
        "bin\macos_arm64",
        "bin\macos_x86_64",
        "bin\polyglot",
        "tmp_dl"
    )
    foreach ($d in $bins) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
    }

    $missing = Test-EngineReadiness -Root $Root
    if ($missing.Count -eq 0) {
        Write-Host "  [OK] All portable engines already staged and verified in bin\." -ForegroundColor Green
        return $true
    }

    if ($DryRun) {
        Write-Host "  [DRY-RUN] Missing engine payload(s) that live provisioning would fetch:" -ForegroundColor Yellow
        foreach ($m in $missing) {
            Write-Host ("    [MISSING] {0} ({1})" -f $m.Name, $m.Path) -ForegroundColor Yellow
        }
        return $false
    }

    foreach ($e in Get-EngineManifest) {
        $probe = Join-Path $Root $e.Path
        $expectedMagic = if ($e.Path -like "*.tar.gz") { "TAR_GZ" } elseif ($e.Path -like "*.exe") { "EXE" } else { "ANY" }
        if ((Test-Path $probe) -and (Test-FileMagicHeader -FilePath $probe -Expected $expectedMagic)) {
            Write-Host "  [SKIP] $($e.Name) already staged" -ForegroundColor DarkGreen
            continue
        }

        $archive = Join-Path $tmpDl $e.Archive
        Invoke-ResumableDownload -Url $e.Url -Dest $archive -MagicCheck $e.Magic

        switch ($e.Kind) {
            "extract-python" {
                Expand-Archive -Path $archive -DestinationPath (Join-Path $Root "bin\windows_x86_64\python") -Force
                $pth = @"
python312.zip
.
..\..\..\src
import site
"@
                Set-Content -Path (Join-Path $Root "bin\windows_x86_64\python\python312._pth") -Value $pth -Encoding ASCII
                Write-Host "  [OK]   Configured zero-install Python 3.12.8 (bin\windows_x86_64\python)" -ForegroundColor Green
            }
            "extract-zip" {
                $destDir = Split-Path -Parent $probe
                New-Item -ItemType Directory -Force -Path $destDir | Out-Null
                $extDir = Join-Path $tmpDl ("ext_" + [System.IO.Path]::GetFileNameWithoutExtension($e.Archive))
                Expand-Archive -Path $archive -DestinationPath $extDir -Force
                Get-ChildItem -Path $extDir -Recurse -File | Copy-Item -Destination $destDir -Force
                Remove-Item -Recurse -Force $extDir -ErrorAction SilentlyContinue
                Write-Host "  [OK]   Extracted $($e.Name)" -ForegroundColor Green
            }
            default {
                $destDir = Split-Path -Parent $probe
                New-Item -ItemType Directory -Force -Path $destDir | Out-Null
                Copy-Item -Path $archive -Destination $probe -Force
                Write-Host "  [OK]   Staged $($e.Name)" -ForegroundColor Green
            }
        }
    }

    Remove-Item -Recurse -Force $tmpDl -ErrorAction SilentlyContinue

    $stillMissing = Test-EngineReadiness -Root $Root
    if ($stillMissing.Count -gt 0) {
        throw "Engine staging incomplete: $($stillMissing.Count) payload(s) missing or corrupt after download."
    }
    Write-Host "  [OK] All portable engines staged and verified in bin\." -ForegroundColor Green
    return $true
}

function Show-EngineVerifyReport {
    <# Full offline readiness report: engines + staged ZIMs + staged GGUFs. #>
    param([Parameter(Mandatory = $true)][string]$Root)

    Write-Host ""
    Write-Host "================================================================================" -ForegroundColor Cyan
    Write-Host "  OffGridUSB (offgridusb.com) -- Offline Asset & Engine Verification Report" -ForegroundColor Cyan
    Write-Host "================================================================================" -ForegroundColor Cyan

    Write-Host "`n  [Portable Cross-Platform Engines]" -ForegroundColor Yellow
    foreach ($ec in Get-EngineManifest) {
        $probe = Join-Path $Root $ec.Path
        $exists = Test-Path $probe
        $valid = $false
        if ($exists) {
            $expectedMagic = if ($ec.Path -like "*.tar.gz") { "TAR_GZ" } elseif ($ec.Path -like "*.exe") { "EXE" } else { "ANY" }
            $valid = Test-FileMagicHeader -FilePath $probe -Expected $expectedMagic
        }
        $status = if (-not $exists) { "[MISSING]" } elseif ($valid) { "[READY]" } else { "[BAD HEADER]" }
        $color  = if ($valid) { "Green" } elseif (-not $exists) { "DarkYellow" } else { "Red" }
        $critical = if ($ec.BootCritical) { " [BOOT-CRITICAL]" } else { "" }
        Write-Host ("    {0,-12} {1,-36}{2} ({3})" -f $status, $ec.Name, $critical, $ec.Path) -ForegroundColor $color
    }

    Write-Host "`n  [Staged Internet-in-a-Box OpenZIM Archives (data\zim)]" -ForegroundColor Yellow
    $zimDir = Join-Path $Root "data\zim"
    $zims = if (Test-Path $zimDir) { Get-ChildItem (Join-Path $zimDir "*.zim") -ErrorAction SilentlyContinue } else { @() }
    if (-not $zims -or $zims.Count -eq 0) {
        Write-Host "    [NONE] No .zim files found in data\zim yet." -ForegroundColor DarkYellow
    } else {
        foreach ($z in $zims) {
            $valid = Test-FileMagicHeader -FilePath $z.FullName -Expected "ZIM"
            $tag = if ($valid) { "[VALID ZIM]" } else { "[BAD HEADER]" }
            $col = if ($valid) { "Green" } else { "Red" }
            Write-Host ("    {0,-13} {1,-44} ({2,8:N1} MB)" -f $tag, $z.Name, ($z.Length / 1MB)) -ForegroundColor $col
        }
    }

    Write-Host "`n  [Staged Offline GGUF AI Models (data\models)]" -ForegroundColor Yellow
    $modelDir = Join-Path $Root "data\models"
    $models = if (Test-Path $modelDir) { Get-ChildItem (Join-Path $modelDir "*.gguf") -ErrorAction SilentlyContinue } else { @() }
    if (-not $models -or $models.Count -eq 0) {
        Write-Host "    [NONE] No .gguf models found in data\models yet." -ForegroundColor DarkYellow
    } else {
        foreach ($m in $models) {
            $valid = Test-FileMagicHeader -FilePath $m.FullName -Expected "GGUF"
            $tag = if ($valid) { "[VALID GGUF]" } else { "[BAD HEADER]" }
            $col = if ($valid) { "Green" } else { "Red" }
            Write-Host ("    {0,-13} {1,-44} ({2,8:N1} MB)" -f $tag, $m.Name, ($m.Length / 1MB)) -ForegroundColor $col
        }
    }
    Write-Host ""
}
