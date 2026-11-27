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

// ---- /systems: one pane in focus (PANES-FOCUS-1 "Lens", 2026-11-27, hbar: "click any one of these and it expands to
// most of the screen so I can read it much better ... and then an easy exit back so we see all four") ----
const FOCUS_KEY = 'cc.systems.focus'   // localStorage is per origin, and each brain's console is its own origin

// The saved focus, kept only while that pane is still open.
function readFocus(raw, shown) {
  const s = String(raw || '')
  return ID_RE.test(s) && (shown || []).includes(s) ? s : null
}

// Where each open pane sits. No focus: the grid of gridOf (central first, full height, when it is open). In focus:
// the focused pane takes the wide column at full height, the others stack as title bars in a narrow column beside,
// in the order they were open. -> { cols, rows, place: { sid: {gridColumn, gridRow} }, mini: [sid] }
function framesLayout(shown, focus, central, strip = 'clamp(190px, 18%, 280px)') {
  const all = (shown || []).slice()
  const f = focus && all.includes(focus) ? focus : null
  if (f) {
    const rest = all.filter(x => x !== f)
    const place = { [f]: { gridColumn: 1, gridRow: '1 / -1' } }
    rest.forEach((sid, i) => { place[sid] = { gridColumn: 2, gridRow: i + 1 } })
    return {
      cols: rest.length ? `minmax(0,1fr) ${strip}` : 'minmax(0,1fr)',
      rows: rest.length ? `${rest.map(() => 'auto').join(' ')} minmax(0,1fr)` : 'minmax(0,1fr)',
      place, mini: rest,
    }
  }
  const list = all.filter(x => x !== central)
  const hasC = !!central && all.includes(central)
  const { cols, rows } = gridOf(list.length)
  const place = {}
  if (hasC) place[central] = { gridColumn: 1, gridRow: '1 / -1' }
  list.forEach((sid, i) => { place[sid] = { gridColumn: (hasC ? 2 : 1) + (i % cols), gridRow: 1 + Math.floor(i / cols) } })
  const c = Math.max(1, list.length ? cols : 1)
  return {
    cols: hasC && list.length ? `minmax(0,1fr) repeat(${cols}, minmax(0,1fr))` : `repeat(${c}, minmax(0,1fr))`,
    rows: `repeat(${list.length ? rows : 1}, minmax(0,1fr))`, place, mini: [],
  }
}

// The quiet marks right of a pane's name, from what GET /cc/systems already carries (never a made-up number):
//   run   jobs running in that system now            (tile.counts.running; nothing when zero)
//   open  open rows of ops/systems/<id>/open.tsv     (tile.open_rows.n, when the bridge serves it; tile.open is
//         another thing: an instrument's own page, WALL-3)
//   his   of those, the ones that wait on him         (tile.open_rows.his: court decisions and his tasks; the accent)
//   last  the time of the last turn in its thread     (tile.said.at; "live" while it answers)
// -> [{ k, text, title }], numbers first, few words.
function hhmm(iso, now) {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const n = now ? new Date(now) : new Date()
  const p = (x) => String(x).padStart(2, '0')
  if (d.toDateString() === n.toDateString()) return `${p(d.getHours())}:${p(d.getMinutes())}`
  const days = Math.round((n - d) / 86400000)
  if (days >= 1 && days < 7) return `${days}d`
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

function paneMarks(tile, now) {
  const t = tile || {}
  const sid = t.id || 'this system'
  const out = []
  const run = Number((t.counts || {}).running) || 0
  if (run > 0) out.push({ k: 'run', text: String(run), title: `${run} job${run === 1 ? '' : 's'} running in ${sid} now` })
  const o = t.open_rows && typeof t.open_rows === 'object' ? t.open_rows : null
  if (o && Number(o.n) > 0) {
    out.push({ k: 'open', text: `${o.n} open`, title: `${o.n} open item${o.n === 1 ? '' : 's'} in ${sid} (tasks, next rows, court rows)` })
    if (Number(o.his) > 0) out.push({ k: 'his', text: `${o.his} yours`, title: `${o.his} of them wait on you (court decisions and your tasks)` })
  }
  const s = t.said && typeof t.said === 'object' ? t.said : null
  if (s && s.live) out.push({ k: 'last', text: 'live', title: `${sid} is answering now` })
  else if (s && s.at) {
    const w = hhmm(s.at, now)
    if (w) out.push({ k: 'last', text: w, title: `last turn in the ${sid} thread: ${new Date(s.at).toLocaleString('en-GB')}` })
  }
  return out
}

module.exports = { splitSteer, steerBody, sayUrl, readOpen, toggleOpen, gridOf, readFocus, framesLayout, paneMarks, hhmm,
  OPEN_KEY, FOCUS_KEY, MAX_OPEN, MAX_STEERS }
