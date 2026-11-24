"""BigUploads (scripts/cc/cc_extras.py): files over the 50 MB cap in pieces, resumable (VIDEO-DOOR-1, 2026-11-24).

Synthetic files only, no network beyond a bridge on 127.0.0.1.
    pytest tests/test_cc_big_uploads.py -v
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import pathlib
import stat
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_extras_big", ROOT / "scripts" / "cc" / "cc_extras.py")
X = importlib.util.module_from_spec(spec); sys.modules["cc_extras_big"] = X; spec.loader.exec_module(X)

GB = 1024 ** 3


class FakeHandler:
    def __init__(self, body: bytes, length: int | None = None):
        self.headers = {"Content-Length": str(len(body) if length is None else length), "Content-Type": "application/octet-stream"}
        self.rfile = io.BytesIO(body)


def _big(tmp_path, free=100 * GB, **kw):
    return X.BigUploads(tmp_path / "in", free_fn=lambda: free, **kw)


def _send_all(up, uid, data, start=0, piece=X.BIG_CHUNK):
    off = start
    while off < len(data):
        d = up.chunk(uid, off, FakeHandler(data[off:off + piece]))
        assert d["ok"], d
        off = d["received"]
    return off


def test_whole_file_in_pieces_lands_in_today_with_sha(tmp_path):
    data = os.urandom(3 * X.BIG_CHUNK + 12345)            # four pieces, the last one short
    up = _big(tmp_path)
    s = up.start({"name": "IMG_0412.MOV", "size": len(data), "key": "1732440000000"})
    assert s["ok"] and s["received"] == 0 and s["chunk"] == 8 * 1024 * 1024 and s["name"] == "IMG_0412.MOV"
    _send_all(up, s["id"], data)
    f = up.finish(s["id"])
    assert f["ok"], f
    got = f["files"][0]
    p = pathlib.Path(got["path"])
    assert p.parent.parent == tmp_path / "in" and p.name == "IMG_0412.MOV"
    assert p.read_bytes() == data and got["size"] == len(data) and got["sha256"] == hashlib.sha256(data).hexdigest()
    assert stat.S_IMODE(p.stat().st_mode) & 0o044 == 0o044         # group- and other-readable
    assert not any(n.endswith((".part", ".json")) for n in os.listdir(tmp_path / "in" / ".partial"))
    assert up.status(s["id"])["status"] == 404                       # finished: gone from the partials


def test_interrupted_upload_resumes_where_it_stopped(tmp_path):
    data = os.urandom(2 * X.BIG_CHUNK + 999)
    up = _big(tmp_path)
    s = up.start({"name": "walk.mov", "size": len(data), "key": "k1"})
    uid = s["id"]
    assert up.chunk(uid, 0, FakeHandler(data[:X.BIG_CHUNK]))["received"] == X.BIG_CHUNK
    # the phone drops off mid-piece: the body ends early; nothing of it is written
    cut = data[X.BIG_CHUNK:2 * X.BIG_CHUNK][:1000]
    d = up.chunk(uid, X.BIG_CHUNK, FakeHandler(cut, length=X.BIG_CHUNK))
    assert not d.get("ok") and d["status"] == 408                    # the page sends it again
    assert up.status(uid)["received"] == X.BIG_CHUNK
    # the same file dropped again (a new page, same name, size and key) picks up at the same offset
    up2 = _big(tmp_path)
    s2 = up2.start({"name": "walk.mov", "size": len(data), "key": "k1"})
    assert s2["id"] == uid and s2["received"] == X.BIG_CHUNK
    _send_all(up2, uid, data, start=s2["received"])
    f = up2.finish(uid)
    assert pathlib.Path(f["files"][0]["path"]).read_bytes() == data
    assert f["files"][0]["sha256"] == hashlib.sha256(data).hexdigest()


def test_out_of_step_piece_is_409_with_the_right_offset(tmp_path):
    data = os.urandom(3000)
    up = _big(tmp_path)
    uid = up.start({"name": "a.mp4", "size": 3000})["id"]
    up.chunk(uid, 0, FakeHandler(data[:1000]))
    d = up.chunk(uid, 0, FakeHandler(data[:1000]))                 # a retry of a piece that did arrive
    assert d["status"] == 409 and d["received"] == 1000
    d = up.chunk(uid, 2000, FakeHandler(data[2000:]))               # a gap
    assert d["status"] == 409 and d["received"] == 1000
    assert up.chunk(uid, 1000, FakeHandler(data[1000:] + b"x"))["status"] == 400   # more than the file has
    assert up.finish(uid)["status"] == 409                          # not all there yet
    _send_all(up, uid, data, start=1000, piece=1000)
    assert up.finish(uid)["ok"]


def test_cap_and_free_disk_floor(tmp_path):
    up = _big(tmp_path, max_bytes=100)
    d = up.start({"name": "x.mov", "size": 101})
    assert d["status"] == 413 and "limit" in d["error"]
    assert _big(tmp_path).max == 4 * GB and _big(tmp_path).floor == 5 * GB       # defaults
    # 5.5 GB free, a 1 GB file would leave 4.5: refused before a byte is taken
    d = _big(tmp_path, free=int(5.5 * GB)).start({"name": "big.mov", "size": GB})
    assert d["status"] == 507 and "keeps 5.0 GB free" in d["error"]
    assert _big(tmp_path, free=int(6.5 * GB)).start({"name": "big.mov", "size": GB})["ok"]
    # the disk fills while it uploads: the next piece is refused too
    free = [100 * GB]
    up = X.BigUploads(tmp_path / "in2", free_fn=lambda: free[0])
    uid = up.start({"name": "f.mov", "size": 2000})["id"]
    free[0] = 5 * GB
    assert up.chunk(uid, 0, FakeHandler(b"a" * 1000))["status"] == 507


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_UPLOAD_MAX_BYTES", "12345")
    monkeypatch.setenv("CC_UPLOAD_FLOOR_BYTES", "nonsense")
    up = X.BigUploads(tmp_path / "in")
    assert up.max == 12345 and up.floor == 5 * GB


def test_taken_name_and_bad_input(tmp_path):
    up = _big(tmp_path)
    for key in ("a", "b"):
        uid = up.start({"name": "../../clip?.mov", "size": 4, "key": key})["id"]
        up.chunk(uid, 0, FakeHandler(b"abcd"))
        f = up.finish(uid)
    assert f["files"][0]["name"] == "clip_-1.mov"
    assert up.start({"name": "x", "size": 0})["status"] == 400
    assert up.start({"name": "x", "size": True})["status"] == 400
    assert up.start({"name": "x", "size": "10"})["status"] == 400
    assert up.status("../../etc")["status"] == 404
    assert up.chunk("zz", 0, FakeHandler(b"a"))["status"] == 404
    assert up.finish("0" * 32)["status"] == 404


def test_planted_link_in_the_partials_is_refused(tmp_path):
    up = _big(tmp_path)
    uid = up.start({"name": "v.mov", "size": 4})["id"]
    part = tmp_path / "in" / ".partial" / (uid + ".part")
    part.unlink()
    target = tmp_path / "victim"; target.write_bytes(b"")
    part.symlink_to(target)
    d = up.chunk(uid, 0, FakeHandler(b"abcd"))
    assert d["status"] == 409 and not d.get("ok")
    code, d = up.handle("/upload/big/chunk", FakeHandler(b"abcd"), {"id": uid, "offset": "0"}, dict)
    assert code == 409 and d["ok"] is False
    assert target.read_bytes() == b""                                # never written through the link


def test_bridge_door_needs_the_operator_token_and_works_end_to_end(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    from test_cc_systems import _bridge, _call
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="tok")
    monkeypatch.setattr(m, "BIG_UPLOADS", m.cc_extras.BigUploads(tmp_path / "in", free_fn=lambda: 100 * GB))
    try:
        data = os.urandom(X.BIG_CHUNK + 77)
        st, d = _call(base + "/upload/big/start", {"name": "m.mov", "size": len(data), "key": "1"})
        assert st == 403                                             # no operator token: no door
        H = {"X-CC-Operator": "tok"}
        st, d = _call(base + "/upload/big/start", {"name": "m.mov", "size": len(data), "key": "1"}, H)
        assert st == 200 and d["ok"]
        uid = d["id"]
        st, d = _call(f"{base}/upload/big/chunk?id={uid}&offset=0", data[:X.BIG_CHUNK], H, "application/octet-stream")
        assert st == 200 and d["received"] == X.BIG_CHUNK
        st, d = _call(f"{base}/upload/big/chunk?id={uid}&offset=0", data[:10], H, "application/octet-stream")
        assert st == 409 and d["received"] == X.BIG_CHUNK
        st, d = _call(base + "/upload/big/status", {"id": uid}, H)
        assert st == 200 and d["received"] == X.BIG_CHUNK and d["size"] == len(data)
        st, d = _call(f"{base}/upload/big/chunk?id={uid}&offset={X.BIG_CHUNK}", data[X.BIG_CHUNK:], H, "application/octet-stream")
        assert st == 200
        st, d = _call(base + "/upload/big/finish", {"id": uid}, H)
        assert st == 200 and d["files"][0]["sha256"] == hashlib.sha256(data).hexdigest()
        assert pathlib.Path(d["files"][0]["path"]).read_bytes() == data
    finally:
        srv.shutdown()
