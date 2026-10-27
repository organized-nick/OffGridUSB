#!/usr/bin/env python3
"""
SkuManifestGenerator.py - Generates manifests/product_sku.json for provisioned OffGridUSB drives.
"""

import sys
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path


def generate_sku_manifest(
    sku: str,
    products_json_path: Path,
    target_drive: str = "D:",
    filesystem: str = "exFAT",
    cluster_size_bytes: int = 131072,
    profile_name: str = "Auto",
    output_path: Path | None = None,
) -> dict:
    with open(products_json_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    matched = None
    for p in catalog.get("products", []):
        if p.get("sku") == sku or p.get("product_id") == sku:
            matched = p
            break

    if not matched:
        raise ValueError(f"SKU '{sku}' not found in {products_json_path}")

    profiles = matched.get("payload_profiles", {})
    if profile_name == "Auto":
        profile_key = "lean" if "lean" in profiles else "full"
    else:
        profile_key = profile_name

    profile_data = profiles.get(profile_key, profiles.get("full", {}))

    clean_drive = target_drive.replace(":", "").replace("\\", "").replace("/", "").upper()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
        "schema_version": "1.0",
        "sku": matched.get("sku"),
        "product_id": matched.get("product_id"),
        "name": matched.get("name"),
        "tagline": matched.get("tagline"),
        "tiers": matched.get("tiers"),
        "target_drive_size_gb": matched.get("target_drive_size_gb"),
        "min_drive_capacity_bytes": matched.get("min_drive_capacity_bytes"),
        "features": matched.get("active_features", []),
        "hidden_features": matched.get("hidden_features", []),
        "active_models": profile_data.get("models", []),
        "active_zim_archives": profile_data.get("zim_archives", []),
        "default_model": matched.get("default_model", ""),
        "services": {
            "command_center_port": 8000,
            "kiwix_port": 8081,
            "llama_port": 8082,
        },
        "provisioning": {
            "provisioned_at": now_utc,
            "provisioner_version": "1.0.0",
            "filesystem": filesystem,
            "cluster_size_bytes": cluster_size_bytes,
            "target_drive_letter": f"{clean_drive}:",
        },
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    return manifest


def main():
    parser = argparse.ArgumentParser(description="OffGridUSB SKU Manifest Generator")
    parser.add_argument("--sku", required=True, help="Product SKU (e.g. Product1, Product2, Product3)")
    parser.add_argument(
        "--manifest",
        default=r"C:\Users\ndoki\Desktop\offgridusb\OffGridUSB\manifests\products.json",
        help="Path to products.json",
    )
    parser.add_argument("--drive", default="D:", help="Target drive letter (e.g. D:)")
    parser.add_argument("--fs", default="exFAT", help="Filesystem type")
    parser.add_argument("--cluster-size", type=int, default=131072, help="Cluster size in bytes")
    parser.add_argument("--profile", default="Auto", help="Payload profile (lean, full, Auto)")
    parser.add_argument("--output", help="Output path for product_sku.json")

    args = parser.parse_args()
    manifest = generate_sku_manifest(
        sku=args.sku,
        products_json_path=Path(args.manifest),
        target_drive=args.drive,
        filesystem=args.fs,
        cluster_size_bytes=args.cluster_size,
        profile_name=args.profile,
        output_path=Path(args.output) if args.output else None,
    )

    if not args.output:
        print(json.dumps(manifest, indent=2))
    else:
        print(f"Generated {args.output} for {manifest['name']} ({manifest['sku']})")


if __name__ == "__main__":
    main()
