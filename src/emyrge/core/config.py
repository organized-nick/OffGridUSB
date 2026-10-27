"""Configuration, runtime models, and exception taxonomy for Project eMyrge.

Zero external dependencies (pure standard library).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional


class HardwareTier(IntEnum):
    """Hardware execution tier classification:

    -1: Thin client (ESP32, microcontroller, LoRa terminal; no local LLM; packet size <= 200B)
     0: Ultra-low spec / Browser Wasm (Pi Zero 2 512MB RAM, Chromebook Wasm; 135M-360M Q4; ctx <= 1024)
     1: Legacy PC / SBC (10-yr-old laptop 4GB RAM SSE4.2 fallback, Pi 4/5; 0.5B-1.5B Q4; ctx <= 2048)
     2: Modern PC (Modern laptop/desktop 8-32GB RAM, Metal/CUDA/Vulkan; 7B-12B Q4; ctx <= 8192)
     3: Scavenged Swarm (2-8 weak LAN machines pooled via exo or llama.cpp RPC; 30B-35B MoE)
     4: Supercomputer / Multi-GPU Server (64-512GB RAM, multi-GPU; 35B-70B+ Q4; multi-user hub)
    """

    THIN_CLIENT = -1
    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


class PromptingStrategy(str, Enum):
    """Adaptive prompting strategy based on model parameter scale and capability:

    - SEARCH_THEN_SUMMARIZE: Fixed single-turn pipeline (search -> extract top passages -> summarize).
      Mandatory for Tier 0 and Tier 1 micro-models (<1.5B params) to avoid infinite loops and hallucinated function calls.
    - TOOL_CALLING: Multi-step autonomous agent loop (reason -> query search -> invoke calculator -> critique -> synthesize).
      Enabled for Tier 2, Tier 3, and Tier 4 models (>= 7B params).
    """

    SEARCH_THEN_SUMMARIZE = "search_then_summarize"
    TOOL_CALLING = "tool_calling"


class ExecutionEngine(str, Enum):
    """Execution backend engine assigned to the system profile."""

    THIN_CLIENT = "thin_client"
    BROWSER_WASM = "browser_wasm"
    NATIVE_ARM64 = "native_arm64"
    NATIVE_X86_64_SSE4 = "native_x86_64_sse4"
    NATIVE_X86_64_AVX2 = "native_x86_64_avx2"
    NATIVE_METAL = "native_metal"
    SWARM_RPC = "swarm_rpc"
    SWARM_EXO = "swarm_exo"
    MULTI_GPU = "multi_gpu"


class CpuArchitecture(str, Enum):
    """CPU architecture classifications."""

    X86_64 = "x86_64"
    ARM64 = "arm64"
    X86_32 = "x86_32"
    ARM_32 = "arm_32"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CpuFlags:
    """Probed CPU instruction set extensions."""

    sse4_1: bool = False
    sse4_2: bool = False
    avx: bool = False
    avx2: bool = False
    avx512: bool = False
    neon: bool = False
    raw_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sse4_1": self.sse4_1,
            "sse4_2": self.sse4_2,
            "avx": self.avx,
            "avx2": self.avx2,
            "avx512": self.avx512,
            "neon": self.neon,
            "raw_flags": list(self.raw_flags),
        }

    def __contains__(self, item: str) -> bool:
        if item in self.raw_flags:
            return True
        norm = item.lower().replace("-", "").replace(".", "_")
        return bool(getattr(self, norm, False))

    def __iter__(self):
        return iter(self.raw_flags)


@dataclass
class SystemProfile:
    """Complete hardware diagnostic profile output by HardwareProbe.

    Used by TierSelector, ModelRunner, and UI telemetry.
    """

    platform: str
    os_version: str
    arch: CpuArchitecture
    cpu_flags: CpuFlags
    cpu_cores_physical: int
    cpu_cores_logical: int
    ram_total_mb: int
    ram_free_mb: int
    gpu_name: Optional[str] = None
    gpu_vendor: Optional[str] = None
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    cuda_available: bool = False
    metal_available: bool = False
    vulkan_available: bool = False
    tier: HardwareTier = HardwareTier.TIER_0
    execution_engine: ExecutionEngine = ExecutionEngine.NATIVE_X86_64_SSE4
    prompting_strategy: PromptingStrategy = PromptingStrategy.SEARCH_THEN_SUMMARIZE
    recommended_model_id: str = "smollm2-360m-q8"
    context_window_tokens: int = 1024
    max_tokens_budget: int = 512

    @property
    def vram_mb(self) -> int:
        """Alias for vram_total_mb for cross-specification compatibility."""
        return self.vram_total_mb

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "os_version": self.os_version,
            "arch": self.arch.value if isinstance(self.arch, CpuArchitecture) else str(self.arch),
            "cpu_flags": self.cpu_flags.to_dict() if hasattr(self.cpu_flags, "to_dict") else dict(self.cpu_flags),
            "cpu_cores_physical": self.cpu_cores_physical,
            "cpu_cores_logical": self.cpu_cores_logical,
            "ram_total_mb": self.ram_total_mb,
            "ram_free_mb": self.ram_free_mb,
            "gpu_name": self.gpu_name,
            "gpu_vendor": self.gpu_vendor,
            "vram_total_mb": self.vram_total_mb,
            "vram_mb": self.vram_total_mb,
            "vram_free_mb": self.vram_free_mb,
            "cuda_available": self.cuda_available,
            "metal_available": self.metal_available,
            "vulkan_available": self.vulkan_available,
            "tier": int(self.tier),
            "execution_engine": self.execution_engine.value if isinstance(self.execution_engine, ExecutionEngine) else str(self.execution_engine),
            "prompting_strategy": self.prompting_strategy.value if isinstance(self.prompting_strategy, PromptingStrategy) else str(self.prompting_strategy),
            "recommended_model_id": self.recommended_model_id,
            "context_window_tokens": self.context_window_tokens,
            "max_tokens_budget": self.max_tokens_budget,
        }


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class EmyrgeError(Exception):
    """Base exception for all Project eMyrge errors."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ProbeError(EmyrgeError):
    """Raised when hardware inspection encounters an unrecoverable failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ERR_PROBE_FAILED", message, details)


class UnsupportedArchitectureError(ProbeError):
    """Raised when host CPU is 32-bit or unsupported architecture."""

    def __init__(self, message: str = "Unsupported 32-bit architecture", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details)
        self.code = "ERR_UNSUPPORTED_ARCH"


class PortConflictError(EmyrgeError):
    """Raised when the specified HTTP port is already bound."""

    def __init__(self, port: int, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        msg = message or f"Port {port} is occupied; specify a custom port using --port <PORT>"
        super().__init__("ERR_PORT_IN_USE", msg, details or {"port": port})
        self.port = port


class ThinClientProtocolError(EmyrgeError):
    """Raised on invalid serial framing or corrupted ESP32 command."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ERR_ESP32_BAD_FRAME", message, details)


# ---------------------------------------------------------------------------
# Application Configuration
# ---------------------------------------------------------------------------

@dataclass
class EmyrgeConfig:
    """Runtime directory and deployment configuration."""

    project_root: Path
    host: str = "127.0.0.1"
    port: int = 8000
    headless: bool = False
    chromebook_mode: bool = False
    tier_override: Optional[HardwareTier] = None

    data_dir: Path = field(init=False)
    vault_dir: Path = field(init=False)
    zim_dir: Path = field(init=False)
    models_dir: Path = field(init=False)
    uploads_dir: Path = field(init=False)
    static_dir: Path = field(init=False)

    def __post_init__(self):
        self.data_dir = self.project_root / "data"
        self.vault_dir = self.data_dir / "vault"
        self.zim_dir = self.data_dir / "zim"
        self.models_dir = self.data_dir / "models"
        self.uploads_dir = self.data_dir / "uploads"
        self.static_dir = self.project_root / "web" / "static"

    def ensure_directories(self) -> None:
        """Create standard data directories on portable media if missing."""
        for d in (self.vault_dir, self.zim_dir, self.models_dir, self.uploads_dir):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, project_root: Optional[Path] = None) -> EmyrgeConfig:
        root = project_root or Path(__file__).resolve().parent.parent.parent.parent
        host = os.environ.get("EMYRGE_HOST", "127.0.0.1")
        port = int(os.environ.get("EMYRGE_PORT", "8000"))
        headless = os.environ.get("EMYRGE_HEADLESS", "").lower() in ("1", "true", "yes")
        chromebook = os.environ.get("EMYRGE_CHROMEBOOK", "").lower() in ("1", "true", "yes")
        tier_env = os.environ.get("EMYRGE_TIER")
        tier_override = HardwareTier(int(tier_env)) if tier_env is not None else None

        return cls(
            project_root=root,
            host=host,
            port=port,
            headless=headless,
            chromebook_mode=chromebook,
            tier_override=tier_override,
        )
