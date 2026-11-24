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

// {look, set, from: 'bridge' | 'browser' | 'none'}
async function loadWall(f, storage) {
  const local = readLocal(storage)
  try {
    const r = await f('/cc/wall', { cache: 'no-store' })
    if (r.ok) {
      const d = await json(r)
      if (d && (d.look || d.set !== undefined)) {
        const v = { look: d.look || null, set: Array.isArray(d.set) ? d.set : null }
        if (v.set) writeLocal(storage, v)
        return { ...v, from: 'bridge', ...wallExtra(d) }
      }
    }
  } catch {}
  return local ? { look: local.look || null, set: Array.isArray(local.set) ? local.set : null, from: 'browser' } : { look: null, set: null, from: 'none' }
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
  return { faint: d && Array.isArray(d.faint) ? d.faint.filter(x => typeof x === 'string') : [], fresh, home: !!(d && d.home === true) }
}

// the say-word: a message that is only "wall" (or "the wall", "open the wall") opens /wall, the brain is not asked
const WALL_WORDS = ['wall', 'the wall', 'open the wall', 'open wall']
const isWallWord = (text) => WALL_WORDS.includes(String(text == null ? '' : text).toLowerCase().replace(/\s+/g, ' ').trim().replace(/[.!]$/, '').trim())

const homeOnWall = (path, wall) => String(path || '') === '/' && !!(wall && wall.home === true)

const systemsUrl = (depth) => '/cc/systems' + (depth ? '?depth=' + encodeURIComponent(depth) : '')

module.exports = {
  PROMPTS_MAX, WALL_WORDS, isWallWord, promptsOf, waitsForMore, promptPress, ringOf, wallExtra, homeOnWall,
  KINDS, kindOf, openOf, minsText, jobLines, depthOf, jobsBySystem, addGroups, systemsUrl, treeSize,
  cellLine, cellState, sentOver, sendText, sendClip, Recorder, clipName,
  CENTRE, LOOKS, START_MAX, SET_MAX, LOCAL_KEY, pickLook, keptSet, addTo, removeFrom, rimDots, orbitPlace, rimPlace, loadWall, saveWall,
}
