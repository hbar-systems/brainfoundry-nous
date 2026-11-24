"""The booth (SING-FREE-1, 2026-11-24): scripts/cc/cc_booth.py and the bridge's /cc/booth routes.
A take is kept exactly as sent (sha256 equal), one folder per day, listed newest first, named afterwards without
touching its bytes, never over another file; only WAVs are kept; nothing outside the booth folder resolves; the
routes sit behind the console's page gate."""
import hashlib
import importlib.util
import io
import json
import struct
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_booth  # noqa: E402


def wav_bytes(seconds=0.5, rate=48000, channels=1, width=3):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(channels); w.setsampwidth(width); w.setframerate(rate)
        n = int(seconds * rate)
        frame = (b"\x01\x02\x03" if width == 3 else b"\x01\x02") * channels
        w.writeframes(frame * n)
    return b.getvalue()


def test_slug_is_a_file_name_part():
    assert cc_booth.slug("Control, verse 2!") == "control-verse-2"
    assert cc_booth.slug("  ") == "take"
    assert cc_booth.slug(None) == "take"
    assert cc_booth.slug("../../etc/passwd") == "etc-passwd"
    assert cc_booth.slug("Сосознание") == "sosoznanie"    # Cyrillic spelled in Latin letters
    assert cc_booth.slug("日本") == "take"
    assert len(cc_booth.slug("a" * 300)) == 60


def test_wav_info_reads_the_header():
    i = cc_booth.wav_info(wav_bytes(1.0, 48000, 1, 3))
    assert i == {"channels": 1, "rate": 48000, "bits": 24, "seconds": 1.0}
    assert cc_booth.wav_info(wav_bytes(0.25, 44100, 2, 2))["channels"] == 2
    assert cc_booth.wav_info(b"OggS" + b"\0" * 100) is None
    assert cc_booth.wav_info(b"RIFF\0\0\0\0WAVE") is None


class FakeHandler:
    def __init__(self, body, meta=None):
        self.headers = {"Content-Length": str(len(body)), "Content-Type": "audio/wav"}
        if meta is not None:
            self.headers["X-Booth-Meta"] = urllib.parse.quote(json.dumps(meta))
        self.rfile = io.BytesIO(body)


def test_save_keeps_the_bytes_and_a_card(tmp_path):
    b = cc_booth.Booth(tmp_path / "booth")
    data = wav_bytes(0.5)
    st, d = b.save(FakeHandler(data, {"over": {"kind": "track", "name": "k2.mp3"}}))
    assert st == 200 and d["ok"]
    t = d["take"]
    p = pathlib.Path(t["path"])
    assert p.read_bytes() == data and t["sha256"] == hashlib.sha256(data).hexdigest()
    assert p.parent.name == t["day"] and p.name.startswith(t["day"] + "_") and p.name.endswith("_take.wav")
    assert t["seconds"] == 0.5 and t["bits"] == 24 and t["over"] == {"kind": "track", "name": "k2.mp3"}
    assert json.loads(p.with_suffix(".json").read_text())["dialect"] == "hbar.booth.take/v1"
    # the same second twice: a second file, never over the first
    st2, d2 = b.save(FakeHandler(data))
    assert st2 == 200 and d2["take"]["path"] != t["path"] and p.read_bytes() == data
    assert [x["file"] for x in b.state()["takes"]][0] in (pathlib.Path(d2["take"]["path"]).name, p.name)
    assert len(b.state()["takes"]) == 2


def test_save_refuses_what_is_not_a_wav(tmp_path):
    b = cc_booth.Booth(tmp_path / "booth")
    assert b.save(FakeHandler(b"\x1aE\xdf\xa3webm" * 20))[0] == 400
    assert b.save(FakeHandler(b""))[0] == 413
    assert b.state()["takes"] == []


def test_name_afterwards_keeps_the_bytes(tmp_path):
    b = cc_booth.Booth(tmp_path / "booth")
    data = wav_bytes(0.3)
    t = b.save(FakeHandler(data))[1]["take"]
    st, d = b.rename(t["file"], "Control verse")
    assert st == 200, d
    n = d["take"]
    assert n["name"] == "control-verse" and n["title"] == "Control verse" and n["file"].endswith("_control-verse.wav")
    assert pathlib.Path(n["path"]).read_bytes() == data and n["sha256"] == t["sha256"]
    assert not pathlib.Path(t["path"]).exists() and not pathlib.Path(t["path"]).with_suffix(".json").exists()
    # a second take named the same: -1, the first untouched
    t2 = b.save(FakeHandler(wav_bytes(0.2)))[1]["take"]
    n2 = b.rename(t2["path"], "control verse")[1]["take"]
    assert n2["file"] != n["file"] and pathlib.Path(n["path"]).read_bytes() == data


@pytest.mark.parametrize("raw", ["../x.wav", "/etc/passwd", "2026-11-24_120000_take.json", "", "a\x00b",
                                 "/tmp/2026-11-24/2026-11-24_120000_take.wav"])
def test_nothing_outside_resolves(tmp_path, raw):
    b = cc_booth.Booth(tmp_path / "booth")
    b.save(FakeHandler(wav_bytes(0.1)))
    assert b.take_path(raw) is None
    assert b.rename(raw, "x")[0] == 404


# ---- the bridge's routes ----

def _bridge(monkeypatch, tmp_path, token="tok"):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_HANDS_HOME", str(tmp_path))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("CC_BOOTH_DIR", raising=False)
    monkeypatch.delenv("CC_WORLD_DIR", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge_booth", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "BOOTH", m.cc_booth.Booth(tmp_path / "out" / "studio" / "booth"))
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return m, srv, f"http://127.0.0.1:{srv.server_address[1]}/cc"


def _call(url, body=None, headers=None, ctype="application/json", raw=False):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            b = r.read()
            return r.status, (b, dict(r.headers)) if raw else json.loads(b)
    except urllib.error.HTTPError as e:
        b = e.read() or b"{}"
        return e.code, (b, dict(e.headers)) if raw else json.loads(b)


OP = {"X-CC-Operator": "tok"}


def test_routes_keep_list_name_and_play(monkeypatch, tmp_path):
    m, srv, base = _bridge(monkeypatch, tmp_path)
    try:
        data = wav_bytes(0.4)
        meta = urllib.parse.quote(json.dumps({"over": None}))
        st, d = _call(base + "/booth/take", data, headers={**OP, "X-Booth-Meta": meta}, ctype="audio/wav")
        assert st == 200 and d["ok"], d
        t = d["take"]
        assert t["path"].startswith(str(tmp_path / "out" / "studio" / "booth"))
        st, d = _call(base + "/booth", headers=OP)
        assert st == 200 and [x["file"] for x in d["takes"]] == [t["file"]]
        st, d = _call(base + "/booth/name", {"file": t["file"], "name": "first one"}, headers=OP)
        assert st == 200 and d["take"]["name"] == "first-one"
        p = d["take"]["path"]
        st, (b, h) = _call(base + "/booth/file?path=" + urllib.parse.quote(p), headers={**OP, "Range": "bytes=0-11"}, raw=True)
        assert st == 206 and b == data[:12] and h["Accept-Ranges"] == "bytes"
        st, (b, h) = _call(base + "/booth/file?path=" + urllib.parse.quote(p), headers=OP, raw=True)
        assert st == 200 and b == data and h["Content-Type"].startswith("audio/")
        assert _call(base + "/booth/file?path=../../etc/passwd", headers=OP)[0] == 404
        assert _call(base + "/booth/take", b"not a wav at all", headers=OP, ctype="audio/wav")[0] == 400
    finally:
        srv.shutdown()


def test_routes_need_the_console_session(monkeypatch, tmp_path):
    m, srv, base = _bridge(monkeypatch, tmp_path)
    try:
        assert _call(base + "/booth")[0] == 403
        assert _call(base + "/booth/take", wav_bytes(0.1), ctype="audio/wav")[0] == 403
        assert _call(base + "/booth/name", {"file": "x", "name": "y"}, headers={"X-CC-Operator": "wrong"})[0] == 403
        assert _call(base + "/booth/take", wav_bytes(0.1), headers={**OP, "Origin": "null"}, ctype="audio/wav")[0] == 403
        assert not (tmp_path / "out" / "studio" / "booth").exists()
    finally:
        srv.shutdown()


def test_send_file_answers_and_does_not_hang(monkeypatch, tmp_path):
    # /send-file read its body a second time after the bridge had read it (since 2026-11-08), so every caller
    # waited until its own timeout; the booth's "send to my phone" found it (SING-FREE-1)
    m, srv, base = _bridge(monkeypatch, tmp_path)
    try:
        st, d = _call(base + "/send-file", {"path": str(tmp_path / "x.wav")}, headers=OP)
        assert st == 409 and "Telegram" in d["error"]          # no phone paired on a test brain
    finally:
        srv.shutdown()
