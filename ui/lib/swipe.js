// SWIPE-PAGES-1 "Spaces" (2026-11-28, hbar: "Would be very nice to have a two finger slide if hovering over the [panes]
// so it slides to the second or the third page how similarly three fingers does a window on a MacBook except now we're
// doing inside our console"). Pure functions, no DOM: ui/pages/cc.js (a pane forwards a sideways wheel) and
// ui/pages/systems/index.js (the page row follows the fingers, then settles) use them; tests/test_cc_swipe_pages.py
// runs them under node.
//
// 1. Forwarding (inside a pane). A wheel event goes up to /systems as {type: 'cc-pane-swipe', dx} only when it is
//    clearly sideways (|dx| > 1.5 x |dy|) and nothing under the pointer scrolls sideways itself (a wide code block, a
//    table, a chip row keep their own sideways scroll). Vertical scrolling is never touched.
// 2. The gesture (on /systems). Wheel deltas add up; the row of pages follows them (translateX), with rubber-band
//    resistance where there is no page. No wheel event for IDLE_MS = the fingers lifted: past a third of the width,
//    or a fast flick, it settles on the next page, else it springs back. One page per gesture; after a turn the
//    momentum that follows is ignored until it stops (a gap of IDLE_MS), never sooner than LOCK_MS.
//    Reduced motion: no follow; a sum past STILL_PX turns the page at once.

const SIDE = 1.5          // |dx| must beat |dy| by this much to count as sideways
const IDLE_MS = 120       // no wheel event for this long: the fingers lifted
const LOCK_MS = 650       // the floor of the lock after a turn
const SETTLE_MS = 280     // the settle, ease-out
const FLICK = 0.9         // px per ms over the last VEL_MS: a flick
const FLICK_MIN = 24      // px: a flick must have moved at least this far
const VEL_MS = 60
const STILL_PX = 120      // reduced motion: the old threshold
const PAGE_GAP = 12       // px between two pages while they slide
const EASE = 'cubic-bezier(.22,.61,.36,1)'

// A wheel delta in px (deltaMode 1 = lines, 2 = pages).
function px(delta, mode, page) {
  const d = Number(delta) || 0
  return mode === 1 ? d * 16 : mode === 2 ? d * (Number(page) || 800) : d
}

function sideways(dx, dy) {
  const x = Math.abs(Number(dx) || 0), y = Math.abs(Number(dy) || 0)
  return x > 0 && x > SIDE * y
}

// chain: from the element under the pointer up to the page, each {sw, cw, ox}: scrollWidth, clientWidth, the computed
// overflow-x. True when one of them can scroll sideways itself.
function keepsSideways(chain) {
  return (chain || []).some(n => n && /^(auto|scroll|overlay)$/.test(String(n.ox || '')) && Number(n.sw) > Number(n.cw) + 1)
}

// Does this wheel event go up to /systems?
function forwardSwipe(dx, dy, chain) {
  return sideways(dx, dy) && !keepsSideways(chain)
}

// Rubber band: x px pulled where there is no page gives less and less, never past `w` (iOS's formula, c = 0.55).
function rubber(x, w) {
  const W = Math.max(1, Number(w) || 1)
  const a = Math.abs(Number(x) || 0)
  const r = (1 - 1 / (a * 0.55 / W + 1)) * W
  return x < 0 ? -r : r
}

// Where the row sits for a wheel sum. sum > 0: the fingers went left, toward the next page; the row moves left (x < 0).
// ctx: {w, cur, n}. -> {x, side}: side +1 shows the next page beside, -1 the one before, 0 none (rubber band).
function follow(sum, ctx) {
  const w = Math.max(1, ctx.w)
  const s = Number(sum) || 0
  const side = s > 0 ? 1 : s < 0 ? -1 : 0
  const there = side && ctx.cur + side >= 0 && ctx.cur + side < ctx.n
  if (!there) return { x: -rubber(s, w * 0.5), side: 0 }
  const a = Math.abs(s)
  const span = w + PAGE_GAP
  const x = a <= span ? a : span + rubber(a - span, w * 0.5)
  return { x: -side * x, side }
}

// Where it settles: +1 the next page, -1 the one before, 0 back.
function settleTo(sum, vel, ctx) {
  const s = Number(sum) || 0
  if (!s) return 0
  const d = s > 0 ? 1 : -1
  if (ctx.cur + d < 0 || ctx.cur + d >= ctx.n) return 0
  if (Math.abs(s) > Math.max(1, ctx.w) / 3) return d
  if (Math.abs(s) >= FLICK_MIN && Math.sign(vel) === d && Math.abs(vel) >= FLICK) return d
  return 0
}

function swipeInit() {
  return { phase: 'idle', sum: 0, last: 0, peak: 0, recent: [], lock: 0, lockLast: 0 }
}

// One wheel event {dx, t} (t in ms). ctx: {w, cur, n, still}. -> {st, out}; out is null (nothing to do),
// {kind: 'follow', x, side}, {kind: 'settle', d} (animate to d, then turn) or {kind: 'turn', d} (at once, reduced motion).
function swipeStep(st0, ev, ctx) {
  const st = { ...(st0 || swipeInit()) }
  const t = Number(ev.t) || 0
  const dx = Number(ev.dx) || 0
  if (st.phase === 'settling') return { st, out: null }
  if (st.phase === 'lock') {
    if (t < st.lock || t - st.lockLast < IDLE_MS) { st.lockLast = t; return { st, out: null } }
    Object.assign(st, swipeInit())
  }
  if (st.phase === 'idle' || t - st.last > IDLE_MS) { st.phase = 'drag'; st.sum = 0; st.peak = 0; st.recent = [] }
  st.sum += dx
  st.last = t
  st.recent = st.recent.filter(r => t - r.t <= VEL_MS).concat([{ t, dx }])
  // the speed over the last VEL_MS: what moved after the oldest event there, over the time since it
  if (st.recent.length > 1) {
    const v = st.recent.slice(1).reduce((a, r) => a + r.dx, 0) / Math.max(8, t - st.recent[0].t)
    if (Math.abs(v) > Math.abs(st.peak)) st.peak = v
  }
  if (ctx.still) {
    if (Math.abs(st.sum) > STILL_PX) {
      const d = st.sum > 0 ? 1 : -1
      lockAt(st, t)
      return { st, out: ctx.cur + d >= 0 && ctx.cur + d < ctx.n ? { kind: 'turn', d } : null }
    }
    return { st, out: null }
  }
  const f = follow(st.sum, ctx)
  // all the way over: no need to wait for the fingers (the momentum would only hold it there)
  if (f.side && Math.abs(st.sum) >= Math.max(1, ctx.w) + PAGE_GAP) {
    st.phase = 'settling'
    return { st, out: { kind: 'settle', d: f.side, from: f.x } }
  }
  return { st, out: { kind: 'follow', x: f.x, side: f.side } }
}

// The idle timer fired (no wheel event for IDLE_MS): the fingers lifted.
function swipeIdle(st0, ctx, t) {
  const st = { ...(st0 || swipeInit()) }
  if (st.phase !== 'drag') {
    if (st.phase === 'idle') st.sum = 0
    return { st, out: null }
  }
  if (ctx.still) { Object.assign(st, swipeInit()); return { st, out: null } }
  const d = settleTo(st.sum, st.peak, ctx)
  st.phase = 'settling'
  return { st, out: { kind: 'settle', d, from: follow(st.sum, ctx).x } }
}

// The settle animation ended (or the page turned at once): the lock starts if the page turned.
function swipeSettled(st0, d, t) {
  const st = { ...(st0 || swipeInit()) }
  if (d) { lockAt(st, t); return st }
  return swipeInit()
}

function lockAt(st, t) {
  st.phase = 'lock'; st.lock = t + LOCK_MS; st.lockLast = t; st.sum = 0; st.recent = []; st.peak = 0
}

// Where the panes of a page sit (px inside the frames box) in its grid, the same grid as framesLayout without a focus:
// the central chat a whole column at the left, the others in gridOf's columns and rows, every track equal, `gap` apart.
// -> {sid: {left, top, width, height}}
function pageRects(pg, central, w, h, gap = 6) {
  const all = (pg || []).slice()
  const hasC = !!central && all.includes(central)
  const list = all.filter(x => x !== central)
  const k = list.length
  const cols = k <= 3 ? Math.max(1, k) : 2
  const rows = k ? Math.ceil(k / cols) : 1
  const nc = (hasC && k ? 1 : 0) + (k ? cols : 1)
  const cw = (w - gap * (nc - 1)) / nc
  const rh = (h - gap * (rows - 1)) / rows
  const out = {}
  if (hasC) out[central] = { left: 0, top: 0, width: cw, height: h }
  list.forEach((sid, i) => {
    const c = (hasC ? 1 : 0) + (i % cols), r = Math.floor(i / cols)
    out[sid] = { left: c * (cw + gap), top: r * (rh + gap), width: cw, height: rh }
  })
  return out
}

module.exports = { px, sideways, keepsSideways, forwardSwipe, rubber, follow, settleTo, swipeInit, swipeStep, swipeIdle,
  swipeSettled, pageRects, SIDE, IDLE_MS, LOCK_MS, SETTLE_MS, FLICK, STILL_PX, PAGE_GAP, EASE }
