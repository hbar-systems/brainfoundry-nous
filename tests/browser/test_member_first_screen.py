"""tests/browser/test_member_first_screen.py: a member's first screen is their own start page (MEMBER-SCREEN-2, 2026-11-27).

hbar at Anne's sitting 2026-11-27: "she didnt see [her start page] ... she saw the 3 things she had to connect".
Her layout was quiet with start /apps/week, but the console opened the start page only on the load that first
applied the layout in a browser (and only once a day, only at 960 px and up).

    Chromium (Playwright) -> a front (this file): /cc/* and /api/* answered by a small fake member brain (quiet layout,
    the shipped Week app as the start page, a neutral week page on the desk); the rest to the built console.

Checks, at 1440 and 390: on a bare load the Week app covers the console (fresh browser, and a browser that already
applied this layout); the moving-in cards are behind it; one press on Close shows the chat with the cards; the
menu's Chat (?threads=1) does not open it; no page error. Run as a script it serves the front for html-shot.py:

    NOUS_CONSOLE_BUILD=<ui> python tests/browser/test_member_first_screen.py serve   # prints the URL, Ctrl-C ends

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD, default ui/ here).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
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
WEEK_APP = REPO / "brain-apps" / "shipped" / "week" / "index.html"
OUT = "/home/cc/out"

LAYOUT = {"v": 1, "panels": {"hero": False, "hint": False, "nav": False, "tools": False, "inputbuttons": False, "footer": False,
                             "files": True, "board": True, "gallery": True, "handsfree": True, "sidebyside": False},
          "pane": {"side": "right", "width": None}, "column": "narrow", "theme": "default", "vars": {}, "font": None,
          "size": "normal", "weight": "normal", "density": "compact", "text": "16px", "view": "talk", "start": "/apps/week",
          "voice": {"speak": False, "handsfree": False}, "surfaces": None}
WEEK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:system-ui,sans-serif;margin:0;padding:40px 32px;background:#15130f;color:#ece6da}
h1{font-weight:400;font-size:34px;margin:0 0 28px}.rooms{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
.room{border:1px solid #3a352c;border-radius:16px;padding:22px}.room b{display:block;font-size:20px;font-weight:500;margin-bottom:8px}
.room span{color:#a89f8f}</style></head><body><h1>Sam. This is your brain.</h1><div class="rooms">
<div class="room"><b>Lectures</b><span>What was said, in your notes.</span></div>
<div class="room"><b>Study</b><span>This week's reading, one press each.</span></div>
<div class="room"><b>Dates and mail</b><span>What is owed and when.</span></div></div></body></html>"""
ASKS = {"asks": [{"label": "Plan my week", "send": "Plan my week with me."}]}
API = {
    "/apps/list": {"apps": [{"id": "week", "name": "Week", "version": "0.3.0", "enabled": True,
                             "permissions": ["files.read", "chat.send"], "requires_layers": []}], "ccHome": True},
    "/onboarding/first-use": {"steps": [], "complete": True, "fresh": False},
    "/onboarding/welcome": {"seen_version": 999},
    "/v1/federation/peers": {"peers": []},
    "/v1/help/status": {"helper": None, "ready": False, "message": "no helper set", "button": False, "asked": []},
    "/admin/system": {"warnings": []},
    "/documents": {"documents": []},
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


def cc(method: str, path: str):
    p = path.split("?", 1)[0]
    if p == "/cc/health":
        return 200, {"ok": True, "auth": {"loggedIn": True, "email": "member@example.invalid"}, "out": OUT,
                     "codex": {"installed": False, "signedIn": False}, "local": {"configured": False},
                     "runs": [], "cards_waiting": 0, "session": None}
    if p == "/cc/layout":
        return 200, {"layout": LAYOUT, "lang": "en", "pages": {}}
    if p == "/cc/first-run":
        return 200, {"member": True, "finished": True}
    if p == "/cc/files":
        return 200, {"roots": [{"label": "out", "path": OUT}]}
    if p == f"/cc/files/raw{OUT}/week/index.html":
        return 200, WEEK_PAGE
    if p == f"/cc/files/raw{OUT}/week/asks.json":
        return 200, ASKS
    if p == "/cc/threads":
        return 200, {"threads": [], "archived_count": 0}
    if p == "/cc/permits":
        return 200, {"pending": [], "auto": []}
    if p.startswith("/cc/files/raw"):
        return 404, {"error": "not here"}
    return 200, {}


class Harness:
    def __init__(self, root: Path):
        self.root = root

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
        nport = self.next_port

        class Front(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, data, ctype="application/json", headers=None):
                if not isinstance(data, bytes):
                    ctype = "text/html; charset=utf-8" if isinstance(data, str) else ctype
                    data = data.encode() if isinstance(data, str) else json.dumps(data).encode()
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
                if path.split("?", 1)[0] == "/api/bf/apps/week/index.html":
                    return self._send(200, WEEK_APP.read_bytes(), "text/html; charset=utf-8")
                if path.startswith("/api/"):
                    p = path.split("?", 1)[0]
                    for pre in ("/api/bf", "/api"):
                        if p.startswith(pre + "/"):
                            p = p[len(pre):]
                            break
                    return self._send(200, API.get(p, {}))
                if path == "/cc" or path.startswith("/cc/"):
                    return self._send(*cc(self.command, path))
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
    root = Path(tempfile.mkdtemp(prefix="member-screen-"))
    h = Harness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def launch(p):
    if CHROME_LIBS.is_dir():
        env = dict(os.environ, LD_LIBRARY_PATH=f"{CHROME_LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":"))
        return p.chromium.launch(env=env)
    return p.chromium.launch()


START = 'iframe[src="/apps/week"]'


def covered(page, w, h):
    """The Week app's frame covers the middle of the screen (nothing of the chat shows there)."""
    page.wait_for_selector(START, timeout=15000)
    box = page.locator(START).bounding_box()
    return box is not None and box["width"] >= w - 2 and box["x"] <= 1 and box["height"] >= h * 0.7


@pytest.mark.parametrize("w,h", [(1440, 900), (390, 844)])
def test_member_opens_on_the_start_page(harness, w, h):
    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    with sync_playwright() as p:
        b = launch(p)
        for applied in (False, True):   # a fresh browser, and one that already applied this layout (Anne's)
            page = b.new_page(viewport={"width": w, "height": h})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(harness.url + "/", wait_until="domcontentloaded")
            if applied:   # the second load: cc.layout.applied and cc.start.day are set, as in Anne's browser
                page.wait_for_selector(START, timeout=15000)
                assert page.evaluate("localStorage.getItem('cc.layout.applied')")
                page.goto(harness.url + "/", wait_until="domcontentloaded")
            assert covered(page, w, h), f"start page not the first screen at {w} (applied={applied})"
            page.close()
        # one press on Close: the chat, with the moving-in cards
        page = b.new_page(viewport={"width": w, "height": h})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(harness.url + "/", wait_until="domcontentloaded")
        assert covered(page, w, h)
        page.get_by_role("button", name="Close").click()
        page.wait_for_selector(START, state="detached", timeout=5000)
        page.wait_for_selector(".mi-card", timeout=10000)
        assert page.locator(".mi-card").first.is_visible()
        # the menu's Chat (?threads=1) is the chat, not the start page
        page.goto(harness.url + "/?threads=1", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        assert page.locator(START).count() == 0
        page.close()
        b.close()
    assert not errors, errors


if __name__ == "__main__" and sys.argv[1:] == ["serve"]:
    root = Path(tempfile.mkdtemp(prefix="member-screen-"))
    hh = Harness(root).start()
    print(hh.url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        hh.stop()
        shutil.rmtree(root, ignore_errors=True)
