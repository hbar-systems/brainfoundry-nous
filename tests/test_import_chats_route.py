"""POST /documents/import-chats: the Knowledge page's import card (api/chat_import.py).

Synthetic exports only (the builders in test_import_chats.py). NodeOS is
replaced in-process: the test sees every permit and proposal, and checks that
each selected conversation became one PENDING proposal and nothing else.

Created 2026-10-25.
"""
import io
import json
import os
import sys
import tempfile
import types
import zipfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="import-route-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import main as m  # noqa: E402
from tests.test_import_chats import chatgpt_export, claude_export, claude_projects  # noqa: E402


def _zip(**files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name.replace("__", "/"), json.dumps(data))
    return buf.getvalue()


def _chatgpt_many(n):
    """n one-turn ChatGPT conversations, one day apart, newest last."""
    out = []
    for i in range(n):
        t = 1700000000.0 + i * 86400
        out.append({"id": f"c{i:04d}", "title": f"Chat {i}", "create_time": t, "update_time": t,
                    "current_node": "a", "mapping": {
                        "u": {"id": "u", "parent": None, "children": ["a"], "message": {
                            "author": {"role": "user"}, "create_time": t,
                            "content": {"content_type": "text", "parts": [f"question {i}"]}}},
                        "a": {"id": "a", "parent": "u", "children": [], "message": {
                            "author": {"role": "assistant"}, "create_time": t + 1,
                            "content": {"content_type": "text", "parts": [f"answer {i}"]}}}}})
    return out


@pytest.fixture
def env(monkeypatch, tmp_path):
    seen = types.SimpleNamespace(permits=[], proposals=[], fail_after=None)
    monkeypatch.setattr(m, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(m, "PROPOSAL_TEXT_DIR", tmp_path / "proposal_texts")
    (tmp_path / "proposal_texts").mkdir()

    def fake_permit(agent_id, reason):
        seen.permits.append(agent_id)
        return {"permit_id": f"permit-{len(seen.permits)}", "permit_token": "t"}

    def fake_propose(memory_type, content, permit_id, source_refs=None):
        if seen.fail_after is not None and len(seen.proposals) >= seen.fail_after:
            raise HTTPException(status_code=503, detail="NodeOS authority service unreachable")
        seen.proposals.append({"memory_type": memory_type, "permit_id": permit_id, "refs": source_refs})
        return {"proposal_id": f"prop-{len(seen.proposals):04d}"}

    def no_decide(*a, **kw):
        raise AssertionError("the import must never decide a proposal")

    monkeypatch.setattr(m, "_issue_upload_permit", fake_permit)
    monkeypatch.setattr(m, "_nodeos_propose_memory", fake_propose)
    monkeypatch.setattr(m, "_nodeos_decide_memory", no_decide)
    seen.client = TestClient(m.app)
    seen.tmp = tmp_path
    return seen


def _post(env, data, name="export.zip", **form):
    return env.client.post("/documents/import-chats", files={"file": (name, data, "application/zip")},
                           data={k: str(v) for k, v in form.items()})


def test_chatgpt_zip_proposes_every_conversation_pending(env):
    r = _post(env, _zip(**{"conversations.json": chatgpt_export()}))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["conversations"] == 2 and j["selected"] == 2 and j["proposed"] == 2
    assert j["sources"] == ["chatgpt"] and j["stopped"] == ""
    assert [p["memory_type"] for p in env.proposals] == ["document_embedding"] * 2
    assert env.permits == ["console"]  # one permit covers the run
    names = [p["refs"]["filename"] for p in env.proposals]
    assert all(n.startswith("chatgpt_") and n.endswith(".md") for n in names)
    # the text waits under each proposal id for approval; the regenerated answer is not in it
    texts = [(env.tmp / "proposal_texts" / f"prop-{i:04d}.txt").read_text() for i in (1, 2)]
    assert any("The moon pulls the water." in t for t in texts)
    assert not any("OLD ANSWER" in t for t in texts)


def test_claude_zip_and_projects_left_out(env):
    r = _post(env, _zip(**{"data/conversations.json": claude_export(), "data/projects.json": claude_projects()}))
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["sources"] == ["claude"]
    assert j["projects"] >= 1 and j["selected"] == j["conversations"] == j["proposed"]
    assert not any(p["refs"]["filename"].startswith("claude-project_") for p in env.proposals)


def test_newest_50_by_default(env):
    r = _post(env, _zip(**{"conversations.json": _chatgpt_many(60)}))
    j = r.json()
    assert (j["conversations"], j["selected"], j["proposed"], j["newest"]) == (60, 50, 50, 50)
    names = {p["refs"]["filename"] for p in env.proposals}
    assert not any("chat-0_" in n or "chat-9_" in n for n in names)  # the ten oldest stay outside
    assert any("chat-59_" in n for n in names)


def test_not_a_zip_or_no_conversations_is_400(env):
    assert _post(env, b"hello", name="notes.txt").status_code == 400
    r = _post(env, _zip(**{"users.json": [{"uuid": "x"}]}))
    assert r.status_code == 400 and "No conversations" in r.text
    assert env.proposals == []


def test_gate_down_stops_and_reports(env):
    env.fail_after = 1
    j = _post(env, _zip(**{"conversations.json": chatgpt_export()})).json()
    assert j["proposed"] == 1 and j["selected"] == 2 and "unreachable" in j["stopped"]


def test_scratch_folder_is_removed(env):
    _post(env, _zip(**{"conversations.json": chatgpt_export()}))
    left = list((env.tmp / "runtime" / "chat_imports").iterdir())
    assert left == []
