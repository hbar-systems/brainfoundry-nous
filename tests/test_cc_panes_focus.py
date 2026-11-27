"""PANES-FOCUS-1 "Lens" (2026-11-27): one pane of /systems read large, the others a strip beside; quiet marks
right of each pane's name; a small pane's tools strip folded to its one mark.

hbar 2026-11-27: "should be possibility to click any one of these and it expands to most of the screen so I can read
it much better ... and then an easy exit back so we see all four also we are wasting space next to the titles of the
system. There can be various things that are indicating on system levels how many jobs etc."

Pins: ui/lib/steer.js readFocus / framesLayout / paneMarks under node (the grid is the one of before; in focus every
open pane keeps a place, the focus spans the full height); the page wiring (no remount: the frames keep their keys,
the move is a transform, the focus is kept per brain in localStorage, Esc from inside a pane comes up); cc.js folds
the tools strip only for a /systems pane not in focus and never writes that fold to the console's own choice.

Run from repo root:  pytest tests/test_cc_panes_focus.py -q
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_focus_layout_under_node():
    d = _node(r"""
const S = require('./steer')
const shown = ['world', 'a', 'b', 'c', 'd']
console.log(JSON.stringify({
  read: [S.readFocus('b', shown), S.readFocus('x', shown), S.readFocus('', shown), S.readFocus('../b', ['../b']), S.readFocus(null, shown)],
  grid: S.framesLayout(shown, null, 'world'),
  grid3: S.framesLayout(['a', 'b', 'c'], null, null),
  foc: S.framesLayout(shown, 'c', 'world', '200px'),
  alone: S.framesLayout(['world'], 'world', 'world'),
  gone: S.framesLayout(['a', 'b'], 'zz', null),
  key: S.FOCUS_KEY,
}))
""")
    assert d["read"] == ["b", None, None, None, None]
    g = d["grid"]                                   # the grid of before: central full height, four as two by two
    assert g["cols"] == "minmax(0,1fr) repeat(2, minmax(0,1fr))" and g["rows"] == "repeat(2, minmax(0,1fr))" and g["mini"] == []
    assert g["place"]["world"] == {"gridColumn": 1, "gridRow": "1 / -1"}
    assert g["place"]["a"] == {"gridColumn": 2, "gridRow": 1} and g["place"]["d"] == {"gridColumn": 3, "gridRow": 2}
    assert d["grid3"]["cols"] == "repeat(3, minmax(0,1fr))" and d["grid3"]["place"]["c"] == {"gridColumn": 3, "gridRow": 1}
    f = d["foc"]                                    # focus: wide column, full height; the four others stacked beside
    assert f["cols"] == "minmax(0,1fr) 200px" and f["rows"] == "auto auto auto auto minmax(0,1fr)"
    assert f["place"]["c"] == {"gridColumn": 1, "gridRow": "1 / -1"}
    assert [f["place"][x] for x in ["world", "a", "b", "d"]] == [{"gridColumn": 2, "gridRow": i} for i in range(1, 5)]
    assert f["mini"] == ["world", "a", "b", "d"] and set(f["place"]) == set(["world", "a", "b", "c", "d"])
    assert d["alone"] == {"cols": "minmax(0,1fr)", "rows": "minmax(0,1fr)", "place": {"world": {"gridColumn": 1, "gridRow": "1 / -1"}}, "mini": []}
    assert d["gone"]["mini"] == [] and d["gone"]["cols"] == "repeat(2, minmax(0,1fr))"     # a closed pane is never the focus
    assert d["key"] == "cc.systems.focus"


def test_pane_marks_under_node():
    d = _node(r"""
const S = require('./steer')
const now = '2026-11-27T15:00:00'
const at = new Date(2026, 10, 27, 14, 2).toISOString()
console.log(JSON.stringify({
  full: S.paneMarks({ id: 'hbar.music', counts: { running: 2 }, open_rows: { n: 7, his: 3 }, said: { at, live: false } }, now),
  one: S.paneMarks({ id: 'x', counts: { running: 1 }, open_rows: { n: 1, his: 0 } }, now),
  quiet: S.paneMarks({ id: 'x', counts: { running: 0 }, open_rows: { n: 0, his: 0 }, said: null }, now),
  nofield: S.paneMarks({ id: 'x', counts: {} }, now),
  live: S.paneMarks({ id: 'x', said: { live: true, at: null } }, now),
  old: S.paneMarks({ id: 'x', said: { at: new Date(2026, 10, 25, 9, 0).toISOString() } }, now),
  bad: S.paneMarks({ id: 'x', said: { at: 'nonsense' } }, now),
  none: S.paneMarks(null, now),
  inst: S.paneMarks({ id: 'hbar.ink', open: '/apps/hbar-ink' }, now),
}))
""")
    assert [m["k"] for m in d["full"]] == ["run", "open", "his", "last"]
    assert [m["text"] for m in d["full"]] == ["2", "7 open", "3 yours", "14:02"]
    assert d["full"][0]["title"] == "2 jobs running in hbar.music now"
    assert d["full"][2]["title"].startswith("3 of them wait on you")
    assert all(len(m["text"].split()) <= 2 for m in d["full"])                 # few words, numbers first
    assert [m["text"] for m in d["one"]] == ["1", "1 open"] and d["one"][0]["title"] == "1 job running in x now"
    assert d["quiet"] == [] and d["nofield"] == [] and d["none"] == [] and d["bad"] == []   # nothing when zero or unknown
    assert d["live"] == [{"k": "last", "text": "live", "title": "x is answering now"}]
    assert d["old"][0]["text"] == "2d"
    assert d["inst"] == []          # tile.open is an instrument's page (WALL-3), never a count


def test_systems_page_wiring():
    sy = (ROOT / "ui" / "pages" / "systems" / "index.js").read_text()
    assert "readFocus, framesLayout, paneMarks, layPages" in sy and "OPEN_KEY, FOCUS_KEY, PAGES_KEY, MAX_PANES } from '../../lib/steer'" in sy   # SYSTEMS-PAGES-1 added the pages
    assert "localStorage.setItem(FOCUS_KEY, focus)" in sy and "localStorage.getItem(FOCUS_KEY)" in sy
    # no remount: one Thread per open sid, keyed by sid alone, in the same container in grid and focus
    assert sy.count("<Thread key={sid} sid={sid}") == 1 and "zoom={off ? 'grid' : zoomOf(sid)}" in sy   # off its page: hidden, not focused
    assert "<iframe key={thread + (ask ? ':' + ask.n : '')}" in sy                # the frame's key did not change
    assert "el.animate(" in sy and "duration: 220" in sy and "prefers-reduced-motion: reduce" in sy
    assert "e.data.type !== 'cc-pane-key') return" in sy and "if (e.data.key === 'Escape') zoomTo(null)" in sy   # Esc from inside the pane
    assert "type: 'cc-pane-focus', focus: zoomRef.current === 'focus'" in sy
    assert ".sy-right.mini .sy-frame{position:absolute" in sy and "visibility:hidden" in sy
    assert "back to all the panes (Esc)" in sy and "commit 186eace" in sy         # the look before, by commit
    assert "<Svg k=\"link\" />" in sy                                             # the arrow keeps "open in full"


def test_cc_folds_tools_only_in_the_grid():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "small={!!paneMode && String(paneMode).startsWith('sys-') && !paneBig}" in cc
    assert "if (e.data && e.data.type === 'cc-pane-focus') setPaneBig(!!e.data.focus)" in cc
    assert "const flip = () => (small ? setPeek(o => !o) : setOpen(" in cc         # the peek is never saved
    assert "{small && !open ? null : extra}" in cc

