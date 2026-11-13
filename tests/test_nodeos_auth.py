"""NodeOS reads need the internal key (audit 2026-11-13,
nodeos-unauthenticated-get-exposes-memory-proposal-content).

Created 2026-11-13. NodeOS is published on 127.0.0.1 of the host, which every
local user (another member's cc or hands included) can reach. Memory proposals
carry the owner's remembered text, so every route except /health and
/v1/identity must refuse a caller without X-Internal-Key. Loads the real
nodeos/main.py on a scratch sqlite file; no network.
"""
import importlib.util
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parents[1]
KEY = "test-internal-key-0123456789abcdef"


@pytest.fixture()
def nodeos(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_ENV", "dev")
    monkeypatch.setenv("NODEOS_INTERNAL_KEY", KEY)
    monkeypatch.setenv("NODEOS_SIGNING_SECRET", "test-signing-secret-0123456789")
    monkeypatch.setenv("NODEOS_DB_PATH", str(tmp_path / "nodeos.db"))
    monkeypatch.setenv("NODEOS_MEMORY_LOG_PATH", str(tmp_path / "memory_log.jsonl"))
    monkeypatch.setenv("NODEOS_WORKSPACE_ROOT", str(tmp_path / "repo"))
    spec = importlib.util.spec_from_file_location("nodeos_main_under_test", ROOT / "nodeos" / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init_db()
    return mod


def _get_paths():
    src = (ROOT / "nodeos" / "main.py").read_text()
    return re.findall(r'@app\.get\("([^"]+)"', src)


OPEN = {"/health", "/v1/identity"}


def test_every_get_but_health_and_identity_declares_the_key():
    src = (ROOT / "nodeos" / "main.py").read_text()
    lines = [l for l in src.splitlines() if l.startswith("@app.get(")]
    assert len(lines) >= 17
    for l in lines:
        path = re.match(r'@app\.get\("([^"]+)"', l).group(1)
        if path in OPEN:
            assert "require_internal_key" not in l, path
        else:
            assert "Depends(require_internal_key)" in l, path


def test_reads_refused_without_key(nodeos):
    c = TestClient(nodeos.app, raise_server_exceptions=False)
    probes = ["/v1/memory/proposals", "/v1/memory/proposals/x", "/v1/actions", "/v1/actions/x",
              "/v1/actions/x/commit", "/v1/actions/policy", "/v1/operator/overview",
              "/v1/operator/proposals", "/v1/operator/proposals/x", "/v1/operator/permits",
              "/v1/operator/permits/x", "/v1/operator/audit", "/v1/audit", "/v1/audit/events",
              "/v1/loops/status/x"]
    assert set(p.replace("{proposal_id}", "x").replace("{permit_id}", "x")
               for p in _get_paths()) - OPEN == set(probes)
    for p in probes:
        assert c.get(p).status_code == 401, p
        assert c.get(p, headers={"X-Internal-Key": "wrong"}).status_code == 401, p


def test_proposal_text_readable_with_key_only(nodeos):
    c = TestClient(nodeos.app, raise_server_exceptions=False)
    h = {"X-Internal-Key": KEY}
    r = c.post("/v1/loops/request", headers=h, json={
        "node_id": "n", "agent_id": "a", "loop_type": "research", "ttl_seconds": 60,
        "reason": "test"})
    assert r.status_code == 200, r.text
    permit = r.json()
    r = c.post("/v1/memory/propose", headers=h, json={
        "permit_id": permit["permit_id"],
        "memory_type": "note", "content": "DUMMY private note"})
    assert r.status_code == 200, r.text
    assert c.get("/v1/memory/proposals").status_code == 401
    r = c.get("/v1/memory/proposals", headers=h)
    assert r.status_code == 200
    assert "DUMMY private note" in r.text


def test_health_and_identity_stay_open(nodeos):
    c = TestClient(nodeos.app, raise_server_exceptions=False)
    assert c.get("/health").status_code == 200
    assert c.get("/v1/identity").status_code != 401


def test_api_sends_key_on_every_nodeos_call():
    src = (ROOT / "api" / "main.py").read_text()
    calls = re.findall(r'requests\.(?:get|post)\(\s*f"\{NODEOS_URL\}[^)]*\)', src, re.S)
    assert len(calls) >= 7
    for call in calls:
        assert "headers=_nodeos_headers()" in call, call
