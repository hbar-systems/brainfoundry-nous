"""tests/browser/test_listen.py: /listen and the console's radio strip (LISTEN-1, 2026-11-24) in a real browser.

    Chromium (Playwright; the YouTube IFrame API answered by a stand-in player, so no request leaves the box)
        -> the front of tests/browser/test_sing_booth.py (Caddy's job: /cc to the real bridge with the operator token)
        -> the real cc-bridge in process, whose CC_WORLD_DIR holds a small listening folder

Checks: the tuner lists the stations in their order (pinned series first, newest first; likes; own tracks; the mix;
other playlists); a press plays the station's items in sequence on the one controller; an item whose embedding is
off (error 150) is skipped and counted; next is a skip; own tracks play as files from /cc/listen/file and advance on
their end; the music keeps playing (same controller, same player, no second player) across a console page change and
when a pane that drove it is opened and closed; the bridge's play log holds start, finish, skip and blocked rows with
UTC times. No page error in any of it.

Skips without python playwright or a console build, like test_sing_booth.py.
Run:  NOUS_CONSOLE_BUILD=<ui> /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_listen.py -q
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sing_booth_harness", HERE / "test_sing_booth.py")
hb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hb
spec.loader.exec_module(hb)

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

pytestmark = pytest.mark.skipif(sync_playwright is None or not hb.SERVER_JS.exists(),
                                reason="needs python playwright and a console build (NOUS_CONSOLE_BUILD)")

V = {n: (n * 11)[:11] for n in "abcdefgh"}   # 11-character stand-in video ids
BLOCKED = [V["b"]]

YT_STUB = """
window.__yt = {made: 0, loads: [], plays: 0};
window.YT = {Player: function (el, opts) {
  window.__yt.made++;
  var d = document.getElementById(el), f = document.createElement('iframe');
  f.src = 'about:blank'; f.style.cssText = 'width:200px;height:200px;border:0';
  if (d) d.replaceWith(f);
  var self = this, state = -1, cur = null;
  var fire = function (s) { state = s; opts.events.onStateChange({data: s}); };
  this.getIframe = function () { return f; };
  this.loadVideoById = function (id) { cur = id; window.__yt.loads.push(id);
    setTimeout(function () { if (cur !== id) return;
      if ((window.__ytBlocked || []).indexOf(id) >= 0) opts.events.onError({data: 150}); else { window.__yt.plays++; fire(1); } }, 40); };
  this.cueVideoById = function (id) { cur = id; };
  this.playVideo = function () { fire(1); };
  this.pauseVideo = function () { if (state === 1) fire(2); };
  this.getCurrentTime = function () { return 12.5; };
  this.getDuration = function () { return 180; };
  this.getVideoData = function () { return {video_id: cur}; };
  window.__ytEnd = function () { fire(0); };
  setTimeout(function () { opts.events.onReady({target: self}); }, 10);
}};
if (typeof window.onYouTubeIframeAPIReady === 'function') window.onYouTubeIframeAPIReady();
"""


def tsv(p: Path, header: list[str], rows: list[list]) -> None:
    with open(p, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def make_listening(world: Path) -> None:
    d = world / "systems" / "test.music" / "ops" / "listening"
    d.mkdir(parents=True)
    tsv(d / "2026-11-23_playlists-all.tsv", ["account", "playlist_id", "title", "created", "privacy", "item_count", "fetched"], [
        ["acc", "PLbeatsTwo", "beats II", "2026-08-25", "public", 3, 3],
        ["acc", "PLbeatsOne", "beats", "2026-07-15", "public", 1, 1],
        ["acc", "PLhouseOne", "house 1", "2026-10-13", "public", 1, 1],
    ])
    items = [["acc", "PLbeatsTwo", "beats II", V["a"], "Alpha beat", "Chan A", "Artist A", "2026-01-01", "2026-11-22", 150, "Music"],
             ["acc", "PLbeatsTwo", "beats II", V["b"], "Blocked beat", "Chan B", "Artist B", "2026-01-01", "2026-11-22", 150, "Music"],
             ["acc", "PLbeatsTwo", "beats II", V["c"], "Gamma beat", "Chan C", "Artist C", "2026-01-01", "2026-11-22", 150, "Music"],
             ["acc", "PLbeatsOne", "beats", V["d"], "Delta", "Chan D", "Artist D", "2026-01-01", "2026-11-22", 150, "Music"],
             ["acc", "PLhouseOne", "house 1", V["e"], "Echo house", "Chan E", "Artist E", "2026-01-01", "2026-11-22", 300, "Music"]]
    tsv(d / "2026-11-23_playlist-items.tsv", ["account", "playlist_id", "playlist_title", "video_id", "title", "channel", "artist_guess",
                                              "published", "added", "duration_s", "category"], items)
    tsv(d / "2026-11-23_youtube-likes.tsv", ["source", "video_id", "title", "channel", "artist_guess", "published", "added", "duration_s",
                                             "category", "music"], [["LL", V["f"], "Foxtrot", "Chan F", "Artist F", "", "", 200, "Music", "yes"]])
    tsv(d / "2026-11-23_listening.tsv", ["video_id", "title", "channel", "artist_guess", "music", "own", "styles", "liked"], [
        [V["a"], "Alpha beat", "Chan A", "Artist A", "yes", "no", "beat (rap instrumental)", "no"],
        [V["e"], "Echo house", "Chan E", "Artist E", "yes", "no", "house, deep house", "yes"],
        [V["f"], "Foxtrot", "Chan F", "Artist F", "yes", "no", "afro house", "yes"]])
    (d / "2026-11-23_taste.md").write_text("# taste\n\n## Genres, most first\n\n1. House: afro house, deep house.\n2. Rap beats: boom bap.\n")
    (d / "listen.json").write_text(json.dumps({"first": ["beats"]}))
    media = world / "media"
    media.mkdir()
    hb.tone_wav(media / "one.wav", 1.2, 220, 0.2, wobble=False)
    hb.tone_wav(media / "two.wav", 1.2, 330, 0.2, wobble=False)
    tsv(d / "own.tsv", ["id", "title", "artist", "file", "duration_s"], [
        ["one", "First own", "me", "media/one.wav", 1.2], ["two", "Second own", "me", "media/two.wav", 1.2],
        ["bad", "Outside", "me", "../../etc/passwd", 1]])


@pytest.fixture(scope="module")
def site():
    root = Path(tempfile.mkdtemp(prefix="listen-browser-"))
    h = hb.Harness(root)
    make_listening(h.world)
    h.start()
    yield h
    h.stop()


def plays(h) -> list[dict]:
    p = h.home / "out" / "listen" / "plays.tsv"
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def test_listen_end_to_end(site):
    errors: list[str] = []
    with sync_playwright() as pw:
        kw = {"args": ["--autoplay-policy=no-user-gesture-required"]}
        if hb.CHROME_LIBS.is_dir():
            kw["env"] = dict(os.environ, LD_LIBRARY_PATH=str(hb.CHROME_LIBS))
        b = pw.chromium.launch(**kw)
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("https://www.youtube.com/iframe_api", lambda r: r.fulfill(status=200, content_type="text/javascript", body=YT_STUB))
        page.add_init_script(f"window.__ytBlocked = {json.dumps(BLOCKED)};")
        page.goto(site.url + "/listen")
        page.wait_for_selector("[data-station]")
        order = page.eval_on_selector_all("[data-mk]", "els => els.map(e => e.dataset.mk)")
        assert order == ["pl:PLbeatsTwo", "pl:PLbeatsOne", "likes", "own", "mix", "pl:PLhouseOne"], order

        # beats II: Alpha plays, then the blocked one is skipped and counted, Gamma plays
        page.click('[data-station="pl:PLbeatsTwo"]')
        page.wait_for_function("() => window.__bfListen && window.__bfListen.get().playing")
        assert page.text_content("[data-listen-title]") == "Alpha beat"
        assert page.text_content("[data-listen-artist]") == "Artist A"
        page.evaluate("window.__ytEnd()")                                    # Alpha ends by itself
        page.wait_for_function("() => window.__bfListen.get().now && window.__bfListen.get().now.title === 'Gamma beat' && window.__bfListen.get().playing")
        st = page.evaluate("window.__bfListen.get()")
        assert st["blocked"] == 1
        assert page.evaluate("window.__yt.loads") == [V["a"], V["b"], V["c"]]
        # the video square sits in the strip, 200x200, inside the viewport
        r = page.evaluate("(() => { const r = document.getElementById('bf-listen-yt').getBoundingClientRect(); return [r.left, r.top, r.width, r.height] })()")
        assert r[2] == 200 and r[3] == 200 and r[0] >= 0 and r[1] >= 0, r

        # a console page change: the same controller and the same player keep playing
        page.evaluate("""() => { const a = document.createElement('a'); a.href = '/sing'; a.id = 'go'; a.textContent = 'go';
                                 document.body.appendChild(a); window.__mark = 'kept'; }""")
        page.click("#go")
        page.wait_for_url("**/sing")
        assert page.evaluate("window.__mark") == "kept"                      # no reload
        assert page.evaluate("window.__bfListen.get().playing") is True
        assert page.evaluate("window.__yt.made") == 1
        assert page.is_visible("[data-listen-strip]")

        # a pane: /listen inside an iframe drives the top's player; closing the pane leaves the music on
        page.evaluate("""() => { const f = document.createElement('iframe'); f.id = 'pane'; f.src = '/listen';
                                 f.style.cssText = 'position:fixed;right:0;top:60px;width:600px;height:600px'; document.body.appendChild(f); }""")
        pane = page.frame_locator("#pane")
        pane.locator('[data-station="likes"]').click()
        page.wait_for_function("() => window.__bfListen.get().station === 'likes' && window.__bfListen.get().playing")
        assert page.text_content("[data-listen-title]") == "Foxtrot"
        assert page.evaluate("document.getElementById('pane').contentWindow.__bfListen") is None   # no second player in the pane
        assert page.evaluate("document.getElementById('pane').contentDocument.querySelector('[data-listen-strip]')") is None
        page.evaluate("document.getElementById('pane').remove()")
        page.wait_for_timeout(300)
        assert page.evaluate("window.__bfListen.get().playing") is True
        assert page.evaluate("window.__yt.made") == 1

        # next = a skip; pause; own tracks play as files and advance at their end
        page.click("[data-listen-toggle]")
        page.wait_for_function("() => !window.__bfListen.get().playing")
        page.goto(site.url + "/listen")                                      # a full reload: comes back paused, one press plays
        page.wait_for_selector("[data-listen-strip]")
        assert page.evaluate("window.__bfListen.get().station") == "likes"
        assert page.evaluate("window.__bfListen.get().playing") is False
        page.click('[data-station="own"]')
        page.wait_for_function("() => window.__bfListen.get().now && window.__bfListen.get().now.n === 'one' && window.__bfListen.get().playing")
        page.wait_for_function("() => window.__bfListen.get().now.n === 'two'", timeout=8000)   # one.wav ended by itself
        page.click("[data-listen-next]")                                     # skip two -> wraps to one
        page.wait_for_function("() => window.__bfListen.get().now.n === 'one'")
        page.wait_for_timeout(400)
        b.close()

    assert not errors, errors
    rows = plays(site)
    ev = [(r["event"], r["station_id"], r["item_id"]) for r in rows]
    assert ("start", "pl:PLbeatsTwo", V["a"]) in ev
    assert ("finish", "pl:PLbeatsTwo", V["a"]) in ev
    assert ("blocked", "pl:PLbeatsTwo", V["b"]) in ev
    assert ("start", "pl:PLbeatsTwo", V["c"]) in ev
    assert ("skip", "pl:PLbeatsTwo", V["c"]) in ev                       # the station changed while Gamma played
    assert ("pause", "likes", V["f"]) in ev
    assert ("finish", "own", "one") in ev and ("skip", "own", "two") in ev
    assert all(r["ts_utc"].endswith("Z") and len(r["ts_utc"]) == 20 for r in rows)
    assert next(r for r in rows if r["event"] == "blocked")["reason"] == "yt-150"
    assert {r["tab"] for r in rows} == {"visible"}


def test_file_door_serves_only_listed_tracks(site):
    import urllib.error
    import urllib.request
    ok = urllib.request.urlopen(site.url + "/cc/listen/file?n=one", timeout=10)
    assert ok.status == 200 and ok.read(4) == b"RIFF"
    for n in ("bad", "../media/one.wav", "nope"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(site.url + "/cc/listen/file?n=" + n, timeout=10)
        assert e.value.code == 404
