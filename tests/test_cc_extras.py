"""cc_extras (scripts/cc/cc_extras.py): files roots, range serving, jobs, uploads. No network.

Run from repo root:
    pytest tests/test_cc_extras.py -v
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_extras", ROOT / "scripts" / "cc" / "cc_extras.py")
X = importlib.util.module_from_spec(spec); sys.modules["cc_extras"] = X; spec.loader.exec_module(X)


class FakeHandler:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.status = None; self.hdrs = {}; self.wfile = io.BytesIO(); self.rfile = io.BytesIO()
    def send_response(self, code): self.status = code
    def send_header(self, k, v): self.hdrs[k] = v
    def end_headers(self): pass


def test_files_roots_and_listing(tmp_path):
    out = tmp_path / "out"; out.mkdir(); (out / "a.wav").write_bytes(b"RIFF" + b"\0" * 100); (out / "notes.md").write_text("hi")
    (tmp_path / "secret").mkdir(); (tmp_path / "secret" / "x").write_text("no")
    f = X.Files({"out": str(out), "missing": str(tmp_path / "nope")})
    assert list(f.roots) == ["out"]
    d = f.listing(str(out))
    assert [e["name"] for e in d["entries"]] == ["a.wav", "notes.md"]
    assert d["entries"][0]["kind"] == "audio" and d["entries"][1]["kind"] == "text"
    assert f.listing(str(tmp_path / "secret"))["error"]
    assert f.resolve(str(out / ".." / "secret" / "x")) is None
    assert f.listing(None)["roots"][0]["label"] == "out"


def test_files_range_serving(tmp_path):
    out = tmp_path / "out"; out.mkdir(); (out / "clip.mp3").write_bytes(bytes(range(200)))
    f = X.Files({"out": str(out)})
    h = FakeHandler({"Range": "bytes=10-19"})
    f.serve(h, str(out / "clip.mp3"))
    assert h.status == 206 and h.hdrs["Content-Range"] == "bytes 10-19/200" and h.wfile.getvalue() == bytes(range(10, 20))
    h2 = FakeHandler({})
    f.serve(h2, str(out / "clip.mp3"))
    assert h2.status == 200 and h2.hdrs["Content-Type"].startswith("audio/") and len(h2.wfile.getvalue()) == 200
    h3 = FakeHandler({})
    f.serve(h3, str(tmp_path / "elsewhere"))
    assert h3.status == 404


def test_jobs_run_detached_and_finish(tmp_path):
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"})
    rec = j.start("echo hello; sleep 0.3; echo done", str(tmp_path), "say hello")
    assert rec["id"].startswith("J") and rec["ended"] is None
    for _ in range(50):
        g = j.get(rec["id"])
        if not g["running"]:
            break
        time.sleep(0.1)
    assert g["rc"] == 0 and "done" in g["tail"] and "say hello" == g["title"]
    fin = j.take_unseen()
    assert [x["id"] for x in fin] == [rec["id"]] and j.take_unseen() == []
    assert j.start("sudo ls", None)["error"]
    assert j.start("echo x | sudo tee /x", None)["error"]
    assert j.start("", None)["error"]


def test_jobs_guard_rewrites_or_refuses(tmp_path):
    """2026-10-19: the bridge's guard (cc_guard.check_job) sees every job command before it runs."""
    def guard(c):
        if "bad" in c:
            raise ValueError("refused for the test")
        return c.replace("hello", "guarded")
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"}, guard=guard)
    assert j.start("echo bad", None) == {"error": "refused for the test"}
    rec = j.start("echo hello", str(tmp_path))
    for _ in range(50):
        g = j.get(rec["id"])
        if not g["running"]:
            break
        time.sleep(0.1)
    assert "guarded" in g["tail"] and rec["command"] == "echo hello"     # the record keeps the person's words


def test_uploads_multipart(tmp_path):
    up = X.Uploads(tmp_path / "in")
    boundary = "XYZ"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"../evil name?.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\nhello\r\n--{boundary}--\r\n").encode()
    h = FakeHandler({"Content-Length": str(len(body)), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    h.rfile = io.BytesIO(body)
    d = up.save_multipart(h)
    assert d["ok"] and d["files"][0]["name"] == "evil name_.txt" and d["files"][0]["size"] == 5
    assert pathlib.Path(d["files"][0]["path"]).read_text() == "hello"
    assert "/in/" in d["files"][0]["path"]


def test_uploads_chunked_and_oversized(tmp_path, monkeypatch):
    """2026-10-14: a chunked body is read; an oversized one is read away before the refusal, so the
    proxy delivers the answer instead of a 502 on a broken pipe."""
    up = X.Uploads(tmp_path / "in")
    boundary = "XYZ"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.png\"\r\n"
            f"Content-Type: image/png\r\n\r\nPNGDATA\r\n--{boundary}--\r\n").encode()
    chunked = b"".join(b"%x\r\n%s\r\n" % (len(body[i:i + 10]), body[i:i + 10]) for i in range(0, len(body), 10)) + b"0\r\n\r\n"
    h = FakeHandler({"Transfer-Encoding": "chunked", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    h.rfile = io.BytesIO(chunked + b"NEXT")
    d = up.save_multipart(h)
    assert d["ok"] and pathlib.Path(d["files"][0]["path"]).read_bytes() == b"PNGDATA"
    assert h.rfile.read() == b"NEXT"
    monkeypatch.setattr(X, "MAX_UPLOAD", 20)
    h = FakeHandler({"Content-Length": str(len(body)), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    h.rfile = io.BytesIO(body + b"NEXT")
    assert "upload must be" in up.save_multipart(h)["error"] and h.rfile.read() == b"NEXT"
    h = FakeHandler({"Transfer-Encoding": "chunked", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    h.rfile = io.BytesIO(chunked + b"NEXT")
    assert "upload must be" in up.save_multipart(h)["error"] and h.rfile.read() == b"NEXT"


def test_recent_and_html_kind(tmp_path):
    out = tmp_path / "out"; (out / "a").mkdir(parents=True); (out / "jobs").mkdir()
    (out / "a" / "index.html").write_text("<p>hi</p>"); (out / "a" / "x.png").write_bytes(b"\x89PNG"); (out / "jobs" / "J1.log").write_text("no")
    f = X.Files({"out": str(out)})
    r = f.recent("out")
    assert [e["name"] for e in r] and "J1.log" not in [e["name"] for e in r]
    assert next(e for e in r if e["name"] == "index.html")["kind"] == "html"
    assert f.recent("nope") == []


def test_files_write_roots_secrets_and_conflict(tmp_path):
    # 2026-09-28: the person saves a text file from the Files pane; only inside world/out/in, never
    # secrets or .git, never the brain repo; a stale mtime is a conflict, not a silent overwrite.
    world = tmp_path / "world"; world.mkdir(); brain = tmp_path / "brain"; brain.mkdir()
    (world / "note.md").write_text("one"); (world / ".env").write_text("K=1"); (world / ".git").mkdir(); (world / ".git" / "config").write_text("x")
    (world / "song.wav").write_bytes(b"RIFF"); (brain / "main.py").write_text("print(1)")
    f = X.Files({"world": str(world), "brain": str(brain)})
    d = f.write(str(world / "note.md"), "two")
    assert d["ok"] and (world / "note.md").read_text() == "two" and d["mtime"] > 0
    assert f.write(str(world / "new" / "x.md"), "no")["error"].startswith("the folder")
    assert f.write(str(world / "fresh.md"), "made")["ok"] and (world / "fresh.md").read_text() == "made"
    assert "secrets" in f.write(str(world / ".env"), "K=2")["error"] and (world / ".env").read_text() == "K=1"
    assert "secrets" in f.write(str(world / ".git" / "config"), "y")["error"]
    assert "text" in f.write(str(world / "song.wav"), "y")["error"]
    assert "world, out or in" in f.write(str(brain / "main.py"), "y")["error"] and (brain / "main.py").read_text() == "print(1)"
    assert f.write(str(tmp_path / "outside.md"), "y")["error"].startswith("not a path")
    stale = f.write(str(world / "note.md"), "three", expect_mtime=1)
    assert stale.get("conflict") and (world / "note.md").read_text() == "two"
    now = int((world / "note.md").stat().st_mtime)
    assert f.write(str(world / "note.md"), "three", expect_mtime=now)["ok"] and (world / "note.md").read_text() == "three"
    assert not [x for x in world.iterdir() if x.name.startswith(".note.md.saving")]


def test_telegram_helper_pure_parts(tmp_path):
    """2026-09-29: chunks under the limit on line breaks, card buttons, update parsing, owner
    pinning, the poll offset, all against a fake api."""
    calls = []
    def fake(method, _timeout, **params):
        calls.append((method, params))
        if method == "getUpdates":
            return {"ok": True, "result": [{"update_id": 7, "message": {"message_id": 1, "chat": {"id": 42}, "text": "hi"}},
                                           {"update_id": 8, "callback_query": {"id": "cq1", "data": "allow:p1", "message": {"message_id": 2, "chat": {"id": 42}}}}]}
        return {"ok": True, "result": {}}
    tg = X.Telegram("tok", tmp_path / "tg.json", api=fake)
    assert tg.owner() is None and not tg.owner_ok(42)
    tg.pin(42)
    assert tg.owner_ok(42) and not tg.owner_ok(43) and json.loads((tmp_path / "tg.json").read_text())["owner"] == 42
    ups = tg.poll()
    assert len(ups) == 2 and tg.state()["offset"] == 9 and calls[0][1]["offset"] == 0
    a, b = X.Telegram.parse_update(ups[0]), X.Telegram.parse_update(ups[1])
    assert a["kind"] == "message" and a["text"] == "hi" and a["chat_id"] == 42 and a["file_id"] is None
    assert b["kind"] == "callback" and b["data"] == "allow:p1" and b["callback_id"] == "cq1" and b["message_id"] == 2
    v = X.Telegram.parse_update({"message": {"chat": {"id": 42}, "voice": {"file_id": "f1", "mime_type": "audio/ogg"}}})
    assert v["is_voice"] and v["file_id"] == "f1" and v["file_name"] == "voice.ogg"
    ph = X.Telegram.parse_update({"message": {"message_id": 9, "chat": {"id": 42}, "caption": "look", "photo": [{"file_id": "s", "file_size": 10}, {"file_id": "L", "file_size": 99}]}})
    assert ph["file_id"] == "L" and ph["text"] == "look" and ph["file_name"].endswith(".jpg")
    assert X.Telegram.parse_update({"my_chat_member": {}}) is None
    text = "\n".join("line %d %s" % (i, "x" * 80) for i in range(120))
    parts = X.Telegram.chunks(text, 1000)
    assert all(len(p) <= 1000 for p in parts) and "".join(p + "\n" for p in parts).replace("\n\n", "\n").strip() == text
    assert X.Telegram.chunks("") == [""]
    km = X.Telegram.card_markup("p9")
    assert km["inline_keyboard"][0][0]["callback_data"] == "allow:p9" and km["inline_keyboard"][0][1]["callback_data"] == "deny:p9"
    forced = X.Telegram("tok", tmp_path / "tg2.json", owner="77", api=fake)
    assert forced.owner() == 77 and forced.owner_ok(77) and not forced.owner_ok(42)


def test_uploads_save_bytes(tmp_path):
    u = X.Uploads(tmp_path / "in")
    p1 = u.save_bytes("a b.txt", b"one"); p2 = u.save_bytes("a b.txt", b"two")
    assert Path(p1).read_bytes() == b"one" and Path(p2).name == "a b-1.txt" and Path(p1).parent.name.count("-") == 2


def test_usage_summary_buckets(tmp_path):
    """2026-09-29: totals per period, top threads this month, per door; cost stays None on a subscription."""
    import time as _t
    now = _t.mktime(_t.strptime("2026-09-29 12:00:00", "%Y-%m-%d %H:%M:%S")) - _t.timezone
    lines = [
        json.dumps({"ts": "2026-09-29T10:00:00Z", "tok_in": 100, "tok_cached": 1000, "tok_out": 50, "ms": 2000, "brain_session": "aaaa1111", "via": "page"}),
        json.dumps({"ts": "2026-09-29T11:00:00Z", "tok_in": 200, "tok_cached": 0, "tok_out": 20, "ms": 1000, "brain_session": "bbbb2222", "via": "telegram", "error": True}),
        json.dumps({"ts": "2026-09-25T09:00:00Z", "tok_in": 10, "tok_out": 5, "brain_session": "aaaa1111"}),
        json.dumps({"ts": "2026-08-01T09:00:00Z", "tok_in": 7, "tok_out": 3, "brain_session": "old"}),
        "not json",
    ]
    u = X.usage_summary(lines, now=now, titles={"aaaa1111": "coach"})
    assert u["today"]["turns"] == 2 and u["today"]["in"] == 300 and u["today"]["out"] == 70 and u["today"]["cached"] == 1000 and u["today"]["errors"] == 1
    assert u["week"]["turns"] == 3 and u["month"]["turns"] == 3 and u["all"]["turns"] == 4
    assert u["threads"][0]["thread"] == "bbbb2222" or u["threads"][0]["thread"] == "aaaa1111"
    assert {t["thread"] for t in u["threads"]} == {"aaaa1111", "bbbb2222"} and next(t for t in u["threads"] if t["thread"] == "aaaa1111")["title"] == "coach"
    assert u["via"]["telegram"]["turns"] == 1 and u["via"]["page"]["turns"] == 2
    assert u["all"]["cost"] is None and "invoiced" in u["cost_note"]
    u2 = X.usage_summary([json.dumps({"ts": "2026-09-29T10:00:00Z", "cost": 0.25}), json.dumps({"ts": "2026-09-29T10:01:00Z", "cost": 0.5})], now=now)
    assert abs(u2["today"]["cost"] - 0.75) < 1e-9 and "USD" in u2["cost_note"]


def test_board_tiles_states_order_cards_and_links():
    """Mission control (2026-10-06): one tile per run from what the bridge tracks. Waiting on you first,
    failed pinned until dismissed, then answering, then done; cards ride on their tile; a finished
    tile carries its result line and the links its answer named; jobs and loose permits are tiles too."""
    import time as _t
    now = 1_791_300_000.0
    iso = lambda ts: _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(ts))
    threads = [
        {"brain": "aaaa1111-full", "title": "coach baseline", "last": iso(now - 600)},
        {"brain": "bbbb2222-full", "title": "video crop", "last": iso(now - 60)},
        {"brain": "cccc3333-full", "title": "storage mount", "last": iso(now - 3600)},
        {"brain": "dddd4444-full", "title": "old one", "last": iso(now - 3 * 86400)},
        {"brain": "eeee5555-full", "title": "broke yesterday", "last": iso(now - 30 * 3600)},
        {"brain": "ffff6666-full", "title": "archived", "last": iso(now - 100), "archived": True},
    ]
    runs = [
        {"run": "r1", "thread": "bbbb2222-full", "title": "video crop", "message": "crop it", "started": now - 252, "done": False, "waiting": 0,
         "steps": 6, "agents": 2, "cards": [], "last": "ran: ffmpeg -i in.mp4", "payload": None, "stopped": False},
        {"run": "r2", "thread": "aaaa1111-full", "title": "coach baseline", "message": "go", "started": now - 40, "done": False, "waiting": 1,
         "steps": 1, "agents": 0, "cards": [{"id": "PRM-1", "summary": "run on the box: git commit", "platform": "box"}], "last": "", "payload": None, "stopped": False},
        {"run": "r3", "thread": "cccc3333-full", "title": "storage mount", "message": "mount", "started": now - 3700, "done": True, "waiting": 0, "steps": 0, "agents": 0, "cards": [],
         "last": "", "payload": {"reply": "The box is mounted at /mnt/box. See https://example.org/docs and /home/hands/out/2026-10-06/mount.sh for the script.", "error": False, "ms": 91000, "meta": {"steps": 4}, "pane": {"route": "/files?path=/home/hands/out"}}, "stopped": False},
    ]
    audit = [
        json.dumps({"ts": iso(now - 700), "brain": "aaaa1111-full", "ms": 5000, "error": False, "tok_in": 100, "tok_out": 50}),
        json.dumps({"ts": iso(now - 3600), "brain_session": "cccc3333", "ms": 91000, "error": False, "tok_in": 1000, "tok_out": 500, "cost": 0.25, "via": "telegram"}),
        json.dumps({"ts": iso(now - 30 * 3600), "brain_session": "eeee5555", "ms": 1000, "error": True}),
        "not json",
    ]
    jobs = [{"id": "J1", "title": "render the cut", "started": now - 500, "ended": None, "rc": None, "log": "/home/hands/out/jobs/J1.log", "tail": "# J1\nframe 120\nframe 240\n"},
            {"id": "J2", "title": "tests", "started": now - 900, "ended": now - 800, "rc": 2, "log": "/home/hands/out/jobs/J2.log", "tail": "1 failed\n"}]
    pending = [{"id": "PRM-1", "summary": "dup of the card"}, {"id": "PRM-9", "summary": "send the email"}]
    b = X.board_tiles(runs, audit, jobs, threads, pending, set(), now, result_fn=lambda th, st: "", roots=("/home/hands/out",))
    by = {tl["key"].split(":")[0] + ":" + (tl.get("title") or ""): tl for tl in b["tiles"]}
    states = [tl["state"] for tl in b["tiles"]]
    assert states == sorted(states, key=lambda s: X.BOARD_ORDER[s])
    assert b["counts"] == {"waiting": 2, "failed": 2, "answering": 2, "done": 1}
    w = next(tl for tl in b["tiles"] if tl.get("run") == "r2")
    assert w["state"] == "waiting" and w["cards"][0]["id"] == "PRM-1" and w["href"] == "/talk?thread=aaaa1111-full" and w["tok"] == 150
    a = next(tl for tl in b["tiles"] if tl.get("run") == "r1")
    assert a["state"] == "answering" and a["elapsed_s"] == 252 and a["agents"] == 2 and a["last"].startswith("ran: ffmpeg")
    d = next(tl for tl in b["tiles"] if tl.get("thread") == "cccc3333-full")
    assert d["state"] == "done" and d["last"] == "The box is mounted at /mnt/box." and d["cost"] == 0.25 and d["via"] == "telegram"
    hrefs = [l["href"] for l in d["links"]]
    assert "/files?path=/home/hands/out" in hrefs and "https://example.org/docs" in hrefs and "/files?path=/home/hands/out/2026-10-06/mount.sh" in hrefs
    f = next(tl for tl in b["tiles"] if tl.get("thread") == "eeee5555-full")
    assert f["state"] == "failed"                       # older than a day, still pinned
    assert not any(tl.get("thread") in ("dddd4444-full", "ffff6666-full") for tl in b["tiles"])   # old and done, or archived: not shown
    j1 = next(tl for tl in b["tiles"] if tl["key"] == "job:J1"); j2 = next(tl for tl in b["tiles"] if tl["key"] == "job:J2")
    assert j1["state"] == "answering" and j1["word"] == "running" and j1["last"] == "frame 240" and j2["state"] == "failed" and j2["last"] == "1 failed"
    loose = [tl for tl in b["tiles"] if tl["kind"] == "permit"]
    assert len(loose) == 1 and loose[0]["cards"][0]["id"] == "PRM-9"          # the card already on a run is not doubled
    # dismissing the failed thread and the failed job removes them; nothing else moves
    gone = {f["key"], "job:J2"}
    b2 = X.board_tiles(runs, audit, jobs, threads, pending, gone, now, roots=("/home/hands/out",))
    assert b2["counts"]["failed"] == 0 and len(b2["tiles"]) == len(b["tiles"]) - 2
    assert X.last_sentence("First part. Then the final sentence here.\n") == "Then the final sentence here."
    assert X.first_sentence("**Done.** The rest follows.\n\nMore.") == "Done."


def test_jobs_carry_their_thread_and_are_taken_per_thread(tmp_path):
    """2026-10-11: a finished job's tile goes to the conversation whose hands started it. The
    record carries `thread` (or "unknown") and `run`; a job started before its conversation had
    an id is resolved through the run registry on finish and on every read; take_unseen(thread)
    hands over only that thread's jobs; the rest stay listed as unseen_others until their own
    page takes them, or the person dismisses them, or a day passes."""
    runs = {"r-new": None}
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"}, resolve=lambda rid: runs.get(rid))
    a = j.start("echo a", str(tmp_path), "job of A", thread="thread-A", run="r-a")
    b = j.start("echo b", str(tmp_path), "job of a new conversation", thread="unknown", run="r-new")
    c = j.start("echo c", str(tmp_path), "job of nobody", thread="", run="")
    assert a["thread"] == "thread-A" and a["run"] == "r-a"
    assert b["thread"] == "unknown" and b["run"] == "r-new"
    assert c["thread"] == "unknown" and c["run"] is None
    # get() reads the registry without the lock, so wait for the unseen set (filled last) and not for `running`
    def settled(*xs):
        for _ in range(60):
            if all(x["id"] in j.unseen for x in xs):
                return True
            time.sleep(0.1)
        return False
    assert settled(a, b, c)
    assert all(j.get(x["id"])["rc"] == 0 for x in (a, b, c))
    # the record on disk says so too
    on_disk = {r["id"]: r for r in json.loads((tmp_path / "out" / "jobs" / "jobs.json").read_text())}
    assert on_disk[a["id"]]["thread"] == "thread-A" and on_disk[b["id"]]["thread"] == "unknown"
    # page B polls with its thread: nothing of its own yet (the run has no thread), A's and the orphan are "others"
    assert j.take_unseen("thread-B") == []
    assert sorted(o["id"] for o in j.unseen_others("thread-B")) == sorted([a["id"], b["id"], c["id"]])
    # page A takes only its own; A's tile never reaches B's page
    fin = j.take_unseen("thread-A")
    assert [x["id"] for x in fin] == [a["id"]] and fin[0]["thread"] == "thread-A" and "a" in fin[0]["tail"]
    assert a["id"] not in {o["id"] for o in j.unseen_others("thread-B")}
    # the new conversation's first turn has been recorded by now: the run resolves, the job follows
    runs["r-new"] = "thread-B"
    assert j.get(b["id"])["thread"] == "thread-B" and [x["id"] for x in j.list() if x["thread"] == "thread-B"] == [b["id"]]
    assert [x["id"] for x in j.take_unseen("thread-B")] == [b["id"]]
    # the orphan belongs to nobody: every page sees it in the strip (without the log's tail) until dismissed
    others = j.unseen_others("thread-A")
    assert [o["id"] for o in others] == [c["id"]] and "tail" not in others[0] and others[0]["thread"] == "unknown"
    assert j.mark_seen(c["id"]) is True and j.mark_seen(c["id"]) is False and j.unseen_others(None) == []
    # without a thread nothing is taken by a page that cannot own a job; and old unseen ids expire
    d = j.start("echo d", str(tmp_path), "late", thread="thread-A")
    assert settled(d)
    assert j.take_unseen(None) and j.unseen_others("thread-A") == []   # the old caller shape still takes everything
    e = j.start("echo e", str(tmp_path), "stale", thread="thread-A")
    assert settled(e)
    j.UNSEEN_TTL = 0
    time.sleep(0.05)
    assert j.take_unseen("thread-A") == [] and e["id"] not in j.unseen


def test_board_lists_every_job_with_its_thread():
    """The board stays global (2026-10-11): a job tile shows whichever thread started it, None when unknown."""
    now = 1_800_000_000.0
    jobs = [{"id": "J1", "title": "mine", "started": now - 60, "ended": now - 10, "rc": 0, "log": "/o/J1.log", "thread": "t-1", "tail": "x\n"},
            {"id": "J2", "title": "orphan", "started": now - 60, "ended": None, "rc": None, "log": "/o/J2.log", "thread": "unknown", "tail": ""}]
    b = X.board_tiles([], [], jobs, [], [], set(), now)
    by = {t["key"]: t for t in b["tiles"]}
    assert by["job:J1"]["thread"] == "t-1" and by["job:J2"]["thread"] is None and len(by) == 2


def test_running_jobs_are_counted_per_thread(tmp_path):
    """2026-10-18: the second light. running_by_thread() groups the jobs still running by the
    thread that started them, resolves a new conversation's job through its run, leaves out jobs
    of no known thread and finished ones, and drops a record whose process is gone."""
    runs = {"r-new": None}
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"}, resolve=lambda rid: runs.get(rid))
    a1 = j.start("sleep 30", str(tmp_path), "long A one", thread="thread-A")
    a2 = j.start("sleep 30", str(tmp_path), "long A two", thread="thread-A")
    b = j.start("sleep 30", str(tmp_path), "long of a new one", thread="unknown", run="r-new")
    j.start("sleep 30", str(tmp_path), "long of nobody", thread="")
    q = j.start("true", str(tmp_path), "quick A", thread="thread-A")
    try:
        for _ in range(60):
            if q["id"] in j.unseen:
                break
            time.sleep(0.1)
        got = j.running_by_thread()
        assert set(got) == {"thread-A"}
        assert [x["id"] for x in got["thread-A"]] == [a1["id"], a2["id"]]
        assert got["thread-A"][0] == {"id": a1["id"], "title": "long A one", "started": a1["started"]}
        runs["r-new"] = "thread-B"
        assert [x["id"] for x in j.running_by_thread().get("thread-B", [])] == [b["id"]]
        # a record left "running" by a bridge that restarted mid-job: its pid is gone, it does not count
        reg = tmp_path / "out" / "jobs" / "jobs.json"
        items = json.loads(reg.read_text())
        items.append({"id": "Jghost", "title": "ghost", "pid": 2 ** 22 + 12345, "started": 1, "ended": None, "thread": "thread-C"})
        reg.write_text(json.dumps(items))
        assert "thread-C" not in j.running_by_thread()
    finally:
        for r in json.loads((tmp_path / "out" / "jobs" / "jobs.json").read_text()):
            if r.get("ended") is None and r["id"] != "Jghost":
                try:
                    os.killpg(r["pid"], 9)
                except OSError:
                    pass


def test_recent_sends_drops_a_copy_within_the_window_and_forgets_a_refused_one():
    """2026-10-22, issue 8: the same message within 60 s is a second press; a copy the bridge did
    not take (busy, idle) is forgotten so the page's retry through the other door goes through."""
    clock = [1000.0]
    r = X.RecentSends(60, clock=lambda: clock[0])
    assert r.seen(("t", "hello")) is None
    clock[0] += 3
    assert r.seen(("t", "hello")) == 3
    assert r.seen(("t2", "hello")) is None and r.seen(("t", "other")) is None
    r.forget(("t", "other"))
    assert r.seen(("t", "other")) is None
    clock[0] += 61
    assert r.seen(("t", "hello")) is None


def _multipart(name: str, data: bytes):
    boundary = "XYZ"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: audio/mp4\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    h = FakeHandler({"Content-Length": str(len(body)), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    h.rfile = io.BytesIO(body)
    return h


def test_uploads_same_file_within_a_minute_is_saved_once(tmp_path):
    """2026-10-22, issue 8: four presses landed New Recording 116-1-2-3-4.m4a. The same name, size and
    bytes within 60 s answer with the copy already on the box; other bytes, or later, save anew."""
    clock = [1000.0]
    up = X.Uploads(tmp_path / "in", clock=lambda: clock[0])
    a = up.save_multipart(_multipart("New Recording 116.m4a", b"take-one"))["files"][0]
    clock[0] += 3
    b = up.save_multipart(_multipart("New Recording 116.m4a", b"take-one"))["files"][0]
    assert b["path"] == a["path"] and b.get("duplicate") is True
    c = up.save_multipart(_multipart("New Recording 116.m4a", b"take-two"))["files"][0]
    assert c["path"] != a["path"]
    clock[0] += 61
    d = up.save_multipart(_multipart("New Recording 116.m4a", b"take-one"))["files"][0]
    assert d["path"] not in (a["path"], c["path"]) and not d.get("duplicate")
    assert len(list((tmp_path / "in").rglob("*.m4a"))) == 3


def test_a_job_whose_process_died_is_ended_on_read_and_closeable(tmp_path):
    """2026-10-22, issue 9: a record left running by a bridge restart (J1792407463161, 71 h). On read
    its dead pid ends it (lost, no rc), written back once; the board shows it failed, so it closes."""
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"})
    reg = tmp_path / "out" / "jobs" / "jobs.json"
    live = j.start("sleep 30", str(tmp_path), "still running", thread="t-1")
    try:
        items = json.loads(reg.read_text())
        items.append({"id": "Jghost", "title": "ghost", "pid": 2 ** 22 + 12345, "started": 1, "ended": None, "rc": None,
                      "log": str(tmp_path / "nope.log"), "thread": "t-1"})
        # a pid now held by a process that started long after the job did: reused, not the job
        items.append({"id": "Jreused", "title": "reused", "pid": os.getpid(), "started": 1, "ended": None, "rc": None,
                      "log": str(tmp_path / "nope.log"), "thread": "t-1"})
        reg.write_text(json.dumps(items))
        by = {r["id"]: r for r in j.list()}
        assert by[live["id"]]["ended"] is None
        for jid in ("Jghost", "Jreused"):
            assert by[jid]["ended"] is not None and by[jid]["rc"] is None and by[jid]["lost"] is True
        assert {r["id"]: r for r in json.loads(reg.read_text())}["Jghost"]["lost"] is True   # written back
        assert j.get("Jghost")["lost"] is True
        tiles = {t["key"]: t for t in X.board_tiles([], [], [dict(by["Jghost"], tail="")], [], [], set(), time.time())["tiles"]}
        assert tiles["job:Jghost"]["state"] == "failed" and "restart" in tiles["job:Jghost"]["last"]
        assert X.board_tiles([], [], [dict(by["Jghost"], tail="")], [], [], {"job:Jghost"}, time.time())["tiles"] == []
    finally:
        os.kill(live["pid"], 15)


def test_commit_info_finds_a_commit_and_refuses_a_non_hash(tmp_path):
    import subprocess as sp
    d = str(tmp_path)
    sp.run(["git", "init", "-q", d], check=True)
    Path(d, "a.txt").write_text("x\n")
    sp.run(["git", "-C", d, "add", "a.txt"], check=True)
    sp.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add a"], check=True)
    sha = sp.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    repos = X.commit_repos(d)
    out = X.commit_info(sha[:7], repos)
    assert out["ok"] and out["subject"] == "add a"
    assert out["files"][0]["path"] == "a.txt" and out["pushed"] is False
    assert not X.commit_info("added", repos)["ok"]
    assert not X.commit_info("abcdef0", repos)["ok"]


def test_next_rows_open_candidates_newest_first(tmp_path):
    # standing-page actions (2026-10-26): only candidates with a real id, newest first
    p = tmp_path / "next.tsv"
    head = "id\tts_utc\tthread\tagent_or_job\trepo\twhat\twhy\tcost\tstate\truled_by\tnote\n"
    p.write_text(head + "1025-aaaaaa\tt1\tth\t\tworld\tfirst\twhy1\t10 min\tcandidate\t\t\n"
                 "1025-bbbbbb\tt2\tth\t\tworld\ttaken one\tw\t\ttaken\tme\t\n"
                 "# a comment\n"
                 "1026-cccccc\tt3\tth\t\t-\tsecond\twhy2\t\tcandidate\t\t\n")
    rows = X.next_rows(p)
    assert [r["id"] for r in rows] == ["1026-cccccc", "1025-aaaaaa"]
    assert rows[1]["what"] == "first" and rows[1]["cost"] == "10 min"
    assert X.next_rows(tmp_path / "missing.tsv") == []


def test_job_report_asks_status_and_choices():
    assert X.job_report_asks("all fine\nSTATUS: done") is None
    assert X.job_report_asks("") is None
    tail = ('Two ways.\n<choices>[{"label": "Keep it private", "send": "x"}, "Publish"]</choices>\n'
            "STATUS: needs-you - pick one")
    a = X.job_report_asks(tail)
    assert a["status"] == "needs-you" and a["line"] == "pick one"
    assert a["options"] == ["Keep it private", "Publish"]
    b = X.job_report_asks("**STATUS: blocked** no key\n<choices>not json</choices>")
    assert b["status"] == "blocked" and b["options"] == []


def test_telegram_send_file_picks_the_method(tmp_path):
    """2026-11-08: a track goes as sendAudio, a picture as sendPhoto, a wav as a document; over 50 MB refuses."""
    tg = X.Telegram("tok", tmp_path / "tg.json", api=lambda *a, **k: {"ok": True})
    seen = []
    up = lambda method, field, p, fields: seen.append((method, field, p.name, fields)) or {"ok": True}
    for name in ("beat.mp3", "cover.png", "beat.wav", "clip.mp4"):
        (tmp_path / name).write_bytes(b"x" * 10)
        assert tg.send_file(42, tmp_path / name, caption="hi", upload=up)["ok"]
    assert [s[0] for s in seen] == ["sendAudio", "sendPhoto", "sendDocument", "sendVideo"]
    assert seen[0][1] == "audio" and seen[0][3] == {"chat_id": "42", "caption": "hi"}
    assert X.Telegram.file_method("big.png", 11 * 1024 * 1024) == ("sendDocument", "document")
    big = tmp_path / "big.wav"
    with open(big, "wb") as f:
        f.truncate(51 * 1024 * 1024)
    import pytest
    with pytest.raises(ValueError):
        tg.send_file(42, big, upload=up)


# ── audit 2026-11-13, cc-bridge-writes-follow-hands-planted-links ──────────────────────────────────
# The hands own out/ and in/ after the split; a link they plant must never carry a bridge write.

def _wait_job(j, jid):
    for _ in range(50):
        g = j.get(jid)
        if not g["running"]:
            return g
        time.sleep(0.1)
    return g


def test_job_log_never_follows_a_planted_link(tmp_path):
    secret = tmp_path / "bridge-env"
    secret.write_text("TOKEN=keep\n")
    jobs = tmp_path / "out" / "jobs"
    jobs.mkdir(parents=True)
    t0 = int(time.time())
    for t in range(t0, t0 + 4):                 # the next names the hands can predict
        for n in range(1, 4):
            os.symlink(secret, jobs / f"J{t}{n:03d}.log")
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"})
    rec = j.start("echo PYTHONPATH=/evil", str(tmp_path), "x")
    assert "error" not in rec
    g = _wait_job(j, rec["id"])
    assert secret.read_text() == "TOKEN=keep\n"
    assert not os.path.islink(jobs / f"{rec['id']}.log") and "PYTHONPATH=/evil" in g["tail"]


def test_jobs_registry_link_is_replaced_not_written_through(tmp_path):
    secret = tmp_path / "bridge-env"
    secret.write_text("TOKEN=keep\n")
    jobs = tmp_path / "out" / "jobs"
    jobs.mkdir(parents=True)
    os.symlink(secret, jobs / "jobs.json")
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"})
    rec = j.start("true", str(tmp_path), "x")
    _wait_job(j, rec["id"])
    assert secret.read_text() == "TOKEN=keep\n" and not os.path.islink(jobs / "jobs.json")


def test_job_get_reads_its_own_log_not_the_registry_path(tmp_path):
    secret = tmp_path / "bridge-env"
    secret.write_text("TOKEN=secret\n")
    j = X.Jobs(tmp_path / "out", lambda: {"PATH": "/usr/bin:/bin"})
    (j.dir / "jobs.json").write_text(json.dumps([{"id": "J1001", "title": "x", "pid": None, "started": 1,
                                                  "ended": 2, "rc": 0, "log": str(secret), "thread": "t"},
                                                 {"id": "../../bridge-env", "log": str(secret), "ended": 2}]))
    os.symlink(secret, j.dir / "J1001.log")
    g = j.get("J1001")
    assert "secret" not in g["tail"]
    assert j.get("../../bridge-env") is None


def test_jobs_folder_planted_as_a_link_is_refused(tmp_path):
    bridge = tmp_path / "bridge-home"
    bridge.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    j = X.Jobs(out, lambda: {"PATH": "/usr/bin:/bin"})
    os.rmdir(j.dir)
    os.symlink(bridge, j.dir)
    out.chmod(0o775)                             # a folder the hands' group shares: their link is not trusted
    try:
        rec = j.start("true", str(tmp_path), "x")
    finally:
        out.chmod(0o755)
    assert "error" in rec and list(bridge.iterdir()) == []


def test_uploads_never_create_through_a_link(tmp_path):
    target = tmp_path / "bridge-home" / "planted"
    target.parent.mkdir()
    u = X.Uploads(tmp_path / "in")
    day = tmp_path / "in" / time.strftime("%Y-%m-%d", time.gmtime())
    day.mkdir(parents=True)
    os.symlink(target, day / "voice.ogg")       # dangling: write_bytes used to create its target
    p = u.save_bytes("voice.ogg", b"data")
    assert not target.exists() and Path(p).name == "voice-1.ogg" and Path(p).read_bytes() == b"data"
    assert not os.path.islink(p) and (os.stat(p).st_mode & 0o777) == 0o664


def test_uploads_refuse_a_day_folder_planted_as_a_link(tmp_path):
    bridge = tmp_path / "bridge-home"
    bridge.mkdir()
    inn = tmp_path / "in"
    inn.mkdir()
    os.symlink(bridge, inn / time.strftime("%Y-%m-%d", time.gmtime()))
    inn.chmod(0o775)
    try:
        u = X.Uploads(inn)
        try:
            u.save_bytes("a.txt", b"x")
            raised = False
        except X.UnsafePath:
            raised = True
    finally:
        inn.chmod(0o755)
    assert raised and list(bridge.iterdir()) == []


def test_files_write_replaces_and_never_writes_through_a_link(tmp_path):
    world = tmp_path / "world"
    world.mkdir()
    secret = tmp_path / "bridge-env"
    secret.write_text("TOKEN=keep\n")
    f = X.Files({"world": world})
    # the old fixed temp name, planted: no longer used, and never followed
    os.symlink(secret, world / f".note.md.saving-{os.getpid()}")
    d = f.write(str(world / "note.md"), "hello")
    assert d["ok"] and (world / "note.md").read_text() == "hello" and secret.read_text() == "TOKEN=keep\n"
    assert (os.stat(world / "note.md").st_mode & 0o777) == 0o664
    assert not [p for p in world.iterdir() if ".saving-" in p.name and not p.is_symlink()]


def test_replace_file_helper_sets_mode_and_leaves_no_temp(tmp_path):
    fd = X.open_dir(tmp_path / "a" / "b", create=True)
    try:
        X.replace_file(fd, "x.json", b"{}", 0o664)
        X.replace_file(fd, "x.json", b"[]", 0o664)
        assert X.read_file(fd, "x.json") == b"[]"
    finally:
        os.close(fd)
    assert sorted(p.name for p in (tmp_path / "a" / "b").iterdir()) == ["x.json"]
    assert (os.stat(tmp_path / "a" / "b" / "x.json").st_mode & 0o777) == 0o664


def test_commit_info_runs_nothing_a_repo_config_names(tmp_path):
    """audit 2026-11-13: the world belongs to the hands; the bridge's git reads ignore its fsmonitor, textconv, ext diff."""
    import subprocess
    repo = tmp_path / "world"
    repo.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)
    g("init", "-q")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "a.txt").write_text("x\n")
    (repo / ".gitattributes").write_text("*.txt diff=evil\n")
    g("add", "."); g("commit", "-qm", "one")
    marker = tmp_path / "ran"
    for k in ("core.fsmonitor", "diff.evil.textconv", "diff.external", "core.pager"):
        g("config", k, f"touch {marker}; cat")
    sha = g("rev-parse", "HEAD").stdout.strip()
    d = X.commit_info(sha, [repo])
    assert d and not marker.exists()


def _wait_end(j, jid):
    """Until the job has ended and its result is stored on the record (the step after its end)."""
    for _ in range(80):
        rec = next(r for r in json.loads(j.reg.read_text()) if r["id"] == jid)
        if rec.get("result"):
            return j.get(jid)
        time.sleep(0.1)
    raise AssertionError("job did not end")


def test_job_result_from_a_redirected_file(tmp_path):
    """JOBCARD-1 (2026-11-13): a claude job sends its answer to out/<date>/<tag>.out; on finish the bridge
    copies it into the log under RESULT_MARK, stores the result on the record (text without the CLI's
    settings warning, rc, measured seconds, files), and `full` reads past the stored cut."""
    out = tmp_path / "out"
    day = out / time.strftime("%Y-%m-%d", time.gmtime())
    day.mkdir(parents=True)
    assert X.job_redirect(f"claude -p 'x' > {day}/t.out 2>&1", out) == (day / "t.out").resolve()
    assert X.job_redirect("echo a > /etc/x", out) is None                       # outside out/
    assert X.job_redirect(f"echo a > {day}/a.out; echo b > {day}/b.out", out) is None   # two: no guess
    assert X.job_redirect("make 2>/dev/null >&2", out) is None
    j = X.Jobs(out, lambda: {"PATH": "/usr/bin:/bin"})
    long = "x" * (X.RESULT_CHARS + 50)
    cmd = (f"mkdir -p {day}/t && touch {day}/t/shot.png && "
           f"(echo 'Permission allow rule (.claude/settings.json): Bash(x *) has a wildcard'; "
           f"echo '**Done.** the page is live'; echo {long}) > {day}/t.out 2>&1")
    g = _wait_end(j, j.start(cmd, str(tmp_path), "T-1 world: test")["id"])
    r = g["result"]
    assert r["text"].startswith("**Done.** the page is live") and r["more"] and r["text"].endswith("…")
    assert r["rc"] == 0 and r["secs"] is not None and r["source"] == str((day / "t.out").resolve())
    assert [f["name"] for f in r["files"]] == ["shot.png"] and r["files"][0]["kind"] == "image"
    log = Path(g["log"]).read_text()
    assert X.RESULT_MARK in log and "the page is live" in log                  # the log holds the answer itself
    stored = json.loads((out / "jobs" / "jobs.json").read_text())[0]["result"]
    assert stored["text"] == r["text"]                                          # kept on the record at the end
    (day / "t.out").unlink()                                                    # swept: the log still answers
    full = j.get(g["id"], full=True)["result"]
    assert not full["more"] and full["text"].endswith(long)


def test_job_result_from_a_plain_log(tmp_path):
    """No redirect: the log is the result, without cc-job's two header lines; progress rewritten with \\r
    keeps its last state; a long log keeps its end; a failed job carries its rc."""
    out = tmp_path / "out"
    j = X.Jobs(out, lambda: {"PATH": "/usr/bin:/bin"})
    g = _wait_end(j, j.start("printf '10%%\\r50%%\\r100%%\\n'; echo stems written; exit 3", str(tmp_path))["id"])
    r = g["result"]
    assert r["text"] == "100%\nstems written" and r["rc"] == 3 and r["files"] == []
    assert r["source"] == g["log"]
    rec = {"log": str(tmp_path / "l.log"), "command": "x", "started": 1, "ended": 2, "rc": 0}
    Path(rec["log"]).write_text("# J1 t in /\n# x\n" + "a\n" * 2000 + "THE END\n")
    r = X.job_result(rec, out)
    assert r["more"] and r["text"].startswith("…") and r["text"].endswith("THE END")


def test_job_files_window_own_folder_images_first(tmp_path):
    """Files the job made: written under out/<date>/ between its start and end, only its own folder when it
    wrote there, images first, newest after; outside the window, dot files, the excluded and more than six stay out."""
    out = tmp_path / "out"
    t0 = time.time()
    day = out / time.strftime("%Y-%m-%d", time.gmtime(t0))
    (day / "tag").mkdir(parents=True)
    (day / "other").mkdir()

    def put(p, age):
        p.write_text("x")
        os.utime(p, (t0 - age, t0 - age))
    put(day / "other" / "a.png", 10)
    put(day / "other" / "notes.md", 5)
    put(day / "tag" / "report.html", 20)
    put(day / "tag" / "pic.png", 30)
    put(day / "old.png", 4000)                     # before the job started
    put(day / ".hidden.png", 10)
    put(day / "else.out", 10)                      # another job's result file
    for i in range(6):
        put(day / "other" / f"n{i}.txt", 40 + i)
    fs = X.job_files(t0 - 100, t0, out, prefer="tag", exclude={str(day / "else.out")})
    assert [f["name"] for f in fs] == ["pic.png", "report.html"]   # it wrote in its own folder: only that, image first
    names = [f["name"] for f in X.job_files(t0 - 100, t0, out, prefer="none", exclude={str(day / "else.out")})]
    assert names[:2] == ["a.png", "pic.png"] and names[2] == "notes.md" and len(names) == 6   # no folder: the window
    assert not {"old.png", ".hidden.png", "else.out"} & set(names)


def test_job_result_reads_only_its_own_log_and_desk_files(tmp_path):
    # audit 2026-11-13 merge: the registry is hands-writable, so a record naming another file as its log
    # or its redirect never makes the bridge read that file into a job result.
    out = tmp_path / "out"; out.mkdir()
    secret = tmp_path / "bridge-env"; secret.write_text("CC_SECRET_LINE=1\n")
    j = X.Jobs(out, lambda: {})
    rec = {"id": "J1700000000001", "log": str(secret), "out_file": str(secret),
           "command": "echo hi", "started": 1700000000, "ended": 1700000001, "rc": 0}
    r = j.result(rec)
    assert "CC_SECRET_LINE" not in (r or {}).get("text", "")
    (j.dir / "J1700000000001.log").symlink_to(secret)        # a planted link where the log belongs
    r = j.result(rec)
    assert "CC_SECRET_LINE" not in (r or {}).get("text", "")
    (j.dir / "J1700000000001.log").unlink()
    (j.dir / "J1700000000001.log").write_text("# J1 t\n# echo hi\nhello\n")
    assert "hello" in j.result(rec)["text"]
