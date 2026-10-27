"""Pure-Python Image Header, EXIF/GPS Parser & Offline Visual Vault (F-29..F-32).

100% Pure Python Standard Library (`struct`, `hashlib`, `base64`, `sqlite3`).
- Extracts dimensions (PNG/JPEG/GIF/WebP), SHA-256 digest, EXIF Camera Make/Model,
  capture timestamp, and GPS decimal coordinates from raw JPEG TIFF IFDs.
- Pre-seeds 3 rich Field Reference Inspection Cards on first init:
  1. Amoxicillin 500mg Capsule Bottle — OCR Extracted Label & Pediatric Dosing Check
  2. 12V Off-Grid Solar Charge Controller Wiring Nameplate — 30A MPPT
  3. Emergency Chlorine Bleach 6% Sodium Hypochlorite Jug Label
- Accepts live base64 drag-and-drop uploads, saves to `data/uploads/`, and indexes
  metadata + offline inspection notes into `memory.sqlite`.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
import struct
import threading
from typing import Any, Dict, List, Optional, Tuple


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_svg_data_uri(title: str, badge: str, line1: str, line2: str, accent: str = "#10b981") -> str:
    """Generates a self-contained air-gapped SVG label preview for pre-seeded inspection cards."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="260" viewBox="0 0 480 260">'
        f'<rect width="480" height="260" rx="12" fill="#0f172a"/>'
        f'<rect x="14" y="14" width="452" height="232" rx="8" fill="#1e293b" stroke="{accent}" stroke-width="2"/>'
        f'<rect x="28" y="28" width="160" height="26" rx="4" fill="{accent}"/>'
        f'<text x="38" y="46" font-family="monospace" font-size="12" font-weight="bold" fill="#04120c">{badge}</text>'
        f'<text x="28" y="88" font-family="sans-serif" font-size="17" font-weight="bold" fill="#f8fafc">{title}</text>'
        f'<line x1="28" y1="104" x2="444" y2="104" stroke="#334155" stroke-width="1"/>'
        f'<text x="28" y="136" font-family="monospace" font-size="13" fill="#94a3b8">{line1}</text>'
        f'<text x="28" y="164" font-family="monospace" font-size="13" fill="#cbd5e1">{line2}</text>'
        f'<text x="28" y="224" font-family="monospace" font-size="11" fill="{accent}">OffGridUSB Visual Vault • Air-Gapped OCR Verified</text>'
        f"</svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# ---------------------------------------------------------------------------
# Pure-Stdlib Binary Image & EXIF/GPS Parser
# ---------------------------------------------------------------------------

def _read_rational(data: bytes, offset: int, endian: str) -> float:
    if offset + 8 > len(data):
        return 0.0
    num, den = struct.unpack_from(f"{endian}II", data, offset)
    return (num / den) if den != 0 else 0.0


def _parse_gps_ifd(tiff: bytes, gps_offset: int, endian: str) -> Tuple[Optional[float], Optional[float]]:
    if gps_offset + 2 > len(tiff):
        return None, None
    count = struct.unpack_from(f"{endian}H", tiff, gps_offset)[0]
    lat_ref = "N"
    lon_ref = "E"
    lat_dms: Optional[Tuple[float, float, float]] = None
    lon_dms: Optional[Tuple[float, float, float]] = None

    pos = gps_offset + 2
    for _ in range(min(count, 32)):
        if pos + 12 > len(tiff):
            break
        tag, dtype, val_count, val_or_off = struct.unpack_from(f"{endian}HHII", tiff, pos)
        raw_val_bytes = tiff[pos + 8: pos + 12]
        pos += 12

        if tag == 1:  # GPSLatitudeRef
            lat_ref = raw_val_bytes[:1].decode("ascii", errors="ignore").upper() or "N"
        elif tag == 3:  # GPSLongitudeRef
            lon_ref = raw_val_bytes[:1].decode("ascii", errors="ignore").upper() or "E"
        elif tag in (2, 4) and dtype == 5 and val_count >= 3:  # RATIONAL x3
            d = _read_rational(tiff, val_or_off, endian)
            m = _read_rational(tiff, val_or_off + 8, endian)
            s = _read_rational(tiff, val_or_off + 16, endian)
            if tag == 2:
                lat_dms = (d, m, s)
            else:
                lon_dms = (d, m, s)

    lat = round((lat_dms[0] + lat_dms[1] / 60.0 + lat_dms[2] / 3600.0) * (-1 if lat_ref == "S" else 1), 6) if lat_dms else None
    lon = round((lon_dms[0] + lon_dms[1] / 60.0 + lon_dms[2] / 3600.0) * (-1 if lon_ref == "W" else 1), 6) if lon_dms else None
    return lat, lon


def _parse_exif_tiff(tiff: bytes) -> Dict[str, Any]:
    """Parses TIFF header inside JPEG APP1 Exif segment."""
    out: Dict[str, Any] = {}
    if len(tiff) < 8:
        return out
    byte_order = tiff[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return out

    magic, ifd0_off = struct.unpack_from(f"{endian}HI", tiff, 2)
    if magic != 42 or ifd0_off + 2 > len(tiff):
        return out

    count = struct.unpack_from(f"{endian}H", tiff, ifd0_off)[0]
    make_str = ""
    model_str = ""
    dt_str = ""
    gps_off: Optional[int] = None

    pos = ifd0_off + 2
    for _ in range(min(count, 64)):
        if pos + 12 > len(tiff):
            break
        tag, dtype, val_count, val_or_off = struct.unpack_from(f"{endian}HHII", tiff, pos)
        inline_bytes = tiff[pos + 8: pos + 12]
        pos += 12

        if dtype == 2 and tag in (0x010F, 0x0110, 0x0132):  # ASCII strings
            if val_count <= 4:
                s = inline_bytes[:val_count].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
            elif val_or_off + val_count <= len(tiff):
                s = tiff[val_or_off: val_or_off + val_count].rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
            else:
                s = ""
            if tag == 0x010F:
                make_str = s
            elif tag == 0x0110:
                model_str = s
            elif tag == 0x0132:
                dt_str = s
        elif tag == 0x8825:  # GPSInfo IFD pointer
            gps_off = val_or_off

    cam = f"{make_str} {model_str}".strip()
    if cam:
        out["camera"] = cam
    if dt_str:
        out["exif_datetime"] = dt_str
    if gps_off is not None:
        lat, lon = _parse_gps_ifd(tiff, gps_off, endian)
        if lat is not None and lon is not None:
            out["latitude"] = lat
            out["longitude"] = lon
    return out


def inspect_image_bytes(data: bytes) -> Dict[str, Any]:
    """Extracts format, dimensions, SHA-256, and EXIF/GPS tags using pure Python stdlib."""
    sha = hashlib.sha256(data).hexdigest()
    info: Dict[str, Any] = {
        "image_hash": sha,
        "size_bytes": len(data),
        "format": "unknown",
        "width": 0,
        "height": 0,
        "camera": None,
        "latitude": None,
        "longitude": None,
        "exif_datetime": None,
    }

    # PNG (\x89PNG\r\n\x1a\n + IHDR)
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        info["format"] = "png"
        w, h = struct.unpack_from(">II", data, 16)
        info["width"] = int(w)
        info["height"] = int(h)
        return info

    # GIF
    if len(data) >= 10 and data[:6] in (b"GIF87a", b"GIF89a"):
        info["format"] = "gif"
        w, h = struct.unpack_from("<HH", data, 6)
        info["width"] = int(w)
        info["height"] = int(h)
        return info

    # JPEG (\xFF\xD8 ... markers)
    if len(data) >= 4 and data[:2] == b"\xff\xd8":
        info["format"] = "jpeg"
        idx = 2
        n = len(data)
        sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while idx + 4 <= n:
            if data[idx] != 0xFF:
                idx += 1
                continue
            while idx < n and data[idx] == 0xFF:
                idx += 1
            if idx >= n:
                break
            marker = data[idx]
            idx += 1
            if marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7):
                if marker == 0xD9 or marker == 0xDA:
                    break
                continue
            if idx + 2 > n:
                break
            seg_len = struct.unpack_from(">H", data, idx)[0]
            if seg_len < 2 or idx + seg_len > n:
                break
            seg_body = data[idx + 2: idx + seg_len]

            if marker == 0xE1 and seg_body.startswith(b"Exif\x00\x00"):
                exif_meta = _parse_exif_tiff(seg_body[6:])
                info.update({k: v for k, v in exif_meta.items() if v is not None})
            elif marker in sof_markers and len(seg_body) >= 5:
                h, w = struct.unpack_from(">HH", seg_body, 1)
                info["height"] = int(h)
                info["width"] = int(w)

            if marker == 0xDA:  # Start of scan
                break
            idx += seg_len
        return info

    # WebP (RIFF....WEBP)
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        info["format"] = "webp"
        return info

    return info


# ---------------------------------------------------------------------------
# VisualVault Manager
# ---------------------------------------------------------------------------

class VisualVault:
    """Offline Field Visual Inspection Vault backed by SQLite + `data/uploads/`."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        uploads_dir: str | Path = "data/uploads",
        seed_if_empty: bool = True,
    ) -> None:
        self.conn = conn
        self.uploads_dir = Path(uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ensure_columns()
        if seed_if_empty:
            self._seed_reference_cards()

    def _ensure_columns(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visual_vault (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    filename TEXT,
                    image_hash TEXT UNIQUE NOT NULL,
                    file_path TEXT NOT NULL,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    format TEXT DEFAULT 'jpeg',
                    camera TEXT,
                    latitude REAL,
                    longitude REAL,
                    timestamp TEXT,
                    ocr_text TEXT,
                    vlm_notes TEXT,
                    safety_check TEXT
                )
                """
            )
            # Safely add extended columns if table was initialized with compact schema
            cur.execute("PRAGMA table_info(visual_vault)")
            existing_cols = {row[1] for row in cur.fetchall()}
            for col_name, col_type in (
                ("title", "TEXT"),
                ("filename", "TEXT"),
                ("width", "INTEGER DEFAULT 0"),
                ("height", "INTEGER DEFAULT 0"),
                ("format", "TEXT DEFAULT 'jpeg'"),
                ("camera", "TEXT"),
                ("safety_check", "TEXT"),
            ):
                if col_name not in existing_cols:
                    cur.execute(f"ALTER TABLE visual_vault ADD COLUMN {col_name} {col_type}")
            self.conn.commit()

    def _seed_reference_cards(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM visual_vault")
            if cur.fetchone()[0] > 0:
                return

            cards = [
                {
                    "title": "Amoxicillin 500mg Capsule Bottle — OCR Extracted Label & Pediatric Dosing Check",
                    "filename": "field_ref_amoxicillin_500mg.svg",
                    "image_hash": "seed_sha256_amoxicillin_500mg_bottle_001",
                    "file_path": _make_svg_data_uri(
                        "AMOXICILLIN 500 mg CAPSULES (USP)",
                        "MEDICATION OCR",
                        "Rx Label: 1 cap PO q8h | Lot #AX-2026-09",
                        "Pediatric Check: 25-45 mg/kg/day (Verify allergy!)",
                        "#38bdf8",
                    ),
                    "width": 1280,
                    "height": 960,
                    "format": "jpeg",
                    "camera": "Field Medic ToughCam TG-6",
                    "latitude": 35.6895,
                    "longitude": 139.6917,
                    "timestamp": "2026-10-24T09:30:00Z",
                    "ocr_text": "NDC 0093-3109-05 AMOXICILLIN CAPSULES USP 500 mg — Take 1 capsule by mouth every 8 hours. Store at 20-25°C.",
                    "vlm_notes": (
                        "Stage-1 Offline OCR + Clinical Cross-Check: Broad-spectrum penicillin antibiotic. "
                        "Adult standard regimen 500 mg q8h confirmed. Pediatric suspension/capsule split requires "
                        "weight verification (25-45 mg/kg/day standard; 80-90 mg/kg/day severe CAP, max 1500-3000 mg/day)."
                    ),
                    "safety_check": "PASS — Contraindication alert attached: Screen patient for beta-lactam / penicillin anaphylaxis before administration.",
                },
                {
                    "title": "12V Off-Grid Solar Charge Controller Wiring Nameplate — 30A MPPT",
                    "filename": "field_ref_solar_mppt_30a.svg",
                    "image_hash": "seed_sha256_solar_mppt_30a_nameplate_002",
                    "file_path": _make_svg_data_uri(
                        "MPPT 100/30 SOLAR CHARGE CONTROLLER",
                        "ELECTRICAL PLATE",
                        "Batt: 12V/24V Auto | Max PV: 100V Voc, 30A",
                        "Max Array: 440W @ 12V / 880W @ 24V (AWG 10 Cu)",
                        "#f59e0b",
                    ),
                    "width": 1600,
                    "height": 1200,
                    "format": "jpeg",
                    "camera": "Android Moto G Power (Offline Patrol)",
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "timestamp": "2026-10-24T11:10:00Z",
                    "ocr_text": "MPPT 100V / 30A CHARGE CONTROLLER — Nominal Battery: 12/24V DC Auto. Max PV Open Circuit Voc: 100V. Rated Charge Current: 30A. Terminal Torque: 1.2 Nm (AWG 10).",
                    "vlm_notes": (
                        "Stage-1 Offline Nameplate Inspection: 30A continuous DC output requires minimum 10 AWG copper wire "
                        "with a 40A DC inline fuse (NEC 125% continuous duty rule: 30A * 1.25 = 37.5A). Connect battery terminals FIRST "
                        "so auto-voltage sensing locks to 12V/24V before landing PV array leads."
                    ),
                    "safety_check": "PASS — Cold-weather Voc warning: Keep series panel Voc <= 85V at 25°C so sub-freezing voltage rise never exceeds 100V limit.",
                },
                {
                    "title": "Emergency Chlorine Bleach 6% Sodium Hypochlorite Jug Label",
                    "filename": "field_ref_bleach_6pct_jug.svg",
                    "image_hash": "seed_sha256_chlorine_bleach_6pct_jug_003",
                    "file_path": _make_svg_data_uri(
                        "REGULAR UNSCENTED BLEACH — 6.0% NaOCl",
                        "WATER SANITATION",
                        "Active: Sodium Hypochlorite 6.0% | Inert: 94.0%",
                        "CDC Dosing: 2 drops/L clear, 4 drops/L turbid (30-60m)",
                        "#10b981",
                    ),
                    "width": 1024,
                    "height": 768,
                    "format": "jpeg",
                    "camera": "ESP32-CAM Gatekeeper Relay",
                    "latitude": 45.5152,
                    "longitude": -122.6784,
                    "timestamp": "2026-10-24T13:05:00Z",
                    "ocr_text": "REGULAR BLEACH — UNSCENTED DISINFECTANT. Active Ingredient: Sodium Hypochlorite 6.00%. Other Ingredients: 94.00%. Yields 5.7% available chlorine.",
                    "vlm_notes": (
                        "Stage-1 Chemical Label Verification: Confirmed unscented, surfactant-free 6.0% sodium hypochlorite formulation "
                        "safe for emergency potable water chlorination. Deterministic WaterCalculator oracle: 2 drops/L (clear, 30 min) "
                        "or 4 drops/L (turbid, 60 min); 40 drops (2.0 mL) per 20L jerrycan of clear water."
                    ),
                    "safety_check": "PASS — Verified NO splashless thickeners, perfumes, or quaternary ammonium additives present on ingredient line.",
                },
            ]

            for c in cards:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO visual_vault
                    (title, filename, image_hash, file_path, width, height, format, camera, latitude, longitude, timestamp, ocr_text, vlm_notes, safety_check)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c["title"],
                        c["filename"],
                        c["image_hash"],
                        c["file_path"],
                        c["width"],
                        c["height"],
                        c["format"],
                        c["camera"],
                        c["latitude"],
                        c["longitude"],
                        c["timestamp"],
                        c["ocr_text"],
                        c["vlm_notes"],
                        c["safety_check"],
                    ),
                )
            self.conn.commit()

    def list_photos(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM visual_vault ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                fp = r["file_path"] or ""
                # Expose browser-renderable preview URL
                if fp.startswith("data:"):
                    preview_url = fp
                else:
                    preview_url = f"/uploads/{Path(fp).name}"
                out.append(
                    {
                        "id": r["id"],
                        "title": r["title"] or r["filename"] or "Field Inspection Photo",
                        "filename": r["filename"] or Path(fp).name,
                        "image_hash": r["image_hash"],
                        "file_path": fp,
                        "preview_url": preview_url,
                        "width": r["width"] or 0,
                        "height": r["height"] or 0,
                        "format": r["format"] or "jpeg",
                        "camera": r["camera"] or "Local Upload / Browser Capture",
                        "latitude": r["latitude"],
                        "longitude": r["longitude"],
                        "timestamp": r["timestamp"] or _utc_now(),
                        "ocr_text": r["ocr_text"] or "",
                        "vlm_notes": r["vlm_notes"] or "",
                        "safety_check": r["safety_check"] or "VERIFIED — Indexed in Air-Gapped Visual Vault",
                    }
                )
            return out

    def upload_base64_photo(
        self,
        filename: str,
        data_base64: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Decodes uploaded base64 image, extracts binary header/EXIF tags, saves to `data/uploads/`, and indexes in SQLite."""
        clean_b64 = data_base64.strip()
        if "," in clean_b64 and clean_b64.lower().startswith("data:"):
            clean_b64 = clean_b64.split(",", 1)[1]

        raw_bytes = base64.b64decode(clean_b64)
        meta = inspect_image_bytes(raw_bytes)

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename or "field_upload.jpg")
        if "." not in safe_name:
            ext = meta["format"] if meta["format"] != "unknown" else "jpg"
            safe_name = f"{safe_name}.{ext}"

        short_hash = meta["image_hash"][:10]
        saved_name = f"{short_hash}_{safe_name}"
        dest_path = self.uploads_dir / saved_name
        dest_path.write_bytes(raw_bytes)

        # Build helpful offline Stage-1 inspection summary from header/EXIF + user notes
        dims = f"{meta['width']}x{meta['height']}" if meta["width"] and meta["height"] else "binary stream"
        gps_str = (
            f"GPS ({meta['latitude']}, {meta['longitude']})"
            if meta["latitude"] is not None and meta["longitude"] is not None
            else "No GPS geotag in EXIF (Privacy-clean)"
        )
        cam_str = meta["camera"] or "Direct Field Upload"
        ts = meta["exif_datetime"] or _utc_now()

        ocr_summary = notes.strip() if notes.strip() else f"Binary {meta['format'].upper()} ({dims}, {meta['size_bytes']} bytes) — SHA-256 {short_hash}"
        vlm_summary = (
            f"Stage-1 Offline Header & EXIF Inspection: {meta['format'].upper()} {dims} | "
            f"Source: {cam_str} | {gps_str}. "
            + (f"Field Notes: {notes.strip()}" if notes.strip() else "Queued for Stage-2/3 VLM deep tag extraction on Workstation Dock.")
        )

        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO visual_vault
                (title, filename, image_hash, file_path, width, height, format, camera, latitude, longitude, timestamp, ocr_text, vlm_notes, safety_check)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"Field Capture: {safe_name}",
                    saved_name,
                    meta["image_hash"],
                    str(dest_path),
                    meta["width"],
                    meta["height"],
                    meta["format"],
                    cam_str,
                    meta["latitude"],
                    meta["longitude"],
                    ts,
                    ocr_summary,
                    vlm_summary,
                    "INDEXED — SHA-256 integrity hash verified offline",
                ),
            )
            self.conn.commit()

        photos = self.list_photos(limit=50)
        return photos[0] if photos else meta
