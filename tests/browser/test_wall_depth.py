"""tests/browser/test_wall_depth.py: the wall's depth layer reads and never disturbs (WALL-3, 2026-11-24).

hbar: "everything is hidden, and i can gain access some easy way WITHOUT interfering with production and the main
focus". The layer opens on a press of a system's light or count, and closes on Esc or a press outside.

    Chromium (Playwright) -> a front (this file): /cc/* answered by a small fake bridge that logs every request;
    /api answered small; the rest to the built console (next standalone).

Checks, on /wall in the orbit: with a thread open beside (its frame marked) and a slow request in flight, opening the
layer, reading its four rows (now, jobs with their inside, the tree, the thread), closing it with Esc and with a press
outside sends nothing (no request but GET from the page, none of the send doors touched), the frame beside is the same
frame (not reloaded), the slow request finishes, and no request fails. While open, the poll asks for that system's tree
(GET /cc/systems?depth=<id>). The tree's Talk puts the ask into that system's box and sends nothing. An instrument has
no box and opens beside. The centre's layer groups every running job by system and shows the two waits. No page error.

Skips without python playwright or a console build (NOUS_CONSOLE_BUILD=<ui dir after npm ci && npm run build>,
default ui/ here), like test_panes_health.py.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_wall_depth.py -q
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("wall3_panes_health", Path(__file__).with_name("test_panes_health.py"))
_ph = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ph)
BUILD, SERVER_JS, Harness, launch = _ph.BUILD, _ph.SERVER_JS, _ph.Harness, _ph.launch   # the same front and console

T = {s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(["world", "hbar.film", "hbar.music", "hbar.ink"], 1)}
TREE = {"title": "This thread", "nodes": [{"id": "1", "label": "Cut the trailer", "state": "done"},
                                          {"id": "2", "label": "Colour pass", "state": "running", "ask": "How far is the colour pass?",
                                           "children": [{"id": "2.1", "label": "Grade the reel", "state": "yours"}]}]}
SEND_DOORS = ("/say", "/cc/chat", "/cc/queue", "/cc/systems/thread", "/cc/transcribe", "/cc/systems/voice", "/cc/wall")


def tiles(depth):
    def tile(sid, **o):
        t = {"id": sid, "kind": "work", "thread": T.get(sid), "said": None, "counts": {"running": 0}, "detail": {},
             "jobs": [], "summary": None, "tree_n": 0, "domain": "", "open": None}
        t.update(o)
        return t
    film = tile("hbar.film", counts={"running": 2}, tree_n=3, summary={"text": "K2 is released; the trailer is next.", "from": "card"},
                said={"text": "Grading the first reel", "live": True, "waiting": False, "at": None},
                jobs=[{"id": "J1", "title": "FILM-2 Grade: the colour pass", "mins": 75, "brief": "2026-11-24_film-2.md",
                       "steps": ["reading the reel", "writing the LUT"], "made": ["grade.png"],
                       "waiter": {"id": "J2", "title": "PUSH-TRAIN-9 Conductor"}, "tag": "FILM-2", "thread": ""},
                      {"id": "J3", "title": "FILM-3 Titles", "mins": 4, "brief": "", "steps": [], "made": [], "waiter": None, "tag": "FILM-3", "thread": ""}])
    if depth == "hbar.film":
        film["tree"] = TREE
    return [tile("world", counts={"running": 1}, summary={"text": "Three builds wait for a push.", "from": "thread"},
                 jobs=[{"id": "J5", "title": "STEWARD done box", "mins": 2, "steps": [], "made": [], "waiter": None, "brief": "", "tag": "STEWARD", "thread": ""}]),
            film,
            tile("hbar.music", said={"text": "The chorus is in.", "live": False, "waiting": False, "at": "2026-11-24T10:00:00Z"}),
            tile("hbar.ink", kind="instrument", open="/tasks", domain="hbar.ink", thread=None)]


class WallHarness(Harness):
    def __init__(self, root):
        super().__init__(root)
        self.log: list[tuple[float, str, str]] = []

    def cc(self, method, path, body):
        with self.lock:
            self.log.append((time.time(), method, path))
        p, _, q = path.partition("?")
        if p == "/cc/systems":
            depth = q.split("depth=", 1)[1].split("&", 1)[0].replace("%2E", ".") if "depth=" in q else None
            return 200, {"tiles": tiles(depth), "running": 3, "waits": {"court": 5, "tasks_today": 2}, "built": "x"}
        if p == "/cc/wall":
            return 200, {"look": "orbit", "set": ["hbar.film", "hbar.music", "hbar.ink"], "seed": False, "max": 16}
        if p == "/cc/stream-test":
            time.sleep(3.0)
            return 200, {"done": True}
        if p == "/cc/health":
            return 200, self.health()
        return super().cc(method, path, body)


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="wall-depth-"))
    h = WallHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def test_layer_opens_reads_and_closes_without_a_send(harness):
    from playwright.sync_api import sync_playwright
    h, errors, failed, reqs = harness, [], [], []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(".wo-b[aria-label='hbar.film'] .wo-dp", timeout=20000)
        # at rest: no layer; the instrument has no box
        assert page.locator(".wd").count() == 0
        assert page.locator(".wo-b[aria-label='hbar.ink'] .wo-box").count() == 0
        assert page.locator(".wo-b[aria-label='hbar.film'] .wo-box").count() == 1
        # a thread beside, its frame marked; a slow request in flight
        page.click(".wo-b[aria-label='hbar.music'] .wo-nm")              # WALL-6: the name enters; the card opens the thread
        page.click(".we-veil[data-enter-for='hbar.music'] .we-foot button")
        page.wait_for_selector("iframe.wl-fr", timeout=10000)
        frame = next(f for f in page.frames if "pane=wall-hbar.music" in f.url)
        frame.wait_for_load_state("domcontentloaded")
        frame.evaluate("window.__wall3 = 'kept'")
        page.evaluate("window.__slow = fetch('/cc/stream-test').then(r => r.json())")
        page.wait_for_timeout(200)
        t0 = time.time()
        page.on("request", lambda r: reqs.append((r.method, r.url, r.frame == page.main_frame)))
        # open: the four rows, one line each
        page.click(".wo-b[aria-label='hbar.film'] .wo-dp")
        page.wait_for_selector(".wd[data-depth='hbar.film']", timeout=5000)
        txt = page.locator(".wd").inner_text()
        assert "K2 is released" in txt and "2 running" in txt and "read the whole thread" in txt
        page.click(".wd .wd-r:has-text('jobs')")
        page.wait_for_selector(".wd-j", timeout=3000)
        page.click(".wd-j:first-child .wd-jh")
        inside = page.locator(".wd-in").inner_text()
        assert "writing the LUT" in inside and "PUSH-TRAIN-9" in inside and "grade.png" in inside
        page.click(".wd .wd-r:has-text('tree')")
        page.wait_for_selector(".wd [data-tree-row='2']", timeout=8000)   # the poll brought the tree (?depth=)
        # Esc closes the layer only; the thread beside stays
        page.keyboard.press("Escape")
        page.wait_for_selector(".wd", state="detached", timeout=3000)
        assert page.locator(".wl-side").count() == 1
        # a press outside closes it too
        page.click(".wo-b[aria-label='hbar.film'] .wo-dp")
        page.wait_for_selector(".wd", timeout=3000)
        page.mouse.click(300, 130)
        page.wait_for_selector(".wd", state="detached", timeout=3000)
        slow = page.evaluate("window.__slow")
        assert slow == {"done": True}, slow
        assert frame.evaluate("window.__wall3") == "kept"                 # the same frame: nothing reloaded beside
        assert not failed, failed
        sends = [r for r in reqs if r[0] != "GET" and r[2]]
        assert not sends, sends
        with h.lock:
            during = [x for x in h.log if x[0] >= t0]
        assert not [x for x in during if x[1] != "GET" and any(d in x[2] for d in SEND_DOORS)], during
        assert any(x[2].startswith("/cc/systems?wall=1&depth=hbar.film") for x in during)
        b.close()
    assert not errors, errors


def test_tree_talk_fills_the_box_instrument_opens_centre_layer(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/wall", wait_until="domcontentloaded")
        page.wait_for_selector(".wo-b[aria-label='hbar.film'] .wo-dp", timeout=20000)
        t0 = time.time()
        page.click(".wo-b[aria-label='hbar.film'] .wo-dp")
        page.click(".wd .wd-r:has-text('tree')")
        page.wait_for_selector(".wd [data-tree-row='2']", timeout=8000)
        page.click(".wd [data-tree-row='2']")
        page.click(".wd [data-tree-card='2'] a:has-text('talk')")
        page.wait_for_selector(".wd", state="detached", timeout=3000)
        assert page.input_value(".wo-b[aria-label='hbar.film'] .wo-in") == "How far is the colour pass?"
        with h.lock:
            assert not [x for x in h.log if x[0] >= t0 and x[1] != "GET"], "talk sent something"
        # an instrument opens beside, never a thread
        page.click(".wo-b[aria-label='hbar.ink'] .wo-nm")
        page.wait_for_selector("aside.wl-side iframe[src='/tasks']", timeout=5000)
        page.click("aside.wl-side .wl-x")
        # the centre: every job by system, and the two waits that open beside
        page.click(".wo-cn")
        page.wait_for_selector(".wd[data-depth='world']", timeout=3000)
        page.click(".wd .wd-r:has-text('jobs')")
        groups = page.locator(".wd-sys").all_inner_texts()
        assert groups[0].startswith("film") and len(groups) == 2, groups
        w = page.locator(".wd-w").inner_text()
        assert "2" in w and "5" in w and "court" in w
        page.click(".wd-w button:has-text('court')")
        page.wait_for_selector("aside.wl-side iframe[src='/cc/page/court/']", timeout=5000)
        b.close()
    assert not errors, errors
