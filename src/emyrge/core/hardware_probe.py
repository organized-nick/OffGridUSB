"""Hardware Elasticity Probing and Dynamic Tier Selection for Project eMyrge.

Zero external dependencies (pure Python 3.14 standard library).
Complies with F-04, F-05, F-06, and F-20 specifications.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from emyrge.core.config import (
    CpuArchitecture,
    CpuFlags,
    ExecutionEngine,
    HardwareTier,
    PromptingStrategy,
    SystemProfile,
)


class HardwareProbe:
    """Hardware diagnostic probing engine for Project eMyrge.

    Inspects host CPU instruction sets, memory capacity, and GPU/VRAM
    to dynamically map execution tiers and prompting strategies.
    """

    @classmethod
    def normalize_cpu_flag(cls, flag: str) -> str:
        """Normalizes CPU flag string, handling hyphens and delimiters (e.g. avx-512 to avx512).

        Examples:
            'avx-512' -> 'avx512'
            'avx-512f' -> 'avx512f'
            'avx-2' -> 'avx2'
        """
        s = str(flag).strip().lower()
        if s.startswith("avx-"):
            s = "avx" + s[4:]
        return re.sub(r"([a-z]+)-(\d+)", r"\1\2", s)

    @classmethod
    def probe_cpu_flags(cls) -> CpuFlags:
        """Detects vector extensions (SSE4.1, SSE4.2, AVX, AVX2, AVX-512, ARM NEON).

        Uses official kernel APIs without executing unverified assembly shellcode.
        """
        plat = platform.system().lower()
        flags: List[str] = []
        sse4_1 = sse4_2 = avx = avx2 = avx512 = neon = False

        if plat == "windows":
            try:
                k32 = ctypes.windll.kernel32
                feature_map = {
                    "sse4_1": 37,  # PF_SSE4_1_INSTRUCTIONS_AVAILABLE
                    "sse4_2": 38,  # PF_SSE4_2_INSTRUCTIONS_AVAILABLE
                    "avx": 39,     # PF_AVX_INSTRUCTIONS_AVAILABLE
                    "avx2": 40,    # PF_AVX2_INSTRUCTIONS_AVAILABLE
                    "avx512": 41,  # PF_AVX512F_INSTRUCTIONS_AVAILABLE
                    "neon": 19,    # PF_ARM_NEON_INSTRUCTIONS_AVAILABLE
                }
                for name, code in feature_map.items():
                    if k32.IsProcessorFeaturePresent(code):
                        flags.append(name)
                sse4_1 = "sse4_1" in flags
                sse4_2 = "sse4_2" in flags
                avx = "avx" in flags
                avx2 = "avx2" in flags
                avx512 = "avx512" in flags
                neon = "neon" in flags
            except Exception:
                # Fallback to registry heuristic
                flags, (sse4_1, sse4_2, avx, avx2, avx512, neon) = cls._probe_windows_registry_cpu()

        elif plat == "linux":
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith(("flags", "Features")):
                            raw = line.split(":", 1)[1].strip().split()
                            flags.extend(raw)
                flags_set = set(flags) | {cls.normalize_cpu_flag(f) for f in flags}
                sse4_1 = "sse4_1" in flags_set
                sse4_2 = "sse4_2" in flags_set
                avx = "avx" in flags_set
                avx2 = "avx2" in flags_set
                avx512 = any(f.startswith("avx512") for f in flags_set)
                neon = bool(flags_set & {"neon", "asimd"})
            except Exception:
                pass

        elif plat == "darwin":
            try:
                if platform.machine().lower() == "arm64":
                    neon = True
                    flags.append("neon")
                else:
                    out = subprocess.check_output(["sysctl", "-a"], text=True, stderr=subprocess.DEVNULL).lower()
                    sse4_1 = "sse4.1" in out or "sse4_1" in out
                    sse4_2 = "sse4.2" in out or "sse4_2" in out
                    avx = "avx1.0" in out or " avx " in out
                    avx2 = "avx2" in out
                    avx512 = "avx512" in out
                    if sse4_1:
                        flags.append("sse4_1")
                    if sse4_2:
                        flags.append("sse4_2")
                    if avx:
                        flags.append("avx")
                    if avx2:
                        flags.append("avx2")
                    if avx512:
                        flags.append("avx512")
            except Exception:
                if platform.machine().lower() == "arm64":
                    neon = True
                    flags.append("neon")

        return CpuFlags(
            sse4_1=sse4_1,
            sse4_2=sse4_2,
            avx=avx,
            avx2=avx2,
            avx512=avx512,
            neon=neon,
            raw_flags=flags,
        )

    @classmethod
    def _probe_windows_registry_cpu(cls) -> Tuple[List[str], Tuple[bool, bool, bool, bool, bool, bool]]:
        """Fallback CPU detection via Windows registry processor string."""
        flags: List[str] = []
        try:
            import winreg

            key_path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                identifier, _ = winreg.QueryValueEx(key, "Identifier")
                name_lower = f"{name} {identifier}".lower()

                # Modern x86_64 processors universally have SSE4
                sse4_1 = sse4_2 = "intel" in name_lower or "amd" in name_lower or "core" in name_lower
                avx = avx2 = any(gen in name_lower for gen in ("core", "ryzen", "xeon", "i3", "i5", "i7", "i9"))
                avx512 = any(gen in name_lower for gen in ("xeon", "skylake-x", "tiger", "zen 4"))
                neon = "arm" in name_lower or "snapdragon" in name_lower
                if sse4_1:
                    flags.extend(["sse4_1", "sse4_2"])
                if avx2:
                    flags.extend(["avx", "avx2"])
                if avx512:
                    flags.append("avx512")
                if neon:
                    flags.append("neon")
                return flags, (sse4_1, sse4_2, avx, avx2, avx512, neon)
        except Exception:
            return flags, (True, True, True, True, False, False)

    @classmethod
    def probe_memory(cls) -> Tuple[int, int]:
        """Returns (ram_total_mb, ram_free_mb)."""
        plat = platform.system().lower()

        if plat == "windows":
            try:
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                mem = MEMORYSTATUSEX()
                mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                    total_mb = int(mem.ullTotalPhys // (1024 * 1024))
                    free_mb = int(mem.ullAvailPhys // (1024 * 1024))
                    return (total_mb, free_mb)
            except Exception:
                pass

        elif plat == "linux":
            try:
                total, free = 0, 0
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total = int(line.split()[1]) // 1024
                        elif line.startswith("MemAvailable:"):
                            free = int(line.split()[1]) // 1024
                if total > 0:
                    return (total, free)
            except Exception:
                pass

        elif plat == "darwin":
            try:
                raw_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
                total_mb = raw_bytes // (1024 * 1024)
                return (total_mb, total_mb // 2)
            except Exception:
                pass

        return (4096, 2048)

    @classmethod
    def probe_gpu(cls) -> Tuple[Optional[str], Optional[str], int, int, bool, bool, bool]:
        """Returns (gpu_name, gpu_vendor, vram_total_mb, vram_free_mb, cuda, metal, vulkan)."""
        # 1. NVIDIA CUDA Driver C-API via ctypes (< 1ms)
        libs = ["nvcuda.dll", "libcuda.so.1", "libcuda.so"]
        for lib in libs:
            try:
                cuda = ctypes.windll.LoadLibrary(lib) if sys.platform == "win32" else ctypes.cdll.LoadLibrary(lib)
                if cuda.cuInit(0) == 0:
                    count = ctypes.c_int()
                    cuda.cuDeviceGetCount(ctypes.byref(count))
                    if count.value > 0:
                        dev = ctypes.c_int()
                        cuda.cuDeviceGet(ctypes.byref(dev), 0)
                        buf = ctypes.create_string_buffer(256)
                        cuda.cuDeviceGetName(buf, 256, dev)
                        name = buf.value.decode("utf-8")
                        total_bytes = ctypes.c_size_t()
                        cuda.cuDeviceTotalMem_v2(ctypes.byref(total_bytes), dev)
                        mb = int(total_bytes.value // (1024 * 1024))
                        return (name, "nvidia", mb, mb, True, False, False)
            except Exception:
                continue

        # 2. nvidia-smi fallback
        if shutil.which("nvidia-smi"):
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out:
                    parts = [p.strip() for p in out.splitlines()[0].split(",")]
                    name = parts[0]
                    total = int(parts[1])
                    free = int(parts[2]) if len(parts) > 2 else total
                    return (name, "nvidia", total, free, True, False, False)
            except Exception:
                pass

        # 3. Apple Silicon Metal Unified Memory
        if platform.system().lower() == "darwin" and platform.machine().lower() == "arm64":
            total_ram, _ = cls.probe_memory()
            metal_vram = int(total_ram * 0.75)
            return ("Apple Silicon GPU (Metal)", "apple", metal_vram, metal_vram, False, True, False)

        # 4. Windows Registry Video Adapter Detection (AMD / Intel / Non-CUDA)
        if sys.platform == "win32":
            try:
                import winreg

                base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
                    idx = 0
                    best_name = None
                    max_vram = 0
                    while True:
                        try:
                            subkey = winreg.EnumKey(root, idx)
                            idx += 1
                            if subkey.isdigit():
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{subkey}") as k:
                                    try:
                                        desc, _ = winreg.QueryValueEx(k, "DriverDesc")
                                        for prop in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                                            try:
                                                raw_val, _ = winreg.QueryValueEx(k, prop)
                                                if isinstance(raw_val, bytes):
                                                    v_mb = int.from_bytes(raw_val, "little") // (1024 * 1024)
                                                elif isinstance(raw_val, int):
                                                    v_mb = raw_val // (1024 * 1024)
                                                else:
                                                    v_mb = 0
                                                if v_mb > max_vram:
                                                    max_vram = v_mb
                                                    best_name = desc
                                                break
                                            except FileNotFoundError:
                                                pass
                                    except FileNotFoundError:
                                        pass
                        except OSError:
                            break
                    if best_name and max_vram > 0:
                        vendor = "amd" if "amd" in best_name.lower() or "radeon" in best_name.lower() else (
                            "intel" if "intel" in best_name.lower() else "unknown"
                        )
                        return (best_name, vendor, max_vram, max_vram, False, False, True)
            except Exception:
                pass

        return (None, None, 0, 0, False, False, False)

    @classmethod
    def get_prompting_strategy(cls, tier: Union[HardwareTier, int]) -> str:
        """Selects prompting strategy based on HardwareTier or tier integer.

        Tiers -1, 0, 1 -> "search_then_summarize"
        Tiers 2, 3, 4 -> "tool_calling"
        """
        tier_val = int(tier)
        if tier_val <= 1:
            return PromptingStrategy.SEARCH_THEN_SUMMARIZE.value
        return PromptingStrategy.TOOL_CALLING.value

    @classmethod
    def probe_system(cls, mock_data: Optional[Dict[str, Any]] = None) -> SystemProfile:
        """Assembles a complete SystemProfile, resolving HardwareTier, ExecutionEngine,
        and PromptingStrategy dynamically.
        """
        if mock_data is not None:
            plat = mock_data.get("platform", "linux")
            arch_str = mock_data.get("arch", "x86_64")
            if arch_str in [a.value for a in CpuArchitecture]:
                arch = CpuArchitecture(arch_str)
            elif arch_str in ("amd64", "x86_64"):
                arch = CpuArchitecture.X86_64
            elif arch_str in ("arm64", "aarch64"):
                arch = CpuArchitecture.ARM64
            else:
                arch = CpuArchitecture.UNKNOWN

            raw_flags = mock_data.get("cpu_flags", {})
            if isinstance(raw_flags, CpuFlags):
                cpu_flags = raw_flags
            elif isinstance(raw_flags, list):
                raw_list = [str(f).lower() for f in raw_flags]
                normalized = [cls.normalize_cpu_flag(f) for f in raw_list]
                flags_set = set(raw_list) | set(normalized)
                cpu_flags = CpuFlags(
                    sse4_1="sse4_1" in flags_set or "sse4.1" in flags_set or any("sse4" in f for f in flags_set),
                    sse4_2="sse4_2" in flags_set or "sse4.2" in flags_set,
                    avx="avx" in flags_set,
                    avx2="avx2" in flags_set,
                    avx512=any("avx512" in f for f in flags_set),
                    neon=bool(flags_set & {"neon", "asimd"}),
                    raw_flags=list(raw_flags),
                )
            elif isinstance(raw_flags, dict):
                norm_dict = {cls.normalize_cpu_flag(str(k)): v for k, v in raw_flags.items()}
                r_flags = norm_dict.get("raw_flags", raw_flags.get("raw_flags", []))
                cpu_flags = CpuFlags(
                    sse4_1=bool(norm_dict.get("sse4_1", False) or raw_flags.get("sse4_1", False)),
                    sse4_2=bool(norm_dict.get("sse4_2", False) or raw_flags.get("sse4_2", False)),
                    avx=bool(norm_dict.get("avx", False) or raw_flags.get("avx", False)),
                    avx2=bool(norm_dict.get("avx2", False) or raw_flags.get("avx2", False)),
                    avx512=bool(norm_dict.get("avx512", False) or raw_flags.get("avx512", False)),
                    neon=bool(norm_dict.get("neon", False) or raw_flags.get("neon", False)),
                    raw_flags=list(r_flags),
                )
            else:
                cpu_flags = CpuFlags()

            cores_phys = mock_data.get("cpu_cores_physical") or 2
            cores_log = mock_data.get("cpu_cores_logical") or 4
            ram_total = mock_data.get("ram_total_mb")
            if ram_total is None:
                ram_total = 4096
            ram_free = mock_data.get("ram_free_mb")
            if ram_free is None:
                ram_free = ram_total // 2
            gpu_name = mock_data.get("gpu_name")
            gpu_vendor = mock_data.get("gpu_vendor")
            vram_total = mock_data.get("vram_total_mb", mock_data.get("vram_mb", 0))
            vram_free = mock_data.get("vram_free_mb", vram_total)
            cuda = mock_data.get("cuda_available", False)
            metal = mock_data.get("metal_available", False)
            vulkan = mock_data.get("vulkan_available", False)
            is_wasm = mock_data.get("is_wasm", False)
            is_swarm = mock_data.get("is_swarm", False)
            is_thin_client = mock_data.get("is_thin_client", False) or mock_data.get("is_mcu", False)
            os_ver = mock_data.get("os_version", "1.0.0")

        else:
            plat = platform.system().lower()
            os_ver = platform.version()
            mach = platform.machine().lower()
            if mach in ("x86_64", "amd64"):
                arch = CpuArchitecture.X86_64
            elif mach in ("arm64", "aarch64"):
                arch = CpuArchitecture.ARM64
            elif mach in ("i386", "i686", "x86"):
                arch = CpuArchitecture.X86_32
            elif mach.startswith("arm"):
                arch = CpuArchitecture.ARM_32
            else:
                arch = CpuArchitecture.UNKNOWN

            cpu_flags = cls.probe_cpu_flags()
            cores_log = os.cpu_count() or 2
            cores_phys = max(1, cores_log // 2)
            ram_total, ram_free = cls.probe_memory()
            gpu_name, gpu_vendor, vram_total, vram_free, cuda, metal, vulkan = cls.probe_gpu()
            is_wasm = False
            is_swarm = False
            is_thin_client = False

        # Classify Hardware Tier and Runtime Parameters
        if is_thin_client or ram_total < 64:
            tier = HardwareTier.THIN_CLIENT
            engine = ExecutionEngine.THIN_CLIENT
            strat = PromptingStrategy.SEARCH_THEN_SUMMARIZE
            model_id = "none_client_relay"
            ctx_tokens = 256
            max_tokens = 128

        elif is_wasm:
            tier = HardwareTier.TIER_0
            engine = ExecutionEngine.BROWSER_WASM
            strat = PromptingStrategy.SEARCH_THEN_SUMMARIZE
            model_id = "smollm2-135m-q4"
            ctx_tokens = 1024
            max_tokens = 256

        elif is_swarm:
            tier = HardwareTier.TIER_3
            engine = ExecutionEngine.SWARM_RPC
            strat = PromptingStrategy.TOOL_CALLING
            model_id = "qwen2.5-32b-instruct-q4"
            ctx_tokens = 8192
            max_tokens = 1024

        elif ram_total >= 64000 or vram_total >= 24000:
            tier = HardwareTier.TIER_4
            engine = ExecutionEngine.MULTI_GPU if (vram_total >= 24000 or cuda) else ExecutionEngine.NATIVE_X86_64_AVX2
            strat = PromptingStrategy.TOOL_CALLING
            model_id = "llama-3.3-70b-instruct-q4"
            ctx_tokens = 32768
            max_tokens = 2048

        elif ram_total < 1024 or ram_free < 600:
            tier = HardwareTier.TIER_0
            engine = ExecutionEngine.NATIVE_ARM64 if arch == CpuArchitecture.ARM64 else ExecutionEngine.NATIVE_X86_64_SSE4
            strat = PromptingStrategy.SEARCH_THEN_SUMMARIZE
            model_id = "smollm2-360m-q8"
            ctx_tokens = 1024
            max_tokens = 256

        elif ram_total >= 8000 and (cpu_flags.avx2 or metal or cuda or vram_total >= 4000):
            tier = HardwareTier.TIER_2
            engine = ExecutionEngine.NATIVE_METAL if metal else ExecutionEngine.NATIVE_X86_64_AVX2
            strat = PromptingStrategy.TOOL_CALLING
            model_id = "llama-3.2-3b-instruct-q4"
            ctx_tokens = 8192
            max_tokens = 1024

        else:
            tier = HardwareTier.TIER_1
            engine = ExecutionEngine.NATIVE_ARM64 if arch == CpuArchitecture.ARM64 else ExecutionEngine.NATIVE_X86_64_SSE4
            strat = PromptingStrategy.SEARCH_THEN_SUMMARIZE
            model_id = "qwen2.5-1.5b-instruct-q4"
            ctx_tokens = 2048
            max_tokens = 512

        return SystemProfile(
            platform=plat,
            os_version=os_ver,
            arch=arch,
            cpu_flags=cpu_flags,
            cpu_cores_physical=cores_phys,
            cpu_cores_logical=cores_log,
            ram_total_mb=ram_total,
            ram_free_mb=ram_free,
            gpu_name=gpu_name,
            gpu_vendor=gpu_vendor,
            vram_total_mb=vram_total,
            vram_free_mb=vram_free,
            cuda_available=cuda,
            metal_available=metal,
            vulkan_available=vulkan,
            tier=tier,
            execution_engine=engine,
            prompting_strategy=strat,
            recommended_model_id=model_id,
            context_window_tokens=ctx_tokens,
            max_tokens_budget=max_tokens,
        )
