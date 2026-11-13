"""cc_threads_store (scripts/cc/cc_threads_store.py): threads.json survives a full disk and a lost
list comes back from the brain's sessions (2026-11-13). Pure, temp dirs only.

Run from repo root:
    pytest tests/test_cc_threads_store.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_threads_store", ROOT / "scripts" / "cc" / "cc_threads_store.py")
S = importlib.util.module_from_spec(spec); sys.modules["cc_threads_store"] = S; spec.loader.exec_module(S)


def _iso(ago_s: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago_s))


def test_save_load_and_bak(tmp_path):
    f = tmp_path / "threads.json"
    S.save(f, [{"brain": "a"}])
    S.save(f, [{"brain": "a"}, {"brain": "b"}])
    assert [x["brain"] for x in S.load(f)] == ["a", "b"]
    assert [x["brain"] for x in json.loads((tmp_path / "threads.json.bak").read_text())] == ["a"]


def test_broken_file_reads_the_bak_not_empty(tmp_path):
    f = tmp_path / "threads.json"
    S.save(f, [{"brain": "a"}, {"brain": "b"}])
    S.save(f, [{"brain": "a"}, {"brain": "b"}, {"brain": "c"}])
    f.write_text('[{"brain": "a"}, {"bra')            # a short write, as on a full disk
    assert [x["brain"] for x in S.load(f)] == ["a", "b"]


def test_failed_write_leaves_old_file_whole(tmp_path, monkeypatch):
    f = tmp_path / "threads.json"
    S.save(f, [{"brain": "a"}])
    real = S.os.replace

    def full(src, dst):
        if str(dst) == str(f):
            raise OSError(28, "No space left on device")
        return real(src, dst)
    monkeypatch.setattr(S.os, "replace", full)
    with pytest.raises(OSError):
        S.save(f, [{"brain": "a"}, {"brain": "b"}])
    assert json.loads(f.read_text()) == [{"brain": "a"}]
    assert not list(tmp_path.glob("*.tmp"))


def _transcript(d: pathlib.Path, sid: str, message: str, ts: str) -> None:
    line = {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": f"<persona>p</persona>\n<message>\n{message}\n</message>"}}
    f = d / f"{sid}.jsonl"
    f.write_text(json.dumps({"type": "summary"}) + "\n" + json.dumps(line) + "\n")
    t = S._when(ts) or time.time()
    import os; os.utime(f, (t, t))


def test_recover_adds_missing_matches_transcript_and_archives_old(tmp_path):
    proj = tmp_path / "proj"; proj.mkdir()
    _transcript(proj, "t-new", "fix the   login page please", _iso(3600))
    _transcript(proj, "t-old", "write the blog post", _iso(30 * 86400))
    items = [{"brain": "kept", "title": "CC: kept", "last": _iso(60)}]
    sessions = [
        {"session_id": "kept", "model_name": "cc", "title": "CC: kept", "created_at": _iso(60)},
        {"session_id": "s1", "model_name": "cc", "title": "CC: fix the login page please", "created_at": _iso(3700)[:-1]},
        {"session_id": "s2", "model_name": "cc", "title": "CC: write the blog post", "created_at": _iso(30 * 86400 + 10)},
        {"session_id": "web", "model_name": "llama", "title": "CC: not a console thread", "created_at": _iso(10)},
    ]
    out, n = S.recover(items, sessions, proj)
    assert n == 2
    by = {x["brain"]: x for x in out}
    assert set(by) == {"kept", "s1", "s2"}
    assert by["s1"]["claude"] == "t-new" and not by["s1"].get("archived") and by["s1"]["recovered"]
    assert by["s2"]["archived"] is True
    assert out[-1]["brain"] == "kept"                 # ordered by last activity
    again, n2 = S.recover(out, sessions, proj)
    assert n2 == 0 and again == out


def test_recover_without_transcript_still_restores(tmp_path):
    out, n = S.recover([], [{"session_id": "s", "model_name": "cc", "title": "CC: hello there",
                             "created_at": _iso(100)}], tmp_path / "missing")
    assert n == 1 and out[0]["claude"] is None and out[0]["brain"] == "s"
