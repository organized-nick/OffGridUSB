"""Distributed-inference orchestration for the OffGridUSB swarm web UI.

Turns a verified swarm cluster into a running llama.cpp setup with zero
terminal commands, in two roles:

- coordinator (the machine hosting the model via llama-server):
  POSTs RPC control requests to every verified peer's web app
  (each peer announces its ``web_port``), then spawns ``llama-server``
  with ``--rpc ip:port,...`` and proportional ``--tensor-split`` weights.
- peer (any machine running the web app): exposes the control surface
  ``/api/swarm/rpc/{start,stop}`` which starts/stops a local
  ``ggml-rpc-server`` bound on 0.0.0.0:<rpc_port>.

The inference RPC port is deliberately distinct from the swarm handshake
port (50052) to avoid the documented ggml/emyrge port collision; both the
coordinator and the peers default to 50055 for ggml rpc traffic.

100% Python Standard Library.
"""

from __future__ import annotations

import json
import os
import platform
import hashlib
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DEFAULT_INFERENCE_RPC_PORT = 50055
DEFAULT_LLAMA_PORT = 8080
DEFAULT_CTX = 8192
DEFAULT_PARALLEL = 2
_READINESS_TIMEOUT = 20.0
_PEER_HTTP_TIMEOUT = 10.0
_ANNOUNCE_TTL = 0.5


class SwarmInferenceError(Exception):
    """Coordinator-side launcher failure (bad plan, missing binary, spawn error)."""


def _find_binary_in_dir(directory: Path, prefixes: tuple[str, ...]) -> Optional[Path]:
    if not directory.is_dir():
        return None
    children = [c for c in sorted(directory.iterdir()) if c.is_file()]
    # exact-name pass first: '<prefix>.exe' must win over anything else
    for prefix in prefixes:
        for child in children:
            if child.name.lower() == f"{prefix}.exe":
                return child
    for child in children:
        name = child.name.lower()
        # skip companion builds that share the prefix but aren't runnable targets
        # (e.g. llama-server-impl.dll next to llama-server.exe)
        if name.endswith((".dll", ".so.0", ".pdb")):
            continue
        for prefix in prefixes:
            if name.startswith(prefix):
                return child
    return None


def _ensure_posix_executable(path: Path) -> Path:
    if os.name != "nt" and path.is_file() and not os.access(path, os.X_OK):
        try:
            path.chmod(0o755)
        except OSError:
            pass
    return path


_POSIX_RUNTIME_ROOT = "/tmp/emyrge_runtime"  # module-level so tests can override


def _extract_posix_tar_runtime(archive: Path, slot_name: str, prefixes: tuple[str, ...]) -> Optional[Path]:
    """Extract a portable tar.gz llama bundle into /tmp/emyrge_runtime/<slot> (RAM-backed).

    Mirrors the logic in emyrge.ai.model_runner so .so/.dylib symlinks survive
    exFAT sticks; returns the first binary matching ``prefixes`` if present.
    """
    if not archive.is_file() or os.name == "nt":
        return None
    import tarfile

    slot_dir = Path(_POSIX_RUNTIME_ROOT) / slot_name
    try:
        if not (slot_dir / ".complete").exists():
            slot_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(slot_dir)
            (slot_dir / ".complete").touch()
        for child in sorted(slot_dir.rglob("*")):
            if child.is_file() and child.name.lower().startswith(prefixes):
                return _ensure_posix_executable(child)
        for child in sorted(slot_dir.rglob("*")):
            if child.is_dir():
                found = _find_binary_in_dir(child, prefixes)
                if found:
                    return found
    except (OSError, tarfile.TarError):
        return None
    return None


def _platform_dirs(project_root: Path) -> List[Path]:
    sys_name = platform.system().lower()
    mach = platform.machine().lower()
    is_arm = mach in ("arm64", "aarch64")
    if sys_name == "windows":
        tag = "windows_arm64" if is_arm else "windows_x86_64"
        return [project_root / "bin" / tag / "llama", project_root / "bin" / "llama"]
    if sys_name == "darwin":
        tag = "macos_arm64" if is_arm else "macos_x86_64"
        return [project_root / "bin" / tag / "llama"]
    tag = "linux_arm64" if is_arm else "linux_x86_64"
    return [project_root / "bin" / tag / "llama", project_root / "bin" / tag]


def find_llama_binary(project_root: Path) -> Optional[Path]:
    """Locate a host-compatible ``llama-server`` binary (stick layout, PATH)."""
    root = Path(project_root)
    for d in _platform_dirs(root):
        found = _find_binary_in_dir(d, ("llama-server",))
        if found and found.stat().st_size > 1024:
            return found
    for d in _platform_dirs(root):
        for tar_name, slot in (
            ("llama-ubuntu-x64.tar.gz", "linux_x86_64_llama"),
            ("llama-ubuntu-arm64.tar.gz", "linux_arm64_llama"),
            ("llama-macos-arm64.tar.gz", "macos_arm64_llama"),
            ("llama-macos-x64.tar.gz", "macos_x86_64_llama"),
        ):
            archive = d.parent / tar_name if d.name == "llama" else d / tar_name
            if archive.is_file():
                found = _extract_posix_tar_runtime(archive, slot, ("llama-server",))
                if found:
                    return found
    which_bin = shutil.which("llama-server") or shutil.which("llama-server.exe")
    return Path(which_bin) if which_bin else None


def find_rpc_server_binary(project_root: Path) -> Optional[Path]:
    """Locate a host-compatible ``ggml-rpc-server`` binary (stick layout, PATH)."""
    root = Path(project_root)
    for d in _platform_dirs(root):
        found = _find_binary_in_dir(d, ("ggml-rpc-server",))
        if found and found.stat().st_size > 1024:
            return _ensure_posix_executable(found)
    for d in _platform_dirs(root):
        if d.is_dir():
            # llama/rpc archives first; keep trying the remaining archives if one
            # doesn't contain the target binary (bin/ may mix kiwix + llama tars)
            archives = sorted(d.iterdir(), key=lambda c: (not c.name.lower().startswith("llama"), c.name))
            for child in archives:
                if not child.is_file() or not child.name.lower().endswith(".tar.gz"):
                    continue
                digest = hashlib.sha256(str(child).encode()).hexdigest()[:16]
                slot = f"rpc_{digest}"
                found = _extract_posix_tar_runtime(child, slot, ("ggml-rpc-server",))
                if found:
                    return found
    which_bin = shutil.which("ggml-rpc-server") or shutil.which("ggml-rpc-server.exe")
    return Path(which_bin) if which_bin else None


def local_model_dirs() -> List[Path]:
    """Local-disk (non-app-dir) model directories to prefer for big models.

    Tier-3 weights (20 GB+) are unusable from a slow USB/exFAT stick as a live
    model source — the metadata scan spins forever — but the same file on the
    local SSD loads fine. These dirs are scanned only when explicitly asked.
    """
    home = Path.home()
    if os.name == "nt":
        return [home / "Downloads", home / "swarm-tools" / "models"]
    return [home / "models", home / ".local" / "share" / "emyrge" / "models"]


def discover_models(project_root: Path, include_local: bool = False) -> List[Dict[str, Any]]:
    """List valid GGUF weights (>= 5 MB with GGUF magic).

    ``project_root``/data/models is the app's own model dir (the stick).
    With ``include_local``=True, well-known local-disk model dirs are scanned
    too and preferred — UI-launched tier-3 inference must load weights from
    the local disk, never the stick.
    """
    wanted: List[tuple] = [(Path(project_root) / "data" / "models", "app")]
    if include_local:
        for d in local_model_dirs():
            wanted.append((d, "local"))
    out: List[Dict[str, Any]] = []
    seen: set = set()
    # local-disk entries first, then the app dir; alphabetical within each
    for d, label in sorted(wanted, key=lambda t: (t[1] != "local", str(t[0]))):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.gguf")):
            if str(p) in seen:
                continue
            try:
                if p.stat().st_size < 5 * 1024 * 1024:
                    continue
                with open(p, "rb") as fh:
                    if fh.read(4) != b"GGUF":
                        continue
                seen.add(str(p))
                out.append({"path": str(p), "name": p.name,
                            "size_mb": p.stat().st_size // (1024 * 1024),
                            "source": label})
            except OSError:
                continue
    return out


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def local_ip_for(ip: str, port: int) -> str:
    """Best-effort source address this machine would use to reach ip:port."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((ip, max(1, int(port))))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return ""


def _fmt_weight(w: Any) -> str:
    v = float(w)
    return str(int(v)) if v == int(v) else str(round(v, 3))


def build_rpc_command(model: str, rpc_endpoints: List[str], weights: List[float],
                      llama_port: int = DEFAULT_LLAMA_PORT,
                      llama_binary: Optional[str] = None) -> Dict[str, Any]:
    """Assemble the llama-server invocation for a pooled cluster.

    weights are proportional compute-memory shares in the order:
    coordinator first, then every --rpc endpoint in listed order — the
    llama.cpp --tensor-split positional convention.
    """
    args: List[str] = []
    if llama_binary:
        args.append(llama_binary)
    args += ["-m", str(model), "--host", "0.0.0.0", "--port", str(llama_port)]
    if rpc_endpoints:
        args += ["--rpc", ",".join(rpc_endpoints)]
        args += ["--tensor-split", ",".join(_fmt_weight(w) for w in weights)]
    args += ["-ngl", "99", "-c", str(DEFAULT_CTX), "--parallel", str(DEFAULT_PARALLEL)]
    return {
        "args": args,
        "rpc_endpoints": rpc_endpoints,
        "tensor_split": ",".join(_fmt_weight(w) for w in weights) if rpc_endpoints else None,
        "port": llama_port,
    }


def _peer_post(ip: str, web_port: int, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"http://{ip}:{int(web_port)}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=_PEER_HTTP_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        body["_status"] = resp.status
        return body


class SwarmInference:
    """Owns the distributed-inference lifecycle for one web-app process.

    A single instance can act as peer (local ggml-rpc-server), coordinator
    (llama-server + remote peer control), or both; roles are independent.
    """

    def __init__(self, project_root: Any, on_event: Optional[Callable[[str, str], None]] = None,
                 web_port: int = 8000) -> None:
        self.project_root = Path(project_root)
        self.web_port = int(web_port)
        self._event = on_event or (lambda kind, msg: None)
        self._lock = threading.RLock()
        self._starting = False
        self._last_error: Optional[str] = None
        self._rpc_proc: Optional[subprocess.Popen] = None
        self._rpc_port: Optional[int] = None
        self._rpc_binary: Optional[Path] = None
        self._llama_proc: Optional[subprocess.Popen] = None
        self._llama_port: Optional[int] = None
        self._llama_model: Optional[str] = None
        self._rpc_endpoints: List[str] = []
        self._tensor_split: Optional[str] = None
        self._peers: List[Dict[str, Any]] = []
        self._extra: Dict[str, Any] = {}

    # ------------------------------------------------------------------ peer

    def rpc_running(self) -> bool:
        with self._lock:
            return self._rpc_proc is not None and self._rpc_proc.poll() is None

    def start_local_rpc(self, port: int = DEFAULT_INFERENCE_RPC_PORT,
                        binary: Optional[str] = None) -> Dict[str, Any]:
        """Peer role: spawn ggml-rpc-server bound on 0.0.0.0:port."""
        with self._lock:
            if self.rpc_running():
                if self._rpc_port == int(port):
                    return {"ok": True, "already_running": True, "port": int(port),
                            "binary": str(self._rpc_binary)}
                return {"ok": False, "error": f"rpc-server already running on port {self._rpc_port}"}
            path = Path(binary) if binary else find_rpc_server_binary(self.project_root)
            if not path or not path.is_file():
                return {"ok": False, "error": "ggml-rpc-server binary not found on this machine"}
            cmd = [str(path), "--host", "0.0.0.0", "--port", str(int(port))]
            try:
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                env = os.environ.copy()
                if os.name != "nt":
                    lib_dir = str(path.parent)
                    env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
                self._rpc_proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, env=env, creationflags=flags,
                )
            except OSError as exc:
                self._rpc_proc = None
                return {"ok": False, "error": f"failed to spawn ggml-rpc-server: {exc}"}
            self._rpc_port = int(port)
            self._rpc_binary = path
        deadline = time.time() + _READINESS_TIMEOUT
        while time.time() < deadline:
            if _is_port_open("127.0.0.1", port, timeout=0.4):
                break
            if self._rpc_proc is not None and self._rpc_proc.poll() is not None:
                break
            time.sleep(0.2)
        # readiness probe passes on ANY listener on the port — including a
        # pre-existing server we don't own. A freshly spawned binary that
        # fails to bind (EADDRINUSE) exits immediately; require OUR process
        # to still be alive after a short grace period or treat it as a
        # port-conflict failure.
        if self._rpc_proc is not None and self._rpc_proc.poll() is None:
            time.sleep(0.5)
            if self._rpc_proc.poll() is None and _is_port_open("127.0.0.1", port, timeout=0.4):
                self._event("rpc_started", f"ggml-rpc-server online on port {port}")
                return {"ok": True, "already_running": False, "port": int(port), "binary": str(path)}
        self.stop_local_rpc()
        return {"ok": False, "error": f"ggml-rpc-server failed to open port {port} (in use or exited)"}

    def stop_local_rpc(self) -> Dict[str, Any]:
        with self._lock:
            proc, self._rpc_proc, port = self._rpc_proc, None, self._rpc_port
            self._rpc_port = None
        if proc is None:
            return {"ok": True, "already_stopped": True}
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass
        self._event("rpc_stopped", f"ggml-rpc-server on port {port} stopped")
        return {"ok": True, "already_stopped": False}

    # ------------------------------------------------------------ coordinator

    def llama_running(self) -> bool:
        with self._lock:
            return self._llama_proc is not None and self._llama_proc.poll() is None

    def start(self, model: str, peers: List[Dict[str, Any]],
              host_weight: Optional[float] = None,
              rpc_port: int = DEFAULT_INFERENCE_RPC_PORT,
              llama_port: int = DEFAULT_LLAMA_PORT,
              extra_args: Optional[List[str]] = None,
              rpc_binary: Optional[str] = None) -> Dict[str, Any]:
        """Coordinator role: start rpc-servers on peers, then llama-server here.

        ``peers`` are verified handshake dicts with ip/port and, when known,
        web_port (the peer's OffGridUSB web app). Machines without a
        reachable web app are reported per-peer and skipped.
        """
        if not Path(model).is_file():
            return {"ok": False, "error": f"model file not found: {model}"}
        if self.llama_running():
            return {"ok": False, "error": f"inference already running on port {self._llama_port}; stop it first"}
        binary = rpc_binary or find_llama_binary(self.project_root)
        if not binary or not Path(binary).is_file():
            return {"ok": False, "error": "llama-server binary not found on this machine"}

        self_ip_cache: Dict[str, str] = {}
        started: List[Dict[str, Any]] = []
        for p in peers:
            entry = dict(p)
            ip = str(p.get("ip"))
            entry["rpc_port"] = int(p.get("inference_rpc_port") or rpc_port)
            entry["ok"] = False
            entry["detail"] = "skipped"
            web_port = p.get("web_port")
            src_ip = local_ip_for(ip, int(web_port) if web_port else 80) if (ip in ("127.0.0.1",) or web_port) else ""
            is_self = (src_ip and src_ip == ip) or (ip in ("127.0.0.1", "::1") and web_port and int(web_port) == self.web_port)
            if web_port and is_self:
                # this machine hosts the inference; never rpc-control ourselves
                entry["detail"] = "this machine (inference host)"
                started.append(entry)
                continue
            if web_port:
                try:
                    res = _peer_post(ip, int(web_port), "/api/swarm/rpc/start",
                                     {"rpc_port": entry["rpc_port"]})
                    entry["ok"] = bool(res.get("ok"))
                    entry["detail"] = res.get("error") or "started"
                except Exception as exc:  # noqa: BLE001 - peer control is best-effort
                    entry["detail"] = f"peer control failed: {exc}"
            else:
                entry["detail"] = "no web_port announced (peer app too old or absent)"
            started.append(entry)

        endpoints = [f"{e['ip']}:{e['rpc_port']}" for e in started if e["ok"]]
        host_w = float(host_weight) if host_weight else 0.0
        weights = [host_w] + [max(1.0, float(p.get("ram_mb") or 512) + float(p.get("vram_mb") or 0))
                              for p in started if p["ok"]]
        if not any(w > 0 for w in weights):
            weights = [1.0] * len(weights)
        plan = build_rpc_command(model, endpoints, weights, llama_port=llama_port,
                                 llama_binary=str(binary))
        if extra_args:
            for a in extra_args:
                if a not in plan["args"]:
                    plan["args"].append(str(a))

        self._event("inference_start", f"launching llama-server on :{llama_port} "
                    f"({len(endpoints)} rpc endpoint(s), split {plan['tensor_split']})")
        try:
            env = os.environ.copy()
            lib_dir = str(Path(binary).parent)
            if os.name != "nt":
                env["LD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('LD_LIBRARY_PATH', '')}".rstrip(":")
                env["DYLD_LIBRARY_PATH"] = f"{lib_dir}:{env.get('DYLD_LIBRARY_PATH', '')}".rstrip(":")
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            proc = subprocess.Popen(plan["args"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL, cwd=str(Path(binary).parent),
                                    env=env, creationflags=flags)
        except OSError as exc:
            self._event("inference_failed", f"llama-server spawn failed: {exc}")
            return {"ok": False, "error": f"failed to spawn llama-server: {exc}",
                    "peers": started, "plan": plan}

        with self._lock:
            self._llama_proc = proc
            self._llama_port = int(llama_port)
            self._llama_model = str(model)
            self._rpc_endpoints = endpoints
            self._tensor_split = plan["tensor_split"]
            self._peers = started
            self._extra = {"binary": str(binary)}
        deadline = time.time() + _READINESS_TIMEOUT
        while time.time() < deadline:
            if _is_port_open("127.0.0.1", llama_port, timeout=0.5):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.3)
        # same port-ownership check as the peer rpc path: a pre-existing
        # llama-server on the port must not read as OUR success
        if proc.poll() is None:
            time.sleep(0.5)
            if proc.poll() is None and _is_port_open("127.0.0.1", llama_port, timeout=0.5):
                with self._lock:
                    self._peers = started
                self._event("inference_ready", f"llama-server online on :{llama_port} — swarm inference ready")
                return {"ok": True, **self.status()}
        self.stop()
        return {"ok": False, "error": f"llama-server exited or failed to open port {llama_port} (in use?)",
                "peers": started, "plan": plan}

    def start_async(self, model: str, peers: List[Dict[str, Any]],
                    host_weight: Optional[float] = None,
                    rpc_port: int = DEFAULT_INFERENCE_RPC_PORT,
                    llama_port: int = DEFAULT_LLAMA_PORT,
                    extra_args: Optional[List[str]] = None,
                    rpc_binary: Optional[str] = None) -> Dict[str, Any]:
        """Coordinator role, backgrounded: return immediately and run start() in a thread.

        Loading a tier-3 model blocks for minutes; the web app is single-threaded
        and must never wedge on the /api/swarm/inference/start handler. Progress
        and the outcome surface through status() ("starting", "last_error").
        """
        with self._lock:
            if self._starting:
                return {"ok": False, "error": "a launch is already in progress"}
            if self.llama_running():
                return {"ok": False, "error": f"inference already running on port {self._llama_port}; stop it first"}
            self._starting = True
            self._last_error = None

        def _run() -> None:
            try:
                res = self.start(model=model, peers=peers, host_weight=host_weight,
                                 rpc_port=rpc_port, llama_port=llama_port,
                                 extra_args=extra_args, rpc_binary=rpc_binary)
                if not res.get("ok"):
                    with self._lock:
                        self._last_error = res.get("error") or "inference launch failed"
            finally:
                with self._lock:
                    self._starting = False

        threading.Thread(target=_run, daemon=True, name="swarm-inference-start").start()
        return {"ok": True, "starting": True, "model": str(model)}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            proc, self._llama_proc, port = self._llama_proc, None, self._llama_port
            peers, self._peers = self._peers, []
            self._rpc_endpoints = []
            self._tensor_split = None
        results: List[Dict[str, Any]] = []
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    proc.kill()
                except OSError:
                    pass
        for p in peers:
            if p.get("web_port"):
                try:
                    _peer_post(p["ip"], int(p["web_port"]), "/api/swarm/rpc/stop", {})
                    results.append({"id": p.get("id"), "ok": True})
                except Exception as exc:  # noqa: BLE001
                    results.append({"id": p.get("id"), "ok": False, "error": str(exc)})
        if proc is not None:
            self._event("inference_stopped", f"llama-server on :{port} stopped; rpc peers released")
        return {"ok": True, "stopped_peers": results}

    def chat(self, prompt: str, n_predict: int = 256, temperature: float = 0.8) -> Dict[str, Any]:
        """Proxy a /completion request to the locally spawned llama-server."""
        if not self.llama_running():
            return {"ok": False, "error": "no swarm inference running"}
        try:
            with self._lock:
                port = self._llama_port
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/completion",
                data=json.dumps({"prompt": prompt, "n_predict": int(n_predict),
                                 "temperature": float(temperature)}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "content": data.get("content", ""), "raw": data}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"completion failed: {exc}"}

    # ------------------------------------------------------------------ status

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.llama_running(),
                "starting": self._starting,
                "last_error": self._last_error,
                "llama_port": self._llama_port,
                "model": self._llama_model,
                "rpc_endpoints": list(self._rpc_endpoints),
                "tensor_split": self._tensor_split,
                "rpc_server_local": self.rpc_running(),
                "rpc_server_port": self._rpc_port,
                "peers": [dict(p) for p in self._peers],
                "binary": self._extra.get("binary"),
            }
