// Steering and several system threads (BOARD-5, 2026-11-23, hbar 2026-11-22: "We are getting way too
// disorganised we have so many threads open"). Pure functions, no DOM: ui/pages/cc.js and ui/pages/systems.js
// use them, tests/test_cc_steer.py runs them under node.
//
// 1. The steer line. The reasoner may end an answer with one block per system, at most four:
//      <steer>{"system": "hbar.music", "say": "three loops from the september track"}</steer>
//    The page cuts the blocks out and shows each as a line with a Send button. Nothing is sent until the
//    person presses it; the press opens the system's standing thread (POST /cc/systems/thread) and sends
//    the turn through POST /cc/threads/<id>/say, the operator door, with this thread as "from" so the
//    steered turn reports back here (REPORT-1). A bare mention of the tag in prose stays in the text.
// 2. The /systems layout: which system threads are open beside the tiles (2 to 4), kept in localStorage.

const MAX_STEERS = 4
const MAX_SAY = 4000
const ID_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/            // scripts/cc/cc_systems.py ID_RE
const STEER_RE = /<steer>\s*(\{[\s\S]*?\})\s*<\/steer>/g
const OPEN_RE = /<steer>\s*(?:\{[^<]*)?$/    // still streaming in: hidden to the end

function known(t) {
  const s = String(t || '').trim()
  return !!s && s !== 'unknown' && !s.startsWith('new:') && s.length <= 120
}

function cleanSteer(raw) {
  let o
  try { o = JSON.parse(raw) } catch { return null }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return null
  const system = String(o.system || '').trim().toLowerCase()
  const say = String(o.say || '').replace(/\r/g, '').trim()
  if (!ID_RE.test(system) || !say || say.length > MAX_SAY) return null
  return { system, say }
}

// -> { body, steers: [{ system, say }] }   at most four, one per system (the last word for a system wins)
function splitSteer(text) {
  const src = typeof text === 'string' ? text : ''
  const found = []
  let body = src.replace(STEER_RE, (m, json) => { const s = cleanSteer(json); if (s) { found.push(s); return '' } return m })
  body = body.replace(OPEN_RE, '')
  const by = new Map()
  found.forEach(s => { by.delete(s.system); by.set(s.system, s) })
  return { body: body.replace(/\n{3,}/g, '\n\n').trimEnd(), steers: [...by.values()].slice(0, MAX_STEERS) }
}

// What the Send press posts to /cc/threads/<id>/say. A page on a thread that has no id yet steers without
// a report address (the bridge then reports to nobody), never with a placeholder.
function steerBody(steer, cur) {
  const body = { message: String((steer && steer.say) || '').slice(0, 8000) }
  if (known(cur)) body.from = cur
  return body
}

function sayUrl(thread) {
  return '/cc/threads/' + encodeURIComponent(String(thread || '')) + '/say'
}

// ---- /systems: the open system threads ----
const OPEN_KEY = 'cc.systems.open'
const MAX_OPEN = 4

// Read the saved list (a JSON array of ids); an older page saved one id under cc.systems.sel.
function readOpen(raw, legacy) {
  let v = null
  try { v = JSON.parse(raw || 'null') } catch {}
  const list = Array.isArray(v) ? v : (legacy ? [legacy] : [])
  const out = []
  list.forEach(x => { const s = String(x || ''); if (ID_RE.test(s) && !out.includes(s)) out.push(s) })
  return out.slice(-MAX_OPEN)
}

// A press on a tile: open it beside the others, or close it when it is open. A fifth closes the oldest.
function toggleOpen(list, sid, max = MAX_OPEN) {
  const l = (list || []).filter(x => x !== sid)
  if (l.length !== (list || []).length) return l
  return [...l, sid].slice(-max)
}

// The /panes rule (ui/pages/panes.js): up to three side by side, four as two by two.
function gridOf(n) {
  const k = Math.max(0, Math.min(MAX_OPEN, n | 0))
  const cols = k <= 3 ? Math.max(1, k) : 2
  return { cols, rows: Math.max(1, Math.ceil(k / cols)) }
}

module.exports = { splitSteer, steerBody, sayUrl, readOpen, toggleOpen, gridOf, OPEN_KEY, MAX_OPEN, MAX_STEERS }
