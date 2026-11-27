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
function readOpen(raw, legacy, max = MAX_OPEN) {
  let v = null
  try { v = JSON.parse(raw || 'null') } catch {}
  const list = Array.isArray(v) ? v : (legacy ? [legacy] : [])
  const out = []
  list.forEach(x => { const s = String(x || ''); if (ID_RE.test(s) && !out.includes(s)) out.push(s) })
  return out.slice(-max)
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

// ---- /systems in pages of four (SYSTEMS-PAGES-1 "Folio", 2026-11-27, hbar: "More than four systems is probably
// difficult to visually follow so I'm thinking we should have pages ... one page 4 systems the next page 2") ----
const PAGE_MAX = 4          // panes on one page (the central chat counts as one when it is open)
const MAX_PANES = 16        // open panes in all, across the pages
const PAGES_KEY = 'cc.systems.pages'   // {pageOf: {sid: page}, cur}: localStorage, one origin per brain

// Where each open pane sits. `shown` is every open pane in the order it was opened, `pageOf` the saved page of each
// (0-based), `cur` the page he looks at. A saved pane keeps its page while that page has room (a page over four sends
// the extra to the next); a newly opened one goes on the page he looks at when it has room, else the last page when it
// has room, else a new page: a fifth starts page 2, it never refuses and never squeezes. Empty pages close up.
// Within a page the panes keep the order they were opened. -> { pages: [[sid]], pageOf: {sid: i} }
function layPages(shown, pageOf, cur) {
  const all = (shown || []).filter((x, i, a) => x && a.indexOf(x) === i)
  const saved = pageOf && typeof pageOf === 'object' ? pageOf : {}
  const pos = (s) => all.indexOf(s)
  const pages = []
  const room = (i) => (pages[i] || []).length < PAGE_MAX
  const put = (sid, i) => { while (pages.length <= i) pages.push([]); pages[i].push(sid) }
  const known = all.filter(s => Number.isInteger(saved[s]) && saved[s] >= 0 && saved[s] < MAX_PANES)
  known.sort((a, b) => saved[a] - saved[b] || pos(a) - pos(b)).forEach(sid => { let i = saved[sid]; while (!room(i)) i++; put(sid, i) })
  const c = Number.isInteger(cur) && cur >= 0 ? cur : 0
  all.filter(s => !known.includes(s)).forEach(sid => {
    let i = pages[c] && room(c) ? c : Math.max(0, pages.length - 1)
    while (!room(i)) i++
    put(sid, i)
  })
  const out = pages.filter(p => p && p.length).map(p => p.slice().sort((a, b) => pos(a) - pos(b)))
  if (!out.length) out.push([])
  const of = {}
  out.forEach((p, i) => p.forEach(s => { of[s] = i }))
  return { pages: out, pageOf: of }
}

// Read the saved {pageOf, cur}; anything odd reads as nothing saved.
function readPages(raw) {
  let v = null
  try { v = JSON.parse(raw || 'null') } catch {}
  const pageOf = {}
  if (v && v.pageOf && typeof v.pageOf === 'object') {
    Object.entries(v.pageOf).forEach(([k, n]) => { if (ID_RE.test(k) && Number.isInteger(n) && n >= 0 && n < MAX_PANES) pageOf[k] = n })
  }
  const cur = v && Number.isInteger(v.cur) && v.cur >= 0 && v.cur < MAX_PANES ? v.cur : 0
  return { pageOf, cur }
}

// Move one pane to page `to` (0-based; to === pages.length starts a new page). -> the new pageOf (layPages closes up).
function movePane(pageOf, sid, to) {
  const n = Math.max(0, Math.min(MAX_PANES - 1, to | 0))
  return { ...(pageOf || {}), [sid]: n }
}

// The quiet page marks: per page its number, what runs on it (jobs running in its systems, plus threads answering now),
// whether something on it waits on him (a pane that waits for him, or his open rows: the accent dot), and whether a
// pane on it finished an answer or raised a card while he looked at another page (`news`: a set of sids).
//   tileOf(sid) -> the GET /cc/systems tile; states: {sid: {busy, waiting}} from each frame's 'cc-pane-state'.
function pageMarks(pages, tileOf, states, news, names) {
  const st = states || {}
  const nw = news || new Set()
  return (pages || []).map((p, i) => {
    let run = 0, waits = 0, fresh = 0
    p.forEach(sid => {
      const t = (tileOf && tileOf(sid)) || {}
      run += Number((t.counts || {}).running) || 0
      if (st[sid] && st[sid].busy && !st[sid].waiting) run += 1
      if ((st[sid] && st[sid].waiting) || Number((t.open || {}).his) > 0) waits += 1
      if (nw.has(sid)) fresh += 1
    })
    const nm = p.map(s => (names && names[s]) || s).join(', ')
    const bits = [`page ${i + 1}: ${nm || 'empty'}`]
    if (run) bits.push(`${run} running`)
    if (waits) bits.push(`${waits} wait${waits === 1 ? 's' : ''} on you`)
    if (fresh) bits.push(`${fresh} finished or asked while you were away`)
    return { n: i + 1, run, waits, fresh, title: bits.join('; ') }
  })
}

module.exports = { splitSteer, steerBody, sayUrl, readOpen, toggleOpen, gridOf, readFocus, framesLayout, paneMarks, hhmm,
  layPages, readPages, movePane, pageMarks,
  OPEN_KEY, FOCUS_KEY, MAX_OPEN, MAX_STEERS, PAGE_MAX, MAX_PANES, PAGES_KEY }
