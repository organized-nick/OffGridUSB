"""Core hardware probing, configuration, and execution tier management for Project eMyrge."""

import sys
from emyrge.core.config import (
    CpuArchitecture,
    CpuFlags,
    EmyrgeConfig,
    EmyrgeError,
    ExecutionEngine,
    HardwareTier,
    PortConflictError,
    ProbeError,
    PromptingStrategy,
    SystemProfile,
    ThinClientProtocolError,
    UnsupportedArchitectureError,
)
from emyrge.core.hardware_probe import HardwareProbe

# Ensure backward/cross compatibility if submodules import emyrge.core.models
from emyrge.core import config as _config_mod
sys.modules["emyrge.core.models"] = _config_mod

__all__ = [
    "HardwareProbe",
    "HardwareTier",
    "PromptingStrategy",
    "ExecutionEngine",
    "CpuArchitecture",
    "CpuFlags",
    "SystemProfile",
    "EmyrgeConfig",
    "EmyrgeError",
    "ProbeError",
    "UnsupportedArchitectureError",
    "PortConflictError",
    "ThinClientProtocolError",
]
