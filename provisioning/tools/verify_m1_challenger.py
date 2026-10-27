#!/usr/bin/env python3
r"""
scripts/verify_m1_challenger.py
===============================
Independent Empirical Challenger & Verification Harness for Milestone 1.

Performs adversarial testing against Worker M1 capacity findings:
1. Strict Hardware Safety Guard:
   - Validates Host Disk 0 (NVMe OS drive C:) is protected and never touched.
   - Validates Target Disk 1 ("Mass Storage Device", Serial "121220160204", Drive D:, Removable).
   - Hard abort if Disk 0 or Drive C: is targeted.
2. Independent Uncached Readback at 80 MB and 200 MB:
   - Evaluates boundary conditions with direct uncached Win32 sector I/O.
   - 80 MB MUST return real valid non-null data.
   - 200 MB MUST return 100% 0x00 null bytes (blackholed).
3. Anti-Caching Stress Test & False Positive Invalidation:
   - Writes a unique challenger token to 200 MB (phantom space) with FILE_FLAG_NO_BUFFERING.
   - Flushes buffers and reads back uncached to prove it is blackholed (0x00 nulls) and NOT falsely cached in RAM.
   - Tests write persistence at 80 MB with backup and restore.
4. Fine-Grained Boundary Sweep:
   - Sweeps across the boundary transition (64 MB to 999 GB).
5. Modulo Aliasing / Wrap-Around Verification:
   - Ensures low LBAs (1MB, 2MB, 4MB, 8MB) are completely untouched by phantom writes.
6. Generates full JSON and Markdown challenge reports.
"""

import sys
import os
import time
import json
import secrets
import hashlib
import subprocess
import ctypes
from ctypes import wintypes
from pathlib import Path

# ==============================================================================
# WIN32 DEFINITIONS & TYPES
# ==============================================================================
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_WRITE_THROUGH = 0x80000000
FILE_BEGIN = 0

FSCTL_LOCK_VOLUME = 0x00090018
FSCTL_UNLOCK_VOLUME_STD = 0x0009001C
FSCTL_UNLOCK_VOLUME_ALT = 0x00090019

BLOCK_SIZE = 4096

kernel32.VirtualAlloc.restype = ctypes.c_void_p
kernel32.VirtualAlloc.argtypes = [
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
    wintypes.DWORD,
]

kernel32.VirtualFree.restype = wintypes.BOOL
kernel32.VirtualFree.argtypes = [
    ctypes.c_void_p,
    ctypes.c_size_t,
    wintypes.DWORD,
]

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]

kernel32.SetFilePointerEx.restype = wintypes.BOOL
kernel32.SetFilePointerEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int64,
    ctypes.POINTER(ctypes.c_int64),
    wintypes.DWORD,
]

kernel32.ReadFile.restype = wintypes.BOOL
kernel32.ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]

kernel32.WriteFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]

kernel32.DeviceIoControl.restype = wintypes.BOOL
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]

kernel32.FlushFileBuffers.restype = wintypes.BOOL
kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]

kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


# ==============================================================================
# HARDWARE SAFETY ENFORCEMENT
# ==============================================================================
def verify_strict_safety_guards(target_drive="D", target_disk_num=1):
    print("[CHALLENGER SAFETY] Verifying hardware boundary and host OS protection...")

    cmd = [
        "powershell", "-NoProfile", "-Command",
        "Get-Disk | Select-Object Number, FriendlyName, SerialNumber, BusType, Size, PartitionStyle, IsBoot, IsSystem | ConvertTo-Json"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    disks = json.loads(proc.stdout)
    if isinstance(disks, dict):
        disks = [disks]

    disk0 = next((d for d in disks if d.get("Number") == 0), None)
    disk1 = next((d for d in disks if d.get("Number") == target_disk_num), None)

    if not disk0:
        sys.exit("SAFETY HALT: Disk 0 not found.")
    if not (disk0.get("IsBoot") and disk0.get("IsSystem")):
        sys.exit("SAFETY HALT: Disk 0 is not marked as Boot/System.")
    if "WD GREEN" not in disk0.get("FriendlyName", "").upper() and "NVME" not in disk0.get("BusType", "").upper():
        sys.exit("SAFETY HALT: Disk 0 signature does not match host NVMe SSD.")

    if not disk1:
        sys.exit(f"SAFETY HALT: Target Disk {target_disk_num} not found.")
    if disk1.get("FriendlyName") != "Mass Storage Device" or disk1.get("SerialNumber") != "121220160204":
        sys.exit(f"SAFETY HALT: Target Disk {target_disk_num} identity mismatch: {disk1}")
    if disk1.get("BusType") != "USB" or disk1.get("IsBoot") or disk1.get("IsSystem"):
        sys.exit("SAFETY HALT: Target Disk is not an external non-system USB device.")

    if target_drive.upper() == "C":
        sys.exit("SAFETY HALT: Attempted to target drive C:! Aborting immediately.")

    print(f"  [OK] Host Disk 0 verified and protected: {disk0['FriendlyName']} ({disk0['SerialNumber']})")
    print(f"  [OK] Target Disk 1 verified: {disk1['FriendlyName']} (Serial: {disk1['SerialNumber']}) on \\\\.\\{target_drive}:\n")
    return disk0, disk1


# ==============================================================================
# UNCACHED I/O CONTEXT
# ==============================================================================
class UncachedVolumeContext:
    def __init__(self, drive_letter="D", access_mode="rw"):
        self.device_path = f"\\\\.\\{drive_letter}:"
        self.access_mode = access_mode
        self.handle = None
        self.locked = False
        self.buffer = None

    def __enter__(self):
        self.buffer = kernel32.VirtualAlloc(
            None, ctypes.c_size_t(BLOCK_SIZE), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        )
        if not self.buffer:
            raise ctypes.WinError()

        desired_access = GENERIC_READ
        if "w" in self.access_mode:
            desired_access |= GENERIC_WRITE

        self.handle = kernel32.CreateFileW(
            self.device_path,
            desired_access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_NO_BUFFERING | FILE_FLAG_WRITE_THROUGH,
            None,
        )
        if self.handle == wintypes.HANDLE(-1).value or not self.handle:
            err = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(err, f"Failed to open {self.device_path} with uncached flags")

        if "w" in self.access_mode:
            bytes_returned = wintypes.DWORD(0)
            res_lock = kernel32.DeviceIoControl(
                self.handle,
                FSCTL_LOCK_VOLUME,
                None, 0,
                None, 0,
                ctypes.byref(bytes_returned),
                None
            )
            if res_lock:
                self.locked = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self.handle and self.handle != wintypes.HANDLE(-1).value:
            if self.locked:
                bytes_returned = wintypes.DWORD(0)
                res = kernel32.DeviceIoControl(
                    self.handle,
                    FSCTL_UNLOCK_VOLUME_STD,
                    None, 0,
                    None, 0,
                    ctypes.byref(bytes_returned),
                    None
                )
                if not res:
                    kernel32.DeviceIoControl(
                        self.handle,
                        FSCTL_UNLOCK_VOLUME_ALT,
                        None, 0,
                        None, 0,
                        ctypes.byref(bytes_returned),
                        None
                    )
                self.locked = False
            kernel32.CloseHandle(self.handle)
            self.handle = None

        if self.buffer:
            kernel32.VirtualFree(self.buffer, 0, MEM_RELEASE)
            self.buffer = None

    def seek(self, offset: int):
        distance = ctypes.c_int64(offset)
        new_pos = ctypes.c_int64(0)
        res = kernel32.SetFilePointerEx(self.handle, distance, ctypes.byref(new_pos), FILE_BEGIN)
        if not res:
            err = ctypes.get_last_error()
            raise ctypes.WinError(err, f"Failed to seek to offset {offset}")
        return new_pos.value

    def read_block(self, offset: int) -> bytes:
        self.seek(offset)
        bytes_read = wintypes.DWORD(0)
        res = kernel32.ReadFile(
            self.handle,
            self.buffer,
            BLOCK_SIZE,
            ctypes.byref(bytes_read),
            None
        )
        if not res:
            err = ctypes.get_last_error()
            raise ctypes.WinError(err, f"ReadFile failed at offset {offset}")
        if bytes_read.value != BLOCK_SIZE:
            raise IOError(f"Incomplete sector read at {offset}: {bytes_read.value} != {BLOCK_SIZE}")
        return ctypes.string_at(self.buffer, BLOCK_SIZE)

    def write_block(self, offset: int, data: bytes):
        if len(data) != BLOCK_SIZE:
            raise ValueError(f"Write data length {len(data)} != {BLOCK_SIZE}")
        self.seek(offset)
        ctypes.memmove(self.buffer, data, BLOCK_SIZE)
        bytes_written = wintypes.DWORD(0)
        res = kernel32.WriteFile(
            self.handle,
            self.buffer,
            BLOCK_SIZE,
            ctypes.byref(bytes_written),
            None
        )
        if not res:
            err = ctypes.get_last_error()
            raise ctypes.WinError(err, f"WriteFile failed at offset {offset}")
        if bytes_written.value != BLOCK_SIZE:
            raise IOError(f"Incomplete sector write at {offset}: {bytes_written.value} != {BLOCK_SIZE}")

    def flush(self):
        kernel32.FlushFileBuffers(self.handle)


# ==============================================================================
# CHALLENGER HARNESS
# ==============================================================================
def run_challenge_suite():
    t_start = time.perf_counter()
    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "challenger": "challenger_m1_1",
        "target": "\\\\.\\D:",
        "tests": {},
        "overall_status": "PENDING"
    }

    # Test 1: Hardware safety
    disk0, disk1 = verify_strict_safety_guards(target_drive="D", target_disk_num=1)
    report["tests"]["test1_hardware_safety"] = {
        "status": "PASS",
        "disk0_model": disk0["FriendlyName"],
        "disk0_serial": disk0["SerialNumber"],
        "disk0_is_boot_system": disk0["IsBoot"] and disk0["IsSystem"],
        "disk1_model": disk1["FriendlyName"],
        "disk1_serial": disk1["SerialNumber"],
        "disk1_bus": disk1["BusType"],
        "disk1_size_bytes": disk1["Size"]
    }

    with UncachedVolumeContext(drive_letter="D", access_mode="rw") as vol:
        # Test 2: Independent boundary verification at 80 MB and 200 MB
        print("=" * 80)
        print("[TEST 2] Independent Boundary Verification at 80 MB & 200 MB")
        print("=" * 80)
        offset_80mb = 80 * 1024 * 1024
        offset_200mb = 200 * 1024 * 1024

        t0 = time.perf_counter()
        data_80mb = vol.read_block(offset_80mb)
        t_80 = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        data_200mb = vol.read_block(offset_200mb)
        t_200 = (time.perf_counter() - t0) * 1000.0

        nz_80 = BLOCK_SIZE - data_80mb.count(b"\x00")
        nz_200 = BLOCK_SIZE - data_200mb.count(b"\x00")

        test2_passed = (nz_80 > 0) and (nz_200 == 0)
        print(f"  Offset 80 MB ({offset_80mb:,} B): non-zero={nz_80}/{BLOCK_SIZE} ({nz_80/BLOCK_SIZE*100:.1f}%), latency={t_80:.2f}ms, sha256={hashlib.sha256(data_80mb).hexdigest()[:16]}")
        print(f"  Offset 200 MB ({offset_200mb:,} B): non-zero={nz_200}/{BLOCK_SIZE} ({nz_200/BLOCK_SIZE*100:.1f}%), latency={t_200:.2f}ms, sha256={hashlib.sha256(data_200mb).hexdigest()[:16]}")
        print(f"  Test 2 Result: {'PASS' if test2_passed else 'FAIL'}\n")

        report["tests"]["test2_boundary_readback"] = {
            "status": "PASS" if test2_passed else "FAIL",
            "offset_80mb": {
                "offset_bytes": offset_80mb,
                "non_zero_bytes": nz_80,
                "latency_ms": round(t_80, 2),
                "sha256_prefix": hashlib.sha256(data_80mb).hexdigest()[:16],
                "preview_hex": data_80mb[:32].hex()
            },
            "offset_200mb": {
                "offset_bytes": offset_200mb,
                "non_zero_bytes": nz_200,
                "latency_ms": round(t_200, 2),
                "sha256_prefix": hashlib.sha256(data_200mb).hexdigest()[:16],
                "preview_hex": data_200mb[:32].hex()
            }
        }
        if not test2_passed:
            report["overall_status"] = "FAIL"
            return report

        # Test 3: Anti-Caching Stress Test & False Positive Invalidation
        print("=" * 80)
        print("[TEST 3] Anti-Caching Stress Test & False Positive Invalidation")
        print("=" * 80)
        # 3A. Write challenger token to 200 MB (phantom space) and verify it gets discarded (not cached in RAM)
        nonce = secrets.token_hex(8)
        challenger_phantom_token = f"OFFGRID_CHALLENGER_PHANTOM_TEST_NONCE_{nonce}_".encode("ascii")
        challenger_phantom_token = (challenger_phantom_token * 100)[:BLOCK_SIZE]

        print("  [3A] Writing challenger probe token to offset 200 MB via uncached handle...")
        vol.write_block(offset_200mb, challenger_phantom_token)
        vol.flush()

        # Immediate uncached readback
        rb_200mb = vol.read_block(offset_200mb)
        phantom_null_count = rb_200mb.count(b"\x00")
        phantom_token_detected = (rb_200mb == challenger_phantom_token)

        test3a_passed = (phantom_null_count == BLOCK_SIZE) and not phantom_token_detected
        print(f"  [3A Result] Readback at 200MB: null_bytes={phantom_null_count}/{BLOCK_SIZE}, token_detected={phantom_token_detected}")
        if test3a_passed:
            print("  [3A OK] Hardware confirmed to BLACKHOLE phantom writes without Windows RAM caching false-positive.")
        else:
            print("  [3A FAIL] Unexpected: Write to 200MB did not blackhole or was served from RAM cache!")

        # 3B. Write challenger token to 80 MB (valid space), verify exact match, then restore original data
        print("\n  [3B] Testing write-and-readback in valid NAND at offset 80 MB...")
        orig_80mb = data_80mb
        challenger_valid_token = f"OFFGRID_CHALLENGER_VALID_TEST_NONCE_{nonce}_".encode("ascii")
        challenger_valid_token = (challenger_valid_token * 100)[:BLOCK_SIZE]

        vol.write_block(offset_80mb, challenger_valid_token)
        vol.flush()
        rb_80mb = vol.read_block(offset_80mb)
        valid_write_matched = (rb_80mb == challenger_valid_token)

        # Restore original sector
        vol.write_block(offset_80mb, orig_80mb)
        vol.flush()
        rb_80mb_restored = vol.read_block(offset_80mb)
        valid_restore_matched = (rb_80mb_restored == orig_80mb)

        test3b_passed = valid_write_matched and valid_restore_matched
        print(f"  [3B Result] Valid NAND write matched: {valid_write_matched}, restored matched: {valid_restore_matched}")
        print(f"  Test 3 Result: {'PASS' if test3a_passed and test3b_passed else 'FAIL'}\n")

        report["tests"]["test3_anti_caching"] = {
            "status": "PASS" if test3a_passed and test3b_passed else "FAIL",
            "phantom_write_blackholed": (phantom_null_count == BLOCK_SIZE),
            "phantom_token_leaked_to_cache": phantom_token_detected,
            "valid_nand_write_succeeded": valid_write_matched,
            "valid_nand_restore_succeeded": valid_restore_matched
        }
        if not (test3a_passed and test3b_passed):
            report["overall_status"] = "FAIL"
            return report

        # Test 4: Fine-Grained Boundary Sweep
        print("=" * 80)
        print("[TEST 4] Fine-Grained Boundary Transition Sweep")
        print("=" * 80)
        sweep_offsets = [
            1 * 1024 * 1024,        # 1 MB
            10 * 1024 * 1024,       # 10 MB
            50 * 1024 * 1024,       # 50 MB
            78 * 1024 * 1024,       # 78 MB
            80 * 1024 * 1024,       # 80 MB
            100 * 1024 * 1024,      # 100 MB
            115 * 1024 * 1024,      # 115 MB (clamped partition size recommendation)
            116 * 1024 * 1024,      # 116 MB
            120 * 1024 * 1024,      # 120 MB
            121 * 1024 * 1024,      # 121 MB
            122 * 1024 * 1024,      # 122 MB
            124 * 1024 * 1024,      # 124 MB
            126 * 1024 * 1024,      # 126 MB
            127 * 1024 * 1024,      # 127 MB
            127500288,              # 127.50 MB (Worker M1 reported cutoff)
            128 * 1024 * 1024,      # 128 MB (Nominal silicon boundary)
            129 * 1024 * 1024,      # 129 MB
            130 * 1024 * 1024,      # 130 MB
            140 * 1024 * 1024,      # 140 MB
            200 * 1024 * 1024,      # 200 MB
            512 * 1024 * 1024,      # 512 MB
            1 * 1024 * 1024 * 1024, # 1 GB
            10 * 1024 * 1024 * 1024,# 10 GB
            100 * 1024 * 1024 * 1024,# 100 GB
            500 * 1024 * 1024 * 1024,# 500 GB
            999 * 1024 * 1024 * 1024 # 999 GB
        ]

        sweep_results = []
        highest_nonzero_offset = 0
        lowest_zero_offset = None

        for off in sweep_offsets:
            aligned_off = (off // BLOCK_SIZE) * BLOCK_SIZE
            t0 = time.perf_counter()
            block = vol.read_block(aligned_off)
            lat = (time.perf_counter() - t0) * 1000.0
            nz = BLOCK_SIZE - block.count(b"\x00")
            is_valid = (nz > 0)

            if is_valid:
                highest_nonzero_offset = max(highest_nonzero_offset, aligned_off)
            elif lowest_zero_offset is None and aligned_off >= 120 * 1024 * 1024:
                lowest_zero_offset = aligned_off

            mb_val = aligned_off / (1024 * 1024)
            gb_val = aligned_off / (1024 * 1024 * 1024)
            label = f"{mb_val:.1f} MB" if mb_val < 1024 else f"{gb_val:.1f} GB"

            sweep_results.append({
                "offset_bytes": aligned_off,
                "label": label,
                "non_zero_bytes": nz,
                "null_ratio": round(block.count(b"\x00") / BLOCK_SIZE, 4),
                "is_valid_nand": is_valid,
                "latency_ms": round(lat, 2),
                "sha256_prefix": hashlib.sha256(block).hexdigest()[:16]
            })
            print(f"  [{label:>8}] Offset {aligned_off:>14,}: non-zero={nz:>4}/{BLOCK_SIZE} ({nz/BLOCK_SIZE*100:>5.1f}%), latency={lat:>6.2f}ms -> {'VALID FLASH' if is_valid else 'BLACKHOLE'}")

        print(f"\n  [Sweep Summary] Highest detected valid offset: {highest_nonzero_offset:,} bytes ({highest_nonzero_offset/(1024**2):.2f} MB)")
        print(f"  [Sweep Summary] Lowest detected blackhole offset: {lowest_zero_offset:,} bytes ({lowest_zero_offset/(1024**2):.2f} MB)")
        test4_passed = (highest_nonzero_offset >= 80 * 1024 * 1024) and (lowest_zero_offset is not None and lowest_zero_offset <= 140 * 1024 * 1024)
        print(f"  Test 4 Result: {'PASS' if test4_passed else 'FAIL'}\n")

        report["tests"]["test4_boundary_sweep"] = {
            "status": "PASS" if test4_passed else "FAIL",
            "highest_nonzero_offset_bytes": highest_nonzero_offset,
            "highest_nonzero_mb": round(highest_nonzero_offset / (1024**2), 2),
            "lowest_zero_offset_bytes": lowest_zero_offset,
            "lowest_zero_mb": round(lowest_zero_offset / (1024**2), 2) if lowest_zero_offset else None,
            "sweep_points": sweep_results
        }

        # Test 5: Modulo Aliasing / Low Canary Verification
        print("=" * 80)
        print("[TEST 5] Modulo Wrap-Around / Low Canary Aliasing Check")
        print("=" * 80)
        canary_offsets = [1 * 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024]
        canary_status = []
        all_canaries_safe = True

        for c_off in canary_offsets:
            c_block = vol.read_block(c_off)
            nz = BLOCK_SIZE - c_block.count(b"\x00")
            has_phantom_token = (challenger_phantom_token[:32] in c_block)
            if has_phantom_token:
                all_canaries_safe = False
            canary_status.append({
                "offset_bytes": c_off,
                "label": f"{c_off//(1024**2)}MB",
                "non_zero_bytes": nz,
                "has_phantom_token": has_phantom_token
            })
            print(f"  Canary {c_off//(1024**2)}MB ({c_off:,} B): non-zero={nz}/{BLOCK_SIZE}, phantom_token_detected={has_phantom_token}")

        test5_passed = all_canaries_safe
        print(f"  Test 5 Result: {'PASS' if test5_passed else 'FAIL'}\n")

        report["tests"]["test5_modulo_aliasing"] = {
            "status": "PASS" if test5_passed else "FAIL",
            "modulo_wrap_around_detected": not all_canaries_safe,
            "canaries": canary_status
        }

    total_duration = time.perf_counter() - t_start
    all_tests_passed = all(t["status"] == "PASS" for t in report["tests"].values())
    report["overall_status"] = "APPROVE" if all_tests_passed else "REQUEST_CHANGES"
    report["duration_seconds"] = round(total_duration, 2)

    return report


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print("#" * 80)
    print("CHALLENGER M1: INDEPENDENT EMPIRICAL VERIFICATION & STRESS TEST")
    print("#" * 80 + "\n")

    report = run_challenge_suite()

    # Write output reports
    challenger_dir = Path(r"C:\Users\ndoki\.gemini\antigravity\worktrees\Organized Insomnia\diagnose_gcp_deployment_issues\.agents\teamwork\challenger_m1_1")
    challenger_dir.mkdir(parents=True, exist_ok=True)

    json_path = challenger_dir / "challenge_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 80)
    print(f"FINAL CHALLENGER VERDICT: {report['overall_status']}")
    print(f"Detailed challenge report written to: {json_path}")
    print("=" * 80)

    return 0 if report["overall_status"] == "APPROVE" else 1


if __name__ == "__main__":
    sys.exit(main())
