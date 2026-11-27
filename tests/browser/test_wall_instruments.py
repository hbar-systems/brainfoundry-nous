"""tests/browser/test_wall_instruments.py: a system's instruments on the orbit (WALL-5, 2026-11-24).

hbar, on the live wall: "okay but where is my musical surfaces tho those i wanted actually -- i want to create more
than the hbar.ink". The register (GET /cc/surfaces) gives a system its instruments; a press on the name fans them out,
a press on one opens it beside, Esc folds them back, a pinned one stays out and survives a reload.

    Chromium (Playwright) -> a front (test_panes_health.Harness): /cc/* answered by a small fake bridge that keeps the
    wall's setting in memory and logs every request; the rest to the built console (next standalone).

Checks, on /wall in the orbit at 1440 (WALL-6 moved the fan into the entered card): at rest only the pinned instrument
is out, in a row under the box; a press on the name enters the system and its card holds every instrument; a hover
opens nothing; a press on one opens its page beside (no thread); an `ask` one fills the system's box and sends nothing;
the card's "whole thread" opens the thread beside; the ring saves {pinned} on the bridge and the pin is there after a
reload. At 390 the card fits the screen. No page error.

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


def inst_in_card(page):
    return sorted(page.locator(".we [data-instrument]").evaluate_all("els => els.map(e => e.dataset.instrument)"))


# WALL-6 (2026-11-26): one press on a name enters the system; its instruments are in the entered card (each opens beside,
# an ask fills the box, a small ring pins it); the pinned ones sit in a row under the body at rest. No hover fan.
def test_instruments_in_the_entered_card_and_the_pin_survives_reload(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wf-i[data-instrument='sing']", timeout=20000)
        # at rest: only the pinned one is out, under the body; the system keeps its box
        assert shown(page, MUSIC) == ["sing"] and shown(page, FILM) == []
        assert page.locator(MUSIC + " .wo-box").count() == 1
        sing, box = page.locator(MUSIC + " .wf-i").first.bounding_box(), page.locator(MUSIC + " .wo-box").bounding_box()
        assert sing["y"] >= box["y"] + box["height"] - 1                    # a row under the box, not toward the centre
        # a press on the name enters: every instrument in the card (its own first, the lent K2 too), nothing beside
        page.click(MUSIC + " .wo-nm")
        page.wait_for_selector(".we-veil[data-enter-for='sys.music']", timeout=3000)
        assert inst_in_card(page) == ["k2", "listen", "sing", "studio"]
        assert page.locator("aside.wl-side").count() == 0
        # a hover on a name opens nothing
        page.keyboard.press("Escape")
        page.wait_for_selector(".we-veil", state="detached", timeout=3000)
        page.hover(FILM + " .wo-nm")
        page.wait_for_timeout(500)
        assert page.locator(".we-veil").count() == 0 and shown(page, FILM) == []
        # a press on one opens it beside, never a thread; the card closes
        page.click(MUSIC + " .wo-nm")
        page.click(".we [data-instrument='studio'] .we-ins")
        page.wait_for_selector("aside.wl-side iframe[src='/cc/page/rooms/studio/']", timeout=5000)
        assert page.locator(".we-veil").count() == 0
        page.click("aside.wl-side .wl-x")
        # an ask one fills the system's box and sends nothing
        t0 = time.time()
        page.click(MUSIC + " .wo-nm")
        page.click(".we [data-instrument='listen'] .we-ins")
        assert page.input_value(MUSIC + " .wo-in") == "listen on it"
        with h.lock:
            assert not [x for x in h.log if x[0] >= t0 and x[1] != "GET"], "an ask instrument sent something"
        # the whole thread beside, from the card
        page.click(MUSIC + " .wo-nm")
        page.click(".we-foot button")
        page.wait_for_selector("iframe.wl-fr[src*='pane=wall-sys.music']", timeout=5000)
        page.click("aside.wl-side .wl-x")
        # the ring keeps studio out: saved on the bridge, there after a reload
        page.click(MUSIC + " .wo-nm")
        page.click(".we [data-instrument='studio'] .we-pin")
        deadline = time.time() + 5
        while time.time() < deadline and h.wall["pinned"] != ["sing", "studio"]:
            time.sleep(0.1)
        assert h.wall["pinned"] == ["sing", "studio"]
        assert page.get_attribute(".we [data-instrument='studio'] .we-pin", "aria-pressed") == "true"
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wf-i[data-instrument='studio']", timeout=20000)
        assert shown(page, MUSIC) == ["sing", "studio"]
        b.close()
    assert not errors, errors


def test_phone_card_holds_the_instruments(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(MUSIC + " .wo-nm", timeout=20000)
        page.tap(MUSIC + " .wo-nm")
        page.wait_for_selector(".we [data-instrument='k2']", timeout=3000)
        r = page.locator(".we").bounding_box()
        assert r["x"] >= 0 and r["x"] + r["width"] <= 390
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        b.close()
    assert not errors, errors
