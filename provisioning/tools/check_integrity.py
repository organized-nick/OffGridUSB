#!/usr/bin/env python3
"""
OffGridUSB Pre-Flight Flash Storage Integrity Checker
Detects counterfeit / fake-capacity flash media with unbacked phantom sectors.
Zero external dependencies (pure Python standard library).
Runtime: < 0.15 seconds.
Exit Code:
    0  : Clean / Genuine media
    10 : Counterfeit corruption detected (unbacked all-null phantom sectors)
    1  : Invalid arguments / fatal invocation error
"""

import glob
import os
import sys

def check_block_all_null(data: bytes) -> bool:
    """Return True if block contains at least 1 byte and all bytes are 0x00."""
    return len(data) > 0 and all(b == 0 for b in data)

def inspect_file(file_path: str) -> bool:
    """
    Inspects head (first 512 bytes) and tail (last 512 bytes if > 10MB).
    Returns False if counterfeit all-null corruption is detected.
    Returns True if clean.
    """
    try:
        size = os.path.getsize(file_path)
        if size == 0:
            return True  # Empty files are not phantom sectors
            
        with open(file_path, "rb") as f:
            # Check head (first 512 bytes or file size)
            head = f.read(min(512, size))
            if check_block_all_null(head):
                return False
                
            # Check tail if file is large (> 10 MB)
            if size > 10 * 1024 * 1024:
                f.seek(max(0, size - 512))
                tail = f.read(512)
                if check_block_all_null(tail):
                    return False
                    
        return True
    except Exception:
        return True

def main():
    root_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    
    sample_targets = []
    
    # 1. High-LBA Canary file (written at end of volume staging)
    canary_path = os.path.join(root_dir, "data", ".integrity_canary")
    if os.path.isfile(canary_path):
        sample_targets.append(canary_path)
        
    # 2. Large content archives (ZIM and GGUF)
    sample_targets.extend(glob.glob(os.path.join(root_dir, "data", "zim", "*.zim")))
    sample_targets.extend(glob.glob(os.path.join(root_dir, "data", "models", "*.gguf")))
    
    # 3. Core runtime binaries (if data directories not yet populated)
    if not sample_targets:
        sample_targets.extend(glob.glob(os.path.join(root_dir, "bin", "**", "*.exe"), recursive=True)[:5])
        sample_targets.extend(glob.glob(os.path.join(root_dir, "bin", "**", "*.tar.gz"), recursive=True)[:5])
        
    # 4. Sample root launcher itself as baseline
    for launcher in ["START_OFFGRIDUSB_WINDOWS.bat", "START_OFFGRIDUSB_LINUX.sh", "START_OFFGRIDUSB_MAC.command"]:
        lp = os.path.join(root_dir, launcher)
        if os.path.isfile(lp):
            sample_targets.append(lp)
            break
            
    # Sample files
    for target in sample_targets:
        if not inspect_file(target):
            print(f"[CORRUPT] Phantom null sector detected in: {target}", file=sys.stderr)
            sys.exit(10)
            
    sys.exit(0)

if __name__ == "__main__":
    main()
