"""The private seat (SEAT-3, 2026-11-23): scripts/cc/cc_private.py and its use in cc-bridge.py.

No network and no model: Ollama is a stub opener; the tools run through a recording runner. Run from repo root:
    pytest tests/test_cc_private.py -v
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
sys.path.insert(0, str(ROOT / "tests"))
import cc_local  # noqa: E402
import cc_private  # noqa: E402
from test_cc_codex import _load, _no_popen  # noqa: E402

BASE = "http://127.0.0.1:11435/v1"


class _R(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _ollama(replies, seen=None, tags=("qwen3:4b", cc_local.PRIVATE_MODEL)):
    """A stub urlopen: /v1/models answers (the seat's probe); /api/tags lists `tags`; /api/chat answers the
    next of `replies` (a message dict)."""
    it = iter(replies)
    def opener(req, timeout=None):
        if req.full_url.endswith("/v1/models"):
            return _R(b"{}")
        if req.full_url.endswith("/api/tags"):
            return _R(json.dumps({"models": [{"name": t} for t in tags]}).encode())
        body = json.loads(req.data.decode())
        if seen is not None:
            seen.append(body)
        return _R(json.dumps({"message": next(it), "prompt_eval_count": 100, "eval_count": 10}).encode())
    return opener


def _ws(tmp_path):
    ws = tmp_path / "brain"
    (ws / "notes").mkdir(parents=True, exist_ok=True)
    (ws / "notes" / "garden.md").write_text("Tomatoes split after the rain.\n")
    (ws / ".env").write_text("BRAIN_API_KEY=secret-never-read\n")
    (ws / "api").mkdir(exist_ok=True)
    (ws / "api" / "identity_private.key").write_text("k")
    return ws


# ------------------------------------------------------------ paths and tools ----
def test_paths_stay_inside_the_brain_and_off_secrets(tmp_path):
    ws = _ws(tmp_path)
    assert cc_private.safe_path(ws, "notes/garden.md") == (ws / "notes" / "garden.md").resolve()
    for bad in ("../x", "/etc/passwd", "~/.ssh/id_ed25519", ".env", "notes/../.env", "api/identity_private.key",
                ".ssh/config", ".cc-bridge/env", "a\x00b", "", "  "):
        assert cc_private.safe_path(ws, bad) is None or bad == "/etc/passwd", bad
    # an absolute path is taken as inside the brain, never as the box's own file
    p = cc_private.safe_path(ws, "/etc/passwd")
    assert p is not None and ws.resolve() in p.parents


def test_a_symlink_out_of_the_brain_is_refused(tmp_path):
    ws = _ws(tmp_path)
    (tmp_path / "outside.txt").write_text("not yours")
    (ws / "notes" / "link.md").symlink_to(tmp_path / "outside.txt")
    assert cc_private.safe_path(ws, "notes/link.md") is None


def test_tools_are_fixed_read_only_argv(tmp_path):
    ws = _ws(tmp_path)
    argv, no = cc_private.tool_argv("read_file", {"path": "notes/garden.md"}, ws)
    assert no is None and argv[:3] == ["head", "-c", str(cc_private.READ_CAP)] and argv[3] == "--"
    argv, _ = cc_private.tool_argv("list_files", {"path": "."}, ws)
    assert argv[0] == "ls" and argv[-2] == "--"
    argv, _ = cc_private.tool_argv("search", {"text": "-rf /; rm"}, ws)
    assert argv[0] == "grep" and argv[argv.index("--") + 1] == "-rf /; rm"   # the text is data after --, never a flag
    for name, args in (("shell", {"cmd": "rm -rf /"}), ("write_file", {"path": "x"}), ("read_file", {"path": ".env"}),
                       ("search", {"text": "a\nb"}), ("read_file", "notes")):
        argv, no = cc_private.tool_argv(name, args, ws)
        assert argv is None and no, name


def test_search_and_listing_drop_secret_names(tmp_path):
    ws = _ws(tmp_path)
    out = f"{ws}/notes/garden.md:1:Tomatoes\n{ws}/.env:1:BRAIN_API_KEY=x\n"
    assert cc_private.tool_result("search", out, 0, ws) == "notes/garden.md:1:Tomatoes"
    assert ".env" not in cc_private.tool_result("list_files", ".env\nnotes/\napi/\n", 0, ws)


def test_loose_json_tool_call_from_a_small_model():
    assert cc_private.loose_call('{"name": "read_file", "parameters": {"path": "notes/a.md"}}') == ("read_file", {"path": "notes/a.md"})
    assert cc_private.loose_call('{"name": "say_hi", "parameters": {}}') is None
    assert cc_private.loose_call("Here: {\"name\": \"read_file\"}") is None


# ------------------------------------------------------------ one turn ----
def test_turn_reads_through_the_runner_and_answers(tmp_path):
    ws = _ws(tmp_path)
    ran, seen = [], []
    def run(argv):
        ran.append(argv)
        return (ws / "notes" / "garden.md").read_text(), 0
    op = _ollama([{"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "notes/garden.md"}}}]},
                  {"content": "They split after the rain."}], seen)
    events = []
    d = cc_private.run_turn(BASE, "qwen3:4b", "SYS", "<message>what went wrong?</message>", [], ws, run,
                            on_event=lambda k, p: events.append((k, p)), opener=op)
    assert d["error"] is None and d["reply"] == "They split after the rain." and d["steps"] == 1
    assert ran == [["head", "-c", str(cc_private.READ_CAP), "--", str((ws / "notes" / "garden.md").resolve())]]
    assert events == [("tool", {"name": "read_file", "brief": "read_file: notes/garden.md"})]
    assert seen[0]["think"] is False and seen[0]["options"]["num_ctx"] == cc_private.CTX
    assert seen[0]["options"]["num_predict"] == cc_private.PREDICT   # every call ends by itself on a shared Ollama
    assert {t["function"]["name"] for t in seen[0]["tools"]} == {"read_file", "list_files", "search"}
    tool_msg = seen[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["content"].startswith("<file-content")
    # what the thread keeps: the person's message and the answer, never the file
    assert [m["role"] for m in d["messages"]] == ["user", "assistant"] and "Tomatoes" not in json.dumps(d["messages"])


def test_a_refused_path_never_reaches_the_runner(tmp_path):
    ws = _ws(tmp_path)
    def run(argv):
        raise AssertionError("nothing may run for a secret")
    op = _ollama([{"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": ".env"}}}]},
                  {"content": "I may not open that file."}])
    d = cc_private.run_turn(BASE, "qwen3:4b", "SYS", "read .env", [], ws, run, opener=op)
    assert d["reply"] == "I may not open that file." and d["steps"] == 1


def test_endless_tool_calls_end_the_turn(tmp_path):
    ws = _ws(tmp_path)
    call = {"content": "", "tool_calls": [{"function": {"name": "list_files", "arguments": {"path": "."}}}]}
    seen = []
    d = cc_private.run_turn(BASE, "m", "SYS", "x", [], ws, lambda a: ("notes/\n", 0),
                            opener=_ollama([call] * (cc_private.MAX_STEPS + 1), seen, tags=("m",)))
    assert d["error"] and d["steps"] == cc_private.MAX_STEPS
    assert "tools" not in seen[-1] and len(seen) == cc_private.MAX_STEPS + 1   # the last round has no tools, and its call never ran


def test_installed_check():
    assert cc_private.installed(BASE, "qwen3:4b", opener=_ollama([])) is True
    assert cc_private.installed(BASE, "phi4-mini", opener=_ollama([])) is False
    assert cc_private.installed(BASE, "x", opener=lambda r, timeout=None: (_ for _ in ()).throw(OSError())) is None


# ------------------------------------------------------------ settings ----
def test_private_needs_the_owner_opt_in_and_keeps_an_owner_endpoint_on_codex():
    assert cc_local.settings({})["base"] == ""
    st = cc_local.settings({"CC_PRIVATE": "1"})
    assert (st["base"], st["model"], st["engine"]) == (cc_local.PRIVATE_URL, cc_local.PRIVATE_MODEL, "native")
    own = cc_local.settings({"CC_LOCAL_BASE_URL": "http://100.64.1.2:8000/v1", "CC_LOCAL_MODEL": "qwen-72b"})
    assert own["engine"] == "codex"   # unchanged for an owner's pod
    assert cc_local.settings({"CC_PRIVATE": "1", "CC_LOCAL_ENGINE": "codex"})["engine"] == "codex"
    s = cc_local.status({"CC_PRIVATE": "1"}, live=False, chosen=False)
    assert s["configured"] and not s["chosen"] and s["label"] == "Private brain"


# ------------------------------------------------------------ in the bridge ----
def test_offered_is_not_chosen(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("CC_PRIVATE", "1")
    for k in ("CC_LOCAL_BASE_URL", "CC_LOCAL_MODEL", "CC_LOCAL_CHOSEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(m, "_auth_status", lambda *a, **kw: {"loggedIn": False})
    monkeypatch.setattr(m, "_codex_status", lambda *a, **kw: {"installed": False})
    assert m._default_seat() == "claude"                      # the sign-in screen still shows
    assert m._local_status(live=False)["chosen"] is False
    m._private_choose(True)
    assert m._default_seat() == "local" and m._local_status(live=False)["chosen"] is True
    m._private_choose(False)
    assert m._default_seat() == "claude"


def test_bridge_native_turn_runs_tools_as_hands_and_keeps_text_history(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("CC_PRIVATE", "1")
    monkeypatch.delenv("CC_LOCAL_BASE_URL", raising=False)
    monkeypatch.delenv("CC_LOCAL_MODEL", raising=False)
    (tmp_path / "brain" / "notes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "brain" / "notes" / "a.md").write_text("hello")
    monkeypatch.setattr(m.subprocess, "Popen", _no_popen)          # no Codex process on this engine
    op = _ollama([{"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "notes/a.md"}}}]},
                  {"content": "It says hello."}])
    monkeypatch.setattr(cc_private.urllib.request, "urlopen", op)
    wrapped = []
    monkeypatch.setattr(m, "_as_hands", lambda cmd, env=None: wrapped.append(cmd) or cmd)
    reply, sid, err = m._run_codex_turn("what is in notes/a.md?", None, on_event=lambda k, p: None, seat="local")
    assert (reply, err) == ("It says hello.", False) and len(sid) == 32
    assert wrapped and wrapped[0][0] == "head"                       # the read went through the hands wrapper
    assert m.META["cost"] == 0 and m.META["steps"] == 1
    hist = json.loads((m.PRIVATE_DIR / f"{sid}.json").read_text())
    assert [h["role"] for h in hist] == ["user", "assistant"]


def test_bridge_refuses_when_the_model_is_not_installed(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("CC_PRIVATE", "1")
    monkeypatch.delenv("CC_LOCAL_BASE_URL", raising=False)
    monkeypatch.setattr(cc_private.urllib.request, "urlopen", _ollama([], tags=("llama3.2:3b",)))   # one urllib for both modules
    monkeypatch.setattr(m, "_run_turn", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no fallback to Claude")))
    reply, sid, err = m._run_codex_turn("hi", None, on_event=lambda k, p: None, seat="local")
    assert err is True and "not installed" in reply and "nothing fell back" in reply


# ------------------------------------------------------------ round 2 of the bench: the engine's own words ----
SYS_WITH_PROPOSAL = ("You are the brain. You may read files. When the person asks for a change on this box, you may propose "
                     "exactly one shell command: end your answer with <box-proposal>{...}</box-proposal>. ... You cannot "
                     "change anything else from this surface: not memory, not settings.")


def test_system_keeps_the_rule_in_the_engines_words_and_context_moves_out_of_the_message():
    s = cc_private.private_system(SYS_WITH_PROPOSAL, "<persona>\nMara\n</persona>")
    assert "you may propose exactly one shell command" not in s          # the copied JSON example is gone
    assert "Only when the person asks you to CHANGE" in s and "Never propose to read" in s
    assert s.rstrip().endswith("Mara\n</persona>")
    no_box = cc_private.private_system("You are the brain. When the person wants a change, say exactly what you would change.")
    assert "<box-proposal>" not in no_box                                # without the box lane there is nothing to propose
    ctx, msg = cc_private.split_prompt("<persona>\nP\n</persona>\n\n<memory>\nM\n</memory>\n\n<message>\nhello\n</message>")
    assert (ctx, msg) == ("<persona>\nP\n</persona>\n\n<memory>\nM\n</memory>", "hello")


def test_a_read_dressed_as_a_proposal_runs_as_the_read_and_a_change_stays_a_proposal(tmp_path):
    assert cc_private.proposal_as_read('<box-proposal>{"command": "read_file \'notes/a.md\'", "summary": "x"}</box-proposal>') == ("read_file", {"path": "notes/a.md"})
    assert cc_private.proposal_as_read('<box-proposal>{"command": "list_files", "summary": "x"}</box-proposal>') == ("list_files", {"path": "."})
    for change in ("rm -rf notes", "read_file notes/a.md; rm x", "cat .env", "search"):
        assert cc_private.proposal_as_read('<box-proposal>{"command": "%s"}</box-proposal>' % change) is None, change
    ws = _ws(tmp_path)
    ran = []
    op = _ollama([{"content": '<box-proposal>{"command": "read_file notes/garden.md"}</box-proposal>'}, {"content": "They split."}])
    d = cc_private.run_turn(BASE, "qwen3:4b", SYS_WITH_PROPOSAL, "<message>\nwhat went wrong?\n</message>", [], ws,
                            lambda a: ran.append(a) or ("Tomatoes split", 0), opener=op)
    assert d["reply"] == "They split." and ran and ran[0][0] == "head"
    # a proposed read of a secret is refused like any other read
    op = _ollama([{"content": '<box-proposal>{"command": "read_file .env"}</box-proposal>'}, {"content": "I may not."}])
    d = cc_private.run_turn(BASE, "qwen3:4b", SYS_WITH_PROPOSAL, "x", [], ws, lambda a: (_ for _ in ()).throw(AssertionError("no run")), opener=op)
    assert d["reply"] == "I may not."


def test_copied_context_blocks_are_cut_from_the_answer():
    assert cc_private.clean_reply("<memory>\nold\n</memory>\n\nThe answer.") == "The answer."
    assert cc_private.clean_reply("<persona>x</persona>Hi") == "Hi"
