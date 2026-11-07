"""Tests for the Codex seat's gated write mode (2026-11-03): scripts/cc/cc_codex_gate.py and
scripts/cc/cc-codex-hook.py. The end-to-end tests run the real Codex CLI against a stub model
endpoint and a stub bridge /ask; they run when CC_TEST_CODEX_BIN names a codex 0.162.1 binary
(no sign-in needed), and skip otherwise."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

CC = Path(__file__).resolve().parent.parent / "scripts" / "cc"
sys.path.insert(0, str(CC))
import cc_codex_gate as g  # noqa: E402

HOOK = CC / "cc-codex-hook.py"


# ------------------------------------------------------------ pure ----
def test_cmd_is_gated():
    cmd = g.build_cmd("/x/codex", "/w")
    assert 'sandbox_mode="workspace-write"' in cmd and 'approval_policy="never"' in cmd
    assert "--ignore-user-config" not in cmd          # trust lives in config.toml
    assert "--ignore-rules" in cmd and cmd[-1] == "-"


@pytest.mark.parametrize("bad", [["--yolo"], ["--dangerously-bypass-hook-trust"], ["-c", "bypass_hook_trust=true"],
                                 ["-c", 'sandbox_mode="danger-full-access"'], ["--disable", "hooks"],
                                 ["-c", "features.hooks=false"], ["-c", 'approval_policy="on-request"'],
                                 ["-p", "loose"], ["--add-dir", "/"], ["--search"]])
def test_loosening_refused(bad):
    with pytest.raises(g.Unsafe):
        g.build_cmd("/x/codex", "/w", extra=bad)


def test_no_sandbox_only_when_chosen():
    assert "danger-full-access" in g.build_cmd("/x/codex", "/w", sandbox="danger-full-access")
    with pytest.raises(g.Unsafe):
        g.build_cmd("/x/codex", "/w", sandbox="read-only-ish")


def test_resume_bad_sid():
    with pytest.raises(g.Unsafe):
        g.build_cmd("/x/codex", "/w", session_id="x; rm")


def test_env_has_hook_keys_only():
    e = g.env({"HOME": "/h", "CC_ASK_TOKEN": "t", "CC_PORT": "7682", "BRAIN_API_KEY": "k", "ANTHROPIC_API_KEY": "a"})
    assert e["CC_ASK_TOKEN"] == "t" and "BRAIN_API_KEY" not in e and "ANTHROPIC_API_KEY" not in e


def test_config_header_and_trust():
    t = g.config_toml("/h/.codex", "sha256:" + "a" * 64, {"mcpServers": {"ableton-systems": {
        "command": "/usr/bin/python3", "args": ["-m", "srv"], "env": {"K": "v"}}, "bad name": {"command": "x"}}})
    assert t.startswith(g.HEADER) and g.config_ours(t)
    assert '[hooks.state."/h/.codex/hooks.json:pre_tool_use:0:0"]' in t
    assert "[mcp_servers.ableton-systems]" in t and "bad name" not in t
    assert not g.config_ours('model = "o3"\n') and g.config_ours("")
    with pytest.raises(g.Unsafe):
        g.config_toml("/h", 'x"\n[evil]', {})


def test_verdict():
    cmd = g.hook_command("/usr/bin/python3", "/s/cc-codex-hook.py")
    h = {"key": g.hook_key("/h"), "command": cmd, "handlerType": "command", "enabled": True,
         "matcher": None, "async": False, "timeoutSec": 1020, "trustStatus": "trusted"}
    assert g.verdict([h], "/h", cmd, 900)[0]
    assert not g.verdict([{**h, "trustStatus": "untrusted"}], "/h", cmd, 900)[0]
    assert not g.verdict([{**h, "matcher": "Bash"}], "/h", cmd, 900)[0]
    assert not g.verdict([{**h, "command": "true"}], "/h", cmd, 900)[0]
    assert not g.verdict([{**h, "timeoutSec": 60}], "/h", cmd, 900)[0]
    assert not g.verdict([], "/h", cmd, 900)[0]


def test_asks_mapping():
    assert g.asks({"tool_name": "Bash", "tool_input": {"command": "ls"}}) == [("Bash", {"command": "ls"})]
    p = "*** Begin Patch\n*** Add File: a.txt\n+x\n*** Update File: /abs/b.py\n@@\n*** End Patch"
    assert g.asks({"tool_name": "apply_patch", "tool_input": {"command": p}, "cwd": "/w"}) == [
        ("Write", {"file_path": "/w/a.txt"}), ("Edit", {"file_path": "/abs/b.py"})]
    assert g.asks({"tool_name": "mcp__ableton__live_do", "tool_input": {"a": 1}}) == [("mcp__ableton__live_do", {"a": 1})]


def test_hook_fails_closed_without_bridge():
    for stdin in (g.PROBE_INPUT, "not json", ""):
        r = subprocess.run([sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
                           env={"CC_PORT": "1", "PATH": os.environ.get("PATH", "")}, timeout=20)
        assert r.returncode == 0 and g.probe_ok(r.stdout), (stdin, r.stdout)


# ------------------------------------------------------------ end to end ----
BIN = os.environ.get("CC_TEST_CODEX_BIN", "")
e2e = pytest.mark.skipif(not (BIN and Path(BIN).exists()), reason="CC_TEST_CODEX_BIN not set")


def _serve(handler):
    s = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class _Model(BaseHTTPRequestHandler):
    """A Responses endpoint: first a shell call that writes written.txt, then a final message."""
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        outs = [i for i in body.get("input", []) if isinstance(i, dict) and i.get("type") == "function_call_output"]
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        if outs:
            item = {"type": "message", "role": "assistant", "id": "m1",
                    "content": [{"type": "output_text", "text": "tool said: " + str(outs[-1].get("output"))[:400]}]}
        else:
            item = {"type": "function_call", "name": "exec_command", "call_id": "c1",
                    "arguments": json.dumps({"cmd": "echo stub > written.txt"})}
        for ev in ({"type": "response.created", "response": {"id": "r"}},
                   {"type": "response.output_item.done", "item": item},
                   {"type": "response.completed", "response": {"id": "r", "usage": {
                       "input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}}):
            self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode())


def _bridge(decision, calls, token):
    class B(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.headers.get("X-CC-Ask") != token:
                out, code = {"behavior": "deny", "message": "not the hook"}, 403
            else:
                calls.append(req)
                out, code = ({"behavior": "allow"} if decision == "allow" else
                             {"behavior": "deny", "message": "the person refused this action"}), 200
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(out).encode())
    return B


def _seat(tmp_path, trusted=True):
    home, ws = tmp_path / "codex-home", tmp_path / "ws"
    home.mkdir(); ws.mkdir()
    ttl = 30
    (home / "hooks.json").write_text(g.hooks_json(sys.executable, HOOK, ttl))
    envb = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", ""), "CODEX_HOME": str(home)}
    run = lambda argv: g._spawn(argv, envb)
    cmdline = g.hook_command(sys.executable, HOOK)
    h = g.ours(g.hooks_list(BIN, str(ws), run), home, cmdline)
    assert h is not None and h["trustStatus"] == "untrusted"
    (home / "config.toml").write_text(g.config_toml(home, h["currentHash"] if trusted else None))
    ok, why = g.verdict(g.hooks_list(BIN, str(ws), run), home, cmdline, ttl)
    return home, ws, envb, ok, why


def _turn(home, ws, envb, decision, sandbox="danger-full-access"):
    calls, token = [], "tok-" + os.urandom(4).hex()
    m, b = _serve(_Model), _serve(_bridge(decision, calls, token))
    extra = ["-c", 'model_provider="stub"', "-c", 'model_providers.stub.name="stub"',
             "-c", f'model_providers.stub.base_url="http://127.0.0.1:{m.server_port}/v1"',
             "-c", 'model_providers.stub.wire_api="responses"', "-c", 'model_providers.stub.env_key="STUB_KEY"']
    cmd = g.build_cmd(BIN, str(ws), model="stub-model", sandbox=sandbox, extra=extra)
    env = {**g.env({**envb, "CC_PORT": str(b.server_port), "CC_BASE": "/cc", "CC_ASK_TOKEN": token,
                    "CC_PERMIT_TTL": "30"}), "STUB_KEY": "x"}
    p = subprocess.run(cmd, input="write the file", capture_output=True, text=True, timeout=90, env=env, cwd=ws)
    m.shutdown(); b.shutdown()
    return p, calls


@e2e
def test_e2e_deny_refuses_write(tmp_path):
    home, ws, envb, ok, why = _seat(tmp_path)
    assert ok, why
    p, calls = _turn(home, ws, envb, "deny")
    assert not (ws / "written.txt").exists(), p.stdout[-800:]
    assert [c["tool_name"] for c in calls] == ["Bash"] and calls[0]["tool_input"]["command"] == "echo stub > written.txt"
    assert calls[0]["seat"] == "codex" and "blocked by PreToolUse hook" in p.stdout


@e2e
def test_e2e_allow_passes(tmp_path):
    home, ws, envb, ok, why = _seat(tmp_path)
    assert ok, why
    p, calls = _turn(home, ws, envb, "allow")
    assert (ws / "written.txt").read_text().strip() == "stub", p.stdout[-800:]
    assert len(calls) == 1


@e2e
def test_e2e_untrusted_hook_is_skipped_so_the_check_refuses(tmp_path):
    # Why the gate check exists: without the trust entry Codex skips the hook and the write runs.
    home, ws, envb, ok, why = _seat(tmp_path, trusted=False)
    assert not ok and "untrusted" in why
    p, calls = _turn(home, ws, envb, "deny")
    assert calls == [] and (ws / "written.txt").exists()


@e2e
def test_e2e_workspace_write_reaches_the_gate(tmp_path):
    # In the default sandbox the gate decides first; a deny never reaches the sandbox.
    home, ws, envb, ok, why = _seat(tmp_path)
    p, calls = _turn(home, ws, envb, "deny", sandbox="workspace-write")
    assert len(calls) == 1 and not (ws / "written.txt").exists()


# ------------------------------------------------------------ the bridge ----
def _tc():
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_cc_codex_helpers", Path(__file__).parent / "test_cc_codex.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bridge_write_mode_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_CODEX_WRITE", raising=False)
    m = _tc()._load(monkeypatch, tmp_path)
    assert not m.CODEX_WRITE and m._seat_read_only("codex") and m._seat_read_only("local")
    assert m._codex_gate_check() == (False, "off (CC_CODEX_WRITE is not 1)")


def test_bridge_refuses_write_mode_without_the_box_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_CODEX_WRITE", "1")
    monkeypatch.delenv("CC_BOX", raising=False)
    t = _tc()
    m = t._load(monkeypatch, tmp_path, str(t._fake(tmp_path, "ok")))
    ok, why = m._codex_gate_check()
    assert not ok and "box lane" in why and m._seat_read_only("codex")


def test_bridge_refuses_an_owner_config(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_CODEX_WRITE", "1")
    t = _tc()
    m = t._load(monkeypatch, tmp_path, str(t._fake(tmp_path, "ok")))
    monkeypatch.setattr(m, "BOX_ENABLED", True)
    monkeypatch.setattr(m, "GATE", object())
    monkeypatch.setattr(m, "CODEX_HOME_HANDS", tmp_path / "ch")
    (tmp_path / "ch").mkdir()
    (tmp_path / "ch" / "config.toml").write_text('model = "o3"\n')
    ok, why = m._codex_gate_check()
    assert not ok and "owner's own" in why


def test_bridge_auto_posture_keeps_sudo_on_a_card(monkeypatch, tmp_path):
    m = _tc()._load(monkeypatch, tmp_path)
    monkeypatch.setitem(m.CODEX_GATE, "ok", True)
    monkeypatch.setenv("CC_POSTURE", "auto")
    assert m._codex_auto_allows("Bash", {"command": "ls -la"})
    assert m._codex_auto_allows("Edit", {"file_path": "/w/a"})
    for c in ("sudo ls", "echo x && sudo rm -rf /", "x | sudo tee /etc/f", "(sudo id)"):
        assert not m._codex_auto_allows("Bash", {"command": c}), c
    assert not m._codex_auto_allows("orfeo_post", {})
    monkeypatch.setenv("CC_POSTURE", "cards")
    assert not m._codex_auto_allows("Bash", {"command": "ls"})
    monkeypatch.setenv("CC_POSTURE", "auto")
    monkeypatch.setitem(m.CODEX_GATE, "ok", False)
    assert not m._codex_auto_allows("Bash", {"command": "ls"})


def test_bridge_gated_turn_runs_workspace_write_with_the_hook_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_CODEX_WRITE", "1")
    t = _tc()
    f = t._fake(tmp_path, "ok")
    m = t._load(monkeypatch, tmp_path, str(f))
    def passed():
        m.CODEX_GATE.update({"ok": True, "why": "trusted"})
        return dict(m.CODEX_GATE)
    monkeypatch.setattr(m, "_codex_gate_refresh", passed)
    reply, sid, err = m._run_codex_turn("make the file", None)
    assert not err and reply == "the answer"
    call = json.loads((f.parent / "call.json").read_text())
    argv = call["argv"]
    assert argv[argv.index("-s") + 1] == "workspace-write" and "--ignore-user-config" not in argv
    assert call["env"].get("CC_ASK_TOKEN") == m.ASK_TOKEN and "BRAIN_API_KEY" not in call["env"]
    assert "raises a card" in call["prompt"] and not m._seat_read_only("codex")
    assert m._codex_status(fresh=True)["label"] == "Codex (gated)"


def test_bridge_refused_check_runs_read_only_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_CODEX_WRITE", "1")
    t = _tc()
    f = t._fake(tmp_path, "ok")
    m = t._load(monkeypatch, tmp_path, str(f))
    reply, sid, err = m._run_codex_turn("make the file", None)
    argv = json.loads((f.parent / "call.json").read_text())["argv"]
    assert argv[argv.index("-s") + 1] == "read-only" and "write mode refused" in reply and "box lane" in reply


def test_bridge_gated_seat_queues_proposals(monkeypatch, tmp_path):
    m = _tc()._load(monkeypatch, tmp_path)
    monkeypatch.setitem(m.CODEX_GATE, "ok", True)
    prop = '<proposal>{"platform": "box", "action_id": "x", "summary": "write a file"}</proposal>'
    monkeypatch.setattr(m, "_run_codex_turn", lambda msg, sid, **kw: ("I will do this. " + prop, "x-2", False))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b3"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")
    status, payload = m._turn_inner("do it", thread=None, new=True, reasoner="codex")
    assert "raises no cards" not in payload["reply"] and payload["proposal"] is not None


class _AutoGate:
    def __init__(self):
        self.calls = []

    def call(self, tool, args, permit_id=None):
        self.calls.append((tool, dict(args)))
        return type("R", (), {"permit": {"id": "pa1", "ttl_seconds": 900}, "error": None, "reason": None})()

    def get(self, pid):
        return None

    def deny(self, pid):
        self.calls.append(("deny", pid))


def test_bridge_auto_allowed_codex_call_leaves_a_permit_and_a_decision(monkeypatch, tmp_path):
    # hbar 2026-11-07: in the auto posture a Codex call ran with no trace in the permit history
    m = _tc()._load(monkeypatch, tmp_path)
    gate = _AutoGate()
    monkeypatch.setattr(m, "BOX_ENABLED", True)
    monkeypatch.setattr(m, "GATE", gate)
    monkeypatch.setattr(m, "_auto_has", lambda a: False)
    ran, logged = [], []
    monkeypatch.setattr(m, "_run_permit", lambda pid, pm: ran.append(pid) or {"ok": True, "status": "executed"})
    monkeypatch.setattr(m, "_decision_log", lambda *a, **k: logged.append(a))
    r = m._box_ask("Bash", {"command": "printf ok > /tmp/x"}, session_id="s1", auto_why="the auto posture, Codex seat")
    assert r == {"behavior": "allow"}
    assert gate.calls and gate.calls[0][0] == "box_act" and gate.calls[0][1]["platform"] == "box"
    assert ran == ["pa1"]
    assert logged and logged[0][:3] == ("pa1", "allow", "auto posture")


def test_bridge_codex_call_without_auto_still_waits_for_a_card(monkeypatch, tmp_path):
    m = _tc()._load(monkeypatch, tmp_path)
    gate = _AutoGate()
    monkeypatch.setattr(m, "BOX_ENABLED", True)
    monkeypatch.setattr(m, "GATE", gate)
    monkeypatch.setattr(m, "_auto_has", lambda a: False)
    monkeypatch.setattr(m, "_run_permit", lambda pid, pm: (_ for _ in ()).throw(AssertionError("must not run")))
    r = m._box_ask("Bash", {"command": "printf ok > /tmp/x"})
    assert r["behavior"] == "deny" and ("deny", "pa1") in gate.calls   # nobody watching: refused, never run


def test_bridge_temporary_page_key_gets_a_clear_reply(monkeypatch, tmp_path):
    # hbar 2026-11-07: an orphan "new:<ms>" key from the page came back "not on this box any more"
    m = _tc()._load(monkeypatch, tmp_path)
    st, d = m._turn_inner("hello", thread="new:1762512000000", new=False)
    assert st == 404 and "never saved" in d["reply"]
    st, d = m._turn_inner("hello", thread="0000-not-a-thread", new=False)
    assert st == 404 and "not on this box" in d["reply"]
