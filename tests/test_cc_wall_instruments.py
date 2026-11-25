"""The wall's instruments (WALL-5, 2026-11-24): a system carries the instruments the register names for it.

hbar 2026-11-24, on the live orbit: "okay but where is my musical surfaces tho those i wanted actually -- i want to
create more than the hbar.ink". The register file of a surface may list instruments (name, one-word label, an
`open` on the console origin or an `ask` for the host system's box, the systems it fans around, hue and mark). On the
wall a press on a system's name fans them out around it; a pinned one stays out beside its system, saved with the set.

Pins: the register check (cc_surfaces.surface / load: addresses stay on the console, one of open or ask, `on` ids,
hue, unique names across files), ui/lib/wall.js under node (instrumentsOf, allInstruments, pinnedOut, togglePin,
cleanPinned, fanPlace), the pinned list kept on the bridge (cc_layout.validate_wall), and the page's wiring.
The browser half (fan opens and folds, press opens beside, pin survives reload) is tests/browser/test_wall_instruments.py.

Run from repo root:
    pytest tests/test_cc_wall_instruments.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
spec = importlib.util.spec_from_file_location("cc_surfaces", ROOT / "scripts" / "cc" / "cc_surfaces.py")
S = importlib.util.module_from_spec(spec); sys.modules["cc_surfaces"] = S; spec.loader.exec_module(S)
import test_cc_wall as WL  # noqa: E402


def card(**kw):
    d = {"name": "alpha", "system": "sys.a", "say": ["alpha"], "hue": "#B5532F", "mark": "wave",
         "actions": [{"label": "Open", "open": "/a", "kind": "page"}]}
    d.update(kw)
    return d


def test_instruments_come_back_clean_with_defaults():
    s, why = S.surface(card(instruments=[
        {"name": "one", "open": "/one/"},
        {"name": "two", "label": "Two words here and more", "ask": "play two", "on": ["sys.b", "sys.b", "sys.a"],
         "hue": "#ABCDEF", "mark": "ring", "note": "n"}]))
    assert why == ""
    assert s["instruments"] == [
        {"name": "one", "label": "one", "note": "", "open": "/one/", "on": ["sys.a"], "hue": "#b5532f", "mark": "wave"},
        {"name": "two", "label": "Two words here a", "note": "n", "ask": "play two", "on": ["sys.b", "sys.a"], "hue": "#abcdef",
         "mark": "ring"}]


def test_a_file_without_instruments_has_no_key():
    s, _ = S.surface(card())
    assert "instruments" not in s


@pytest.mark.parametrize("bad, why", [
    ("x", "instruments"),
    ([{"name": "x"}], "open or ask"),
    ([{"name": "x", "open": "/a", "ask": "b"}], "open or ask"),
    ([{"name": "x", "open": "https://evil.example/"}], "address off the console"),
    ([{"name": "x", "open": "//evil.example/"}], "address off the console"),
    ([{"name": "X Y", "open": "/a"}], "instrument name"),
    ([{"name": "x", "open": "/a"}, {"name": "x", "open": "/b"}], "instrument name"),
    ([{"name": "x", "open": "/a", "on": []}], "on"),
    ([{"name": "x", "open": "/a", "on": ["Not An Id"]}], "on"),
    ([{"name": "x", "open": "/a", "hue": "red"}], "hue"),
    ([{"name": f"i{n}", "open": "/a"} for n in range(9)], "instruments"),
])
def test_bad_instruments_skip_the_whole_card(bad, why):
    s, w = S.surface(card(instruments=bad))
    assert s is None and why in w


def test_an_instrument_name_belongs_to_the_first_file(tmp_path):
    f = tmp_path / "w" / "registry" / "surfaces"
    f.mkdir(parents=True)
    (f / "a.json").write_text(json.dumps(card(instruments=[{"name": "sing", "open": "/sing"}])))
    (f / "b.json").write_text(json.dumps(card(name="beta", system="sys.b", say=["beta"],
                                              instruments=[{"name": "sing", "open": "/other"}, {"name": "film", "open": "/f"}])))
    d = S.load(tmp_path / "w")
    got = {s["name"]: [i["name"] for i in s["instruments"]] for s in d["surfaces"]}
    assert got == {"alpha": ["sing"], "beta": ["film"]}
    assert {"file": "b.json", "why": "instrument 'sing' is alpha's"} in d["skipped"]


def test_the_worlds_register_carries_the_music_instruments():
    """On a box with the world beside it: music fans take, loops, K2, listen (DEMO-1 2026-11-25: take folded sing and
    studio into one path, record, demo, ask); media fans the film rooms."""
    world = pathlib.Path("/home/hands/world")
    if not (world / "registry" / "surfaces" / "music.json").is_file():
        pytest.skip("no world on this box")
    d = S.load(world)
    assert not [x for x in d["skipped"] if "instrument" in x["why"]]
    on = {}
    for s in d["surfaces"]:
        for i in s.get("instruments", []):
            for sid in i["on"]:
                on.setdefault(sid, []).append(i["name"])
    assert {"take", "loops", "k2", "listen"} <= set(on.get("hbar.music", []))
    assert {"film", "shots", "control"} <= set(on.get("hbar.media", []))


LIB = r"""
const W = require('./wall')
const surfaces = [
  {name: 'film', system: 'sys.film', instruments: [
     {name: 'k2', label: 'K2', open: '/k2/', on: ['sys.music', 'sys.film'], hue: '#888888', mark: 'frames'}]},
  {name: 'music', system: 'sys.music', instruments: [
     {name: 'sing', label: 'sing', open: '/sing', on: ['sys.music'], hue: '#c8643a', mark: 'wave'},
     {name: 'listen', label: 'listen', ask: 'listen on it', on: ['sys.music']},
     {name: 'bad name', label: 'x', open: '/x', on: ['sys.music']},
     {name: 'none', label: 'none', on: ['sys.music']}]},
  {name: 'again', system: 'sys.x', instruments: [{name: 'sing', label: 'other', open: '/other', on: ['sys.x']}]},
  null, {name: 'empty'}]
const fan = [0, 1, 2].map(k => W.fanPlace(k, 3, {x: 20, y: 85}))
const one = W.fanPlace(0, 1, {x: 87, y: 50})
const pf = W.pinFirst([{name: 'a'}, {name: 'b'}, {name: 'c'}], ['c']).map(i => i.name)
const p0 = []
const p1 = W.togglePin(p0, 'sing')
const p2 = W.togglePin(p1, 'sing')
let many = []
for (let i = 0; i < 20; i++) many = W.togglePin(many, 'i' + i)
console.log(JSON.stringify({
  music: W.instrumentsOf('sys.music', surfaces).map(i => i.name),
  film: W.instrumentsOf('sys.film', surfaces).map(i => i.name),
  x: W.instrumentsOf('sys.x', surfaces).map(i => i.name),
  nobody: W.instrumentsOf('', surfaces).length,
  bad: W.instrumentsOf('sys.music', 'nope').length,
  all: Object.keys(W.allInstruments(surfaces)).sort(),
  home: W.allInstruments(surfaces).k2.home,
  out: W.pinnedOut(['sys.film'], ['sing', 'k2', 'gone', 'k2'], surfaces).map(o => [o.inst.name, o.host]),
  outNone: W.pinnedOut([], ['sing'], surfaces).length,
  p1, p2, same: p1 === p0, many: many.length, max: W.PIN_MAX,
  clean: W.cleanPinned(['a', 'a', 'B C', 3, 'b']),
  fan, one, pf,
}))
"""


def test_instrument_lib_under_node():
    d = WL._node(LIB)
    assert d["music"] == ["sing", "listen", "k2"]          # its own first, then the lent one; a bad one never shows
    assert d["film"] == ["k2"] and d["x"] == [] and d["nobody"] == 0 and d["bad"] == 0
    assert d["all"] == ["k2", "listen", "sing"] and d["home"] == "sys.film"
    assert d["out"] == [["k2", "sys.film"]] and d["outNone"] == 0
    assert d["p1"] == ["sing"] and d["p2"] == [] and d["same"] is False
    assert d["many"] == d["max"] == 12
    assert d["clean"] == ["a", "b"]
    # a column on the side facing the symbol, centred on the name's row, evenly spaced; pinned ones take the first slots
    assert [f["dx"] for f in d["fan"]] == [140, 140, 140] and [f["dy"] for f in d["fan"]] == [-34, 0, 34]
    assert d["one"] == {"dx": -140, "dy": 0, "side": -1}
    assert d["pf"] == ["c", "a", "b"]


# ---- the pinned list on the bridge ----
def test_layout_keeps_pinned_beside_the_set(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts" / "cc"))
    import cc_layout
    st = cc_layout.Store(tmp_path)
    assert st.wall()["pinned"] is None
    assert st.set_wall({"pinned": ["sing", "studio", "sing"]})["pinned"] == ["sing", "studio"]
    assert st.set_wall({"look": "orbit"})["pinned"] == ["sing", "studio"]     # a patch keeps what it does not name
    for bad in ({"pinned": "sing"}, {"pinned": ["Not One"]}, {"pinned": [f"i{n}" for n in range(13)]}):
        with pytest.raises(cc_layout.LayoutError):
            st.set_wall(bad)
    assert st.set_wall({"pinned": []})["pinned"] == []


def test_wall_view_pinned_seed_then_his_own(monkeypatch, tmp_path):
    import test_cc_wall_orbit as O
    m = O._bridge(monkeypatch, tmp_path, {"look": "orbit", "set": ["hbar.music"], "pinned": ["sing", "loops"]})
    d = m._wall_view()
    assert d["pinned"] == ["sing", "loops"] and d["pinned_seed"] is True
    st, r = m._wall_save({"pinned": ["studio"]})
    assert st == 200 and r["pinned"] == ["studio"] and r["pinned_seed"] is False and r["set"] == ["hbar.music"]
    st, r = m._wall_save({"pinned": ["Bad Name"]})
    assert st == 400
    m2 = O._bridge(monkeypatch, tmp_path / "b")
    assert m2._wall_view()["pinned"] == [] and m2._wall_view()["pinned_seed"] is False


def test_page_wiring_fan_pin_and_register():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    o = (ROOT / "ui" / "components" / "WallOrbit.js").read_text()
    f = (ROOT / "ui" / "components" / "WallFan.js").read_text()
    assert "fetch('/cc/surfaces'" in w and "saveWall(fetch, store(), { pinned: next })" in w and "surfaces={surfaces} pinned={pinned} onPin={onPin}" in w
    assert "instrumentsOf(sid, surfaces)" in o and "if (has && !fanned) { onFan(t.id, 'press'); return }" in o
    assert "setFan(null) } }" in o                                         # Esc folds the fan
    assert "contains('wo-in')) onFan(null)" in o                            # typing in the box folds it (WALL-4's prompts show)
    assert "onRoute({ route: i.open, title: i.label })" in o and "onTalk(sid, i.ask)" in o   # beside, or into the box
    assert "<Box sid={t.id}" in o                                           # the system keeps its box
    assert "fanPlace(k, n, at)" in f and "data-instrument={inst.name}" in f and "aria-pressed={pinned}" in f
    for name in ("sing", "studio", "loops", "hbar.music", "k2"):            # the template names no instrument
        assert f"'{name}'" not in f and f"'{name}'" not in o


def test_a_newer_seed_with_other_pins_asks_never_overwrites(monkeypatch, tmp_path):
    """WALL-4's seed rule, for pins too: his own pinned list stays until he says 'take it'."""
    import os
    import test_cc_wall_orbit as O
    m = O._bridge(monkeypatch, tmp_path, {"look": "orbit", "set": ["hbar.music"], "pinned": ["sing"]})
    st, r = m._wall_save({"set": ["hbar.music"], "pinned": ["studio"]})
    assert st == 200 and r["pinned"] == ["studio"] and not r.get("fresh")
    seed = pathlib.Path(m.WORLD_DIR) / "ops" / "wall" / "wall.json"
    seed.write_text(json.dumps({"look": "orbit", "set": ["hbar.music"], "pinned": ["sing", "loops"]}))
    later = m.LAYOUT.wall_meta()["at"] + 60
    os.utime(seed, (later, later))
    d = m._wall_view()
    assert d["pinned"] == ["studio"]                                        # never replaced silently
    assert d["fresh"] and d["fresh"]["pinned"] == ["sing", "loops"] and d["fresh"]["set"] == ["hbar.music"]
    st, r = m._wall_save({"seen": d["fresh"]["stamp"]})                     # keep mine
    assert st == 200 and not r["fresh"] and r["pinned"] == ["studio"]
