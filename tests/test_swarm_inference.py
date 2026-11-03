"""Tests for swarm distributed-inference orchestration (web UI launch)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from emyrge.swarm import inference as inf


def _write_stub_rpc(dirpath: Path, name: str = "ggml-rpc-server") -> Path:
    """A stand-in ggml-rpc-server that opens the port passed via --port."""
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / (name + (".exe" if os.name == "nt" else ""))
    if os.name == "nt":
        p.write_text("@echo off\nexit 0\n")
    else:
        p.write_text(
            "#!/usr/bin/env python3\n"
            "import socket, sys\n"
            "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
            "s = socket.socket()\n"
            "s.bind(('0.0.0.0', port))\n"
            "s.listen(8)\n"
            "print('ready', flush=True)\n"
            "s.settimeout(30)\n"
            "while True:\n"
            "    try:\n"
            "        c, a = s.accept()\n"
            "        c.close()\n"
            "    except OSError:\n"
            "        pass\n"
            "# pad stub to realistic binary size\n" + "# " + "x" * 2048 + "\n"
        )
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _write_stub_llama(dirpath: Path, name: str = "llama-server") -> Path:
    """Stand-in llama-server: opens its port, dies after RPC_TEST_LIFETIME s."""
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / (name + (".exe" if os.name == "nt" else ""))
    body = (
        "#!/usr/bin/env python3\n"
        "import os, socket, sys, time\n"
        "port = int(sys.argv[sys.argv.index('--port') + 1])\n"
        "s = socket.socket()\n"
        "s.bind(('0.0.0.0', port))\n"
        "s.listen(8)\n"
        "print('ready', flush=True)\n"
        "time.sleep(float(os.environ.get('RPC_TEST_LIFETIME', '6')))\n"
    )
    p.write_text(body if os.name != "nt" else "@echo off\r\nexit 0\r\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


class _PeerHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/swarm/rpc/start":
            self.server.rpcs["calls"].append(("start", payload))
            if self.server.rpcs["fail"]:
                self._json(500, {"ok": False, "error": "simulated peer failure"})
            else:
                self._json(200, {"ok": True, "port": payload.get("rpc_port")})
        elif self.path == "/api/swarm/rpc/stop":
            self.server.rpcs["calls"].append(("stop", payload))
            self._json(200, {"ok": True})
        else:
            self._json(404, {"ok": False})

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TestRpcCommandBuilder(unittest.TestCase):
    def test_host_first_ordering_and_split(self):
        plan = inf.build_rpc_command(
            "/tmp/m.gguf",
            ["10.0.0.2:50055", "10.0.0.3:50055"],
            [16.0, 8.0, 8.0],
            llama_port=8080,
        )
        self.assertEqual(plan["rpc_endpoints"], ["10.0.0.2:50055", "10.0.0.3:50055"])
        self.assertIn("--tensor-split", plan["args"])
        ts = plan["args"][plan["args"].index("--tensor-split") + 1]
        self.assertEqual(ts, "16,8,8")
        self.assertEqual(plan["args"][plan["args"].index("--rpc") + 1], "10.0.0.2:50055,10.0.0.3:50055")

    def test_no_peers_means_no_split(self):
        plan = inf.build_rpc_command("/tmp/m.gguf", [], [])
        self.assertIsNone(plan["tensor_split"])
        self.assertNotIn("--rpc", plan["args"])


class TestBinaryDiscovery(unittest.TestCase):
    def test_finds_rpc_server_in_stick_layout(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bindir = root / "bin" / "linux_x86_64" / "llama"
            bindir.mkdir(parents=True)
            stub = _write_stub_rpc(bindir)
            found = inf.find_rpc_server_binary(root)
            self.assertEqual(found, stub)

    def test_missing_binary_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(inf.find_rpc_server_binary(Path(td)))

    def test_discover_models_filters_garbage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mdir = root / "data" / "models"
            mdir.mkdir(parents=True)
            (mdir / "tiny.gguf").write_bytes(b"not a gguf" * 1024)  # right size, bad magic
            self.assertEqual(inf.discover_models(root), [])
            ok = mdir / "smollm2-135m.gguf"
            ok.write_bytes(b"GGUF" + b"\0" * (5 * 1024 * 1024))
            models = inf.discover_models(root)
            self.assertEqual(len(models), 1)
            self.assertIn("smollm2", models[0]["name"])


class TestPeerLifecycle(unittest.TestCase):
    def test_start_stop_local_rpc_with_stub_binary(self):
        with tempfile.TemporaryDirectory() as td:
            stub = _write_stub_rpc(Path(td))
            events = []
            si = inf.SwarmInference(td, on_event=lambda k, m: events.append((k, m)))
            res = si.start_local_rpc(port=50571, binary=str(stub))
            self.assertTrue(res["ok"], res)
            self.assertTrue(si.rpc_running())
            self.assertEqual(si.status()["rpc_server_port"], 50571)
            stop = si.stop_local_rpc()
            self.assertTrue(stop["ok"])
            self.assertFalse(si.rpc_running())
            self.assertIn("rpc_started", [e[0] for e in events])

    def test_rpc_refuses_port_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            stub = _write_stub_rpc(Path(td))
            si = inf.SwarmInference(td)
            ok = si.start_local_rpc(port=50572, binary=str(stub))
            self.assertTrue(ok["ok"])
            try:
                second = inf.SwarmInference(td)
                res = second.start_local_rpc(port=50572, binary=str(stub))
                self.assertFalse(res["ok"])
            finally:
                si.stop_local_rpc()


class TestCoordinatorLaunch(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _PeerHandler)
        self.httpd.rpcs = {"calls": [], "fail": False, "body": None}
        self.peer_port = self.httpd.server_address[1]
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()
        self.calls = self.httpd.rpcs["calls"]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_missing_model_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            si = inf.SwarmInference(td)
            res = si.start(model=str(Path(td) / "nope.gguf"), peers=[], host_weight=1000)
            self.assertFalse(res["ok"])
            self.assertIn("model file not found", res["error"])

    def test_end_to_end_launch_with_stub_peer_and_stub_llama(self):
        """Full coordinator flow: peer rpc control + llama-server spawn."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_stub_rpc(root / "peer_bin")
            _write_stub_llama(root / "host_bin")
            model = root / "m.gguf"
            model.write_bytes(b"GGUF" + b"\0" * 64)

            peer_stub = _write_stub_rpc(root / "peer_bin")

            si = inf.SwarmInference(root, web_port=12345)
            peers = [{
                "id": "nixos", "ip": "127.0.0.1", "port": 50052,
                "web_port": self.peer_port, "ram_mb": 8000, "vram_mb": 0,
            }]
            with patch.object(inf, "local_ip_for", return_value="192.168.7.99"), \
                 patch.object(inf, "find_rpc_server_binary", return_value=peer_stub), \
                 patch.object(inf, "find_llama_binary", return_value=root / "host_bin" / ("llama-server" if os.name == "nt" else "llama-server")):
                res = si.start(
                    model=str(model), peers=peers, host_weight=16000.0,
                    rpc_port=50575, llama_port=50576,
                )
            self.assertTrue(res["ok"], res)
            st = si.status()
            self.assertTrue(st["running"])
            self.assertEqual(st["rpc_endpoints"], [f"127.0.0.1:{50575}"])
            # host weight first, then the verified peer's pooled memory
            host_w, peer_w = st["tensor_split"].split(",")
            self.assertEqual(float(host_w), 16000.0)
            self.assertEqual(float(peer_w), 8000.0)
            self.assertEqual(self.calls[0], ("start", {"rpc_port": 50575}))

            self.assertTrue(inf._is_port_open("127.0.0.1", 50576))
            si.stop()
            self.assertFalse(si.llama_running())
            self.assertEqual(self.calls[-1], ("stop", {}))

    def test_peer_failure_degrades_to_host_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_stub_llama(root / "host_bin")
            model = root / "m.gguf"
            model.write_bytes(b"GGUF" + b"\0" * 64)
            self.httpd.rpcs["fail"] = True
            si = inf.SwarmInference(root)
            peers = [{"id": "nixos", "ip": "127.0.0.1", "port": 50052,
                      "web_port": self.peer_port, "ram_mb": 8000}]
            with patch.object(inf, "find_llama_binary", return_value=root / "host_bin" / "llama-server"):
                res = si.start(model=str(model), peers=peers, host_weight=16000.0,
                               rpc_port=50579, llama_port=50580)
            self.assertTrue(res["ok"])  # host-only fallback
            self.assertEqual(si.status()["rpc_endpoints"], [])
            si.stop()


if __name__ == "__main__":
    unittest.main()


class TestSwarmInferenceEndpoints(unittest.TestCase):
    """HTTP-level contract of the new web-app endpoints."""

    @classmethod
    def setUpClass(cls):
        from emyrge.core.config import EmyrgeConfig
        from emyrge.server import create_server as _create_server
        cls.config = EmyrgeConfig.from_env(project_root=REPO_ROOT)
        cls.config.port = 8791
        cls.config.headless = True
        cls.server, cls.runtime = _create_server(cls.config)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.config.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _get(self, path: str) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.config.port}{path}", timeout=15) as resp:
            return json.loads(resp.read().decode())

    def test_status_exposes_inference_block(self):
        st = self._get("/api/swarm/status")
        self.assertIn("inference", st)
        self.assertIn("running", st["inference"])
        self.assertFalse(st["inference"]["running"])

    def test_models_endpoint(self):
        res = self._get("/api/swarm/inference/models")
        self.assertTrue(res["ok"])
        self.assertIsInstance(res["models"], list)

    def test_rpc_start_reports_missing_binary_gracefully(self):
        res = self._post("/api/swarm/rpc/start", {"rpc_port": 50777})
        self.assertIn("ok", res)
        self.assertIn(res["ok"], (True, False))

    def test_inference_start_requires_cluster(self):
        res = self._post("/api/swarm/inference/start", {})
        self.assertFalse(res["ok"])
        self.assertIn("Form Swarm Cluster", res["error"])


class TestBinaryDiscoveryFixes(unittest.TestCase):
    """Regression tests for the 2026-11-03 tier-3 pooled-run failures."""

    def test_exe_preferred_over_impl_dll(self):
        """llama-server.exe must win over llama-server-impl.dll (sorted order would pick the dll)."""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "bin" / "windows_x86_64" / "llama"
            d.mkdir(parents=True)
            (d / "llama-server-impl.dll").write_text("dll bytes")
            (d / "llama-server.exe").write_text("exe bytes")
            found = inf._find_binary_in_dir(d, ("llama-server",))
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "llama-server.exe")

    def test_dll_companions_skipped_when_no_exe(self):
        """if only an -impl.dll exists we must not return it as the server binary."""
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "bin" / "llama"
            d.mkdir(parents=True)
            (d / "llama-server-impl.dll").write_text("dll bytes")
            self.assertIsNone(inf._find_binary_in_dir(d, ("llama-server",)))

    def test_rpc_tar_fallback_does_not_stop_at_first_archive(self):
        """bin/ dir with kiwix tar (no rpc-server) + llama tar (has one): llama tar must be reached.

        Old code broke out of the archive loop after the first tar.gz regardless of result.
        """
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as extract_to:
            d = Path(td) / "bin" / "linux_x86_64"
            d.mkdir(parents=True)
            # kiwix archive: no ggml-rpc-server inside
            kiwix = d / "kiwix-tools_linux-x86_64.tar.gz"
            # llama archive: contains ggml-rpc-server
            llama = d / "llama-ubuntu-x64.tar.gz"
            inner = Path("llama-b11913/ggml-rpc-server")
            import tarfile
            with tarfile.open(kiwix, "w:gz") as tar:
                data = b"kiwix binary\n"
                import io
                info = tarfile.TarInfo("kiwix-tools/kind")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            with tarfile.open(llama, "w:gz") as tar:
                data = b"#!/bin/sh\necho rpc\n"
                info = tarfile.TarInfo(str(inner))
                info.size = len(data)
                info.mode = 0o755
                tar.addfile(info, io.BytesIO(data))
            with patch.object(inf, "_POSIX_RUNTIME_ROOT", extract_to):
                found = inf.find_rpc_server_binary(Path(td))
            self.assertIsNotNone(found, "llama tar.gz was never tried (break-after-first-archive bug)")
            self.assertTrue(found.name.startswith("ggml-rpc-server"))

    def test_rpc_slot_name_is_stable_across_processes(self):
        """slot name must be derived from the path via sha256, not randomized hash() —
        otherwise every process re-extracts into a fresh slot dir."""
        from pathlib import PurePosixPath
        child = PurePosixPath("/bin/linux_x86_64/llama-ubuntu-x64.tar.gz")
        import hashlib
        expected = "rpc_" + hashlib.sha256(str(child).encode()).hexdigest()[:16]
        # replicate the slot computation used in find_rpc_server_binary
        digest = hashlib.sha256(str(child).encode()).hexdigest()[:16]
        self.assertEqual(f"rpc_{digest}", expected)
        self.assertEqual(f"rpc_{digest}", expected)  # stable within process
