"""tests/browser/test_take.py: /take (DEMO-1, 2026-11-25) in a real browser with a synthetic microphone.

The built console + the real cc-bridge (temp folders) + a front that does Caddy's job: the harness of
test_sing_booth.py. The world's renderer is not part of the template, so its output (demo.json, the MP3s, the
draft) is written by the test where the renderer would write it.

Checks, end to end: the page opens on Record with the strip and one record control; a dropped file is kept on the
box by its hash and plays under the voice; the take lands in the booth marked surface "take" with where the track
started; spoken lines show large and the take carries its group; over a playlist track (a stand-in for the YouTube
IFrame API, the same calls the real one answers) the take carries the embed's clock pairs. On Demo: the take waits
("making"), then plays its treatments, and keep moves it to Ask; again and drop are single presses. On Ask: draft,
then the form with the address and the offer line; send stays off until the offer is written, then the press lands
as ask.send.json. The synced demo player keeps the voice on the (stand-in) embed's clock. No page error.

Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_take.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sing_booth import SERVER_JS, Harness, launch, tone_wav  # noqa: E402

FAKE_YT = r"""
(() => {
  // a stand-in for the YouTube IFrame API: a player whose clock runs at real time while "playing"
  class Player {
    constructor(el, o) {
      this.o = o; this.t = 0; this.st = 5; this.at = 0
      const f = document.createElement('iframe'); f.title = 'YouTube player'; f.style.cssText = 'width:200px;height:200px;border:0;background:#111'
      const host = typeof el === 'string' ? document.getElementById(el) : el
      host.replaceWith(f); this.f = f
      setTimeout(() => o.events && o.events.onReady && o.events.onReady({ target: this }), 30)
    }
    _now() { return this.st === 1 ? this.t + (performance.now() - this.at) / 1000 : this.t }
    _set(s) { this.st = s; if (this.o.events && this.o.events.onStateChange) this.o.events.onStateChange({ data: s }) }
    playVideo() { if (this.st !== 1) { this.at = performance.now(); setTimeout(() => this._set(1), 60) } }
    pauseVideo() { this.t = this._now(); this._set(2) }
    seekTo(s) { this.t = s; this.at = performance.now() }
    getCurrentTime() { return this._now() }
    getPlayerState() { return this.st }
    getDuration() { return 200 }
    getIframe() { return this.f }
    destroy() { try { this.f.remove() } catch (e) {} }
  }
  window.YT = { Player }
})()
"""


@pytest.fixture(scope="module")
def harness():
    pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")
    if not SERVER_JS.exists():
        pytest.skip(f"no console build at {SERVER_JS.parent.parent.parent} (npm ci && npm run build)")
    if not shutil.which("node"):
        pytest.skip("node not installed")
    tmp = Path(tempfile.mkdtemp(prefix="take-"))
    h = Harness(tmp)
    lines = h.world / "systems" / "m" / "ops" / "take"
    lines.mkdir(parents=True)
    (lines / "lines.json").write_text(json.dumps({"sets": [{"id": "k2", "title": "K2, spoken", "treatment": "phone", "groups": [
        {"n": 1, "bar": 1, "lines": ["the first line to read", "and its second"]}, {"n": 2, "bar": 21, "lines": ["the next group"]}]}]}))
    lst = h.world / "systems" / "m" / "ops" / "listening"
    lst.mkdir(parents=True)
    (lst / "2026-11-20_playlists-all.tsv").write_text("account\tplaylist_id\ttitle\tcreated\tprivacy\titem_count\tfetched\n"
                                                      "a\tPLbeats0001\tBEATS test\t2026-01-01\tprivate\t1\t2026-11-20\n")
    (lst / "2026-11-20_playlist-items.tsv").write_text("account\tplaylist_id\tplaylist_title\tvideo_id\ttitle\tchannel\tartist_guess\tduration_s\n"
                                                       "a\tPLbeats0001\tBEATS test\tabcdefghijk\tDark Beat\tProd Channel\tProd\t180\n")
    h.start()
    voice = tmp / "voice.wav"
    tone_wav(voice, 6, 220, 0.35)
    h.voice = voice
    yield h
    h.stop()
    shutil.rmtree(tmp, ignore_errors=True)


def take_dir(h) -> Path:
    return h.home / "out" / "studio" / "take"


def newest_card(h) -> tuple[Path, dict]:
    w = max(h.takes(), key=lambda x: x.stat().st_mtime)
    return w, json.loads(w.with_suffix(".json").read_text())


def fake_demo(h, w: Path, embed=False):
    d = take_dir(h) / "demos" / w.stem
    (d / "v01").mkdir(parents=True, exist_ok=True)
    tr = []
    for tid, label in (("dry", "dry"), ("chain", "warm"), ("phone", "phone")):
        shutil.copy(h.voice, d / "v01" / f"voice_{tid}.wav")
        it = {"id": tid, "label": label, "voice": f"demos/{w.stem}/v01/voice_{tid}.wav"}
        if not embed:
            it["mix"] = it["voice"]
        tr.append(it)
    v = {"v": "v01", "treatments": tr, "first": "dry", "voice_s": 6}
    if embed:
        v["sync"] = {"rate": 1.0, "video_at_voice_0": 0.0, "pairs": 20, "residual_ms_max": 4}
    (d / "demo.json").write_text(json.dumps({"versions": [v], "status": "ready"}))
    return d


def errs(pg, bucket):
    pg.on("pageerror", lambda e: bucket.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and "Failed to load resource" not in m.text and bucket.append(m.text))


def test_record_over_a_file_then_demo_keep_ask_send(harness):
    from playwright.sync_api import sync_playwright
    h = harness
    track = h.root / "their beat.wav"
    tone_wav(track, 2.5, 440, 0.4, wobble=False)
    errors = []
    with sync_playwright() as p:
        b = launch(p, h.voice)
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        errs(pg, errors)
        pg.goto(h.url + "/take")
        pg.locator(".tk-strip").wait_for()
        assert pg.locator(".tk-st.on").inner_text().startswith("record")
        assert pg.locator(".tk-btn").count() == 1 and "Wired headphones" in pg.locator(".tk-hp").inner_text()
        pg.locator("input[type=file]").set_input_files(str(track))
        pg.locator(".tk-under", has_text="their beat").wait_for(timeout=10000)
        kept = list((take_dir(h) / "backing").glob("*.wav"))
        assert len(kept) == 1 and kept[0].read_bytes() == track.read_bytes()
        pg.locator(".tk-btn").click()
        pg.locator(".tk-word", has_text="kept").wait_for(timeout=25000)      # the track ends, the take stops by itself
        w, card = newest_card(h)
        o = card["over"]
        assert card["page"]["surface"] == "take" and o["kind"] == "file" and o["backing"] == kept[0].stem and o["mine"] is False
        assert o["track_start_in_take_s"] and o["track_start_in_take_s"] > o["marker_in_take_s"] > 0.2
        # Demo: making, then ready
        pg.locator(".tk-st", has_text="demo").click()
        pg.locator(".tk-tag.making").wait_for(timeout=8000)
        fake_demo(h, w)
        pg.reload()
        pg.locator(".tk-st", has_text="demo").click()
        pg.locator(".tk-tag.ready").wait_for(timeout=8000)
        pg.locator(".tk-row button").first.click()
        pg.locator(".tk-tr button").nth(1).click()
        pg.wait_for_function("(() => { const a = document.querySelector('audio'); return a && !a.paused && a.currentTime > 0.2 })()", timeout=8000)
        pg.locator(".tk-w.keep").click()
        pg.locator(".tk-st.on", has_text="ask").wait_for(timeout=8000)          # kept over their track: on to Ask
        v = json.loads((take_dir(h) / "demos" / w.stem / "verdict.json").read_text())
        assert v["word"] == "keep" and v["treatment"] == "chain"
        pg.locator(".tk-w.keep", has_text="draft").click()
        pg.locator(".tk-tag.drafting").wait_for(timeout=8000)
        d = take_dir(h) / "demos" / w.stem
        assert (d / "ask.want.json").exists()
        (d / "ask.json").write_text(json.dumps({"to": "prod@mail.co", "subject": "can I use \"their beat\"?",
                                                "body": "Hi Prod,\n\nI recorded a verse.\n\nI would like to use it. [your offer: write it here]\n\nThanks,\nhbar",
                                                "contact": {"found_on": "https://www.youtube.com/watch?v=abcdefghijk", "line": "For leases: prod@mail.co"},
                                                "attach": str(d / "v01" / "voice_chain.wav")}))
        pg.reload()
        pg.locator(".tk-st", has_text="ask").click()
        pg.locator(".tk-form").wait_for(timeout=8000)
        send = pg.locator(".tk-form button[type=submit]")
        assert send.is_disabled()
        if os.environ.get("TAKE_SHOTS"):
            pg.screenshot(path=os.path.join(os.environ["TAKE_SHOTS"], "ask-1440.png"), full_page=True)
        box = pg.locator(".tk-form textarea")
        box.fill(box.input_value().replace("[your offer: write it here]", "I can pay 150 EUR for the lease."))
        assert send.is_enabled()
        send.click()
        pg.locator(".tk-tag.sending").wait_for(timeout=8000)
        s = json.loads((d / "ask.send.json").read_text())
        assert s["to"] == "prod@mail.co" and "150 EUR" in s["body"]
        b.close()
    assert not errors, errors


def test_lines_and_an_embed_take_and_synced_demo(harness):
    from playwright.sync_api import sync_playwright
    h = harness
    errors = []
    with sync_playwright() as p:
        b = launch(p, h.voice)
        ctx = b.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script(FAKE_YT)
        pg = ctx.new_page()
        errs(pg, errors)
        pg.goto(h.url + "/take")
        pg.locator(".tk-strip").wait_for()
        # spoken lines: shown large, one take per group
        pg.locator(".tk-chip", has_text="K2, spoken").click()
        pg.locator(".tk-read", has_text="the first line to read").wait_for()
        pg.locator(".tk-btn").click()
        pg.locator(".tk.rec").wait_for(timeout=8000)
        pg.wait_for_timeout(1500)
        pg.locator(".tk-btn").click()
        pg.locator(".tk-word", has_text="kept").wait_for(timeout=15000)
        _, card = newest_card(h)
        assert card["page"]["lines"]["set"] == "k2" and card["page"]["lines"]["group"] == 1 and card["over"]["kind"] == "none"
        pg.locator(".tk-read", has_text="the next group").wait_for()            # on to the next group by itself
        pg.locator(".tk-chip", has_text="none").first.click()
        # a playlist track through the (stand-in) embed
        pg.locator(".tk-chip", has_text="orfeo library").click()            # DEMO-2: one search over his library
        pg.locator(".tk-q input").fill("dark prod")
        pg.locator(".tk-it", has_text="Dark Beat").click()
        pg.locator(".tk-under iframe").wait_for(timeout=8000)
        pg.wait_for_function("!document.querySelector('.tk-btn').disabled", timeout=8000)
        pg.locator(".tk-btn").click()
        pg.locator(".tk.rec").wait_for(timeout=8000)
        pg.wait_for_timeout(3500)
        pg.locator(".tk-btn").click()
        pg.locator(".tk-word", has_text="kept").wait_for(timeout=15000)
        w, card = newest_card(h)
        o = card["over"]
        assert o["kind"] == "embed" and o["video_id"] == "abcdefghijk" and o["marker_in_take_s"] is not None
        assert len(o["pairs"]) >= 5 and o["pairs_all"] >= 10 and abs(o["fit_rate"] - 1) < 0.03, o   # a 3 s take; the scatter shrinks over minutes
        assert o["embed_start_in_take_s"] > o["marker_in_take_s"]
        # the synced demo
        fake_demo(h, w, embed=True)
        pg.goto(h.url + "/take?demo=" + w.stem)
        pg.locator(".tk-tr button").first.wait_for(timeout=8000)
        pg.locator(".tk-tr button").first.click()
        pg.locator(".tk-sync", has_text="in sync").wait_for(timeout=15000)
        drift = pg.evaluate("window.__takeDrift.slice(-8)")
        assert drift and max(abs(x) for x in drift) < 120, drift
        b.close()
    assert not errors, errors


def test_orfeo_library_search_live_and_blocked_embed(harness):
    """DEMO-2: the orfeo library search under the voice. Typing finds his library (no YouTube call); the press
    searches YouTube through the (stubbed) One door; a result whose embedding is off is greyed with its reason, a
    press on it sets nothing and says why, the one line offers "drop the file instead"; a playable result goes under
    the take through the embed."""
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "cc"))
    import cc_find
    h = harness
    calls = []

    def yt(action, key, q):
        calls.append(action)
        if action == cc_find.SEARCH_ACTION:
            return {"items": [{"id": {"videoId": "goodgoodgo1"}, "snippet": {"title": "Lose Yourself (Instrumental)", "channelTitle": "Eminem"}},
                              {"id": {"videoId": "blockedbea1"}, "snippet": {"title": "Lose Control Beat", "channelTitle": "A Label"}}]}
        ids = q["id"].split(",")
        if q["part"] == "status":
            return {"items": [{"id": i, "status": {"embeddable": i != "blockedbea1", "privacyStatus": "public"}} for i in ids]}
        return {"items": [{"id": i, "contentDetails": {"duration": "PT3M5S"}} for i in ids]}

    lst = h.world / "systems" / "m" / "ops" / "listening"
    (lst / "listen.json").write_text(json.dumps({"first": ["beats"]}))           # the BEATS series comes first
    h.bridge.LISTEN._cache = None
    h.bridge.FIND = cc_find.Find(h.bridge.LISTEN, h.bridge.TAKE, h.root / "find-state", get=yt)
    bad = []
    shots = os.environ.get("DEMO2_SHOTS")
    with sync_playwright() as p:
        b = launch(p, h.voice)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_init_script(FAKE_YT)
        pg = ctx.new_page()
        errs(pg, bad)
        pg.goto(h.url + "/take")
        pg.locator(".tk-eye", has_text="orfeo").wait_for(timeout=15000)
        pg.locator(".tk-chip", has_text="orfeo library").click()
        pg.locator(".tk-find header", has_text="orfeo library").wait_for()
        pg.locator(".tk-sc button", has_text="from BEATS test").wait_for()          # the BEATS shortcut on top
        pg.wait_for_timeout(400)
        opened = len(calls)                                  # opening checks the recent tracks' flags (a cached week)
        pg.locator(".tk-q input").fill("dark")
        pg.locator(".tk-it", has_text="Dark Beat").wait_for()
        pg.wait_for_timeout(400)
        assert len(calls) == opened                                                # typing never reaches YouTube
        pg.locator(".tk-q input").fill("lose")
        pg.locator(".tk-note", has_text="Nothing in your tracks").wait_for()
        pg.locator(".tk-q button", has_text="search YouTube").click()
        good = pg.locator(".tk-it", has_text="Lose Yourself (Instrumental)")
        good.wait_for(timeout=8000)
        blocked = pg.locator(".tk-it.off", has_text="Lose Control Beat")
        blocked.wait_for()
        assert "embedding is off" in blocked.inner_text()
        assert "3:05" in good.inner_text()
        pg.locator(".tk-grey", has_text="embedding off").wait_for()
        assert pg.locator(".tk-grey button", has_text="drop the file instead").count() == 1
        if shots:
            pg.screenshot(path=os.path.join(shots, "01-orfeo-search.png"))
        blocked.click(force=True)                            # aria-disabled: a press still says why
        pg.locator(".tk-word.err", has_text="embedding is off").wait_for()
        assert pg.locator(".tk-under").count() == 0                                # nothing set under the take
        good.click()
        pg.locator(".tk-under iframe").wait_for(timeout=8000)
        assert "Lose Yourself" in pg.locator(".tk-under").inner_text()
        if shots:
            pg.screenshot(path=os.path.join(shots, "02-picked.png"))
        assert set(calls) <= {cc_find.SEARCH_ACTION, cc_find.VIDEOS_ACTION} and calls.count(cc_find.SEARCH_ACTION) == 1 and cc_find.SEARCH_ACTION not in calls[:opened]
        # an empty box again: recent is empty in this harness (no embed takes yet in this test's order), shortcuts stay
        pg.locator(".tk-chip", has_text="orfeo library").click()              # a pick closed the list; open it again
        pg.locator(".tk-q input").fill("")
        pg.locator(".tk-sc button", has_text="from BEATS test").wait_for()
        if shots:
            pg.set_viewport_size({"width": 390, "height": 900})
            pg.locator(".tk-q input").fill("lose")
            pg.locator(".tk-q button").click()
            pg.locator(".tk-it.off").wait_for()
            pg.screenshot(path=os.path.join(shots, "03-orfeo-search-phone.png"), full_page=True)
        b.close()
    assert not bad, bad


def test_fetched_copy_under_the_voice_parts_and_the_library_strip(harness):
    """DEMO-3: a YouTube pick whose copy is in the private library plays from the copy (kind yt, like a file) and the
    take carries the video id; a pick YouTube refused keeps the embed and offers one press "fetch through my Mac", which
    lands as fetch/<id>.want.json with via_mac; a demo over the copy has a parts strip (voice, drums, their vocal) and
    the Ask screen shows each fetched track on the strip fetched / demo made / asked / yes / no."""
    from playwright.sync_api import sync_playwright
    h = harness
    lib = h.root / "library"
    f = lib / "abcdefghijk"
    f.mkdir(parents=True, exist_ok=True)
    tone_wav(f / "audio.wav", 8, 110, 0.3)
    (f / "track.json").write_text(json.dumps({"video_id": "abcdefghijk", "title": "Dark Beat", "artist": "Prod", "state": "demo made",
                                              "audio": "audio.wav", "wav": "audio.wav", "demos": [{}], "grid": {"bpm": 120, "key": "A minor"},
                                              "contact": "prod@beats.example", "claims": ["FREE FOR NON-PROFIT, credit me"]}))
    h.bridge.TAKE.library = lib
    bad = []
    shots = os.environ.get("DEMO3_SHOTS")
    with sync_playwright() as p:
        b = launch(p, h.voice)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        ctx.add_init_script(FAKE_YT)
        pg = ctx.new_page()
        errs(pg, bad)
        pg.goto(h.url + "/take")
        pg.locator(".tk-chip", has_text="orfeo library").wait_for(timeout=15000)
        pg.locator(".tk-chip", has_text="orfeo library").click()
        pg.locator(".tk-q input").fill("dark")
        pg.locator(".tk-it", has_text="Dark Beat").click()
        pg.locator(".tk-under", has_text="your private copy").wait_for(timeout=8000)
        assert pg.locator(".tk-under iframe").count() == 0                        # the copy, not the embed
        if shots:
            pg.screenshot(path=os.path.join(shots, "01-record-over-the-copy.png"))
        n0 = len(h.takes())
        pg.locator(".tk-btn").click()
        pg.wait_for_timeout(2500)
        pg.locator(".tk-btn").click()
        for _ in range(40):
            if len(h.takes()) > n0:
                break
            pg.wait_for_timeout(250)
        w, card = newest_card(h)
        assert card["over"]["kind"] == "yt" and card["over"]["video_id"] == "abcdefghijk"
        assert card["over"]["track_start_in_take_s"] is not None
        # a demo over the copy, with the track's parts (the renderer's output, written here)
        d = fake_demo(h, w)
        dj = json.loads((d / "demo.json").read_text())
        for k in ("drums", "vocals"):
            shutil.copy(h.voice, d / "v01" / f"stem_{k}.wav")
        dj["versions"][0]["stems"] = {"drums": f"demos/{w.stem}/v01/stem_drums.wav", "vocals": f"demos/{w.stem}/v01/stem_vocals.wav"}
        (d / "demo.json").write_text(json.dumps(dj))
        pg.reload()
        pg.locator(".tk-st", has_text="demo").click()
        pg.locator(".tk-row", has_text="Dark Beat").first.locator("button").first.click()
        pg.locator(".tk-parts").wait_for(timeout=8000)
        assert pg.locator(".tk-parts .tk-chip", has_text="their vocal").count() == 1
        pg.locator(".tk-parts .tk-w").click()
        pg.locator(".tk-parts .tk-chip", has_text="drums").click()
        assert pg.locator(".tk-parts .tk-chip.on", has_text="drums").count() == 0
        if shots:
            pg.screenshot(path=os.path.join(shots, "02-demo-parts.png"))
        # the strip on Ask
        pg.locator(".tk-st", has_text="ask").click()
        row = pg.locator("[aria-label='orfeo library, private'] .tk-row", has_text="Dark Beat")
        row.wait_for(timeout=8000)
        assert row.locator(".tk-libst i.on").inner_text().lower() == "demo made"
        assert "FREE FOR NON-PROFIT" in row.inner_text()
        if shots:
            pg.screenshot(path=os.path.join(shots, "03-ask-library-strip.png"), full_page=True)
        # a pick YouTube refused: the embed stays, one press through the Mac
        (take_dir(h) / "fetch").mkdir(parents=True, exist_ok=True)
        (take_dir(h) / "fetch" / "lmnopqrstuv.json").write_text(json.dumps({"state": "refused", "why": "YouTube's bot wall", "via_mac": False}))
        lst = h.world / "systems" / "m" / "ops" / "listening"
        with (lst / "2026-11-20_playlist-items.tsv").open("a") as fh:
            fh.write("a\tPLbeats0001\tBEATS test\tlmnopqrstuv\tWall Beat\tWall Channel\tWall\t150\n")
        h.bridge.LISTEN._cache = None
        pg.reload()
        pg.locator(".tk-chip", has_text="orfeo library").click()
        pg.locator(".tk-q input").fill("wall")
        pg.locator(".tk-it", has_text="Wall Beat").click()
        btn = pg.locator(".tk-under button", has_text="fetch through my Mac")
        btn.wait_for(timeout=8000)
        assert pg.locator(".tk-under iframe").count() == 1                        # the embed stays meanwhile
        btn.click()
        want = take_dir(h) / "fetch" / "lmnopqrstuv.want.json"
        for _ in range(20):
            if want.exists():
                break
            pg.wait_for_timeout(250)
        assert json.loads(want.read_text())["via_mac"] is True
        b.close()
    assert not bad, bad
