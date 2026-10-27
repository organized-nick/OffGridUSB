"""OffGridUSB Command Center Server & SKU Manifest Integration.

Zero-Dependency Air-Gapped Web Server for Project OffGridUSB.
Loads manifests/product_sku.json at startup and exposes product metadata
in GET /api/status and GET /api/product.

Compatible with Python 3.10+ (Windows Embeddable, Linux, macOS)
using only the Python Standard Library.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Fallback default product descriptor for Product2 (FieldReady)
DEFAULT_PRODUCT_DESCRIPTOR: Dict[str, Any] = {
    "schema_version": "1.0",
    "sku": "Product2",
    "product_id": "fieldready",
    "name": "OffGridUSB — FieldReady",
    "tagline": "Tactical Field Survival, Clinical Medical Vault, STEM Education & 3.8B Offline AI",
    "tiers": [0, 1],
    "target_drive_size_gb": 32,
    "min_drive_capacity_bytes": 31450000000,
    "features": [
        "kiwix_reader",
        "grounded_ai_professor",
        "survival_calculators",
        "memory_vault",
        "photo_ocr_vault",
        "stem_tutor",
    ],
    "hidden_features": [
        "swarm_cluster",
        "lan_mesh_rpc",
        "settlement_hub",
        "distillation_on_dock",
        "lora_mesh_agent",
    ],
    "active_models": [
        "smollm2-135m-instruct-q4_k_m.gguf",
        "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "Phi-3.5-mini-instruct-Q4_K_S.gguf",
    ],
    "active_zim_archives": [
        "zimgit-water_en_2024-08.zim",
        "zimgit-medicine_en_2024-08.zim",
        "wikipedia_en_medicine_mini_2026-10.zim",
        "wikipedia_en_top_mini_2026-09.zim",
    ],
    "default_model": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "services": {
        "command_center_port": 8000,
        "kiwix_port": 8081,
        "llama_port": 8082,
    },
    "provisioning": {
        "provisioned_at": "2026-10-27T16:00:00Z",
        "provisioner_version": "1.0.0",
        "filesystem": "exFAT",
        "cluster_size_bytes": 131072,
        "target_drive_letter": "D:",
    },
}


def load_product_sku(project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Loads manifests/product_sku.json relative to repository root / USB root.

    If manifests/product_sku.json does not exist or is malformed,
    defaults gracefully to a standard Product2 descriptor.
    """
    root = project_root
    if root is None:
        candidate = Path(__file__).resolve().parent.parent.parent
        root = candidate

    sku_path = Path(root) / "manifests" / "product_sku.json"
    if sku_path.is_file():
        try:
            content = sku_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                descriptor = dict(DEFAULT_PRODUCT_DESCRIPTOR)
                descriptor.update(data)
                # Guarantee mandatory fields
                if "sku" not in descriptor:
                    descriptor["sku"] = "Product2"
                if "name" not in descriptor:
                    descriptor["name"] = "OffGridUSB — FieldReady"
                if "tiers" not in descriptor:
                    descriptor["tiers"] = [0, 1]
                if "features" not in descriptor:
                    descriptor["features"] = list(DEFAULT_PRODUCT_DESCRIPTOR["features"])
                if "hidden_features" not in descriptor:
                    descriptor["hidden_features"] = list(DEFAULT_PRODUCT_DESCRIPTOR["hidden_features"])
                if "active_models" not in descriptor:
                    descriptor["active_models"] = list(DEFAULT_PRODUCT_DESCRIPTOR["active_models"])
                return descriptor
        except Exception:
            pass

    return dict(DEFAULT_PRODUCT_DESCRIPTOR)


def create_server(config=None):
    from emyrge.web.app import create_server as _create_server
    return _create_server(config)


def main(argv=None):
    from emyrge.web.app import main as _main
    return _main(argv)


def __getattr__(name: str) -> Any:
    if name in ("EmyrgeRuntime", "EmyrgeHTTPHandler", "ReusableThreadingHTTPServer"):
        from emyrge.web import app
        return getattr(app, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "DEFAULT_PRODUCT_DESCRIPTOR",
    "load_product_sku",
    "create_server",
    "main",
    "EmyrgeRuntime",
    "EmyrgeHTTPHandler",
    "ReusableThreadingHTTPServer",
]

if __name__ == "__main__":
    sys.exit(main())
