"""tests/browser/test_wall_instruments.py: a system's instruments on the orbit (WALL-5, 2026-11-24).

hbar, on the live wall: "okay but where is my musical surfaces tho those i wanted actually -- i want to create more
than the hbar.ink". The register (GET /cc/surfaces) gives a system its instruments; a press on the name fans them out,
a press on one opens it beside, Esc folds them back, a pinned one stays out and survives a reload.

    Chromium (Playwright) -> a front (test_panes_health.Harness): /cc/* answered by a small fake bridge that keeps the
    wall's setting in memory and logs every request; the rest to the built console (next standalone).

Checks, on /wall in the orbit at 1440: at rest only the pinned instrument is out and the box is there; a press on the
name fans every instrument out and opens nothing; Esc folds them; a press on one opens its page beside (no thread); an
`ask` one fills the system's box and sends nothing; with the fan out, the next press on the name opens the thread
beside; a hover fans a system out and leaving folds it; the pin mark saves {pinned} on the bridge and the pin is there
after a reload. At 390 the fan is a row under the name. No page error.

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>).

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_wall_instruments.py -q
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("wall5_panes_health", Path(__file__).with_name("test_panes_health.py"))
_ph = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ph)
BUILD, SERVER_JS, Harness, launch = _ph.BUILD, _ph.SERVER_JS, _ph.Harness, _ph.launch

T = {s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(["world", "sys.music", "sys.film"], 1)}
SURFACES = [
    {"name": "film", "system": "sys.film", "say": ["film"], "hue": "#3f6a6a", "line": "", "mark": "frames", "actions": [],
     "instruments": [{"name": "k2", "label": "K2", "open": "/cc/page/rooms/k2/", "on": ["sys.music", "sys.film"], "hue": "#8c8c86", "mark": "frames", "note": ""},
                     {"name": "cut", "label": "cut", "open": "/cc/page/rooms/film/", "on": ["sys.film"], "hue": "#3f6a6a", "mark": "frames", "note": ""}]},
    {"name": "music", "system": "sys.music", "say": ["music"], "hue": "#b5532f", "line": "", "mark": "wave", "actions": [],
     "instruments": [{"name": "sing", "label": "sing", "open": "/sing", "on": ["sys.music"], "hue": "#c8643a", "mark": "wave", "note": ""},
                     {"name": "studio", "label": "studio", "open": "/cc/page/rooms/studio/", "on": ["sys.music"], "hue": "#a0673a", "mark": "ring", "note": ""},
                     {"name": "listen", "label": "listen", "ask": "listen on it", "on": ["sys.music"], "hue": "#7a5f8e", "mark": "wave", "note": ""}]},
]


def tile(sid):
    return {"id": sid, "kind": "work", "thread": T.get(sid), "said": None, "counts": {"running": 0}, "detail": {},
            "jobs": [], "summary": None, "tree_n": 0, "domain": "", "open": None}


class FanHarness(Harness):
    def __init__(self, root):
        super().__init__(root)
        self.log: list[tuple[float, str, str, object]] = []
        self.wall = {"look": "orbit", "set": ["sys.music", "sys.film"], "pinned": ["sing"]}

    def cc(self, method, path, body):
        with self.lock:
            self.log.append((time.time(), method, path, body))
        p = path.partition("?")[0]
        if p == "/cc/systems":
            return 200, {"tiles": [tile(s) for s in T], "running": 0, "waits": {}, "built": "x"}
        if p == "/cc/surfaces":
            return 200, {"surfaces": SURFACES, "skipped": []}
        if p == "/cc/wall":
            if method == "POST":
                try:
                    d = json.loads(body) if isinstance(body, (bytes, str)) else (body or {})
                except ValueError:
                    d = {}
                self.wall.update({k: d[k] for k in ("look", "set", "pinned") if k in d})
                return 200, {"ok": True, **self.wall}
            return 200, {**self.wall, "seed": False, "max": 16}
        if p == "/cc/health":
            return 200, self.health()
        return super().cc(method, path, body)


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="wall-fan-"))
    h = FanHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


MUSIC = ".wo-b[aria-label='sys.music']"
FILM = ".wo-b[aria-label='sys.film']"


def shown(page, sel):
    return sorted(page.locator(sel + " .wf-i").evaluate_all("els => els.map(e => e.dataset.instrument)"))


def test_fan_opens_folds_opens_beside_and_the_pin_survives_reload(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wf-i[data-instrument='sing']", timeout=20000)
        # at rest: only the pinned one is out; the system keeps its box
        assert shown(page, MUSIC) == ["sing"] and shown(page, FILM) == []
        assert page.locator(MUSIC + " .wo-box").count() == 1
        # a press on the name: every instrument out (its own first, the lent K2 too), nothing opened beside
        page.mouse.move(5, 5)
        page.click(MUSIC + " .wo-nm")
        page.wait_for_selector(MUSIC + " .wf[data-fan-open='true']", timeout=3000, state="attached")
        assert shown(page, MUSIC) == ["k2", "listen", "sing", "studio"]
        assert page.locator("aside.wl-side").count() == 0
        # Esc folds them back to the pinned one
        page.keyboard.press("Escape")
        page.wait_for_selector(MUSIC + " .wf[data-fan-open='false']", timeout=3000, state="attached")
        assert shown(page, MUSIC) == ["sing"]
        # a press on one opens it beside, never a thread
        page.click(MUSIC + " .wo-nm")
        page.click(MUSIC + " .wf-i[data-instrument='studio'] .wf-o")
        page.wait_for_selector("aside.wl-side iframe[src='/cc/page/rooms/studio/']", timeout=5000)
        assert shown(page, MUSIC) == ["sing"]                              # the fan folds after a press
        page.click("aside.wl-side .wl-x")
        # an ask one fills the box and sends nothing
        t0 = time.time()
        page.click(MUSIC + " .wo-nm")
        page.click(MUSIC + " .wf-i[data-instrument='listen'] .wf-o")
        assert page.input_value(MUSIC + " .wo-in") == "listen on it"
        with h.lock:
            assert not [x for x in h.log if x[0] >= t0 and x[1] != "GET"], "an ask instrument sent something"
        # with the fan out, the next press on the name opens the thread beside, as before
        page.click(MUSIC + " .wo-nm")
        page.wait_for_selector(MUSIC + " .wf[data-fan-open='true']", timeout=3000, state="attached")
        page.click(MUSIC + " .wo-nm")
        page.wait_for_selector("iframe.wl-fr[src*='pane=wall-sys.music']", timeout=5000)
        page.click("aside.wl-side .wl-x")
        # a hover fans the film out; leaving folds it
        page.hover(FILM + " .wo-nm")
        page.wait_for_selector(FILM + " .wf[data-fan-open='true']", timeout=3000, state="attached")
        assert shown(page, FILM) == ["cut", "k2"]
        page.mouse.move(5, 890)
        page.wait_for_selector(FILM + " .wf", state="detached", timeout=3000)
        # the pin mark keeps studio out: saved on the bridge, there after a reload
        page.click(MUSIC + " .wo-nm")
        page.click(MUSIC + " .wf-i[data-instrument='studio'] .wf-p")
        deadline = time.time() + 5
        while time.time() < deadline and h.wall["pinned"] != ["sing", "studio"]:
            time.sleep(0.1)
        assert h.wall["pinned"] == ["sing", "studio"]
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wf-i[data-instrument='studio']", timeout=20000)
        assert shown(page, MUSIC) == ["sing", "studio"]
        b.close()
    assert not errors, errors


def test_phone_fans_as_a_row_under_the_name(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wo-nm", timeout=20000)
        page.tap(MUSIC + " .wo-nm")
        page.wait_for_selector(MUSIC + " .wf[data-fan-open='true']", timeout=3000, state="attached")
        name = page.locator(MUSIC + " .wo-nm").bounding_box()
        first = page.locator(MUSIC + " .wf-i").first.bounding_box()
        assert first["y"] > name["y"] and first["x"] >= 0 and first["x"] + first["width"] <= 390
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        b.close()
    assert not errors, errors
