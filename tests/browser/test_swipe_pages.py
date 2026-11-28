"""tests/browser/test_swipe_pages.py: a two-finger sideways slide over /systems moves to the next page (SWIPE-PAGES-1, 2026-11-28).

hbar 2026-11-28: "Would be very nice to have a two finger slide if hovering over the [panes] so it slides to the second
or the third page how similarly three fingers does a window on a MacBook except now we're doing inside our console".

    Chromium (Playwright) -> the SYSTEMS-PAGES-1 harness (tests/browser/test_systems_pages.py): /cc/* answered by a small
    fake bridge with demo data, the rest by the built console. Nothing is sent anywhere.

Checks: real wheel events over a pane's frame (page.mouse.wheel, so they land inside the frame) move the row with the
fingers, the next page's panes beside it; on release it settles on page 2; no frame loaded again and the pane that slid
in kept its frame size; a draft stays; a short slide springs back; a vertical wheel never turns; a wide block that
scrolls sideways keeps its own scroll; the slide back returns to page 1. Reduced motion: no follow, an instant turn.
The frame rate of the slide is measured (headless Chromium paints on the CPU). SWIPE_SHOTS=<dir> saves the shots and
fps.json.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_swipe_pages.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("systems_pages_harness", HERE / "test_systems_pages.py")
sp = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sp
_spec.loader.exec_module(sp)
pf = sp.pf
SYSTEMS = sp.SYSTEMS
ALL = ["world"] + SYSTEMS


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not pf.SERVER_JS.exists():
        pytest.skip(f"no console build at {pf.BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="swipe-pages-"))
    h = sp.Harness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def cur_page(page):
    return page.evaluate("(() => { const b = [...document.querySelectorAll('nav.sy-pg .sy-pgb')]; return b.findIndex(x => x.getAttribute('aria-current') === 'page') + 1 })()")


def shift(page):
    return page.evaluate("(() => { const el = document.querySelector('.sy-frames'); const m = new DOMMatrixReadOnly(getComputedStyle(el).transform); return m.m41 })()")


def frame_size(page, sid):
    return page.evaluate("(s) => { const f = document.querySelector(`aside[aria-label=\"${s} thread\"] iframe`); const r = f.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)] }",
                         "central" if sid == "world" else sid)


def over(page, sid):
    bb = pf.box(page, sid)
    page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] * 0.6)


def slide(page, dx, n, gap_ms=16):
    for _ in range(n):
        page.mouse.wheel(dx, 0)
        page.wait_for_timeout(gap_ms)


def open_six(page, h):
    page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS), wait_until="domcontentloaded")
    fs = sp.wait_frames(page, 6)
    assert len(fs) == 6, sorted(fs)
    page.wait_for_timeout(1500)
    return fs


def test_slide_follows_settles_and_keeps_everything(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    shots = os.environ.get("SWIPE_SHOTS")
    with sync_playwright() as p:
        b = pf.launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        fs = open_six(page, h)
        loads = []
        page.on("framenavigated", lambda f: f != page.main_frame and loads.append(f.url))
        assert cur_page(page) == 1 and [sp.off(page, s) for s in ALL] == [False] * 4 + [True] * 2
        fs["sys-hbar.media"].fill("textarea", "a draft before the slide")
        fs["sys-hbar.media"].evaluate("document.activeElement && document.activeElement.blur()")
        w = page.evaluate("document.querySelector('.sy-frames').clientWidth")
        before = frame_size(page, "hbar.systems")

        # a vertical wheel inside a pane never turns the page
        over(page, "hbar.media")
        for _ in range(8):
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(16)
        page.wait_for_timeout(500)
        assert cur_page(page) == 1 and abs(shift(page)) < 0.5

        # a short slide follows, then springs back
        over(page, "brainfoundry")
        slide(page, 12, 6)
        page.wait_for_timeout(30)
        mid = shift(page)
        assert -100 < mid < -20, mid                                         # the row follows the fingers
        page.wait_for_timeout(700)
        assert cur_page(page) == 1 and abs(shift(page)) < 0.5

        # a block inside a pane that scrolls sideways keeps its own scroll
        fm = fs["sys-hbar.media"]
        fm.evaluate("""() => { const d = document.createElement('div'); d.id = 'wide'; d.style.cssText = 'position:fixed;left:0;top:120px;width:100%;height:220px;overflow-x:auto;z-index:99;background:#fff';
          d.innerHTML = '<div style="width:3000px;height:200px">a wide table</div>'; document.body.appendChild(d) }""")
        bb = pf.box(page, "hbar.media")
        page.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + 70 + 120 + 100)
        page.wait_for_timeout(100)
        slide(page, 30, 10)
        page.wait_for_timeout(600)
        assert cur_page(page) == 1 and abs(shift(page)) < 0.5                # no turn, no follow
        assert fm.evaluate("document.getElementById('wide').scrollLeft") > 100   # it scrolled itself
        fm.evaluate("document.getElementById('wide').remove()")

        # the slide: wheel events land inside the pane's frame and come up as cc-pane-swipe
        page.evaluate("""() => { window.__fps = { n: 0, on: true, t0: performance.now() };
          const tick = () => { if (!window.__fps.on) return; window.__fps.n++; requestAnimationFrame(tick) }; requestAnimationFrame(tick) }""")
        over(page, "hbar.media")
        t0 = time.time()
        slide(page, 22, 22)
        page.wait_for_timeout(20)
        x = shift(page)
        assert -w * 0.8 < x < -w / 3, (x, w)                                # mid-slide: past a third, not there yet
        assert "peek" in (pf.aside(page, "hbar.systems").get_attribute("class") or "")
        assert pf.aside(page, "hbar.systems").evaluate("e => getComputedStyle(e).visibility") == "visible"
        sb = pf.box(page, "hbar.systems")
        fr = page.evaluate("document.querySelector('.sy-frames').getBoundingClientRect().left")
        assert sb["x"] > fr + w + x - 2, (sb, fr, w, x)                       # page 2 sits beside page 1, moving with it
        mid_size = frame_size(page, "hbar.systems")
        if shots:
            # the fingers rest mid-slide while the shot is taken (a tiny slide every 40 ms keeps the release from firing)
            # the settle that starts when the fingers lift is held at its first frame (CDP: animations at rate 0), so the
            # shot shows where the fingers left the row; then it plays on
            cdp = page.context.new_cdp_session(page)
            cdp.send("Animation.enable")
            cdp.send("Animation.setPlaybackRate", {"playbackRate": 0})
            page.wait_for_timeout(250)
            held = shift(page)
            page.screenshot(path=str(Path(shots) / "mid-slide.png"))
            cdp.send("Animation.setPlaybackRate", {"playbackRate": 1})
            print("mid-slide shot: row at", held, "px of", w)
        page.wait_for_timeout(700)                                             # the fingers lifted: it settles
        fps = page.evaluate("(() => { window.__fps.on = false; return { frames: window.__fps.n, ms: performance.now() - window.__fps.t0 } })()")
        fps["wall_s"] = round(time.time() - t0, 3)
        fps["fps"] = round(fps["frames"] * 1000 / fps["ms"], 1)
        assert cur_page(page) == 2 and abs(shift(page)) < 0.5
        assert [sp.off(page, s) for s in ALL] == [True] * 4 + [False] * 2
        after = frame_size(page, "hbar.systems")
        assert all(abs(a - c) <= 1 for a, c in zip(mid_size, after)), (before, mid_size, after)   # no resize at the turn
        assert "peek" not in (pf.aside(page, "hbar.systems").get_attribute("class") or "")
        if shots:
            page.screenshot(path=str(Path(shots) / "settled-page-2.png"))
            (Path(shots) / "fps.json").write_text(json.dumps(fps) + "\n")

        # the last page: nothing after it, a rubber band, back in place
        over(page, "hbar.music")
        slide(page, 25, 8)
        page.wait_for_timeout(20)
        rb = shift(page)
        assert -150 < rb < 0, rb
        page.wait_for_timeout(700)
        assert cur_page(page) == 2 and abs(shift(page)) < 0.5

        # a long slide back with momentum: page 1, one page only, the momentum after it ignored
        over(page, "hbar.systems")
        slide(page, -40, 50, 12)
        page.wait_for_timeout(800)
        assert cur_page(page) == 1 and abs(shift(page)) < 0.5
        assert fs["sys-hbar.media"].query_selector("textarea").input_value() == "a draft before the slide"
        assert loads == [], f"frames loaded again: {loads}"
        with h.lock:
            sent = [x for x in h.posts if x in ("/cc/chat", "/cc/steer") or x.endswith("/say") or "/sessions/" in x]
            assert sent == [], sent
        b.close()
    assert not errors, errors


def test_reduced_motion_turns_at_once(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    with sync_playwright() as p:
        b = pf.launch(p)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        open_six(page, h)
        over(page, "hbar.media")
        seen = []
        for _ in range(10):
            page.mouse.wheel(20, 0)
            page.wait_for_timeout(16)
            seen.append(shift(page))
        page.wait_for_timeout(300)
        assert all(abs(s) < 0.5 for s in seen), seen                         # never follows
        assert cur_page(page) == 2
        b.close()
    assert not errors, errors
