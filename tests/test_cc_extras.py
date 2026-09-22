"""cc_extras (scripts/cc/cc_extras.py): files roots, range serving, jobs, uploads. No network.

Run from repo root:
    pytest tests/test_cc_extras.py -v
"""
from __future__ import annotations

import importlib.util
import io
import json
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
