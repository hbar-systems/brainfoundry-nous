"""gpu.sh answer check (scripts/gpu/gpu.sh): status asks the tunnel with Host: localhost,
because the pod's Ollama listens on its loopback and refuses (403) a tailnet Host.
A stub HTTP server stands in for the pod; no RunPod call, no pod.

Run from repo root:
    pytest tests/test_gpu_answers.py -v
"""
from __future__ import annotations

import http.server
import json
import pathlib
import shutil
import subprocess
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GPU = ROOT / "scripts" / "gpu" / "gpu.sh"

pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="needs bash and curl")


class _Ollama(http.server.BaseHTTPRequestHandler):
    hosts: list[str] = []

    def do_GET(self):
        host = self.headers.get("Host") or ""
        self.hosts.append(host)
        if host.split(":")[0] != "localhost":
            self.send_response(403)
            self.end_headers()
            return
        body = json.dumps({"models": [{"name": "qwen3:32b", "model": "qwen3:32b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def stub():
    _Ollama.hosts = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Ollama)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()


def _status(tmp_path, port, model):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    now = int(time.time())
    (state / "private.env").write_text(
        f"PROFILE=private\nPOD=STUB\nSTARTED={now}\nDEADLINE={now + 3600}\nMODEL={model}\nPORT={port}\nSPOKE=1\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "GPU_CONFIG": "/dev/null",
           "GPU_STATE_DIR": str(state), "GPU_BIND": "127.0.0.1"}
    return subprocess.run(["bash", str(GPU), "status"], env=env, capture_output=True, text=True, timeout=30)


def test_status_answers_with_host_localhost(tmp_path, stub):
    r = _status(tmp_path, stub, "qwen3:32b")
    assert r.returncode == 0, r.stderr
    assert "answers yes" in r.stdout
    assert _Ollama.hosts == ["localhost"]


def test_status_says_no_when_model_not_served(tmp_path, stub):
    r = _status(tmp_path, stub, "llama3:8b")
    assert "answers no" in r.stdout
