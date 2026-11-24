"""tests/browser/test_sing_booth.py: the booth (/sing, SING-FREE-1 2026-11-24) in a real browser with a synthetic
microphone.

    Chromium (Playwright, --use-fake-device-for-media-stream fed a generated WAV)
        -> a front (this file: /cc to the bridge with the operator token, as Caddy does; /api answered small;
           the rest to the built console, next standalone server.js)
        -> the real cc-bridge (in process, temp folders), whose /cc/booth routes keep the takes

Checks, end to end: the page opens on one enabled record control with no loop chosen and no loop list shown;
press, sing (the synthetic voice), stop: one 24-bit WAV lands in <out>/studio/booth/<day>/, as long as the take,
with the voice in it, its sha256 equal to its card; named afterwards, the file is renamed and its bytes are the
same; "send to my phone" answers the bridge's reason when no phone is paired; play works. Over a track (a file
given to the page): the track plays, the take holds only the microphone plus the marker, and the card says where
the track started in the take. Over a loop: the take is kept in the booth and its pair (wav + hbar.sing.take/v1)
goes to /cc/upload for the rooms. No page error in any of it.

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>,
default ui/ here), like test_console_login.py.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_sing_booth.py -q
Serve it for a look (prints the URL, Ctrl-C ends):  ... python tests/browser/test_sing_booth.py serve [port]
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("NOUS_CONSOLE_BUILD", str(REPO / "ui")))
SERVER_JS = BUILD / ".next" / "standalone" / "server.js"
TOKEN = "booth-test-operator-token"
CHROME_LIBS = Path(os.environ.get("NOUS_CHROME_LIBS", str(Path.home() / ".local/chromelibs/root/usr/lib/aarch64-linux-gnu")))
# the bridge runs with a temp HOME; the browsers stay where this user's cache has them
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright"))

API = {
    "/apps/list": {"apps": [], "ccHome": True},
    "/onboarding/first-use": {"steps": [], "complete": True, "fresh": False},
    "/onboarding/welcome": {"seen_version": 999},
    "/v1/federation/peers": {"peers": []},
    "/v1/help/status": {"helper": None, "ready": False, "message": "no helper set", "button": True, "asked": []},
    "/admin/system": {"warnings": []},
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, timeout: float = 40.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"nothing listening on 127.0.0.1:{port}")


def tone_wav(path: Path, seconds: float, freq: float, amp: float, rate: int = 48000, wobble: bool = True) -> None:
    """A voice-like test signal: a tone whose loudness moves like phrases (syllables at 4 Hz)."""
    n = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        fr = bytearray()
        for i in range(n):
            env = (0.55 + 0.45 * math.sin(2 * math.pi * 4 * i / rate)) if wobble else 1.0
            fr += struct.pack("<h", int(32767 * amp * env * math.sin(2 * math.pi * freq * i / rate)))
        w.writeframes(bytes(fr))


class Harness:
    """The built console + the real bridge on temp folders + a front that does Caddy's job."""

    def __init__(self, root: Path, port: int | None = None):
        self.root = root
        self.home = root / "hands"
        (self.home / "out").mkdir(parents=True)
        (self.home / "in").mkdir(parents=True)
        self.world = root / "world"
        (self.world / "ops" / "sing").mkdir(parents=True)
        (root / "brain").mkdir()
        # a loop catalogue the page reads through /cc/files/raw (the world's ops/sing/loops.json)
        tone_wav(self.world / "ops" / "sing" / "beat.wav", 4 * 240 / 120, 110, 0.3, wobble=False)
        loop = {"id": "test_beat:a", "slug": "test_beat_a", "track": "test_beat", "part": "a", "label": "A", "key": "A minor",
                "bars": 4, "bpm": 120, "rate": 48000, "samples": 4 * 2 * 48000, "audio": "ops/sing/beat.wav", "layer": "full"}
        (self.world / "ops" / "sing" / "loops.json").write_text(json.dumps({"loops": [loop], "grid_bars": 8}))
        self.port = port or free_port()
        self.next_port = free_port()

    def start(self):
        env = {"HOME": str(self.root), "CC_CWD": str(self.root / "brain"), "CC_HANDS_HOME": str(self.home),
               "CC_OPERATOR_TOKEN": TOKEN, "CC_WORLD_DIR": str(self.world),
               "CC_SYSTEMS_SEED": str(self.root / "no-seed.json"), "CC_SYSTEMS_BOARD": str(self.root / "board.json")}
        self._old = {k: os.environ.get(k) for k in list(env) + ["CC_BOOTH_DIR", "BRAIN_API_KEY", "CC_TELEGRAM_TOKEN"]}
        os.environ.update(env)
        for k in ("CC_BOOTH_DIR", "BRAIN_API_KEY", "CC_TELEGRAM_TOKEN"):
            os.environ.pop(k, None)
        spec = importlib.util.spec_from_file_location("cc_bridge_booth_browser", REPO / "scripts" / "cc" / "cc-bridge.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        self.bridge = m
        self.bsrv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
        threading.Thread(target=self.bsrv.serve_forever, daemon=True).start()
        bport = self.bsrv.server_address[1]
        # the console, copied as the Dockerfile does (standalone + static + public)
        app = self.root / "console"
        shutil.copytree(BUILD / ".next" / "standalone", app, symlinks=True)
        shutil.copytree(BUILD / ".next" / "static", app / ".next" / "static")
        if (BUILD / "public").is_dir():
            shutil.copytree(BUILD / "public", app / "public")
        self.node = subprocess.Popen(["node", "server.js"], cwd=str(app), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env=dict(os.environ, PORT=str(self.next_port), HOSTNAME="127.0.0.1", NEXT_TELEMETRY_DISABLED="1"))
        wait_port(self.next_port)
        nport = self.next_port

        class Front(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _go(self):
                path = self.path
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else None
                if path.startswith("/api/"):
                    p = path.split("?", 1)[0]
                    for pre in ("/api/bf", "/api"):
                        if p.startswith(pre + "/"):
                            p = p[len(pre):]
                            break
                    data = json.dumps(API.get(p, {})).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
                    return
                up = bport if path == "/cc" or path.startswith("/cc/") else nport
                hdr = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
                if up == bport:
                    hdr["X-CC-Operator"] = TOKEN
                req = urllib.request.Request(f"http://127.0.0.1:{up}{path}", data=body, method=self.command, headers=hdr)
                try:
                    r = urllib.request.urlopen(req, timeout=60)
                    code, rh, data = r.status, r.headers, r.read()
                except urllib.error.HTTPError as e:
                    code, rh, data = e.code, e.headers, e.read()
                self.send_response(code)
                for k, v in rh.items():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_HEAD = _go

        self.front = ThreadingHTTPServer(("127.0.0.1", self.port), Front)
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.port}"
        return self

    @property
    def booth(self) -> Path:
        return self.home / "out" / "studio" / "booth"

    def takes(self) -> list[Path]:
        return sorted(self.booth.glob("*/*.wav")) if self.booth.is_dir() else []

    def stop(self):
        for s in ("front", "bsrv"):
            try:
                getattr(self, s).shutdown()
            except Exception:
                pass
        try:
            self.node.terminate(); self.node.wait(10)
        except Exception:
            pass
        for k, v in getattr(self, "_old", {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def launch(p, voice: Path):
    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-audio-capture={voice}", "--autoplay-policy=no-user-gesture-required"]
    if CHROME_LIBS.is_dir():
        env = dict(os.environ, LD_LIBRARY_PATH=f"{CHROME_LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":"))
        return p.chromium.launch(args=args, env=env)
    return p.chromium.launch(args=args)


def rms_db(path: Path) -> float:
    with wave.open(str(path)) as w:
        n, width = w.getnframes(), w.getsampwidth()
        fr = w.readframes(n)
    vals = [int.from_bytes(fr[i:i + width], "little", signed=True) / (1 << (8 * width - 1)) for i in range(0, len(fr), width * 50)]
    r = math.sqrt(sum(v * v for v in vals) / max(1, len(vals)))
    return 20 * math.log10(max(r, 1e-9))


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (npm ci && npm run build)")
    if not shutil.which("node"):
        pytest.skip("node not installed")
    tmp = Path(tempfile.mkdtemp(prefix="booth-"))
    h = Harness(tmp).start()
    voice = tmp / "voice.wav"
    tone_wav(voice, 6, 220, 0.35)
    h.voice = voice
    yield h
    h.stop()
    shutil.rmtree(tmp, ignore_errors=True)


def test_just_sing_keep_name_play_send(harness):
    from playwright.sync_api import sync_playwright
    h = harness
    errors = []
    with sync_playwright() as p:
        b = launch(p, h.voice)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errors.append(m.text))
        pg.goto(h.url + "/sing")
        ring = pg.locator(".bo-ring")
        ring.wait_for()
        assert ring.is_enabled() and "press and sing" in ring.inner_text()
        assert pg.locator(".bo-loops").count() == 0                     # the loops stay folded away
        pg.locator(".bo-empty").filter(has_text="Nothing yet").wait_for()
        ring.click()
        pg.locator(".bo.rec").wait_for(timeout=8000)
        t_on = time.time()
        pg.wait_for_timeout(2600)
        assert pg.locator(".bo-clock").inner_text() in ("0:02", "0:03")
        lv = float(pg.evaluate("getComputedStyle(document.querySelector('.bo')).getPropertyValue('--pk')") or 0)
        assert lv > 0.3                                                 # the meter moves with the voice
        if os.environ.get("BOOTH_SHOTS"):
            pg.screenshot(path=os.path.join(os.environ["BOOTH_SHOTS"], "recording-1440.png"))
        ring.click()
        held = time.time() - t_on
        pg.locator(".bo-t.fresh").wait_for(timeout=15000)
        takes = h.takes()
        assert len(takes) == 1
        w = takes[0]
        with wave.open(str(w)) as f:
            secs = f.getnframes() / f.getframerate()
            assert f.getsampwidth() == 3 and f.getnchannels() in (1, 2)
        assert 2.3 < secs and abs(secs - held) < 1.0, (secs, held)      # the take is as long as the press was
        assert rms_db(w) > -30                                          # the synthetic voice is in it
        card = json.loads(w.with_suffix(".json").read_text())
        assert card["sha256"] == hashlib.sha256(w.read_bytes()).hexdigest() and card["over"] is None
        before = w.read_bytes()
        # name it afterwards
        inp = pg.locator(".bo-nm input")
        inp.fill("first verse")
        inp.press("Enter")
        pg.locator(".bo-tname", has_text="first verse").wait_for(timeout=8000)
        named = h.takes()
        assert len(named) == 1 and named[0].name.endswith("_first-verse.wav") and named[0].read_bytes() == before
        # send to my phone: no phone paired on this test brain, so the bridge's reason shows
        pg.locator(".bo-send").first.click()
        pg.locator(".bo-said", has_text="not sent").wait_for(timeout=8000)
        assert "Telegram" in pg.locator(".bo-said").first.inner_text()
        # play it back
        pg.locator(".bo-play").first.click()
        pg.wait_for_function("(() => { const a = document.querySelector('audio'); return a && !a.paused && a.currentTime > 0.2 })()", timeout=8000)
        pg.locator(".bo-play").first.click()
        b.close()
    assert not errors, errors


def test_over_a_track_and_over_a_loop(harness):
    from playwright.sync_api import sync_playwright
    h = harness
    track = h.root / "my track.wav"
    tone_wav(track, 2.0, 440, 0.4, wobble=False)
    errors = []
    n0 = len(h.takes())
    with sync_playwright() as p:
        b = launch(p, h.voice)
        pg = b.new_page(viewport={"width": 390, "height": 844})
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and errors.append(m.text))
        pg.goto(h.url + "/sing")
        pg.locator(".bo-ring").wait_for()
        pg.locator("input[type=file]").set_input_files(str(track))
        pg.locator(".bo-over", has_text="my track.wav").wait_for(timeout=8000)
        assert "headphones" in pg.locator(".bo-hp").inner_text().lower()
        pg.locator(".bo-ring").click()
        # the track is 2 s: the take stops by itself 1.5 s after it ends
        pg.locator(".bo-t.fresh").wait_for(timeout=20000)
        w = max(h.takes(), key=lambda x: x.stat().st_mtime)
        card = json.loads(w.with_suffix(".json").read_text())
        o = card["over"]
        assert o["kind"] == "track" and o["name"] == "my track.wav"
        assert o["marker_in_take_s"] is not None and abs(o["marker_in_take_s"] - 0.35) < 0.15, o
        assert o["track_start_in_take_s"] > o["marker_in_take_s"]
        if os.environ.get("BOOTH_SHOTS"):
            pg.screenshot(path=os.path.join(os.environ["BOOTH_SHOTS"], "over-track-390.png"), full_page=True)
        # back to just the voice, then a loop
        pg.locator(".bo-over button").click()
        assert pg.locator(".bo-over").count() == 0
        pg.locator(".bo-opt", has_text="over a loop").click()
        pg.locator(".bo-tn", has_text="test beat").wait_for()
        if not pg.locator(".bo-p").count():                               # one loop: its track opens by itself
            pg.locator(".bo-tn", has_text="test beat").click()
        pg.locator(".bo-p").first.click()
        pg.locator(".bo-over", has_text="120 BPM").wait_for()
        pg.locator(".bo-ring").click()
        pg.locator(".bo.rec").wait_for(timeout=8000)
        pg.wait_for_timeout(3500)
        pg.locator(".bo-ring").click()
        pg.locator(".bo-said", has_text="grid").wait_for(timeout=15000)
        assert "also sent" in pg.locator(".bo-said", has_text="grid").inner_text()
        b.close()
    w = max(h.takes(), key=lambda x: x.stat().st_mtime)
    assert json.loads(w.with_suffix(".json").read_text())["over"]["kind"] == "loop"
    sides = sorted((h.home / "in").glob("*/sing_*.json"))
    assert len(sides) == 1
    side = json.loads(sides[0].read_text())
    assert side["dialect"] == "hbar.sing.take/v1" and side["recorded"]["mime"] == "audio/wav" and side["page"]["marker_in_take_s"] is not None
    assert sides[0].with_suffix(".wav").is_file() and sides[0].with_suffix(".wav").read_bytes() == w.read_bytes()
    assert not errors, errors


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "serve":
    tmp = Path(tempfile.mkdtemp(prefix="booth-serve-"))
    h = Harness(tmp, int(sys.argv[2]) if len(sys.argv) > 2 else None).start()
    import cc_booth  # noqa: E402  (the bridge put scripts/cc on the path)

    class _H:
        def __init__(self, data, name):
            self.headers = {"Content-Length": str(len(data)), "X-Booth-Meta": urllib.parse.quote(json.dumps({"name": name}))}
            self.rfile = io.BytesIO(data)
    import urllib.parse  # noqa: E402
    for secs, name in ((48, "control verse 2"), (95, "k2 hook idea"), (31, "")):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(3); w.setframerate(48000); w.writeframes(b"\0\0\0" * 48000 * secs)
        h.bridge.BOOTH.save(_H(b.getvalue(), name))
        time.sleep(1.1)
    print(h.url + "/sing", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        h.stop()
