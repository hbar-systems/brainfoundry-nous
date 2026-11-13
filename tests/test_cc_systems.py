"""The systems board (BOARD-3, 2026-11-12): the standing-thread map, the tile data and the bridge's endpoints.

Run from repo root:
    pytest tests/test_cc_systems.py -v
No network beyond 127.0.0.1, no reasoner (a fake CLI where a turn runs), no brain api (a stub).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_systems  # noqa: E402

TID = "11111111-2222-3333-4444-555555555555"
TID2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------- the map ----

def test_map_creates_once_and_reuses(tmp_path):
    tm = cc_systems.ThreadMap(tmp_path / "state" / "systems-threads.json")
    calls = []
    make = lambda s: calls.append(s) or TID   # noqa: E731
    assert tm.resolve("hbar.music", make) == (TID, True)
    assert tm.resolve("hbar.music", make) == (TID, False)
    assert tm.resolve("hbar.music", lambda s: TID2) == (TID, False)   # never a second thread
    assert calls == ["hbar.music"]
    assert tm.get("hbar.music") == TID and tm.threads() == {"hbar.music": TID}


def test_map_is_persisted_and_atomic(tmp_path):
    p = tmp_path / "systems-threads.json"
    cc_systems.ThreadMap(p).resolve("world", lambda s: TID)
    d = json.loads(p.read_text())
    assert d["systems"]["world"]["thread"] == TID and d["systems"]["world"]["via"] == "bridge"
    # a new process (a restart) sees the same map and does not create
    again = cc_systems.ThreadMap(p)
    assert again.resolve("world", lambda s: (_ for _ in ()).throw(AssertionError("created again"))) == (TID, False)
    assert not [x for x in p.parent.iterdir() if x.name.endswith(".tmp")]   # no leftovers from the tmp + replace


def test_map_failed_create_writes_nothing(tmp_path):
    p = tmp_path / "m.json"
    tm = cc_systems.ThreadMap(p)
    assert tm.resolve("world", lambda s: None) == (None, False)
    assert tm.threads() == {}
    assert tm.resolve("world", lambda s: TID) == (TID, True)


def test_map_concurrent_sends_make_one_thread(tmp_path):
    p = tmp_path / "m.json"
    made, out = [], []
    lock = threading.Lock()

    def make(s):
        time.sleep(0.05)   # the brain api takes a moment; others arrive meanwhile
        with lock:
            made.append(s)
            return f"{len(made):08d}-0000-0000-0000-000000000000"

    def go():
        # each sender with its own map object, as two bridge processes would be (flock), or one (lock)
        out.append(cc_systems.ThreadMap(p).resolve("hbar.music", make)[0])

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(made) == 1 and len(set(out)) == 1 and out[0].startswith("00000001")


def test_map_adopts_the_static_boards_seed_once(tmp_path):
    seed = tmp_path / "board-threads.json"
    seed.write_text(json.dumps({"hbar.music": TID2, "world": "not-a-thread"}))
    tm = cc_systems.ThreadMap(tmp_path / "m.json", seed=seed)
    assert tm.resolve("hbar.music", lambda s: TID, exists=lambda t: True) == (TID2, False)
    assert tm.get("hbar.music") == TID2
    assert tm.resolve("world", lambda s: TID, exists=lambda t: True) == (TID, True)   # a bad seed id is ignored
    # a seed thread the box does not know is not adopted
    seed.write_text(json.dumps({"self": TID2}))
    assert tm.resolve("self", lambda s: TID, exists=lambda t: False) == (TID, True)


def test_map_keep_fields_are_saved(tmp_path):
    tm = cc_systems.ThreadMap(tmp_path / "m.json")
    tm.resolve("world", lambda s: TID)
    tm.resolve("world", lambda s: None, keep=lambda s, e: {"claude": "s7", "title": "CC: world: standing thread"})
    assert tm.load()["world"]["keep"] == {"claude": "s7", "title": "CC: world: standing thread"}


# ---------------------------------------------------------------- the tiles ----

def _world(tmp_path):
    w = tmp_path / "world"
    (w / "registry").mkdir(parents=True)
    (w / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.music", "status": "active", "description": "music"},
        {"id": "brainfoundry", "status": "active", "description": "brains"},
        {"id": "hbar.blog", "status": "forming", "description": "blog"}]}))
    (w / "ops" / "inbox").mkdir(parents=True)
    (w / "ops" / "inbox" / "rulings.tsv").write_text(
        "key\tref\tlane\tkind\ttitle\task\toptions\tdid\tundo\tstate\n# a comment\n"
        f"R1\t{TID}\thbar\tquestion\tWhich hbar.music master goes out first tonight please\tpick\ta => b\t\t\topen\n"
        "R2\t-\thbar\tdecision\tsomething done\task\t\t\t\tclosed\n")
    (w / "ops" / "chop").mkdir(parents=True)
    now = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)
    thoughts = [{"text": f"brainfoundry idea number {i} with many extra words here", "system": "brainfoundry",
                 "kind": "idea" if i % 2 else "question", "importance": i % 4, "thread": TID2,
                 "ts": f"2026-11-1{1 if i > 3 else 2}T1{i}:00:00Z"} for i in range(10)]
    thoughts.append({"text": "a stray", "system": "no.such", "kind": "fact", "importance": 1, "ts": "2026-11-12T10:00:00Z"})
    (w / "ops" / "chop" / "2026-11-12.json").write_text(json.dumps({"thoughts": thoughts}))
    (w / "ops" / "next.tsv").write_text("id\tts_utc\tthread\tagent_or_job\trepo\twhat\twhy\tcost\tstate\n"
                                        "N1\t2026-11-12T09:00Z\t-\tx\tsystems/hbar.blog/repos/site\tship the post\twhy\t1 h\tcandidate\n")
    return w, now


def test_board_tiles_numbers_lines_and_groups(tmp_path):
    w, now = _world(tmp_path)
    jobs = [{"id": "J1", "title": "MUSIC-1 hbar.music: render the stems", "started": int(now.timestamp()) - 60, "ended": None,
             "thread": TID, "log": "/home/hands/out/jobs/J1.log"},
            {"id": "J2", "title": "X: old work", "started": 1, "ended": 2, "log": "/home/hands/out/jobs/J2.json"}]
    d = cc_systems.board(w, jobs, {"hbar.music": TID}, now=now)
    t = {x["id"]: x for x in d["tiles"]}
    assert set(t) >= {"hbar.music", "brainfoundry", "hbar.blog", "world", "self", "unfiled"}
    # moving = running jobs + open court + thoughts of the last 24 h
    assert t["hbar.music"]["moving"] == 2 and t["hbar.music"]["thread"] == TID
    assert t["brainfoundry"]["moving"] == 4   # i = 0..3 are on the 12th, after 20:00 minus 24 h
    assert d["tiles"][0]["id"] in ("brainfoundry", "hbar.music")   # ordered by moving
    bf = t["brainfoundry"]
    assert len(bf["lines"]) == 7 and bf["extra"] == 3
    assert sum(g["count"] for g in bf["more"]) == 3 and [g["kind"] for g in bf["more"]] == sorted(
        [g["kind"] for g in bf["more"]], key=cc_systems.GROUPS.index)
    for g in bf["more"]:
        keys = [(x["importance"], x["ts"]) for x in g["lines"]]
        assert keys == sorted(keys, reverse=True)
    for tile in d["tiles"]:
        for ln in tile["lines"] + [x for g in tile["more"] for x in g["lines"]]:
            assert len(ln["text"].replace("...", "").split()) <= 8
            assert ".json" not in ln["href"]
    assert t["unfiled"]["total"] == 1
    assert t["hbar.blog"]["lines"][0]["text"] == "ship the post"   # filed by its repo path
    assert t["world"]["lines"][0]["href"] == ""   # the job whose only link was a .json lost the link, kept the words


def test_board_counts_live_agents_and_detail(tmp_path):
    """BOARD-4: four numbers per tile; running and done today live from the job list; the detail behind each."""
    w, now = _world(tmp_path)
    (w / "ops" / "jobs" / "briefs").mkdir(parents=True)
    (w / "ops" / "jobs" / "briefs" / "x-1.md").write_text("# X-1\nWork on hbar.blog, then brainfoundry.\n")
    t = int(now.timestamp())
    jobs = [{"id": "J1", "title": "MUSIC-1 hbar.music: render", "started": t - 60, "ended": None},
            {"id": "J2", "title": "MUSIC-2 hbar.music: mix", "started": t - 600, "ended": t - 300},          # done today
            {"id": "J3", "title": "MUSIC-0 hbar.music: old", "started": t - 3 * 86400, "ended": t - 3 * 86400 + 5},
            {"id": "J4", "title": "X-1 Clerk: unnamed work", "started": t - 30, "ended": None,
             "command": 'claude -p "Read /home/x/world/ops/jobs/briefs/x-1.md and carry it out"'},
            {"id": "J5", "title": "Z-1 nothing named", "started": t - 30, "ended": None, "system": "brainfoundry"}]
    d = cc_systems.board(w, jobs, {}, now=now)
    tl = {x["id"]: x for x in d["tiles"]}
    assert tl["hbar.music"]["counts"] == {"running": 1, "done_today": 1, "tasks": 1, "next": 0}
    assert tl["hbar.blog"]["counts"]["running"] == 1        # filed by its brief
    assert tl["hbar.blog"]["counts"]["next"] == 1
    assert tl["brainfoundry"]["counts"]["running"] == 1     # an explicit system field wins
    assert d["running"] == 3 and d["source"] == "world"
    assert d["tiles"][0]["counts"]["running"] >= 1          # agents running sort first
    det = tl["hbar.music"]["detail"]
    assert det["running"]["lines"][0]["run"] and det["done_today"]["count"] == 1
    assert det["tasks"]["lines"][0]["group"] == "questions"   # the open court item is his task
    bf = tl["brainfoundry"]["detail"]["tasks"]
    assert bf["count"] == 0                                 # ideas and questions of the chopper are not tasks


def test_done_job_line_carries_its_result(tmp_path):
    """JOBCARD-1: a done job's line shows the first sentence of its result, the result file and the files it
    made as pane links (a json file never); a running job has none."""
    w, now = _world(tmp_path)
    t = int(now.timestamp())
    res = {"text": "**Built.** The page is live at /systems. More after.", "rc": 0, "secs": 300,
           "source": "/home/hands/out/d/m.out",
           "files": [{"name": "shot.png", "path": "/home/hands/out/d/m/shot.png", "kind": "image"},
                     {"name": "state.json", "path": "/home/hands/out/d/m/state.json", "kind": "text"}]}
    jobs = [{"id": "J2", "title": "MUSIC-2 hbar.music: mix", "started": t - 600, "ended": t - 300, "rc": 0, "result": res},
            {"id": "J1", "title": "MUSIC-1 hbar.music: render", "started": t - 60, "ended": None}]
    tl = {x["id"]: x for x in cc_systems.board(w, jobs, {}, now=now)["tiles"]}
    done = tl["hbar.music"]["detail"]["done_today"]["lines"][0]["result"]
    assert done["first"] == "Built." and done["href"] == "/files?path=/home/hands/out/d/m.out"
    assert done["files"] == [{"name": "shot.png", "href": "/files?path=/home/hands/out/d/m/shot.png", "image": True}]
    assert "result" not in tl["hbar.music"]["detail"]["running"]["lines"][0]


def test_board_reads_the_static_board_as_data(tmp_path):
    """BOARD-4: board.json (scripts/board.py) is the source of court, thoughts and next, and of job filing."""
    w, now = _world(tmp_path)
    static = {"built": "2026-11-12 19:50:00Z", "job_system": {"J9": "hbar.blog"},
              "court": [{"id": "R7", "kind": "decision", "title": "pick the cover", "thread": TID, "system": "hbar.music"}],
              "thoughts": [{"text": "call the mastering engineer", "kind": "task-for-him", "importance": 2,
                            "ts": "2026-11-12T19:00:00Z", "thread": "", "system": "hbar.music"}],
              "next": [{"id": "N9", "what": "write the post", "ts": "2026-11-12T09:00Z", "repo": "", "thread": None,
                        "system": "hbar.blog"}]}
    jobs = [{"id": "J9", "title": "Q-1 something", "started": int(now.timestamp()) - 9, "ended": None}]
    d = cc_systems.board(w, jobs, {}, now=now, static=static)
    tl = {x["id"]: x for x in d["tiles"]}
    assert d["source"] == "board.json" and d["static_built"] == "2026-11-12 19:50:00Z"
    assert tl["hbar.music"]["counts"]["tasks"] == 2          # the court item and the task thought, not the world's files
    assert tl["hbar.blog"]["counts"] == {"running": 1, "done_today": 0, "tasks": 0, "next": 1}
    assert tl["brainfoundry"]["counts"]["tasks"] == 0 and tl["brainfoundry"]["moving"] == 0
    # load_static: absent -> None; re-read only when the mtime moves
    p = tmp_path / "board.json"
    assert cc_systems.load_static(p) is None
    p.write_text(json.dumps(static))
    cache = {}
    assert cc_systems.load_static(p, cache)["built"] == static["built"]
    cache["data"] = {"cached": True}
    assert cc_systems.load_static(p, cache) == {"cached": True}
    p.write_text("not json")
    assert cc_systems.load_static(tmp_path / "nope.json", cache) is None


def test_board_without_world_has_the_three_extra_tiles(tmp_path):
    d = cc_systems.board(None, [], {})
    assert [x["id"] for x in d["tiles"]] == ["self", "world"]   # unfiled shows only when it holds something


def test_phrase_and_voice_name():
    assert cc_systems.phrase('BOARD-3 "Quartermaster III": one two three four five six seven') == "Quartermaster III: one two three four five six..."
    assert cc_systems.voice_name("hbar.music", "clip.webm", now=0) == "memo_hbar.music_19700101T000000Z.webm"
    assert cc_systems.voice_name("world", "clip.exe", now=0).endswith(".webm")


# ---------------------------------------------------------------- the bridge ----

def _bridge(monkeypatch, tmp_path, token=""):
    fake = tmp_path / "fake-claude"
    fake.write_text('''#!/usr/bin/env python3
import json
def p(o): print(json.dumps(o), flush=True)
p({"type": "system", "subtype": "init", "model": "claude-x", "session_id": "s9"})
p({"type": "result", "result": "noted on the music line", "session_id": "s9", "is_error": False, "num_turns": 1, "usage": {"input_tokens": 1, "output_tokens": 1}, "modelUsage": {}})
''')
    fake.chmod(0o755)
    w, _ = _world(tmp_path)
    monkeypatch.setenv("CC_BIN", str(fake))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_WORLD_DIR", str(w))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge_systems", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    made = []

    def api(method, path, body=None):
        if method == "POST" and path == "/sessions":
            made.append(body)
            return {"session_id": TID}
        return {}
    monkeypatch.setattr(m, "_brain_api", api)
    monkeypatch.setattr(m, "UPLOADS", m.cc_extras.Uploads(tmp_path / "in"))
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/cc"
    return m, srv, base, made


def _call(url, body=None, headers=None, ctype="application/json"):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_endpoints_thread_once_then_chat_lands_in_it(monkeypatch, tmp_path):
    m, srv, base, made = _bridge(monkeypatch, tmp_path)
    try:
        st, d = _call(base + "/systems")
        assert st == 200 and d["world"] is True and {"hbar.music", "world"} <= {t["id"] for t in d["tiles"]}
        assert all(t["thread"] is None for t in d["tiles"])
        st, d = _call(base + "/systems/thread", {"system": "hbar.music"})
        assert st == 200 and d == {"ok": True, "system": "hbar.music", "thread": TID, "created": True}
        st, d = _call(base + "/systems/thread", {"system": "hbar.music"})
        assert st == 200 and d["thread"] == TID and d["created"] is False
        assert len(made) == 1 and made[0]["title"] == "CC: hbar.music: standing thread"
        assert json.loads((tmp_path / ".cc-bridge" / "systems-threads.json").read_text())["systems"]["hbar.music"]["thread"] == TID
        assert any(x["brain"] == TID and x["system"] == "hbar.music" for x in m._threads_load())
        st, d = _call(base + "/systems")
        assert {t["id"]: t["thread"] for t in d["tiles"]}["hbar.music"] == TID
        # the page then makes the chat page's own call into that thread
        box_before = m._load_state()
        st, d = _call(base + "/chat", {"message": "a note for music", "new": False, "thread": TID, "stream": False, "queue": True})
        assert st == 200 and d["thread"] == TID and d["reply"] == "noted on the music line"
        assert m._load_state() == box_before   # the box's current thread did not move
        assert next(x for x in m._threads_load() if x["brain"] == TID)["claude"] == "s9"
        _call(base + "/systems")   # the board's poll keeps the thread's seat ids beside the map entry
        # the list dropped the thread (it keeps 200): the map brings it back, never a new one
        m._threads_save([])
        st, d = _call(base + "/systems/thread", {"system": "hbar.music"})
        assert d["thread"] == TID and d["created"] is False and len(made) == 1
        assert next(x for x in m._threads_load() if x["brain"] == TID)["claude"] == "s9"
        # unknown systems are refused
        st, d = _call(base + "/systems/thread", {"system": "no.such"})
        assert st == 400
    finally:
        srv.shutdown()


def test_endpoint_takes_the_static_board_when_there(monkeypatch, tmp_path):
    m, srv, base, made = _bridge(monkeypatch, tmp_path)
    try:
        st, d = _call(base + "/systems")
        assert st == 200 and d["source"] == "world" and all("counts" in t and "detail" in t for t in d["tiles"])
        (tmp_path / "board.json").write_text(json.dumps({"built": "b1", "court": [], "thoughts": [], "job_system": {},
                                                         "next": [{"what": "from the static board", "system": "self"}]}))
        st, d = _call(base + "/systems")
        tl = {t["id"]: t for t in d["tiles"]}
        assert d["source"] == "board.json" and d["static_built"] == "b1"
        assert tl["self"]["counts"]["next"] == 1 and tl["hbar.music"]["counts"]["tasks"] == 0
    finally:
        srv.shutdown()


def test_endpoints_brain_down_creates_nothing(monkeypatch, tmp_path):
    m, srv, base, made = _bridge(monkeypatch, tmp_path)
    monkeypatch.setattr(m, "_brain_api", lambda *a, **k: None)
    try:
        st, d = _call(base + "/systems/thread", {"system": "world"})
        assert st == 502 and m.SYSTEMS_THREADS.threads() == {}
    finally:
        srv.shutdown()


def test_voice_is_kept_as_a_memo_for_the_system(monkeypatch, tmp_path):
    m, srv, base, made = _bridge(monkeypatch, tmp_path)
    body, ctype = m._multipart_encode({}, "file", "clip.webm", b"OggS-fake-audio", "audio/webm")
    try:
        st, d = _call(base + "/systems/voice?system=hbar.music", body, ctype=ctype)
        assert st == 200 and d["ok"] and d["system"] == "hbar.music"
        p = pathlib.Path(d["path"])
        assert p.parent.parent == tmp_path / "in" and p.name.startswith("memo_hbar.music_") and p.suffix == ".webm"
        assert p.read_bytes() == b"OggS-fake-audio"
        side = json.loads(pathlib.Path(d["path"] + ".system.json").read_text())
        assert side["system"] == "hbar.music" and side["via"] == "systems"
        assert _call(base + "/systems/voice?system=no.such", body, ctype=ctype)[0] == 400
        assert _call(base + "/systems/voice?system=world", b"x", ctype="text/plain")[0] == 400
    finally:
        srv.shutdown()


def test_endpoints_need_the_operator_token(monkeypatch, tmp_path):
    m, srv, base, made = _bridge(monkeypatch, tmp_path, token="tok")
    try:
        assert _call(base + "/systems")[0] == 403
        assert _call(base + "/systems/thread", {"system": "world"})[0] == 403
        assert _call(base + "/systems", headers={"X-CC-Operator": "tok"})[0] == 200
        # an app frame inside the console is refused even with the token
        assert _call(base + "/systems/thread", {"system": "world"}, headers={"X-CC-Operator": "tok", "Origin": "null"})[0] == 403
        assert made == []
    finally:
        srv.shutdown()
