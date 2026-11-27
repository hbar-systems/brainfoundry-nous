"""tests/browser/test_panes_focus.py: one pane of /systems read large and back, nothing lost (PANES-FOCUS-1, 2026-11-27).

hbar 2026-11-27, four panes open: "should be possibility to click any one of these and it expands to most of the
screen so I can read it much better ... and then an easy exit back so we see all four".

    Chromium (Playwright) -> a front (this file): /cc/* and the thread reads answered by a small fake bridge with demo
    threads long enough to scroll; the rest to the built console (next standalone). Nothing is sent anywhere.

Checks: /systems?open=a,b,c,d shows the central chat and four panes; in the grid a pane's tools strip is its one mark
(no seat line); a press on c's title bar grows c to most of the width at full height, the others become title bars
beside with their marks, and c's strip shows the seat line again; a press on a bar in the strip moves the focus; Esc
goes back to the grid with b's typed draft and c's scroll kept and no frame loaded again; the focus survives a reload;
Esc from inside the focused pane (outside its box) comes back too; no turn is sent (no chat, say or steer door). No page error.
PANES_FOCUS_SHOTS=<dir> also saves grid.png and focus.png there.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_panes_focus.py -q
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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("NOUS_CONSOLE_BUILD", str(REPO / "ui")))
SERVER_JS = BUILD / ".next" / "standalone" / "server.js"
CHROME_LIBS = Path(os.environ.get("NOUS_CHROME_LIBS", str(Path.home() / ".local/chromelibs/root/usr/lib/aarch64-linux-gnu")))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache" / "ms-playwright"))

SYSTEMS = ["hbar.media", "brainfoundry", "hbar.security", "hbar.systems"]
THREADS = {s: f"{i:08x}-0000-4000-8000-00000000000{i}" for i, s in enumerate(["world"] + SYSTEMS, 1)}
BY_T = {v: k for k, v in THREADS.items()}
NOW = datetime.now(timezone.utc)
# demo marks: jobs running, open rows and the ones that wait on him, the last turn (all "(demo)")
MARKS = {"world": (3, 12, 4, 6), "hbar.media": (1, 9, 2, 40), "brainfoundry": (2, 31, 5, 3),
         "hbar.security": (0, 6, 1, 95), "hbar.systems": (1, 14, 0, 18)}

API = {
    "/apps/list": {"apps": [], "ccHome": True},
    "/onboarding/first-use": {"steps": [], "complete": True, "fresh": False},
    "/onboarding/welcome": {"seen_version": 999},
    "/v1/federation/peers": {"peers": []},
    "/v1/help/status": {"helper": None, "ready": False, "message": "no helper set", "button": True, "asked": []},
    "/admin/system": {"warnings": []},
}

PARA = ("(demo) {sid}: the second pass is done. The photographs are out of the library, web-sized, location stripped; "
        "the originals were not touched and their checksums match. Next is the draft cut on the bars, then a listen pass "
        "before anything goes further. Nothing waits for you here except the one decision named below.")


def messages(sid: str) -> list:
    out = []
    for i in range(9):
        out.append({"role": "user", "content": f"(demo) {sid}: where are we on part {i + 1}?"})
        out.append({"role": "assistant", "content": f"**Part {i + 1}.** " + PARA.format(sid=sid) + "\n\n- one line done\n- one line running\n- one line yours"})
    return out


def tile(sid: str) -> dict:
    run, n, his, mins = MARKS.get(sid, (0, 0, 0, 0))
    at = (NOW - timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": sid, "description": sid, "kind": "work", "thread": THREADS.get(sid),
            "counts": {"running": run, "done_today": 1, "tasks": his, "next": max(0, n - his)},
            "detail": {k: {"count": 0, "lines": []} for k in ("running", "done_today", "tasks", "next")},
            "open_rows": {"n": n, "his": his}, "said": {"text": "(demo) last line", "live": False, "waiting": False, "at": at},
            "lines": [], "more": [], "jobs": []}


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
    """The built console + a front that answers /cc and the thread reads itself (demo data, nothing sent)."""

    def __init__(self, root: Path, port: int = 0):
        self.root, self.port = root, port
        self.posts: list[str] = []
        self.lock = threading.Lock()

    def cc(self, method: str, path: str, body: bytes | None):
        p = path.split("?", 1)[0]
        if method == "POST" and p not in ("/cc/systems/thread", "/cc/client-error", "/cc/view"):
            with self.lock:
                self.posts.append(p)
        if p == "/cc/health":
            return 200, {"ok": True, "auth": {"loggedIn": True, "email": None}, "codex": {"installed": True, "signedIn": True, "method": "chatgpt"},
                         "local": {"configured": False}, "runs": [], "cards_waiting": 0, "session": None, "box": True, "posture": "cards"}
        if p == "/cc/systems":
            return 200, {"tiles": [tile(s) for s in ["world"] + SYSTEMS], "running": 7, "built": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if p == "/cc/systems/thread":
            d = json.loads(body or b"{}")
            return 200, {"thread": THREADS.get(d.get("system"), THREADS["world"])}
        if p == "/cc/threads":
            return 200, {"threads": [{"brain": t, "title": f"CC: {s}: standing thread"} for s, t in THREADS.items()], "archived_count": 0}
        if p == "/cc/permits":
            return 200, {"pending": [], "auto": []}
        if p == "/cc/surfaces":
            return 200, {"surfaces": []}
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
                    if p.startswith("/sessions/") and p.endswith("/messages"):
                        sid = BY_T.get(p.split("/")[2], "world")
                        return self._send(200, json.dumps({"messages": messages(sid)}).encode())
                    if self.command == "POST":
                        with h.lock:
                            h.posts.append(p)
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

        self.front = ThreadingHTTPServer(("127.0.0.1", self.port), Front)
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
    root = Path(tempfile.mkdtemp(prefix="panes-focus-"))
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
    out = {}
    for f in page.frames:
        if "pane=" in f.url:
            out[f.url.split("pane=", 1)[1].split("&", 1)[0]] = f
    return out


def aside(page, sid):
    return page.locator(f'aside[aria-label="{"central" if sid == "world" else sid} thread"]')


def box(page, sid):
    return aside(page, sid).bounding_box()


def text_of(frame):
    return frame.evaluate("document.body.innerText")


def test_focus_grows_moves_and_returns_with_nothing_lost(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    shots = os.environ.get("PANES_FOCUS_SHOTS")
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS), wait_until="domcontentloaded")
        end = time.time() + 25
        while time.time() < end:
            fs = panes(page)
            if len(fs) >= 5 and all(f.query_selector("textarea") and f.query_selector(".cc-conv") for f in fs.values()):
                break
            page.wait_for_timeout(150)
        fs = panes(page)
        assert len(fs) == 5, sorted(fs)
        page.wait_for_timeout(1200)
        loads = []
        page.on("framenavigated", lambda f: f != page.main_frame and loads.append(f.url))
        with h.lock:
            h.posts.clear()
        # the grid: every pane's tools strip is its one mark, no seat line
        for name, f in fs.items():
            t = text_of(f)
            assert "tools ▸" in t.lower() or "TOOLS ▸" in t, f"{name}: no tools mark"
            assert "SEAT" not in t.upper().split("TOOLS", 1)[-1][:400] or not f.query_selector("text=Codex"), f"{name}: seat line shown in the grid"
        # the marks right of the name
        head = aside(page, "brainfoundry").locator(".sy-marks").inner_text()
        assert "2" in head and "31 open" in head and "5 yours" in head, head
        # a draft in one pane, a scroll in another
        fb, fc = fs["sys-hbar.media"], fs["sys-hbar.security"]
        fb.fill("textarea", "a draft that must stay")
        fc.evaluate("document.querySelector('.cc-conv').scrollTop = 300")
        page.wait_for_timeout(200)
        top = fc.evaluate("document.querySelector('.cc-conv').scrollTop")
        assert top > 100, top
        if shots:
            page.screenshot(path=str(Path(shots) / "grid.png"))
        grid = {s: box(page, s) for s in ["world"] + SYSTEMS}
        # press the security pane's title bar
        aside(page, "hbar.security").locator(".sy-nmb").click()
        page.wait_for_timeout(450)
        big = box(page, "hbar.security")
        assert big["width"] > 0.7 * 1440 and big["height"] > 0.8 * (900 - 60), big
        for s in ["world", "hbar.media", "brainfoundry", "hbar.systems"]:
            bb = box(page, s)
            assert bb["width"] < 0.25 * 1440 and bb["height"] < 120, (s, bb)
            assert "mini" in (aside(page, s).get_attribute("class") or "")
        assert "31 open" in aside(page, "brainfoundry").inner_text()           # the strip keeps its marks
        page.wait_for_timeout(300)
        assert fc.query_selector("text=Codex") is not None, "the focused pane's strip does not show the seat line"
        assert page.evaluate("localStorage.getItem('cc.systems.focus')") == "hbar.security"
        if shots:
            page.screenshot(path=str(Path(shots) / "focus.png"))
        # a press on a bar in the strip moves the focus
        aside(page, "brainfoundry").locator(".sy-ph").click()
        page.wait_for_timeout(450)
        assert box(page, "brainfoundry")["width"] > 0.7 * 1440
        assert "mini" in (aside(page, "hbar.security").get_attribute("class") or "")
        # Esc: back to the grid exactly
        page.keyboard.press("Escape")
        page.wait_for_timeout(450)
        for s in ["world"] + SYSTEMS:
            bb = box(page, s)
            assert abs(bb["x"] - grid[s]["x"]) < 2 and abs(bb["width"] - grid[s]["width"]) < 2 and abs(bb["height"] - grid[s]["height"]) < 2, (s, bb, grid[s])
        assert fb.query_selector("textarea").input_value() == "a draft that must stay"
        assert abs(fc.evaluate("document.querySelector('.cc-conv').scrollTop") - top) < 2
        assert loads == [], f"frames loaded again: {loads}"
        assert page.evaluate("localStorage.getItem('cc.systems.focus')") is None
        # the corner mark grows it too; a press on the focused bar goes back
        aside(page, "hbar.systems").locator('button[aria-label^="read hbar.systems large"]').last.click()
        page.wait_for_timeout(450)
        assert box(page, "hbar.systems")["width"] > 0.7 * 1440
        aside(page, "hbar.systems").locator(".sy-nmb").click()
        page.wait_for_timeout(450)
        assert box(page, "hbar.systems")["width"] < 0.5 * 1440
        # Esc from inside the focused pane, outside its text box
        aside(page, "hbar.media").locator(".sy-nmb").click()
        page.wait_for_timeout(450)
        # (a press on an answer line opens a reply slot, which takes the first Esc itself: LINE-TALK-1)
        fs["sys-hbar.media"].evaluate("document.activeElement && document.activeElement.blur()")
        fs["sys-hbar.media"].press("body", "Escape")
        page.wait_for_timeout(450)
        assert box(page, "hbar.media")["width"] < 0.5 * 1440, "Esc inside the pane did not come back"
        assert loads == [], f"frames loaded again: {loads}"
        # the focus survives a reload
        aside(page, "brainfoundry").locator(".sy-nmb").click()
        page.wait_for_timeout(450)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector('aside[aria-label="brainfoundry thread"].focus', timeout=15000)
        assert box(page, "brainfoundry")["width"] > 0.7 * 1440
        with h.lock:
            sent = [x for x in h.posts if x in ("/cc/chat", "/cc/steer") or x.endswith("/say") or "/sessions/" in x]
            assert sent == [], sent                                              # nothing was sent (read marks may be)
        b.close()
    assert not errors, errors


def test_phone_focus_is_full_screen_with_back(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS) + "&focus=brainfoundry", wait_until="domcontentloaded")
        page.wait_for_selector('aside[aria-label="brainfoundry thread"].show', timeout=15000)
        bb = box(page, "brainfoundry")
        assert bb["width"] >= 389 and bb["height"] > 600, bb
        aside(page, "brainfoundry").locator(".sy-back").click()
        page.wait_for_timeout(300)
        assert not aside(page, "brainfoundry").is_visible()
        assert page.evaluate("localStorage.getItem('cc.systems.focus')") is None
        b.close()
    assert not errors, errors
