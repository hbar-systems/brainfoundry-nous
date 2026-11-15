// Cortex (AGENTS-VIS-1, hbar 2026-11-15): the agents at work drawn as a brain. Pure helpers, no React:
// the point cloud and its regions, which region a running thing lights, the events read from two
// successive readings of the board, the hourly throughput and the header counters. Everything here
// comes from what the bridge already serves (GET /cc/board, /cc/agents, /cc/systems, /cc/health and the
// owner's board.json through /cc/files/raw); nothing is invented, and an idle brain stays dark.

// Axes: x left to right, y up, z front (+) to back (-). Units roughly the half-length of the brain.
// Each region: where its label and tracts anchor, and what lights it in "by role".
export const REGIONS = [
  { id: 'centre', name: 'thalamus', role: 'conversation', what: 'turns answering you', at: [0, -0.02, 0.02] },
  { id: 'frontal', name: 'frontal', role: 'waits for you', what: 'cards and turns that wait for your yes', at: [0.12, 0.2, 0.62] },
  { id: 'motor', name: 'motor cortex', role: 'jobs', what: 'background jobs running', at: [0.3, 0.42, 0.14] },
  { id: 'parietal', name: 'parietal', role: 'standing agents', what: 'standing agents on a run', at: [-0.26, 0.42, -0.28] },
  { id: 'temporal', name: 'temporal', role: 'subagents', what: 'subagents a turn fanned out to', at: [0.46, -0.2, 0.12] },
  { id: 'occipital', name: 'occipital', role: 'tool calls', what: 'steps the live turns took', at: [-0.06, 0.06, -0.7] },
  { id: 'hippocampus', name: 'hippocampus', role: 'just filed', what: 'work that finished in the last 30 min', at: [-0.24, -0.18, -0.08] },
  { id: 'cerebellum', name: 'cerebellum', role: 'failed', what: 'runs that failed and are not dismissed', at: [0, -0.3, -0.48] },
]
export const REGION_IDX = Object.fromEntries(REGIONS.map((r, i) => [r.id, i]))

// a small seeded generator, so the brain has the same folds on every load (and in the server render)
function rng(seed) {
  let s = seed >>> 0
  return () => { s = (s + 0x6d2b79f5) >>> 0; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
}

// which region a point belongs to, from its position (a cartoon of the anatomy, enough to read)
function regionOf(x, y, z, shell) {
  if (!shell) {
    if (Math.hypot(x, y + 0.02, z - 0.02) < 0.16) return REGION_IDX.centre
    if (Math.abs(Math.abs(x) - 0.24) < 0.1 && Math.abs(y + 0.18) < 0.09 && Math.abs(z + 0.06) < 0.22) return REGION_IDX.hippocampus
  }
  if (y < -0.17 && z < -0.3) return REGION_IDX.cerebellum
  if (z < -0.42) return REGION_IDX.occipital
  if (Math.abs(x) > 0.3 && y < -0.02 && z > -0.42) return REGION_IDX.temporal
  if (z > 0.32) return REGION_IDX.frontal
  if (z > 0.02 && y > 0.04) return REGION_IDX.motor
  if (y > 0.04) return REGION_IDX.parietal
  return z > 0 ? REGION_IDX.frontal : REGION_IDX.parietal
}

// The point cloud: two folded hemispheres (surface with gyri), a sparse interior, the cerebellum and the
// stem. Returned as flat typed arrays (x, y, z, region, weight) so a frame is one loop.
const BRAINS = {}
export function makeBrain(n = 9000, seed = 7) {
  const key = `${n}:${seed}`
  if (BRAINS[key]) return BRAINS[key]
  const r = rng(seed)
  const X = new Float32Array(n), Y = new Float32Array(n), Z = new Float32Array(n), R = new Uint8Array(n), W = new Float32Array(n)
  let i = 0
  const put = (x, y, z, shell) => {
    if (i >= n) return
    X[i] = x; Y[i] = y; Z[i] = z; R[i] = regionOf(x, y, z, shell); W[i] = 0.55 + 0.45 * r(); i++
  }
  const cortex = Math.floor(n * 0.72), inner = Math.floor(n * 0.12), cereb = Math.floor(n * 0.11)
  for (let k = 0; k < cortex; k++) {
    const side = k % 2 ? 1 : -1
    // a direction on the unit sphere, kept to this hemisphere's outer side
    const u = r() * 2 - 1, th = r() * Math.PI * 2
    const s = Math.sqrt(1 - u * u)
    let dx = s * Math.cos(th), dy = u, dz = s * Math.sin(th)
    dx = Math.abs(dx) * side
    // folds: a few crossing waves on the surface, deeper sulci where they meet
    const fold = Math.sin(dz * 13 + dy * 7) * Math.sin(dy * 11 - dx * 5) + 0.5 * Math.sin(dz * 23 + dx * 9)
    const rad = 1 + 0.045 * fold - (r() < 0.25 ? r() * 0.08 : 0)
    // flatter bottom, taller front, a midline gap
    let x = dx * 0.4 * rad + side * 0.035, y = dy * (dy < 0 ? 0.3 : 0.43) * rad, z = dz * 0.7 * rad
    if (y < -0.12 && z < -0.25) { y = -0.12 - (y + 0.12) * 0.3 }   // tucked above the cerebellum
    put(x, y + 0.04, z, true)
  }
  for (let k = 0; k < inner; k++) {
    // interior: thalamus near the centre, the two hippocampi, a few white-matter points
    const pick = r()
    if (pick < 0.35) put((r() - 0.5) * 0.24, -0.02 + (r() - 0.5) * 0.2, 0.02 + (r() - 0.5) * 0.24, false)
    else if (pick < 0.7) { const side = r() < 0.5 ? -1 : 1; const t = r(); put(side * (0.22 + (r() - 0.5) * 0.06), -0.18 + Math.sin(t * 3) * 0.05, -0.26 + t * 0.4, false) }
    else put((r() - 0.5) * 0.6, (r() - 0.3) * 0.5, (r() - 0.5) * 1.1, false)
  }
  for (let k = 0; k < cereb; k++) {
    const u = r() * 2 - 1, th = r() * Math.PI * 2, s = Math.sqrt(1 - u * u)
    const fold = 1 + 0.05 * Math.sin(u * 40)
    put(s * Math.cos(th) * 0.26 * fold, -0.27 + u * 0.1 * fold, -0.46 + s * Math.sin(th) * 0.16 * fold, true)
  }
  while (i < n) {
    const t = r()
    put((r() - 0.5) * 0.1, -0.2 - t * 0.32, -0.2 - t * 0.1 + (r() - 0.5) * 0.06, false)
  }
  BRAINS[key] = { n, X, Y, Z, R, W }
  return BRAINS[key]
}

// The tag a job carries in its title ("AGENTS-VIS-1: ...") or, for a conversation, its first words.
const TAG = /\b([A-Z][A-Z0-9]{1,}(?:-[A-Z0-9]+)+)\b/
export function tagOf(title) {
  const t = String(title || '').trim()
  const m = TAG.exec(t)
  if (m) return { tag: m[1], rest: t.replace(m[0], '').replace(/^[\s:·,-]+/, '').trim() || t }
  return { tag: null, rest: t || 'untitled' }
}

// Which region a board tile lights, by role.
export function regionForTile(t) {
  if (!t) return null
  if (t.state === 'waiting') return 'frontal'
  if (t.state === 'failed') return 'cerebellum'
  if (t.state === 'answering') return t.kind === 'job' ? (t.agent ? 'parietal' : 'motor') : 'centre'
  if (t.state === 'done' && t.ago_s !== null && t.ago_s !== undefined && t.ago_s < 1800) return 'hippocampus'
  return null
}

// Activity per region (0..1 targets) and the count that lit it, from the board alone.
export function roleActivity(board) {
  const tiles = (board && board.tiles) || []
  const n = Object.fromEntries(REGIONS.map(r => [r.id, 0]))
  for (const t of tiles) {
    const reg = regionForTile(t)
    if (reg) n[reg] += 1
    if (t.state === 'answering' || t.state === 'waiting') {
      n.temporal += Number(t.agents) || 0
      n.occipital += Number(t.steps) || 0
    }
  }
  const level = {}
  for (const r of REGIONS) {
    const c = n[r.id]
    // one thing lights a region clearly; more things light it brighter, never past full
    level[r.id] = c <= 0 ? 0 : r.id === 'occipital' ? Math.min(1, 0.25 + Math.log10(1 + c) * 0.45) : Math.min(1, 0.55 + 0.15 * (c - 1))
  }
  return { count: n, level }
}

// By system: the systems board's tiles (GET /cc/systems) placed on the regions, busiest first.
export function systemActivity(systems) {
  const tiles = ((systems && systems.tiles) || []).filter(t => t && t.id)
  const busy = tiles.slice().sort((a, b) => ((b.counts || {}).running || 0) - ((a.counts || {}).running || 0) || (b.moving || 0) - (a.moving || 0))
  const slots = REGIONS.map(r => r.id)
  const out = []
  busy.slice(0, slots.length).forEach((t, k) => {
    const running = (t.counts || {}).running || 0
    out.push({ region: slots[k], system: t.id, running, moving: t.moving || 0,
               level: running > 0 ? Math.min(1, 0.55 + 0.15 * (running - 1)) : t.moving > 0 ? 0.18 : 0 })
  })
  return out
}

// Events read from two readings of the board: a tile that appears, changes state, says a new line or
// takes steps. `seed` on the first reading: the finished tiles become the tail's past, dated by ago_s.
export function boardEvents(prev, next, now = Date.now()) {
  const out = []
  const tiles = (next && next.tiles) || []
  if (!prev) {
    for (const t of tiles) {
      if (t.state === 'answering' || t.state === 'waiting') out.push({ ts: t.started ? Date.parse(t.started) : now, key: t.key, region: regionForTile(t), kind: t.state, text: `${t.state === 'waiting' ? 'waits for your yes' : 'running'}: ${t.title}`, href: t.href, seed: true })
      else if (t.ago_s !== null && t.ago_s !== undefined) out.push({ ts: now - t.ago_s * 1000, key: t.key, region: t.state === 'failed' ? 'cerebellum' : 'hippocampus', kind: t.state, text: `${t.state === 'failed' ? 'failed' : 'finished'}: ${t.title}`, href: t.href, seed: true })
    }
    return out.sort((a, b) => a.ts - b.ts).slice(-40)
  }
  const before = new Map(((prev && prev.tiles) || []).map(t => [t.key, t]))
  for (const t of tiles) {
    const p = before.get(t.key)
    const region = regionForTile(t)
    if (!p) {
      out.push({ ts: now, key: t.key, region, kind: t.state, text: `${t.state === 'answering' ? 'started' : t.state === 'waiting' ? 'waits for your yes' : t.state === 'failed' ? 'failed' : 'finished'}: ${t.title}`, href: t.href })
      continue
    }
    if (p.state !== t.state) out.push({ ts: now, key: t.key, region, kind: t.state, text: `${t.state === 'done' ? 'finished' : t.state === 'waiting' ? 'waits for your yes' : t.state === 'failed' ? 'failed' : 'running again'}: ${t.title}`, href: t.href })
    else if ((t.state === 'answering' || t.state === 'waiting') && t.last && t.last !== p.last) {
      const steps = (Number(t.steps) || 0) - (Number(p.steps) || 0)
      out.push({ ts: now, key: t.key, region: steps > 0 ? 'occipital' : region, kind: 'line', text: `${tagOf(t.title).tag || tagOf(t.title).rest.slice(0, 28)}: ${t.last}`, href: t.href, steps: Math.max(0, steps) })
    }
    if ((Number(t.agents) || 0) > (Number(p.agents) || 0)) out.push({ ts: now, key: t.key, region: 'temporal', kind: 'agent', text: `${(t.agents - (p.agents || 0))} subagent${t.agents - (p.agents || 0) === 1 ? '' : 's'} out from: ${t.title}`, href: t.href })
  }
  return out
}

// Finished work per hour over the last 24 h (jobs and conversations), oldest hour first.
export function hourly(board) {
  const bins = new Array(24).fill(0)
  for (const t of (board && board.tiles) || []) {
    if ((t.state !== 'done' && t.state !== 'failed') || t.ago_s === null || t.ago_s === undefined) continue
    const h = Math.floor(t.ago_s / 3600)
    if (h >= 0 && h < 24) bins[23 - h] += 1
  }
  return bins
}

// The header counters, each from a named source; null where the source did not answer.
export function counters({ board, agents, health, desk }) {
  const tiles = (board && board.tiles) || []
  const live = tiles.filter(t => t.state === 'answering' || t.state === 'waiting')
  const sum = (list, k) => list.reduce((s, t) => s + (Number(t[k]) || 0), 0)
  const c = (board && board.counts) || {}
  return {
    running: board ? (c.answering || 0) : null,
    waiting: board ? (c.waiting || 0) : null,
    done: board ? (c.done || 0) : null,
    failed: board ? (c.failed || 0) : null,
    steps: board ? sum(live, 'steps') : null,
    subagents: board ? sum(live, 'agents') : null,
    tokens: board ? sum(tiles, 'tok') : null,
    standing: agents && Array.isArray(agents.agents) ? agents.agents.filter(a => a.enabled).length : null,
    jobs: health && typeof health.jobs_running === 'number' ? health.jobs_running : (board ? tiles.filter(t => t.kind === 'job' && t.state === 'answering').length : null),
    court: desk && desk.counts && typeof desk.counts.court === 'number' ? desk.counts.court : null,
    next: desk && desk.counts && typeof desk.counts.next === 'number' ? desk.counts.next : null,
  }
}

export const kNum = (n) => { if (n === null || n === undefined) return '·'; n = Number(n) || 0; return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 10000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n) }
