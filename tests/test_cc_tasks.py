"""The reasoner's task-write path (2026-10-20): cc-job task add -> bridge /tasks/add -> brain POST /tasks.

Run from repo root:
    pytest tests/test_cc_tasks.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _bridge(monkeypatch, tmp_path, with_key=True):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    if with_key:
        monkeypatch.setenv("BRAIN_API_KEY", "test-key")
    else:
        monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


def _capture(m, monkeypatch, ok=True):
    calls = []
    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"ok": True, "task": {"id": "abc123", **(body or {})}} if ok else None
    monkeypatch.setattr(m, "_brain_api", fake)
    return calls


def test_add_passes_text_due_and_source(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = _capture(m, monkeypatch)
    m.STATE_DIR.mkdir(parents=True, exist_ok=True)
    m.THREADS_FILE.write_text(json.dumps([{"brain": "t1", "title": "Music verdicts"}]))
    code, d = m._task_add({"text": "  hear the\n21 loops ", "due": "2026-10-21T09:00:00+02:00", "thread": "t1"})
    assert code == 200 and d["ok"]
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/tasks")
    assert body["text"] == "hear the 21 loops"
    assert body["due"] == "2026-10-21T07:00:00Z"
    assert body["source"] == "the brain (Music verdicts)"


def test_add_refuses_empty_long_bad_due_and_no_key(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    _capture(m, monkeypatch)
    assert m._task_add({"text": "  "})[0] == 400
    assert m._task_add({"text": "x" * 501})[0] == 400
    assert m._task_add({"text": "a", "due": "tomorrow"})[0] == 400
    m2 = _bridge(monkeypatch, tmp_path, with_key=False)
    assert m2._task_add({"text": "a"})[0] == 409


def test_add_rate_limit_and_brain_down(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    _capture(m, monkeypatch)
    m.TASK_RATE["n"] = 2
    assert m._task_add({"text": "a"})[0] == 200
    assert m._task_add({"text": "b"})[0] == 200
    assert m._task_add({"text": "c"})[0] == 429
    m.TASK_RATE["times"].clear()
    _capture(m, monkeypatch, ok=False)
    code, d = m._task_add({"text": "d"})
    assert code == 502 and not d["ok"]


def test_store_keeps_source_and_stamps_created(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_RUNTIME_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("tasks_store_t", ROOT / "api" / "tasks_store.py")
    ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)
    owner = ts.add("buy strings")
    brain = ts.add("sign the memos", source="the brain (Memos)")
    assert "source" not in owner and owner["created"].endswith("Z")
    assert ts.list_tasks()[1]["source"] == "the brain (Memos)" or ts.list_tasks()[0]["source"] == "the brain (Memos)"
    assert brain["id"] != owner["id"]


def test_add_carries_known_thread_id_only(monkeypatch, tmp_path):
    # 2026-10-24: a task remembers the thread that made it, so /tasks links back to it.
    m = _bridge(monkeypatch, tmp_path)
    calls = _capture(m, monkeypatch)
    m.STATE_DIR.mkdir(parents=True, exist_ok=True)
    m.THREADS_FILE.write_text(json.dumps([{"brain": "t1", "title": "Music verdicts"}]))
    m._task_add({"text": "a", "thread": "t1"})
    m._task_add({"text": "b", "thread": "ghost"})
    assert calls[0][2]["thread"] == "t1"
    assert calls[1][2]["thread"] is None


def test_done_closes_reopens_and_refuses_bad_ids(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    def fake(method, path, body=None):
        calls.append((method, path))
        return {"ok": "missing" not in path}
    monkeypatch.setattr(m, "_brain_api", fake)
    code, d = m._task_done({"ids": ["56a02549837f", "ff296c822577"]})
    assert code == 200 and d["ok"]
    assert calls == [("POST", "/tasks/56a02549837f/complete?done=true"), ("POST", "/tasks/ff296c822577/complete?done=true")]
    calls.clear()
    m._task_done({"ids": ["56a02549837f"], "done": False})
    assert calls == [("POST", "/tasks/56a02549837f/complete?done=false")]
    assert m._task_done({"ids": ["../etc", "x y"]})[0] == 400
    assert m._task_done({})[0] == 400
    m2 = _bridge(monkeypatch, tmp_path, with_key=False)
    assert m2._task_done({"ids": ["56a02549837f"]})[0] == 409


def test_threads_brief_lists_ids_titles_not_archived(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.STATE_DIR.mkdir(parents=True, exist_ok=True)
    m.THREADS_FILE.write_text(json.dumps([
        {"brain": "a1", "title": "YC sitting", "last": "2026-10-24T10:00:00Z"},
        {"brain": "a2", "title": "old", "archived": True},
        {"claude": "c-only", "title": "no brain id"}]))
    d = m._threads_brief()
    assert [t["id"] for t in d["threads"]] == ["a1"]
    assert d["threads"][0]["title"] == "YC sitting"


def test_store_keeps_thread(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAIN_RUNTIME_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location("tasks_store_t2", ROOT / "api" / "tasks_store.py")
    ts = importlib.util.module_from_spec(spec); spec.loader.exec_module(ts)
    assert ts.add("x", source="the brain (a)", thread="t1")["thread"] == "t1"
    assert "thread" not in ts.add("y")
