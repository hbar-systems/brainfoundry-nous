"""
The private library guard (DEMO-3, 2026-11-25): scripts/cc/cc_library.py, and the bridge's release doors
(/orfeo/post, /send-file) refusing another artist's audio before their yes.

Run from repo root:
    pytest tests/test_cc_library.py -v
"""
import hashlib
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))

import cc_library  # noqa: E402


def _lib(tmp_path, cleared=False, state="demo made"):
    lib = tmp_path / "library"
    f = lib / "dQw4w9WgXcQ"
    f.mkdir(parents=True)
    audio = f / "audio.webm"
    audio.write_bytes(b"their audio")
    demo = tmp_path / "demo_v01.mp3"
    demo.write_bytes(b"his voice over their audio")
    card = {"video_id": "dQw4w9WgXcQ", "title": "Song A", "artist": "Artist A", "state": state, "cleared": cleared,
            "contact": "artist@example.org"}
    (f / "track.json").write_text(json.dumps(card))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    (lib / "index.json").write_text(json.dumps({"files": {sha(audio): card | {"what": "fetched track"},
                                                          sha(demo): card | {"what": "demo over it"}}}))
    return lib, audio, demo


def test_refuses_library_file_demo_and_copies(tmp_path):
    lib, audio, demo = _lib(tmp_path)
    copy = tmp_path / "elsewhere.webm"
    copy.write_bytes(audio.read_bytes())
    for p in (audio, demo, copy):
        why = cc_library.refusal(lib, path=p)
        assert why and "Artist A" in why and "private library" in why
    assert cc_library.refusal(lib, sha256=hashlib.sha256(b"their audio").hexdigest())


def test_lets_own_and_cleared_and_no_library(tmp_path):
    lib, audio, demo = _lib(tmp_path, cleared=True, state="yes")
    mine = tmp_path / "mine.wav"
    mine.write_bytes(b"my own track")
    assert cc_library.refusal(lib, path=audio) is None
    assert cc_library.refusal(lib, path=demo) is None
    assert cc_library.refusal(lib, path=mine) is None
    assert cc_library.refusal(tmp_path / "no-such-dir", path=mine) is None
    assert cc_library.refusal("", path=mine) is None


def test_unindexed_file_in_library_folder_refused(tmp_path):
    lib = tmp_path / "library"
    (lib / "abcdefghijk").mkdir(parents=True)
    p = lib / "abcdefghijk" / "audio.m4a"
    p.write_bytes(b"x")
    assert cc_library.refusal(lib, path=p)


def _bridge(monkeypatch, tmp_path, lib):
    pytest.importorskip("permitd")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_BOX", "1")
    monkeypatch.setenv("CC_LIBRARY_DIR", str(lib))
    monkeypatch.delenv("CC_POSTURE", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge_library", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_library"] = mod
    spec.loader.exec_module(mod)
    mod.BRAIN_API_KEY = "k"
    return mod


def test_orfeo_post_refuses_before_the_card(monkeypatch, tmp_path):
    lib, audio, demo = _lib(tmp_path)
    m = _bridge(monkeypatch, tmp_path, lib)
    asked, sent = [], []
    body = {"kind": "track", "title": "my verse", "audio_url": "https://files.example.com/a.mp3",
            "audio_sha256": hashlib.sha256(demo.read_bytes()).hexdigest(), "station": "https://orfeo.music"}
    code, d = m._orfeo_post(body, ask=lambda *a: asked.append(a) or {"behavior": "allow"}, api=lambda *a: sent.append(a))
    assert code == 403 and "private library" in d["error"] and not asked and not sent


def test_send_file_refuses_library_audio(monkeypatch, tmp_path):
    lib, audio, demo = _lib(tmp_path)
    m = _bridge(monkeypatch, tmp_path, lib)
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    p = out / "demo_v01.mp3"
    p.write_bytes(demo.read_bytes())

    class TG:
        sent = []
        @staticmethod
        def owner():
            return 1
        @classmethod
        def send_file(cls, *a, **k):
            cls.sent.append(a)
            return {"ok": True}

    monkeypatch.setattr(m, "TG", TG)
    monkeypatch.setattr(m, "FILES", m.cc_extras.Files({"out": str(out)}), raising=False)
    monkeypatch.setattr(m.cc_extras, "Files", lambda roots: type("F", (), {"resolve": staticmethod(lambda raw: pathlib.Path(raw))})())
    code, d = m._send_file(str(p))
    assert code == 403 and "private library" in d["error"] and not TG.sent
