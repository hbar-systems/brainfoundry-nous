"""Codex and Claude Code history comes in (MEMBERS-11, hbar 2026-11-23, docs/IMPORT.md).

Synthetic session files only, written here: no line of anyone's real history. The parsers keep the
person's typed messages and the visible replies and drop everything else; the three walkers offer
only the session files of ~/.codex/sessions and ~/.claude/projects (never auth.json, config or
credentials); the api turns a session under those labels into ONE conversation document, PENDING,
with its Continue here starting point; a .jsonl anywhere else is refused.
"""
import json
import shutil

import pytest

from tests.test_move_in_survey import NOW, _home, server, h, li, ls, cc  # noqa: F401  (fixture and helpers)
from tests.test_laptop_agent import _run_line, _owner_chooses, _survey_paths, needs_shell
from api import chat_import
from api import laptop_agent as la

ic = chat_import.tool()


@pytest.fixture(autouse=True)
def _roomy_disk(monkeypatch):
    """A survey token's byte cap follows the free disk; this box's own disk must not decide the test."""
    du = shutil._ntuple_diskusage(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)
    monkeypatch.setattr(shutil, "disk_usage", lambda p: du)

TOOL_SECRET = "sk-live-TOOLOUTPUT-9f8e7d6c5b4a"      # only ever inside a tool result
ENV_SECRET = "AWS_SECRET_ACCESS_KEY=abc123ENVONLY"   # only ever inside injected context
REASONING = "PRIVATE-REASONING-TRACE"


def _lines(*objs):
    return ("\n".join(json.dumps(o) for o in objs) + "\n").encode()


def codex_session(cwd="/Users/sam/work/thesis", events=False, sub=False):
    ts = lambda s: f"2026-11-08T15:{s:02d}:00.000Z"  # noqa: E731
    meta = {"id": "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001", "timestamp": ts(0), "cwd": cwd,
            "originator": "codex_cli_rs", "cli_version": "0.99.0", "source": "cli"}
    if sub:
        meta.update({"source": {"subagent": {"parent": "x"}}, "thread_source": "subagent"})
    out = [
        {"timestamp": ts(0), "type": "session_meta", "payload": meta},
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "message", "role": "developer",
         "content": [{"type": "input_text", "text": "<permissions instructions>sandbox</permissions instructions>"}]}},
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": f"<environment_context>\n  <cwd>{cwd}</cwd>\n  {ENV_SECRET}\n</environment_context>"}]}},
        {"timestamp": ts(1), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /Users/sam/work/thesis\n\nbe terse"}]}},
        {"timestamp": ts(2), "type": "turn_context", "payload": {"cwd": cwd, "model": "m"}},
        {"timestamp": ts(2), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "Fix the failing test in the parser module"}]}},
        {"timestamp": ts(3), "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": REASONING}],
         "encrypted_content": "gAAAA"}},
        {"timestamp": ts(3), "type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "commentary",
         "content": [{"type": "output_text", "text": "Looking at the build first."}]}},
        {"timestamp": ts(4), "type": "response_item", "payload": {"type": "function_call", "name": "shell",
         "arguments": json.dumps({"command": ["cat", ".env"]}), "call_id": "c1"}},
        {"timestamp": ts(4), "type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1",
         "output": f"OPENAI_API_KEY={TOOL_SECRET}"}},
        {"timestamp": ts(5), "type": "response_item", "payload": {"type": "custom_tool_call", "name": "apply_patch",
         "input": "*** Begin Patch\n+secret line\n*** End Patch", "call_id": "c2"}},
        {"timestamp": ts(5), "type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "c2",
         "output": [{"type": "input_text", "text": TOOL_SECRET}]}},
        {"timestamp": ts(6), "type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer",
         "content": [{"type": "output_text", "text": "Fixed: the tolerance was too tight."}]}},
        {"timestamp": ts(6), "type": "event_msg", "payload": {"type": "token_count", "info": {"total": 5}}},
        {"timestamp": ts(7), "type": "response_item", "payload": {"type": "message", "role": "user",
         "content": [{"type": "input_text", "text": "Thanks, now write the summary"}]}},
        {"timestamp": ts(8), "type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer",
         "content": [{"type": "output_text", "text": "Summary written to notes."}]}},
    ]
    if events:  # newer CLI: the clean copy of what was typed and said, beside the items
        out += [
            {"timestamp": ts(2), "type": "event_msg", "payload": {"type": "user_message", "message": "Fix the failing test in the parser module", "images": []}},
            {"timestamp": ts(6), "type": "event_msg", "payload": {"type": "agent_message", "message": "Fixed: the tolerance was too tight."}},
            {"timestamp": ts(7), "type": "event_msg", "payload": {"type": "user_message", "message": "Thanks, now write the summary"}},
            {"timestamp": ts(8), "type": "event_msg", "payload": {"type": "agent_message", "message": "Summary written to notes."}},
        ]
    return _lines(*out)


def claude_code_session(cwd="/Users/sam/code/site"):
    sid = "5b1c2d3e-0000-4000-8000-00000000abcd"
    base = {"sessionId": sid, "cwd": cwd, "version": "2.0.0", "gitBranch": "main", "userType": "external", "isSidechain": False}
    ts = lambda s: f"2026-11-09T10:{s:02d}:00.000Z"  # noqa: E731
    u = lambda i, content, **kw: {**base, "type": "user", "uuid": f"u{i}", "parentUuid": None, "timestamp": ts(i),  # noqa: E731
                                  "message": {"role": "user", "content": content}, **kw}
    a = lambda i, content, **kw: {**base, "type": "assistant", "uuid": f"a{i}", "parentUuid": f"u{i}", "timestamp": ts(i),  # noqa: E731
                                  "message": {"role": "assistant", "model": "claude-x", "content": content}, **kw}
    return _lines(
        {"type": "summary", "summary": "old summary line", "leafUuid": "u1"},
        {"type": "file-history-snapshot", "messageId": "m", "snapshot": {"trackedFileBackups": {"a.py": {"backupFileName": "x"}}}},
        u(1, "Caveat: The messages below were generated by the user while running local commands.", isMeta=True),
        u(2, "<command-name>/clear</command-name>\n<command-message>clear</command-message>\n<command-args></command-args>"),
        u(3, "<local-command-stdout>cleared</local-command-stdout>"),
        u(4, [{"type": "text", "text": "Make the header sticky on mobile"},
              {"type": "text", "text": f"<system-reminder>{ENV_SECRET}</system-reminder>"}]),
        a(4, [{"type": "thinking", "thinking": REASONING, "signature": "sig"},
              {"type": "text", "text": "I will read the stylesheet."},
              {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/Users/sam/code/site/.env"}}]),
        u(5, [{"type": "tool_result", "tool_use_id": "t1", "content": f"STRIPE_KEY={TOOL_SECRET}"}],
          toolUseResult={"stdout": TOOL_SECRET}),
        a(5, [{"type": "text", "text": "Done: position sticky with a top offset."}]),
        {**u(6, "side task prompt"), "isSidechain": True},
        {**a(6, [{"type": "text", "text": "side answer"}]), "isSidechain": True},
        a(7, [{"type": "text", "text": "API Error: overloaded"}], isApiErrorMessage=True),
        u(8, [{"type": "text", "text": "And the footer?"}, {"type": "image", "source": {"type": "base64", "data": "iVBOR"}}]),
        a(8, [{"type": "text", "text": "The footer now matches."}]),
        {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted", **base, "timestamp": ts(9)},
        u(10, "This session is being continued from a previous conversation...", isCompactSummary=True,
          isVisibleInTranscriptOnly=True),
    )


# ── the parsers ──────────────────────────────────────────────────────

def _doc(data):
    c = ic.session_conversation(data, "x.jsonl")
    return c, ic.render(c)


def test_codex_keeps_typed_and_visible_only():
    c, doc = _doc(codex_session())
    assert c["source"] == "codex" and c["id"] == "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0001"
    assert [r for r, _w, _t in c["turns"]] == ["user", "assistant", "user", "assistant"]
    assert c["title"] == "Fix the failing test in the parser module"
    assert c["date"] == "2026-11-08" and c["updated"] == "2026-11-08T15:08:00Z"
    assert "Looking at the build first.\n\nFixed: the tolerance was too tight." in doc   # one answer, split around tools
    assert "Working folder: /Users/sam/work/thesis" in doc and "## Assistant (Codex)" in doc
    for gone in (TOOL_SECRET, ENV_SECRET, REASONING, "AGENTS.md", "permissions instructions", "apply_patch", "secret line"):
        assert gone not in doc


def test_codex_event_copy_is_used_once_and_subagents_are_not_conversations():
    c, doc = _doc(codex_session(events=True))
    assert [r for r, _w, _t in c["turns"]] == ["user", "assistant", "user", "assistant"]
    assert doc.count("Fix the failing test") == 2   # title and the one turn
    assert ic.session_conversation(codex_session(sub=True))["turns"] == []


def test_claude_code_keeps_typed_and_visible_only():
    c, doc = _doc(claude_code_session())
    assert c["source"] == "claude-code" and c["id"] == "5b1c2d3e-0000-4000-8000-00000000abcd"
    assert c["title"] == "Make the header sticky on mobile"
    assert [r for r, _w, _t in c["turns"]] == ["user", "assistant", "user", "assistant"]
    assert "I will read the stylesheet.\n\nDone: position sticky with a top offset." in doc
    assert "And the footer?\n\n[image]" in doc and "## Assistant (Claude Code)" in doc
    assert "Working folder: /Users/sam/code/site" in doc
    for gone in (TOOL_SECRET, ENV_SECRET, REASONING, "Caveat", "/clear", "cleared", "side task", "side answer",
                 "API Error", "continued from a previous", "old summary", "backupFileName", "tool_use", ".env"):
        assert gone not in doc


def test_not_a_session_and_prep_names():
    assert ic.session_conversation(b'{"a": 1}\nnot json\n') is None
    assert ic.session_kind([]) == ""


def test_prep_reads_a_dropped_jsonl(tmp_path):
    for data, src in ((codex_session(), "codex"), (claude_code_session(), "claude-code")):
        f = tmp_path / f"{src}.jsonl"
        f.write_bytes(data)
        rows = ic.prep(f, tmp_path / f"out-{src}")
        assert len(rows) == 1 and rows[0]["source"] == src and rows[0]["kind"] == "conversation"
        name = rows[0]["file"].split("/")[-1]
        assert name.startswith(src + "_2026-11-0") and cc.is_chat(name) and cc.source_of(name) == src
        p = cc.parse((tmp_path / f"out-{src}" / rows[0]["file"]).read_text())
        assert p["started"].startswith("2026-11-0") and p["turns"][0]["who"] == "me"


def test_import_chats_route_takes_a_jsonl(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    r = c.post("/documents/import-chats", files={"file": ("rollout-2026-11-08T15-00-00-x.jsonl", codex_session(), "application/x-ndjson")})
    assert r.status_code == 200, r.text
    assert r.json()["sources"] == ["codex"] and r.json()["proposed"] == 1
    assert server.proposals[-1]["refs"]["filename"].startswith("codex_2026-11-08_")


# ── the walkers ──────────────────────────────────────────────────────

def _agent_home(home):
    files = {
        ".codex/auth.json": '{"OPENAI_API_KEY": "sk-AUTHJSON"}',
        ".codex/config.toml": "model = 'x'",
        ".codex/history.jsonl": '{"text": "HISTORYJSONL"}',
        ".codex/sessions/2026/11/08/notes.txt": "not a chat",
        ".claude/.credentials.json": '{"token": "CREDENTIALS"}',
        ".claude/settings.json": "{}",
        ".claude/CLAUDE.md": "memory",
        ".claude/projects/-Users-sam-code-site/memory/MEMORY.md": "memory folder",
        ".claude/projects/-Users-sam-code-site/5b1c2d3e/subagents/agent-1.jsonl": '{"type": "user"}',
        ".claude/projects/-Users-sam-code-site/token-dump.jsonl": '{"x": 1}',
        ".claude/projects/-Users-sam-code-site/.hidden.jsonl": '{"x": 1}',
    }
    for rel, body in files.items():
        p = home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    s = home / ".codex/sessions/2026/11/08/rollout-2026-11-08T15-00-00-0199aaaa.jsonl"
    s.write_bytes(codex_session())
    (home / ".claude/projects/-Users-sam-code-site/5b1c2d3e-0000-4000-8000-00000000abcd.jsonl").write_bytes(claude_code_session())
    (home / ".claude/projects/-Users-sam-code-site/empty.jsonl").write_text("")
    big = home / ".claude/projects/-Users-sam-code-site/big.jsonl"
    with open(big, "wb") as f:
        f.truncate(h.MAX_FILE_BYTES + 1)


CODEX_NAME = "Codex history/2026/11/08/rollout-2026-11-08T15-00-00-0199aaaa.jsonl"
CLAUDE_NAME = "Claude Code history/-Users-sam-code-site/5b1c2d3e-0000-4000-8000-00000000abcd.jsonl"


def test_python_survey_offers_session_files_only(tmp_path):
    _agent_home(tmp_path)
    rows, skipped, _places, roots = h.survey(tmp_path, system="linux")
    names = sorted(n for n, _s, _m in rows)
    assert names == sorted([CODEX_NAME, CLAUDE_NAME])
    assert roots == ["Codex history", "Claude Code history"]
    assert skipped["Codex history/2026: not a chat"] == 1
    assert skipped["Claude Code history/-Users-sam-code-site: not a chat"] == 2      # subagent file, memory folder
    assert skipped["Claude Code history/-Users-sam-code-site: secret"] == 1           # token-dump.jsonl
    assert skipped["Claude Code history/-Users-sam-code-site: over 25 MB"] == 1
    assert skipped["Claude Code history/-Users-sam-code-site: empty"] == 1
    assert not any("auth" in k or "credential" in k or "config" in k for k in skipped)  # never walked


def test_history_roots_not_followed_through_links(tmp_path):
    real = tmp_path / "elsewhere"
    (real / "sessions").mkdir(parents=True)
    (real / "sessions" / "a.jsonl").write_text("{}")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".codex").symlink_to(real)
    assert h.history_roots(home) == []


def test_plan_groups_each_history_whole_into_knowledge():
    files = [[f"Codex history/2026/11/{d:02d}/rollout-{i}.jsonl", 100, NOW] for d in range(1, 20) for i in range(30)]
    files += [[CLAUDE_NAME, 50, NOW], ["Documents/a.jsonl", 10, NOW], ["Codex history/x.txt", 5, NOW]]
    inv = ls.validate({"files": files})
    assert len(inv["files"]) == 19 * 30 + 1            # a .jsonl elsewhere, a .txt under the label: not offered
    g = {x["folder"]: x for x in ls.plan(inv, NOW)}
    assert set(g) == {"Codex history", "Claude Code history"}   # never split, even over 400 files
    assert g["Codex history"]["kind"] == g["Codex history"]["proposal"] == "knowledge"
    assert g["Codex history"]["why"] == "codex_history" and g["Claude Code history"]["why"] == "claude_code_history"


def test_rendered_agents_carry_the_history_roots():
    sh = la.render("sh", "https://brain.example/api/bf")
    assert "HISTORY_ROOTS=('Codex history|.codex/sessions|0' 'Claude Code history|.claude/projects|2')" in sh
    assert 'ext != "jsonl"' in sh and "W_HISTORY=" in sh
    ps = la.render("ps1", "https://brain.example/api/bf", "ru")
    assert "@{ label = 'Codex history'; sub = '.codex\\sessions'; depth = 0 }" in ps
    assert "@{ label = 'Claude Code history'; sub = '.claude\\projects'; depth = 2 }" in ps
    assert "$HistoryExt = 'jsonl'" in ps and "HISTORY = 'История Codex" in ps


@needs_shell
def test_agent_sh_brings_history_as_conversations(server, tmp_path):
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    _agent_home(home)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    t = _owner_chooses(c, pick=lambda gs: [g["id"] for g in gs if g["folder"] in ("Codex history", "Claude Code history")])
    r = _run_line(server.url, tok, home, agent_tmp)
    t.join(10)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Codex history, Claude Code history" in r.stdout and "Cloud folders: iCloud Drive, Google Drive, Dropbox." in r.stdout

    listed, data = _survey_paths(server.m)
    rows, skipped, _places, roots = h.survey(home, system="darwin")
    assert listed == sorted(n for n, _s, _m in rows)            # the shell walk is the Python walk
    assert data["skipped"] == skipped and data["roots"] == roots
    assert CODEX_NAME in listed and CLAUDE_NAME in listed
    assert not any(x in p for p in listed for x in ("auth", "credentials", "config", "settings", "subagents", "MEMORY"))

    names = sorted(p["refs"]["filename"] for p in server.proposals)
    assert len(names) == 2 and names[0].startswith("claude-code_2026-11-09_") and names[1].startswith("codex_2026-11-08_")
    texts = " ".join(p.read_text() for p in (server.tmp / "proposal_texts").glob("*.txt"))
    for gone in (TOOL_SECRET, ENV_SECRET, REASONING, "sk-AUTHJSON", "CREDENTIALS", "HISTORYJSONL"):
        assert gone not in texts
    # Continue here has the starting point of both
    kept = cc.listing(server.tmp / "chat_continue")
    assert sorted(k["vendor"] for k in kept) == ["Claude Code", "Codex"]
    assert "Done: 2 sent, 0 not taken." in r.stdout


# ── the route ────────────────────────────────────────────────────────

def _send(c, tok, path, data):
    return c.post("/documents/import-laptop/file", data={"path": path},
                  files={"file": (path.split("/")[-1], data, "application/octet-stream")},
                  headers={"Authorization": f"Bearer {tok}"})


def test_route_session_under_label_is_one_pending_conversation(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    r = _send(c, tok, CODEX_NAME, codex_session())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "PENDING" and j["name"].startswith("codex_2026-11-08_fix-the-failing-test")
    assert server.proposals[-1]["refs"]["filename"] == j["name"]
    text = (server.tmp / "proposal_texts" / f"{j['proposal_id']}.txt").read_text()
    assert text.startswith("# Fix the failing test") and TOOL_SECRET not in text
    assert cc.get(server.tmp / "chat_continue", j["name"])["vendor"] == "Codex"
    st = c.get("/documents/import-laptop/status").json()["run"]
    assert st["files"] == 1 and st["bytes"] == len(codex_session())   # charged to the token

    assert _send(c, tok, CLAUDE_NAME, claude_code_session()).json()["name"].startswith("claude-code_")
    # a session of the other tool under a label, or nothing typed: not a conversation
    assert _send(c, tok, "Codex history/2026/a.jsonl", claude_code_session()).status_code == 422
    assert _send(c, tok, "Codex history/2026/b.jsonl", codex_session(sub=True)).status_code == 422


def test_route_refuses_jsonl_elsewhere_and_without_token(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    for path in ("Documents/rollout.jsonl", "Codex history.jsonl", "laptop/Codex history/a.jsonl"):
        assert _send(c, tok, path, codex_session()).status_code == 415, path
    assert _send(c, tok, ".codex/sessions/a.jsonl", codex_session()).status_code == 400
    assert c.post("/documents/import-laptop/file", data={"path": CODEX_NAME},
                  files={"file": ("a.jsonl", codex_session(), "application/octet-stream")}).status_code == 401
    assert server.proposals == []
