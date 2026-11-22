"""Cortex page and spider overlay (AGENTS-VIS-1, hbar 2026-11-15). Created 2026-11-15.
Static checks on the console sources plus the pure helpers in ui/lib/cortex.js run under node.
No network, no reasoner.

    pytest tests/test_cortex_page.py -v
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


def test_cortex_is_reachable_next_to_the_board():
    cc = (UI / "pages" / "cc.js").read_text()
    assert "['/cortex', 'Cortex']" in cc                                   # the pane's page selector
    assert "togglePaneRoute('/cortex', 'Cortex')" in cc                    # the toolbar button after board
    assert cc.index("togglePaneRoute('/board', 'Board')") < cc.index("togglePaneRoute('/cortex', 'Cortex')")
    assert '<a href="/cortex" style={link}>cortex</a>' in (UI / "pages" / "board.js").read_text()
    assert '<a href="/cortex" style={link}>cortex</a>' in (UI / "pages" / "agents.js").read_text()


def test_cortex_reads_real_sources_only():
    src = (UI / "pages" / "cortex.js").read_text()
    for route in ("'/cc/board'", "'/cc/agents'", "'/cc/systems'", "'/cc/health'", "'/cc/files/raw'"):
        assert route in src
    assert "visibilitychange" in src                                       # polling stops with the tab
    assert "Math.random" not in src                                        # no invented numbers on the page
    assert "Nothing runs right now." in src                                # an honest idle state


def test_spiders_respect_motion_and_visibility():
    src = (UI / "components" / "Spiders.js").read_text()
    assert "prefers-reduced-motion: reduce" in src
    assert "visibilitychange" in src and "cancelAnimationFrame" in src
    assert "pointerEvents: 'none'" in src                                  # never takes a click
    cc = (UI / "pages" / "cc.js").read_text()
    assert "<Spiders count={busy ? 1 : 0}" in cc                           # in the chat only while a turn runs


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_cortex_helpers(tmp_path):
    lib = (UI / "lib" / "cortex.js").read_text()
    mod = tmp_path / "cortex.mjs"
    mod.write_text(lib)
    script = tmp_path / "run.mjs"
    script.write_text("""
import { makeBrain, tagOf, roleActivity, boardEvents, hourly, counters, REGIONS } from './cortex.mjs'
const b = makeBrain(3000)
const regions = new Set(Array.from(b.R))
const board = { tiles: [
  { key: 'run:1', kind: 'run', state: 'answering', title: 'ORG-1 plan', steps: 4, agents: 2, last: 'a', tok: 100 },
  { key: 'job:1', kind: 'job', state: 'answering', agent: true, title: 'LAW-1: docket' },
  { key: 'job:2', kind: 'job', state: 'done', title: 'x', ago_s: 4000 },
], counts: { answering: 2, waiting: 0, done: 1, failed: 0 } }
const next = { tiles: [{ ...board.tiles[0], steps: 6, last: 'b' }, { ...board.tiles[1], state: 'done', ago_s: 1 }, board.tiles[2]], counts: {} }
const idle = { tiles: [board.tiles[2]], counts: { done: 1 } }
console.log(JSON.stringify({
  n: b.n, regions: regions.size, same: makeBrain(3000) === b,
  tag: tagOf('AGENTS-VIS-1: the agents visual'), notag: tagOf('push the branch'),
  role: roleActivity(board), idle: roleActivity(idle).level,
  events: boardEvents(board, next, 1000).map(e => [e.kind, e.region]),
  hourly: hourly(board), counters: counters({ board, agents: { agents: [{ enabled: true }, { enabled: false }] }, health: null, desk: null }),
  nregions: REGIONS.length,
}))
""")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True, timeout=60).stdout)
    assert out["n"] == 3000 and out["regions"] == out["nregions"] and out["same"]
    assert out["tag"] == {"tag": "AGENTS-VIS-1", "rest": "the agents visual"}
    assert out["notag"] == {"tag": None, "rest": "push the branch"}
    assert out["role"]["count"]["centre"] == 1 and out["role"]["count"]["parietal"] == 1
    assert out["role"]["count"]["temporal"] == 2 and out["role"]["count"]["occipital"] == 4
    assert all(v == 0 for v in out["idle"].values())                      # idle: every region dark
    assert ["line", "occipital"] in out["events"] and ["done", "hippocampus"] in out["events"]
    assert sum(out["hourly"]) == 1 and out["hourly"][22] == 1
    c = out["counters"]
    assert c["running"] == 2 and c["steps"] == 4 and c["subagents"] == 2 and c["standing"] == 1
    assert c["court"] is None and c["next"] is None                        # no desk: shown as a dot, not a zero
