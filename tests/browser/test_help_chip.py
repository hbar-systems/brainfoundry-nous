"""tests/browser/test_help_chip.py: the "Something wrong? Ask hbar" chip covers no Send and is faint at rest (CHIP-1, 2026-11-27).

hbar 2026-11-27, twice: "the ask hbar service at corner ... its blocking the send button! or be like slightly super
transparent until hovered over and clicked"; "the something wrong ask hbar button position, style it should be transparent!".
In both screenshots the chip sat over the round Send of a composer inside an iframe pane (a /systems column, the /wall
centre thread): the old placement asked document.elementsFromPoint, which reports a same-origin iframe as the <iframe>
itself, never the button inside it.

    Chromium (Playwright) -> the PANES-FOCUS-1 harness (tests/browser/test_panes_focus.py): demo threads, nothing sent.

Checks, at 1280x800, 1440x900, 1512x900, 1728x1000 and 390x844: on /systems with four columns, on /wall with the central
thread open beside, and on /talk, the chip's rect touches no button, text box or input of any composer, in the page or in
any pane. At rest its opacity is about a quarter; hover and keyboard focus bring it to full. No page error.
HELP_CHIP_SHOTS=<dir> also saves <page>-<w>.png there.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_help_chip.py -q
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from tests.browser.test_panes_focus import BUILD, SERVER_JS, SYSTEMS, THREADS, Harness, launch, panes

SIZES = [(1280, 800), (1440, 900), (1512, 900), (1728, 1000), (390, 844)]
CONTROLS = "button, textarea, input, select, a[href], [role='button'], [contenteditable='true']"


class ChipHarness(Harness):
    def cc(self, method, path, body):
        p = path.split("?", 1)[0]
        if p == "/cc/wall":
            return 200, {"look": "orbit", "set": SYSTEMS, "seed": False, "max": 16}
        return super().cc(method, path, body)


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    root = Path(tempfile.mkdtemp(prefix="help-chip-"))
    h = ChipHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


RECTS_JS = """(sel) => Array.from(document.querySelectorAll(sel)).filter(e => {
  if (e.closest('[data-help-button],[data-help-panel]')) return false
  const r = e.getBoundingClientRect(), cs = getComputedStyle(e)
  return r.width >= 1 && r.height >= 1 && cs.visibility !== 'hidden' && cs.display !== 'none'
}).map(e => { const r = e.getBoundingClientRect()
  return {x: r.left, y: r.top, w: r.width, h: r.height, what: (e.tagName + ' ' + (e.getAttribute('aria-label') || e.title || e.textContent || '')).slice(0, 50)} })"""


def controls(page):
    """Every visible control's rect in page coordinates: the page's own and each pane's (shifted by its frame)."""
    out = [dict(r, where="page") for r in page.evaluate(RECTS_JS, CONTROLS)]
    for f in page.frames:
        if f == page.main_frame:
            continue
        try:
            fb = f.frame_element().bounding_box()
        except Exception:
            continue
        if not fb:
            continue
        for r in f.evaluate(RECTS_JS, CONTROLS):
            x, y = r["x"] + fb["x"], r["y"] + fb["y"]
            # only what shows inside the frame's box
            if x + r["w"] <= fb["x"] or y + r["h"] <= fb["y"] or x >= fb["x"] + fb["width"] or y >= fb["y"] + fb["height"]:
                continue
            out.append(dict(r, x=x, y=y, where=f.url.split("?", 1)[-1][:40]))
    return out


def touching(chip, rs):
    return [r for r in rs if chip["x"] < r["x"] + r["w"] and r["x"] < chip["x"] + chip["width"]
            and chip["y"] < r["y"] + r["h"] and r["y"] < chip["y"] + chip["height"]]


def settle_frames(page, n, timeout=25.0):
    end = time.time() + timeout
    while time.time() < end:
        fs = panes(page)
        if len(fs) >= n and all(f.query_selector("textarea") for f in fs.values()):
            return fs
        page.wait_for_timeout(150)
    return panes(page)


def check(page, label, shots, w):
    page.wait_for_selector("[data-help-button]", timeout=15000)
    page.wait_for_timeout(3400)           # the chip places itself every 1.5 s; frames lay out
    chip = page.locator("[data-help-button]").bounding_box()
    assert chip, f"{label} {w}: no chip"
    hit = touching(chip, controls(page))
    if shots:
        page.screenshot(path=str(Path(shots) / f"{label}-{w}.png"))
    assert not hit, f"{label} at {w}: the chip {chip} covers {hit[:4]}"
    return chip


def test_chip_covers_no_composer_anywhere(harness):
    from playwright.sync_api import sync_playwright
    h, errors = harness, []
    shots = os.environ.get("HELP_CHIP_SHOTS")
    with sync_playwright() as p:
        b = launch(p)
        for w, ht in SIZES:
            ctx = b.new_context(viewport={"width": w, "height": ht}, has_touch=w < 500, is_mobile=w < 500)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            # /systems, four columns (phone: the columns stack, one shows)
            page.goto(h.url + "/systems?open=" + ",".join(SYSTEMS), wait_until="domcontentloaded")
            settle_frames(page, 1 if w < 500 else 4)
            check(page, "systems", shots, w)
            # /talk, the composer of the page itself
            page.goto(h.url + "/talk?thread=" + THREADS["world"], wait_until="domcontentloaded")
            page.wait_for_selector("textarea", timeout=15000)
            check(page, "talk", shots, w)
            # /wall, the central thread open beside
            if w >= 500:
                page.goto(h.url + "/wall", wait_until="domcontentloaded")
                page.wait_for_selector("button.wo-sym", timeout=15000)
                page.locator("button.wo-sym").first.click()
                page.wait_for_selector("button.wo-th", timeout=15000)
                page.locator("button.wo-th").first.click()
                end = time.time() + 20
                while time.time() < end and not any("pane=wall-" in f.url and f.query_selector("textarea") for f in page.frames):
                    page.wait_for_timeout(150)
                assert any("pane=wall-" in f.url for f in page.frames), "the central thread did not open beside"
                check(page, "wall", shots, w)
            ctx.close()
        b.close()
    assert not errors, errors


def test_chip_is_faint_at_rest_full_on_hover_and_focus(harness):
    from playwright.sync_api import sync_playwright
    h = harness
    with sync_playwright() as p:
        b = launch(p)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(h.url + "/talk?thread=" + THREADS["world"], wait_until="domcontentloaded")
        chip = page.locator("[data-help-button]")
        chip.wait_for(timeout=15000)
        page.mouse.move(5, 5)
        page.wait_for_timeout(400)
        rest = float(chip.evaluate("e => getComputedStyle(e).opacity"))
        bg = chip.evaluate("e => getComputedStyle(e).backgroundColor")
        assert rest <= 0.3, rest
        assert bg in ("rgba(0, 0, 0, 0)", "transparent"), bg
        chip.hover()
        page.wait_for_timeout(400)
        assert float(chip.evaluate("e => getComputedStyle(e).opacity")) > 0.95
        page.mouse.move(5, 5)
        page.wait_for_timeout(400)
        chip.focus()
        page.keyboard.press("Shift+Tab")
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)
        assert float(chip.evaluate("e => getComputedStyle(e).opacity")) > 0.95, "keyboard focus does not bring it up"
        b.close()
