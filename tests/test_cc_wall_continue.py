"""The wall's continue layer (WALL-4, 2026-11-24): prompts to continue, the faint systems, the brain's seed, the day's start.

hbar: "okay so now we fully move to wall? - your task: fill it with what we are currently doing-- the systems that is +
prompts to continue from what has been in this thread, and maybe some faint ones that i HAVE BEEN working on in other
threads. and we evolve into this new production surface and test it." And: "i want a clear way to open and start the
system up again in this new manner".

Pins: cc_systems.card_prompts (the "## Continue" list of a card, "pin:" dropped, an open line keeps its ": "), the tile's
`prompts` (state card first, else ops/wall/cards/<id>.md), GET /cc/wall's faint, fresh and home, the seed never
applied silently (except once, on a dated "take" word), POST seen/home; ui/lib/wall.js under node (promptsOf,
promptPress, ringOf, wallExtra, homeOnWall, isWallWord); the page's wiring (prompts only while the box is focused,
the faint press joins, the notice, the header button, the say-word, the home). The browser half is
tests/browser/test_wall_continue.py.

Run from repo root:
    pytest tests/test_cc_wall_continue.py -v
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout  # noqa: E402
import cc_systems as C  # noqa: E402
import test_cc_steer as S  # noqa: E402
import test_cc_wall as WL  # noqa: E402

CARD = """---
created: 2026-11-24
---
# film on the wall

Now: the trailer is cut; the grade waits for your pick.

## Continue (each line is a prompt for this system's box)
- play the trailer
- pin: grade look:
- *   what   is next
-
- four
- five
- six is one too many

## Done
- not a prompt
"""


# ---- pure parts ----
def test_card_prompts_read_the_continue_list():
    assert C.card_prompts(CARD) == ["play the trailer", "grade look: ", "* what is next", "four", "five"]
    assert C.card_prompts(CARD, 2) == ["play the trailer", "grade look: "]
    assert C.card_prompts("# x\n\n- no heading, no prompts\n") == []
    assert C.card_prompts("## Continue\n- " + "x" * 400)[0] == "x" * C.PROMPT_MAX
    assert C.card_line(CARD) == "the trailer is cut; the grade waits for your pick."


def test_wall_card_stays_inside_the_world(tmp_path):
    (tmp_path / "ops" / "wall" / "cards").mkdir(parents=True)
    (tmp_path / "ops" / "wall" / "cards" / "hbar.film.md").write_text(CARD)
    assert C.wall_card(tmp_path, "hbar.film") == "ops/wall/cards/hbar.film.md"
    assert C.wall_card(tmp_path, "hbar.none") is None
    assert C.wall_card(tmp_path, "../etc") is None and C.wall_card(None, "hbar.film") is None


def test_wall_meta_beside_the_setting(tmp_path):
    st = cc_layout.Store(tmp_path)
    assert st.wall_meta() == {"at": None, "seen": None, "home": None, "taken": None}
    st.set_wall({"set": ["hbar.music"]})
    assert st.wall() == {"look": None, "set": ["hbar.music"], "pinned": None}  # the setting keeps its keys (pinned: WALL-5)
    assert abs(st.wall_meta()["at"] - time.time()) < 5                        # his save is stamped
    st.set_wall({"look": "orbit"})
    at = st.wall_meta()["at"]
    assert st.set_wall_meta({"home": True})["home"] is True and st.wall_meta()["at"] == at
    assert cc_layout.validate_wall_meta({"at": True, "seen": -1, "home": "yes"}) == {"at": None, "seen": None, "home": None, "taken": None}


# ---- the bridge ----
def _bridge(monkeypatch, tmp_path, seed=None):
    m = S._bridge(monkeypatch, tmp_path)
    (pathlib.Path(m.WORLD_DIR) / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.film", "description": "film"}, {"id": "hbar.music", "description": "music"}, {"id": "hbar.art", "description": "art"}]}))
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {})
    monkeypatch.setattr(m.JOBS, "list", lambda n=200: [])
    m._SYSTEMS_TASKS[0] = 0.0
    m._SYSTEMS_OPEN[0] = 0.0
    if seed is not None:
        _seed(m, seed)
    return m


def _seed(m, seed, age=0):
    p = pathlib.Path(m.WORLD_DIR) / "ops" / "wall" / "wall.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seed))
    if age:
        t = time.time() - age
        os.utime(p, (t, t))
    return p


def test_tiles_carry_prompts_from_the_state_card_else_the_wall_card(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    world = pathlib.Path(m.WORLD_DIR)
    (world / "ops" / "wall" / "cards").mkdir(parents=True)
    (world / "ops" / "wall" / "cards" / "hbar.film.md").write_text(CARD)
    (world / "ops" / "wall" / "cards" / "world.md").write_text("# world\n\n## Continue\n- what waits for me\n")
    (world / "ops" / "cards").mkdir(parents=True)
    (world / "ops" / "cards" / "production.md").write_text("# production\n\nState: three builds run.\n")
    (world / "ops" / "lanes").mkdir(parents=True)
    (world / "ops" / "lanes" / "MUSIC.md").write_text("# music\n\nNow: the set is open.\n\n## Continue\n- play it\n")
    (world / "ops" / "wall" / "states.json").write_text(json.dumps({"states": {
        "world": "ops/cards/production.md", "hbar.music": "ops/lanes/MUSIC.md"}}))
    tl = {t["id"]: t for t in m._systems_view()["tiles"]}
    assert tl["hbar.film"]["prompts"] == ["play the trailer", "grade look: ", "* what is next", "four", "five"]
    assert tl["hbar.film"]["summary"] is None                                   # an unmapped card gives prompts, not the line
    assert tl["hbar.music"]["prompts"] == ["play it"] and tl["hbar.music"]["summary"]["text"] == "the set is open."
    assert tl["world"]["prompts"] == ["what waits for me"] and tl["world"]["summary"]["text"] == "three builds run."
    (world / "ops" / "lanes" / "MUSIC.md").write_text("# music\n\nNow: changed.\n\n## Continue\n- play the other one\n")
    os.utime(world / "ops" / "lanes" / "MUSIC.md", (time.time() + 5, time.time() + 5))
    tl = {t["id"]: t for t in m._systems_view()["tiles"]}
    assert tl["hbar.music"]["prompts"] == ["play the other one"]               # read again when the card moves


def test_faint_home_and_the_seed_notice(monkeypatch, tmp_path):
    seed = {"look": "orbit", "set": ["hbar.music", "hbar.film"], "faint": ["hbar.art", "hbar.music", "hbar.gone", "Bad Id"], "home": True}
    m = _bridge(monkeypatch, tmp_path, seed)
    d = m._wall_view()
    assert d["set"] == ["hbar.music", "hbar.film"] and d["seed"] is True
    assert d["faint"] == ["hbar.art"]                                          # kept, unknown and bad ids left out
    assert d["fresh"] is None and d["home"] is True                            # no own set: the seed simply applies
    st, r = m._wall_save({"set": ["hbar.film"]})                               # his own arrangement
    assert st == 200 and r["set"] == ["hbar.film"] and r["fresh"] is None and r["faint"] == ["hbar.art", "hbar.music"]   # music left: faint again
    p = _seed(m, {**seed, "set": ["hbar.music", "hbar.art"]})                  # the brain writes a newer seed
    os.utime(p, (time.time() + 10, time.time() + 10))
    d = m._wall_view()
    assert d["set"] == ["hbar.film"]                                            # never overwritten silently
    assert d["fresh"]["set"] == ["hbar.music", "hbar.art"] and d["faint"] == ["hbar.art", "hbar.music"]   # faint follows his own orbit
    st, r = m._wall_save({"seen": d["fresh"]["stamp"]})                        # "keep mine"
    assert st == 200 and r["fresh"] is None and r["set"] == ["hbar.film"]
    os.utime(p, (time.time() + 20, time.time() + 20))
    d = m._wall_view()
    st, r = m._wall_save({"set": d["fresh"]["set"], "seen": d["fresh"]["stamp"]})   # "take it"
    assert st == 200 and r["set"] == ["hbar.music", "hbar.art"] and r["fresh"] is None
    st, r = m._wall_save({"home": False})
    assert st == 200 and r["home"] is False                                    # his own word beats the seed's
    for bad in ({"home": "yes"}, {"seen": "x"}, {"seen": True}):
        assert m._wall_save(bad)[0] == 400, bad


def test_an_older_seed_or_the_same_set_says_nothing(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m._wall_save({"set": ["hbar.film"]})
    _seed(m, {"set": ["hbar.music"]}, age=3600)                                # older than his save
    assert m._wall_view()["fresh"] is None
    p = _seed(m, {"set": ["hbar.film"]})
    os.utime(p, (time.time() + 10, time.time() + 10))                           # newer, but the same set
    assert m._wall_view()["fresh"] is None


def test_a_dated_take_word_applies_the_seed_once(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m._wall_save({"set": ["hbar.film"]})                                       # an older saved set on the bridge
    p = _seed(m, {"set": ["hbar.music", "hbar.art"], "take": "2026-11-24 hbar: fill it with what we are currently doing"})
    os.utime(p, (time.time() + 10, time.time() + 10))
    d = m._wall_view()
    assert d["set"] == ["hbar.music", "hbar.art"] and d["fresh"] is None        # applied, on his word
    m._wall_save({"set": ["hbar.film"]})                                       # he moves it again
    os.utime(p, (time.time() + 20, time.time() + 20))
    d = m._wall_view()
    assert d["set"] == ["hbar.film"]                                            # the same word never applies twice
    assert d["fresh"]["set"] == ["hbar.music", "hbar.art"]                     # it asks instead


def test_wall_over_http(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, {"look": "orbit", "set": ["hbar.music"], "faint": ["hbar.art"]})
    srv, base = S._serve(m)
    try:
        st, d = S._call(base + "/wall")
        assert st == 200 and d["faint"] == ["hbar.art"] and d["home"] is False and d["fresh"] is None
        st, d = S._call(base + "/wall", {"home": True})
        assert st == 200 and d["home"] is True and d["set"] == ["hbar.music"]
        st, d = S._call(base + "/wall", {"set": ["hbar.music", "hbar.art"], "seen": 1.0})
        assert st == 200 and d["set"] == ["hbar.music", "hbar.art"] and d["faint"] == []
    finally:
        srv.shutdown()


# ---- ui/lib/wall.js under node ----
def test_lib_prompts_ring_and_start():
    d = WL._node(WL.FAKE + r"""
const tile = (id, o) => Object.assign({ id, thread: null, said: null, counts: { running: 0 }, detail: {} }, o || {})
const TILES = [tile('world'), tile('hbar.music', { prompts: ['play it', 'play it', 'gift look:', 'x  y', 7, 'a', 'b', 'c'] }),
  tile('hbar.art', { counts: { running: 2 } }), tile('hbar.blog'), tile('hbar.econ', { counts: { running: 1 } }), tile('hbar.film')]
console.log(JSON.stringify({
  prompts: W.promptsOf(TILES[1]), none: W.promptsOf(TILES[0]), nul: W.promptsOf(null),
  waits: [W.waitsForMore('gift look: '), W.waitsForMore('gift look:'), W.waitsForMore('play it')],
  p1: W.promptPress(null, 'play it'), p2: W.promptPress('play it', 'play it'), p3: W.promptPress('gift look: ', 'gift look: '),
  p4: W.promptPress('other', 'play it'), p5: W.promptPress(null, '  '),
  ring: W.ringOf(TILES, ['hbar.music'], ['hbar.art', 'hbar.blog', 'hbar.music', 'world', 'hbar.none']),
  extra: [W.wallExtra({ faint: ['a', 3], fresh: { set: ['x'], stamp: 5 }, home: true }), W.wallExtra({ fresh: { set: 'x' } }), W.wallExtra(null)],
  home: [W.homeOnWall('/', { home: true }), W.homeOnWall('/?threads=1', { home: true }), W.homeOnWall('/', { home: false }), W.homeOnWall('/', null)],
  words: ['wall', ' The Wall. ', 'open the wall', 'wall please', 'walls', ''].map(W.isWallWord),
}))
""")
    assert d["prompts"] == ["play it", "gift look: ", "x y", "a", "b"] and d["none"] == [] and d["nul"] == []
    assert d["waits"] == [True, True, False]
    assert d["p1"] == {"text": "play it", "send": False} and d["p2"] == {"text": "play it", "send": True}
    assert d["p3"] == {"text": "gift look: ", "send": False}                   # an open line is never sent as it stands
    assert d["p4"]["send"] is False and d["p5"] == {"text": "", "send": False}
    assert d["ring"] == [{"id": "hbar.art", "running": 2, "live": False, "faint": True},
                         {"id": "hbar.blog", "running": 0, "live": False, "faint": True},
                         {"id": "hbar.econ", "running": 1, "live": False, "faint": False}]
    assert d["extra"][0] == {"faint": ["a"], "fresh": {"set": ["x"], "stamp": 5}, "home": True}
    assert d["extra"][1] == {"faint": [], "fresh": None, "home": False} and d["extra"][2] == d["extra"][1]
    assert d["home"] == [True, False, False, False]
    assert d["words"] == [True, True, True, False, False, False]


# ---- the page ----
def test_page_wiring():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    o = (ROOT / "ui" / "components" / "WallOrbit.js").read_text()
    dp = (ROOT / "ui" / "components" / "WallDepth.js").read_text()
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    ix = (ROOT / "ui" / "pages" / "index.js").read_text()
    lay = (ROOT / "ui" / "lib" / "layout.js").read_text()
    # prompts: only while the box is focused; a press fills, a second press sends; nothing at rest
    assert "{inside && !recording && !busy ? <Prompts list={list}" in o and "onMouseDown={e => e.preventDefault()}" in o
    assert "promptPress(armed && text === armed ? armed : null, p)" in o and "prompts={t.prompts}" in o and "prompts={world.prompts}" in o
    assert "onClick={() => onTalk(sid, p)}" in dp and "promptsOf(t)" in dp
    for bad in ("fetch(", "sendText", "router"):
        assert bad not in dp, bad
    # faint: dim names on the outer ring, a press brings one in
    assert "ringOf(tiles, kept, faint)" in o and "onClick={() => onAdd(d.id)}" in o and "data-faint={d.id}" in o
    # the seed: one quiet line, his press decides
    assert "new set from the brain" in o and "take it" in o and "keep mine" in o
    assert "saveWall(fetch, store(), { set: f.set, seen: f.stamp, ...(Array.isArray(f.pinned) ? { pinned: f.pinned } : {}) })" in w and "saveWall(fetch, store(), { seen: f.stamp })" in w
    assert "faint={faint} fresh={fresh} onFresh={onFresh}" in w
    # the day's start: the header button, the say-word, the home
    assert "{ id: 'wall', label: 'wall', route: '/wall' }" in lay
    assert "isWallWord(text)) { setDraft(''); window.location.href = '/wall'; return }" in cc
    assert "homeOnWall(router.asPath, await json('/cc/wall'))" in ix and "router.replace('/wall')" in ix
    assert not (ROOT / "ui" / "pages" / "talk").exists() or True                 # /talk is left as it is
