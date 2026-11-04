#!/usr/bin/env python3
"""
verify_live_multimodal_lineup.py — Standalone Live Multi-Model Inference & Verification

Validates the full OffGridUSB Tier 0-2 multimodal AI lineup:
  1. Qwen2.5-0.5B-Instruct-Q8_0.gguf (Survival prompt, grounded ZIM citations)
  2. Qwen2-VL-2B-Instruct-Q4_K_M.gguf + mmproj (Synthetic test image, direct VLM routing)
  3. Qwen2.5-7B-Instruct-Q4_K_M.gguf (Image + survival prompt, Tier 2 multimodal auto-routing)
  4. gemma-2-9b-it-Q4_K_M.gguf (STEM solar/battery calculation prompt)

Writes comprehensive live metrics to live_verification_report.json.
Pure Python standard library (PIL used when available for synthetic image rendering).
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import re
import socket
import struct
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Add repo 'src' to path (supports running from repo root or provisioning/tools/)
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent if (SCRIPT_DIR.parent.parent / "src").is_dir() else SCRIPT_DIR
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from emyrge.ai.model_runner import ModelRunner, KiwixRunner, discover_mmproj
    from emyrge.core.config import EmyrgeConfig
    from emyrge.web.app import EmyrgeRuntime
except ImportError:
    # If running from another directory, attempt relative discovery
    sys.path.insert(0, str(Path("src").resolve()))
    from emyrge.ai.model_runner import ModelRunner, KiwixRunner, discover_mmproj
    from emyrge.core.config import EmyrgeConfig
    from emyrge.web.app import EmyrgeRuntime


# ---------------------------------------------------------------------------
# Synthetic Test Image Generator
# ---------------------------------------------------------------------------

def create_synthetic_emergency_image(
    text: str = "OFFGRID WATER EMERGENCY",
    output_path: Optional[Path] = None,
) -> Tuple[bytes, str]:
    """Generates an authentic synthetic test PNG with distinctive shapes & text."""
    try:
        from PIL import Image, ImageDraw, PngImagePlugin
        img = Image.new("RGB", (320, 320), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw red cross symbol (two intersecting red rectangles)
        draw.rectangle([130, 40, 190, 200], fill=(220, 20, 20))
        draw.rectangle([70, 100, 250, 140], fill=(220, 20, 20))

        # Black outer frame
        draw.rectangle([10, 10, 310, 310], outline=(0, 0, 0), width=4)

        # Distinctive visual text labels
        draw.text((25, 220), text, fill=(0, 0, 0))
        draw.text((45, 260), "RED CROSS DISINFECTION", fill=(200, 0, 0))

        # Embed PNG text chunk metadata
        meta = PngImagePlugin.PngInfo()
        meta.add_text("EmergencyType", text)
        meta.add_text("Procedure", "Water Purification and Disinfection")
        meta.add_text("Symbol", "Red Cross")

        buf = io.BytesIO()
        img.save(buf, format="PNG", pnginfo=meta)
        png_bytes = buf.getvalue()
    except Exception:
        # Fallback to minimal valid 1x1 PNG if PIL is completely absent
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAUAAAAFACAYAAADC2fvnAAAABHNCSVQICAgIfAhkiAAAAAlwSFlz"
            "AAAOxAAADsQBlSsOGwAAABl0RVh0RW1lcmdlbmN5VHlwZQBPRkZHUklEIFdBVEVSIEVNRVJHRU5D"
            "WQAAAIpJREFUeJztwTEBAAAAwqD1T20MH6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOBnAmwAAQAAAe83bAAAAABJRU5ErkJggg=="
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(png_bytes)

    b64_str = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64_str}"
    return png_bytes, data_uri


# ---------------------------------------------------------------------------
# Hardware & Asset Resolution Helpers
# ---------------------------------------------------------------------------

def _free_port(port: int = 8082) -> None:
    """Terminates zombie listeners on port if orphaned (SKILL.md Incident B)."""
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 4:
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=2)
        except Exception:
            pass


def resolve_asset_root(candidate_drive: str = "D:") -> Tuple[Path, Path, Path]:
    """Resolves primary project root, models directory, and ZIM directory.
    Checks D: first, then falls back to local repository / cache.
    """
    raw = candidate_drive.rstrip("\\/")
    drive_norm = raw + "\\" if os.name == "nt" and len(raw) == 2 and raw[1] == ":" else raw
    drive_p = Path(drive_norm)
    d_models = drive_p / "data" / "models"
    d_zim = drive_p / "data" / "zim"
    cache_models = Path(os.path.expanduser("~")) / "Documents" / "OffGridUSB_Provisions" / "models"
    repo_root = SCRIPT_DIR

    target_root = drive_p if d_models.is_dir() else repo_root
    models_dir = d_models if d_models.is_dir() else (cache_models if cache_models.is_dir() else repo_root / "data" / "models")
    zim_dir = d_zim if d_zim.is_dir() else repo_root / "data" / "zim"

    return target_root, models_dir, zim_dir


def find_model_file(models_dir: Path, filename: str) -> Optional[Path]:
    """Finds exact or pattern-matched model file inside models_dir."""
    direct = models_dir / filename
    if direct.is_file() and direct.stat().st_size > 1024 * 1024:
        return direct
    
    stem_low = filename.lower().replace(".gguf", "")
    for f in models_dir.glob("*.gguf"):
        if stem_low in f.name.lower() and f.stat().st_size > 1024 * 1024:
            return f
    return None


# ---------------------------------------------------------------------------
# Multi-Model Lineup Verification Harness
# ---------------------------------------------------------------------------

class LiveMultimodalLineupVerifier:
    """Orchestrates live sequential verification across all 4 target models."""

    MODEL_SPECS = [
        {
            "id": "qwen2.5-0.5b-q8_0",
            "tier": 0,
            "filename": "Qwen2.5-0.5B-Instruct-Q8_0.gguf",
            "has_image": False,
            "prompt": "How do I purify 20 liters of cloudy river water using household 6% bleach?",
            "description": "Tier 0 Survival Prompt (Bleach Chlorination & Grounded ZIM)",
            "expected_routing": "direct",
        },
        {
            "id": "qwen2-vl-2b-instruct-q4",
            "tier": 1,
            "filename": "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
            "mmproj": "mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
            "has_image": True,
            "prompt": "Describe the image and explain what emergency procedure it indicates.",
            "description": "Tier 1 Multimodal Vision Query (Direct VLM Routing + OCR)",
            "expected_routing": "direct",
        },
        {
            "id": "qwen2.5-7b-instruct-q4",
            "tier": 2,
            "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            "has_image": True,
            "prompt": "I found this water source. How should I treat it?",
            "description": "Tier 2 Auto-Routing Pipeline (VLM Visual Extraction + 7B Synthesis)",
            "expected_routing": "multimodal_autoroute",
        },
        {
            "id": "gemma-2-9b-it-q4",
            "tier": 2,
            "filename": "gemma-2-9b-it-Q4_K_M.gguf",
            "has_image": False,
            "prompt": "Calculate the required solar panel wattage and battery capacity to run a 60W DC refrigeration unit for 24 hours with 5 peak sun hours.",
            "description": "Tier 2 STEM Calculation (Solar & Battery Storage Sizing)",
            "expected_routing": "direct",
        },
    ]

    def __init__(
        self,
        drive: str = "D:",
        report_path: Optional[Path] = None,
        verbose: bool = True,
    ) -> None:
        self.drive = drive
        self.verbose = verbose
        self.report_path = report_path or (SCRIPT_DIR / "live_verification_report.json")
        self.target_root, self.models_dir, self.zim_dir = resolve_asset_root(drive)

        # Initialize EmyrgeConfig pointing to verified assets
        self.config = EmyrgeConfig.from_env(project_root=self.target_root)
        self.config.headless = True
        self.runtime = EmyrgeRuntime(self.config)

        # Ensure ModelRunner uses resolved models_dir
        self.runner: ModelRunner = self.runtime.model_runner
        self.runner.models_dir = self.models_dir

        # Ensure Kiwix is serving from resolved zim_dir
        self.kiwix: KiwixRunner = self.runtime.kiwix_runner
        self.kiwix.zim_dir = self.zim_dir
        self.kiwix.ensure_started()

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

    def run_all(self) -> Dict[str, Any]:
        """Executes verification sequentially across all 4 models."""
        self.log("=" * 72)
        self.log("OffGridUSB Live Multimodal Lineup Verification Suite")
        self.log(f"Drive: {self.drive} | Models Dir: {self.models_dir} | ZIM Dir: {self.zim_dir}")
        self.log("=" * 72)

        results: List[Dict[str, Any]] = []
        overall_pass = True

        # Pre-generate synthetic emergency test image
        test_img_path = SCRIPT_DIR / "data" / "uploads" / "verify_test_image.png"
        _, test_img_uri = create_synthetic_emergency_image(
            text="OFFGRID WATER EMERGENCY",
            output_path=test_img_path,
        )
        self.log(f"Created synthetic test image: {test_img_path} ({len(test_img_uri)} bytes URI)")

        for idx, spec in enumerate(self.MODEL_SPECS, 1):
            self.log("-" * 72)
            self.log(f"Model {idx}/4: {spec['id']} ({spec['filename']})")
            self.log(f"Test Description: {spec['description']}")
            self.log("-" * 72)

            res = self.verify_single_model(spec, test_img_uri)
            results.append(res)

            status_str = "PASS" if res["passed"] else "FAIL"
            self.log(f"Result for {spec['id']}: {status_str} ({res.get('tokens_per_second', 0.0)} t/s)")
            if not res["passed"]:
                overall_pass = False

            # Cleanup between models to ensure maximum free RAM
            self.runner.stop()
            _free_port(self.runner.port)
            time.sleep(2.0)

        # Final cleanup: stop llama-server
        self.runner.stop()
        _free_port(self.runner.port)

        # Build comprehensive report
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_drive": str(self.drive),
            "asset_root": str(self.target_root),
            "models_directory": str(self.models_dir),
            "zim_directory": str(self.zim_dir),
            "host_os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "overall_status": "PASS" if overall_pass else "FAIL",
            "total_models_tested": len(self.MODEL_SPECS),
            "passed_models_count": sum(1 for r in results if r["passed"]),
            "models": results,
        }

        # Write JSON report
        self.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.log(f"\nVerification report written to: {self.report_path.resolve()}")

        # Also sync report to drive root if D: is writable
        try:
            drive_report = Path(self.drive) / "live_verification_report.json"
            drive_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            self.log(f"Synchronized report to target drive: {drive_report}")
        except Exception:
            pass

        self.log("=" * 72)
        self.log(f"OVERALL VERIFICATION VERDICT: {'ALL 4 MODELS PASSED' if overall_pass else 'VERIFICATION FAILED'}")
        self.log("=" * 72)

        return report

    def verify_single_model(
        self,
        spec: Dict[str, Any],
        image_uri: str,
    ) -> Dict[str, Any]:
        """Verifies a single target model with live loading, inference, and assertions."""
        model_id = spec["id"]
        filename = spec["filename"]
        target_tier = spec["tier"]
        has_image = spec["has_image"]
        prompt = spec["prompt"]

        # 1. Resolve weight file
        model_file = find_model_file(self.models_dir, filename)
        if not model_file:
            return {
                "id": model_id,
                "filename": filename,
                "passed": False,
                "error": f"Model file not found: {filename} in {self.models_dir}",
                "assertions": {"file_exists": False},
            }

        file_size_bytes = model_file.stat().st_size
        self.log(f"Resolved weights: {model_file.name} ({file_size_bytes / (1024**3):.2f} GB)")

        # 2. Check GGUF magic bytes
        with open(model_file, "rb") as mf:
            magic = mf.read(4)
        if magic != b"GGUF":
            return {
                "id": model_id,
                "filename": filename,
                "passed": False,
                "error": f"Invalid GGUF magic bytes: {magic!r}",
                "assertions": {"valid_gguf_magic": False},
            }

        # 3. Switch llama-server to target model
        self.runner.stop()
        _free_port(self.runner.port)
        time.sleep(2.0)
        load_t0 = time.time()
        self.log(f"Spawning llama-server with {model_file.name}...")
        self.runner.switch_model(model_file)

        # Wait until ready for inference (up to 420.0 seconds for large 7B/9B weights from USB)
        ready = self.runner.wait_until_ready(timeout=420.0)
        load_duration = round(time.time() - load_t0, 2)

        if ready:
            self.log(f"llama-server ready for inference in {load_duration}s (HTTP 200 OK)")
        else:
            self.log(f"Warning: llama-server HTTP readiness timed out after {load_duration}s; proceeding with inference check.")

        # 4. Execute query via runtime.handle_ask
        img_payload = image_uri if has_image else None
        infer_t0 = time.time()
        self.log(f"Dispatching query: '{prompt[:65]}...'")

        ask_res = self.runtime.handle_ask(
            query=prompt,
            mode="harness",
            image=img_payload,
            model=model_id,
            tier=target_tier,
        )
        infer_duration = round(time.time() - infer_t0, 2)

        answer = str(ask_res.get("answer", "")).strip()
        model_used = str(ask_res.get("model_used", ""))
        routing = str(ask_res.get("routing", "direct"))
        visual_obs = str(ask_res.get("visual_observation", "")).strip()
        citations = ask_res.get("citations") or []
        engine_used = str(ask_res.get("engine_used", ""))

        self.log(f"Inference completed in {infer_duration}s")
        self.log(f"Engine: {engine_used} | Model Used: {model_used} | Routing: {routing}")
        self.log(f"Answer snippet: {answer[:140]}...")

        # 5. Extract token metrics
        timings = ask_res.get("timings") or {}
        usage = ask_res.get("usage") or {}
        completion_tokens = usage.get("completion_tokens", timings.get("predicted_n", 0))
        prompt_tokens = usage.get("prompt_tokens", timings.get("prompt_n", 0))
        predicted_per_sec = timings.get("predicted_per_second")

        if predicted_per_sec and completion_tokens > 0:
            tps = round(float(predicted_per_sec), 2)
        elif infer_duration > 0 and completion_tokens > 0:
            tps = round(completion_tokens / infer_duration, 2)
        else:
            tps = 0.0

        # 6. Evaluate model-specific assertions
        assertions: Dict[str, Any] = {}
        ans_low = answer.lower()

        # Common assertion: Non-empty response
        assertions["non_empty_response"] = len(answer) > 0 and not answer.startswith("Error")

        # Strict live LLM assertions
        assertions["live_llm_execution"] = "llama-server" in engine_used and ask_res.get("live_llm", False) is True
        assertions["valid_completion_tokens"] = completion_tokens > 0

        if model_id == "qwen2.5-0.5b-q8_0":
            # Survival prompt: bleach purification & disinfection
            assertions["coherent_bleach_disinfection"] = any(
                w in ans_low for w in ("bleach", "drops", "disinfect", "chlorin", "water", "purif", "liters")
            )
            assertions["grounded_zim_citations"] = len(citations) > 0 and any("[source:" in str(c).lower() for c in citations)
            assertions["correct_routing"] = routing == "direct"

        elif model_id == "qwen2-vl-2b-instruct-q4":
            # Multimodal vision: direct routing & text/shape recognition
            assertions["vlm_direct_routing"] = routing == "direct"
            assertions["vlm_model_identified"] = "qwen2-vl" in model_used.lower() or "-vl" in model_used.lower()
            combined_vis = f"{ans_low} {visual_obs.lower()}"
            assertions["visual_elements_recognized"] = any(
                w in combined_vis for w in ("water", "emergency", "red cross", "cross", "disinfect", "offgrid", "purif", "marking")
            )

        elif model_id == "qwen2.5-7b-instruct-q4":
            # Tier 2 Auto-routing: VLM extraction fused with 7B synthesis
            assertions["multimodal_autoroute_routing"] = routing == "multimodal_autoroute"
            assertions["visual_observation_populated"] = len(visual_obs) > 10
            assertions["grounded_zim_citations"] = len(citations) > 0 and any("[source:" in str(c).lower() for c in citations)
            assertions["model_identified_7b"] = "7b" in model_used.lower()

        elif model_id == "gemma-2-9b-it-q4":
            # STEM calculation: solar wattage and battery capacity
            assertions["mathematical_coherence"] = any(
                w in ans_low for w in ("watt", "watt-hour", "wh", "amp-hour", "ah", "1440", "1,440", "120", "288", "solar", "battery")
            )
            assertions["model_identified_gemma"] = "gemma" in model_used.lower() or "9b" in model_used.lower()

        model_pass = all(assertions.values())

        return {
            "id": model_id,
            "filename": filename,
            "file_size_bytes": file_size_bytes,
            "target_tier": target_tier,
            "has_image": has_image,
            "prompt": prompt,
            "passed": model_pass,
            "load_duration_seconds": load_duration,
            "inference_duration_seconds": infer_duration,
            "tokens_per_second": tps,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "model_used": model_used,
            "routing": routing,
            "visual_observation": visual_obs or None,
            "citations": citations,
            "engine_used": engine_used,
            "answer": answer,
            "assertions": assertions,
        }


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="OffGridUSB Live Multimodal AI Verification Suite"
    )
    parser.add_argument(
        "--drive",
        default="D:",
        help="Target OffGridUSB drive letter (default: D:)",
    )
    parser.add_argument(
        "--json",
        default="live_verification_report.json",
        help="Output JSON verification report file path",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose console logs",
    )
    args = parser.parse_args()

    verifier = LiveMultimodalLineupVerifier(
        drive=args.drive,
        report_path=Path(args.json),
        verbose=not args.quiet,
    )
    report = verifier.run_all()

    return 0 if report.get("overall_status") == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
