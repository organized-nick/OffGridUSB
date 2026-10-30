#!/usr/bin/env python3
"""
AssetCacheManager.py - Host Asset Cache Manager & Binary Magic Verifier
Part of the OffGridUSB Factory Provisioning Suite.
"""

import os
import sys
import json
import argparse
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SEARCH_PATHS = [
    _REPO_ROOT / "cache",
    _REPO_ROOT / "data",
    _REPO_ROOT / "OFFGRIDUSB_CONSUMER_READY" / "data",
    _REPO_ROOT / "offgridUSB.com" / "data",
    _REPO_ROOT / "models_staging",
    _REPO_ROOT / "zim_Builds",
]

ZIM_MAGIC = b"\x5A\x49\x4D\x04"
GGUF_MAGIC = b"GGUF"


def verify_magic_header(file_path: Path) -> dict:
    """Verifies that the target file exists and starts with ZIM\\x04 or GGUF."""
    path = Path(file_path)
    if not path.is_file():
        return {
            "valid": False,
            "path": str(path),
            "error": "File does not exist",
            "magic": None,
        }

    try:
        with open(path, "rb") as f:
            header = f.read(4)

        if len(header) < 4:
            return {
                "valid": False,
                "path": str(path),
                "error": "File smaller than 4 bytes",
                "magic": None,
            }

        if header == ZIM_MAGIC:
            return {
                "valid": True,
                "path": str(path),
                "type": "ZIM",
                "magic": "ZIM\\x04",
                "size_bytes": path.stat().st_size,
            }
        elif header == GGUF_MAGIC:
            return {
                "valid": True,
                "path": str(path),
                "type": "GGUF",
                "magic": "GGUF",
                "size_bytes": path.stat().st_size,
            }
        else:
            return {
                "valid": False,
                "path": str(path),
                "error": f"Invalid header: {header!r}",
                "magic": header.hex(),
            }
    except Exception as e:
        return {
            "valid": False,
            "path": str(path),
            "error": str(e),
            "magic": None,
        }


def find_asset_in_cache(filename: str, extra_search_paths=None) -> Path | None:
    search_dirs = []
    if extra_search_paths:
        search_dirs.extend([Path(p) for p in extra_search_paths])
    search_dirs.extend(DEFAULT_SEARCH_PATHS)

    for base_dir in search_dirs:
        if not base_dir.exists():
            continue

        # Check direct
        candidate = base_dir / filename
        if candidate.is_file():
            chk = verify_magic_header(candidate)
            if chk["valid"]:
                return candidate

        # Check subdirectories
        for sub in ["zim", "models", "content"]:
            candidate_sub = base_dir / sub / filename
            if candidate_sub.is_file():
                chk = verify_magic_header(candidate_sub)
                if chk["valid"]:
                    return candidate_sub

    return None


def get_sku_inventory(
    product_sku: str,
    products_json: Path,
    extra_cache_dirs=None,
    profile_name="Auto",
) -> dict:
    with open(products_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    matched = None
    for p in data.get("products", []):
        if p.get("sku") == product_sku or p.get("product_id") == product_sku:
            matched = p
            break

    if not matched:
        raise ValueError(f"SKU '{product_sku}' not found in {products_json}")

    profiles = matched.get("payload_profiles", {})
    if profile_name == "Auto":
        profile_key = "lean" if "lean" in profiles else "full"
    else:
        profile_key = profile_name

    profile_data = profiles.get(profile_key, profiles.get("full", {}))

    items = []
    all_available = True
    total_bytes = 0

    # Models
    for m in profile_data.get("models", []):
        found = find_asset_in_cache(m, extra_cache_dirs)
        if found:
            sz = found.stat().st_size
            total_bytes += sz
            items.append(
                {
                    "filename": m,
                    "type": "Model (GGUF)",
                    "size_bytes": sz,
                    "size_mb": round(sz / (1024 * 1024), 1),
                    "status": "AVAILABLE",
                    "magic": "GGUF",
                    "local_path": str(found),
                }
            )
        else:
            all_available = False
            items.append(
                {
                    "filename": m,
                    "type": "Model (GGUF)",
                    "size_bytes": 0,
                    "size_mb": 0.0,
                    "status": "MISSING",
                    "magic": "None",
                    "local_path": None,
                }
            )

    # ZIM archives
    for z in profile_data.get("zim_archives", []):
        found = find_asset_in_cache(z, extra_cache_dirs)
        if found:
            sz = found.stat().st_size
            total_bytes += sz
            items.append(
                {
                    "filename": z,
                    "type": "ZIM Archive",
                    "size_bytes": sz,
                    "size_mb": round(sz / (1024 * 1024), 1),
                    "status": "AVAILABLE",
                    "magic": "ZIM\\x04",
                    "local_path": str(found),
                }
            )
        else:
            all_available = False
            items.append(
                {
                    "filename": z,
                    "type": "ZIM Archive",
                    "size_bytes": 0,
                    "size_mb": 0.0,
                    "status": "MISSING",
                    "magic": "None",
                    "local_path": None,
                }
            )

    return {
        "sku": matched.get("sku"),
        "name": matched.get("name"),
        "profile": profile_key,
        "description": profile_data.get("description"),
        "all_available": all_available,
        "total_bytes": total_bytes,
        "total_gb": round(total_bytes / 1e9, 2),
        "target_usb_gb": matched.get("target_drive_size_gb"),
        "assets": items,
    }


def main():
    parser = argparse.ArgumentParser(
        description="OffGridUSB Asset Cache Manager & Magic Byte Verifier"
    )
    parser.add_argument("--verify", type=str, help="Verify magic header of a specific file")
    parser.add_argument("--sku", type=str, help="Audit cache for a specific product SKU")
    parser.add_argument(
        "--manifest",
        type=str,
        default=str(_REPO_ROOT / "manifests" / "products.json"),
        help="Path to products.json",
    )
    parser.add_argument("--cache-dir", type=str, action="append", help="Extra cache directory")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    if args.verify:
        res = verify_magic_header(Path(args.verify))
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            status = "PASS" if res["valid"] else "FAIL"
            print(f"[{status}] {res['path']}: {res.get('magic', 'Unknown')} ({res.get('error', '')})")
        sys.exit(0 if res["valid"] else 1)

    if args.sku:
        inv = get_sku_inventory(
            args.sku,
            Path(args.manifest),
            extra_cache_dirs=args.cache_dir,
        )
        if args.json:
            print(json.dumps(inv, indent=2))
        else:
            print(f"Asset Status for {inv['name']} ({inv['sku']}) [{inv['profile']} profile]:")
            print(f"Total Bytes: {inv['total_bytes']:,} ({inv['total_gb']} GB) | All Available: {inv['all_available']}")
            print("-" * 75)
            for a in inv["assets"]:
                print(f"  [{a['status']:<9}] {a['filename']:<42} {a['size_mb']:>8.1f} MB  {a['magic']}")
        sys.exit(0 if inv["all_available"] else 2)

    parser.print_help()


if __name__ == "__main__":
    main()
