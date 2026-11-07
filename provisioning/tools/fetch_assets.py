"""Controlled Offline Asset Provisioner & Verifier (F-42, F-43).

100% Pure Python Standard Library.
Downloads and verifies Internet-in-a-Box (.zim) encyclopedias and GGUF AI models
defined in `manifests/zim.json` and `manifests/models.json`.

Usage:
    python -m emyrge.assets.fetch_assets --list
    python -m emyrge.assets.fetch_assets --dry-run --tier 2
    python -m emyrge.assets.fetch_assets --verify
    python -m emyrge.assets.fetch_assets --tier 0
    python -m emyrge.assets.fetch_assets --zim-only --tier 2
    python -m emyrge.assets.fetch_assets --id wikipedia-medicine-mini
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

ZIM_MAGICS = (0x044D495A, 0x5A494D04)
USER_AGENT = "OffGridUSB-Provisioner/0.1 (+https://offgridusb.com)"


def _default_root() -> Path:
    # provisioning/tools/fetch_assets.py -> project root is two levels up.
    return Path(__file__).resolve().parents[2]


def load_manifests(project_root: Optional[Path] = None) -> Dict[str, Any]:
    root = project_root or _default_root()
    models_path = root / "manifests" / "models.json"
    zim_path = root / "manifests" / "zim.json"
    products_path = root / "manifests" / "products.json"

    models_data = json.loads(models_path.read_text(encoding="utf-8")) if models_path.is_file() else {"models": []}
    zim_data = json.loads(zim_path.read_text(encoding="utf-8")) if zim_path.is_file() else {"archives": []}
    products_data = json.loads(products_path.read_text(encoding="utf-8")) if products_path.is_file() else {"products": []}
    return {
        "models": models_data.get("models", []),
        "archives": zim_data.get("archives", []),
        "products": products_data.get("products", []),
    }


def _check_magic_header(path: Path) -> bool:
    """Validates binary magic header for .gguf ('GGUF') or .zim ('ZIM\\x04')."""
    if not path.is_file() or path.stat().st_size < 16:
        return False
    suffix = path.suffix.lower()
    try:
        with open(path, "rb") as f:
            hdr = f.read(4)
        if len(hdr) < 4:
            return False
        if suffix == ".gguf":
            return hdr == b"GGUF"
        if suffix == ".zim":
            magic = struct.unpack("<I", hdr)[0]
            return magic in ZIM_MAGICS
        return True
    except OSError:
        return False


def verify_assets(project_root: Optional[Path] = None) -> Dict[str, Any]:
    root = project_root or _default_root()
    manifests = load_manifests(root)
    models_dir = root / "data" / "models"
    zim_dir = root / "data" / "zim"

    found_models: List[Dict[str, Any]] = []
    if models_dir.is_dir():
        for p in sorted(models_dir.glob("*.gguf")):
            found_models.append(
                {
                    "filename": p.name,
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "header_valid": _check_magic_header(p),
                }
            )

    found_zims: List[Dict[str, Any]] = []
    if zim_dir.is_dir():
        for p in sorted(zim_dir.glob("*.zim")):
            found_zims.append(
                {
                    "filename": p.name,
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "header_valid": _check_magic_header(p),
                }
            )

    return {
        "ok": True,
        "catalog_models_count": len(manifests["models"]),
        "catalog_zim_count": len(manifests["archives"]),
        "staged_models": found_models,
        "staged_zims": found_zims,
    }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _stream_download(url: str, dest: Path, quiet_curl: bool = False) -> None:
    """Streams a remote file to `dest.part` with progress logging and renames atomically."""
    part_path = dest.with_suffix(dest.suffix + ".part")
    existing_bytes = part_path.stat().st_size if part_path.is_file() else 0

    curl_bin = shutil.which("curl")
    if curl_bin:
        curl_cmd = [
            curl_bin,
            "-L",
            "-f",
            "--retry", "5",
            "--retry-connrefused",
            "--retry-delay", "2",
            "--connect-timeout", "30",
            "-A", USER_AGENT,
        ]
        if quiet_curl:
            curl_cmd.extend(["-s", "-S"])
        if existing_bytes > 0:
            curl_cmd.extend(["-C", "-"])
        curl_cmd.extend(["-o", str(part_path), url])
        proc = subprocess.run(curl_cmd)
        if proc.returncode != 0:
            if proc.returncode == 33 and existing_bytes > 0:
                print(f"    [WARN] Server rejected byte range (curl exit code 33). Retrying clean: {url}", flush=True)
                if part_path.is_file():
                    part_path.unlink()
                clean_cmd = [
                    curl_bin,
                    "-L",
                    "-f",
                    "--retry", "5",
                    "--retry-connrefused",
                    "--retry-delay", "2",
                    "--connect-timeout", "30",
                    "-A", USER_AGENT,
                ]
                if quiet_curl:
                    clean_cmd.extend(["-s", "-S"])
                clean_cmd.extend(["-o", str(part_path), url])
                proc = subprocess.run(clean_cmd)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Download failed for {url} (curl exit code {proc.returncode}). "
                    f"Partial file preserved at: {part_path}"
                )
        part_path.replace(dest)
        return

    headers = {"User-Agent": USER_AGENT}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = getattr(resp, "status", 200)
            mode = "ab" if (existing_bytes > 0 and status == 206) else "wb"
            if mode == "wb":
                existing_bytes = 0

            content_len = resp.headers.get("Content-Length")
            total_bytes = (int(content_len) + existing_bytes) if content_len and content_len.isdigit() else 0

            downloaded = existing_bytes
            last_print = 0.0
            with open(part_path, mode) as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if now - last_print >= 1.0:
                        mb_done = downloaded / (1024 * 1024)
                        if total_bytes > 0:
                            pct = min(100.0, (downloaded / total_bytes) * 100.0)
                            mb_total = total_bytes / (1024 * 1024)
                            print(f"    ... {mb_done:,.1f} / {mb_total:,.1f} MB ({pct:.1f}%)", flush=True)
                        else:
                            print(f"    ... {mb_done:,.1f} MB downloaded", flush=True)
                        last_print = now
    except urllib.error.HTTPError as exc:
        # Only discard partial download if the server explicitly rejected the Range header (HTTP 416)
        if exc.code == 416 and existing_bytes > 0:
            if part_path.is_file():
                part_path.unlink()
            print(f"    [WARN] Server rejected byte range (HTTP 416). Restarting clean: {url}", flush=True)
            _stream_download(url, dest)
            return
        raise
    except Exception as exc:
        # Preserve .part file on all other transient network failures
        print(f"    [WARN] Download interrupted ({exc}). Partial file preserved at: {part_path}", flush=True)
        raise

    part_path.replace(dest)


def _print_catalog(manifests: Dict[str, Any]) -> None:
    print("=" * 80)
    print("OffGridUSB (offgridusb.com) -- Internet-in-a-Box (.zim) & AI Model (.gguf) Catalog")
    print("=" * 80)
    print("\n[Internet-in-a-Box OpenZIM Knowledge Packs -- manifests/zim.json]")
    for z in manifests["archives"]:
        print(f"  Tier {z.get('tier', 0)} | {z['id']:<26} | {z.get('size_mb', 0):>8.1f} MB | {z['name']}")
    print("\n[Elastic Offline GGUF AI Models -- manifests/models.json]")
    for m in manifests["models"]:
        print(f"  Tier {m.get('tier', 0)} | {m['id']:<26} | {m.get('size_mb', 0):>8.1f} MB | {m['name']}")
    print("=" * 80)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OffGridUSB (offgridusb.com) Offline Asset Provisioner")
    parser.add_argument("--list", action="store_true", help="List all available Internet-in-a-Box ZIMs and GGUF models")
    parser.add_argument("--dry-run", action="store_true", help="Print planned downloads without fetching")
    parser.add_argument("--verify", action="store_true", help="Verify staged models and ZIM files on disk")
    parser.add_argument("--tier", type=int, default=0, help="Maximum hardware tier assets to fetch (0 to 4, default: 0)")
    parser.add_argument("--sku", type=str, default=None, help="Specific Product SKU (e.g. Product1, Product2, Product2-256, Product3, Product3-256, Tier3, Tier4)")
    parser.add_argument("--profile", type=str, default="full", choices=["lean", "full"], help="SKU payload profile when --sku is specified (default: full)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel download worker threads (default: 4)")
    parser.add_argument("--zim-only", action="store_true", help="Download only Internet-in-a-Box (.zim) archives")
    parser.add_argument("--models-only", action="store_true", help="Download only GGUF (.gguf) AI models")
    parser.add_argument("--id", dest="asset_ids", action="append", default=[], help="Download specific asset ID(s) by manifest id")
    parser.add_argument("--dest-root", type=str, default=None, help="Root directory for data/models & data/zim (default: project root)")
    args = parser.parse_args(argv)

    repo_root = _default_root()
    root = Path(args.dest_root).resolve() if args.dest_root else repo_root
    manifests = load_manifests(repo_root)

    if args.list:
        _print_catalog(manifests)
        return 0

    if args.verify:
        report = verify_assets(root)
        # Verification of a custom dest-root only covers data files; manifests stay repo-side.
        if args.dest_root:
            report["manifest_root"] = str(repo_root)
        print(json.dumps(report, indent=2))
        return 0

    requested_ids = {aid.strip() for aid in args.asset_ids if aid.strip()}
    if requested_ids:
        selected_models = [m for m in manifests["models"] if m.get("id") in requested_ids]
        selected_zims = [z for z in manifests["archives"] if z.get("id") in requested_ids]
    elif args.sku:
        sku_entry = next(
            (p for p in manifests.get("products", []) if p.get("sku", "").lower() == args.sku.strip().lower()),
            None,
        )
        if not sku_entry:
            print(f"[ERROR] Unknown SKU '{args.sku}' in manifests/products.json", file=sys.stderr)
            return 2
        prof = sku_entry.get("payload_profiles", {}).get(args.profile) or sku_entry.get("payload_profiles", {}).get("full", {})
        want_models = set(prof.get("models", []))
        want_zims = set(prof.get("zim_archives", []))

        selected_models = []
        if not args.zim_only:
            for m in manifests["models"]:
                if m["filename"] in want_models:
                    selected_models.append(m)
                if m.get("mmproj") and m["mmproj"] in want_models and m.get("mmproj_url"):
                    selected_models.append({
                        "id": f"{m['id']}-mmproj",
                        "name": f"{m['name']} (mmproj)",
                        "filename": m["mmproj"],
                        "url": m["mmproj_url"],
                        "size_bytes": m.get("mmproj_size_bytes", 0),
                    })
        selected_zims = [] if args.models_only else [z for z in manifests["archives"] if z["filename"] in want_zims]
    else:
        selected_models = [] if args.zim_only else [m for m in manifests["models"] if int(m.get("tier", 0)) <= args.tier]
        selected_zims = [] if args.models_only else [z for z in manifests["archives"] if int(z.get("tier", 0)) <= args.tier]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "sku": args.sku,
                    "profile": args.profile if args.sku else None,
                    "max_tier": args.tier,
                    "planned_models": selected_models,
                    "planned_zims": selected_zims,
                },
                indent=2,
            )
        )
        return 0

    if (root / "models").is_dir() or (root / "zim").is_dir() or not (root / "src").is_dir():
        models_dir = root / "models"
        zim_dir = root / "zim"
    else:
        models_dir = root / "data" / "models"
        zim_dir = root / "data" / "zim"
    models_dir.mkdir(parents=True, exist_ok=True)
    zim_dir.mkdir(parents=True, exist_ok=True)

    print_lock = threading.Lock()
    workers = max(1, int(args.workers))
    quiet_curl = workers > 1

    def _fetch_one(item: Dict[str, Any], target_dir: Path, kind: str) -> None:
        dest = target_dir / item["filename"]
        min_sz = 1024 * 1024 if kind == "model" else 1024
        if dest.exists() and dest.stat().st_size > min_sz and _check_magic_header(dest):
            with print_lock:
                print(f"[SKIP] {kind.upper()} already staged & valid: {dest.name}", flush=True)
            return
        sz_mb = item.get("size_mb") or round(item.get("size_bytes", 0) / (1024 * 1024), 1)
        with print_lock:
            print(f"[FETCH] Downloading {kind.upper()} ({sz_mb} MB): {item['name']} -> {dest.name}", flush=True)
        _stream_download(item["url"], dest, quiet_curl=quiet_curl)
        if not _check_magic_header(dest):
            raise RuntimeError(f"Downloaded file {dest.name} failed magic-byte check.")
        with print_lock:
            print(f"[OK] Verified {kind.upper()} header: {dest.name} ({dest.stat().st_size / (1024 * 1024):.1f} MB)", flush=True)

    tasks = [(m, models_dir, "model") for m in selected_models] + [(z, zim_dir, "zim") for z in selected_zims]
    if workers == 1 or len(tasks) <= 1:
        for item, tdir, kind in tasks:
            _fetch_one(item, tdir, kind)
    else:
        errors: List[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_fetch_one, item, tdir, kind): item["filename"] for item, tdir, kind in tasks}
            for fut in as_completed(futs):
                fname = futs[fut]
                try:
                    fut.result()
                except Exception as exc:
                    with print_lock:
                        print(f"[ERROR] Failed fetching {fname}: {exc}", file=sys.stderr, flush=True)
                    errors.append(f"{fname}: {exc}")
        if errors:
            raise RuntimeError(f"{len(errors)} asset download(s) failed: {'; '.join(errors[:3])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
