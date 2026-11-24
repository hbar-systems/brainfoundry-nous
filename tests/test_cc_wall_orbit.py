"""The wall's orbit (WALL-2, 2026-11-24): the personal look of /wall, beside the generic grid.

hbar: "it should be a full black screen as space ... only say 10 systems visible and spaced out and around, in center
is hbar symbol ... dont START WITH ALL 44 ... if i need to add a system to the page i just have ability to add".

Pins: GET/POST /cc/wall (the look and the kept set, per brain, beside the layout; the world's seed until the owner
chooses; ids outside the registry refused or dropped), and ui/lib/wall.js under node: the look pick (?look= wins),
the kept set (bridge, else browser, else the systems in use; never the centre), add and remove, the rim dot for an
outside system that runs, the ring's places, the localStorage fallback, and send in place from the centre into the
central (world) thread. Also the page's wiring: both looks, the switch, the brain's own symbol, never navigating.

Run from repo root:
    pytest tests/test_cc_wall_orbit.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_cc_steer as S  # noqa: E402
import test_cc_wall as WL  # noqa: E402   (_node, FAKE: the fake bridge for ui/lib/wall.js)

sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout  # noqa: E402


# ---- the setting ----
def test_layout_store_keeps_the_wall_beside_the_layout(tmp_path):
    st = cc_layout.Store(tmp_path)
    assert st.wall() == {"look": None, "set": None}
    assert st.set_wall({"look": "orbit"}) == {"look": "orbit", "set": None}
    assert st.set_wall({"set": ["hbar.music", "hbar.film", "hbar.music"]}) == {"look": "orbit", "set": ["hbar.music", "hbar.film"]}
    assert st.get() is None                                                    # the layout itself untouched
    for bad in ({"look": "wild"}, {"set": "hbar.music"}, {"set": ["Bad Id"]}, {"set": [f"s{i}" for i in range(17)]}, {"x": 1}, {}):
        try:
            st.set_wall(bad)
        except cc_layout.LayoutError:
            continue
        raise AssertionError(bad)
    assert st.wall() == {"look": "orbit", "set": ["hbar.music", "hbar.film"]}


def _bridge(monkeypatch, tmp_path, seed=None):
    m = S._bridge(monkeypatch, tmp_path)
    if seed is not None:
        p = pathlib.Path(m.WORLD_DIR) / "ops" / "wall" / "wall.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps(seed))
    return m


def test_wall_view_generic_without_a_seed(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    d = m._wall_view()
    assert d["look"] == "grid" and d["set"] is None and d["seed"] is False and d["max"] == 16


def test_wall_view_seed_then_the_owners_choice_wins(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, {"look": "orbit", "set": ["hbar.music", "hbar.gone", "hbar.film"], "measured": "14 days"})
    d = m._wall_view()
    assert d["look"] == "orbit" and d["set"] == ["hbar.music", "hbar.film"] and d["seed"] is True   # unknown id dropped
    st, r = m._wall_save({"set": ["hbar.film"]})
    assert st == 200 and r["set"] == ["hbar.film"] and r["seed"] is False and r["look"] == "orbit"
    st, r = m._wall_save({"look": "grid"})
    assert st == 200 and r["look"] == "grid" and r["set"] == ["hbar.film"]
    st, r = m._wall_save({"set": []})                                       # every system let go is a choice too
    assert st == 200 and r["set"] == []


def test_wall_over_http_refuses_what_is_not_a_system(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    srv, base = S._serve(m)
    try:
        st, d = S._call(base + "/wall")
        assert st == 200 and d["look"] == "grid"
        st, d = S._call(base + "/wall", {"set": ["hbar.music", "hbar.nowhere"]})
        assert st == 400 and "hbar.nowhere" in d["error"]
        st, d = S._call(base + "/wall", {"look": "spiral"})
        assert st == 400
        st, d = S._call(base + "/wall", {"look": "orbit", "set": ["hbar.music"]})
        assert st == 200 and d["ok"] and d["set"] == ["hbar.music"]
        st, d = S._call(base + "/wall")
        assert d["look"] == "orbit" and d["set"] == ["hbar.music"]           # survives: it is the bridge's, not the tab's
    finally:
        srv.shutdown()


# ---- ui/lib/wall.js under node ----
TILES = r"""
const tile = (id, o) => Object.assign({ id, thread: null, said: null, counts: { running: 0 }, detail: {} }, o || {})
const TILES = [tile('world', { thread: 't-w', counts: { running: 3 } }), tile('hbar.music', { thread: 't-m' }), tile('hbar.film', { counts: { running: 2 } }),
  tile('hbar.ink'), tile('hbar.blog', { said: { live: true, text: 'writing' } }), tile('hbar.science', { thread: 't-s' })]
"""


def test_look_pick_and_the_kept_set():
    d = WL._node(WL.FAKE + TILES + r"""
const out = {
  look: [W.pickLook('grid', { look: 'orbit' }), W.pickLook('', { look: 'orbit' }), W.pickLook(null, null), W.pickLook('spiral', { look: 'x' })],
  bridge: W.keptSet({ set: ['hbar.science', 'world', 'hbar.gone', 'hbar.science', 'hbar.ink'] }, TILES, { set: ['hbar.film'] }),
  emptyChosen: W.keptSet({ set: [] }, TILES, { set: ['hbar.film'] }),
  browser: W.keptSet(null, TILES, { set: ['hbar.film'] }),
  inUse: W.keptSet(null, TILES, null),
  add: W.addTo(['hbar.ink'], 'hbar.film'), addTwice: W.addTo(['hbar.ink'], 'hbar.ink'), addCentre: W.addTo([], 'world'),
  full: W.addTo(Array.from({ length: 16 }, (_, i) => 's' + i), 'hbar.ink').length,
  remove: W.removeFrom(['hbar.ink', 'hbar.film'], 'hbar.ink'),
}
console.log(JSON.stringify(out))
""")
    assert d["look"] == ["grid", "orbit", "grid", "grid"]
    assert d["bridge"] == ["hbar.science", "hbar.ink"]          # the centre and unknown ids never sit on the ring
    assert d["emptyChosen"] == []
    assert d["browser"] == ["hbar.film"]
    assert d["inUse"] == ["hbar.film", "hbar.music", "hbar.science"]   # running first, then the ones with a thread
    assert d["add"] == ["hbar.ink", "hbar.film"] and d["addTwice"] == ["hbar.ink"] and d["addCentre"] == [] and d["full"] == 16
    assert d["remove"] == ["hbar.film"]


def test_rim_dot_for_an_outside_system_that_runs():
    d = WL._node(WL.FAKE + TILES + r"""
console.log(JSON.stringify({ dots: W.rimDots(TILES, ['hbar.music']), none: W.rimDots(TILES, ['hbar.film', 'hbar.blog']) }))
""")
    assert d["dots"] == [{"id": "hbar.film", "running": 2, "live": False}, {"id": "hbar.blog", "running": 0, "live": True}]
    assert d["none"] == []                                      # the world is the centre, never a rim dot


def test_ring_places_are_spaced_and_the_plus_sits_at_the_bottom():
    d = WL._node(WL.FAKE + r"""
const n = 7, pts = Array.from({ length: n + 1 }, (_, k) => W.orbitPlace(k, n))
const rim = Array.from({ length: 3 }, (_, i) => W.rimPlace(i, 3, n))
console.log(JSON.stringify({ pts, rim }))
""")
    pts = d["pts"]
    assert pts[0] == {"x": 50, "y": 85}                          # "+" at the bottom of the ring
    assert len({(p["x"], p["y"]) for p in pts}) == 8
    gaps = [((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** .5 for a in pts for b in pts if a is not b]
    assert min(gaps) > 20                                        # generous distance between bodies (in % of the sky)
    for p in pts:
        assert 10 <= p["x"] <= 90 and 10 <= p["y"] <= 90
    for r in d["rim"]:                                           # rim dots sit outside the ring
        assert ((r["x"] - 50) / 37) ** 2 + ((r["y"] - 50) / 35) ** 2 > 1.2


def test_load_and_save_fall_back_to_the_browser():
    d = WL._node(WL.FAKE + r"""
const mem = {}; const store = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v) } }
const res = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const up = async (url, init) => (init && init.method === 'POST' ? res(200, { ok: true }) : res(200, { look: 'orbit', set: ['hbar.music'] }))
const down = async () => { throw new Error('away') }
;(async () => {
  const a = await W.loadWall(up, store)
  const s1 = await W.saveWall(down, store, { set: ['hbar.music', 'hbar.film'] })
  const b = await W.loadWall(down, store)
  const s2 = await W.saveWall(up, store, { look: 'grid' })
  const c = await W.loadWall(down, store)
  const e = await W.loadWall(down, { getItem: () => null, setItem: () => {} })
  console.log(JSON.stringify({ a, s1, b, s2, c, e }))
})()
""")
    assert d["a"] == {"look": "orbit", "set": ["hbar.music"], "from": "bridge"}
    assert d["s1"]["ok"] and d["s1"]["kept"] == "browser"
    assert d["b"] == {"look": "orbit", "set": ["hbar.music", "hbar.film"], "from": "browser"}
    assert d["s2"] == {"ok": True, "kept": "bridge"}
    assert d["c"]["look"] == "grid" and d["c"]["set"] == ["hbar.music", "hbar.film"]
    assert d["e"] == {"look": None, "set": None, "from": "none"}


def test_the_centre_sends_in_place_into_the_central_thread():
    d = WL._node(WL.FAKE + r"""
;(async () => {
  const b = bridge()
  const r = await W.sendText(b.f, W.CENTRE, 'what is waiting for me', null)
  console.log(JSON.stringify({ r, calls: b.calls }))
})()
""")
    assert d["r"]["ok"]
    assert d["calls"][0] == {"url": "/cc/systems/thread", "body": {"system": "world"}}
    assert d["calls"][1]["url"].endswith("/say") and d["calls"][1]["body"] == {"message": "what is waiting for me", "via": "wall"}


# ---- the page ----
def test_page_wiring_both_looks_and_the_switch():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    o = (ROOT / "ui" / "components" / "WallOrbit.js").read_text()
    assert "import WallOrbit from '../components/WallOrbit'" in w
    assert "pickLook(new URLSearchParams(window.location.search).get('look'), w)" in w        # ?look=grid keeps the grid
    assert "saveWall(fetch, store(), { look: k })" in w and "saveWall(fetch, store(), { set: next })" in w
    assert "look === 'orbit' ?" in w and "look === 'grid' ?" in w and "<LookSwitch" in w
    assert "process.env.NEXT_PUBLIC_BRAIN_SYMBOL" in w                                           # the brain's own mark
    assert "sendText(fetch, sid, text, threadOf(sid))" in w and "sendClip(fetch, sid, blob, threadOf(sid))" in w
    for src in (w, o):
        assert "router" not in src and "location.href" not in src and "<select" not in src         # never navigates; no native controls
    assert "\u210f" not in o and "'hbar'" not in o and "{symbol}" in o                              # the symbol is the brain's, handed in
    assert "rimDots(tiles, kept)" in o and "orbitPlace(i + 1, kept.length)" in o and "onLeave" in o and "HOLD_MS" in o
    assert "sid={CENTRE}" in o and "background:var(--obg)" in o and "--obg:#000" in o
