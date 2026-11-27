// The wall (WALL-1, 2026-11-24, hbar: "I see in parallel on a dark screen every single system operating and then I
// can write into the small little box ... all I need is that text box to speak into it I don't even have to see
// the entire text"). Pure parts of ui/pages/wall.js, no React: tests/test_cc_wall.py runs them under node with a
// fake fetch and a synthetic microphone.
//
//   cellLine(tile, sent)  the ONE line a cell shows: what is being said now, else what was just sent, else the
//                         running job's title, else the last thing its standing thread said.
//   sendText(...)         a typed or transcribed line into the system's standing thread, in place: the thread is
//                         made once (POST /cc/systems/thread), the turn goes through the steer door
//                         (POST /cc/threads/<id>/say, via "wall"); a thread that is answering takes it in its queue
//                         (POST /cc/queue), so nothing is lost and nothing navigates.
//   sendClip(...)         a recording: transcribed (POST /cc/transcribe) and sent as text; when the box has no speech
//                         service it is kept as a memo for that system (POST /cc/systems/voice), as /systems does.
//   Recorder              the /systems recorder (MediaRecorder), with the browser parts handed in.

const ID_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/

const post = (f, url, body) => f(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const json = async (r) => { try { return await r.json() } catch { return {} } }
const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim()

function cellLine(t, sent) {
  const said = (t && t.said) || null
  if (said && said.live) return { text: squash(said.text) || 'thinking', kind: said.waiting ? 'waits' : 'live' }
  if (sent && sent.text) return { text: squash(sent.text), kind: sent.state === 'error' ? 'error' : 'sent' }
  const run = t && t.detail && t.detail.running && t.detail.running.lines && t.detail.running.lines[0]
  if (run && run.text) return { text: squash(run.text), kind: 'job' }
  if (said && said.text) return { text: squash(said.text), kind: 'said' }
  return { text: '', kind: 'quiet' }
}

// How many jobs run there now (the /systems count) and whether its light is on.
function cellState(t) {
  const n = (t && t.counts && t.counts.running) || 0
  const live = !!(t && t.said && t.said.live)
  return { running: n, on: n > 0 || live }
}

// After a send the cell shows "sent" until the thread starts answering (said.live) or a newer answer lands
// (said.at moves), or a minute passes.
function sentOver(sent, t, now) {
  if (!sent) return true
  if (sent.state === 'error') return now - sent.at > 20000
  const said = (t && t.said) || {}
  if (said.live) return true
  if (said.at && sent.before !== undefined && said.at !== sent.before) return true
  return now - sent.at > 60000
}

async function threadOf(f, sid, known) {
  if (known) return { thread: known }
  const r = await post(f, '/cc/systems/thread', { system: sid })
  const d = await json(r)
  if (!r.ok || !d.thread) return { error: d.error || `the bridge answered ${r.status}` }
  return { thread: d.thread, created: !!d.created }
}

async function sendText(f, sid, text, known) {
  const message = String(text || '').trim()
  if (!ID_RE.test(String(sid || ''))) return { ok: false, error: 'which system?' }
  if (!message) return { ok: false, error: 'nothing to say' }
  try {
    const th = await threadOf(f, sid, known)
    if (!th.thread) return { ok: false, error: th.error }
    const say = () => post(f, '/cc/threads/' + encodeURIComponent(th.thread) + '/say', { message, via: 'wall' })
    let r = await say()
    let d = await json(r)
    if (r.status === 409 && d.busy) {
      const q = await post(f, '/cc/queue', { thread: th.thread, message })
      const qd = await json(q)
      if (q.ok || q.status === 202) return { ok: true, thread: th.thread, created: th.created, queued: true }
      if (q.status !== 409) return { ok: false, thread: th.thread, error: qd.error || d.error || 'it is answering; send it again when it is free' }
      r = await say()          // it finished between the two calls: say it now
      d = await json(r)
    }
    if (!r.ok) return { ok: false, thread: th.thread, error: d.error || `the bridge answered ${r.status}` }
    return { ok: true, thread: th.thread, created: th.created, duplicate: !!d.duplicate }
  } catch {
    return { ok: false, error: 'the bridge did not answer' }
  }
}

function clipName(blob) {
  const t = (blob && blob.type) || ''
  return 'clip.' + (/mp4/.test(t) ? 'm4a' : /ogg/.test(t) ? 'ogg' : 'webm')
}

async function sendClip(f, sid, blob, known, FD) {
  const Form = FD || FormData
  const form = () => { const fd = new Form(); fd.append('file', blob, clipName(blob)); return fd }
  try {
    const r = await f('/cc/transcribe', { method: 'POST', body: form() })
    const d = await json(r)
    if (r.ok && d.ok && String(d.text || '').trim()) {
      const s = await sendText(f, sid, d.text, known)
      return { ...s, heard: String(d.text).trim() }
    }
    if (r.ok && d.ok) return { ok: false, error: 'nothing was heard' }
    if (r.status !== 409) return { ok: false, error: d.error || `the speech service answered ${r.status}` }
    // no speech service on this box: keep it as a memo for the system (the /systems door)
    const v = await f(`/cc/systems/voice?system=${encodeURIComponent(sid)}`, { method: 'POST', body: form() })
    const vd = await json(v)
    if (!v.ok || !vd.ok) return { ok: false, error: vd.error || `the bridge answered ${v.status}` }
    return { ok: true, memo: vd.path || true }
  } catch {
    return { ok: false, error: 'the bridge did not answer' }
  }
}

const MIMES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
const MAX_SECS = 600

// One recording at a time: start() asks for the microphone, stop() gives the clip (a Blob) or null.
class Recorder {
  constructor(env) {
    this.env = env || {}
    this.r = null
  }

  get busy() { return !!this.r }

  async start(onTick) {
    const md = this.env.mediaDevices
    const MR = this.env.MediaRecorder
    if (!(md && md.getUserMedia && MR)) return { error: 'this browser cannot record' }
    let stream
    try { stream = await md.getUserMedia({ audio: true }) } catch { return { error: 'the microphone is not allowed for this page' } }
    const mime = MIMES.find(x => { try { return MR.isTypeSupported(x) } catch { return false } })
    let rec
    try { rec = mime ? new MR(stream, { mimeType: mime }) : new MR(stream) } catch { stream.getTracks().forEach(x => x.stop()); return { error: 'could not start recording' } }
    const r = { rec, stream, chunks: [], since: Date.now(), timer: null, mime: rec.mimeType || mime || 'audio/webm', done: null }
    r.done = new Promise(res => {
      rec.ondataavailable = (e) => { if (e.data && e.data.size) r.chunks.push(e.data) }
      rec.onstop = () => {
        stream.getTracks().forEach(x => x.stop())
        if (r.timer) clearInterval(r.timer)
        const B = this.env.Blob || Blob
        res(r.chunks.length ? new B(r.chunks, { type: r.mime }) : null)
      }
    })
    r.timer = setInterval(() => {
      const s = Math.round((Date.now() - r.since) / 1000)
      if (onTick) onTick(s)
      if (s >= MAX_SECS) { try { rec.stop() } catch {} }
    }, 500)
    this.r = r
    try { rec.start(250) } catch { this.drop(); return { error: 'could not start recording' } }
    return { ok: true }
  }

  async stop() {
    const r = this.r
    if (!r) return null
    try { if (r.rec.state !== 'inactive') r.rec.stop() } catch {}
    const blob = await r.done
    this.r = null
    return blob
  }

  drop() {
    const r = this.r
    this.r = null
    if (!r) return
    try { if (r.timer) clearInterval(r.timer) } catch {}
    try { r.rec.onstop = null; if (r.rec.state !== 'inactive') r.rec.stop() } catch {}
    try { r.stream.getTracks().forEach(x => x.stop()) } catch {}
  }
}

// ---- the orbit (WALL-2, 2026-11-24) ----
// hbar: "it should be a full black screen as space ... only say 10 systems visible and spaced out and around, in
// center is hbar symbol ... dont START WITH ALL 44 ... if i need to add a system to the page i just have ability to
// add". The grid above stays the generic look (/wall?look=grid); the orbit is the personal one. Its kept set lives
// on the bridge (GET/POST /cc/wall, beside the layout) with localStorage as the fallback when the bridge is away.
//
//   pickLook(query, setting)    ?look= wins, else the brain's setting, else the grid
//   keptSet(setting, tiles, local)  the systems in the orbit, in order: the bridge's set, else the browser's, else
//                               the ones in use (a standing thread or something running), at most START_MAX
//   addTo / removeFrom          a new set, never the same array
//   rimDots(tiles, set)         systems outside the orbit that run something now: nothing running is hidden
//   orbitPlace(k, n)            where body k of n sits, in % of the sky; slot 0 (the bottom) is the "+"
//   rimPlace(i, m, n)           where outside dot i of m sits, on the outer ring between the bodies
//   loadWall / saveWall         the setting from the bridge, kept in localStorage too

const CENTRE = 'world'          // the central thread: the world's standing thread is the symbol in the middle
const LOOKS = ['grid', 'orbit']
const START_MAX = 10
const SET_MAX = 16
const LOCAL_KEY = 'cc.wall'

function pickLook(query, setting) {
  const q = String(query || '').toLowerCase()
  if (LOOKS.includes(q)) return q
  const s = setting && setting.look
  return LOOKS.includes(s) ? s : 'grid'
}

function keptSet(setting, tiles, local) {
  const have = new Set((tiles || []).map(t => t && t.id).filter(Boolean))
  const clean = (ids) => {
    const out = []
    for (const x of ids || []) if (typeof x === 'string' && x !== CENTRE && have.has(x) && !out.includes(x)) out.push(x)
    return out.slice(0, SET_MAX)
  }
  if (setting && Array.isArray(setting.set)) return clean(setting.set)
  if (local && Array.isArray(local.set)) return clean(local.set)
  // the orbit starts with areas of work only (WALL-3): an instrument or a site joins only when he adds it
  const used = (tiles || []).filter(t => t && t.id !== CENTRE && kindOf(t) === 'work' && (t.thread || cellState(t).running))
  used.sort((a, b) => cellState(b).running - cellState(a).running)
  return clean(used.map(t => t.id)).slice(0, START_MAX)
}

const addTo = (set, id) => (!id || id === CENTRE || (set || []).includes(id) || (set || []).length >= SET_MAX ? [...(set || [])] : [...(set || []), id])
const removeFrom = (set, id) => (set || []).filter(x => x !== id)

function rimDots(tiles, set) {
  const kept = new Set(set || [])
  return (tiles || []).filter(t => t && t.id !== CENTRE && !kept.has(t.id) && cellState(t).on)
    .map(t => ({ id: t.id, running: cellState(t).running, live: !!(t.said && t.said.live) }))
}

const RX = 37, RY = 35, ORX = 47, ORY = 45
const rnd = (v) => Math.round(v * 100) / 100
function orbitPlace(k, n) {
  const slots = (n || 0) + 1
  const a = Math.PI / 2 + (k * 2 * Math.PI) / slots
  return { x: rnd(50 + RX * Math.cos(a)), y: rnd(50 + RY * Math.sin(a)) }
}
function rimPlace(i, m, n) {
  const slots = Math.max((n || 0) + 1, m || 1)
  const a = Math.PI / 2 + ((i + 0.5) * 2 * Math.PI) / slots
  return { x: rnd(50 + ORX * Math.cos(a)), y: rnd(50 + ORY * Math.sin(a)) }
}

function readLocal(storage) {
  try { const v = JSON.parse((storage && storage.getItem(LOCAL_KEY)) || 'null'); return v && typeof v === 'object' ? v : null } catch { return null }
}
function writeLocal(storage, v) {
  try { if (storage) storage.setItem(LOCAL_KEY, JSON.stringify(v)) } catch {}
}

// {look, set, pinned, from: 'bridge' | 'browser' | 'none'} (pinned: WALL-5, the instruments kept out on the orbit)
async function loadWall(f, storage) {
  const local = readLocal(storage)
  try {
    const r = await f('/cc/wall', { cache: 'no-store' })
    if (r.ok) {
      const d = await json(r)
      if (d && (d.look || d.set !== undefined)) {
        const v = { look: d.look || null, set: Array.isArray(d.set) ? d.set : null, pinned: Array.isArray(d.pinned) ? d.pinned : null }
        if (v.set) writeLocal(storage, v)
        return { ...v, from: 'bridge', ...wallExtra(d) }
      }
    }
  } catch {}
  return local ? { look: local.look || null, set: Array.isArray(local.set) ? local.set : null, pinned: Array.isArray(local.pinned) ? local.pinned : null, from: 'browser' }
    : { look: null, set: null, pinned: null, from: 'none' }
}

// Keeps it in the browser at once, then on the bridge; {ok, kept: 'bridge' | 'browser', error?}
async function saveWall(f, storage, patch) {
  const v = { ...(readLocal(storage) || {}), ...patch }
  writeLocal(storage, v)
  try {
    const r = await post(f, '/cc/wall', patch)
    const d = await json(r)
    if (r.ok && d.ok !== false) return { ok: true, kept: 'bridge' }
    return { ok: true, kept: 'browser', error: d.error || `the bridge answered ${r.status}` }
  } catch {
    return { ok: true, kept: 'browser', error: 'the bridge did not answer' }
  }
}

// ---- depth (WALL-3, 2026-11-24) ----
// hbar: "will i be satisfied with the number of information i can get about the system ... how many jobs are going,
// maybe agentic substructure of each job or info, clear summary, this thing too [the thread tree] ... everything is
// hidden, and i can gain access some easy way WITHOUT interfering with production and the main focus". And: "dont
// confuse systems with surfaces". A registry row is work (you talk into it), an instrument (you open it) or a site.
//
//   kindOf(tile)              'work' | 'instrument' | 'site' (a tile without the field is work)
//   openOf(tile)              where an instrument or site opens: {route} beside on the console, else {href} outside
//   depthOf(tile)             the four one-line rows of the quiet layer: summary, jobs, tree, the thread
//   jobLines(job)             one job's substructure, as short lines: brief, steps, files made, who pushes it
//   jobsBySystem(tiles)       the centre's layer: every running job, grouped by system, busiest first
//   addGroups(tiles)          the "+" list: systems first, then instruments, then sites
//   systemsUrl(depth)         the poll's address; with a layer open it asks for that system's tree too

const KINDS = ['work', 'instrument', 'site']
const kindOf = (t) => (t && KINDS.includes(t.kind) ? t.kind : 'work')

function openOf(t) {
  if (!t) return null
  if (typeof t.open === 'string' && /^\/(?!\/)/.test(t.open)) return { route: t.open }
  if (typeof t.domain === 'string' && /^[a-z0-9.-]+$/.test(t.domain) && t.domain.includes('.')) return { href: 'https://' + t.domain }
  return null
}

function minsText(m) {
  if (typeof m !== 'number' || !(m >= 0)) return ''
  if (m < 1) return 'just started'
  if (m < 60) return m + ' min'
  return Math.floor(m / 60) + ' h ' + String(m % 60).padStart(2, '0')
}

function jobLines(j) {
  if (!j) return []
  const out = []
  if (j.brief) out.push({ k: 'brief', text: j.brief })
  for (const s of (j.steps || []).slice(-3)) out.push({ k: 'step', text: squash(s) })
  if ((j.made || []).length) out.push({ k: 'made', text: j.made.slice(0, 4).join(', ') })
  if (j.waiter && j.waiter.title) out.push({ k: 'pushed by', text: j.waiter.title })
  return out
}

function treeSize(raw) {
  let n = 0
  const walk = (l) => { for (const x of Array.isArray(l) ? l : []) { if (x && typeof x === 'object') { n += 1; walk(x.children) } } }
  walk(raw && raw.nodes)
  return n
}

function depthOf(t) {
  const jobs = (t && Array.isArray(t.jobs)) ? t.jobs : []
  const sum = t && t.summary && t.summary.text ? squash(t.summary.text) : ''
  const said = t && t.said && t.said.text ? squash(t.said.text) : ''
  const n = jobs.length
  const first = n ? jobs[0] : null
  const treeN = (t && typeof t.tree_n === 'number') ? t.tree_n : treeSize(t && t.tree)
  return {
    summary: { text: sum || said || (t && t.description ? squash(t.description) : '') || 'nothing said here yet', from: sum ? (t.summary.from || 'thread') : said ? 'thread' : 'registry' },
    jobs: { n, line: n ? (n + ' running' + (first ? ': ' + squash(first.title).replace(/^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\s*/, '') + (first.mins != null ? ', ' + minsText(first.mins) : '') : '')) : 'nothing running', list: jobs },
    tree: { n: treeN, line: treeN ? treeN + ' branches' : 'no tree yet' },
    thread: !!(t && t.thread),
  }
}

function jobsBySystem(tiles) {
  return (tiles || []).filter(t => t && Array.isArray(t.jobs) && t.jobs.length)
    .map(t => ({ id: t.id, jobs: t.jobs }))
    .sort((a, b) => b.jobs.length - a.jobs.length || String(a.id).localeCompare(String(b.id)))
}

function addGroups(rest) {
  const label = { work: 'systems', instrument: 'instruments', site: 'sites' }
  return KINDS.map(k => ({ kind: k, label: label[k], items: (rest || []).filter(t => kindOf(t) === k) })).filter(g => g.items.length)
}

// ---- continue (WALL-4, 2026-11-24) ----
// hbar: "fill it with what we are currently doing-- the systems that is + prompts to continue from what has been in
// this thread, and maybe some faint ones that i HAVE BEEN working on in other threads ... i want a clear way to open
// and start the system up again in this new manner".
//
//   promptsOf(tile)           up to five prompts to continue (the tile's `prompts`, from the card's "## Continue")
//   waitsForMore(p)           a prompt ending in ":" waits for him to finish it; it is never sent as it stands
//   promptPress(armed, p)     {text, send}: the first press puts the line in the box, a second press on the same
//                             line sends it (never one that waits for more)
//   ringOf(tiles, kept, faint)  the outer ring: the faint systems (dim names, no box; a press brings one in) and the
//                             ones outside the orbit that run something; each {id, running, faint}
//   wallExtra(d)              the faint list, the seed notice and the home setting from GET /cc/wall
//   homeOnWall(path, wall)    the bare console address opens on the wall when the setting is on

const PROMPTS_MAX = 5
function promptsOf(t) {
  const out = []
  for (const p of (t && Array.isArray(t.prompts) ? t.prompts : [])) {
    if (typeof p !== 'string') continue
    const v = p.replace(/\s+/g, ' ').replace(/^\s+/, '').slice(0, 300)
    if (v.trim() && !out.includes(v)) out.push(/:\s*$/.test(v) ? v.replace(/:\s*$/, ': ') : v.trim())
    if (out.length >= PROMPTS_MAX) break
  }
  return out
}
const waitsForMore = (p) => /:\s*$/.test(String(p || ''))
function promptPress(armed, p) {
  const v = String(p || '')
  if (!v.trim()) return { text: '', send: false }
  if (armed === v && !waitsForMore(v)) return { text: v.trim(), send: true }
  return { text: v, send: false }
}

function ringOf(tiles, kept, faint) {
  const by = Object.fromEntries((tiles || []).filter(Boolean).map(t => [t.id, t]))
  const inOrbit = new Set(kept || [])
  const out = []
  for (const id of faint || []) {
    if (typeof id !== 'string' || id === CENTRE || inOrbit.has(id) || !by[id] || out.some(x => x.id === id)) continue
    out.push({ id, running: cellState(by[id]).running, live: !!(by[id].said && by[id].said.live), faint: true })
  }
  for (const d of rimDots(tiles, kept)) if (!out.some(x => x.id === d.id)) out.push({ ...d, faint: false })
  return out
}

function wallExtra(d) {
  const fresh = d && d.fresh && Array.isArray(d.fresh.set) && typeof d.fresh.stamp === 'number' ? { set: d.fresh.set, stamp: d.fresh.stamp } : null
  const tz = d && typeof d.tz === 'string' && /^[A-Za-z_]+(?:\/[A-Za-z0-9_+-]+){0,2}$/.test(d.tz) ? d.tz : null
  return { faint: d && Array.isArray(d.faint) ? d.faint.filter(x => typeof x === 'string') : [], fresh, home: !!(d && d.home === true), tz }
}

// the say-word: a message that is only "wall" (or "the wall", "open the wall") opens /wall, the brain is not asked
const WALL_WORDS = ['wall', 'the wall', 'open the wall', 'open wall']
const isWallWord = (text) => WALL_WORDS.includes(String(text == null ? '' : text).toLowerCase().replace(/\s+/g, ' ').trim().replace(/[.!]$/, '').trim())

const homeOnWall = (path, wall) => String(path || '') === '/' && !!(wall && wall.home === true)

// WALL-6: the wall asks for the slim board (wall=1: no /systems lines, ~1/10 of the bytes every three seconds)
const systemsUrl = (depth) => '/cc/systems?wall=1' + (depth ? '&depth=' + encodeURIComponent(depth) : '')

// ---- instruments (WALL-5, 2026-11-24) ----
// hbar: "where is my musical surfaces tho those i wanted actually -- i want to create more". A system carries the
// instruments the register names for it (GET /cc/surfaces, a file's "instruments": [{name, label, open | ask, on, hue,
// mark}]). At rest nothing new; a press on the name (a hover on a laptop) fans them out around the body; a pinned one
// stays out, as a small body beside its system, kept with the set (GET/POST /cc/wall "pinned").
//
//   instrumentsOf(sid, surfaces)   the instruments that fan around a system: the ones of its own file first, then the
//                                  ones other files lend it, register order, each name once
//   allInstruments(surfaces)       name -> instrument, across the register
//   pinnedOut(kept, pinned, surfaces)  the pinned ones that show: [{inst, host}], host = the first of its systems kept
//   togglePin(pinned, name)        a new list, never the same array
//   fanPlace(k, n, at)             slot k of n beside a body at {x, y} (% of the sky): {dx, dy, side}, px from its name
//   pinFirst(items, pinned)        the pinned ones first, each part in register order
//   cleanPinned(v)                 a list of instrument names, at most PIN_MAX

const PIN_MAX = 12
const NAME_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/

function allInstruments(surfaces) {
  const out = {}
  for (const s of Array.isArray(surfaces) ? surfaces : []) {
    for (const i of (s && Array.isArray(s.instruments)) ? s.instruments : []) {
      if (i && NAME_RE.test(String(i.name || '')) && !out[i.name] && (i.open || i.ask)) out[i.name] = { ...i, surface: s.name, home: s.system }
    }
  }
  return out
}

function instrumentsOf(sid, surfaces) {
  if (!sid) return []
  const all = Object.values(allInstruments(surfaces)).filter(i => Array.isArray(i.on) && i.on.includes(sid))
  return [...all.filter(i => i.home === sid), ...all.filter(i => i.home !== sid)]   // its own first, then the lent ones
}

function cleanPinned(v) {
  const out = []
  for (const x of Array.isArray(v) ? v : []) if (typeof x === 'string' && NAME_RE.test(x) && !out.includes(x)) out.push(x)
  return out.slice(0, PIN_MAX)
}

function pinnedOut(kept, pinned, surfaces) {
  const all = allInstruments(surfaces)
  const ks = kept || []
  const out = []
  for (const n of cleanPinned(pinned)) {
    const i = all[n]
    if (!i) continue
    const host = (i.on || []).find(x => ks.includes(x))
    if (host) out.push({ inst: i, host })
  }
  return out
}

const togglePin = (pinned, name) => {
  const p = cleanPinned(pinned)
  if (!NAME_RE.test(String(name || ''))) return p
  return p.includes(name) ? p.filter(x => x !== name) : (p.length >= PIN_MAX ? p : [...p, name])
}

// A short column beside the body, on the side that faces the symbol (a body left of centre puts it to its right), so
// it never runs off the screen or over the body's own box; slot k of n, centred on the name's row. Pinned ones take
// the first slots (pinFirst), so the ones out at rest keep their places when the rest fan out.
const FAN_X = 140   // clear of the body's own line, box and its prompts (WALL-4)
const FAN_STEP = 34
function fanPlace(k, n, at) {
  const x = at && typeof at.x === 'number' ? at.x : 50
  const side = x > 50.5 ? -1 : 1
  const m = Math.max(n || 1, 1)
  return { dx: side * FAN_X, dy: Math.round((k - (m - 1) / 2) * FAN_STEP), side }
}
const pinFirst = (items, pinned) => {
  const p = Array.isArray(pinned) ? pinned : []
  const l = Array.isArray(items) ? items : []
  return [...l.filter(i => p.includes(i.name)), ...l.filter(i => !p.includes(i.name))]
}

// ---- reading a thread from the wall (LINE-TALK-1, 2026-11-25) ----
// hbar: "how can we read thread thru wall? like something pop out?". A press on a line opens the thread's last answer
// as a card over the wall (ui/components/WallRead.js); these are its two reads.
//
//   readable(text)          an answer without the markers the chat draws itself (tree, steer, pane, choices)
//   lastAnswer(f, thread)   {text} of the thread's last answer (GET /api/bf/sessions/<id>/messages), else {error}
//   transcribe(f, blob)     {ok, text} | {ok: false, error}: a recording into words, never sent by itself

const MARK_RE = /<(tree|steer|pane|choices|card)\b[^>]*>[\s\S]*?<\/\1>/g
const readable = (text) => String(text || '').replace(MARK_RE, '').replace(/\n{3,}/g, '\n\n').trim()

async function lastAnswer(f, thread) {
  if (!thread) return { error: 'no thread here yet' }
  try {
    const r = await f('/api/bf/sessions/' + encodeURIComponent(thread) + '/messages', { cache: 'no-store' })
    if (!r.ok) return { error: `the brain answered ${r.status}` }
    const d = await json(r)
    const list = Array.isArray(d && d.messages) ? d.messages : []
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i]
      if (!m || m.role !== 'assistant') continue
      const text = readable(m.content)
      if (text && !/^\[agent report received[^\]]*\]$/.test(text)) return { text, at: m.created_at || null }
    }
    return { error: 'nothing said in this thread yet' }
  } catch {
    return { error: 'the brain did not answer' }
  }
}

async function transcribe(f, blob, FD) {
  const Form = FD || FormData
  try {
    const fd = new Form(); fd.append('file', blob, clipName(blob))
    const r = await f('/cc/transcribe', { method: 'POST', body: fd })
    const d = await json(r)
    if (r.ok && d.ok && String(d.text || '').trim()) return { ok: true, text: String(d.text).trim() }
    if (r.ok && d.ok) return { ok: false, error: 'nothing was heard' }
    return { ok: false, error: r.status === 409 ? 'this box has no speech service; type it, or use the mic in the box' : (d.error || `the speech service answered ${r.status}`) }
  } catch {
    return { ok: false, error: 'the bridge did not answer' }
  }
}

// ---- the switch between the wall and the columns (LINE-TALK-1, 2026-11-25) ----
// hbar: "maybe we should try that parallel-systems verticle production surface?". The same systems and threads in
// either view: the wall's kept set opens as the columns of /systems (at most four beside the central chat); the
// choice is kept in this browser (cc.view) and told to the bridge (POST /cc/view) so the observer counts it.
//
//   VIEWS, VIEW_KEY          'wall' | 'columns'; the localStorage key
//   readView(storage)        the kept choice, else null
//   columnsUrl(ids, side)    /systems?open=... with the open thread first, then the kept set (four at most)
//   switchView(f, storage, to, from)  keeps the choice and tells the bridge; never throws

const VIEWS = ['wall', 'columns']
const VIEW_KEY = 'cc.view'
const COLUMNS_MAX = 4
function readView(storage) {
  try { const v = storage && storage.getItem(VIEW_KEY); return VIEWS.includes(v) ? v : null } catch { return null }
}
function columnsUrl(ids, side) {
  const out = []
  for (const x of [side, ...(ids || [])]) if (typeof x === 'string' && ID_RE.test(x) && x !== CENTRE && !out.includes(x)) out.push(x)
  const list = out.slice(0, COLUMNS_MAX)
  return '/systems' + (list.length ? '?open=' + list.map(encodeURIComponent).join(',') : '')
}
async function switchView(f, storage, to, from) {
  if (!VIEWS.includes(to)) return { ok: false }
  try { if (storage) storage.setItem(VIEW_KEY, to) } catch {}
  try { await post(f, '/cc/view', { view: to, from: VIEWS.includes(from) ? from : null }) } catch {}
  return { ok: true }
}

// ---- seeing and entering (WALL-6, 2026-11-26) ----
// hbar, tired, 00:51 Bratislava: "the wall needs fixing to see. otherwise the wall is now main one i want to begin
// with but the thing is it just lets me see the current system but not so much easy", and "it doesnt flow. it takes
// too long, it opens and loads too slow", and on the centre box: "can i only send this? i cant type a message and it
// will go through?". So: every body shows what it is doing now at rest (its card's "Now:"), one press enters a
// system (its now-line, its box focused and empty, its shortcuts as separate chips, its latest thing to look at or
// hear), the centre answers "what waits for me today" in place, and the page shows at once from what it saw last.
//
//   nowOf(tile)                 the one line of what a system is doing now: its card's Now: line, else ''
//   latestOf(tile)              {label, href, hear, route}: its latest thing to look at or hear (the card's
//                               "Latest:" line, checked by the bridge); route = it opens beside on the console
//   shortcutsOf(tile, n)        the first n prompts, shown as chips under the empty box (never in the box)
//   clockOf(iso, tz)            "14:05" in the owner's zone (the seed's tz, else the browser's), '' when unreadable
//   todayLines(waits, tz, now)  the centre's three lines: [{time, text, href, late, any}], from waits.today (the bridge
//                               reads the brain's tasks: due today or before, in order, then open ones with no time)
//   SNAP_KEY, readSnap, writeSnap  the last board, setting and register this browser saw, so the page draws at once
//                               and fills in as the bridge answers (never an empty panel)

function nowOf(t) {
  const s = t && t.summary && t.summary.from === 'card' ? squash(t.summary.text) : ''
  return s
}

function latestOf(t) {
  const l = t && t.latest
  if (!l || typeof l.href !== 'string') return null
  const href = l.href.trim()
  const route = /^\/(?!\/)/.test(href)
  if (!route && !/^https:\/\/[^\s]+$/.test(href)) return null
  const label = squash(l.label) || href.split('/').filter(Boolean).pop() || 'open'
  return { label: label.slice(0, 80), href, hear: !!l.hear, route }
}

function shortcutsOf(t, n) {
  return promptsOf(t).slice(0, n || 4)
}

function clockOf(iso, tz) {
  if (typeof iso !== 'string' || !iso) return ''
  if (!/[T ]\d{2}:\d{2}/.test(iso)) return ''                     // a date without a time has no clock
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso.replace(' ', 'T') + 'Z')   // the store keeps UTC
  if (isNaN(d.getTime())) return ''
  try {
    return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, ...(tz ? { timeZone: tz } : {}) }).format(d)
  } catch {
    return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
  }
}

function todayLines(waits, tz, now) {
  const list = waits && Array.isArray(waits.today) ? waits.today : []
  const at = typeof now === 'number' ? now : Date.now()
  const out = []
  for (const x of list) {
    if (!x || typeof x.text !== 'string' || !x.text.trim()) continue
    const due = typeof x.due === 'string' ? x.due : ''
    const when = due ? new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(due) ? due : due.replace(' ', 'T') + 'Z').getTime() : NaN
    // a task that carries its link ("Press Update: https://...") reads as its words; the link is the press
    const raw = squash(x.text)
    const m = raw.match(/https:\/\/[^\s]+/)
    const href = m ? m[0].replace(/[).,;]+$/, '') : null
    const text = (m ? raw.replace(m[0], ' ') : raw).replace(/\s+/g, ' ').replace(/[\s:,-]+$/, '').trim() || raw
    out.push({ time: clockOf(due, tz), text: text.slice(0, 160), href, late: !isNaN(when) && when < at, any: !due })
    if (out.length >= 3) break
  }
  return out
}

const SNAP_KEY = 'cc.wall.snap'
function readSnap(storage) {
  try { const v = JSON.parse((storage && storage.getItem(SNAP_KEY)) || 'null'); return v && typeof v === 'object' ? v : null } catch { return null }
}
function writeSnap(storage, patch) {
  try { if (storage) storage.setItem(SNAP_KEY, JSON.stringify({ ...(readSnap(storage) || {}), ...patch, at: Date.now() })) } catch {}
}

module.exports = {
  nowOf, latestOf, shortcutsOf, clockOf, todayLines, SNAP_KEY, readSnap, writeSnap,
  readable, lastAnswer, transcribe, VIEWS, VIEW_KEY, COLUMNS_MAX, readView, columnsUrl, switchView,
  PIN_MAX, allInstruments, instrumentsOf, cleanPinned, pinnedOut, togglePin, fanPlace, pinFirst,
  PROMPTS_MAX, WALL_WORDS, isWallWord, promptsOf, waitsForMore, promptPress, ringOf, wallExtra, homeOnWall,
  KINDS, kindOf, openOf, minsText, jobLines, depthOf, jobsBySystem, addGroups, systemsUrl, treeSize,
  cellLine, cellState, sentOver, sendText, sendClip, Recorder, clipName,
  CENTRE, LOOKS, START_MAX, SET_MAX, LOCAL_KEY, pickLook, keptSet, addTo, removeFrom, rimDots, orbitPlace, rimPlace, loadWall, saveWall,
}
