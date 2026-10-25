"""The Local seat (scripts/cc/cc_local.py and its use in cc-bridge.py), 2026-10-25.

No network, no real codex or model: the fake codex of test_cc_codex.py runs, and the endpoint
probe is a stub. Run from repo root:
    pytest tests/test_cc_local.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
sys.path.insert(0, str(ROOT / "tests"))
import cc_codex  # noqa: E402
import cc_local  # noqa: E402
from test_cc_codex import _fake, _load, _no_popen, RESTRICTIVE  # noqa: E402

KEY = "local-key-THISMUSTNEVERSHOW99"
BASE = "http://100.64.1.2:8000/v1"
ST = {"base": BASE, "model": "qwen-72b", "key": KEY}


class _Resp:
    def __init__(self, status=200):
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _env(monkeypatch, base=BASE, model="qwen-72b", key=KEY):
    for k, v in (("CC_LOCAL_BASE_URL", base), ("CC_LOCAL_MODEL", model), ("CC_LOCAL_API_KEY", key)):
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_command_is_read_only_carries_the_provider_and_no_key():
    for sid in (None, "0199aaaa-bbbb-cccc"):
        cmd = cc_local.build_cmd("/x/codex", "/w", ST, sid)
        for flag in RESTRICTIVE:
            assert flag in cmd, flag
        if not sid:
            assert cmd[cmd.index("-s") + 1] == "read-only"
        for c in ('model_provider="local"', 'model_providers.local.name="local"',
                  f'model_providers.local.base_url="{BASE}"', 'model_providers.local.wire_api="chat"',
                  'model_providers.local.env_key="CC_LOCAL_API_KEY"'):
            assert c in cmd, c
        assert cmd[cmd.index("-m") + 1] == "qwen-72b" and cmd[-1] == "-"
        assert KEY not in " ".join(cmd)
        cc_codex.assert_restrictive(cmd)


def test_a_key_on_the_command_line_is_refused():
    with pytest.raises(cc_codex.Unsafe):
        cc_local.build_cmd("/x/codex", "/w", {"base": BASE + "/" + KEY, "model": "m", "key": KEY})


@pytest.mark.parametrize("bad", ['http://u:p@h/v1', 'ftp://h/v1', 'http://h/v1"x', 'http://h /v1', "javascript:1", ""])
def test_bad_base_urls_count_as_unset(bad):
    assert cc_local.settings({"CC_LOCAL_BASE_URL": bad})["base"] == ""


def test_env_has_only_the_minimal_names_plus_the_key():
    base = {"HOME": "/h", "USER": "hands", "PATH": "/bin", "LANG": "C.UTF-8", "CC_ASK_TOKEN": "t",
            "BRAIN_API_KEY": "b", "ANTHROPIC_API_KEY": "a"}
    e = cc_local.env(base, KEY)
    assert set(e) == {"HOME", "USER", "PATH", "LANG", "TERM", "NO_COLOR", "CC_LOCAL_API_KEY"}
    assert e["CC_LOCAL_API_KEY"] == KEY
    assert "CC_LOCAL_API_KEY" not in cc_codex.env({**base, "CC_LOCAL_API_KEY": KEY})   # the other seat never gets it


def test_probe_refuses_when_unset_and_runs_nothing(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("no request without a base URL")
    assert cc_local.probe({"base": "", "model": "", "key": ""}, opener=boom) == "local model: no endpoint configured"


def test_probe_refuses_when_nothing_answers():
    def down(req, timeout):
        assert timeout == 5 and req.full_url == BASE + "/models"
        raise OSError("timed out")
    assert cc_local.probe(ST, opener=down) == "local model: endpoint not answering, is the pod up?"
    assert cc_local.probe(ST, opener=lambda r, timeout: _Resp(503)) == cc_local.NOT_ANSWERING
    assert cc_local.probe(ST, opener=lambda r, timeout: _Resp(200)) is None


def test_probe_sends_the_key_as_a_header_only():
    seen = []
    cc_local.probe(ST, opener=lambda r, timeout: seen.append(r) or _Resp())
    assert seen[0].get_header("Authorization") == "Bearer " + KEY and KEY not in seen[0].full_url


def test_status_words_and_no_key():
    env = {"CC_LOCAL_BASE_URL": BASE, "CC_LOCAL_MODEL": "qwen-72b", "CC_LOCAL_API_KEY": KEY}
    ok = cc_local.status(env, opener=lambda r, timeout: _Resp())
    assert ok["line"] == "local: qwen-72b at 100.64.1.2:8000" and ok["reachable"] is True and ok["label"] == "Local (read-only)"
    assert KEY not in json.dumps(ok)
    down = cc_local.status(env, opener=lambda r, timeout: (_ for _ in ()).throw(OSError()))
    assert down["line"] == cc_local.NOT_ANSWERING and down["reachable"] is False
    assert cc_local.status({}, live=False)["line"] == cc_local.NO_ENDPOINT


# ------------------------------------------------------------ in the bridge ----
def test_unset_turn_is_refused_and_nothing_runs_or_falls_back(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, str(_fake(tmp_path)))
    _env(monkeypatch, base=None, model=None, key=None)
    monkeypatch.setattr(m.subprocess, "Popen", _no_popen)
    monkeypatch.setattr(m, "_run_turn", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no fallback to Claude")))
    reply, sid, err = m._run_codex_turn("hi", None, on_event=lambda k, p: None, seat="local")
    assert (reply, err) == ("local model: no endpoint configured", True)


def test_unanswering_endpoint_turn_is_refused(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, str(_fake(tmp_path)))
    _env(monkeypatch)
    monkeypatch.setattr(m.subprocess, "Popen", _no_popen)
    monkeypatch.setattr(cc_local.urllib.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(OSError("timed out")))
    reply, sid, err = m._run_codex_turn("hi", None, on_event=lambda k, p: None, seat="local")
    assert (reply, err) == ("local model: endpoint not answering, is the pod up?", True)


def test_local_turn_runs_read_only_with_the_key_in_env_only(monkeypatch, tmp_path):
    f = _fake(tmp_path, "ok")
    m = _load(monkeypatch, tmp_path, str(f))
    _env(monkeypatch)
    monkeypatch.setenv("CC_ASK_TOKEN", "ask-token-value")
    monkeypatch.setattr(cc_local.urllib.request, "urlopen", lambda req, timeout: _Resp())
    seen = []
    reply, sid, err = m._run_codex_turn("what is in docs?", None, on_event=lambda k, p: seen.append((k, p)), seat="local")
    assert (reply, sid, err) == ("the answer", "0199aaaa-bbbb-cccc", False)
    assert m.META["reasoner"] == "local" and m.META["model"] == "qwen-72b" and m.META["cost"] == 0
    assert seen[0][1]["reasoner"] == "local"
    call = json.loads((f.parent / "call.json").read_text())
    for flag in RESTRICTIVE:
        assert flag in call["argv"], flag
    assert KEY not in " ".join(call["argv"]) and KEY not in call["prompt"]
    assert call["env"]["CC_LOCAL_API_KEY"] == KEY
    assert "CC_ASK_TOKEN" not in call["env"] and "BRAIN_API_KEY" not in call["env"]


def test_router_keeps_a_session_per_seat_and_audits_and_meters_local(monkeypatch, tmp_path):
    f = _fake(tmp_path, "ok")
    m = _load(monkeypatch, tmp_path, str(f))
    _env(monkeypatch)
    monkeypatch.setattr(cc_local.urllib.request, "urlopen", lambda req, timeout: _Resp())
    monkeypatch.setattr(m, "_run_turn", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no fallback to Claude")))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b9"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")
    audit, spend = [], []
    monkeypatch.setattr(m, "_audit_turn", lambda rec: audit.append(rec))
    monkeypatch.setattr(m, "_spend", lambda what, provider, **kw: spend.append((provider, kw)))
    status, payload = m._turn_inner("hi", thread=None, new=True, reasoner="local")
    assert status == 200 and payload["reasoner"] == "local" and payload["error"] is False
    assert audit[-1]["reasoner"] == "local" and audit[-1]["tools"] == "local:read-only"
    assert spend[-1][0] == "self-hosted" and spend[-1][1]["usd"] == 0 and spend[-1][1]["estimate"] is False
    st = m._load_state()
    assert st["local_id"] == "0199aaaa-bbbb-cccc" and not st.get("codex_id") and st["reasoner"] == "local"
    assert "local" in m.REASONERS


def test_health_and_status_never_carry_the_key(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    _env(monkeypatch)
    assert KEY not in json.dumps(m._local_status(live=False))
    assert m._local_status(live=False)["reachable"] is None
