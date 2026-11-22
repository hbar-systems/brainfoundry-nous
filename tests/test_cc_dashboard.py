"""The owner's dashboard (DASH-1, 2026-11-22): the knowledge map read from the world, the pushes row, the view.

Run from repo root:
    pytest tests/test_cc_dashboard.py -v
No network, no bridge: the module only reads files it is handed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_dashboard as D  # noqa: E402


def _world(tmp_path, data=None):
    w = tmp_path / "world"
    (w / "ops" / "dashboard").mkdir(parents=True)
    (w / "ops" / "study").mkdir()
    (w / "ops" / "study" / "drills.md").write_text("# drills\n")
    if data is not None:
        (w / "ops" / "dashboard" / "knowledge.json").write_text(json.dumps(data) if not isinstance(data, str) else data)
    D._cache.clear()
    return w


MAP = {"title": "AI engineering", "line": "From one weight to a fleet.", "groups": [
    {"id": "inference", "name": "Inference", "line": "What one call costs.", "topics": [
        {"id": "batching", "name": "Batching", "line": "Throughput against latency.", "weak": "graded 1/5",
         "points": ["Static against continuous", 7, "", None],
         "links": [{"label": "Drills", "path": "ops/study/drills.md"}, {"label": "Study", "path": "ops/study"},
                   {"label": "Gone", "path": "ops/study/missing.md"}, {"label": "Paper", "url": "https://example.org/p"}]}]}]}


def test_no_world_no_file_or_broken_file_is_no_map(tmp_path):
    assert D.load_map(None) is None and D.load_map("") is None
    assert D.load_map(_world(tmp_path)) is None
    for i, bad in enumerate(("{not json", "[]", '{"groups": "x"}', '{"groups": []}', '{"groups": [{"line": "no name"}]}')):
        assert D.load_map(_world(tmp_path / f"bad{i}", bad)) is None, bad


def test_map_is_cleaned_and_links_are_resolved(tmp_path):
    w = _world(tmp_path, MAP)
    m = D.load_map(w)
    assert m["title"] == "AI engineering" and [g["id"] for g in m["groups"]] == ["inference"]
    t = m["groups"][0]["topics"][0]
    assert t["name"] == "Batching" and t["weak"] == "graded 1/5" and t["points"] == ["Static against continuous", "7"]
    file, folder, gone, paper = t["links"]
    real = os.path.realpath(w)
    assert file["exists"] and not file["dir"] and file["href"] == "/files?path=" + (real + "/ops/study/drills.md").replace("/", "%2F")
    assert folder["exists"] and folder["dir"]
    assert gone["exists"] is False and gone["label"] == "Gone"
    assert paper == {"label": "Paper", "url": "https://example.org/p"}


def test_links_never_leave_the_world(tmp_path):
    (tmp_path / "secret.txt").write_text("k")
    w = _world(tmp_path)
    os.symlink(tmp_path / "secret.txt", w / "ops" / "study" / "door.md")
    for raw in ({"path": "../secret.txt"}, {"path": "ops/../../secret.txt"}, {"path": "/etc/passwd"}, {"path": "~/x"},
                {"path": "ops/study/door.md"}, {"url": "http://example.org"}, {"url": "javascript:alert(1)"},
                {"label": "nothing"}, "ops/study/drills.md", None):
        assert D._link(w, raw) is None, raw
    assert D._link(w, {"path": "ops/study/drills.md"})["exists"] is True


def test_sizes_are_capped(tmp_path):
    big = {"groups": [{"name": f"g{i}", "topics": [
        {"name": f"t{j}", "points": ["p"] * 12, "links": [{"path": "ops/study/drills.md"}] * 12} for j in range(20)]} for i in range(20)]}
    m = D.load_map(_world(tmp_path, big))
    assert len(m["groups"]) == D.MAX_GROUPS and len(m["groups"][0]["topics"]) == D.MAX_TOPICS
    t = m["groups"][0]["topics"][0]
    assert len(t["points"]) == D.MAX_POINTS and len(t["links"]) == D.MAX_LINKS
    assert m["groups"][3]["id"] == "g3" and m["groups"][0]["topics"][2]["id"] == "t2"   # ids fall back to the position
    w = _world(tmp_path / "huge")
    (w / "ops" / "dashboard" / "knowledge.json").write_text(json.dumps({"groups": [{"name": "x" * (D.MAX_BYTES + 1)}]}))
    assert D.load_map(w) is None


def test_map_is_reread_when_the_file_changes(tmp_path):
    w = _world(tmp_path, MAP)
    assert D.load_map(w)["title"] == "AI engineering"
    p = w / "ops" / "dashboard" / "knowledge.json"
    p.write_text(json.dumps({**MAP, "title": "Changed title"}))
    os.utime(p, ns=(1, 1))
    assert D.load_map(w)["title"] == "Changed title"


def test_pushes_reads_the_steward_queue(tmp_path):
    w = _world(tmp_path)
    assert D.pushes(w) == [] and D.pushes(None) == []
    (w / "ops" / "steward").mkdir()
    (w / "ops" / "steward" / "queue.md").write_text(
        "# Steward queue\n\n## Ready to push, your word\n\n"
        "### world (main): 23 commit(s) ahead; leak check: clean\n- abc 2026-11-22 a commit\n\n"
        "### systems/x/repos/notes (main): 2 commit(s) ahead; leak check: REFUSED: 9 private-pattern line(s)\n"
        "### systems/y/repos/site (main): 0 commit(s) ahead; leak check: clean\n"
        "### not a repo line\n")
    assert D.pushes(w) == [
        {"repo": "world", "branch": "main", "ahead": 23, "leak": "clean", "clean": True},
        {"repo": "systems/x/repos/notes", "branch": "main", "ahead": 2, "leak": "REFUSED: 9 private-pattern line(s)", "clean": False}]


def test_view_shows_running_jobs_and_answering_threads_only(tmp_path):
    w = _world(tmp_path, MAP)
    v = D.view(w, [{"id": "t-1", "title": "A thread"}, {"id": "", "title": "no id"}, {"id": "t-2"}, "x"],
               [{"id": "J1", "title": "render", "thread": "t-1", "ended": None}, {"id": "J2", "title": "done", "ended": 5},
                {"id": "J3", "ended": None}, None])
    assert v["world"] is True and v["map"]["title"] == "AI engineering"
    assert v["live"]["threads"] == [{"id": "t-1", "title": "A thread"}, {"id": "t-2", "title": "a thread"}]
    assert v["live"]["jobs"] == [{"id": "J1", "title": "render", "thread": "t-1"}, {"id": "J3", "title": "J3", "thread": ""}]
    assert v["live"]["pushes"] == []
    empty = D.view(None, [], [])
    assert empty == {"map": None, "world": False, "live": {"threads": [], "jobs": [], "pushes": []}}


def test_bridge_answers_the_dashboard_route(monkeypatch, tmp_path):
    import importlib.util
    import threading
    import urllib.request
    w = _world(tmp_path, MAP)
    monkeypatch.setenv("CC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CC_HANDS_HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_WORLD_DIR", str(w))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", "tok")
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir()
    spec = importlib.util.spec_from_file_location("cc_bridge_dashboard", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/cc/dashboard",
                                     headers={"X-CC-Operator": "tok", "Sec-Fetch-Site": "same-origin"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read())
        assert d["map"]["groups"][0]["topics"][0]["name"] == "Batching"
        assert d["live"] == {"threads": [], "jobs": [], "pushes": []} and d["world"] is True
    finally:
        srv.shutdown()
