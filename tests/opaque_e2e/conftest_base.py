"""Shared test fixtures, mock environment builders, and authoritative oracles.

Pure Python standard library (zero external pip packages).
Designed for opaque-box testing across Windows, Linux, and macOS.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union
import unittest


# -----------------------------------------------------------------------------
# Path Resolution
# -----------------------------------------------------------------------------

def get_repo_root() -> Path:
    """Returns the absolute path to the local OffGridUSB repository root."""
    # Current file is tests/opaque_e2e/conftest_base.py -> parent.parent.parent is repo root
    current_file = Path(__file__).resolve()
    return current_file.parent.parent.parent


def get_target_drive() -> Optional[Path]:
    """Returns target drive path (e.g. D:\\) if specified or available."""
    env_target = os.environ.get("OFFGRID_TARGET_DRIVE", "D:")
    target_path = Path(env_target)
    if target_path.exists():
        return target_path
    return None


# -----------------------------------------------------------------------------
# Binary Magic Bytes & Header Constants
# -----------------------------------------------------------------------------

ZIM_MAGIC_LE = b"\x5a\x49\x4d\x04"  # "ZIM\x04"
ZIM_MAGIC_INT_LE = 0x044D495A
ZIM_MAGIC_INT_BE = 0x5A494D04
GGUF_MAGIC = b"GGUF"
GZIP_MAGIC = b"\x1f\x8b"
ELF_MAGIC = b"\x7fELF"
MACHO_64_MAGIC = b"\xfe\xed\xfa\xcf"  # Mach-O 64-bit little endian
MACHO_64_MAGIC_BE = b"\xcf\xfa\xed\xfe"  # Mach-O 64-bit big endian

# Grounded AI Professor Citation Pattern
CITATION_PATTERN = re.compile(r"\[(Source|Lesson):\s*([^#\]]+)(?:#([^\]]+))?\]")


# -----------------------------------------------------------------------------
# Authoritative Mathematical Oracles
# -----------------------------------------------------------------------------

class AuthoritativeWaterOracle:
    """CDC / WHO emergency water purification reference formulas."""

    @staticmethod
    def calculate_bleach(volume_liters: float, is_turbid: bool = False, concentration_pct: float = 6.0) -> Dict[str, Any]:
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")
        if concentration_pct <= 0 or concentration_pct > 15.0:
            raise ValueError("Concentration must be between 1% and 15%")
        base_drops = 4 if is_turbid else 2
        scaling = 6.0 / concentration_pct
        total_drops = math.ceil(volume_liters * base_drops * scaling)
        total_ml = round(total_drops * 0.05, 2)
        contact_time = 60 if is_turbid else 30
        return {
            "method": "bleach",
            "volume_liters": volume_liters,
            "is_turbid": is_turbid,
            "drops": total_drops,
            "volume_ml": total_ml,
            "contact_time_minutes": contact_time,
            "chlorine_ppm_target": 4.0 if is_turbid else 2.0,
        }

    @staticmethod
    def calculate_iodine(volume_liters: float, is_turbid: bool = False) -> Dict[str, Any]:
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")
        drops_per_liter = 10 if is_turbid else 5
        total_drops = math.ceil(volume_liters * drops_per_liter)
        total_ml = round(total_drops * 0.05, 2)
        contact_time = 60 if is_turbid else 30
        return {
            "method": "iodine_2pct",
            "volume_liters": volume_liters,
            "is_turbid": is_turbid,
            "drops": total_drops,
            "volume_ml": total_ml,
            "contact_time_minutes": contact_time,
        }

    @staticmethod
    def calculate_boiling(volume_liters: float, elevation_meters: float = 0.0) -> Dict[str, Any]:
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")
        boil_time = 3 if elevation_meters >= 2000.0 else 1
        return {
            "method": "boiling",
            "volume_liters": volume_liters,
            "elevation_meters": elevation_meters,
            "boil_time_minutes": boil_time,
        }


class AuthoritativeMedicalOracle:
    """WHO Guidelines for diarrhoeal diseases and weight-based analgesics."""

    CLINICAL_MIN_WEIGHT_KG = 2.0
    CLINICAL_MAX_WEIGHT_KG = 250.0

    @classmethod
    def calculate_ors(cls, weight_kg: float) -> Dict[str, Any]:
        if weight_kg < cls.CLINICAL_MIN_WEIGHT_KG or weight_kg > cls.CLINICAL_MAX_WEIGHT_KG:
            raise ValueError("Weight must be between 2 kg and 250 kg")
        volume_4h = round(weight_kg * 75.0, 1)
        hourly_rate = round(volume_4h / 4.0, 1)
        return {
            "weight_kg": weight_kg,
            "total_ors_ml_4h": volume_4h,
            "hourly_rate_ml": hourly_rate,
            "reassessment_interval_hours": 4,
        }

    @classmethod
    def calculate_paracetamol(cls, weight_kg: float) -> Dict[str, Any]:
        if weight_kg < cls.CLINICAL_MIN_WEIGHT_KG or weight_kg > cls.CLINICAL_MAX_WEIGHT_KG:
            raise ValueError("Weight must be between 2 kg and 250 kg")
        calc_single = weight_kg * 15.0
        single_dose = min(1000.0, round(calc_single, 1))
        calc_daily = weight_kg * 60.0
        max_daily = min(4000.0, round(calc_daily, 1))
        return {
            "medication": "paracetamol",
            "weight_kg": weight_kg,
            "single_dose_mg": single_dose,
            "interval_hours": "4-6",
            "max_daily_mg": max_daily,
            "clamped_to_adult_max": calc_single > 1000.0,
        }

    @classmethod
    def calculate_ibuprofen(cls, weight_kg: float) -> Dict[str, Any]:
        if weight_kg < cls.CLINICAL_MIN_WEIGHT_KG or weight_kg > cls.CLINICAL_MAX_WEIGHT_KG:
            raise ValueError("Weight must be between 2 kg and 250 kg")
        calc_single = weight_kg * 10.0
        single_dose = min(400.0, round(calc_single, 1))
        calc_daily = weight_kg * 40.0
        max_daily = min(1200.0, round(calc_daily, 1))
        return {
            "medication": "ibuprofen",
            "weight_kg": weight_kg,
            "single_dose_mg": single_dose,
            "interval_hours": "6-8",
            "max_daily_mg": max_daily,
            "clamped_to_adult_max": calc_single > 400.0,
        }


class AuthoritativeSolarOracle:
    """IEEE 1562 & NEC Article 690 standalone solar and battery sizing."""

    @staticmethod
    def calculate_system(
        daily_wh: float,
        system_voltage: float = 12.0,
        dod: float = 0.8,
        autonomy_days: float = 1.0,
        inverter_eff: float = 0.90,
        peak_sun_hours: float = 4.5,
        system_derating: float = 0.77,
    ) -> Dict[str, Any]:
        if daily_wh <= 0 or system_voltage <= 0 or dod <= 0 or dod > 1.0:
            raise ValueError("Invalid solar parameter")
        if peak_sun_hours <= 0 or autonomy_days <= 0 or inverter_eff <= 0 or inverter_eff > 1.0 or system_derating <= 0 or system_derating > 1.0:
            raise ValueError("Invalid solar parameter")
        battery_ah = round((daily_wh * autonomy_days) / (system_voltage * dod * inverter_eff), 2)
        solar_watts = round(daily_wh / (peak_sun_hours * system_derating), 2)
        return {
            "daily_wh": daily_wh,
            "system_voltage": system_voltage,
            "dod": dod,
            "battery_capacity_ah": battery_ah,
            "solar_array_watts": solar_watts,
            "peak_sun_hours": peak_sun_hours,
        }


class AuthoritativeElectricalOracle:
    """Ohm's Law & DC voltage drop standards."""

    AWG_RESISTANCE: Dict[str, float] = {
        "14": 8.286, "12": 5.211, "10": 3.277, "8": 2.061,
        "6": 1.296, "4": 0.815, "2": 0.513, "1/0": 0.323,
        "2/0": 0.256, "4/0": 0.161,
    }

    @staticmethod
    def solve_ohms_law(
        v: Optional[float] = None,
        i: Optional[float] = None,
        r: Optional[float] = None,
        p: Optional[float] = None,
    ) -> Dict[str, float]:
        params = [x for x in (v, i, r, p) if x is not None]
        if len(params) < 2:
            raise ValueError("At least two parameters required")
        if r is not None and r <= 0:
            raise ValueError("Resistance must be positive")
        if v is not None and v < 0:
            raise ValueError("Voltage cannot be negative")
        if i is not None and i < 0:
            raise ValueError("Current cannot be negative")
        if p is not None and p < 0:
            raise ValueError("Power cannot be negative")

        if v is not None and i is not None:
            if i <= 0: raise ValueError("Current must be positive")
            return {"voltage_v": float(v), "current_a": float(i), "resistance_ohm": float(v / i), "power_w": float(v * i)}
        elif v is not None and r is not None:
            return {"voltage_v": float(v), "current_a": float(v / r), "resistance_ohm": float(r), "power_w": float((v * v) / r)}
        elif i is not None and r is not None:
            return {"voltage_v": float(i * r), "current_a": float(i), "resistance_ohm": float(r), "power_w": float((i * i) * r)}
        elif p is not None and v is not None:
            if v <= 0: raise ValueError("Voltage must be positive")
            return {"voltage_v": float(v), "current_a": float(p / v), "resistance_ohm": float((v * v) / p), "power_w": float(p)}
        elif p is not None and i is not None:
            if i <= 0: raise ValueError("Current must be positive")
            return {"voltage_v": float(p / i), "current_a": float(i), "resistance_ohm": float(p / (i * i)), "power_w": float(p)}
        elif p is not None and r is not None:
            v_calc = math.sqrt(p * r)
            return {"voltage_v": float(v_calc), "current_a": float(math.sqrt(p / r)), "resistance_ohm": float(r), "power_w": float(p)}
        raise ValueError("Unsupported parameter combination")


# -----------------------------------------------------------------------------
# Isolated OffGrid USB Sandbox Generator
# -----------------------------------------------------------------------------

class OffGridSandbox:
    """Creates a temporary, self-contained mock OffGridUSB filesystem environment.

    Allows opaque-box E2E tests to run in full isolation without modifying
    physical hardware, host directories, or waiting for large network transfers.
    """

    def __init__(self, tier: int = 0):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="offgrid_e2e_")
        self.root = Path(self.temp_dir.name)
        self.tier = tier
        self._build_skeleton()

    def _build_skeleton(self):
        """Builds standard root files, launchers, directories, and mock assets."""
        # 1. Standard Directories
        for d in [
            "bin/windows_x86_64/python",
            "bin/windows_x86_64/kiwix",
            "bin/windows_x86_64/llama",
            "bin/windows_arm64/llama",
            "bin/linux_x86_64",
            "bin/linux_arm64",
            "bin/macos_x86_64",
            "bin/macos_arm64",
            "bin/polyglot",
            "data/zim",
            "data/models",
            "data/vault",
            "data/uploads",
            "docs",
            "manifests",
            "scripts",
            "src/emyrge",
            "web/static",
        ]:
            (self.root / d).mkdir(parents=True, exist_ok=True)

        # 2. Root Launchers (CRLF for .bat, LF for .sh / .command)
        root_bat_files = [
            "START_OFFGRIDUSB_WINDOWS.bat",
            "START_EMYRGE_WINDOWS.bat",
            "run_windows.bat",
            "FORMAT_AND_SETUP_USB.bat",
            "DOWNLOAD_INTERNET_IN_A_BOX.bat",
            "MAKE_USB_DRIVES.bat",
        ]
        for bat in root_bat_files:
            content = f"@echo off\r\nrem OffGridUSB Launcher: {bat}\r\nset EMYRGE_PORT=8000\r\n"
            (self.root / bat).write_bytes(content.encode("ascii"))

        root_sh_files = [
            "START_OFFGRIDUSB_LINUX.sh",
            "START_EMYRGE_LINUX.sh",
            "run_linux.sh",
            "START_OFFGRIDUSB_MAC.command",
            "START_EMYRGE_MAC.command",
            "run_macos.command",
        ]
        for sh in root_sh_files:
            content = f"#!/usr/bin/env bash\n# OffGridUSB Launcher: {sh}\nset -e\nexport EMYRGE_PORT=8000\n"
            (self.root / sh).write_bytes(content.encode("ascii"))

        # 3. Documentation
        (self.root / "README.md").write_text("# OffGridUSB Sandbox Deployment\n", encoding="utf-8")
        (self.root / "CONTRIBUTING.md").write_text("# Contributing Guide\n", encoding="utf-8")

        # 4. Manifests
        repo_manifests = get_repo_root() / "manifests"
        if repo_manifests.exists():
            for m in ("zim.json", "models.json"):
                src_m = repo_manifests / m
                if src_m.exists():
                    shutil.copy2(src_m, self.root / "manifests" / m)

        # 5. Seed Mock Binary Assets
        self.stage_mock_engines()
        self.stage_mock_assets(self.tier)

    def stage_mock_engines(self):
        """Stages minimal mock binaries with valid headers for cross-platform audit."""
        # Windows Python
        (self.root / "bin/windows_x86_64/python/python.exe").write_bytes(b"MZ\x90\x00" + b"\x00" * 1024)
        (self.root / "bin/windows_x86_64/python/python312._pth").write_text("..\\..\\..\\src\n.\n", encoding="utf-8")

        # Windows Kiwix & Llama
        (self.root / "bin/windows_x86_64/kiwix/kiwix-serve.exe").write_bytes(b"MZ\x90\x00" + b"\x00" * 1024)
        (self.root / "bin/windows_x86_64/llama/llama-server.exe").write_bytes(b"MZ\x90\x00" + b"\x00" * 1024)

        # POSIX Tarballs with valid gzip headers
        posix_tarballs = [
            "bin/linux_x86_64/kiwix-tools_linux-x86_64.tar.gz",
            "bin/linux_x86_64/llama-ubuntu-x64.tar.gz",
            "bin/linux_arm64/kiwix-tools_linux-aarch64.tar.gz",
            "bin/linux_arm64/llama-ubuntu-arm64.tar.gz",
            "bin/macos_arm64/kiwix-tools_macos.tar.gz",
            "bin/macos_arm64/llama-macos-arm64.tar.gz",
            "bin/macos_x86_64/kiwix-tools_macos-x86_64.tar.gz",
            "bin/macos_x86_64/llama-macos-x64.tar.gz",
        ]
        for tb in posix_tarballs:
            # Gzip header: 0x1f 0x8b + deflate method 0x08 + flags
            gzip_header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + b"\x00" * 256
            (self.root / tb).write_bytes(gzip_header)

        # Polyglot llamafile
        (self.root / "bin/polyglot/llamafile.exe").write_bytes(b"MZqFpD\n\x00" + b"\x00" * 1024)

    def stage_mock_assets(self, tier: int):
        """Stages mock ZIM archives and GGUF models matching tier requirements."""
        # Tier 0 ZIMs
        tier0_zims = [
            "zimgit-water_en_2024-08.zim",
            "zimgit-medicine_en_2024-08.zim",
            "wikipedia_en_medicine_mini_2026-10.zim",
            "wikipedia_en_top_mini_2026-09.zim",
        ]
        for z in tier0_zims:
            # Write ZIM magic header: 0x5a 0x49 0x4d 0x04 (ZIM\x04) + 200KB mock payload
            data = ZIM_MAGIC_LE + b"\x00" * (200 * 1024)
            (self.root / "data/zim" / z).write_bytes(data)

        # Tier 0 Models
        tier0_models = [
            "smollm2-135m-instruct-q4_k_m.gguf",
            "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        ]
        for m in tier0_models:
            # Write GGUF magic header: b"GGUF" + version 3 + 2MB mock payload
            data = GGUF_MAGIC + struct.pack("<I", 3) + b"\x00" * (2 * 1024 * 1024)
            (self.root / "data/models" / m).write_bytes(data)

        # Tier 2 additions
        if tier >= 2:
            tier2_zims = [
                "khanacademy_en_all_2024-05.zim",
                "wikibooks_en_all_maxi_2026-04.zim",
                "wikipedia_en_all_nopic_2024-06.zim",
                "wikipedia_en_all_nopic_2026-06.zim",
            ]
            for z in tier2_zims:
                data = ZIM_MAGIC_LE + b"\x00" * (200 * 1024)
                (self.root / "data/zim" / z).write_bytes(data)

            tier2_models = [
                "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "llama-3.2-3b-instruct-q4_k_m.gguf",
            ]
            for m in tier2_models:
                data = GGUF_MAGIC + struct.pack("<I", 3) + b"\x00" * (2 * 1024 * 1024)
                (self.root / "data/models" / m).write_bytes(data)

    def cleanup(self):
        """Cleans up the temporary sandbox."""
        self.temp_dir.cleanup()


# -----------------------------------------------------------------------------
# Base Test Case Class
# -----------------------------------------------------------------------------

class BaseOpaqueTestCase(unittest.TestCase):
    """Base test case providing shared assertions, sandbox management, and oracles."""

    def setUp(self):
        self.repo_root = get_repo_root()
        self.target_drive = get_target_drive()
        self.sandbox = None

    def tearDown(self):
        if self.sandbox:
            self.sandbox.cleanup()
            self.sandbox = None

    def get_or_create_sandbox(self, tier: int = 0) -> OffGridSandbox:
        if self.sandbox is None or self.sandbox.tier != tier:
            if self.sandbox:
                self.sandbox.cleanup()
            self.sandbox = OffGridSandbox(tier=tier)
        return self.sandbox

    def assert_valid_zim_header(self, file_path: Path):
        """Asserts that the file begins with authoritative OpenZIM magic bytes."""
        self.assertTrue(file_path.exists(), f"ZIM file does not exist: {file_path}")
        with open(file_path, "rb") as f:
            header = f.read(4)
        self.assertGreaterEqual(len(header), 4, f"Truncated ZIM file: {file_path}")
        magic_val = struct.unpack("<I", header)[0]
        self.assertIn(
            magic_val,
            (ZIM_MAGIC_INT_LE, ZIM_MAGIC_INT_BE),
            f"Invalid ZIM magic header: 0x{magic_val:08X} in {file_path.name}",
        )

    def assert_valid_gguf_header(self, file_path: Path):
        """Asserts that the file begins with authoritative GGUF magic bytes."""
        self.assertTrue(file_path.exists(), f"GGUF file does not exist: {file_path}")
        with open(file_path, "rb") as f:
            header = f.read(4)
        self.assertEqual(header, GGUF_MAGIC, f"Invalid GGUF header {header!r} in {file_path.name}")

    def assert_valid_citation(self, text: str):
        """Asserts that text contains at least one valid [Source: ...] or [Lesson: ...] tag."""
        matches = CITATION_PATTERN.findall(text)
        self.assertTrue(len(matches) > 0, f"No valid citation found matching pattern in: {text[:150]}...")
