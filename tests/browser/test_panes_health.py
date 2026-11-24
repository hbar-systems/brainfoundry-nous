"""tests/browser/test_panes_health.py: the chat boxes on /systems take text at once (PANES-FIX-1, 2026-11-24).

hbar's screenshot 2026-11-24 06:30: all four thread boxes on /systems read "connect a reasoner first". Cause: each
pane locked its box until its own /cc/health answered (5.8 s measured) and /systems opens five panes at once.

    Chromium (Playwright) -> a front (this file): /cc/* answered by a small fake bridge whose /cc/health is slowed
    to HEALTH_DELAY seconds and counted; /api answered small; the rest to the built console (next standalone).

Checks: /systems?open=a,b,c,d opens the central chat and four panes; while health is still out every pane's box is
enabled and none says "connect a reasoner first"; a message typed into one pane then is held, and sent to that
pane's own thread (POST /cc/chat) once health answers, never lost; the five frames ask /cc/health once between them,
not five times. With the fake bridge saying no reasoner is signed in, the text shows, and only after the answer;
a message held meanwhile goes back into the box. No page error.

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>,
default ui/ here), like test_console_login.py.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_panes_health.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("NOUS_CONSOLE_BUILD", str(REPO / "ui")))
SERVER_JS = BUILD / ".next" / "standalone" / "server.js"
CHROME_LIBS = Path(os.environ.get("NOUS_CHROME_LIBS", str(Path.home() / ".local/chromelibs/root/usr/lib/aarch64-linux-gnu")))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright"))
HEALTH_DELAY = 4.0
NO_REASONER = "connect a reasoner first"

SYSTEMS = ["a", "b", "c", "d"]
THREADS = {s: f"{i:08x}-0000-4000-8000-00000000000{i}" for i, s in enumerate(["world"] + SYSTEMS, 1)}

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


class Harness:
    """The built console + a front that answers /cc itself (a slowed, counted /cc/health)."""

    def __init__(self, root: Path):
        self.root = root
        self.logged_in = True
        self.health_calls: list[float] = []
        self.chats: list[dict] = []
        self.lock = threading.Lock()

    def health(self) -> dict:
        return {"ok": True, "auth": {"loggedIn": self.logged_in, "email": "test@example.invalid" if self.logged_in else None},
                "codex": {"installed": False, "signedIn": False}, "local": {"configured": False},
                "runs": [], "cards_waiting": 0, "session": None}

    def cc(self, method: str, path: str, body: bytes | None):
        p = path.split("?", 1)[0]
        if p == "/cc/health":
            with self.lock:
                self.health_calls.append(time.time())
            time.sleep(HEALTH_DELAY)
            return 200, self.health()
        if p == "/cc/systems":
            return 200, {"tiles": [{"id": s, "name": s.upper(), "title": s.upper(), "thread": THREADS[s],
                                    "counts": {}, "detail": {}, "lines": [], "groups": {}} for s in SYSTEMS]}
        if p == "/cc/systems/thread":
            d = json.loads(body or b"{}")
            return 200, {"thread": THREADS.get(d.get("system"), THREADS["world"])}
        if p == "/cc/chat" and method == "POST":
            with self.lock:
                self.chats.append(json.loads(body or b"{}"))
            return 503, {"error": "test bridge: no reasoner here"}
        if p == "/cc/threads":
            return 200, {"threads": [], "archived_count": 0}
        if p == "/cc/permits":
            return 200, {"pending": [], "auto": []}
        return 200, {}

    def start(self):
        self.next_port = free_port()
        app = self.root / "console"
        shutil.copytree(BUILD / ".next" / "standalone", app, symlinks=True)
        shutil.copytree(BUILD / ".next" / "static", app / ".next" / "static")
        if (BUILD / "public").is_dir():
            shutil.copytree(BUILD / "public", app / "public")
        self.node = subprocess.Popen(["node", "server.js"], cwd=str(app), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env=dict(os.environ, PORT=str(self.next_port), HOSTNAME="127.0.0.1", NEXT_TELEMETRY_DISABLED="1"))
        wait_port(self.next_port)
        nport, h = self.next_port, self

        class Front(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code: int, data: bytes, ctype: str = "application/json", headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                if not headers:
                    self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

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
                    return self._send(200, json.dumps(API.get(p, {})).encode())
                if path == "/cc" or path.startswith("/cc/"):
                    code, d = h.cc(self.command, path, body)
                    return self._send(code, json.dumps(d).encode())
                hdr = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection")}
                req = urllib.request.Request(f"http://127.0.0.1:{nport}{path}", data=body, method=self.command, headers=hdr)
                try:
                    r = urllib.request.urlopen(req, timeout=60)
                    code, rh, data = r.status, r.headers, r.read()
                except urllib.error.HTTPError as e:
                    code, rh, data = e.code, e.headers, e.read()
                self._send(code, data, headers=dict(rh.items()))

            do_GET = do_POST = do_HEAD = _go

        self.front = ThreadingHTTPServer(("127.0.0.1", 0), Front)
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.front.server_address[1]}"
        return self

    def stop(self):
        try:
            self.front.shutdown()
        except Exception:
            pass
        try:
            self.node.terminate(); self.node.wait(10)
        except Exception:
            pass


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="panes-health-"))
    h = Harness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def launch(p):
    if CHROME_LIBS.is_dir():
        env = dict(os.environ, LD_LIBRARY_PATH=f"{CHROME_LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":"))
        return p.chromium.launch(env=env)
    return p.chromium.launch()


def panes(page):
    """The chat frames on /systems (central + open systems), by their pane name."""
    out = {}
    for f in page.frames:
        if "pane=" in f.url:
            out[f.url.split("pane=", 1)[1].split("&", 1)[0]] = f
    return out


def open_systems(h, p, errors):
    b = launch(p)
    page = b.new_page(viewport={"width": 1600, "height": 1000})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("try { localStorage.clear() } catch (e) {}")
    with h.lock:
        h.health_calls.clear(); h.chats.clear()
    t0 = time.time()
    page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS), wait_until="domcontentloaded")
    end = time.time() + 20
    while time.time() < end:
        fs = panes(page)
        if len(fs) >= 5 and all(f.query_selector("textarea") for f in fs.values()):
            break
        page.wait_for_timeout(100)
    return b, page, t0


def test_boxes_open_while_health_is_out_and_held_message_lands(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    h.logged_in = True
    with sync_playwright() as p:
        b, page, t0 = open_systems(h, p, errors)
        fs = panes(page)
        assert len(fs) == 5, f"expected the central chat and four panes, got {sorted(fs)}"
        took = time.time() - t0
        assert took < HEALTH_DELAY, f"frames took {took:.1f} s to show their boxes; the check is {HEALTH_DELAY} s"
        for name, f in fs.items():
            box = f.query_selector("textarea")
            assert box.is_enabled(), f"{name}: box disabled while health is out"
            ph = box.get_attribute("placeholder") or ""
            assert NO_REASONER not in ph, f"{name}: '{ph}' before the check answered"
        # type into pane b and send before the check answers: held, not lost
        fb = fs["sys-b"]
        fb.fill("textarea", "hello from the opening pane")
        fb.press("textarea", "Enter")
        fb.wait_for_selector("text=held: sends when your brain answers", timeout=2000)
        assert not h.chats, "sent before the check answered"
        # the check answers: the held message goes to b's own thread
        end = time.time() + HEALTH_DELAY + 10
        while time.time() < end and not h.chats:
            page.wait_for_timeout(100)
        assert h.chats, "the held message was never sent"
        msg = h.chats[0]
        assert "hello from the opening pane" in json.dumps(msg)
        assert msg.get("thread") == THREADS["b"] or THREADS["b"] in json.dumps(msg), msg
        assert len(h.chats) == 1, h.chats
        # one shared health check for five frames at opening (all asked within the first second)
        first = [c for c in h.health_calls if c - h.health_calls[0] < 1.0]
        assert len(first) == 1, f"{len(first)} /cc/health calls at opening for five frames"
        for name, f in panes(page).items():
            ph = f.query_selector("textarea").get_attribute("placeholder") or ""
            assert NO_REASONER not in ph, f"{name}: '{ph}' though signed in"
        page.screenshot(path=os.environ.get("PANES_SHOT", str(Path(tempfile.gettempdir()) / "panes-health.png")))
        b.close()
    assert not errors, errors


def test_no_reasoner_shows_only_after_the_answer_and_held_text_returns(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    h.logged_in = False
    try:
        with sync_playwright() as p:
            b, page, t0 = open_systems(h, p, errors)
            fs = panes(page)
            assert len(fs) == 5
            for name, f in fs.items():
                ph = f.query_selector("textarea").get_attribute("placeholder") or ""
                assert NO_REASONER not in ph, f"{name}: '{ph}' before the check answered"
            fc = fs["sys-c"]
            fc.fill("textarea", "kept words")
            fc.press("textarea", "Enter")
            fc.wait_for_selector("text=held: sends when your brain answers", timeout=2000)
            fc.wait_for_function(f"() => (document.querySelector('textarea').placeholder || '').includes('{NO_REASONER}')",
                                 timeout=(HEALTH_DELAY + 10) * 1000)
            assert time.time() - t0 >= HEALTH_DELAY - 0.5
            assert fc.query_selector("textarea").input_value().strip() == "kept words"
            assert not h.chats
            b.close()
    finally:
        h.logged_in = True
    assert not errors, errors
