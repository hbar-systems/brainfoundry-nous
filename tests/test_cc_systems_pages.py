"""SYSTEMS-PAGES-1 "Folio" (2026-11-27): /systems in pages of four; each pane shows what was already done.

hbar 2026-11-27: "More than four systems is probably difficult to visually follow so I'm thinking we should have pages
so people can have a page with all four systems ... one page 4 systems the next page 2 systems pages!" and "I want to
see the updates already made for the system so that I don't repeat myself".

Pins: ui/lib/steer.js layPages / readPages / movePane / pageMarks under node; the page keeps every pane mounted (one
key per pane, hidden off its page, never moved in the DOM), [ and ] change page from the page and from inside a pane,
the pages are kept per brain; cc.js shows the three newest done lines only while the box is empty.

Run from repo root:  pytest tests/test_cc_systems_pages.py -q
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = (ROOT / "ui" / "pages" / "systems" / "index.js").read_text()
CC = (ROOT / "ui" / "pages" / "cc.js").read_text()


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_pages_of_four_under_node():
    d = _node(r"""
const s = require('./steer.js')
const six = ['world', 'a', 'b', 'c', 'd', 'e']
const out = {}
out.fresh = s.layPages(six, {}, 0)
out.five = s.layPages(['world', 'a', 'b', 'c', 'd'], {}, 0)
out.four = s.layPages(['a', 'b', 'c', 'd'], {}, 0)
out.kept = s.layPages(six, { e: 0, a: 1 }, 0)              // e saved on page 1 (page 0 full): overflow goes on
out.gap = s.layPages(['a', 'b'], { a: 3, b: 7 }, 0)         // empty pages close up
out.cur = s.layPages(['a', 'b', 'c', 'd', 'e', 'f'], { a: 0, b: 0, c: 0, d: 0, e: 1 }, 0)  // f: page 0 full -> last page
out.room = s.layPages(['a', 'b', 'c'], { a: 0, b: 1 }, 1)   // c: on the page he looks at
out.moved = s.layPages(six, s.movePane(out.fresh.pageOf, 'b', out.fresh.pages.length), 0)
out.none = s.layPages([], {}, 0)
out.read = [s.readPages('{"pageOf":{"a":1,"../x":0,"b":-1,"c":2.5},"cur":1}'), s.readPages('nonsense'), s.readPages(null)]
const tiles = { a: { counts: { running: 2 }, open_rows: { his: 1 } }, d: { counts: { running: 1 }, open: '/page' } }
out.marks = s.pageMarks(out.fresh.pages, (x) => tiles[x], { b: { busy: true }, e: { busy: true, waiting: true } }, new Set(['d']), { world: 'central' })
out.max = [s.PAGE_MAX, s.MAX_PANES, s.PAGES_KEY]
out.open16 = s.readOpen(JSON.stringify(Array.from({ length: 20 }, (_, i) => 's' + i)), null, s.MAX_PANES).length
out.open4 = s.readOpen(JSON.stringify(['a', 'b', 'c', 'd', 'e'])).length
console.log(JSON.stringify(out))
""")
    assert d["fresh"]["pages"] == [["world", "a", "b", "c"], ["d", "e"]]            # page 1 of four, page 2 of two
    assert d["five"]["pages"] == [["world", "a", "b", "c"], ["d"]]                  # a fifth starts page 2
    assert d["four"]["pages"] == [["a", "b", "c", "d"]]
    assert d["kept"]["pages"] == [["world", "b", "c", "e"], ["a", "d"]]             # e and a keep their pages; d fills the room
    assert d["gap"]["pages"] == [["a"], ["b"]] and d["gap"]["pageOf"] == {"a": 0, "b": 1}
    assert d["cur"]["pages"] == [["a", "b", "c", "d"], ["e", "f"]]
    assert d["room"]["pages"] == [["a"], ["b", "c"]]
    assert d["moved"]["pages"] == [["world", "a", "c"], ["d", "e"], ["b"]]          # b moved to a new page; the others stay
    assert d["none"]["pages"] == [[]]
    assert d["read"][0] == {"pageOf": {"a": 1}, "cur": 1} and d["read"][1] == {"pageOf": {}, "cur": 0} == d["read"][2]
    m1, m2 = d["marks"]
    assert m1["n"] == 1 and m1["run"] == 3 and m1["waits"] == 1 and m1["fresh"] == 0     # a's 2 jobs + b answering; a's his
    assert m2["run"] == 1 and m2["waits"] == 1 and m2["fresh"] == 1                       # d's job; e waits; d finished
    assert "page 1: central, a, b, c" in m1["title"]
    assert d["max"] == [4, 16, "cc.systems.pages"]
    assert d["open16"] == 16 and d["open4"] == 4                                          # the old default stays four


def test_page_keeps_panes_mounted_and_keys():
    assert "{shown.map(sid => {" in PAGE and "const off = !onPage.includes(sid)" in PAGE    # every open pane renders, off ones hidden
    assert "<Thread key={sid}" in PAGE                                                    # one key per pane: never remounted
    assert ".sy-right.off{position:absolute;left:0;top:0;visibility:hidden" in PAGE        # hidden, not display:none, at its size
    assert "e.data.key === '[' || e.data.key === ']'" in PAGE                             # from inside a pane
    assert "(e.key === '[' || e.key === ']')" in PAGE                                     # and from the page
    assert "localStorage.setItem(PAGES_KEY" in PAGE and "readPages(localStorage.getItem(PAGES_KEY))" in PAGE
    assert "/cc/systems/done?system=" in PAGE and "&n=60" in PAGE and "&n=3" in PAGE
    assert "type: 'cc-pane-done'" in PAGE
    assert "<select" not in PAGE                                                          # no native controls


def test_cc_shows_done_lines_only_while_the_box_is_empty():
    assert "e.data.type === 'cc-pane-done'" in CC
    assert "paneMode && paneDone.length > 0 && !draft &&" in CC
