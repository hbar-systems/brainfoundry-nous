"""The Codex seat (scripts/cc/cc_codex.py and its use in cc-bridge.py), 2026-10-15.

No network, no real codex: a fake binary answers `login status` and `exec --json`.
Run from repo root:
    pytest tests/test_cc_codex.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_codex  # noqa: E402

SECRET = "sk-proj-THISMUSTNEVERSHOW1234"

FAKE = '''#!/usr/bin/env python3
import json, os, sys
# the seat runs Codex with a scrubbed environment, so the fake reads its script from files beside it
here = os.path.dirname(os.path.abspath(__file__))
mode = open(os.path.join(here, "mode")).read().strip() if os.path.exists(os.path.join(here, "mode")) else "ok"
if sys.argv[1:3] == ["login", "status"]:
    if mode == "signedout":
        print("Not logged in"); sys.exit(1)
    if mode == "apikey":
        print("Logged in using an API key - %s"); sys.exit(0)
    print("Logged in using ChatGPT"); sys.exit(0)
if sys.argv[1] == "exec":
    prompt = sys.stdin.read()
    open(os.path.join(here, "call.json"), "w").write(json.dumps({"argv": sys.argv, "prompt": prompt, "env": dict(os.environ)}))
    def p(o): print(json.dumps(o), flush=True)
    if mode == "authfail":
        p({"type": "thread.started", "thread_id": "0199aaaa-bbbb-cccc"})
        p({"type": "turn.failed", "error": {"message": "unexpected status 401 Unauthorized"}})
        sys.exit(1)
    p({"type": "thread.started", "thread_id": "0199aaaa-bbbb-cccc"})
    p({"type": "turn.started"})
    p({"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "bash -lc 'ls docs'", "status": "in_progress"}})
    p({"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "bash -lc 'ls docs'", "exit_code": 0}})
    p({"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": "first look"}})
    p({"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": "the answer"}})
    p({"type": "turn.completed", "usage": {"input_tokens": 11, "cached_input_tokens": 5, "output_tokens": 7}})
''' % SECRET


def _fake(tmp_path, mode: str = "ok") -> pathlib.Path:
    f = tmp_path / "hands" / ".local" / "bin" / "codex"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(FAKE)
    f.chmod(0o755)
    _mode(f, mode)
    return f


def _mode(f: pathlib.Path, mode: str) -> None:
    (f.parent / "mode").write_text(mode)


def _load(monkeypatch, tmp_path, codex_bin: str | None = None):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    monkeypatch.delenv("CC_HANDS_USER", raising=False)
    monkeypatch.setenv("CC_CODEX_BIN", codex_bin or str(tmp_path / "nowhere" / "codex"))
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------ the command line ----
RESTRICTIVE = ['sandbox_mode="read-only"', 'approval_policy="never"', 'web_search="disabled"',
               "--ignore-user-config", "--ignore-rules", "--json"]


def test_fresh_and_resumed_commands_are_always_read_only():
    fresh = cc_codex.build_cmd("/x/codex", "/home/hands/world")
    assert fresh[:2] == ["/x/codex", "exec"] and fresh[-1] == "-"
    assert fresh[fresh.index("-s") + 1] == "read-only" and fresh[fresh.index("-C") + 1] == "/home/hands/world"
    resumed = cc_codex.build_cmd("/x/codex", "/w", session_id="0199aaaa-bbbb-cccc", model="gpt-5-codex")
    assert resumed[:3] == ["/x/codex", "exec", "resume"] and resumed[-2:] == ["0199aaaa-bbbb-cccc", "-"]
    assert resumed[resumed.index("-m") + 1] == "gpt-5-codex"
    for cmd in (fresh, resumed):
        for flag in RESTRICTIVE:
            assert flag in cmd, flag
        joined = " ".join(cmd)
        for bad in ("workspace-write", "danger-full-access", "--yolo", "--full-auto", "--search", "bypass"):
            assert bad not in joined


@pytest.mark.parametrize("extra", [
    ["--dangerously-bypass-approvals-and-sandbox"], ["--full-auto"], ["--approve-for-me"], ["--search"],
    ["--dangerously-bypass-hook-trust"], ["--add-dir", "/"], ["-c", 'sandbox_mode="workspace-write"'],
    ["-c", 'approval_policy="on-request"'], ["-c", 'sandbox_mode="danger-full-access"'],
])
def test_anything_that_loosens_the_seat_is_refused(extra):
    cmd = cc_codex.build_cmd("/x/codex", "/w")
    with pytest.raises(cc_codex.Unsafe):
        cc_codex.assert_restrictive(cmd[:-1] + extra + ["-"])


def test_missing_restrictive_flag_is_refused():
    cmd = cc_codex.build_cmd("/x/codex", "/w")
    i = cmd.index('approval_policy="never"')
    with pytest.raises(cc_codex.Unsafe):
        cc_codex.assert_restrictive(cmd[:i - 1] + cmd[i + 1:])
    with pytest.raises(cc_codex.Unsafe):
        cc_codex.assert_restrictive([c for c in cmd if c != "--ignore-user-config"])


def test_session_id_and_model_cannot_smuggle_flags():
    with pytest.raises(cc_codex.Unsafe):
        cc_codex.build_cmd("/x/codex", "/w", session_id="--yolo")
    with pytest.raises(cc_codex.Unsafe):
        cc_codex.build_cmd("/x/codex", "/w", model="--full-auto")


def test_codex_env_carries_no_bridge_keys():
    base = {"HOME": "/home/hands", "PATH": "/usr/bin", "CC_ASK_TOKEN": "t", "BRAIN_API_KEY": "k",
            "ONE_SECRET": "s", "ANTHROPIC_API_KEY": "a", "CC_RUN_ID": "r"}
    env = cc_codex.env(base)
    assert env["HOME"] == "/home/hands" and env["PATH"] == "/usr/bin"
    assert not {"CC_ASK_TOKEN", "BRAIN_API_KEY", "ONE_SECRET", "ANTHROPIC_API_KEY"} & set(env)


# ------------------------------------------------------------------ status ----
def test_status_binary_missing(tmp_path):
    st = cc_codex.status(str(tmp_path / "no-codex"))
    assert st["installed"] is False and st["signedIn"] is False and st["label"] == "Codex (read-only)"
    assert "installed" in cc_codex.refusal(st) and "nothing fell back" in cc_codex.refusal(st)


def test_status_never_carries_the_clis_words(tmp_path, monkeypatch):
    f = _fake(tmp_path, "apikey")
    st = cc_codex.status(str(f))
    assert st["signedIn"] is True and st["method"] == "api-key"
    assert SECRET not in json.dumps(st) and "sk-" not in json.dumps(st)
    _mode(f, "ok")
    st = cc_codex.status(str(f))
    assert st["signedIn"] is True and st["method"] == "chatgpt" and cc_codex.refusal(st) is None
    _mode(f, "signedout")
    st = cc_codex.status(str(f))
    assert st["installed"] is True and st["signedIn"] is False and "not signed in" in cc_codex.refusal(st)


def test_bridge_health_status_has_no_token(monkeypatch, tmp_path):
    f = _fake(tmp_path, "apikey")
    m = _load(monkeypatch, tmp_path, str(f))
    st = m._codex_status(fresh=True)
    assert st["signedIn"] is True and SECRET not in json.dumps(st)


# ------------------------------------------------------------------ routing ----
def test_pick_and_turn_routing(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    assert m._reasoner_pick(None, None, {}) == "claude"
    assert m._reasoner_pick("codex", {"reasoner": "claude"}, {}) == "codex"
    assert m._reasoner_pick(None, {"reasoner": "codex"}, {"reasoner": "claude"}) == "codex"
    assert m._reasoner_pick(None, None, {"reasoner": "codex"}) == "codex"
    assert m._reasoner_pick("gpt", None, {}) == "claude"

    calls = []
    monkeypatch.setattr(m, "_run_turn", lambda msg, sid, **kw: (calls.append(("claude", sid)) or ("from claude", "c-1", False)))
    monkeypatch.setattr(m, "_run_codex_turn", lambda msg, sid, **kw: (calls.append(("codex", sid)) or ("from codex", "x-1", False)))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b1"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")

    status, payload = m._turn_inner("hello", thread=None, new=True, reasoner="codex")
    assert status == 200 and payload["reasoner"] == "codex" and calls == [("codex", None)]
    th = next(x for x in m._threads_load() if x["brain"] == "b1")
    assert th["reasoner"] == "codex" and th["codex"] == "x-1"

    # the thread keeps its seat and its Codex session without being asked again
    status, payload = m._turn_inner("again", thread="b1", new=False)
    assert calls[-1] == ("codex", "x-1") and payload["reasoner"] == "codex"

    # switching the seat on a turn: Claude starts its own session in the same thread
    status, payload = m._turn_inner("now claude", thread="b1", new=False, reasoner="claude")
    assert calls[-1] == ("claude", None) and payload["reasoner"] == "claude"
    th = next(x for x in m._threads_load() if x["brain"] == "b1")
    assert th["reasoner"] == "claude" and th["claude"] == "c-1" and th["codex"] == "x-1"

    # the default for a new thread is Claude
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b2"} if path == "/sessions" else {})
    status, payload = m._turn_inner("plain", thread=None, new=True)
    assert calls[-1] == ("claude", None) and payload["reasoner"] == "claude"


# ------------------------------------------------------------- fail closed ----
def _no_popen(*a, **kw):
    raise AssertionError("nothing may run")


def test_missing_binary_refuses_and_runs_nothing(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(m.subprocess, "Popen", _no_popen)
    monkeypatch.setattr(m, "_run_turn", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no fallback to Claude")))
    reply, sid, err = m._run_codex_turn("hi", None, on_event=lambda k, p: None)
    assert err is True and sid is None and "not installed" in reply and "nothing fell back" in reply


def test_signed_out_refuses_and_runs_nothing(monkeypatch, tmp_path):
    f = _fake(tmp_path, "signedout")
    m = _load(monkeypatch, tmp_path, str(f))
    monkeypatch.setattr(m.subprocess, "Popen", _no_popen)
    reply, sid, err = m._run_codex_turn("hi", "0199aaaa-bbbb-cccc", on_event=lambda k, p: None)
    assert err is True and sid == "0199aaaa-bbbb-cccc" and "not signed in" in reply


def test_signed_out_turn_through_the_router_does_not_fall_back(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(m, "_run_turn", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no fallback to Claude")))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b9"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")
    status, payload = m._turn_inner("hi", thread=None, new=True, reasoner="codex")
    assert status == 200 and payload["error"] is True and payload["reasoner"] == "codex"
    assert "not installed" in payload["reply"]


def test_auth_failure_mid_turn_says_sign_in(monkeypatch, tmp_path):
    f = _fake(tmp_path, "authfail")
    m = _load(monkeypatch, tmp_path, str(f))
    monkeypatch.setattr(m, "_codex_status", lambda fresh=False: {"installed": True, "signedIn": True})
    reply, sid, err = m._run_codex_turn("hi", None, on_event=lambda k, p: None)
    assert err is True and "Sign in with ChatGPT" in reply


# --------------------------------------------------------------- streaming ----
def test_codex_turn_streams_like_the_claude_seat(monkeypatch, tmp_path):
    f = _fake(tmp_path, "ok")
    m = _load(monkeypatch, tmp_path, str(f))
    monkeypatch.setenv("CC_ASK_TOKEN", "ask-token-value")
    seen = []
    reply, sid, err = m._run_codex_turn("what is in docs?", None, on_event=lambda k, p: seen.append((k, p)))
    assert (reply, sid, err) == ("the answer", "0199aaaa-bbbb-cccc", False)
    kinds = [k for k, _ in seen]
    assert kinds == ["start", "tool", "block", "text", "block", "text"]
    assert seen[1][1] == {"name": "shell", "brief": "run: bash -lc 'ls docs'"}
    assert m.META["reasoner"] == "codex" and m.META["in"] == 11 and m.META["cached"] == 5 and m.META["out"] == 7
    call = json.loads((f.parent / "call.json").read_text())
    argv = call["argv"]
    # the restrictive flags are on the real command line, and the prompt is not
    for flag in RESTRICTIVE:
        assert flag in argv, flag
    assert argv[argv.index("-s") + 1] == "read-only" and argv[-1] == "-"
    assert "what is in docs?" not in " ".join(argv) and "what is in docs?" in call["prompt"]
    assert "read-only sandbox" in call["prompt"]
    # the commands Codex runs see none of the bridge's keys
    assert "CC_ASK_TOKEN" not in call["env"] and "BRAIN_API_KEY" not in call["env"]


def test_codex_proposal_raises_no_card(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    prop = '<proposal>{"platform": "box", "action_id": "x", "summary": "write a file"}</proposal>'
    monkeypatch.setattr(m, "_run_codex_turn", lambda msg, sid, **kw: ("I would do this. " + prop, "x-2", False))
    monkeypatch.setattr(m, "_propose", lambda p: (_ for _ in ()).throw(AssertionError("no card from the read-only seat")))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b3"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")
    status, payload = m._turn_inner("do it", thread=None, new=True, reasoner="codex")
    assert payload["proposal"] is None and "raises no cards" in payload["reply"]


# ---------------------------------------------------------------- the page ----
def test_page_has_the_chatgpt_door_and_sends_the_seat():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "Sign in with ChatGPT" in src and "'/claude/?arg=codex-login'" in src
    assert "Sign in with a Claude subscription" in src          # the Claude door stays beside it
    assert "reasoner: seatRef.current" in src and "'/cc/codex/status?fresh=1'" in src
    assert "Codex (read-only)" in src
    # the seat is no dropdown; the one <select> is the pane page switcher (78c3284)
    assert src.count("<select") == 1 and "<select value={pane.route}" in src


def test_door_runs_the_device_code_login_as_the_hands():
    src = (ROOT / "scripts" / "cc" / "install.sh").read_text()
    assert "codex-login)" in src and "codex login --device-auth" in src
    inst = (ROOT / "scripts" / "cc" / "install-codex.sh").read_text()
    assert "CODEX_VERSION=${CODEX_VERSION:-" + cc_codex.PINNED_VERSION + "}" in inst   # one pin, in step with the bridge
    assert '"@openai/codex@$CODEX_VERSION"' in inst and "--prefix" in inst and "codex login --device-auth" in inst


# ------------------------------------------------- SEAT-1: the signed-in seat (2026-11-08) ----
def _signed(m, monkeypatch, claude=False, codex=False, installed=True, local=False):
    monkeypatch.setattr(m, "_auth_status", lambda fresh=False: {"loggedIn": claude, "email": None, "method": None})
    monkeypatch.setattr(m, "_codex_status", lambda fresh=False: {"installed": installed, "signedIn": codex})
    monkeypatch.setattr(m, "_local_status", lambda live=True: {"configured": local})


def test_default_seat_is_the_signed_in_reasoner(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    _signed(m, monkeypatch, claude=True, codex=True)
    assert m._default_seat() == "claude"
    _signed(m, monkeypatch, codex=True)
    assert m._default_seat() == "codex"
    _signed(m, monkeypatch, codex=True, installed=False)   # a sign-in without the binary answers nothing
    assert m._default_seat() == "claude"
    _signed(m, monkeypatch, local=True)
    assert m._default_seat() == "local"
    _signed(m, monkeypatch)
    assert m._default_seat() == "claude"
    # the default only fills a gap: the turn's own seat and the thread's seat still win
    _signed(m, monkeypatch, codex=True)
    assert m._reasoner_pick(None, None, {}, default=m._default_seat) == "codex"
    assert m._reasoner_pick("claude", None, {}, default=m._default_seat) == "claude"
    assert m._reasoner_pick(None, {"reasoner": "claude"}, {}, default=m._default_seat) == "claude"


def test_a_turn_naming_no_seat_goes_to_codex_on_a_chatgpt_only_brain(monkeypatch, tmp_path):
    """Telegram, the queue and any door that sends no seat: a brain signed in only with ChatGPT
    answered on Claude and refused (hbar 2026-11-07 for Alexander's brain)."""
    m = _load(monkeypatch, tmp_path)
    _signed(m, monkeypatch, codex=True)
    calls = []
    monkeypatch.setattr(m, "_run_turn", lambda msg, sid, **kw: (calls.append("claude") or ("from claude", "c-1", False)))
    monkeypatch.setattr(m, "_run_codex_turn", lambda msg, sid, **kw: (calls.append("codex") or ("from codex", "x-1", False)))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "b9"} if path == "/sessions" else {})
    monkeypatch.setattr(m, "_recent", lambda msg, fresh: "")
    status, payload = m._turn_inner("hello", thread=None, new=True, reasoner=None)
    assert status == 200 and calls == ["codex"] and payload["reasoner"] == "codex"


def test_health_fresh_rereads_both_sign_ins():
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    health = src.split('if route == "/health":', 1)[1].split("elif route ==", 1)[0]
    assert '_fresh = self._query().get("fresh") == "1"' in health
    assert '"auth": _auth_status(fresh=_fresh)' in health and '"codex": _codex_status(fresh=_fresh)' in health


def test_sign_in_card_rechecks_and_never_offers_a_second_chatgpt_login():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "fetch(fresh === true ? '/cc/health?fresh=1' : '/cc/health'" in src
    assert "onClose={() => { setPane(null); loadHealth(true) }}" in src          # a closed sign-in panel looks again
    card = src.split("function SignIn(", 1)[1].split("\nfunction ", 1)[0]
    assert "onRecheck" in card and ">recheck</Btn>" in card
    assert "{codexCanSignIn(health && health.codex) && (" in card
    assert "press reconnect" not in card and "press recheck after signing in" not in card   # no button by that name
    assert "const codexCanSignIn = (cx) => !!(cx && cx.installed && !cx.signedIn)" in src


# ---- the door's codex-login and login cases, run for real against fake CLIs ----
FAKE_CODEX_LOGIN = '''#!/usr/bin/env bash
here="$(dirname "$0")"
if [ "$1 $2" = "login status" ]; then [ -f "$here/signed" ]; exit $?; fi
if [ "$1 $2" = "login --device-auth" ]; then echo login >> "$here/calls"; [ "$(cat "$here/next" 2>/dev/null)" = ok ] && touch "$here/signed"; exit 0; fi
exit 2
'''
FAKE_CLAUDE_LOGIN = '''#!/usr/bin/env bash
here="$(dirname "$0")"
if [ "$1 $2" = "auth login" ]; then [ "$(cat "$here/next" 2>/dev/null)" = ok ] && touch "$here/csigned"; exit 0; fi
if [ "$1 $2" = "auth status" ]; then if [ -f "$here/csigned" ]; then echo '{"loggedIn": true}'; else echo '{"loggedIn": false}'; fi; exit 0; fi
exit 2
'''


def _door(tmp_path):
    import getpass
    import subprocess
    src = (ROOT / "scripts" / "cc" / "install.sh").read_text()
    body = src.split("<<'DOOR'\n", 1)[1].split("\nDOOR\n", 1)[0]
    home = tmp_path / "hands"
    body = body.replace("/home/__LOGIN_USER__", str(home)).replace("__LOGIN_USER__", getpass.getuser())
    body = body.replace("__CODEX_INSTALL__", "bash scripts/cc/install-codex.sh elena")
    door = tmp_path / "door.sh"
    door.write_text(body)
    bin_ = home / ".local" / "bin"
    bin_.mkdir(parents=True)
    for name, text in (("clear", "#!/bin/sh\n"), ("sleep", "#!/bin/sh\n")):   # no 3600 s wait in a test
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)

    def run(arg):
        r = subprocess.run(["bash", str(door), arg], capture_output=True, text=True, timeout=30,
                           env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
        return r.stdout
    return bin_, run


def _fake_cli(bin_, name, text):
    (bin_ / name).write_text(text)
    (bin_ / name).chmod(0o755)


def test_door_codex_login_says_what_happened(tmp_path):
    bin_, run = _door(tmp_path)
    out = run("codex-login")   # not installed: who installs it and the owner's one command, nothing for the member (2026-11-08)
    assert "not installed for this brain" in out and "The owner of this box" in out
    assert "bash scripts/cc/install-codex.sh elena" in out and "nothing for you to type" in out.lower()
    _fake_cli(bin_, "codex", FAKE_CODEX_LOGIN)
    (bin_ / "next").write_text("fail")
    out = run("codex-login")
    assert "Not signed in yet" in out and "Signed in." not in out
    (bin_ / "next").write_text("ok")
    out = run("codex-login")
    assert "Signed in. Close this panel" in out and (bin_ / "calls").read_text().count("login") == 2
    # signed in: the door starts no new device login (it would drop this one)
    out = run("codex-login")
    assert "already signed in" in out and (bin_ / "calls").read_text().count("login") == 2


def test_door_claude_login_says_done_only_when_signed_in(tmp_path):
    bin_, run = _door(tmp_path)
    _fake_cli(bin_, "claude", FAKE_CLAUDE_LOGIN)
    (bin_ / "next").write_text("fail")
    out = run("login")
    assert "Not signed in yet" in out and "Signed in." not in out and "Done." not in out
    (bin_ / "next").write_text("ok")
    assert "Signed in. Close this panel" in run("login")
