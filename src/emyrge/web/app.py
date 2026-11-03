"""Zero-Dependency Air-Gapped Web Server & REST API for Project eMyrge.

100% Pure Python Standard Library (`http.server.ThreadingHTTPServer`).
Compatible with Windows Embeddable Python 3.12 (`python-3.12.8-embed-amd64`),
Linux, and macOS with zero pip packages installed.

Run via:
    python -m emyrge.web.app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import platform
import socket
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import webbrowser

from emyrge.ai.model_runner import KiwixRunner, ModelRunner, probe_usb_platforms
from emyrge.calculators.electrical_formulas import ElectricalCalculator
from emyrge.calculators.medical_rehydration import MedicalCalculator
from emyrge.calculators.solar_battery import SolarCalculator
from emyrge.calculators.source_audit import CalculatorRouter, SourceAudit
from emyrge.calculators.water_purification import WaterCalculator
from emyrge.core.config import EmyrgeConfig, HardwareTier
from emyrge.core.hardware_probe import HardwareProbe
from emyrge.knowledge.grounding_harness import (
    Citation,
    CitationType,
    GroundedSource,
    GroundingHarness,
)
from emyrge.knowledge.khan_curriculum import KhanCurriculum
from emyrge.knowledge.seed_corpus import DEFAULT_KHAN_LESSONS, DEFAULT_ZIM_ARTICLES
from emyrge.knowledge.zim_reader import ZimReader
from emyrge.memory.memory_vault import MemoryVault
from emyrge.mesh.packet_chunker import PacketChunker
from emyrge.server import DEFAULT_PRODUCT_DESCRIPTOR, load_product_sku
from emyrge.swarm.cluster_sim import ClusterCoordinator
from emyrge.swarm.inference import (
    SwarmInference,
    discover_models,
    find_rpc_server_binary,
)
from emyrge.swarm.runtime import (
    local_ips, is_self_announce,
    CoordinatorDiscovery,
    CoordinatorRuntime,
    SwarmNode,
    detect_local_hardware,
)
from emyrge.swarm.watchdog import SwarmWatchdog, peers_from_verified
from emyrge.vision.visual_vault import VisualVault


TIER_NAMES: Dict[int, str] = {
    -1: "Tier -1: Thin-Client / MCU Relay (<=200B Frames)",
    0: "Tier 0: Ultra-Low Spec / Browser Wasm (135M-500M Q4)",
    1: "Tier 1: Legacy 4GB SSE4.2 PC / SBC (0.5B-1.5B Q4)",
    2: "Tier 2: Modern AVX2 / Metal / CUDA PC (3B-8B Q4)",
    3: "Tier 3: Exo / llama.cpp RPC Scavenged LAN Swarm (32B)",
    4: "Tier 4: Settlement Workstation / Multi-GPU Hub (70B+)",
}

# How long a peer keeps a coordinator's cluster-membership notice before it
# expires (the coordinator refreshes it every watchdog probe cycle).
MEMBERSHIP_TTL_SEC = 45.0

SIMULATED_PROFILES: Dict[str, Dict[str, Any]] = {
    "esp32": {
        "cpu_model": "Espressif ESP32-S3 Xtensa LX7 @ 240MHz",
        "mock": {
            "platform": "freertos",
            "os_version": "ESP-IDF v5.2",
            "arch": "unknown",
            "cpu_flags": [],
            "cpu_cores_physical": 2,
            "cpu_cores_logical": 2,
            "ram_total_mb": 8,
            "ram_free_mb": 4,
            "gpu_name": None,
            "vram_total_mb": 0,
            "is_thin_client": True,
        },
    },
    "pi_zero": {
        "cpu_model": "Broadcom BCM2710A1 Cortex-A53 ARM64 @ 1.0GHz (Pi Zero 2 W)",
        "mock": {
            "platform": "linux",
            "os_version": "Debian Bookworm Lite 6.6",
            "arch": "arm64",
            "cpu_flags": ["neon", "asimd", "crc32"],
            "cpu_cores_physical": 4,
            "cpu_cores_logical": 4,
            "ram_total_mb": 512,
            "ram_free_mb": 290,
            "gpu_name": "VideoCore IV",
            "vram_total_mb": 0,
        },
    },
    "old_laptop": {
        "cpu_model": "Intel(R) Core(TM) i3-380M @ 2.53GHz (2011 Legacy SSE4.2 — No AVX)",
        "mock": {
            "platform": "windows",
            "os_version": "Windows 10 LTSC",
            "arch": "x86_64",
            "cpu_flags": ["sse4_1", "sse4_2"],
            "cpu_cores_physical": 2,
            "cpu_cores_logical": 4,
            "ram_total_mb": 4096,
            "ram_free_mb": 2150,
            "gpu_name": "Intel HD Graphics (Ironlake)",
            "vram_total_mb": 0,
        },
    },
    "chromebook": {
        "cpu_model": "Locked School Chromebook (Air-Gapped WebAssembly Sandbox)",
        "mock": {
            "platform": "browser_wasm",
            "os_version": "ChromeOS 130 Wasm32-SIMD",
            "arch": "unknown",
            "cpu_flags": ["wasm_simd128"],
            "cpu_cores_physical": 2,
            "cpu_cores_logical": 4,
            "ram_total_mb": 2048,
            "ram_free_mb": 900,
            "gpu_name": "WebGPU / WebGL Sandbox",
            "vram_total_mb": 256,
            "is_wasm": True,
        },
    },
    "swarm": {
        "cpu_model": "4-Node Heterogeneous Exo + llama.cpp RPC LAN Cluster",
        "mock": {
            "platform": "lan_swarm",
            "os_version": "Exo P2P Ring + llama.cpp RPC",
            "arch": "x86_64",
            "cpu_flags": ["sse4_2", "avx2", "neon", "cuda", "metal"],
            "cpu_cores_physical": 18,
            "cpu_cores_logical": 32,
            "ram_total_mb": 36864,
            "ram_free_mb": 28400,
            "gpu_name": "Pooled RTX 3060 12GB + Apple M1 Metal",
            "vram_total_mb": 18432,
            "cuda_available": True,
            "metal_available": True,
            "is_swarm": True,
        },
    },
    "supercomputer": {
        "cpu_model": "AMD EPYC 9354P 32-Core + 4x NVIDIA RTX 4090 Settlement Hub",
        "mock": {
            "platform": "linux",
            "os_version": "Ubuntu 24.04 LTS Server",
            "arch": "x86_64",
            "cpu_flags": ["sse4_1", "sse4_2", "avx", "avx2", "avx512"],
            "cpu_cores_physical": 32,
            "cpu_cores_logical": 64,
            "ram_total_mb": 131072,
            "ram_free_mb": 108500,
            "gpu_name": "4x NVIDIA GeForce RTX 4090 (NVLink)",
            "vram_total_mb": 98304,
            "cuda_available": True,
        },
    },
}


def _detect_host_cpu_model() -> str:
    """Detects human-readable CPU brand string using pure stdlib."""
    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if name and str(name).strip():
                    return str(name).strip()
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    proc = platform.processor()
    return proc.strip() if proc and proc.strip() else f"{platform.machine()} Processor"


def _to_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_bool(val: Any, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    return str(val).strip().lower() in ("1", "true", "yes", "on", "turbid", "cloudy")


# ---------------------------------------------------------------------------
# Shared Application Runtime State
# ---------------------------------------------------------------------------

class EmyrgeRuntime:
    """Centralized thread-safe orchestrator holding all eMyrge subsystems."""

    def __init__(self, config: EmyrgeConfig) -> None:
        self.config = config
        self.config.ensure_directories()

        self._lock = threading.RLock()
        self.simulated_tier: str = "auto"
        self.host_cpu_model: str = _detect_host_cpu_model()
        self.product_info: Dict[str, Any] = load_product_sku(self.config.project_root)

        # Initialize Memory & Visual Vaults
        self.memory_vault = MemoryVault(db_path=self.config.vault_dir / "memory.sqlite", seed_if_empty=True)
        self.visual_vault = VisualVault(
            conn=self.memory_vault.conn,
            uploads_dir=self.config.uploads_dir,
            seed_if_empty=True,
        )

        # Initialize Offline Knowledge Readers with built-in survival & STEM seed corpus
        self.zim_reader = ZimReader(
            data_dir=self.config.zim_dir,
            fallback_articles=DEFAULT_ZIM_ARTICLES,
        )
        self.khan_curriculum = KhanCurriculum(
            db_path=self.config.data_dir / "khan_curriculum.sqlite",
            fallback_lessons=DEFAULT_KHAN_LESSONS,
        )

        # Initialize Background Kiwix (8081) and llama-server (8082) Runners
        self.kiwix_runner = KiwixRunner(project_root=self.config.project_root, host="127.0.0.1", port=8081)
        self.model_runner = ModelRunner(project_root=self.config.project_root, host="127.0.0.1", port=8082)

        # Kick off non-blocking background server discovery
        threading.Thread(target=self._background_warmup, daemon=True).start()

        # Live swarm state (from src/emyrge/swarm/runtime.py) — singletons per process
        self.swarm_node: Optional[SwarmNode] = None
        self.swarm_discovery: Optional[CoordinatorDiscovery] = None
        self.swarm_coordinator: Optional[CoordinatorRuntime] = None
        self.swarm_last_plan: Optional[Dict[str, Any]] = None
        # turnkey swarm state: health watchdog, UI event feed, options
        self.swarm_watchdog: Optional[SwarmWatchdog] = None
        self.swarm_events: List[Dict[str, Any]] = []
        self.swarm_dropped: List[Dict[str, Any]] = []
        self.swarm_options: Dict[str, bool] = {"auto_reform": True}
        # cluster-membership notice pushed to us by the coordinating node
        # (task: peers' UIs should reflect that they joined a cluster)
        self.swarm_membership: Dict[str, Any] = {}
        self.swarm_local_hw: Dict[str, Any] = detect_local_hardware()
        # local ip set for self-announce recognition (loopback + per-interface)
        self.swarm_local_ips: frozenset = local_ips()
        # distributed-inference launcher (coordinator + peer roles in one)
        self.swarm_inference = SwarmInference(
            project_root=self.config.project_root,
            on_event=self._swarm_event,
            web_port=self.config.port,
        )

        # Initialize Grounding Harness
        self.harness = GroundingHarness(
            zim_reader=self.zim_reader,
            khan_curriculum=self.khan_curriculum,
            model_runner=self.model_runner,
            source_audit=SourceAudit,
            memory_db=self.memory_vault.conn,
        )

    def _background_warmup(self) -> None:
        try:
            self.kiwix_runner.ensure_started()
        except Exception:
            pass
        try:
            self.model_runner.ensure_started()
        except Exception:
            pass

    def get_active_hardware(self) -> Dict[str, Any]:
        with self._lock:
            sim = self.simulated_tier

        if sim != "auto" and sim in SIMULATED_PROFILES:
            preset = SIMULATED_PROFILES[sim]
            profile = HardwareProbe.probe_system(mock_data=preset["mock"])
            cpu_model = preset["cpu_model"]
        else:
            profile = HardwareProbe.probe_system()
            if self.config.tier_override is not None:
                profile.tier = self.config.tier_override
            cpu_model = self.host_cpu_model

        tier_int = int(profile.tier)
        flags_list = list(profile.cpu_flags.raw_flags) if profile.cpu_flags.raw_flags else [
            k for k, v in profile.cpu_flags.to_dict().items() if k != "raw_flags" and v
        ]
        strategy = HardwareProbe.get_prompting_strategy(tier_int)

        return {
            "os": f"{profile.platform} ({profile.os_version})" if profile.os_version else profile.platform,
            "platform": profile.platform,
            "arch": profile.arch.value,
            "cpu_model": cpu_model,
            "cpu_flags": flags_list,
            "cpu_cores_physical": profile.cpu_cores_physical,
            "cpu_cores_logical": profile.cpu_cores_logical,
            "ram_total_mb": profile.ram_total_mb,
            "ram_free_mb": profile.ram_free_mb,
            "gpu_name": profile.gpu_name or "CPU Vector Execution (No Discrete GPU)",
            "vram_mb": profile.vram_total_mb,
            "tier": tier_int,
            "tier_name": TIER_NAMES.get(tier_int, f"Tier {tier_int}"),
            "strategy": strategy,
            "execution_engine": profile.execution_engine.value,
            "recommended_model": profile.recommended_model_id,
            "context_window_tokens": profile.context_window_tokens,
        }

    def get_status_payload(self) -> Dict[str, Any]:
        hw = self.get_active_hardware()
        llm_st = self.model_runner.get_status()
        kiwix_st = self.kiwix_runner.get_status()
        platforms_ready = llm_st.get("platforms_ready") or probe_usb_platforms(self.config.project_root)

        product_meta = {
            "sku": self.product_info.get("sku", "Product2"),
            "product_id": self.product_info.get("product_id", "fieldready"),
            "name": self.product_info.get("name", "OffGridUSB — FieldReady"),
            "tagline": self.product_info.get("tagline", ""),
            "tiers": self.product_info.get("tiers", [0, 1]),
            "target_drive_size_gb": self.product_info.get("target_drive_size_gb", 32),
            "features": list(self.product_info.get("features", [])),
            "hidden_features": list(self.product_info.get("hidden_features", [])),
            "active_models": list(self.product_info.get("active_models", [])),
            "active_zim_archives": list(self.product_info.get("active_zim_archives", [])),
            "default_model": self.product_info.get("default_model", ""),
        }

        return {
            "ok": True,
            "status": "ready" if (llm_st.get("llm_ready") or llm_st.get("llm_running")) else "standby",
            "hardware": hw,
            "services": {
                "llm_running": llm_st["llm_running"],
                "llm_ready": llm_st["llm_ready"],
                "llm_port": llm_st["llm_port"],
                "llm_model": llm_st["llm_model"],
                "llm_engine": llm_st["llm_engine"],
                "kiwix_running": kiwix_st["kiwix_running"],
                "kiwix_port": kiwix_st["kiwix_port"],
                "kiwix_url": kiwix_st["kiwix_url"],
                "zim_files": kiwix_st["zim_files"],
            },
            "platforms_ready": platforms_ready,
            "simulated_tier": self.simulated_tier,
            "product": product_meta,
        }

    def set_simulated_hardware(self, profile_name: str) -> Dict[str, Any]:
        norm = (profile_name or "auto").strip().lower()
        alias_map = {
            "auto": "auto",
            "host": "auto",
            "real": "auto",
            "esp32": "esp32",
            "mcu": "esp32",
            "thin_client": "esp32",
            "pi_zero": "pi_zero",
            "pi_zero2": "pi_zero",
            "old_laptop": "old_laptop",
            "laptop_sse4": "old_laptop",
            "legacy": "old_laptop",
            "chromebook": "chromebook",
            "wasm": "chromebook",
            "swarm": "swarm",
            "exo": "swarm",
            "supercomputer": "supercomputer",
            "workstation": "supercomputer",
        }
        chosen = alias_map.get(norm, "auto")
        with self._lock:
            self.simulated_tier = chosen
        return self.get_status_payload()

    def run_calculator(self, calc_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        ctype = (calc_type or "").strip().lower()
        p = params or {}

        if ctype == "water":
            if p.get("volume_gallons") not in (None, ""):
                try:
                    vol_gal = float(p["volume_gallons"])
                except (TypeError, ValueError):
                    raise ValueError("Water volume must be strictly positive")
                if vol_gal <= 0.0:
                    raise ValueError("Water volume must be strictly positive")
                vol = WaterCalculator.gallons_to_liters(vol_gal)
            else:
                raw_vol = p.get("volume_liters", p.get("liters", p.get("volume")))
                if raw_vol is None or raw_vol == "":
                    vol = 5.0
                else:
                    vol = _to_float(raw_vol)
                    if vol is None or vol <= 0.0:
                        raise ValueError("Water volume must be strictly positive")
            turbid = _to_bool(p.get("is_turbid", p.get("turbid", p.get("clarity", p.get("water_clarity")))), False)
            cloudy = _to_bool(p.get("is_cloudy", p.get("cloudy")), False)
            method = str(p.get("method") or "bleach").strip().lower()
            conc_raw = p.get("concentration_pct", p.get("concentration", p.get("bleach_percent")))
            if conc_raw is None or conc_raw == "":
                conc = 6.0
            else:
                conc = _to_float(conc_raw)
                if conc is None or conc <= 0.0 or conc > 15.0:
                    raise ValueError("Concentration must be between 1% and 15%")
            elev = _to_float(p.get("elevation_meters", p.get("elevation")), 0.0) or 0.0
            res = WaterCalculator.calculate(
                {
                    "volume_liters": vol,
                    "is_turbid": turbid or cloudy,
                    "method": method,
                    "concentration_pct": conc,
                    "elevation_meters": max(0.0, elev),
                    "is_cloudy": cloudy or turbid,
                }
            )
            res["summary"] = WaterCalculator.format_mesh_summary(res)
            return res

        if ctype == "solar":
            wh = _to_float(p.get("daily_wh", p.get("wh", p.get("load_wh"))), 600.0) or 600.0
            sys_v = _to_float(p.get("system_voltage", p.get("voltage")), 12.0) or 12.0
            dod = _to_float(p.get("dod", p.get("depth_of_discharge")), 0.8) or 0.8
            if dod > 1.0:  # Handle UI percentage input e.g. 80 -> 0.80
                dod = dod / 100.0
            days = _to_float(p.get("autonomy_days", p.get("days")), 1.0) or 1.0
            inv_eff = _to_float(p.get("inverter_eff", p.get("efficiency")), 0.90) or 0.90
            if inv_eff > 1.0:
                inv_eff = inv_eff / 100.0
            sun_h = _to_float(p.get("peak_sun_hours", p.get("sun_hours")), 4.5) or 4.5
            derate = _to_float(p.get("system_derating", p.get("derating")), 0.77) or 0.77
            if derate > 1.0:
                derate = derate / 100.0

            res = SolarCalculator.calculate_system(
                daily_wh=max(1.0, wh),
                system_voltage=max(6.0, sys_v),
                dod=min(1.0, max(0.1, dod)),
                autonomy_days=max(0.5, days),
                inverter_eff=min(1.0, max(0.1, inv_eff)),
                peak_sun_hours=max(0.5, sun_h),
                system_derating=min(1.0, max(0.1, derate)),
            )
            res["equipment"] = SolarCalculator.get_equipment_recommendations(res)
            res["summary"] = SolarCalculator.format_mesh_summary(res)
            return res

        if ctype == "medical":
            wt = _to_float(p.get("weight_kg", p.get("weight")), 15.0) or 15.0
            if p.get("weight_lbs") not in (None, ""):
                wt = MedicalCalculator.lbs_to_kg(float(p["weight_lbs"]))
            wt = min(250.0, max(2.0, wt))
            med = str(p.get("medication", p.get("drug", p.get("regimen", "ors")))).strip().lower()
            res = MedicalCalculator.calculate({"weight_kg": wt, "medication": med})
            res["summary"] = MedicalCalculator.format_mesh_summary(res)
            return res

        if ctype == "electrical":
            mode = str(p.get("mode") or "ohms_law").strip().lower()
            if mode in ("voltage_drop", "drop") or p.get("one_way_length_meters") is not None or p.get("length_meters") is not None:
                src_v = _to_float(p.get("source_voltage", p.get("voltage", p.get("v"))), 12.0) or 12.0
                curr = _to_float(p.get("current_a", p.get("current", p.get("i"))), 10.0) or 10.0
                length_m = _to_float(p.get("one_way_length_meters", p.get("length_meters", p.get("length"))), 15.0) or 15.0
                awg = str(p.get("wire_awg", p.get("awg", "10"))).strip()
                if awg:
                    res = ElectricalCalculator.calculate_voltage_drop_by_awg(
                        source_voltage=max(1.0, src_v),
                        current_a=max(0.0, curr),
                        one_way_length_meters=max(0.1, length_m),
                        wire_awg=awg if awg in ("14", "12", "10", "8", "6", "4", "2", "1/0", "2/0", "4/0") else "10",
                    )
                else:
                    r_km = _to_float(p.get("wire_resistance_ohm_per_km"), 3.277) or 3.277
                    res = ElectricalCalculator.calculate_dc_voltage_drop(
                        source_voltage=max(1.0, src_v),
                        current_a=max(0.0, curr),
                        one_way_length_meters=max(0.1, length_m),
                        wire_resistance_ohm_per_km=max(0.01, r_km),
                    )
                res["summary"] = ElectricalCalculator.format_mesh_summary(res)
                return res

            # Ohm's Law solver: ensure at least 2 parameters have safe defaults if user submits partial form
            v = _to_float(p.get("v", p.get("voltage")))
            i = _to_float(p.get("i", p.get("current", p.get("current_a"))))
            r = _to_float(p.get("r", p.get("resistance", p.get("resistance_ohm"))))
            pw = _to_float(p.get("p", p.get("power", p.get("watts"))))
            provided = [x for x in (v, i, r, pw) if x is not None and x > 0]
            if len(provided) < 2:
                if v is None:
                    v = 12.0
                if i is None and r is None and pw is None:
                    r = 4.0
                elif r is None and i is None:
                    i = 3.0
            res = ElectricalCalculator.solve_ohms_law(v=v, i=i, r=r, p=pw)
            res["summary"] = ElectricalCalculator.format_mesh_summary(res)
            return res

        raise ValueError(f"Unsupported calculator type '{calc_type}'. Expected water, solar, medical, or electrical.")

    def handle_ask(self, query: str, mode: str = "harness") -> Dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {
                "ok": False,
                "error": "Query must not be empty.",
                "answer": "Please enter a survival, medical, engineering, or STEM question.",
                "mode": mode,
            }

        hw = self.get_active_hardware()
        tier = hw["tier"]
        strategy = hw["strategy"]
        norm_mode = (mode or "harness").strip().lower()

        # 1. Retrieve GroundingHarness sources (Vault Master Notes + built-in ZIM + Khan Curriculum)
        ctx = self.harness.retrieve_context(q, limit=5)
        combined_sources: List[GroundedSource] = list(ctx.sources)

        # 2. Query Live Kiwix Server (Port 8081) for real ZIM passages (`wikipedia_en_medicine_mini`, `zimgit-water`, `zimgit-medicine`)
        live_kiwix = self.kiwix_runner.search_live(q, limit=3, fetch_body=True)
        seen_titles = {s.title.lower() for s in combined_sources}
        for k_hit in live_kiwix:
            t_low = k_hit["title"].lower()
            if t_low not in seen_titles:
                seen_titles.add(t_low)
                combined_sources.append(
                    GroundedSource(
                        source_type="zim",
                        title=k_hit["title"],
                        url_or_id=k_hit["url"],
                        snippet=k_hit["snippet"],
                        section_or_topic=k_hit["book"],
                        full_text=k_hit["full_text"],
                        score=k_hit["score"],
                    )
                )

        combined_sources.sort(key=lambda s: s.score, reverse=True)
        top_sources = combined_sources[:5]

        # 3. Auto-run Deterministic Safety Calculator if safety-critical intent detected
        calc_result: Optional[Dict[str, Any]] = None
        calc_summary: Optional[str] = None
        route_info = CalculatorRouter.analyze_query(q)
        if route_info.route != "general":
            try:
                calc_result = self.run_calculator(route_info.route, route_info.extracted_parameters)
                calc_result["calculator_type"] = route_info.route
                calc_summary = self.harness._format_calculator_context(route_info.route, calc_result)
            except Exception:
                calc_result = None

        citations = self.harness.format_citations(top_sources)
        source_dicts = [s.to_dict() for s in top_sources]
        for sd, s_obj in zip(source_dicts, top_sources):
            sd["full_text"] = s_obj.full_text or s_obj.snippet

        # 4. Direct (Zero-AI) Mode
        if norm_mode in ("direct", "non_harness"):
            if top_sources:
                lead = top_sources[0]
                cit_tag = citations[0].raw_tag if citations else ""
                ans = f"{lead.full_text or lead.snippet} {cit_tag}".strip()
                if calc_summary:
                    ans = f"{calc_summary}\n\n{ans}"
            elif calc_summary:
                ans = calc_summary
            else:
                ans = "No matching offline articles or curriculum lessons found for this query."

            audit_dict = {"is_clean": True, "flagged_claims": [], "annotated_text": ans}
            mem_id = self.memory_vault.store_interaction(
                query=q,
                answer=ans,
                citations=[c.to_dict() for c in citations],
                mode="direct",
                model_tier=tier,
                verified=True,
                needs_distillation=False,
            )
            return {
                "ok": True,
                "answer": ans,
                "source": str(citations[0].raw_tag if citations else ""),
                "annotated_answer": ans,
                "mode": "direct",
                "engine_used": "direct-zim-khan-index (0 LLM tokens)",
                "strategy": "direct_lookup",
                "citations": [c.to_dict() for c in citations],
                "sources": source_dicts,
                "calculator_result": calc_result,
                "audit": audit_dict,
                "memory_id": mem_id,
                "queued_for_distillation": False,
            }

        # 5. Grounded AI Harness Mode
        ctx_blocks: List[str] = []
        if calc_summary:
            ctx_blocks.append(f"[DETERMINISTIC SAFETY ORACLE]\n{calc_summary}")
        for s in top_sources:
            sec_str = f"#{s.section_or_topic}" if s.section_or_topic else ""
            ctx_blocks.append(f"[Source: {s.title}{sec_str}]\n{(s.full_text or s.snippet)[:600]}")
        context_blob = "\n\n".join(ctx_blocks)

        if strategy == "search_then_summarize":
            sys_prompt = (
                "You are OffGridUSB (offgridusb.com) running in SEARCH_THEN_SUMMARIZE mode for compact hardware. "
                "Summarize ONLY the verified facts and exact dosages from the Grounding Passages in 3-5 clear sentences. "
                "Include clickable citations exactly like [Source: Title#Section] or [Lesson: Subject/Topic]. Never invent numbers."
            )
        else:
            sys_prompt = (
                "You are OffGridUSB (offgridusb.com) running in multi-source TOOL_CALLING synthesis mode. "
                "Cross-reference the Deterministic Calculator Oracle, Master Field Notes, and OpenZIM / Khan passages "
                "to deliver an authoritative, step-by-step protocol with inline citations [Source: Title#Section]."
            )

        user_prompt = f"Grounding Passages:\n{context_blob}\n\nField Question: {q}\nGrounded Response:"

        # Thin-client MCU mode simulates compact packet-ready synthesis directly
        if tier == int(HardwareTier.THIN_CLIENT):
            gen_res = {
                "text": ModelRunner._deterministic_synthesis(
                    user_prompt=user_prompt,
                    fallback_sources=source_dicts,
                    calculator_summary=calc_summary,
                )[:360],
                "engine": "esp32-gateway-compact-relay",
                "live_llm": False,
            }
        else:
            gen_res = self.model_runner.complete_chat(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                max_tokens=320,
                fallback_sources=source_dicts,
                calculator_summary=calc_summary,
            )

        draft_answer = gen_res["text"]

        # Ensure at least one verified clickable citation tag is attached
        parsed_cits = self.harness.parse_citations(draft_answer)
        has_source_tag = "[source:" in draft_answer.lower()
        if (not parsed_cits or not has_source_tag) and citations:
            source_cit = next((c for c in citations if c.raw_tag.lower().startswith("[source:")), citations[0])
            tag_to_add = source_cit.raw_tag if source_cit.raw_tag.lower().startswith("[source:") else f"[Source: {source_cit.title}]"
            draft_answer = f"{draft_answer.rstrip()} {tag_to_add}"
            if not parsed_cits:
                parsed_cits = [source_cit]
        final_cits = parsed_cits if parsed_cits else citations

        # 6. Two-Pass Numerical Safety Verification (SourceAudit)
        audit_sources = [s.full_text or s.snippet for s in top_sources]
        if calc_summary:
            audit_sources.append(calc_summary)
        audit_report = SourceAudit.audit(draft_answer, audit_sources)

        # Queue for 70B Distillation-on-Dock if running on low-spec hardware (Tier <= 1) or audit flagged discrepancy
        queue_distill = bool(
            (not audit_report.is_clean)
            or (tier <= 1 and len(q.split()) >= 6 and route_info.route in ("medical", "general"))
        )

        mem_id = self.memory_vault.store_interaction(
            query=q,
            answer=audit_report.annotated_text,
            citations=[c.to_dict() for c in final_cits],
            mode="harness",
            model_tier=tier,
            verified=audit_report.is_clean and not queue_distill,
            needs_distillation=queue_distill,
        )

        return {
            "ok": True,
            "answer": draft_answer,
            "source": str(final_cits[0].raw_tag if final_cits else (citations[0].raw_tag if citations else "")),
            "annotated_answer": audit_report.annotated_text,
            "mode": "harness",
            "engine_used": gen_res["engine"],
            "strategy": strategy,
            "citations": [c.to_dict() for c in final_cits],
            "sources": source_dicts,
            "calculator_result": calc_result,
            "audit": audit_report.to_dict(),
            "memory_id": mem_id,
            "queued_for_distillation": queue_distill,
        }

    def handle_knowledge_search(self, query: str) -> Dict[str, Any]:
        q = (query or "").strip()
        kiwix_st = self.kiwix_runner.get_status()
        kiwix_url = kiwix_st["kiwix_url"]

        if not q:
            zim_list = [z.to_dict() for z in self.zim_reader.list_articles(limit=12)]
            khan_list = [
                {
                    "lesson_id": les.lesson_id,
                    "subject": les.subject,
                    "topic": les.topic,
                    "title": les.title,
                    "snippet": les.content[:200],
                }
                for les in self.khan_curriculum._lessons.values()
            ]
            return {
                "ok": True,
                "query": "",
                "total": len(zim_list) + len(khan_list),
                "zim_results": zim_list,
                "khan_results": khan_list,
                "kiwix_url": kiwix_url,
                "kiwix_running": kiwix_st["kiwix_running"],
            }

        # Combine live Kiwix search + built-in ZIM corpus
        zim_out: List[Dict[str, Any]] = []
        seen_titles: set[str] = set()

        for kh in self.kiwix_runner.search_live(q, limit=6, fetch_body=False):
            zim_out.append(
                {
                    "title": kh["title"],
                    "url": kh["url"],
                    "snippet": kh["snippet"],
                    "section": kh["book"],
                    "score": kh["score"],
                    "live_kiwix": True,
                }
            )
            seen_titles.add(kh["title"].lower())

        for zs in self.zim_reader.search(q, limit=6):
            if zs.title.lower() not in seen_titles:
                d = zs.to_dict()
                art = self.zim_reader.get_article(zs.url)
                if art:
                    d["full_text"] = art.text_content
                d["live_kiwix"] = False
                zim_out.append(d)

        khan_out = [ks.to_dict() for ks in self.khan_curriculum.search(q, limit=6)]
        return {
            "ok": True,
            "query": q,
            "total": len(zim_out) + len(khan_out),
            "zim_results": zim_out,
            "khan_results": khan_out,
            "kiwix_url": kiwix_url,
            "kiwix_running": kiwix_st["kiwix_running"],
        }

    # ------------------------------------------------------------------
    # Live swarm runtime management (src/emyrge/swarm/runtime.py)
    # ------------------------------------------------------------------

    def _swarm_event(self, kind: str, msg: str) -> None:
        with self._lock:
            self.swarm_events.append({"ts": time.time(), "kind": kind, "msg": msg})
            if len(self.swarm_events) > 50:
                self.swarm_events = self.swarm_events[-50:]

    def _reform_cluster(self, alive_peers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Watchdog callback: re-plan against the surviving peers only."""
        with self._lock:
            coordinator = self.swarm_coordinator or CoordinatorRuntime()
            self.swarm_coordinator = coordinator
            seeds = [{"ip": p["ip"], "port": int(p.get("port", 50052))} for p in alive_peers]
        plan = coordinator.form_cluster(seeds=seeds, discovered=[])
        with self._lock:
            self.swarm_last_plan = plan
        self._announce_membership((plan.get("live") or {}).get("handshakes") or [])
        return plan

    def _announce_membership(self, handshakes: List[Dict[str, Any]]) -> None:
        """Tell every verified peer's web app that it is part of this cluster.

        Each peer's UI then shows an "in cluster" badge (membership expires on
        the peer after MEMBERSHIP_TTL_SEC without a refresh, so a dead
        coordinator is reflected too). Runs in a background thread so cluster
        formation and watchdog probe cycles never block on HTTP.
        """
        live_hs = [
            h for h in (handshakes or [])
            if isinstance(h, dict) and h.get("ok") and h.get("ip") and h.get("web_port")
        ]
        # never announce to ourselves (loopback web app on our own port)
        targets = [
            (str(h["ip"]), int(h["web_port"]))
            for h in live_hs
            if not (str(h["ip"]).startswith("127.") or str(h["ip"]) == "::1")
            or int(h["web_port"]) != int(self.config.port)
        ]
        if not targets:
            return
        payload = {
            "coordinator": f"offgrid-{os.getpid()}",
            "coordinator_web_port": int(self.config.port),
            "peers": [
                {"id": h.get("id"), "ip": h.get("ip"), "port": h.get("port"),
                 "ram_mb": h.get("ram_mb"), "vram_mb": h.get("vram_mb")}
                for h in live_hs
            ],
        }
        data = json.dumps(payload).encode("utf-8")

        def _post_all() -> None:
            for ip, wp in targets:
                try:
                    req = urllib.request.Request(
                        f"http://{ip}:{wp}/api/swarm/cluster/announce",
                        data=data,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=2.0).read()
                except Exception:
                    pass  # best-effort; peer expiry handles unreachable peers

        threading.Thread(target=_post_all, daemon=True, name="swarm-membership-announce").start()

    def _watchdog_cycle(self, alive_peers: List[Dict[str, Any]]) -> None:
        """Watchdog hook: keep peer membership notices fresh every probe cycle."""
        self._announce_membership(alive_peers)

    def _start_watchdog(self, plan: Dict[str, Any]) -> None:
        """Start (or replace) the health watchdog after a successful scan."""
        if self.swarm_watchdog is not None:
            self.swarm_watchdog.stop()
            self.swarm_watchdog = None
        if not self.swarm_options.get("auto_reform", True):
            return
        live = (plan or {}).get("live") or {}
        verified = live.get("verified_nodes") or []
        # peers come from the live handshake results (ip+port are authoritative);
        # memory fields get enriched from the plan's layer_split below.
        peers = peers_from_verified(live.get("handshakes") or [])
        peers = [p for p in peers if p.get("id") in verified]
        # enrich peers with memory data from the plan's layer split
        split_by_id = {}
        for s in (plan or {}).get("layer_split") or []:
            split_by_id[s.get("node_id")] = s
        for p in peers:
            s = split_by_id.get(p.get("id")) or {}
            p["ram_mb"] = s.get("ram_mb") or p.get("ram_mb")
            p["vram_mb"] = s.get("vram_mb") or p.get("vram_mb")
        if not peers:
            return
        wd = SwarmWatchdog(
            peers=peers,
            reform=self._reform_cluster,
            on_event=self._swarm_event,
            on_cycle=self._watchdog_cycle,
        )
        self.swarm_watchdog = wd
        wd.start()

    def swarm_status(self) -> Dict[str, Any]:
        with self._lock:
            node = self.swarm_node.info() if self.swarm_node is not None else None
            discovered = self.swarm_discovery.snapshot() if self.swarm_discovery is not None else []
            # self-announces (loopback copies + stale same-host instances) are
            # this machine, not peers — the UI shows one entry per device
            discovered = [
                d for d in discovered
                if not is_self_announce(d, self.swarm_local_ips, self.config.port)
            ]
            last_plan = self.swarm_last_plan
            watchdog_running = bool(self.swarm_watchdog and self.swarm_watchdog.is_running())
            health = dict(self.swarm_watchdog.health) if self.swarm_watchdog is not None else None
            dropped = list(self.swarm_dropped)
            events = list(self.swarm_events[-20:])
            options = dict(self.swarm_options)
            membership = dict(self.swarm_membership) if self.swarm_membership else None
        # compute peer ages for the UI (stale detection)
        now = time.time()
        for d in discovered:
            ts = d.get("last_seen")
            d["age_s"] = round(now - ts, 1) if isinstance(ts, (int, float)) else None
        wd_nodes = (health or {}).get("nodes") or []
        if watchdog_running and wd_nodes:
            healthy = all(n.get("ok") for n in wd_nodes)
            state = "healthy" if healthy else "degraded"
            dropped_count = sum(1 for n in wd_nodes if not n.get("ok"))
        else:
            live = (last_plan or {}).get("live") or {}
            formed = bool(live.get("cluster_formed"))
            state = "idle" if not last_plan else ("healthy" if formed else "degraded")
            dropped_count = 0
        # peers learn about cluster membership via the coordinator's announce
        if membership is not None:
            age = time.time() - float(membership.get("updated_at") or 0)
            if age > MEMBERSHIP_TTL_SEC:
                membership = None
        if membership is not None and state == "idle":
            state = "member"
        return {
            "ok": True,
            "node_running": node is not None,
            "node": node,
            "discovered": discovered,
            "last_plan": last_plan,
            "watchdog_running": watchdog_running,
            "health": health,
            "dropped": dropped,
            "dropped_count": dropped_count,
            "cluster_state": state,
            "events": events,
            "options": options,
            "membership": membership,
            "live_nodes": self.swarm_live_nodes(),
            "local_hardware": self.swarm_local_hw,
            "inference": self.swarm_inference.status(),
        }

    def swarm_live_nodes(self) -> List[Dict[str, Any]]:
        """Real node inventory for cluster planning (no demo fixtures).

        Merges, in priority order: this device (broadcasting node info, or
        auto-detected hardware when idle), watchdog-tracked peers (with live
        online/offline status), and UDP-discovered peers. Deduped by node id.
        """
        with self._lock:
            node = self.swarm_node.info() if self.swarm_node is not None else None
            discovered = self.swarm_discovery.snapshot() if self.swarm_discovery is not None else []
            health = dict(self.swarm_watchdog.health) if self.swarm_watchdog is not None else None
        nodes: Dict[str, Dict[str, Any]] = {}
        if node is not None:
            nodes[node["id"]] = {
                "id": node["id"], "name": f"{node['id']} (this device)",
                "ip": node["ip"], "port": node["port"],
                "ram_mb": node.get("ram_mb") or 0, "vram_mb": node.get("vram_mb") or 0,
                "arch": node.get("arch") or "unknown", "online": True,
            }
        else:
            hw = self.swarm_local_hw or {}
            if hw.get("ram_mb"):
                nodes["this-device"] = {
                    "id": "this-device", "name": "This device (node not started)",
                    "ip": "127.0.0.1", "port": 50052,
                    "ram_mb": hw.get("ram_mb") or 0, "vram_mb": hw.get("vram_mb") or 0,
                    "arch": hw.get("arch") or "unknown", "online": True,
                }
        for n in (health or {}).get("nodes") or []:
            nid = str(n.get("id") or "")
            if not nid or nid in nodes:
                continue
            nodes[nid] = {
                "id": nid, "name": nid, "ip": n.get("ip") or "0.0.0.0",
                "port": int(n.get("port") or 50052),
                "ram_mb": n.get("ram_mb") or 0, "vram_mb": n.get("vram_mb") or 0,
                "arch": n.get("arch") or "unknown", "online": bool(n.get("ok")),
            }
        for d in discovered:
            nid = str(d.get("id") or "")
            if not nid or nid in nodes:
                continue
            # same self-announce filter as swarm_status — stale same-host
            # instances (different pid id) must not show as separate nodes
            if is_self_announce(d, self.swarm_local_ips, self.config.port):
                continue
            nodes[nid] = {
                "id": nid, "name": nid, "ip": d.get("ip") or "0.0.0.0",
                "port": int(d.get("port") or 50052),
                "ram_mb": d.get("ram_mb") or 0, "vram_mb": d.get("vram_mb") or 0,
                "arch": d.get("arch") or "unknown", "online": True,
            }
        return list(nodes.values())

    def swarm_cluster_announce(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Peer endpoint: the coordinator told us we are part of its cluster."""
        coordinator = str(params.get("coordinator") or "unknown")
        peers_raw = params.get("peers") if isinstance(params.get("peers"), list) else []
        peers = [p for p in peers_raw if isinstance(p, dict) and p.get("id")]
        with self._lock:
            prev = self.swarm_membership.get("coordinator")
            self.swarm_membership = {
                "coordinator": coordinator,
                "coordinator_web_port": params.get("coordinator_web_port"),
                "peers": peers,
                "updated_at": time.time(),
            }
        if prev != coordinator:
            self._swarm_event(
                "cluster_joined",
                f"this node is part of a swarm cluster coordinated by {coordinator} ({len(peers)} peer(s) + coordinator)",
            )
        return {"ok": True}

    def swarm_set_options(self, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if "auto_reform" in params:
                self.swarm_options["auto_reform"] = bool(params["auto_reform"])
            opts = dict(self.swarm_options)
        if not opts.get("auto_reform") and self.swarm_watchdog is not None:
            self.swarm_watchdog.stop()
            self.swarm_watchdog = None
        return {"ok": True, "options": opts, "watchdog_running": bool(self.swarm_watchdog and self.swarm_watchdog.is_running())}

    def swarm_watchdog_stop(self) -> Dict[str, Any]:
        with self._lock:
            wd = self.swarm_watchdog
            self.swarm_watchdog = None
        if wd is not None:
            wd.stop()
            self._swarm_event("watchdog_stopped", "cluster health monitoring stopped by user")
        return {"ok": True}

    def swarm_start_node(self, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if self.swarm_node is not None:
                return {"ok": True, "already_running": True, "node": self.swarm_node.info()}
            node_id = str(params.get("id") or f"offgrid-{os.getpid()}")
            # turnkey default: advertise the REAL machine unless the UI
            # explicitly passes ram_mb/vram_mb overrides.
            auto_detect = not params.get("ram_mb") and not params.get("vram_mb")
            hw = detect_local_hardware() if auto_detect else {}
            ram_mb = int(params.get("ram_mb") or hw.get("ram_mb") or 4096)
            vram_mb = int(params.get("vram_mb") or hw.get("vram_mb") or 0)
            arch = str(params.get("arch") or hw.get("arch") or "x86_64")
            node = SwarmNode(
                node_id=node_id,
                port=int(params.get("port", 50052)),
                rpc_port=int(params.get("rpc_port", 50053)),
                ram_mb=ram_mb,
                vram_mb=vram_mb,
                arch=arch,
                web_port=int(params.get("web_port") or self.config.port),
            )
            try:
                node.start()
            except OSError as exc:
                return {"ok": False, "error": f"failed to bind swarm node ports: {exc}"}
            self.swarm_node = node
            # Ensure this device also listens for UDP announces so it can see peers
            if self.swarm_discovery is None:
                self.swarm_discovery = CoordinatorDiscovery()
                self.swarm_discovery.start()
            info = node.info()
        self._swarm_event("node_started", f"{info['id']} started ({ram_mb} MB RAM, {vram_mb} MB VRAM, {arch})")
        return {"ok": True, "already_running": False, "node": info, "auto_detected": auto_detect}

    def swarm_rpc_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Peer control endpoint: start this machine's ggml-rpc-server."""
        return self.swarm_inference.start_local_rpc(
            port=int(params.get("rpc_port") or 50055),
            binary=params.get("binary") or find_rpc_server_binary(self.config.project_root),
        )

    def swarm_rpc_stop(self) -> Dict[str, Any]:
        """Peer control endpoint: stop this machine's ggml-rpc-server."""
        return self.swarm_inference.stop_local_rpc()

    def swarm_inference_models(self) -> Dict[str, Any]:
        return {"ok": True, "models": discover_models(self.config.project_root)}

    def swarm_inference_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinator: launch distributed inference across the verified cluster."""
        with self._lock:
            plan = self.swarm_last_plan
            health = dict(self.swarm_watchdog.health) if self.swarm_watchdog is not None else None
        live = (plan or {}).get("live") or {}
        if not live.get("cluster_formed"):
            return {"ok": False, "error": "no verified cluster — Form Swarm Cluster first"}
        # peers: verified handshake entries enriched with memory from the plan
        split_by_id = {s.get("node_id"): s for s in (plan or {}).get("layer_split") or []}
        peers = []
        for h in live.get("handshakes") or []:
            if not h.get("ok"):
                continue
            entry = {
                "id": h.get("id"), "ip": h.get("ip"), "port": h.get("port"),
                "web_port": h.get("web_port"),
                "ram_mb": h.get("ram_mb"), "vram_mb": h.get("vram_mb"),
            }
            s = split_by_id.get(h.get("id")) or {}
            entry["ram_mb"] = entry["ram_mb"] or s.get("ram_mb")
            entry["vram_mb"] = entry["vram_mb"] or s.get("vram_mb")
            if entry.get("web_port"):
                peers.append(entry)
        if not peers:
            return {"ok": False, "error": "no cluster peers with a web app to control — upgrade peers to this build"}
        model = str(params.get("model") or "")
        if not model:
            models = discover_models(self.config.project_root)
            if not models:
                return {"ok": False, "error": "no .gguf model staged in data/models/"}
            model = models[0]["path"]
        host_w = None
        local = detect_local_hardware()
        if params.get("host_weight"):
            host_w = float(params["host_weight"])
        elif (health or {}).get("host_weight_mb"):
            host_w = float(health["host_weight_mb"])
        else:
            host_w = float(local.get("ram_mb") or 512) + float(local.get("vram_mb") or 0)
        try:
            extra = params.get("extra_args") if isinstance(params.get("extra_args"), list) else None
        except Exception:
            extra = None
        return self.swarm_inference.start(
            model=model,
            peers=peers,
            host_weight=host_w,
            rpc_port=int(params.get("rpc_port") or 50055),
            llama_port=int(params.get("llama_port") or 8080),
            extra_args=extra,
        )

    def swarm_inference_stop(self) -> Dict[str, Any]:
        return self.swarm_inference.stop()

    def swarm_inference_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        prompt = str(params.get("prompt") or params.get("q") or "")
        if not prompt.strip():
            return {"ok": False, "error": "empty prompt"}
        return self.swarm_inference.chat(
            prompt,
            n_predict=int(params.get("n_predict") or 256),
            temperature=float(params.get("temperature") or 0.8),
        )

    def swarm_stop_node(self) -> Dict[str, Any]:
        with self._lock:
            node = self.swarm_node
            self.swarm_node = None
            node_id = node.id if node is not None else None
        if node is None:
            return {"ok": True, "already_stopped": True}
        try:
            node.stop()
        except Exception:
            pass
        self._swarm_event("node_stopped", f"{node_id} stopped broadcasting")
        return {"ok": True, "already_stopped": False}

    def swarm_scan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Discover live LAN nodes and form a verified cluster (live plan)."""
        window = max(0.0, float(params.get("window", 2.0)))
        seeds_raw = params.get("seeds") if isinstance(params.get("seeds"), list) else []
        seeds: List[Dict[str, Any]] = []
        for s in seeds_raw:
            if not isinstance(s, dict) or not s.get("ip"):
                continue
            try:
                seeds.append({"ip": str(s["ip"]), "port": int(s.get("port", 50052))})
            except (TypeError, ValueError):
                continue
        with self._lock:
            if self.swarm_discovery is None:
                self.swarm_discovery = CoordinatorDiscovery()
                self.swarm_discovery.start()
            if self.swarm_coordinator is None:
                self.swarm_coordinator = CoordinatorRuntime()
            coordinator = self.swarm_coordinator
        time.sleep(window)
        discovered = self.swarm_discovery.snapshot()
        # self-announces are this machine (incl. stale zombie instances from an
        # earlier launch under a different pid id) — never cluster candidates.
        # Also dedupe discovered entries by ip:port (one endpoint = one machine).
        seen_eps = {(str(s["ip"]), int(s["port"])) for s in seeds}
        filtered: List[Dict[str, Any]] = []
        for d in discovered:
            if is_self_announce(d, self.swarm_local_ips, self.config.port):
                self._swarm_event(
                    "self_announce_ignored",
                    f"ignored announce from this machine ({d.get('ip')}) — it is the coordinator host",
                )
                continue
            ep = (str(d.get("ip") or ""), int(d.get("port") or 50052))
            if ep in seen_eps:
                continue
            seen_eps.add(ep)
            filtered.append(d)
        discovered = filtered
        try:
            plan = coordinator.form_cluster(
                seeds=seeds,
                discovered=discovered,
                simulate_drop=bool(params.get("simulate_drop", False)),
            )
        except Exception as exc:
            return {"ok": False, "error": f"cluster formation failed: {exc}"}
        with self._lock:
            self.swarm_last_plan = plan
            dropped_after_scan = [h for h in ((plan.get("live") or {}).get("handshakes") or []) if not h.get("ok")]
            self.swarm_dropped = dropped_after_scan
        live = (plan or {}).get("live") or {}
        if live.get("cluster_formed"):
            self._swarm_event(
                "cluster_formed",
                f"cluster formed: {len(live.get('verified_nodes') or [])} node(s) verified — {plan.get('unlocked_model', '')}",
            )
            self._start_watchdog(plan)
            self._announce_membership(live.get("handshakes") or [])
        elif dropped_after_scan:
            self._swarm_event("scan_failed", f"no cluster: {[h.get('error') for h in dropped_after_scan]}")
        return {"ok": True, **plan}

    def handle_mesh_command(self, command: str) -> Dict[str, Any]:
        cmd = (command or "").strip()
        if not cmd:
            cmd = "@ai emergency water bleach dose"

        lower = cmd.lower()
        if lower.startswith("@log "):
            note = cmd[5:].strip()
            self.memory_vault.store_interaction(
                query=f"[MESH FIELD LOG] {note}",
                answer=f"Logged via Tactical Relay: {note}",
                citations=[],
                mode="mesh_log",
                model_tier=-1,
                verified=True,
                needs_distillation=False,
            )
            reply = f"LOG SAVED: {note}"
        elif lower.startswith("@calc "):
            rest = cmd[6:].strip()
            kv_params: Dict[str, Any] = {}
            tokens = rest.split()
            cmd_type = tokens[0].lower() if tokens else "water"
            for t in tokens[1:]:
                if "=" in t:
                    k, v = t.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip().lower()
                    if v in ("true", "yes", "1"):
                        kv_params[k] = True
                    elif v in ("false", "no", "0"):
                        kv_params[k] = False
                    else:
                        try:
                            kv_params[k] = float(v) if "." in v else int(v)
                        except ValueError:
                            kv_params[k] = v
            route_info = CalculatorRouter.analyze_query(rest)
            merged_params = dict(route_info.extracted_parameters)
            merged_params.update(kv_params)
            ctype = cmd_type if (cmd_type in ("water", "medicine", "solar", "electrical", "telecom", "structural")) else (route_info.route if route_info.route != "general" else "water")
            try:
                res = self.run_calculator(ctype, merged_params)
                reply = res.get("summary") or res.get("mesh_summary") or str(res)
            except Exception as e:
                reply = f"CALC ERR: {e}"
        else:
            q_body = cmd[4:].strip() if lower.startswith("@ai ") else cmd
            ask_res = self.handle_ask(q_body, mode="direct")
            reply = ask_res.get("answer", "")[:380]

        packets = PacketChunker.chunk_reply(reply, max_bytes=200)
        return {
            "ok": True,
            "command": cmd,
            "raw_reply": reply,
            "message": reply,
            "packets": packets,
        }


# ---------------------------------------------------------------------------
# Multi-Threaded Stdlib HTTP Request Handler
# ---------------------------------------------------------------------------

MIME_OVERRIDES: Dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


class EmyrgeHTTPHandler(BaseHTTPRequestHandler):
    """Handles REST JSON endpoints and static SPA assets with zero third-party deps."""

    runtime: EmyrgeRuntime  # Attached dynamically on server creation

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet clean single-line logging; suppress noisy polling logs
        if args and isinstance(args[0], str) and "/api/status" in args[0]:
            return
        try:
            if sys.stderr is not None:
                sys.stderr.write(f"[OffGridUSB HTTP] {self.address_string()} - {format % args}\n")
                sys.stderr.flush()
        except Exception:
            pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Cache-Control", "no-store")

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 25 * 1024 * 1024))
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8", errors="ignore"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if path in ("/api/status", "/api/health", "/api/telemetry"):
                self._send_json(200, self.runtime.get_status_payload())
                return

            if path in ("/api/product", "/api/sku"):
                prod = dict(self.runtime.product_info)
                prod.setdefault("ok", True)
                prod.setdefault("product", self.runtime.product_info)
                self._send_json(200, prod)
                return

            if path == "/api/knowledge/search":
                q = (qs.get("q") or qs.get("query") or [""])[0]
                self._send_json(200, self.runtime.handle_knowledge_search(q))
                return

            if path == "/api/knowledge/article":
                art_id = (qs.get("id") or qs.get("url") or [""])[0]
                ctype = (qs.get("type") or ["zim"])[0]
                dc = self.runtime.harness.get_direct_content(ctype, art_id)
                if dc:
                    self._send_json(200, {"ok": True, "article": dc.to_dict()})
                else:
                    self._send_json(404, {"ok": False, "error": f"Article '{art_id}' not found"})
                return

            if path == "/api/knowledge/khan":
                subjects = self.runtime.khan_curriculum.get_subjects()
                topics = [t.to_dict() for t in self.runtime.khan_curriculum.get_topics()]
                lessons = [les.to_dict() for les in self.runtime.khan_curriculum._lessons.values()]
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "subjects": subjects,
                        "topics": topics,
                        "lessons": lessons,
                    },
                )
                return

            if path in ("/api/memory", "/api/vault/search"):
                q = (qs.get("q") or qs.get("query") or [""])[0]
                search_res = self.runtime.memory_vault.search(q)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "entries": search_res["entries"],
                        "master_notes": search_res["master_notes"],
                        "pending_count": self.runtime.memory_vault.pending_count(),
                        "fts5_enabled": self.runtime.memory_vault.fts5_available,
                    },
                )
                return

            if path == "/api/vision":
                self._send_json(200, {"ok": True, "photos": self.runtime.visual_vault.list_photos()})
                return

            if path == "/api/swarm/plan":
                plan = ClusterCoordinator.plan_cluster(
                    nodes=self.runtime.swarm_live_nodes(), simulate_drop=False)
                self._send_json(200, {"ok": True, **plan})
                return

            if path == "/api/swarm/status":
                self._send_json(200, self.runtime.swarm_status())
                return

            if path == "/api/swarm/inference/models":
                self._send_json(200, self.runtime.swarm_inference_models())
                return

            # Static File & Uploaded Asset Serving
            self._serve_static(path)

        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc), "trace": traceback.format_exc()[-400:]})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON request body: {exc}"})
            return

        try:
            if path == "/api/simulate-hardware":
                prof = str(body.get("profile", body.get("preset", body.get("hardware", "auto"))))
                status_payload = self.runtime.set_simulated_hardware(prof)
                self._send_json(200, status_payload)
                return

            if path in ("/api/ask", "/api/query", "/api/professor"):
                q = str(body.get("query", body.get("q", "")))
                mode = str(body.get("mode", "harness"))
                res = self.runtime.handle_ask(q, mode=mode)
                self._send_json(200, res)
                return

            clean_path = path.rstrip("/")
            if clean_path in ("/api/calc", "/api/calculators", "/api/calculator/water_purification"):
                ctype = str(body.get("type", body.get("calculator", "water")))
                params = body.get("params") if isinstance(body.get("params"), dict) else {
                    k: v for k, v in body.items() if k not in ("type", "calculator")
                }
                try:
                    calc_res = self.runtime.run_calculator(ctype, params)
                    self._send_json(200, {"ok": True, "type": ctype, "result": calc_res})
                except ValueError as ve:
                    self._send_json(400, {"ok": False, "type": ctype, "error": str(ve)})
                return

            if path == "/api/knowledge/khan/evaluate":
                lesson_id = str(body.get("lesson_id", ""))
                ex_id = str(body.get("exercise_id", ""))
                ans = str(body.get("answer", ""))
                eval_res = self.runtime.khan_curriculum.evaluate_exercise(lesson_id, ex_id, ans)
                self._send_json(200, {"ok": True, "result": eval_res.to_dict()})
                return

            if path == "/api/memory/distill":
                distilled = self.runtime.memory_vault.run_distillation_on_dock()
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "upgraded_count": distilled["upgraded_count"],
                        "upgraded_notes": distilled["upgraded_notes"],
                        "master_notes": distilled["master_notes"],
                        "pending_count": self.runtime.memory_vault.pending_count(),
                    },
                )
                return

            if path in ("/api/memory", "/api/vault"):
                action = str(body.get("action", "query")).lower()
                text = str(body.get("text", body.get("query", body.get("q", ""))))
                if action == "store":
                    answer = str(body.get("answer", body.get("content", text)))
                    cits = body.get("citations", [])
                    entry_id = self.runtime.memory_vault.store_interaction(
                        query=text,
                        answer=answer,
                        citations=cits,
                        mode="manual",
                        model_tier=1,
                        verified=True,
                        needs_distillation=False,
                    )
                    self._send_json(200, {"ok": True, "action": "store", "id": entry_id, "text": text})
                else:
                    search_res = self.runtime.memory_vault.search(text)
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "action": "query",
                            "query": text,
                            "entries": search_res.get("entries", []),
                            "master_notes": search_res.get("master_notes", []),
                        },
                    )
                return

            if path == "/api/vision/upload":
                fname = str(body.get("filename", "field_capture.jpg"))
                b64_data = str(body.get("data_base64", body.get("data", "")))
                notes = str(body.get("notes", ""))
                if not b64_data:
                    self._send_json(400, {"ok": False, "error": "Missing 'data_base64' image payload"})
                    return
                photo = self.runtime.visual_vault.upload_base64_photo(fname, b64_data, notes=notes)
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "photo": photo,
                        "photos": self.runtime.visual_vault.list_photos(),
                    },
                )
                return

            if path == "/api/mesh/send":
                cmd = str(body.get("command", ""))
                self._send_json(200, self.runtime.handle_mesh_command(cmd))
                return

            if path == "/api/swarm/plan":
                nodes = body.get("nodes") if isinstance(body.get("nodes"), list) else None
                # An explicit node list (from the UI's live inventory checkboxes)
                # wins; otherwise plan against the real live cluster, never the
                # demo fixtures.
                if not nodes:
                    nodes = self.runtime.swarm_live_nodes()
                sim_drop = _to_bool(body.get("simulate_drop"), False)
                plan = ClusterCoordinator.plan_cluster(nodes=nodes, simulate_drop=sim_drop)
                self._send_json(200, {"ok": True, **plan})
                return

            if path == "/api/swarm/node/start":
                self._send_json(200, self.runtime.swarm_start_node(body))
                return

            if path == "/api/swarm/node/stop":
                self._send_json(200, self.runtime.swarm_stop_node())
                return

            if path in ("/api/swarm/scan", "/api/swarm/coordinate"):
                self._send_json(200, self.runtime.swarm_scan(body))
                return

            if path == "/api/swarm/options":
                self._send_json(200, self.runtime.swarm_set_options(body))
                return

            if path == "/api/swarm/watchdog/stop":
                self._send_json(200, self.runtime.swarm_watchdog_stop())
                return

            if path == "/api/swarm/rpc/start":
                self._send_json(200, self.runtime.swarm_rpc_start(body))
                return

            if path == "/api/swarm/rpc/stop":
                self._send_json(200, self.runtime.swarm_rpc_stop())
                return

            if path == "/api/swarm/cluster/announce":
                self._send_json(200, self.runtime.swarm_cluster_announce(body))
                return

            if path == "/api/swarm/inference/start":
                self._send_json(200, self.runtime.swarm_inference_start(body))
                return

            if path == "/api/swarm/inference/stop":
                self._send_json(200, self.runtime.swarm_inference_stop())
                return

            if path == "/api/swarm/inference/chat":
                self._send_json(200, self.runtime.swarm_inference_chat(body))
                return

            self._send_json(404, {"ok": False, "error": f"Unknown POST endpoint: {path}"})

        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc), "trace": traceback.format_exc()[-400:]})

    def _serve_static(self, req_path: str) -> None:
        static_root = self.runtime.config.static_dir.resolve()
        uploads_root = self.runtime.config.uploads_dir.resolve()

        # Uploaded visual vault images (`/uploads/<name>`)
        if req_path.startswith("/uploads/"):
            rel_up = req_path[len("/uploads/"):].lstrip("/")
            candidate = (uploads_root / rel_up).resolve()
            if str(candidate).startswith(str(uploads_root)) and candidate.is_file():
                self._stream_file(candidate)
                return
            self._send_json(404, {"ok": False, "error": "Uploaded file not found"})
            return

        # Normalize `/` -> `index.html` (or fallback to `wasm/chromebook.html` if index.html isn't staged yet)
        clean_rel = req_path.lstrip("/")
        if clean_rel.startswith("static/"):
            clean_rel = clean_rel[len("static/"):]

        if clean_rel == "" or clean_rel == "index.html":
            idx_file = static_root / "index.html"
            if idx_file.is_file():
                self._stream_file(idx_file)
                return
            wasm_fallback = static_root / "wasm" / "chromebook.html"
            if wasm_fallback.is_file():
                self._stream_file(wasm_fallback)
                return

        candidate = (static_root / clean_rel).resolve()
        if str(candidate).startswith(str(static_root)) and candidate.is_file():
            self._stream_file(candidate)
            return

        self._send_json(404, {"ok": False, "error": f"Path not found: {req_path}"})

    def _stream_file(self, file_path: Path) -> None:
        ext = file_path.suffix.lower()
        mime = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_server(config: Optional[EmyrgeConfig] = None) -> Tuple[ReusableThreadingHTTPServer, EmyrgeRuntime]:
    cfg = config or EmyrgeConfig.from_env()
    runtime = EmyrgeRuntime(cfg)

    class BoundHandler(EmyrgeHTTPHandler):
        pass

    BoundHandler.runtime = runtime
    server = ReusableThreadingHTTPServer((cfg.host, cfg.port), BoundHandler)
    return server, runtime


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="OffGridUSB (offgridusb.com) Zero-Dependency HTTP Backend")
    parser.add_argument("--host", default=os.environ.get("EMYRGE_HOST", "127.0.0.1"), help="Bind host address")
    parser.add_argument("--port", type=int, default=int(os.environ.get("EMYRGE_PORT", "8000")), help="Bind TCP port")
    parser.add_argument("--headless", action="store_true", help="Headless server mode")
    parser.add_argument("--tier", type=int, default=None, help="Optional hardware tier override (-1..4)")
    args, _ = parser.parse_known_args(argv)

    base_cfg = EmyrgeConfig.from_env()
    base_cfg.host = args.host
    base_cfg.port = args.port
    if args.headless:
        base_cfg.headless = True
    if args.tier is not None:
        base_cfg.tier_override = HardwareTier(args.tier)

    try:
        server, runtime = create_server(base_cfg)
    except OSError as e:
        sys.stderr.write(
            f"[ERROR] Failed to bind {base_cfg.host}:{base_cfg.port} ({e}). "
            f"Try specifying a free port with --port <PORT>.\n"
        )
        return 1

    hw = runtime.get_active_hardware()
    print(f"[OffGridUSB] Air-Gapped Backend Ready -> http://{base_cfg.host}:{base_cfg.port}")
    print(f"[OffGridUSB] Detected Hardware: {hw['cpu_model']} | RAM: {hw['ram_total_mb']} MB | {hw['tier_name']}")
    print("[OffGridUSB] Background Kiwix (8081) & LLM (8082) runners warming up...")
    sys.stdout.flush()

    if not base_cfg.headless:
        browser_host = "127.0.0.1" if base_cfg.host in ("0.0.0.0", "") else base_cfg.host
        target_url = f"http://{browser_host}:{base_cfg.port}"
        threading.Thread(target=webbrowser.open, args=(target_url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OffGridUSB] Shutting down cleanly...")
    finally:
        server.server_close()
        runtime.model_runner.stop()
        runtime.kiwix_runner.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
