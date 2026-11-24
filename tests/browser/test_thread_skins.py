"""tests/browser/test_thread_skins.py: a thread's skin belongs to that thread, in a real browser (SKIN-4, 2026-11-24).

hbar 2026-11-24: "I WANT SKINS TO CHANGE INDIVIDUALLY BY THREAD AND STOP RECHANGING COLOR WHEN I OPEN NEW THREAD,
OR RELOAD THE PAGE OR ANYTHING ELSE AS SUCH." (after "open the thread" on a report card turned a thread black and
gold, and changing one thread's colour changed other threads).

    Chromium (Playwright) -> a fake bridge + api (this file; one port, the rest proxied)
                          -> the built console (next standalone server.js)

The fake bridge keeps threads, their `style` and the console default in memory, with the box's own rules
(scripts/cc/cc_skin.py: what a style may hold, what a child thread takes from its parent, the default's shape).
It filters /cc/threads like the box (search, archive), answers it after a short wait (a slow box), and serves a
layout file with the "black" colours, so the six cases see what his browser sees:
  a  set thread A's skin, open thread B: each keeps its own (B archived, so not in the list)
  b  a choices button of mode "agent": the parent keeps its skin; the new thread starts in the parent's
  c  reload: the same skin from the first frame to the last
  d  two tabs on two threads: changing one never changes the other, live or after a reload
  e  the thread list (searched, archive), /board, /systems and /panes never overwrite a thread's skin
  f  a thread with no skin of its own wears the default; changing the default touches only those, on every device
Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")

REPO = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("NOUS_CONSOLE_BUILD", str(REPO / "ui")))
SERVER_JS = BUILD / ".next" / "standalone" / "server.js"
SHOTS = os.environ.get("SKIN4_SHOTS")   # a directory: each case leaves its screenshots there
CHROME_LIBS = Path(os.environ.get("NOUS_CHROME_LIBS", str(Path.home() / ".local/chromelibs/root/usr/lib/aarch64-linux-gnu")))

pytestmark = pytest.mark.skipif(not SERVER_JS.exists(), reason=f"no console build at {BUILD} (npm ci && npm run build)")

_spec = importlib.util.spec_from_file_location("cc_skin_rules", REPO / "scripts" / "cc" / "cc_skin.py")
cc_skin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc_skin)

READ = "[document.documentElement.dataset.theme || null, document.documentElement.dataset.font || null]"
# every value <html data-theme> ever takes in a document, from the first script on (a flash counts)
WATCH = """(() => { window.__themes = [];
  const note = () => { const h = document.documentElement; const t = h && h.getAttribute('data-theme'); if (t && window.__themes[window.__themes.length - 1] !== t) window.__themes.push(t) };
  note(); new MutationObserver(note).observe(document, { attributes: true, childList: true, subtree: true, attributeFilter: ['data-theme'] }) })()"""
BLACK = {"--bg": "#000000", "--surface": "#050505", "--surface2": "#0b0b0b", "--text": "#e6e6e6", "--muted": "#7a7a7a",
         "--border": "#1c1c1c", "--user-bg": "#e6e6e6", "--user-text": "#000000", "--code-bg": "#000000"}

SEED = {
    "t-a": {"brain": "t-a", "title": "Deck pass", "started": "2026-11-24T08:00:00Z", "last": "2026-11-24T09:00:00Z", "style": {"skin": "rose", "font": "lora"}},
    "t-b": {"brain": "t-b", "title": "Loops with father", "started": "2026-11-23T08:00:00Z", "last": "2026-11-23T09:00:00Z", "style": {"skin": "fox", "font": "jetbrains"}, "archived": True},
    "t-n": {"brain": "t-n", "title": "Groceries", "started": "2026-11-22T08:00:00Z", "last": "2026-11-22T09:00:00Z"},
}
HIST = {"t-a": "Slides 1-3 shown.", "t-b": "The four-bar bass first.", "t-n": "Milk, eggs, coffee.", "t-child": "Started from the deck pass."}


class Fake:
    threads: dict = {}
    default: dict = {}
    calls: list = []
    next_port = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.threads = copy.deepcopy(SEED)
            cls.default = {}
            cls.calls = []


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}"), raw
        except ValueError:
            return {}, raw

    def _fake(self, req):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, dict(urllib.parse.parse_qsl(u.query))
        Fake.calls.append((self.command, p, req if self.command == "POST" else q))
        T = Fake.threads
        if p == "/cc/health":
            return {"ok": True, "auth": {"loggedIn": True}, "box": True, "posture": "cards", "runs": []}
        if p == "/cc/threads":
            time.sleep(0.8)   # a box that takes a moment: nothing may paint the default meanwhile
            items = [dict(x) for x in T.values()]
            a = q.get("archived")
            items = [x for x in items if x.get("archived")] if a == "only" else items if a == "1" else [x for x in items if not x.get("archived")]
            if q.get("q", "").strip():
                items = [x for x in items if q["q"].strip().casefold() in (x["title"] + " " + x["brain"]).casefold()]
            return {"threads": items, "archived_count": sum(1 for x in T.values() if x.get("archived"))}
        if p == "/cc/threads/style":
            th = T.get(q.get("brain", ""))
            return (404, {"ok": False}) if th is None else {"ok": True, "style": cc_skin.thread_style(th.get("style")) or {}}
        if p == "/cc/threads/update":
            th = T.get(req.get("brain"))
            if th is None:
                return 404, {"ok": False}
            if "style" in req:
                st = cc_skin.thread_style(req.get("style")) or {}
                if st:
                    th["style"] = st
                else:
                    th.pop("style", None)
            return {"ok": True, "thread": th}
        if p == "/cc/skin":
            if self.command == "POST":
                Fake.default.update(cc_skin.default_skin(req))
            return {"ok": True, **Fake.default}
        if p == "/cc/chat":
            # a choices button of mode "agent" (REPORT-1): a thread of its own, linked to its parent; the box's rule
            # for its look (cc_skin.child_style, as scripts/cc/cc-bridge.py _inherit_style applies it)
            parent = req.get("parent")
            child = {"brain": "t-child", "title": "CC: " + str(req.get("message", ""))[:40], "started": "2026-11-24T10:00:00Z", "last": "2026-11-24T10:00:00Z"}
            if parent in T:
                st = cc_skin.child_style(T[parent].get("style"))
                if st:
                    child["style"] = st
            T["t-child"] = child
            return {"thread": "t-child", "reply": "started", "title": child["title"]}
        if p == "/cc/layout":
            return {"layout": {"theme": "black"}, "resolved": {"vars": BLACK, "zoom": 1.0, "weight": None}}
        if p.startswith("/api/bf/sessions/") and p.endswith("/messages"):
            sid = p.split("/")[4]
            return {"messages": [{"role": "assistant", "content": HIST.get(sid, "..."), "created_at": "2026-11-24T09:00:00Z"}]}
        if p == "/cc/board":
            return {"tiles": [{"id": "t-a", "kind": "thread", "title": "Deck pass", "href": "/talk?thread=t-a", "state": "idle"}]}
        if p.startswith("/cc/") or p.startswith("/api/bf/") or p.startswith("/claude/") or p.startswith("/api/"):
            return {}
        return None

    def _proxy(self, raw):
        req = urllib.request.Request(f"http://127.0.0.1:{Fake.next_port}{self.path}", data=raw or None, method=self.command,
                                     headers={k: v for k, v in self.headers.items() if k.lower() not in ("host", "accept-encoding", "content-length")})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, body, ct = r.status, r.read(), r.headers.get("Content-Type", "text/html")
        except urllib.error.HTTPError as e:
            code, body, ct = e.code, e.read(), e.headers.get("Content-Type", "text/html")
        self._send(code, body, ct)

    def do_GET(self):
        req, raw = self._body() if self.command == "POST" else ({}, b"")
        ans = self._fake(req)
        if ans is None:
            return self._proxy(raw)
        code, body = ans if isinstance(ans, tuple) else (200, ans)
        self._send(code, body)

    do_POST = do_GET


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 40.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"port {port} never opened")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("console") / "standalone"
    shutil.copytree(SERVER_JS.parent, d, symlinks=True)
    if not (d / ".next" / "static").exists():
        shutil.copytree(BUILD / ".next" / "static", d / ".next" / "static")
    if (BUILD / "public").exists() and not (d / "public").exists():
        shutil.copytree(BUILD / "public", d / "public")
    Fake.next_port = _free_port()
    env = dict(os.environ, PORT=str(Fake.next_port), HOSTNAME="127.0.0.1")
    proc = subprocess.Popen(["node", "server.js"], cwd=d, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_port(Fake.next_port)
    srv = ThreadingHTTPServer(("127.0.0.1", _free_port()), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    proc.terminate()
    proc.wait(10)


@pytest.fixture()
def browser(base):
    Fake.reset()
    with sync_api.sync_playwright() as p:
        env = dict(os.environ, LD_LIBRARY_PATH=f"{CHROME_LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}".rstrip(":")) if CHROME_LIBS.is_dir() else None
        b = p.chromium.launch(env=env) if env else p.chromium.launch()
        yield b
        b.close()


def _ctx(browser, base, local: dict | None = None):
    """One browser profile (one localStorage, so storage events cross its tabs, as in his browser)."""
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script(WATCH)
    seed = {"cc.toolline": "1", **(local or {})}
    ctx.add_init_script("(() => { if (sessionStorage.getItem('__seeded')) return; sessionStorage.setItem('__seeded', '1');"
                        f" const s = {json.dumps(seed)}; for (const k in s) {{ if (localStorage.getItem('__seeded_' + k)) continue;"
                        " localStorage.setItem(k, s[k]); localStorage.setItem('__seeded_' + k, '1') } })()")
    ctx.errors = []
    return ctx


def _tab(ctx, base, path, settle=2600):
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: ctx.errors.append(f"{path}: {e}"))
    pg.goto(base + path, wait_until="load")
    pg.wait_for_timeout(settle)
    return pg


def _skin(pg):
    return pg.evaluate(READ)


def _themes(pg):
    return pg.evaluate("window.__themes")


def _bg(pg):
    return pg.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase()")


def _shot(pg, name):
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(Path(SHOTS) / f"{name}.png"))


def _press_skin(pg, skin):
    pg.locator("[data-skin-scope]").wait_for(timeout=15000)
    pg.get_by_text(skin, exact=True).first.click()
    pg.wait_for_timeout(1500)   # the tool line writes 500 ms after the last touch


def _stored(brain):
    return (Fake.threads.get(brain) or {}).get("style") or {}


def test_a_open_thread_b_each_keeps_its_own(browser, base):
    ctx = _ctx(browser, base)
    A = _tab(ctx, base, "/talk?thread=t-a")
    assert _skin(A)[0] == "rose"
    _press_skin(A, "sage")
    assert _skin(A)[0] == "sage" and _stored("t-a").get("skin") == "sage"
    # open thread B in the same tab, as the board's tile does (B is archived, so not in the thread list)
    A.evaluate("window.postMessage({ type: 'cc-open-thread', thread: 't-b' }, location.origin)")
    A.wait_for_timeout(2600)
    _shot(A, "a-thread-b-after-open")
    assert _skin(A) == ["fox", "jetbrains"], "thread B must wear its own skin"
    assert _stored("t-a").get("skin") == "sage" and _stored("t-b").get("skin") == "fox"
    A.goto(base + "/talk?thread=t-a"); A.wait_for_timeout(2600)
    _shot(A, "a-thread-a-back")
    assert _skin(A)[0] == "sage"
    assert not ctx.errors, ctx.errors


def test_b_agent_choice_parent_keeps_child_inherits(browser, base):
    ctx = _ctx(browser, base)
    A = _tab(ctx, base, "/talk?thread=t-a")
    A.evaluate("window.__themes = [document.documentElement.dataset.theme]")   # from the press on
    A.evaluate("window.postMessage({ type: 'cc-thread', text: 'walk the deck slide by slide', label: 'deck pass' }, location.origin)")
    A.wait_for_timeout(3500)
    _shot(A, "b-parent-after-agent")
    assert _skin(A)[0] == "rose" and set(_themes(A)) == {"rose"}, _themes(A)
    assert _stored("t-a") == SEED["t-a"]["style"], "the parent's look is never rewritten"
    child = _tab(ctx, base, "/talk?thread=t-child")
    _shot(child, "b-child-thread")
    assert _skin(child) == ["rose", "lora"], "a thread started from a thread starts in its parent's skin"
    _press_skin(child, "ocean")
    assert _stored("t-child").get("skin") == "ocean" and _stored("t-a").get("skin") == "rose"
    assert _skin(A)[0] == "rose"
    # the same rule for the "new thread" button: the blank conversation opened from A still wears A's skin
    A.get_by_text("new thread", exact=True).first.click()
    A.wait_for_timeout(1500)
    _shot(A, "b-new-thread-from-a")
    assert _skin(A) == ["rose", "lora"], "a new thread opened from a thread starts in that thread's skin"
    assert _stored("t-a") == SEED["t-a"]["style"]
    assert not ctx.errors, ctx.errors


def test_c_reload_same_skin_from_first_frame(browser, base):
    ctx = _ctx(browser, base)
    A = _tab(ctx, base, "/talk?thread=t-a")
    assert _skin(A)[0] == "rose"
    for _ in range(2):
        A.reload(wait_until="load"); A.wait_for_timeout(2600)
        assert _themes(A) == ["rose"], f"reload painted {_themes(A)}"
    _shot(A, "c-after-reload")
    assert not ctx.errors, ctx.errors


def test_d_two_tabs_two_threads(browser, base):
    # this browser once had the tool line switched to "default" (SKIN-3 remembered it in cc.skinScope)
    ctx = _ctx(browser, base, {"cc.skinScope": "default"})
    A = _tab(ctx, base, "/talk?thread=t-a")
    N = _tab(ctx, base, "/talk?thread=t-n")
    assert _skin(N)[0] == "gold"
    _press_skin(A, "sage")
    N.wait_for_timeout(800)
    _shot(A, "d-tab-a-sage"); _shot(N, "d-tab-n-untouched")
    assert _skin(A)[0] == "sage", "the press in thread A changes thread A"
    assert _themes(N) == ["gold"], f"tab N repainted live: {_themes(N)}"
    N.reload(wait_until="load"); N.wait_for_timeout(2600)
    assert _themes(N) == ["gold"], f"tab N after reload: {_themes(N)}"
    assert Fake.default == {} and "style" not in Fake.threads["t-n"]
    assert not ctx.errors, ctx.errors


def test_e_list_board_systems_panes_never_overwrite(browser, base):
    ctx = _ctx(browser, base)
    A = _tab(ctx, base, "/talk?thread=t-a&threads=1")   # the thread list open beside the thread (NAV-1)
    assert _skin(A)[0] == "rose"
    assert _bg(A) not in ("#000000", "#000"), "the layout file's colours painted over the thread's own skin"
    A.evaluate("window.__themes = [document.documentElement.dataset.theme]")   # from here on (a first-ever open has no cache yet)
    # the thread list, searched for another thread
    box = A.locator("input[aria-label='Search threads']").first
    box.wait_for(timeout=10000)
    box.fill("groceries"); A.wait_for_timeout(2500)
    _shot(A, "e-list-searched")
    assert _skin(A)[0] == "rose", "searching the thread list changed the thread's skin"
    other = [_tab(ctx, base, p) for p in ("/board", "/systems", "/panes")]
    A.wait_for_timeout(1500)
    for pg in other:
        _shot(pg, "e-" + pg.url.rsplit("/", 1)[-1].split("?")[0])
    assert set(_themes(A)) == {"rose"}, _themes(A)
    assert _stored("t-a") == SEED["t-a"]["style"]
    assert not [c for c in Fake.calls if c[1] == "/cc/threads/update" and c[2].get("brain") != "t-a"]
    assert not ctx.errors, ctx.errors


def test_f_default_only_where_no_own_choice(browser, base):
    ctx = _ctx(browser, base)
    N = _tab(ctx, base, "/talk?thread=t-n")
    A = _tab(ctx, base, "/talk?thread=t-a")
    assert _skin(N)[0] == "gold"
    N.locator("[data-skin-scope]").get_by_text("default", exact=True).click()
    _press_skin(N, "ocean")
    A.wait_for_timeout(800)
    _shot(N, "f-no-own-default-ocean"); _shot(A, "f-own-untouched")
    assert _skin(N)[0] == "ocean" and _skin(A)[0] == "rose"
    assert "style" not in Fake.threads["t-n"] and _stored("t-a") == SEED["t-a"]["style"]
    assert Fake.default.get("skin") == "ocean", "the default lives on the box"
    # another device (a fresh browser profile) opens the thread with no skin of its own
    other = _ctx(browser, base)
    N2 = _tab(other, base, "/talk?thread=t-n")
    _shot(N2, "f-other-device")
    assert _skin(N2)[0] == "ocean"
    assert not ctx.errors and not other.errors, ctx.errors + other.errors
