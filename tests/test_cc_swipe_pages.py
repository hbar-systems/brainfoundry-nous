"""SWIPE-PAGES-1 "Spaces" (2026-11-28): a two-finger sideways slide over /systems moves to the next page, like Mac spaces.

hbar 2026-11-28: "Would be very nice to have a two finger slide if hovering over the [panes] so it slides to the second
or the third page how similarly three fingers does a window on a MacBook except now we're doing inside our console".

Pins ui/lib/swipe.js under node: the forwarding rule (sideways vs vertical vs a child that scrolls sideways itself), the
follow with its rubber band, the settle (a third of the width, a flick, else back), one page per slide and the lock
after a turn, reduced motion, and the page rects beside; and the wiring in cc.js and systems/index.js.

Run from repo root:  pytest tests/test_cc_swipe_pages.py -q
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


def test_forwarding_rule():
    d = _node(r"""
const s = require('./swipe.js')
const plain = [{ sw: 400, cw: 400, ox: 'visible' }, { sw: 1200, cw: 1200, ox: 'hidden' }]
const wide = [{ sw: 400, cw: 400, ox: 'visible' }, { sw: 900, cw: 500, ox: 'auto' }, { sw: 1200, cw: 1200, ox: 'visible' }]
const clipped = [{ sw: 900, cw: 500, ox: 'hidden' }]   // overflow hidden: cut, not scrollable by him
console.log(JSON.stringify({
  side: s.forwardSwipe(40, 5, plain),
  diag: s.forwardSwipe(40, 30, plain),         // 40 < 1.5 x 30
  vert: s.forwardSwipe(0, 60, plain),
  zero: s.forwardSwipe(0, 0, plain),
  wide: s.forwardSwipe(40, 0, wide),
  clipped: s.forwardSwipe(40, 0, clipped),
  left: s.forwardSwipe(-40, 2, plain),
  lines: s.px(3, 1), pages: s.px(1, 2, 700), pix: s.px(7, 0),
}))
""")
    assert d["side"] and d["left"] and d["clipped"]
    assert not d["diag"] and not d["vert"] and not d["zero"] and not d["wide"]
    assert d["lines"] == 48 and d["pages"] == 700 and d["pix"] == 7


def test_follow_settle_and_lock():
    d = _node(r"""
const s = require('./swipe.js')
const ctx = { w: 900, cur: 0, n: 2, still: false }
const run = (deltas, c, step = 8, t0 = 1000) => {
  let st = s.swipeInit(), outs = [], t = t0
  for (const dx of deltas) { const r = s.swipeStep(st, { dx, t }, c); st = r.st; outs.push(r.out); t += step }
  return { st, outs, t }
}
const out = {}
// a slow drag of 400 px (past a third of 900) then lift: settles on page 2
let a = run(Array(40).fill(10), ctx, 16)
out.followLast = a.outs[a.outs.length - 1]
let q = s.swipeIdle(a.st, ctx, a.t + 130)
out.slowFar = q.out
// a slow drag of 200 px: springs back
a = run(Array(20).fill(10), ctx, 16)
out.slowShort = s.swipeIdle(a.st, ctx, a.t + 130).out
// a quick flick of 120 px in 40 ms: turns
a = run([30, 30, 30, 30], ctx, 10)
out.flick = s.swipeIdle(a.st, ctx, a.t + 130).out
// a flick the other way, on page 1: nothing before it, springs back (rubber band)
a = run([-30, -30, -30, -30], ctx, 10)
out.rubberFollow = a.outs[3]
out.rubberSettle = s.swipeIdle(a.st, ctx, a.t + 130).out
out.rubber = [s.rubber(100, 450), s.rubber(10000, 450), s.rubber(-100, 450)]
// all the way over: settles at once, without waiting for the fingers
a = run(Array(100).fill(10), ctx, 8)
out.overAt = a.outs.findIndex(o => o && o.kind === 'settle')
out.overOut = a.outs[out.overAt]
out.afterOver = a.outs.slice(out.overAt + 1).every(o => o === null)          // momentum while it settles: ignored
// after a turn: the momentum that follows is ignored until a gap, never before the 650 ms floor
let st = s.swipeSettled(a.st, 1, 5000)
const c2 = { ...ctx, cur: 1 }
let r1 = s.swipeStep(st, { dx: 20, t: 5100 }, c2)              // within the floor
let r2 = s.swipeStep(r1.st, { dx: 20, t: 5700 }, c2)           // past the floor but momentum (no gap since 5100? 600 ms gap)
out.lock = [r1.out, r2.out && r2.out.kind]
st = s.swipeSettled(a.st, 1, 5000)
let t = 5000, ign = 0, r
for (let i = 0; i < 60; i++) { t += 16; r = s.swipeStep(st, { dx: 5, t }, c2); st = r.st; if (r.out === null) ign++ }
out.momentumIgnored = ign                                       // 60 events, 16 ms apart: all ignored (no gap)
r = s.swipeStep(st, { dx: 5, t: t + 200 }, c2)                  // the fingers lifted and came back
out.newGesture = r.out && r.out.kind
// spring back: no lock
out.back = s.swipeSettled(a.st, 0, 9000).phase
// reduced motion: no follow, an instant turn past 120 px, then the lock
a = run([50, 50, 50], { ...ctx, still: true }, 10)
out.still = a.outs
out.stillPhase = a.st.phase
// last page: no page after it
a = run(Array(60).fill(10), { w: 900, cur: 1, n: 2 }, 16)
out.lastSettle = s.swipeIdle(a.st, { w: 900, cur: 1, n: 2 }, a.t + 130).out
out.settleTo = [s.settleTo(301, 0, ctx), s.settleTo(299, 0, ctx), s.settleTo(60, 1.2, ctx), s.settleTo(20, 3, ctx), s.settleTo(60, -1.2, ctx)]
out.consts = [s.IDLE_MS, s.LOCK_MS, s.SETTLE_MS]
console.log(JSON.stringify(out))
""")
    fl = d["followLast"]
    assert fl["kind"] == "follow" and fl["side"] == 1 and fl["x"] == -400            # the row follows the fingers 1:1
    assert d["slowFar"]["kind"] == "settle" and d["slowFar"]["d"] == 1
    assert d["slowShort"]["d"] == 0
    assert d["flick"]["d"] == 1
    rf = d["rubberFollow"]
    assert rf["side"] == 0 and 0 < rf["x"] < 120                                    # pulled 120, gives less
    assert d["rubberSettle"]["d"] == 0
    assert d["rubber"][0] < 100 and d["rubber"][1] < 450 and d["rubber"][2] == -d["rubber"][0]
    assert d["overOut"]["kind"] == "settle" and d["overOut"]["d"] == 1 and d["afterOver"]
    assert d["lock"][0] is None and d["lock"][1] == "follow"                       # floor holds; a 600 ms gap is a new slide
    assert d["momentumIgnored"] == 60 and d["newGesture"] == "follow"
    assert d["back"] == "idle"
    assert d["still"][0] is None and d["still"][1] is None and d["still"][2] == {"kind": "turn", "d": 1}
    assert d["stillPhase"] == "lock"
    assert d["lastSettle"]["d"] == 0
    assert d["settleTo"] == [1, 0, 1, 0, 0]
    assert d["consts"] == [120, 650, 280]


def test_page_rects_match_the_grid():
    d = _node(r"""
const s = require('./swipe.js')
console.log(JSON.stringify({
  two: s.pageRects(['a', 'b'], null, 1006, 800, 6),
  four: s.pageRects(['world', 'a', 'b', 'c'], 'world', 1018, 800, 6),
  sq: s.pageRects(['a', 'b', 'c', 'd'], null, 1006, 806, 6),
  one: s.pageRects(['world'], 'world', 900, 800, 6),
}))
""")
    assert d["two"]["a"] == {"left": 0, "top": 0, "width": 500, "height": 800}
    assert d["two"]["b"]["left"] == 506
    f = d["four"]
    assert f["world"]["height"] == 800 and f["world"]["width"] == 250 and f["c"]["left"] == 768
    assert d["sq"]["d"] == {"left": 506, "top": 406, "width": 500, "height": 400}
    assert d["one"]["world"]["width"] == 900


def test_wiring():
    # the pane: a sideways wheel that nothing under the pointer keeps goes up; only in a /systems pane
    assert "type: 'cc-pane-swipe', dx" in CC and "forwardSwipe(dx, dy, chain)" in CC
    assert "startsWith('sys-')" in CC and "{ passive: false }" in CC
    # the page: same origin check as cc-pane-key, the same feed as its own bars, transform only, one commit
    assert "e.data.type !== 'cc-pane-swipe'" in PAGE and "e.origin !== window.location.origin" in PAGE
    assert "feedRef.current(dx)" in PAGE and PAGE.count("feedRef.current(dx)") == 2
    assert "translate3d(" in PAGE and "flushSync(" in PAGE
    assert "onWheel={onWheel}" not in PAGE                                         # the React wheel (passive) is gone
    assert ".sy-right.off.peek{visibility:visible}" in PAGE
