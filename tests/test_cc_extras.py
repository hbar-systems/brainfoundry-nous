"""cc_extras (scripts/cc/cc_extras.py): files roots, range serving, jobs, uploads. No network.

Run from repo root:
    pytest tests/test_cc_extras.py -v
"""
from __future__ import annotations

import importlib.util
import io
import json
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
    assert u["all"]["cost"] is None and "subscription" in u["cost_note"]
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
