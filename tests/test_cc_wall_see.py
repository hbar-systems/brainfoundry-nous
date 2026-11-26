"""The wall, seen and entered (WALL-6, 2026-11-26).

hbar, 00:51 Bratislava, tired: "the wall needs fixing to see. otherwise the wall is now main one i want to begin with
but the thing is it just lets me see the current system but not so much easy", "it doesnt flow. it takes too long, it
opens and loads too slow", and on the centre box: "can i only send this? i cant type a message and it will go through?".

Pins: cc_systems.card_latest (a card's "Latest:" line: https, a console route or a file under the out folder or the
world, nothing else) and today_list (due today or before, earliest first, then the ones with no time, three at most);
the bridge's slim board (?wall=1 drops the /systems lists), each tile's `latest`, waits.today read in the owner's zone,
GET /cc/wall's tz; ui/lib/wall.js under node (nowOf, latestOf, shortcutsOf, clockOf, todayLines, readSnap/writeSnap,
systemsUrl); and the page's wiring (one press enters, the entered box starts empty and focused, shortcuts are chips
that never send by themselves, Esc leaves the card first, the page draws from the last snapshot, the first asks start
before React draws, the thread beside shows a skeleton with its last line, no long hover titles on the orbit).
The browser half is tests/browser/test_wall_see.py.

Run from repo root:
    pytest tests/test_cc_wall_see.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_systems as C  # noqa: E402
import test_cc_wall as WL  # noqa: E402
import test_cc_wall_continue as WC  # noqa: E402

W = pathlib.Path("/w")
OUT = ("/o",)


def test_card_latest_takes_only_safe_targets():
    lt = lambda s: C.card_latest(s, W, OUT)   # noqa: E731
    assert lt("Now: x\n\nLatest: the cut | /o/2026-11-26/cut/v1.mp4\n") == {"label": "the cut", "href": "/cc/files/raw/o/2026-11-26/cut/v1.mp4", "hear": True}
    assert lt("Latest: /cc/page/rooms/k2/") == {"label": "k2", "href": "/cc/page/rooms/k2/", "hear": False}
    assert lt("Latest: sing it | /sing")["href"] == "/sing"
    assert lt("Latest: ops/wall/x.png")["href"] == "/cc/files/raw/w/ops/wall/x.png"       # relative: in the world
    assert lt("Latest: a site | https://hbar.systems/v0.3")["href"] == "https://hbar.systems/v0.3"
    for bad in ("Latest: /etc/passwd", "Latest: http://x.y/z", "Latest: //x.y/z", "Latest: a | /o/../etc/passwd",
                "Latest: javascript:alert(1)", "Latest: two words", "Latest: ftp://x", "Now: nothing latest"):
        assert lt(bad) is None, bad
    assert lt("---\nLatest: /o/front.png\n---\n# card\n") is None                           # front matter is not the card


def test_today_list_in_order_three_at_most():
    tasks = [{"text": "later", "due": "2026-11-27T09:00:00Z"}, {"text": "b", "due": "2026-11-26T17:45:00Z"},
             {"text": "none"}, {"text": "late", "due": "2026-11-25T08:00:00Z"}, {"text": "done", "due": "2026-11-26T01:00:00Z", "done": True},
             {"text": "  ", "due": "2026-11-26T02:00:00Z"}, {"text": "a", "due": "2026-11-26T14:00:00Z"}, "junk"]
    assert C.today_list(tasks, "2026-11-26") == [{"text": "late", "due": "2026-11-25T08:00:00Z"}, {"text": "a", "due": "2026-11-26T14:00:00Z"},
                                                 {"text": "b", "due": "2026-11-26T17:45:00Z"}]
    assert C.today_list([{"text": "none"}], "2026-11-26") == [{"text": "none", "due": None}]
    assert C.today_list(None, "2026-11-26") == []


def test_bridge_slim_board_latest_and_today(monkeypatch, tmp_path):
    m = WC._bridge(monkeypatch, tmp_path, {"look": "orbit", "set": ["hbar.music"], "tz": "Europe/Bratislava"})
    world = pathlib.Path(m.WORLD_DIR)
    (world / "ops" / "wall" / "cards").mkdir(parents=True, exist_ok=True)
    (world / "ops" / "wall" / "cards" / "hbar.music.md").write_text(
        "# music\n\nNow: the set is open.\n\nLatest: the page | /cc/page/rooms/page-video/\n\n## Continue\n- play it\n")
    tasks = [{"text": "study day 2", "due": "2000-01-01T14:00:00Z"}, {"text": "free one"}]
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"tasks": tasks} if path == "/tasks" else {})
    m._SYSTEMS_TASKS[0] = 0.0
    full = m._systems_view()
    m._SYSTEMS_TASKS[0] = 0.0
    slim = m._systems_view(None, slim=True)
    mu = {t["id"]: t for t in slim["tiles"]}["hbar.music"]
    assert mu["latest"] == {"label": "the page", "href": "/cc/page/rooms/page-video/", "hear": False}
    assert mu["prompts"] == ["play it"]
    for k in ("lines", "more", "extra", "moving", "total"):
        assert all(k not in t for t in slim["tiles"]), k
    assert all(set(t["detail"]) <= {"running"} for t in slim["tiles"])
    assert len(json.dumps(slim)) < len(json.dumps(full))
    assert slim["waits"]["today"] == [{"text": "study day 2", "due": "2000-01-01T14:00:00Z"}, {"text": "free one", "due": None}]
    assert slim["waits"]["tasks_today"] == 1
    assert m._wall_view()["tz"] == "Europe/Bratislava"
    WC._seed(m, {"look": "orbit", "set": ["hbar.music"], "tz": "../../etc/passwd"})
    assert m._wall_view()["tz"] is None                                        # only a zone name passes
    WC._seed(m, {"look": "orbit", "set": ["hbar.music"], "tz": "Not/AZone"})
    assert len(m._owner_today()) == 10                                         # an unknown zone falls back to UTC


def test_bridge_systems_door_reads_wall_flag(monkeypatch, tmp_path):
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    assert 'self._send(200, _systems_view(q.get("depth") or None, slim=q.get("wall") == "1"))' in src


def test_lib_see_and_enter_under_node():
    d = WL._node(r"""
const W = require('./wall.js')
const store = { m: {}, getItem(k) { return this.m[k] === undefined ? null : this.m[k] }, setItem(k, v) { this.m[k] = String(v) } }
W.writeSnap(store, { systems: { tiles: [{ id: 'a' }] } }); W.writeSnap(store, { wall: { set: ['a'] } })
const snap = W.readSnap(store)
const bad = { getItem() { throw new Error('no') }, setItem() { throw new Error('no') } }
W.writeSnap(bad, { x: 1 })
const t = { summary: { text: '  the set  is open. ', from: 'card' }, prompts: ['one', 'two', 'three', 'four', 'five'],
  latest: { label: 'the page', href: '/cc/page/rooms/k2/' } }
console.log(JSON.stringify({
  now: W.nowOf(t), nowThread: W.nowOf({ summary: { text: 'x', from: 'thread' } }), nowNone: W.nowOf(null),
  latest: W.latestOf(t), latestOut: W.latestOf({ latest: { label: 'a', href: 'https://hbar.systems/x' } }),
  latestBad: [W.latestOf({ latest: { href: 'javascript:alert(1)' } }), W.latestOf({ latest: { href: 'http://x' } }), W.latestOf({ latest: { href: '//x.y' } }), W.latestOf({})],
  cuts: W.shortcutsOf(t, 4),
  clock: W.clockOf('2026-11-26T14:00:00Z', 'Europe/Bratislava'), clockNaive: W.clockOf('2026-11-26T14:00:00', 'Europe/Bratislava'),
  clockDate: W.clockOf('2026-11-26', 'Europe/Bratislava'), clockBadTz: W.clockOf('2026-11-26T14:00:00Z', 'No/Where') !== '',
  today: W.todayLines({ today: [
    { text: 'Study day 2: slides 6-10: https://console.example/cc/files/raw/s/index.html', due: '2026-11-26T14:00:00Z' },
    { text: 'Press Update (brings Take): https://console.example/update.', due: '2026-11-26T17:45:00Z' },
    { text: 'no time', due: null }, { text: 'fourth', due: null }, { text: '' }] }, 'Europe/Bratislava', Date.parse('2026-11-26T15:00:00Z')),
  todayNone: W.todayLines(null), todayList: W.todayLines({ today: 'x' }),
  snapKeys: Object.keys(snap).sort(), snapNull: W.readSnap(bad), snapEmpty: W.readSnap({ getItem() { return '[' } }),
  urls: [W.systemsUrl(null), W.systemsUrl('hbar.film')],
  extraTz: [W.wallExtra({ tz: 'Europe/Bratislava' }).tz, W.wallExtra({ tz: '../x' }).tz, W.wallExtra({}).tz],
}))
""")
    assert d["now"] == "the set is open." and d["nowThread"] == "" and d["nowNone"] == ""
    assert d["latest"] == {"label": "the page", "href": "/cc/page/rooms/k2/", "hear": False, "route": True}
    assert d["latestOut"]["route"] is False and d["latestBad"] == [None, None, None, None]
    assert d["cuts"] == ["one", "two", "three", "four"]
    assert d["clock"] == "15:00" and d["clockNaive"] == "15:00" and d["clockDate"] == "" and d["clockBadTz"] is True
    assert d["today"] == [
        {"time": "15:00", "text": "Study day 2: slides 6-10", "href": "https://console.example/cc/files/raw/s/index.html", "late": True, "any": False},
        {"time": "18:45", "text": "Press Update (brings Take)", "href": "https://console.example/update", "late": False, "any": False},
        {"time": "", "text": "no time", "href": None, "late": False, "any": True}]
    assert d["todayNone"] == [] and d["todayList"] == []
    assert d["snapKeys"] == ["at", "systems", "wall"] and d["snapNull"] is None and d["snapEmpty"] is None
    assert d["urls"] == ["/cc/systems?wall=1", "/cc/systems?wall=1&depth=hbar.film"]
    assert d["extraTz"] == ["Europe/Bratislava", None, None]


def test_page_wiring():
    w = (ROOT / "ui" / "pages" / "wall.js").read_text()
    o = (ROOT / "ui" / "components" / "WallOrbit.js").read_text()
    en = (ROOT / "ui" / "components" / "WallEnter.js").read_text()
    # one press on a name enters; the symbol enters the brain
    assert "onEnter(t.id)" in o and "onClick={() => onEnter(CENTRE)}" in o and "<WallEnter key={entered}" in o
    # the entered box: empty, focused, its own placeholder; a send button beside the mic
    assert "useState('')" in en and "inp.current.focus()" in en and "'type your own message'" in en
    assert 'className="we-ic go" onClick={send} disabled={!text.trim() || busy}' in en
    # shortcuts are chips below the box and only fill it
    cut = en.split("const cut = (p) => {", 1)[1].split("\n  }", 1)[0]
    assert "setText(v)" in cut and "onSend" not in cut and "or start from a shortcut" in en
    # latest and instruments open beside; back by press, by a press outside, by Esc (the page closes the card first)
    assert "data-latest-for={sid}" in en and "onRoute({ route: l.href, title: l.label })" in en
    assert "onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}" in en and ">back</button>" in en
    esc = w.split("const onKey = (e) => {", 1)[1]
    assert esc.index("enteredRef.current") < esc.index("if (depthRef.current)")
    # at rest: the now-line under each name, today's lines in the centre, an empty box to type into
    assert '<p className="wo-now" data-now-for={t.id}>{now}</p>' in o and "<Today waits={waits} tz={tz} ready={ready} onRoute={onRoute} />" in o
    assert "wide ? 'type to the brain' : 'type here'" in o
    # fast: snapshot first, the first asks before React draws, the slim board, never an empty side panel
    assert "const snap = readSnap(store)" in w and "writeSnap(snapStore(), { systems: d })" in w
    assert "window.location.pathname === '/wall'" in w and "[systemsUrl(null), '/cc/wall', '/cc/surfaces']" in w
    assert "<SideSkel last={last} />" in w and "onLoad={() => setLoaded(true)}" in w
    # seeing: no long hover titles on the orbit's bodies; positions clamped inside the sky
    assert "title={inst ?" not in o and "title={`${t.id}" not in o
    assert "left:clamp(116px,var(--x),calc(100% - 116px))" in o and "left:clamp(64px,var(--x),calc(100% - 64px))" in o
    for name in ("hbar.music", "sing", "studio", "Europe/Bratislava"):         # the template names nothing of his
        assert f"'{name}'" not in o and f"'{name}'" not in en and f"'{name}'" not in w
