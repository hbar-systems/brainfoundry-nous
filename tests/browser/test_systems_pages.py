"""tests/browser/test_systems_pages.py: /systems in pages of four, what each system already did (SYSTEMS-PAGES-1, 2026-11-27).

hbar 2026-11-27: "More than four systems is probably difficult to visually follow so I'm thinking we should have pages
... one page 4 systems the next page 2 systems pages!" and "I want to see the updates already made for the system so
that I don't repeat myself".

    Chromium (Playwright) -> the PANES-FOCUS-1 harness (tests/browser/test_panes_focus.py): /cc/* answered by a small
    fake bridge with demo data, the rest by the built console. Nothing is sent anywhere.

Checks: central and five systems open as page 1 of four and page 2 of two, with quiet page marks; the press, ] and [
(from the page and from inside a pane) change page; a draft typed on page 2 is there after a visit to page 1 and no
frame loaded again; a pane on the other page that ends an answer lights its page's mark; a pane moves to another page
from its bar and the pages survive a reload; the "done" mark carries the count of 14 days and opens the finished work
over the pane's top (Esc closes, nothing navigates); the three newest done lines sit above the empty box and go when
he types. Phone: one column, the tabs grouped by page. No page error. SYSTEMS_PAGES_SHOTS=<dir> saves the shots.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_systems_pages.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("panes_focus_harness", HERE / "test_panes_focus.py")
pf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = pf
_spec.loader.exec_module(pf)

SYSTEMS = ["hbar.media", "brainfoundry", "hbar.security", "hbar.systems", "hbar.music"]
pf.THREADS.update({s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(SYSTEMS, 11)})
pf.BY_T.clear()
pf.BY_T.update({v: k for k, v in pf.THREADS.items()})
pf.MARKS["hbar.music"] = (0, 4, 0, 12)


def done_rows(sid: str, n: int, total: int) -> list:
    out = []
    for i in range(n):
        ts = (pf.NOW - timedelta(hours=7 * i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"ts": ts, "what": f"(demo) {sid}: finished piece {total - i}, tests green, card closed", "job": f"DEMO-{i}",
                    "state": "waits for push" if i == 1 else "pushed", "thread": pf.THREADS.get(sid, ""),
                    "link": f"/home/hands/out/2026-11-27/demo-{i}/REPORT.md", "repo": "world"})
    return out


COUNTS = {"world": 9, "hbar.media": 6, "brainfoundry": 14, "hbar.security": 3, "hbar.systems": 5, "hbar.music": 7}


class Harness(pf.Harness):
    def cc(self, method, path, body):
        p = path.split("?", 1)[0]
        if p == "/cc/systems/done":
            q = dict(x.split("=", 1) for x in (path.split("?", 1)[1] if "?" in path else "").split("&") if "=" in x)
            sid = q.get("system", "").replace("%2E", ".")
            if not sid:
                return 200, {"ok": True, "counts": COUNTS}
            n = min(int(q.get("n") or 3), COUNTS.get(sid, 0))
            return 200, {"ok": True, "built": pf.NOW.isoformat(), "days": 14, "system": sid, "count": COUNTS.get(sid, 0), "rows": done_rows(sid, n, COUNTS.get(sid, 0))}
        if p == "/cc/systems":
            return 200, {"tiles": [pf.tile(s) for s in ["world"] + SYSTEMS], "running": 7, "built": pf.NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
        return super().cc(method, path, body)


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not pf.SERVER_JS.exists():
        pytest.skip(f"no console build at {pf.BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="systems-pages-"))
    h = Harness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def off(page, sid):
    return "off" in (pf.aside(page, sid).get_attribute("class") or "")


def wait_frames(page, n):
    end = time.time() + 30
    while time.time() < end:
        fs = pf.panes(page)
        if len(fs) >= n and all(f.query_selector("textarea") and f.query_selector(".cc-conv") for f in fs.values()):
            return fs
        page.wait_for_timeout(150)
    return pf.panes(page)


def test_pages_of_four_and_what_was_done(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    shots = os.environ.get("SYSTEMS_PAGES_SHOTS")
    with sync_playwright() as p:
        b = pf.launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS), wait_until="domcontentloaded")
        fs = wait_frames(page, 6)
        assert len(fs) == 6, sorted(fs)                                  # all six mounted, both pages
        page.wait_for_timeout(1500)
        loads = []
        page.on("framenavigated", lambda f: f != page.main_frame and loads.append(f.url))
        with h.lock:
            h.posts.clear()
        # page 1: central and the first three; page 2: the other two, hidden but there
        marks = page.locator("nav.sy-pg .sy-pgb")
        assert marks.count() == 2 and marks.nth(0).get_attribute("aria-current") == "page"
        assert [off(page, s) for s in ["world"] + SYSTEMS] == [False, False, False, False, True, True]
        for s in ["world", "hbar.media", "brainfoundry", "hbar.security"]:
            bb = pf.box(page, s)
            assert bb["width"] > 250 and bb["height"] > 300, (s, bb)
        assert "page 2: hbar.systems, hbar.music" in (marks.nth(1).get_attribute("title") or "")
        # the done mark: the count of 14 days
        dm = pf.aside(page, "brainfoundry").locator('button.sy-pm[title*="finished in brainfoundry"]')
        dm.wait_for(timeout=10000)
        assert dm.inner_text().strip() == "14"
        # the three newest above the empty box
        fb = fs["sys-brainfoundry"]
        end = time.time() + 8
        while time.time() < end and not fb.query_selector(".cc-pane-done"):
            page.wait_for_timeout(150)
        lines = fb.locator(".cc-pane-done").inner_text()
        assert "finished piece 14" in lines and "finished piece 12" in lines and "finished piece 11" not in lines, lines
        if shots:
            page.screenshot(path=str(Path(shots) / "page-1-of-2.png"))
        fb.fill("textarea", "x")
        page.wait_for_timeout(150)
        assert fb.query_selector(".cc-pane-done") is None                # nothing while he types
        fb.fill("textarea", "")
        page.wait_for_timeout(150)
        assert fb.query_selector(".cc-pane-done") is not None
        # the layer over the pane's top, Esc closes, nothing navigates
        url = page.url
        dm.click()
        layer = pf.aside(page, "brainfoundry").locator(".sy-dl")
        layer.wait_for(timeout=8000)
        page.wait_for_function("document.querySelectorAll('.sy-dl .sy-dr').length >= 14", timeout=8000)
        t = layer.inner_text()
        assert "already done" in t and "14 in 14 days" in t and "waits for push" in t and "report" in t, t[:400]
        first = layer.locator(".sy-dr").first.inner_text()
        assert "finished piece 14" in first                              # newest first
        if shots:
            page.screenshot(path=str(Path(shots) / "done-layer.png"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        assert layer.count() == 0 and page.url == url
        # ] goes to page 2: the two panes take the space, page 1 is hidden and mounted
        page.locator("body").press("]")
        page.wait_for_timeout(400)
        assert [off(page, s) for s in ["world"] + SYSTEMS] == [True, True, True, True, False, False]
        assert marks.nth(1).get_attribute("aria-current") == "page"
        for s in ["hbar.systems", "hbar.music"]:
            bb = pf.box(page, s)
            assert bb["width"] > 500 and bb["height"] > 600, (s, bb)
        fm = fs["sys-hbar.music"]
        fm.fill("textarea", "a draft on page two")
        if shots:
            page.screenshot(path=str(Path(shots) / "page-2-of-2.png"))
        # [ from inside a pane (outside its box) comes back
        fm.evaluate("document.activeElement && document.activeElement.blur()")
        fm.press("body", "[")
        page.wait_for_timeout(400)
        assert not off(page, "world") and off(page, "hbar.music")
        # a pane on page 2 ends an answer: page 2's mark lights; looking at it clears the light
        fs["sys-hbar.systems"].evaluate("window.parent.postMessage({type:'cc-pane-state', busy:true}, location.origin)")
        page.wait_for_timeout(200)
        fs["sys-hbar.systems"].evaluate("window.parent.postMessage({type:'cc-pane-state', busy:false}, location.origin)")
        page.wait_for_timeout(300)
        assert marks.nth(1).locator(".f").count() == 1
        marks.nth(1).click()
        page.wait_for_timeout(400)
        assert fm.query_selector("textarea").input_value() == "a draft on page two"   # the draft stayed
        assert marks.nth(1).locator(".f").count() == 0
        marks.nth(0).click()
        page.wait_for_timeout(300)
        # move brainfoundry to page 2 from its bar
        pf.aside(page, "brainfoundry").locator('button[aria-label="move brainfoundry to another page"]').click()
        pf.aside(page, "brainfoundry").locator('.sy-mv button', has_text="2").click()
        page.wait_for_timeout(400)
        assert off(page, "brainfoundry") and not off(page, "hbar.media")
        saved = json.loads(page.evaluate("localStorage.getItem('cc.systems.pages')"))
        assert saved["pageOf"]["brainfoundry"] == 1 and saved["cur"] == 0, saved
        assert loads == [], f"frames loaded again: {loads}"
        # the pages survive a reload
        page.reload(wait_until="domcontentloaded")
        wait_frames(page, 6)
        page.wait_for_timeout(800)
        assert off(page, "brainfoundry") and not off(page, "hbar.media") and off(page, "hbar.music")
        with h.lock:
            sent = [x for x in h.posts if x in ("/cc/chat", "/cc/steer") or x.endswith("/say") or "/sessions/" in x]
            assert sent == [], sent
        b.close()
    assert not errors, errors


def test_phone_pages_are_sections(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    shots = os.environ.get("SYSTEMS_PAGES_SHOTS")
    with sync_playwright() as p:
        b = pf.launch(p)
        page = b.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS) + "&focus=hbar.music", wait_until="domcontentloaded")
        a = pf.aside(page, "hbar.music")
        page.wait_for_selector('aside[aria-label="hbar.music thread"].show', timeout=15000)
        bb = a.bounding_box()
        assert bb["width"] >= 389 and bb["height"] > 600, bb
        assert page.locator("nav.sy-pg").is_hidden()
        labels = a.locator(".sy-tabs .pgl").all_inner_texts()
        assert labels == ["1", "2"], labels
        page.wait_for_timeout(800)
        if shots:
            page.screenshot(path=str(Path(shots) / "phone.png"))
        b.close()
    assert not errors, errors
