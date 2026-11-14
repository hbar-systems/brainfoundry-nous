"""The memo tape as a console page (TAPE-2, 2026-11-14): scripts/cc/cc_tape.py and the bridge's /cc/tape routes.
Route scoping (nothing outside the tape folder, only the page's own files written), the page gate (operator token,
app frames refused), byte ranges for the audio, and a talk-through take assembled from slices uploaded through the
console's /cc/upload with the slice list written through /cc/tape/write."""
import importlib.util
import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_tape  # noqa: E402


def _tape(tmp_path):
    root = tmp_path / "in" / "memos"
    (root / "m1" / "dispatch").mkdir(parents=True)
    (root / "index.json").write_text('{"memos": [{"id": "m1"}]}\n')
    (root / "m1" / "bits.json").write_text('{"id": "m1", "bits": []}\n')
    (root / "m1" / "source.m4a").write_bytes(bytes(range(256)) * 4)
    (root / "m1" / "page.html").write_text("<script>alert(1)</script>")
    (root / ".lock").write_text("")
    (tmp_path / "outside.json").write_text('{"secret": 1}')
    return cc_tape.Tape(root, signer="ana"), root


def test_no_tape_says_so(tmp_path):
    assert cc_tape.Tape(tmp_path / "nothing").state() == {"tape": False}
    (tmp_path / "empty").mkdir()
    assert cc_tape.Tape(tmp_path / "empty").state() == {"tape": False}   # a folder without index.json is no tape


def test_state_names_the_folder(tmp_path):
    t, root = _tape(tmp_path)
    assert t.state() == {"tape": True, "dir": str(root.resolve()), "vocab": False, "signer": "ana"}
    (root / "vocab.json").write_text("{}")
    assert t.state()["vocab"] is True


@pytest.mark.parametrize("raw", ["index.json", "m1/bits.json", "m1/source.m4a"])
def test_reads_inside_the_folder(tmp_path, raw):
    t, root = _tape(tmp_path)
    assert t.readable(raw)[0] == (root / raw).resolve()
    assert t.readable(str(root / raw))[0] == (root / raw).resolve()     # the absolute spelling too


def test_reads_nothing_outside_or_hidden_or_runnable(tmp_path):
    t, root = _tape(tmp_path)
    (root / "m1" / "link.json").symlink_to(tmp_path / "outside.json")
    for raw in ["../outside.json", str(tmp_path / "outside.json"), "m1/../../outside.json", "m1/link.json",
                ".lock", "m1/page.html", "/etc/passwd", "", None, "m1/\x00bits.json", "m1"]:
        assert t.readable(raw)[0] is None, raw
    assert t.stat("../outside.json")["ok"] is False


def test_writes_only_the_pages_own_files(tmp_path):
    t, root = _tape(tmp_path)
    ok = ["m1/bits.json", "m1/dispatch/bit-03.reply-1.md", "inbox/talk-20261114-002728-ab12.rec.json",
          "inbox/x.webm.take.txt", "inbox/text-1763080000.txt", str(root / "m1" / "bits.json")]
    for raw in ok:
        assert t.writable(raw)[0] is not None, raw
    bad = ["index.json", "board.json", "vocab.json", "seen.json", "m1/source.m4a", "m1/transcript.json",
           "inbox/evil.sh", "inbox/talk-x.rec.json/../../index.json", "../outside.json", "m1/.bits.json",
           "inbox/../m1/waveform.json", "m1/dispatch/notes.md", str(tmp_path / "outside.json")]
    for raw in bad:
        assert t.writable(raw)[0] is None, raw
        assert t.write(raw, "x")["ok"] is False


def test_write_conflict_and_inbox_made(tmp_path):
    t, root = _tape(tmp_path)
    mt = t.stat("m1/bits.json")["mtime"]
    d = t.write("m1/bits.json", '{"id": "m1", "bits": [1]}\n', mt)
    assert d["ok"] and json.loads((root / "m1" / "bits.json").read_text())["bits"] == [1]
    os.utime(root / "m1" / "bits.json", (mt + 50, mt + 50))
    d = t.write("m1/bits.json", "{}", mt)
    assert d["ok"] is False and d["conflict"] is True
    assert not (root / "inbox").exists()
    assert t.write("inbox/talk-a1.rec.json", '{"parts": []}')["ok"]          # the inbox is made on first use
    assert (root / "inbox" / "talk-a1.rec.json").stat().st_mode & 0o777 == 0o664
    assert t.write("m1/nope/bit-01.reply-1.md", "x")["ok"] is False
    assert t.write("m1/bits.json", None)["ok"] is False


# ---- the bridge's routes ----

def _bridge(monkeypatch, tmp_path, token="tok"):
    t, root = _tape(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_HANDS_HOME", str(tmp_path))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_TAPE_SIGNER", "ana")
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("CC_TAPE_DIR", raising=False)
    monkeypatch.delenv("CC_WORLD_DIR", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge_tape", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "UPLOADS", m.cc_extras.Uploads(tmp_path / "in"))
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return m, srv, f"http://127.0.0.1:{srv.server_address[1]}/cc", root


def _call(url, body=None, headers=None, ctype="application/json", raw=False):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            return r.status, (b, dict(r.headers)) if raw else json.loads(b)
    except urllib.error.HTTPError as e:
        b = e.read() or b"{}"
        return e.code, (b, dict(e.headers)) if raw else json.loads(b)


OP = {"X-CC-Operator": "tok"}


def test_routes_read_and_write_the_tape(monkeypatch, tmp_path):
    m, srv, base, root = _bridge(monkeypatch, tmp_path)
    try:
        st, d = _call(base + "/tape", headers=OP)
        assert st == 200 and d["tape"] is True and d["dir"] == str(root.resolve()) and d["signer"] == "ana"
        st, d = _call(base + "/tape/file?path=index.json", headers=OP)
        assert st == 200 and d["memos"][0]["id"] == "m1"
        st, d = _call(base + "/tape/stat?path=m1/bits.json", headers=OP)
        assert st == 200 and d["ok"] and isinstance(d["mtime"], int)
        st, d = _call(base + "/tape/write", {"path": str(root / "m1" / "bits.json"), "text": '{"id":"m1","bits":[2]}', "mtime": d["mtime"]}, headers=OP)
        assert st == 200 and d["ok"]
        st, d = _call(base + "/tape/write", {"path": "m1/bits.json", "text": "{}", "mtime": 1}, headers=OP)
        assert st == 409 and d["conflict"]
        # outside the folder, or a file the page does not write: refused
        assert _call(base + "/tape/file?path=../outside.json", headers=OP)[0] == 404
        assert _call(base + "/tape/file?path=" + str(tmp_path / "outside.json"), headers=OP)[0] == 404
        assert _call(base + "/tape/file?path=m1/page.html", headers=OP)[0] == 404
        assert _call(base + "/tape/stat?path=../outside.json", headers=OP)[0] == 404
        assert _call(base + "/tape/write", {"path": "index.json", "text": "{}"}, headers=OP)[0] == 400
        assert _call(base + "/tape/write", {"path": "../outside.json", "text": "{}"}, headers=OP)[0] == 400
        assert json.loads((tmp_path / "outside.json").read_text()) == {"secret": 1}
        assert json.loads((root / "index.json").read_text())["memos"][0]["id"] == "m1"
    finally:
        srv.shutdown()


def test_audio_comes_in_byte_ranges(monkeypatch, tmp_path):
    m, srv, base, root = _bridge(monkeypatch, tmp_path)
    try:
        st, (b, h) = _call(base + "/tape/file?path=m1/source.m4a", headers={**OP, "Range": "bytes=10-19"}, raw=True)
        assert st == 206 and b == bytes(range(10, 20)) and h["Content-Range"] == "bytes 10-19/1024"
        assert h["Accept-Ranges"] == "bytes" and h["Content-Type"].startswith("audio/")
    finally:
        srv.shutdown()


def test_routes_need_the_console_session(monkeypatch, tmp_path):
    m, srv, base, root = _bridge(monkeypatch, tmp_path)
    try:
        assert _call(base + "/tape")[0] == 403
        assert _call(base + "/tape/file?path=index.json")[0] == 403
        assert _call(base + "/tape/write", {"path": "m1/bits.json", "text": "{}"})[0] == 403
        assert _call(base + "/tape/write", {"path": "m1/bits.json", "text": "{}"}, headers={"X-CC-Operator": "wrong"})[0] == 403
        # an app frame or a sandboxed desk page inside the console: refused even with the token
        assert _call(base + "/tape", headers={**OP, "Origin": "null"})[0] == 403
        assert _call(base + "/tape/write", {"path": "m1/bits.json", "text": "{}"}, headers={**OP, "Sec-Fetch-Site": "cross-site"})[0] == 403
        assert json.loads((root / "m1" / "bits.json").read_text()) == {"id": "m1", "bits": []}
    finally:
        srv.shutdown()


def test_brain_without_a_tape(monkeypatch, tmp_path):
    m, srv, base, root = _bridge(monkeypatch, tmp_path)
    try:
        (root / "index.json").unlink()
        assert _call(base + "/tape", headers=OP) == (200, {"tape": False})
        assert _call(base + "/tape/write", {"path": "m1/bits.json", "text": "{}"}, headers=OP)[0] == 400
    finally:
        srv.shutdown()


def test_talk_through_slices_assemble(monkeypatch, tmp_path):
    """The page's recorder: each slice through the console's /cc/upload, then the slice list through
    /cc/tape/write. The watcher's contract: the listed files are .part files in a dated folder of in/,
    in order, and joined they are the recording byte for byte."""
    m, srv, base, root = _bridge(monkeypatch, tmp_path)
    take = os.urandom(3 * 65536 + 123)
    slices = [take[i:i + 70000] for i in range(0, len(take), 70000)]
    rid = "20261114-002728-ab12"
    parts = []
    try:
        for k, sl in enumerate(slices, 1):
            body, ctype = m._multipart_encode({}, "file", f"talk-{rid}-{k:04d}.webm.part", sl, "audio/webm")
            st, d = _call(base + "/upload", body, headers=OP, ctype=ctype)
            assert st == 200 and d["ok"], d
            parts.append(d["files"][0]["path"])
            man = {"id": rid, "ext": "webm", "parts": parts, "done": k == len(slices)}
            st, d = _call(base + "/tape/write", {"path": f"{root}/inbox/talk-{rid}.rec.json", "text": json.dumps(man) + "\n"}, headers=OP)
            assert st == 200 and d["ok"], d
        man = json.loads((root / "inbox" / f"talk-{rid}.rec.json").read_text())
        assert man["done"] is True and len(man["parts"]) == len(slices) == 3
        for p in map(pathlib.Path, man["parts"]):
            assert p.name.endswith(".part") and p.parent.parent == tmp_path / "in"
            assert len(p.parent.name) == 10 and p.parent.name[4] == "-"          # in/<YYYY-MM-DD>/
        assert b"".join(pathlib.Path(p).read_bytes() for p in man["parts"]) == take
        # a slice list may not be written for a name the watcher would not take
        assert _call(base + "/tape/write", {"path": "inbox/talk-../../x.rec.json", "text": "{}"}, headers=OP)[0] == 400
    finally:
        srv.shutdown()


def test_page_is_generic_and_uses_only_its_doors():
    """The template is public: the page names no one's paths or systems, and reaches the bridge only
    through /cc/tape and the console's /cc/upload (never the Files pane's raw door, which sandboxes pages)."""
    import re
    src = (ROOT / "ui" / "lib" / "tape" / "tape.js").read_text() + (ROOT / "ui" / "pages" / "tape.js").read_text()
    for word in ("/home/", "hbar", "Telegram", "ops/memos", "/cc/files/raw", "/cc/files/write"):
        assert word not in src, word
    doors = set(re.findall(r"'(/cc/[a-z/]+)", src))
    assert doors <= {"/cc/tape", "/cc/tape/file", "/cc/tape/stat", "/cc/tape/write", "/cc/upload"}, doors
    assert "/cc/upload" in doors and "/cc/tape/write" in doors
