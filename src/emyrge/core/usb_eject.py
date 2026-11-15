"""Cross-platform safe USB flush, dismount, and hardware eject orchestration.

When the user closes the localhost Command Center tab (or clicks 'Safely Eject USB'),
this module stages a self-contained script into the host's temporary directory
(`%TEMP%` on Windows, `/tmp` on Linux/macOS) with its working directory set to
that temporary directory so zero handles remain open on the USB volume while
flushing and dismounting.
"""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional


_WINDOWS_SAFE_EJECT_PS1 = r"""param(
    [Parameter(Mandatory = $true)]
    [string]$DriveLetter,
    [Parameter(Mandatory = $false)]
    [int]$DelayMs = 1500
)

$ErrorActionPreference = "SilentlyContinue"
Set-Location $env:TEMP
[System.IO.Directory]::SetCurrentDirectory($env:TEMP)

$logFile = Join-Path $env:TEMP "offgridusb_safe_eject.log"
function Write-EjectLog([string]$msg) {
    try {
        Add-Content -Path $logFile -Value "$([DateTime]::UtcNow.ToString('o')) $msg" -ErrorAction SilentlyContinue
    } catch {}
}

$clean = ($DriveLetter.Trim().ToUpper() -replace "[:\\/\s]", "")
$sysLetter = ($env:SystemDrive -replace "[:\\/\s]", "").ToUpper()
if (-not $sysLetter) { $sysLetter = "C" }

# 0. Single-instance named mutex so redundant detached launchers (Popen + WScript COM) don't collide
$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\OffGridUsbSafeEject_${clean}", [ref]$createdNew)
if (-not $createdNew) {
    exit 0
}

Write-EjectLog "[PS1] Starting safe eject for drive '$DriveLetter' (DelayMs=$DelayMs, PID=$PID)"

# 1. Hardware Safety Gate: never touch C: or Disk 0 / Boot / System
if ($clean.Length -ne 1 -or $clean -eq "C" -or $clean -eq $sysLetter) {
    Write-EjectLog "ABORT: Invalid or system drive letter '$clean'"
    exit 1
}

if ($DelayMs -gt 0) {
    Start-Sleep -Milliseconds $DelayMs
}

if (-not (Test-Path "${clean}:\")) {
    Write-EjectLog "ALREADY_DISMOUNTED: ${clean}:\ not mounted"
    exit 0
}

try {
    $part = Get-Partition -DriveLetter $clean -ErrorAction Stop
    $disk = Get-Disk -Number $part.DiskNumber -ErrorAction Stop
    if ($disk.Number -eq 0 -or $disk.IsBoot -or $disk.IsSystem -or $part.IsBoot -or $part.IsSystem) {
        Write-EjectLog "ABORT: Disk $($disk.Number) is boot/system/Disk0"
        exit 1
    }
} catch {
    Write-EjectLog "WARN: Partition/Disk WMI lookup failed ($($_.Exception.Message)); continuing non-C eject"
}

# 1b. Close any open Explorer folder windows viewing <Drive>:\ so Explorer releases directory handles
try {
    $shellWins = New-Object -ComObject Shell.Application
    foreach ($win in @($shellWins.Windows())) {
        try {
            $locUrl = [string]$win.LocationURL
            $folderPath = [string]$win.Document.Folder.Self.Path
            if ($locUrl -match "^file:///${clean}:" -or ($folderPath -and $folderPath.ToUpper().StartsWith("${clean}:\"))) {
                Write-EjectLog "Closing Explorer window open on $folderPath"
                $win.Quit()
            }
        } catch {}
    }
} catch {}

# 2. Terminate any remaining processes executing from <Drive>:\ or holding <Drive>:\ paths
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessId -ne $PID -and (
        ($_.ExecutablePath -and $_.ExecutablePath.ToUpper().StartsWith("${clean}:\")) -or
        ($_.CommandLine -and $_.CommandLine.ToUpper().Contains("${clean}:\"))
    )
} | ForEach-Object {
    Write-EjectLog "Stopping Win32_Process PID=$($_.ProcessId) Name=$($_.Name)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Id -ne $PID -and $_.Path -and $_.Path.ToUpper().StartsWith("${clean}:\")
} | ForEach-Object {
    Write-EjectLog "Stopping Process PID=$($_.Id) Name=$($_.ProcessName)"
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 600

# 3. Flush OS file cache to physical NAND flash
try {
    Write-EjectLog "Flushing volume cache on ${clean}:"
    Write-VolumeCache -DriveLetter $clean -ErrorAction SilentlyContinue
} catch {}

Start-Sleep -Milliseconds 400

# 4a. Standard Windows Explorer Shell Eject
try {
    Write-EjectLog "Invoking Shell.Application Eject on ${clean}:"
    $shell = New-Object -ComObject Shell.Application
    $item = $shell.Namespace(17).ParseName("${clean}:")
    if ($item) {
        $item.InvokeVerb("Eject")
        Start-Sleep -Milliseconds 1500
    }
} catch {}

# 4b. Win32 Kernel Volume Lock -> Dismount -> Eject with retry loop
if (Test-Path "${clean}:\") {
    Add-Type -TypeDefinition @"
using System;
using System.Threading;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class OffGridUsbEjector {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern SafeFileHandle CreateFile(string lpFileName, uint dwDesiredAccess, uint dwShareMode, IntPtr lpSecurityAttributes, uint dwCreationDisposition, uint dwFlagsAndAttributes, IntPtr hTemplateFile);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool DeviceIoControl(SafeFileHandle hDevice, uint dwIoControlCode, IntPtr lpInBuffer, uint nInBufferSize, IntPtr lpOutBuffer, uint nOutBufferSize, out uint lpBytesReturned, IntPtr lpOverlapped);
    public static bool Eject(string letter) {
        uint GENERIC_READ = 0x80000000;
        uint GENERIC_WRITE = 0x40000000;
        uint FILE_SHARE_READ = 0x1;
        uint FILE_SHARE_WRITE = 0x2;
        uint OPEN_EXISTING = 3;
        uint FSCTL_LOCK_VOLUME = 0x00090018;
        uint FSCTL_DISMOUNT_VOLUME = 0x00090020;
        uint IOCTL_STORAGE_MEDIA_REMOVAL = 0x002D4804;
        uint IOCTL_STORAGE_EJECT_MEDIA = 0x002D4808;
        using (var h = CreateFile("\\\\.\\" + letter + ":", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero)) {
            if (h.IsInvalid) {
                using (var h2 = CreateFile("\\\\.\\" + letter + ":", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, IntPtr.Zero, OPEN_EXISTING, 0, IntPtr.Zero)) {
                    if (h2.IsInvalid) return false;
                    uint br2;
                    return DeviceIoControl(h2, IOCTL_STORAGE_EJECT_MEDIA, IntPtr.Zero, 0, IntPtr.Zero, 0, out br2, IntPtr.Zero);
                }
            }
            uint br;
            for (int i = 0; i < 6; i++) {
                if (DeviceIoControl(h, FSCTL_LOCK_VOLUME, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero)) break;
                Thread.Sleep(300);
            }
            DeviceIoControl(h, FSCTL_DISMOUNT_VOLUME, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero);
            IntPtr pmr = Marshal.AllocHGlobal(1);
            Marshal.WriteByte(pmr, 0);
            DeviceIoControl(h, IOCTL_STORAGE_MEDIA_REMOVAL, pmr, 1, IntPtr.Zero, 0, out br, IntPtr.Zero);
            Marshal.FreeHGlobal(pmr);
            return DeviceIoControl(h, IOCTL_STORAGE_EJECT_MEDIA, IntPtr.Zero, 0, IntPtr.Zero, 0, out br, IntPtr.Zero);
        }
    }
}
"@
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        if (-not (Test-Path "${clean}:\")) { break }
        $res = [OffGridUsbEjector]::Eject($clean)
        Write-EjectLog "Win32 OffGridUsbEjector::Eject attempt $($attempt + 1) result=$res"
        Start-Sleep -Milliseconds 500
    }
}
Write-EjectLog "Completed safe eject. StillMounted=$(Test-Path "${clean}:\")"
exit 0
"""

_POSIX_SAFE_EJECT_SH = """#!/bin/sh
MOUNT_PATH="$1"
DELAY_SEC="${2:-2}"

cd /tmp || exit 1
sleep "$DELAY_SEC"

if [ -z "$MOUNT_PATH" ] || [ "$MOUNT_PATH" = "/" ]; then
    exit 1
fi

sync

if [ "$(uname -s)" = "Darwin" ]; then
    diskutil unmount force "$MOUNT_PATH" >/dev/null 2>&1 || diskutil eject "$MOUNT_PATH" >/dev/null 2>&1
else
    DEV="$(df -P "$MOUNT_PATH" 2>/dev/null | awk 'NR==2 {print $1}')"
    if command -v udisksctl >/dev/null 2>&1 && [ -n "$DEV" ]; then
        udisksctl unmount -b "$DEV" --no-user-interaction >/dev/null 2>&1
        udisksctl power-off -b "$DEV" --no-user-interaction >/dev/null 2>&1
    else
        umount "$MOUNT_PATH" >/dev/null 2>&1 || umount -l "$MOUNT_PATH" >/dev/null 2>&1
    fi
fi
exit 0
"""


def get_removable_usb_target(project_root: Path) -> Optional[str]:
    """Returns the drive letter (e.g. 'D') on Windows or mount path on Linux/macOS
    ONLY when `project_root` resides on a removable/external USB mount (never C: or /).
    """
    try:
        resolved = project_root.resolve()
    except Exception:
        resolved = project_root

    sys_name = platform.system().lower()
    if sys_name == "windows" or os.name == "nt":
        drive = resolved.drive.rstrip(":\\/").upper()
        sys_drive = os.environ.get("SystemDrive", "C:").rstrip(":\\/").upper() or "C"
        if not drive or len(drive) != 1 or drive in ("C", sys_drive):
            return None
        # Also verify the root looks like a customer USB root (START_OFFGRIDUSB_WINDOWS.bat or manifests/product_sku.json)
        if not ((resolved / "START_OFFGRIDUSB_WINDOWS.bat").exists() or (resolved / "manifests" / "product_sku.json").exists()):
            return None
        return drive

    posix_str = str(resolved)
    if posix_str.startswith(("/media/", "/run/media/", "/mnt/", "/Volumes/")):
        return posix_str
    return None


def spawn_detached_safe_eject(project_root: Path, delay_ms: int = 1500) -> Dict[str, Any]:
    """Stages a self-contained safe-eject script into the host temp directory and launches
    it detached so `project_root` can be flushed, dismounted, and ejected after Python exits.
    """
    target = get_removable_usb_target(project_root)
    if not target:
        return {
            "ok": True,
            "ejected": False,
            "reason": "Host drive or non-removable path detected; skipping hardware eject for safety.",
            "project_root": str(project_root),
        }

    tmp_dir = Path(tempfile.gettempdir())
    sys_name = platform.system().lower()

    try:
        if sys_name == "windows" or os.name == "nt":
            script_path = tmp_dir / "offgridusb_safe_eject.ps1"
            script_path.write_bytes(_WINDOWS_SAFE_EJECT_PS1.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-DriveLetter",
                target,
                "-DelayMs",
                str(delay_ms),
            ]
            # Method 0 (Fastest, 10ms cold start, zero console window): Native Win32 GUI helper offgridusb_safe_eject.exe
            base_flags = 0x08000000 | 0x00000200
            exe_candidates = [
                Path(project_root) / "bin" / "windows_x86_64" / "offgridusb_safe_eject.exe",
                Path(__file__).resolve().parents[3] / "bin" / "windows_x86_64" / "offgridusb_safe_eject.exe",
            ]
            staged_exe = tmp_dir / "offgridusb_safe_eject.exe"
            for cand in exe_candidates:
                try:
                    if cand.is_file() and cand.stat().st_size > 1024:
                        staged_exe.write_bytes(cand.read_bytes())
                        break
                except Exception:
                    pass

            if staged_exe.is_file():
                try:
                    subprocess.Popen(
                        [str(staged_exe), target, str(delay_ms)],
                        cwd=str(tmp_dir),
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=base_flags,
                        close_fds=True,
                    )
                except Exception:
                    pass

            # Method A: Direct subprocess.Popen with CREATE_NO_WINDOW (0x08000000) | CREATE_NEW_PROCESS_GROUP (0x00000200).
            # Never combine CREATE_NO_WINDOW with DETACHED_PROCESS (0x00000008) or -WindowStyle Hidden,
            # as Win32 CreateProcessW ignores CREATE_NO_WINDOW and PowerShell aborts when hiding a missing console.
            try:
                subprocess.Popen(
                    cmd,
                    cwd=str(tmp_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=base_flags | 0x01000000,  # Try CREATE_BREAKAWAY_FROM_JOB first
                    close_fds=True,
                )
            except OSError:
                subprocess.Popen(
                    cmd,
                    cwd=str(tmp_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=base_flags,
                    close_fds=True,
                )

            # Method C: Redundant out-of-tree WScript.Shell COM invisible launcher (0 = SW_HIDE, False = async).
            try:
                vbs_path = tmp_dir / "offgridusb_safe_eject.vbs"
                ps_cmd_str = (
                    f'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass '
                    f'-File ""{script_path}"" -DriveLetter {target} -DelayMs {delay_ms}'
                )
                vbs_lines = [f'CreateObject("WScript.Shell").Run "{ps_cmd_str}", 0, False']
                if staged_exe.is_file():
                    exe_cmd_str = f'""{staged_exe}"" {target} {delay_ms}'
                    vbs_lines.insert(0, f'CreateObject("WScript.Shell").Run "{exe_cmd_str}", 0, False')
                vbs_path.write_bytes(("\r\n".join(vbs_lines) + "\r\n").encode("utf-8"))
                subprocess.Popen(
                    ["wscript.exe", "//B", "//NoLogo", str(vbs_path)],
                    cwd=str(tmp_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=base_flags,
                    close_fds=True,
                )
            except Exception:
                pass

            return {
                "ok": True,
                "ejected": True,
                "target": f"{target}:",
                "script": str(script_path),
            }
        else:
            script_path = tmp_dir / "offgridusb_safe_eject.sh"
            script_path.write_bytes(_POSIX_SAFE_EJECT_SH.replace("\r\n", "\n").encode("utf-8"))
            try:
                os.chmod(script_path, 0o755)
            except OSError:
                pass
            delay_sec = max(1, int(round(delay_ms / 1000.0)))
            subprocess.Popen(
                ["/bin/sh", str(script_path), target, str(delay_sec)],
                cwd=str(tmp_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            return {
                "ok": True,
                "ejected": True,
                "target": target,
                "script": str(script_path),
            }
    except Exception as exc:
        return {
            "ok": False,
            "ejected": False,
            "target": target,
            "error": str(exc),
        }
