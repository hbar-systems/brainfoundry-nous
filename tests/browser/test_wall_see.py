"""tests/browser/test_wall_see.py: the wall, seen and entered (WALL-6, 2026-11-26).

hbar: "the wall needs fixing to see ... it just lets me see the current system but not so much easy", "it opens and
loads too slow", and "can i only send this? i cant type a message and it will go through?".

    Chromium (Playwright) -> a front (test_panes_health.Harness): /cc/* answered by a small fake bridge that keeps the
    wall's setting in memory, logs every request, and can be slowed; the rest to the built console (next standalone).

Checks, on /wall in the orbit: at rest each body shows its now-line and the centre shows today's lines with their
times; one press on a name opens the entered card with its box EMPTY and focused, its shortcuts as chips and its latest
link; a chip fills the box and sends nothing; Enter sends what is typed (one POST to the thread's say door); Esc goes
back; the symbol enters the brain; on a second visit with the bridge slowed by 3 s the systems are drawn from the last
snapshot within 1.5 s and the card still opens; at 828 x 783 (his window) nothing is cut at an edge. No page error.

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>).

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_wall_see.py -q
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("wall6_panes_health", Path(__file__).with_name("test_panes_health.py"))
_ph = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ph)
BUILD, SERVER_JS, Harness, launch = _ph.BUILD, _ph.SERVER_JS, _ph.Harness, _ph.launch

T = {s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(["world", "sys.music", "sys.film", "sys.media"], 1)}
NOW = {"sys.music": "the set is open at 124 BPM; three empty tracks wait.", "sys.film": "the trailer is cut.", "sys.media": "the night walk draft waits."}


def tile(sid):
    t = {"id": sid, "kind": "work", "thread": T.get(sid), "said": None, "counts": {"running": 0}, "detail": {},
         "jobs": [], "summary": {"text": NOW[sid], "from": "card"} if sid in NOW else None, "tree_n": 0, "domain": "", "open": None,
         "prompts": [], "latest": None}
    if sid == "sys.music":
        t["prompts"] = ["play the intro", "finish dates: ", "which loops are in E minor"]
        t["latest"] = {"label": "the page", "href": "/cc/page/rooms/k2/", "hear": False}
    if sid == "world":
        t["prompts"] = ["what waits for me today, in order"]
    return t


class SeeHarness(Harness):
    def __init__(self, root):
        super().__init__(root)
        self.log: list[tuple[float, str, str, object]] = []
        self.wall = {"look": "orbit", "set": ["sys.music", "sys.film", "sys.media"], "pinned": [], "tz": "Europe/Bratislava"}
        self.slow = 0.0

    def cc(self, method, path, body):
        with self.lock:
            self.log.append((time.time(), method, path, body))
        p = path.partition("?")[0]
        if p == "/cc/systems":
            if self.slow:
                time.sleep(self.slow)
            return 200, {"tiles": [tile(s) for s in T], "running": 0, "built": "x",
                         "waits": {"today": [{"text": "Study day 2: slides 6-10: https://console.example/s/", "due": "2026-11-26T14:00:00Z"},
                                             {"text": "Press Update", "due": "2026-11-26T17:45:00Z"}], "tasks_today": 2}}
        if p == "/cc/surfaces":
            return 200, {"surfaces": [], "skipped": []}
        if p == "/cc/wall":
            if self.slow:
                time.sleep(self.slow)
            if method == "POST":
                return 200, {"ok": True, **self.wall}
            return 200, {**self.wall, "seed": False, "max": 16, "faint": [], "fresh": None, "home": False}
        if p.startswith("/cc/threads/") and p.endswith("/say") and method == "POST":
            return 200, {"ok": True}
        if p == "/cc/health":
            return 200, self.health()
        return super().cc(method, path, body)

    def says(self):
        with self.lock:
            return [json.loads(b) for _, m, p, b in self.log if m == "POST" and p.endswith("/say")]


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="wall-see-"))
    h = SeeHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


MUSIC = ".wo-b[aria-label='sys.music']"


def test_see_enter_send_and_snapshot(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " [data-now-for='sys.music']", timeout=20000)
        # at rest: the now-line under the name, today's lines with times in his zone
        assert "124 BPM" in page.inner_text(MUSIC + " .wo-now")
        page.wait_for_selector("[data-today] li .tm", timeout=5000)
        assert page.locator("[data-today] li .tm").all_inner_texts()[:2] == ["15:00", "18:45"]
        assert page.locator("[data-today] li a.tx").first.inner_text() == "Study day 2: slides 6-10"
        # one press enters: the box is empty and focused, the shortcuts are chips, the latest link is there
        page.click(MUSIC + " .wo-nm")
        page.wait_for_selector(".we-veil[data-enter-for='sys.music']", timeout=3000)
        assert page.input_value(".we-in") == ""
        assert page.evaluate("document.activeElement.classList.contains('we-in')")
        assert page.locator(".we-chip").all_inner_texts() == ["play the intro", "finish dates:", "which loops are in E minor"]
        assert page.get_attribute("[data-latest-for='sys.music']", "href") == "/cc/page/rooms/k2/"
        # a chip fills the box and sends nothing
        before = len(h.says())
        page.click(".we-chip:has-text('play the intro')")
        page.wait_for_timeout(400)
        assert page.input_value(".we-in") == "play the intro" and len(h.says()) == before
        # his own words: typed, Enter, one send to that system's thread
        page.fill(".we-in", "bring the groove in after 8 bars")
        page.keyboard.press("Enter")
        deadline = time.time() + 5
        while time.time() < deadline and len(h.says()) == before:
            time.sleep(0.1)
        assert [s["message"] for s in h.says()[before:]] == ["bring the groove in after 8 bars"]
        assert page.input_value(".we-in") == ""
        # Esc goes back; the symbol enters the brain
        page.keyboard.press("Escape")
        page.wait_for_selector(".we-veil", state="detached", timeout=3000)
        page.click(".wo-sym")
        page.wait_for_selector(".we-veil[data-enter-for='world']", timeout=3000)
        assert "what waits for me today, in order" in page.inner_text(".we-chips")
        page.click(".we-back")
        page.wait_for_selector(".we-veil", state="detached", timeout=3000)
        # a second visit with a slow bridge: drawn from the last snapshot at once, and it still enters
        h.slow = 3.0
        try:
            t0 = time.time()
            page.goto(h.url + "/wall", wait_until="domcontentloaded")
            page.wait_for_selector(MUSIC + " [data-now-for='sys.music']", timeout=1500)
            drawn = time.time() - t0
            assert page.get_attribute(".wl", "data-snap") == "1"
            page.click(MUSIC + " .wo-nm")
            page.wait_for_selector(".we-veil[data-enter-for='sys.music']", timeout=1500)
        finally:
            h.slow = 0.0
        assert drawn < 1.5
        ctx.close()
        # his window: nothing cut at an edge
        page = b.new_page(viewport={"width": 828, "height": 783})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wo-nm", timeout=20000)
        page.wait_for_timeout(500)
        cut = page.evaluate("""() => [...document.querySelectorAll('.wo-nm, .wo-now, .wo-box, .wo-d, [data-today] li')]
            .map(e => e.getBoundingClientRect()).filter(r => r.width && (r.left < -1 || r.right > innerWidth + 1)).length""")
        assert cut == 0
        b.close()
    assert not errors, errors
