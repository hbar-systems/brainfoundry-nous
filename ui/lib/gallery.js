// Gallery (2026-10-09): a deck of conversations, the active one in front, its neighbours blurred
// behind it. Pure functions, no DOM: ui/pages/gallery.js draws, tests/test_cc_bridge.py runs these
// under node.
//
// A card is { uid, thread, title? }. uid is the React key and never changes, so a card is never
// remounted when the deck slides; thread is the brain thread id, or 'new' until the first message
// names it.

const RADIUS = 2   // cards mounted on each side of the front one: 2 + 1 + 2 = 5 live at most

// The deck order. The first call takes the order the box gives (pinned first, then most recently
// active). Later calls keep the order the deck already has, so a poll never shuffles cards under
// the reader's hands (nor remounts a frame); threads that are gone drop out, new ones join at the
// end, and a 'new' card that has since been given a thread is not listed twice.
function mergeCards(prev, threads, mkUid) {
  const list = Array.isArray(threads) ? threads.filter(t => t && t.brain) : []
  const ids = new Set(list.map(t => t.brain))
  const out = []
  const seen = new Set()
  for (const c of prev || []) {
    if (c.thread !== 'new' && !ids.has(c.thread)) continue
    if (c.thread !== 'new') { if (seen.has(c.thread)) continue; seen.add(c.thread) }
    out.push(c)
  }
  for (const t of list) {
    if (seen.has(t.brain)) continue
    seen.add(t.brain)
    out.push({ uid: mkUid(), thread: t.brain })
  }
  return out
}

function indexOfThread(cards, thread) {
  const i = cards.findIndex(c => c.thread === thread)
  return i < 0 ? 0 : i
}

function clampIndex(i, n) { return n <= 0 ? 0 : Math.min(n - 1, Math.max(0, i | 0)) }

// move the front by d cards; the deck does not wrap (an end is an end)
function step(front, d, n) { return clampIndex(front + d, n) }

// the indices that stay mounted: the front and RADIUS on each side, in deck order
function windowIndices(n, front, radius = RADIUS) {
  if (n <= 0) return []
  const f = clampIndex(front, n)
  const out = []
  for (let i = Math.max(0, f - radius); i <= Math.min(n - 1, f + radius); i++) out.push(i)
  return out
}

// how a card at offset d from the front is drawn. x is a share of the card's own width.
function slot(d) {
  const a = Math.abs(d)
  const sign = d < 0 ? -1 : 1
  if (a === 0) return { x: 0, scale: 1, blur: 0, bright: 1, opacity: 1, z: 10 }
  if (a === 1) return { x: sign * 0.27, scale: 0.94, blur: 3, bright: 0.55, opacity: 1, z: 9 }
  if (a === 2) return { x: sign * 0.46, scale: 0.88, blur: 6, bright: 0.35, opacity: 1, z: 8 }
  return { x: sign * 0.6, scale: 0.8, blur: 8, bright: 0.2, opacity: 0, z: 1 }
}

// keys that move the deck, from anywhere that is not a text field: -1, +1, 0 (leave) or null
function keyAction(key) {
  if (key === 'ArrowLeft' || key === '[') return -1
  if (key === 'ArrowRight' || key === ']') return 1
  return null
}

// a wheel gesture moves one card per call at most; the caller passes the time of the last move
function wheelAction(e, lastMs, nowMs, gapMs = 260) {
  if (nowMs - lastMs < gapMs) return 0
  const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
  if (Math.abs(d) < 4) return 0
  return d > 0 ? 1 : -1
}

module.exports = { RADIUS, mergeCards, indexOfThread, clampIndex, step, windowIndices, slot, keyAction, wheelAction }
