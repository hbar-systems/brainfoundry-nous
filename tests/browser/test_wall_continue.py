"""tests/browser/test_wall_continue.py: prompts to continue, the faint ring, the brain's seed (WALL-4, 2026-11-24).

hbar: "fill it with what we are currently doing-- the systems that is + prompts to continue from what has been in this
thread, and maybe some faint ones that i HAVE BEEN working on in other threads. and we evolve into this new production
surface and test it."

    Chromium (Playwright) -> the WALL-3 front (test_panes_health.py's Harness): /cc/* answered by a fake bridge that logs
    every request; the rest to the built console (next standalone).

Checks, on /wall in the orbit: at rest no prompt shows; focusing a box shows its prompts (at most five); a press puts
the line in the box and sends nothing; a second press on the same line sends it in place (the steer door, the page
stays); a line ending in ":" fills and waits, a second press does not send it; the layer's prompts fill the box too.
The centre's box shows the centre's list. The faint ring shows dim names; a press brings one into the orbit (POST
/cc/wall with the new set) and it gets its box; a faint one with something running shows its count. The seed notice
shows "new set from the brain": "keep mine" answers with the seed's stamp only, "take it" saves the seed's set. No
page error. Skips like test_wall_depth.py.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_wall_continue.py -q
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("wall4_panes_health", Path(__file__).with_name("test_panes_health.py"))
_ph = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ph)
BUILD, SERVER_JS, Harness, launch = _ph.BUILD, _ph.SERVER_JS, _ph.Harness, _ph.launch

T = {s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(["world", "hbar.film", "hbar.music", "hbar.art", "hbar.blog"], 1)}
FILM_P = ["play the trailer", "grade look: ", "status of FILM-2", "four", "five"]


def tiles():
    def tile(sid, **o):
        t = {"id": sid, "kind": "work", "thread": T.get(sid), "said": None, "counts": {"running": 0}, "detail": {},
             "jobs": [], "summary": None, "tree_n": 0, "domain": "", "open": None, "prompts": []}
        t.update(o)
        return t
    return [tile("world", prompts=["what waits for me today", "continue production"]),
            tile("hbar.film", prompts=FILM_P, summary={"text": "The trailer is cut.", "from": "card"}),
            tile("hbar.music", prompts=["play the K2 intro"]),
            tile("hbar.art", counts={"running": 2}, jobs=[{"id": "J7", "title": "ART-2 Rooms", "mins": 3, "steps": [], "made": [], "waiter": None, "brief": "", "tag": "ART-2", "thread": ""}]),
            tile("hbar.blog")]


class ContinueHarness(Harness):
    def __init__(self, root):
        super().__init__(root)
        self.log: list[tuple[float, str, str, object]] = []
        self.wall = {"look": "orbit", "set": ["hbar.film", "hbar.music"], "seed": False, "max": 16,
                     "faint": ["hbar.art", "hbar.blog"], "fresh": {"set": ["hbar.music", "hbar.film", "hbar.blog"], "stamp": 1795560000.5}, "home": True}

    def cc(self, method, path, body):
        with self.lock:
            self.log.append((time.time(), method, path, body))
        p, _, q = path.partition("?")
        if p == "/cc/systems":
            return 200, {"tiles": tiles(), "running": 2, "waits": {"court": 0, "tasks_today": 0}, "built": "x"}
        if p == "/cc/wall":
            if method == "POST":
                b = json.loads(body or b"{}")
                if "set" in b:
                    self.wall["set"] = b["set"]
                if "seen" in b:
                    self.wall["fresh"] = None
                return 200, {"ok": True, **self.wall}
            return 200, dict(self.wall)
        if p.startswith("/cc/threads/") and p.endswith("/say"):
            return 202, {"ok": True, "system": "x", "thread": p.split("/")[3]}
        if p == "/cc/health":
            return 200, self.health()
        return super().cc(method, path, body)


@pytest.fixture()
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="wall-continue-"))
    h = ContinueHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def _body(x):
    b = x[3]
    return json.loads(b or b"{}") if isinstance(b, (bytes, str)) else (b or {})


def _posts(h, t0, part):
    with h.lock:
        return [x for x in h.log if x[0] >= t0 and x[1] == "POST" and part in x[2]]


# WALL-6 (2026-11-26, hbar: "can i only send this? i cant type a message and it will go through?"): the prompts are
# shortcut chips in the entered card, under an EMPTY box; a chip puts its words in the box and never sends; Enter sends
# what the box holds; nothing under a body's box at rest or on focus.
def test_prompts_are_shortcuts_that_fill_and_never_send(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(".wo-b[aria-label='hbar.film'] .wo-in", timeout=20000)
        page.click(".wo-fresh button:has-text('keep mine')")                 # out of the way first (checked below)
        t0 = time.time()
        page.click(".wo-b[aria-label='hbar.film'] .wo-in")                   # focusing a body's box shows no list
        page.wait_for_timeout(300)
        assert page.locator(".wo-pr, .wo-p").count() == 0
        page.click(".wo-b[aria-label='hbar.film'] .wo-nm")
        page.wait_for_selector(".we-veil[data-enter-for='hbar.film']", timeout=3000)
        assert page.input_value(".we-in") == ""
        chips = page.locator(".we-chip").all_inner_texts()
        assert [x.strip() for x in chips] == [x.strip() for x in FILM_P][:4], chips
        # a chip fills, sends nothing; pressed again, still nothing
        page.click(".we-chip:has-text('play the trailer')")
        page.click(".we-chip:has-text('play the trailer')")
        assert page.input_value(".we-in") == "play the trailer"
        assert not _posts(h, t0, "/say")
        # an open line fills and waits for him
        page.click(".we-chip:has-text('grade look')")
        assert page.input_value(".we-in") == "grade look: "
        page.type(".we-in", "warm")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)
        said = _posts(h, t0, "/say")
        assert len(said) == 1 and _body(said[0])["message"] == "grade look: warm", said
        assert page.url.endswith("/wall")                                      # never navigated
        # the layer's prompts still fill the body's box
        page.keyboard.press("Escape")
        page.click(".wo-b[aria-label='hbar.film'] .wo-dp")
        page.wait_for_selector(".wd .wd-p", timeout=3000)
        page.click(".wd .wd-p:has-text('four')")
        page.wait_for_selector(".wd", state="detached", timeout=3000)
        assert page.input_value(".wo-b[aria-label='hbar.film'] .wo-in") == "four"
        assert len(_posts(h, t0, "/say")) == 1
        # the brain's card shows the centre's list; the centre's own box is empty at rest
        assert page.input_value(".wo-cbox .wo-in") == ""
        page.click(".wo-sym")
        page.wait_for_selector(".we-veil[data-enter-for='world'] .we-chip", timeout=3000)
        assert "what waits for me today" in page.locator(".we-chips").inner_text()
        b.close()
    assert not errors, errors


def test_faint_ring_joins_and_the_seed_notice(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector("[data-faint='hbar.art']", timeout=20000)
        t0 = time.time()
        assert page.locator("[data-faint='hbar.blog']").count() == 1
        assert page.locator(".wo-b[aria-label='hbar.art']").count() == 0
        assert "2" in page.locator("[data-faint='hbar.art']").inner_text()     # running: its count shows
        # the notice: one quiet line, nothing changed yet
        page.wait_for_selector(".wo-fresh", timeout=3000)
        assert "new set from the brain" in page.locator(".wo-fresh").inner_text()
        assert not _posts(h, t0, "/cc/wall")
        # a faint press brings it in, with its box
        page.click("[data-faint='hbar.art']")
        page.wait_for_selector(".wo-b[aria-label='hbar.art'] .wo-in", timeout=3000)
        sv = _posts(h, t0, "/cc/wall")
        body = _body(sv[-1])
        assert body == {"set": ["hbar.film", "hbar.music", "hbar.art"]}, body
        assert page.locator("[data-faint='hbar.art']").count() == 0
        # take it: the seed's set, with its stamp
        page.click(".wo-fresh button:has-text('take it')")
        page.wait_for_selector(".wo-fresh", state="detached", timeout=3000)
        sv = _posts(h, t0, "/cc/wall")
        body = _body(sv[-1])
        assert body == {"set": ["hbar.music", "hbar.film", "hbar.blog"], "seen": 1795560000.5}, body
        page.wait_for_selector(".wo-b[aria-label='hbar.blog'] .wo-in", timeout=3000)
        b.close()
    assert not errors, errors


def test_keep_mine_answers_with_the_stamp_only(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(".wo-fresh", timeout=20000)
        t0 = time.time()
        page.click(".wo-fresh button:has-text('keep mine')")
        page.wait_for_selector(".wo-fresh", state="detached", timeout=3000)
        page.wait_for_timeout(300)
        sv = _posts(h, t0, "/cc/wall")
        body = _body(sv[-1])
        assert body == {"seen": 1795560000.5}, body
        assert page.locator(".wo-b[aria-label='hbar.blog']").count() == 0      # his set stays
        b.close()
    assert not errors, errors
