"""/take (DEMO-1, 2026-11-25): scripts/cc/cc_take.py, the sync helpers in ui/lib/take.js, and the page's promises.

The owner asked for one surface: record, demo, ask. These tests hold the bridge to its word: a take recorded on
/take shows with where it stands (the demo being made, ready, kept, again, dropped, the ask drafted, sent, answered);
a dropped track is kept by its hash and only audio is taken; a verdict needs a demo; an ask needs a kept demo, an
address, and the offer line filled; nothing outside the take folder (or a film room's cuts) is served; the booth
keeps the embed's clock pairs. The node part: the clock fit, the sync step and the drift numbers."""
import hashlib
import io
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_booth  # noqa: E402
import cc_take  # noqa: E402

PAGE = (ROOT / "ui" / "pages" / "take.js").read_text()


def wav_bytes(seconds=0.5, rate=48000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(3); w.setframerate(rate)
        w.writeframes(b"\x01\x02\x03" * int(seconds * rate))
    return b.getvalue()


class H:
    def __init__(self, data, headers):
        self.headers = {"Content-Length": str(len(data)), **headers}
        self.rfile = io.BytesIO(data)


def save_take(booth, over, lines=None, name="t"):
    meta = {"name": name, "over": over, "page": {"surface": "take", "lines": lines}}
    from urllib.parse import quote
    code, d = booth.save(H(wav_bytes(), {"X-Booth-Meta": quote(json.dumps(meta))}))
    assert code == 200, d
    return d["take"]


@pytest.fixture()
def env(tmp_path):
    world = tmp_path / "world"
    (world / "systems" / "m" / "ops" / "take").mkdir(parents=True)
    room = tmp_path / "room"
    (room / "cuts").mkdir(parents=True)
    (world / "systems" / "m" / "ops" / "take" / "lines.json").write_text(json.dumps({"sets": [
        {"id": "k2", "title": "K2", "groups": [{"n": 1, "bar": 1, "lines": ["a"]}, {"n": 2, "bar": 9, "lines": ["b"]}],
         "film": {"room": str(room)}}]}))
    booth = cc_booth.Booth(tmp_path / "booth")
    t = cc_take.Take(booth, tmp_path / "take", str(world))
    return t, booth, room, tmp_path


def demo_for(t, take, versions=None):
    d = t.root / "demos" / take["file"].removesuffix(".wav")
    d.mkdir(parents=True, exist_ok=True)
    (d / "demo.json").write_text(json.dumps({"versions": versions or [{"v": "v01", "treatments": [{"id": "dry", "voice": "demos/x/v01/voice_dry.mp3"}]}]}))
    return d


def test_state_lists_take_surface_only_with_step(env):
    t, booth, _, _ = env
    save_take(booth, {"kind": "embed", "video_id": "abcdefghijk", "pairs": [[1.0, 0.5], [2.0, 1.5]]}, name="over yt")
    from urllib.parse import quote
    booth.save(H(wav_bytes(), {"X-Booth-Meta": quote(json.dumps({"name": "sing page"}))}))   # a /sing take: not listed
    s = t.state()
    assert s["ok"] and len(s["takes"]) == 1
    k = s["takes"][0]
    assert k["step"]["state"] == "making" and k["over"]["pairs"] == [[1.0, 0.5], [2.0, 1.5]]   # the booth kept the pairs
    assert [x["id"] for x in s["lines"]] == ["k2"] and s["films"][0]["cuts"] == []


def test_the_strip_walks_record_demo_ask(env):
    t, booth, _, _ = env
    k = save_take(booth, {"kind": "embed", "video_id": "abcdefghijk", "title": "Beat", "artist": "Prod"})
    assert t.verdict({"take": k["file"], "word": "keep"})[0] == 404            # no demo yet
    d = demo_for(t, k)
    assert t.state()["takes"][0]["step"]["state"] == "ready"
    assert t.ask({"take": k["file"], "word": "draft"})[0] == 409               # keep first
    assert t.verdict({"take": k["file"], "word": "maybe"})[0] == 400
    assert t.verdict({"take": k["file"], "word": "keep", "treatment": "phone"})[0] == 200
    assert t.state()["takes"][0]["step"]["state"] == "to-ask"
    assert t.ask({"take": k["file"], "word": "draft"})[0] == 200
    assert t.state()["takes"][0]["step"]["state"] == "drafting"
    (d / "ask.json").write_text(json.dumps({"to": "a@b.co", "body": "Hi\n[your offer: write it here]"}))
    assert t.state()["takes"][0]["step"]["state"] == "drafted"
    assert t.ask({"take": k["file"], "word": "send", "to": "nope", "subject": "s", "body": "x"})[0] == 400
    code, r = t.ask({"take": k["file"], "word": "send", "to": "a@b.co", "subject": "s", "body": "Hi [your offer: x]"})
    assert code == 400 and "offer" in r["error"]
    assert t.ask({"take": k["file"], "word": "send", "to": "a@b.co", "subject": "can I", "body": "Hi, 100 EUR"})[0] == 200
    assert json.loads((d / "ask.send.json").read_text())["to"] == "a@b.co"
    assert t.state()["takes"][0]["step"]["state"] == "sending"
    assert t.ask({"take": k["file"], "word": "send", "to": "a@b.co", "subject": "again", "body": "x"})[0] == 409   # once
    (d / "ask.sent.json").write_text(json.dumps({"ok": True, "to": "a@b.co", "at": "2026-11-25T00:00:00Z"}))
    assert t.state()["takes"][0]["step"]["state"] == "sent"
    assert t.ask({"take": k["file"], "word": "answer", "answer": "yes"})[0] == 200
    assert t.state()["takes"][0]["step"]["state"] == "answered"


def test_own_track_kept_is_done_and_again_and_drop(env):
    t, booth, _, _ = env
    k = save_take(booth, {"kind": "own", "n": "abyss", "mine": True})
    demo_for(t, k)
    t.verdict({"take": k["file"], "word": "keep"})
    assert t.state()["takes"][0]["step"] == {"at": "done", "state": "kept", "say": "kept"}
    t.verdict({"take": k["file"], "word": "again"})
    st = t.state()["takes"][0]
    assert st["step"]["state"] == "again" and st["verdict"]["before"]["word"] == "keep"   # the old word stays on record
    t.verdict({"take": k["file"], "word": "drop"})
    assert t.state()["takes"][0]["step"]["state"] == "dropped"
    assert (booth.root).glob("*/*.wav")                                                   # drop never deletes the take
    assert len(list(booth.root.glob("*/*.wav"))) == 1


def test_a_renamed_take_keeps_its_demo(env):
    t, booth, _, _ = env
    k = save_take(booth, {"kind": "none"}, name="first")
    demo_for(t, k)
    code, r = booth.rename(k["file"], "better name")
    assert code == 200
    assert t.state()["takes"][0]["step"]["state"] == "ready"


def test_backing_kept_by_hash_audio_only(env):
    t, _, _, _ = env
    data = b"ID3fake-mp3-bytes" * 100
    code, d = t.backing(H(data, {"X-Take-Name": "My%20Beat.mp3"}))
    assert code == 200 and d["id"] == hashlib.sha256(data).hexdigest()[:16]
    assert (t.root / "backing" / f"{d['id']}.mp3").read_bytes() == data
    assert t.backing(H(data, {"X-Take-Name": "My%20Beat.mp3"}))[1]["id"] == d["id"]          # same bytes, same file
    assert t.backing(H(b"x", {"X-Take-Name": "notes.txt"}))[0] == 400


def test_files_served_only_inside(env, tmp_path):
    t, booth, room, _ = env
    k = save_take(booth, {"kind": "none"})
    d = demo_for(t, k)
    (d / "v01").mkdir()
    (d / "v01" / "voice_dry.mp3").write_bytes(b"mp3")
    (room / "cuts" / "k2_spoken_v01.mp4").write_bytes(b"mp4")
    (tmp_path / "secret.mp3").write_bytes(b"no")
    assert t.file_path(f"demos/{d.name}/v01/voice_dry.mp3") is not None
    assert t.file_path(str(room / "cuts" / "k2_spoken_v01.mp4")) is not None
    assert t.file_path(str(tmp_path / "secret.mp3")) is None
    assert t.file_path("demos/../../secret.mp3") is None
    assert t.file_path(f"demos/{d.name}/demo.json") is None                                  # audio and video only
    assert t.file_path("other/x.mp3") is None
    (d / "v01" / "link.mp3").symlink_to(tmp_path / "secret.mp3")
    assert t.file_path(f"demos/{d.name}/v01/link.mp3") is None


def test_page_promises():
    assert "page: { surface: 'take'" in PAGE                     # recorded through the booth, marked as /take's
    assert "youtube-nocookie" in PAGE and "iframe_api" in PAGE     # the official embed, nothing downloaded
    for word in ("'keep'", "'again'", "'drop'", "'draft'", "'send'"):
        assert word in PAGE
    assert "Wired headphones on" in PAGE
    assert "hasOffer(f.body)" in PAGE                              # send stays off until the offer is written


def _node(tmp_path, body):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    shutil.copy(ROOT / "ui" / "lib" / "take.js", tmp_path / "take.mjs")
    r = subprocess.run([node, "--input-type=module", "-e", f"import('./take.mjs').then(m=>{{{body}}})"],
                       capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_clock_fit_and_sync_step(tmp_path):
    out = _node(tmp_path, """
      const pairs = []; for (let i = 0; i < 50; i++) pairs.push([1 + i * 0.2, 0.25 + 1.001 * (1 + i * 0.2) + (i % 2 ? 0.004 : -0.004)])
      const f = m.fitLine(pairs)
      const inTake = m.pairsInTake([[10.0, 0.0], [12.0, 2.0]], 0.36, 10.35, 0.02)
      const map = { rate: 1, video_at_voice_0: 30 }
      console.log(JSON.stringify({ f, inTake, hold: m.syncStep(40, 10.01, map), nudge: m.syncStep(40, 10.06, map),
        seek: m.syncStep(40, 11, map), wait: m.syncStep(29, 0, map), st: m.driftStats([1, -2, 3, -40]),
        strip: m.stripCounts([{ step: { at: 'demo', state: 'ready' } }, { step: { at: 'ask', state: 'drafted' } }]),
        offer: [m.hasOffer('x [your offer: ]'), m.hasOffer('100 EUR')] }))
    """)
    assert abs(out["f"]["rate"] - 1.001) < 1e-3 and abs(out["f"]["at0"] - 0.25) < 0.01 and out["f"]["maxResMs"] < 6
    assert out["inTake"][0] == [0.03, 0.0] and out["inTake"][1] == [2.03, 2.0]
    assert out["hold"]["action"] == "hold" and out["nudge"]["action"] == "nudge" and out["nudge"]["rate"] < 1
    assert out["seek"]["action"] == "seek" and out["wait"]["action"] == "wait"
    assert out["st"]["max"] == 40 and out["st"]["n"] == 4
    assert out["strip"]["ready"] == 1 and out["strip"]["toAsk"] == 1
    assert out["offer"] == [False, True]


# ---- DEMO-3 (2026-11-25): the private library of fetched tracks on /take

def _lib_track(lib, vid="OpJeQP2QzkY", state="demo made", **kw):
    f = lib / vid
    f.mkdir(parents=True)
    (f / "audio.webm").write_bytes(b"their audio")
    (f / "track.wav").write_bytes(b"wav")
    (f / "track.json").write_text(json.dumps({"video_id": vid, "title": "Control", "artist": "Stamina Beats", "state": state,
                                              "audio": "audio.webm", "wav": "track.wav", "demos": [{}], "grid": {"bpm": 100},
                                              "stems": {"drums": "stems/drums.wav"}, **kw}))
    return f


def test_library_states_fetch_door_and_copy_served(env, tmp_path):
    t, booth, room, _ = env
    lib = tmp_path / "library"
    _lib_track(lib)
    t = cc_take.Take(booth, tmp_path / "take", str(tmp_path / "world"), None, str(lib))
    st = t.state()["library"]
    assert st[0]["state"] == "demo made" and st[0]["play"] == "library/OpJeQP2QzkY/audio.webm" and st[0]["stems"] == ["drums"]
    assert t.file_path("library/OpJeQP2QzkY/audio.webm") is not None          # his console plays the copy
    assert t.file_path("library/OpJeQP2QzkY/track.json") is None
    assert t.file_path("library/OpJeQP2QzkY/../../take/x.mp3") is None
    code, d = t.fetch({"video_id": "abcdefghijk", "title": "Their Beat"})
    assert code == 200 and (t.root / "fetch" / "abcdefghijk.want.json").exists()
    assert {"video_id": "abcdefghijk", "state": "fetching", "title": "Their Beat"} in t.state()["library"]
    (t.root / "fetch" / "abcdefghijk.json").write_text(json.dumps({"state": "refused", "why": "YouTube's bot wall", "via_mac": False}))
    row = next(x for x in t.state()["library"] if x["video_id"] == "abcdefghijk")
    assert row["state"] == "refused" and "bot wall" in row["why"]
    t.fetch({"video_id": "abcdefghijk", "via_mac": True})                        # his press: through the Mac, once
    row = next(x for x in t.state()["library"] if x["video_id"] == "abcdefghijk")
    assert row["state"] == "fetching" and row["via_mac"]
    assert t.fetch({"video_id": "../etc"})[0] == 400


def test_library_no_is_never_served_or_fetched_again(env, tmp_path):
    t, booth, room, _ = env
    lib = tmp_path / "library"
    f = _lib_track(lib, state="no")
    (f / "audio.webm").unlink()
    t = cc_take.Take(booth, tmp_path / "take", str(tmp_path / "world"), None, str(lib))
    assert t.state()["library"][0]["play"] is None
    assert t.file_path("library/OpJeQP2QzkY/audio.webm") is None
    assert t.fetch({"video_id": "OpJeQP2QzkY"})[0] == 409
