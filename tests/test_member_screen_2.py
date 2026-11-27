"""MEMBER-SCREEN-2 (hbar 2026-11-27, Anne's sitting). Created 2026-11-27.
1. The spiders are off unless the owner turned them on (bf-spiders = "1").
2. A member's quiet home opens on its start page every time, covering the console; the chat is one press away.
Static checks on the console sources plus the pure helpers run under node. No network.

    pytest tests/test_member_screen_2.py -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def _node(mod: str, script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", f"const m=require('./{mod}');" + script],
                       capture_output=True, text=True, timeout=30, cwd=str(UI / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_spiders_off_unless_turned_on():
    got = _node("spiders.js", "console.log(JSON.stringify([null, undefined, '', '0', 'true', '1'].map(m.spidersFrom)))")
    assert got == [False, False, False, False, False, True]
    src = (UI / "components" / "Spiders.js").read_text()
    assert "!== '0'" not in src                       # a missing value no longer means on
    assert "useState(false)" in src.split("export function useSpidersOn")[1].split("\n")[1]
    cortex = (UI / "pages" / "cortex.js").read_text()
    assert "spidersSet(!spiders)" in cortex           # the chip on /cortex stays the switch


QUIET = {"panels": {"hero": False, "nav": False, "tools": False}, "view": "talk", "start": "/apps/week"}
LOUD = {"panels": {}, "view": "talk", "start": "/apps/week"}


def test_start_page_opens_every_time_on_a_member_home():
    cases = [
        (QUIET, ""), (QUIET, "?start=1"), (QUIET, "?threads=1"), (QUIET, "?thread=abc"), (QUIET, "?pane=x"),
        (LOUD, ""), ({**QUIET, "start": None}, ""), ({**QUIET, "view": "gallery"}, ""), ({**QUIET, "view": "doors"}, ""),
    ]
    got = _node("quietHome.js", f"console.log(JSON.stringify({json.dumps(cases)}.map(([l,s]) => m.startOpens(l,s))))")
    assert got == ["cover", "cover", None, None, None, "beside", None, None, "cover"]


def test_console_opens_the_start_page_before_the_applied_layout_check():
    cc = (UI / "pages" / "cc.js").read_text()
    i = cc.index("const how = startOpens(d.layout, firstSearch.current)")
    j = cc.index("if (seen === st) return")
    assert i < j                                      # Anne's bug: it sat after this early return
    assert "cover: how === 'cover'" in cc
    assert "useRef(typeof window !== 'undefined' ? window.location.search : '')" in cc   # ?threads=1 is gone by then
    assert "innerWidth >= 960)) {" not in cc         # no width rule: a phone gets the page too
    # the cover: Pane starts wide, and words handed to the chat uncover it so the answer is seen
    assert "useState(!!pane.cover)" in cc
    assert "setPane(p => (p && p.cover ? (window.innerWidth < 960 ? null : { ...p, cover: false }) : p))" in cc
