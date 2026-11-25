"""tests/browser/test_line_talk.py: press a line and keep talking; read a thread from the wall (LINE-TALK-1, 2026-11-25).

hbar: "if i can click the line say the line say, 'The court: ' -- and this automatically either does what the ask
button does or what note does.. but point is by clicking i can continue to talk without needing to press too much".
And: "how can we read thread thru wall? like something pop out?".

    Chromium (Playwright) -> the PANES-FIX-1 front (test_panes_health.py's Harness): /cc/* answered by a fake bridge
    that logs every request; /api/bf/sessions/<id>/messages from its table; the rest to the built console. A synthetic
    microphone: a fake SpeechRecognition (the chat) and a fake MediaRecorder (the wall), so dictation runs end to end.

Checks:
  chat  one press on a list item opens a slot right under it, bound to the line, the cursor in it; a press on a
        heading opens a second; a press on a plain sentence still underlines the clause (no slot); a drag still
        selects; Enter sends ONE /cc/chat whose message carries both lines and both remarks; the slots go.
  chat  holding a line for half a second opens its slot and dictates into it; the release stops it; the words stay,
        nothing is sent; the slot's mic does the same with two presses.
  wall  a press on a system's line opens its last answer as a card over the wall (no navigation, no send); Esc and
        the x close it; a press on a point line in it opens a slot; holding a line records into the slot
        (POST /cc/transcribe, nothing sent); Enter sends one About-this message into that thread (the steer door).
  view  the corner switch: wall -> columns opens /systems with the kept set as columns and notes it (POST /cc/view);
        the choice is kept, so /wall goes on to the columns; columns -> wall comes back.
No page error in any of it.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_line_talk.py -q
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("lt1_panes_health", Path(__file__).with_name("test_panes_health.py"))
_ph = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ph)
BUILD, SERVER_JS, Harness, launch = _ph.BUILD, _ph.SERVER_JS, _ph.Harness, _ph.launch

T = {s: f"{i:08x}-0000-4000-8000-0000000000{i:02d}" for i, s in enumerate(["world", "hbar.film", "hbar.music", "chat"], 1)}
ANSWER = ("## Where it stands\n\n"
          "- **The court:** three rulings wait\n"
          "- the trailer is cut to 40 s\n\n"
          "A plain sentence here, with some words to press. And another one after it.\n\n"
          "| item | state |\n|---|---|\n| K2 | done |\n")
_ph.API.update({f"/sessions/{T['chat']}/messages": {"messages": [{"role": "user", "content": "where are we"},
                                                                   {"role": "assistant", "content": ANSWER, "created_at": "2026-11-25T10:00:00Z"}]},
                f"/sessions/{T['hbar.film']}/messages": {"messages": [{"role": "assistant", "content": ANSWER, "created_at": "2026-11-25T10:00:00Z"}]},
                f"/sessions/{T['world']}/messages": {"messages": [{"role": "assistant", "content": "**Today:** two jobs run\n\nnothing else", "created_at": "2026-11-25T10:00:00Z"}]}})

MIC = r"""
(() => {
  window.__sr = 0; window.__mr = 0
  class FakeSR {
    start() { window.__sr++; this.on = true; setTimeout(() => { if (this.on && this.onresult) this.onresult({ results: [Object.assign([{ transcript: 'take the first' }], { isFinal: true })] }) }, 120) }
    stop() { if (!this.on) return; this.on = false; setTimeout(() => this.onend && this.onend(), 20) }
    abort() { this.stop() }
  }
  window.SpeechRecognition = FakeSR; window.webkitSpeechRecognition = FakeSR
  const md = navigator.mediaDevices || {}
  md.getUserMedia = async () => ({ getTracks: () => [{ stop() {} }] })
  try { Object.defineProperty(navigator, 'mediaDevices', { value: md, configurable: true }) } catch (e) {}
  class FakeMR {
    static isTypeSupported(t) { return t === 'audio/webm' }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm' }
    start() { window.__mr++; this.state = 'recording' }
    stop() { if (this.state === 'inactive') return; this.state = 'inactive'; setTimeout(() => { this.ondataavailable && this.ondataavailable({ data: new Blob(['x'], { type: 'audio/webm' }) }); this.onstop && this.onstop() }, 10) }
  }
  window.MediaRecorder = FakeMR
})()
"""


def tiles():
    def tile(sid, **o):
        t = {"id": sid, "kind": "work", "thread": T.get(sid), "said": None, "counts": {"running": 0}, "detail": {},
             "jobs": [], "summary": None, "tree_n": 0, "domain": "", "open": None, "prompts": []}
        t.update(o)
        return t
    return [tile("world", said={"text": "reading the handoff", "live": True, "waiting": False, "at": None}),
            tile("hbar.film", said={"text": "The trailer is cut to 40 s.", "live": False, "waiting": False, "at": "2026-11-25T10:00:00Z"}),
            tile("hbar.music")]


class LineHarness(Harness):
    def __init__(self, root):
        super().__init__(root)
        self.log: list[tuple[float, str, str, object]] = []
        self.wall = {"look": "grid", "set": ["hbar.film", "hbar.music"], "seed": False, "max": 16, "faint": [], "fresh": None, "home": False}

    def health(self) -> dict:
        return {**super().health(), "box": True, "posture": "cards"}

    def cc(self, method, path, body):
        b = None
        if body:
            try:
                b = json.loads(body)
            except ValueError:
                b = "<binary>"
        with self.lock:
            self.log.append((time.time(), method, path, b))
        p = path.split("?", 1)[0]
        if p == "/cc/health":
            return 200, self.health()
        if p == "/cc/systems":
            return 200, {"tiles": tiles(), "running": 0, "waits": {"court": 0, "tasks_today": 0}, "built": "x"}
        if p == "/cc/wall":
            return 200, dict(self.wall)
        if p == "/cc/threads":
            return 200, {"threads": [{"brain": T["chat"], "claude": None, "title": "CC: where are we", "started": "2026-11-25T09:00:00Z", "last": "2026-11-25T10:00:00Z"}], "archived_count": 0}
        if p.startswith("/cc/threads/") and p.endswith("/say"):
            return 202, {"ok": True, "system": "x", "thread": p.split("/")[3]}
        if p == "/cc/transcribe":
            return 200, {"ok": True, "text": "from the clip"}
        if p == "/cc/view":
            return 200, {"ok": True}
        if p == "/cc/chat":
            return 200, {"reply": "noted", "thread": T["chat"]}
        if p == "/cc/surfaces":
            return 200, {"surfaces": []}
        return super().cc(method, path, body)

    def calls(self, method=None, prefix=""):
        with self.lock:
            return [x for x in self.log if (method is None or x[1] == method) and x[2].startswith(prefix)]


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {BUILD} (set NOUS_CONSOLE_BUILD after npm run build)")
    _ph.HEALTH_DELAY = 0
    root = Path(tempfile.mkdtemp(prefix="line-talk-"))
    h = LineHarness(root).start()
    yield h
    h.stop()
    shutil.rmtree(root, ignore_errors=True)


def _page(p, h, path, width=1440, local=None):
    b = launch(p)
    ctx = b.new_context(viewport={"width": width, "height": 900})
    ctx.add_init_script("try { if (!sessionStorage.getItem('__lt')) { localStorage.clear(); sessionStorage.setItem('__lt', '1');"
                        f" const s = {json.dumps(local or {})}; for (const k in s) localStorage.setItem(k, s[k]) }} }} catch (e) {{}}")
    ctx.add_init_script(MIC)
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(h.url + path)
    return b, page, errors


def _press(page, loc):
    """One plain press near the start of the line (a locator click: scrolled into view, measured when stable)."""
    box = loc.bounding_box()
    loc.click(position={"x": 12, "y": box["height"] / 2})


def test_chat_line_press_opens_bound_slots_and_sends_one_message(harness):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, page, errors = _page(p, harness, f"/talk?thread={T['chat']}")
        li = page.locator("[data-bubble] li", has_text="the trailer is cut")
        li.wait_for(timeout=20000)
        page.wait_for_timeout(600)
        n0 = len(harness.calls("POST", "/cc/chat"))
        # a plain sentence: the clause press as before, no slot
        _press(page, page.locator("[data-bubble] p", has_text="A plain sentence"))
        page.wait_for_timeout(200)
        assert page.locator("[data-lineslot]").count() == 0
        assert page.locator("[data-pickui] >> text=note").count() == 1
        page.keyboard.press("Escape")
        # a press on a bold phrase still opens its own card (a door), never a slot
        page.locator("[data-bubble] strong", has_text="The court").click()
        page.wait_for_timeout(200)
        assert page.locator("[data-infocard]").count() == 1 and page.locator("[data-lineslot]").count() == 0
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert page.locator("[data-infocard]").count() == 0
        # one press on a list item: the slot right under it, bound, the cursor in it
        _press(page, li)
        slot = page.locator("[data-lineslot]")
        slot.wait_for(timeout=3000)
        assert slot.count() == 1
        assert "About this:the trailer is cut to 40 s" in slot.inner_text().replace("\n", "")
        assert li.locator("[data-lineslot]").count() == 1                       # inside that list item, under its line
        assert page.evaluate("document.activeElement && document.activeElement.classList.contains('lt-in')")
        page.keyboard.type("cut it to 30")
        # a heading: a second slot; the first keeps its words
        _press(page, page.locator("[data-bubble] h2", has_text="Where it stands"))
        page.locator("[data-lineslot]").nth(1).wait_for(timeout=3000)
        assert page.locator("[data-lineslot]").count() == 2
        page.keyboard.type("and say where")
        assert "goes with 1 more" in page.locator("[data-lineslot]", has_text="Where it stands").inner_text()
        # a table row is a point too
        _press(page, page.locator("[data-bubble] tr", has_text="K2"))
        page.wait_for_timeout(200)
        assert page.locator("[data-lineslot]").count() == 3
        page.keyboard.press("Escape")                                           # an empty slot closes on Esc
        page.wait_for_timeout(200)
        assert page.locator("[data-lineslot]").count() == 2
        assert len(harness.calls("POST", "/cc/chat")) == n0                     # nothing sent yet
        page.locator("[data-lineslot] textarea").nth(0).click()
        page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
        sent = harness.calls("POST", "/cc/chat")[n0:]
        assert len(sent) == 1, sent
        msg = sent[0][3]["message"]
        assert 'the line I pressed: "the trailer is cut to 40 s"' in msg and "my remark: cut it to 30" in msg
        assert 'the line I pressed: "Where it stands"' in msg and "my remark: and say where" in msg
        assert msg.startswith("[remarks, each on a line I pressed or a span I marked")
        assert page.locator("[data-lineslot]").count() == 0
        # a drag still selects (the remark popup), never a slot
        hb = li.bounding_box()
        page.mouse.move(hb["x"] + 4, hb["y"] + hb["height"] / 2)
        page.mouse.down()
        page.mouse.move(hb["x"] + 120, hb["y"] + hb["height"] / 2, steps=8)
        page.mouse.up()
        page.wait_for_timeout(200)
        assert page.locator("[data-lineslot]").count() == 0
        assert page.locator("[data-pickui] >> text=note").count() == 1
        assert not errors, errors
        b.close()


def test_chat_hold_dictates_into_the_slot_and_the_mic_does_too(harness):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, page, errors = _page(p, harness, f"/talk?thread={T['chat']}")
        li = page.locator("[data-bubble] li", has_text="The court")
        li.wait_for(timeout=20000)
        page.wait_for_timeout(600)
        n0 = len(harness.calls("POST", "/cc/chat"))
        box = li.bounding_box()
        page.mouse.move(box["x"] + 30, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(900)                                              # held: the slot opens and listens
        slot = page.locator("[data-lineslot]")
        assert slot.count() == 1 and page.evaluate("window.__sr") == 1
        assert slot.locator(".lt-b.rec").count() == 1
        page.mouse.up()                                                         # the release stops it
        page.wait_for_timeout(400)
        assert page.locator("[data-infocard]").count() == 0                     # held on the bold lead: its card stays shut
        assert slot.locator("textarea").input_value() == "take the first"
        assert slot.locator(".lt-b.rec").count() == 0
        assert len(harness.calls("POST", "/cc/chat")) == n0                     # dictation never sends by itself
        # the slot's mic: press, words come, press again
        slot.locator("[data-lt-mic]").click()
        page.wait_for_timeout(300)
        assert page.evaluate("window.__sr") == 2
        slot.locator("[data-lt-mic]").click()
        page.wait_for_timeout(300)
        assert slot.locator("textarea").input_value() == "take the first take the first"
        assert len(harness.calls("POST", "/cc/chat")) == n0
        slot.locator("[data-lt-send]").click()
        page.wait_for_timeout(1000)
        sent = harness.calls("POST", "/cc/chat")[n0:]
        assert len(sent) == 1 and 'the line I pressed: "The court: three rulings wait"' in sent[0][3]["message"]
        assert not errors, errors
        b.close()


def test_wall_line_opens_the_last_answer_and_talks_in_place(harness):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, page, errors = _page(p, harness, "/wall?look=grid")
        line = page.locator('[data-read-for="hbar.film"]')
        line.wait_for(timeout=20000)
        n_say = len(harness.calls("POST", "/cc/threads/"))
        url0 = page.url
        line.click()
        card = page.locator('[data-wallread="hbar.film"]')
        card.wait_for(timeout=5000)
        card.locator("li", has_text="the trailer is cut").wait_for(timeout=5000)
        assert page.url == url0                                                  # not a navigation
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        assert card.count() == 0
        assert len(harness.calls("POST", "/cc/threads/")) == n_say               # opening and closing sends nothing
        # the centre's live line: plain words, and it opens too
        cen = page.locator('[data-read-for="world"]')
        assert "reading the handoff" in cen.inner_text()
        cen.click()
        page.locator('[data-wallread="world"]').wait_for(timeout=5000)
        assert "now: reading the handoff" in page.locator('[data-wallread="world"]').inner_text()
        page.locator('[data-wallread="world"] button[aria-label="close"]').click()
        page.wait_for_timeout(200)
        assert page.locator("[data-wallread]").count() == 0
        # line talk inside the card
        line.click()
        card.locator("li", has_text="the trailer is cut").wait_for(timeout=5000)
        _press(page, card.locator("li", has_text="the trailer is cut"))
        card.locator("[data-lineslot]").wait_for(timeout=3000)
        assert page.evaluate("document.activeElement && document.activeElement.classList.contains('lt-in')")
        page.keyboard.type("make it 30")
        # holding another line records into its slot (transcribed, never sent)
        h2 = card.locator("li", has_text="The court")
        hb = h2.bounding_box()
        page.mouse.move(hb["x"] + 30, hb["y"] + hb["height"] / 2)
        page.mouse.down()
        page.wait_for_timeout(800)
        assert page.evaluate("window.__mr") == 1
        page.mouse.up()
        page.wait_for_timeout(600)
        court = card.locator("[data-lineslot]", has_text="The court")
        assert court.locator("textarea").input_value() == "from the clip"
        assert len(harness.calls("POST", "/cc/transcribe")) == 1
        assert len(harness.calls("POST", "/cc/threads/")) == n_say
        court.locator("textarea").click()
        page.keyboard.press("Enter")
        page.wait_for_timeout(800)
        says = harness.calls("POST", "/cc/threads/")[n_say:]
        assert len(says) == 1 and says[0][2] == f"/cc/threads/{T['hbar.film']}/say"
        assert says[0][3]["message"] == 'About this: "the trailer is cut to 40 s" - make it 30\n\nAbout this: "The court: three rulings wait" - from the clip'
        assert says[0][3]["via"] == "wall"
        assert page.locator("[data-wallread]").count() == 0
        assert page.url == url0
        assert not errors, errors
        b.close()


def test_corner_switch_wall_and_columns(harness):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, page, errors = _page(p, harness, "/wall?look=orbit")
        sw = page.locator('.vw-sw button[data-view="columns"]')
        sw.wait_for(timeout=20000)
        page.wait_for_timeout(800)
        n0 = len(harness.calls("POST", "/cc/view"))
        sw.click()
        page.wait_for_url("**/systems?open=*", timeout=10000)
        assert "/systems?open=hbar.film,hbar.music" in page.url
        v = harness.calls("POST", "/cc/view")[n0:]
        assert [x[3] for x in v] == [{"view": "columns", "from": "wall"}]
        assert page.evaluate("localStorage.getItem('cc.view')") == "columns"
        # remembered: the wall goes on to the columns
        page.goto(harness.url + "/wall")
        page.wait_for_url("**/systems*", timeout=10000)
        back = page.locator('.vw-sw button[data-view="wall"]')
        back.wait_for(timeout=10000)
        back.click()
        page.wait_for_url("**/wall?view=wall", timeout=10000)
        assert page.evaluate("localStorage.getItem('cc.view')") == "wall"
        v = harness.calls("POST", "/cc/view")[n0:]
        assert [x[3] for x in v] == [{"view": "columns", "from": "wall"}, {"view": "wall", "from": "columns"}]
        page.locator(".vw-sw").wait_for(timeout=10000)
        assert not errors, errors
        b.close()
