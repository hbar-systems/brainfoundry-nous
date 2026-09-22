"""Hands on the box (scripts/cc/cc-bridge.py, CC_BOX=1): the reasoner's own tool calls,
gated by a card. No reasoner, no network; permitd from the venv.

Run from repo root:
    pytest tests/test_cc_box.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import threading
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytest.importorskip("permitd")


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_BOX", "1")
    monkeypatch.setenv("CC_PERMIT_TTL", "5")
    monkeypatch.delenv("ONE_SECRET", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_box", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_box"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_box_key_and_remember_rules(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    assert m._box_key("Bash", {"command": "git status"}) == ("git", "run on the box: git status", True)
    aid, _, ok = m._box_key("Bash", {"command": "sudo systemctl restart cc-bridge"})
    assert aid == "sudo systemctl" and ok is False          # sudo is never remembered
    assert m._box_key("Bash", {"command": "rm -rf /tmp/x"})[2] is False
    assert m._box_key("Bash", {"command": "echo hi | bash"})[2] is False
    aid, summary, ok = m._box_key("Edit", {"file_path": "/home/cc/notes/a.md"})
    assert aid == "edit /home/cc/notes" and "a.md" in summary and ok is True
    assert m._box_key("WebFetch", {"url": "x"})[2] is False


def test_box_gate_registered_without_one(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    assert m.GATE is not None and m.BOX_ENABLED is True and m.ONE_ENABLED is False
    assert "hands on it" in m.SYSTEM and "brain-write" in m.SYSTEM
    s = json.loads(m._hook_settings())
    hook = s["hooks"]["PermissionRequest"][0]["hooks"][0]
    assert hook["type"] == "command" and hook["command"].endswith("cc-permit-hook.py") and hook["timeout"] > 5


def test_box_ask_denied_when_nobody_watches(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    m.LIVE["emit"] = None
    d = m._box_ask("Bash", {"command": "touch /tmp/a"})
    assert d["behavior"] == "deny" and "watching" in d["message"]


def test_box_ask_allowed_by_click_and_remembered(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    cards = []
    m.LIVE["emit"] = lambda kind, payload: cards.append((kind, payload))
    out = {}

    def ask():
        out["d"] = m._box_ask("Bash", {"command": "git status"})
    th = threading.Thread(target=ask)
    th.start()
    for _ in range(50):
        if cards:
            break
        time.sleep(0.05)
    assert cards and cards[0][0] == "ask"
    card = cards[0][1]
    assert card["platform"] == "box" and card["method"] == "Bash" and card["remember_ok"] is True
    pm = m.GATE.get(card["id"])
    outcome = m._run_permit(card["id"], pm)
    assert outcome["ok"] is True
    m._box_settle(card["id"], "allow")
    m._auto_add(pm.args, title="git")
    th.join(3)
    assert out["d"] == {"behavior": "allow"}
    # second time: no card to click, allowed from the owner's earlier choice, still a permit
    cards.clear()
    d2 = m._box_ask("Bash", {"command": "git log -1"})
    assert d2 == {"behavior": "allow"}
    assert cards and cards[0][1].get("auto") is True


def test_box_ask_refused(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    cards = []
    m.LIVE["emit"] = lambda kind, payload: cards.append(payload)
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("d", m._box_ask("Write", {"file_path": "/home/cc/notes/x.txt"})))
    th.start()
    for _ in range(50):
        if cards:
            break
        time.sleep(0.05)
    m.GATE.deny(cards[0]["id"])
    m._box_settle(cards[0]["id"], "deny", "the person refused this action")
    th.join(3)
    assert out["d"]["behavior"] == "deny" and "refused" in out["d"]["message"]


def test_hook_script_denies_without_bridge(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "CC_PORT": "1", "CC_PERMIT_TTL": "1"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "cc" / "cc-permit-hook.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                       capture_output=True, text=True, env=env, timeout=30)
    out = json.loads(r.stdout)
    dec = out["hookSpecificOutput"]["decision"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
    assert dec["behavior"] == "deny" and "bridge" in dec["message"]


def test_posture_auto_adds_ask_rules_and_mode(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    assert m._posture_current() == "cards"
    assert "permissions" not in json.loads(m._hook_settings())
    monkeypatch.setenv("CC_POSTURE", "auto")
    s = json.loads(m._hook_settings())
    assert s["permissions"]["ask"] == list(m.ASK_ALWAYS)
    assert s["hooks"]["PermissionRequest"]           # the card hook stays
    monkeypatch.setenv("CC_POSTURE", "nonsense")
    assert m._posture_current() == "cards"


def test_judged_posture_runs_or_asks(monkeypatch, tmp_path):
    import io, urllib.request
    monkeypatch.setenv("TYPESAFE_API_KEY", "t")
    monkeypatch.setenv("CC_POSTURE", "judged")
    m = _load(monkeypatch, tmp_path)
    assert m._posture_current() == "judged"
    answers = {"safe": 0.97, "intent": 0.95, "risk": 0.2}

    class R:
        def __init__(self, body): self.body = body
        def read(self): return json.dumps(self.body).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    seen = {}
    def fake_open(req, timeout=0):
        seen["body"] = json.loads(req.data)
        seen["auth"] = req.headers.get("Authorization")
        return R({"answers": {"safe": {"noul": answers["safe"]}, "intent": {"noul": answers["intent"]},
                              "risk": {"score": answers["risk"]}}, "usage": {"input_tokens": 300}})
    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    m.LAST_MESSAGE["text"] = "run the tests"
    cards = []
    m.LIVE["emit"] = lambda k, p: cards.append(p)
    d = m._box_ask("Bash", {"command": "pytest -q"})
    assert d == {"behavior": "allow"} and cards[-1]["auto"] is True and "judged safe 0.97" in cards[-1]["why"]
    assert seen["auth"] == "Bearer t" and seen["body"]["state"]["person_request"] == "run the tests"
    assert set(seen["body"]["questions"]) == {"safe", "intent", "risk"}
    # below the threshold: a card is shown, with the numbers on it, and the ask waits
    answers.update({"safe": 0.4, "risk": 2.5})
    cards.clear()
    th = threading.Thread(target=lambda: m._box_ask("Bash", {"command": "rm -rf build"}))
    th.start()
    for _ in range(50):
        if cards:
            break
        time.sleep(0.05)
    assert cards and not cards[0].get("auto") and cards[0]["judge"]["ok"] is False
    m.GATE.deny(cards[0]["id"]); m._box_settle(cards[0]["id"], "deny"); th.join(3)
    # sudo is never judged
    cards.clear()
    th = threading.Thread(target=lambda: m._box_ask("Bash", {"command": "sudo systemctl restart cc-bridge"}))
    th.start()
    for _ in range(50):
        if cards:
            break
        time.sleep(0.05)
    assert cards and "judge" not in cards[0]
    m.GATE.deny(cards[0]["id"]); m._box_settle(cards[0]["id"], "deny"); th.join(3)
    # judge unreachable: ask
    def broken(req, timeout=0): raise OSError("down")
    monkeypatch.setattr(urllib.request, "urlopen", broken)
    assert m._judge("Bash", {"command": "ls"}, "run on the box: ls") is None
