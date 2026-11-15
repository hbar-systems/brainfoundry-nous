import Head from 'next/head'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { LIGHT, LIGHT_CSS } from '../lib/activity'
import { REGIONS, REGION_IDX, makeBrain, tagOf, roleActivity, systemActivity, boardEvents, hourly, counters, kNum } from '../lib/cortex'
import Spiders, { useSpidersOn, spidersSet } from '../components/Spiders'

// Cortex (AGENTS-VIS-1, hbar 2026-11-15: "make the agents visual part of the system"). The agents at work
// drawn as a brain: a point cloud that turns slowly, each region lit by what runs in it (by role: a turn
// answering you in the thalamus, jobs in the motor cortex, standing agents parietal, subagents temporal,
// tool calls occipital, what waits for your yes frontal, what just finished in the hippocampus, failures
// in the cerebellum; or by system, the systems board placed on the same regions). Tracts light from the
// centre to every lit region, a ring pulses where an event lands. Beside it: the running work by tag (a
// press opens it, as on the board), slices through the cloud, the finished work per hour, the steps of
// the live turns and the event tail. Data: GET /cc/board every 3 s; /cc/health, /cc/agents, /cc/systems
// and the owner's board.json (/cc/files/raw<out>/board/board.json) every 15 s; all paused while the tab
// is hidden. No number on this page is made up: a source that does not answer shows a dot, and an idle
// brain stays dark and says so.

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)', surface: 'var(--surface)',
  line: 'var(--border)', bg: 'var(--bg)', warn: '#d4b86a', bad: '#c0605a', ok: '#7fc99c',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const cap = { ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: C.dim }
const clock = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` }
const hhmm = (ts) => { const d = new Date(ts); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}` }
const ago = (s) => { s = Math.max(0, Math.round(s)); return s < 90 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago` }

const CSS = `
.cx-chip { transition: transform 140ms cubic-bezier(0.23,1,0.32,1), border-color 160ms ease, color 160ms ease; }
.cx-chip:active { transform: scale(0.97); }
.cx-chip:focus-visible, .cx-row:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
.cx-row { transition: background-color 160ms ease; }
@media (hover: hover) and (pointer: fine) { .cx-row:hover { background-color: var(--surface2); } .cx-chip:hover { color: var(--text); } }
.cx-grid { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr) 340px; grid-template-areas: 'stage side' 'extra side'; align-items: start; }
.cx-low { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.cx-counters { display: grid; grid-template-columns: repeat(11, minmax(0, 1fr)); }
.cx-stage { height: min(62vh, 620px); }
.cx-wrap ::selection { background: var(--accent); color: var(--bg); }
.cx-tail::-webkit-scrollbar { width: 6px; } .cx-tail::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.cx-num { font-variant-numeric: tabular-nums; }
.cx-ev { animation: cxin 260ms cubic-bezier(0.23,1,0.32,1); }
@keyframes cxin { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
@media (max-width: 1100px) { .cx-counters { grid-template-columns: repeat(6, minmax(0, 1fr)); } }
@media (max-width: 900px) { .cx-grid { grid-template-areas: 'stage' 'side' 'extra'; } .cx-grid, .cx-low { grid-template-columns: minmax(0, 1fr); } .cx-stage { height: 64vw; min-height: 300px; } }
@media (max-width: 520px) { .cx-counters { grid-template-columns: repeat(3, minmax(0, 1fr)); } .cx-from { display: none; } }
@media (prefers-reduced-motion: reduce) { .cx-ev { animation: none; } .cx-chip { transition: none; } }
`

function Chip({ on, children, onClick, title }) {
  return (
    <button className="cx-chip" onClick={onClick} title={title} aria-pressed={!!on}
      style={{ ...mono, fontSize: '11px', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', background: 'transparent',
               border: `1px solid ${on ? C.gold : C.line}`, color: on ? C.gold : C.dim }}>
      {children}
    </button>
  )
}

function Panel({ title, right, children, style }) {
  return (
    <section style={{ border: `1px solid ${C.line}`, borderRadius: '10px', backgroundColor: C.surface, padding: '10px 12px', minWidth: 0, ...style }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
        <h2 style={{ ...cap, margin: 0, fontWeight: 400, color: C.ink }}>{title}</h2>
        <span style={{ flex: 1 }} />
        {right && <span style={{ ...mono, fontSize: '10px', color: C.dim }}>{right}</span>}
      </div>
      {children}
    </section>
  )
}

// a tile's address: in the console's side pane a conversation switches the chat beside it (as on /board)
function openHref(href) {
  if (!href) return
  const m = /^\/talk\?thread=([\w:-]{1,80})$/.exec(href)
  let framed = false
  try { framed = window.self !== window.top } catch { framed = true }
  if (m && framed) { try { window.parent.postMessage({ type: 'cc-open-thread', thread: m[1] }, window.location.origin); return } catch {} }
  window.location.href = href
}

function readColors() {
  const css = getComputedStyle(document.documentElement)
  const v = (k, d) => (css.getPropertyValue(k) || d).trim() || d
  return { bg: v('--bg', '#0e0c0b'), ink: v('--text', '#e8e0d5'), dim: v('--muted', '#6b5f52'), accent: v('--accent', '#c9a96e'), line: v('--border', '#2a2420') }
}

// colour per region: the accent for the conversation, the activity lights' colours elsewhere
const TONE = { centre: 'accent', frontal: '#d4b86a', motor: '#d4b86a', parietal: '#7fc99c', temporal: '#9fb7c9', occipital: '#b9a6d0', hippocampus: '#7fc99c', cerebellum: '#c0605a' }
const toneOf = (id, colors) => (TONE[id] === 'accent' ? colors.accent : TONE[id])

function project(x, y, z, yaw, pitch, cx, cy, sc) {
  const cyw = Math.cos(yaw), syw = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch)
  const x1 = x * cyw + z * syw, z1 = -x * syw + z * cyw
  const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp
  const p = 2.4 / (2.4 - z2)
  return [cx + x1 * sc * p, cy - y2 * sc * p, z2, p]
}

// The stage: the point cloud, tracts, rings and labels on one canvas. `lit` is read every frame from a
// ref, so a new reading of the board eases in without restarting the loop.
function Stage({ litRef, pulsesRef, labelsRef, reduced, idle }) {
  const ref = useRef(null)
  const brain = useRef(null)
  const view = useRef({ yaw: 1.95, pitch: 0.22, sway: 0, drag: null, act: new Float32Array(REGIONS.length) })
  useEffect(() => {
    const cv = ref.current
    if (!cv) return undefined
    const ctx = cv.getContext('2d')
    const small = window.innerWidth < 600
    if (!brain.current || brain.current.small !== small) brain.current = { small, b: makeBrain(small ? 5200 : 9000) }
    const B = brain.current.b
    const colors = readColors()
    const fam = (getComputedStyle(cv).getPropertyValue('--font-mono') || '').trim() || 'monospace'
    let raf = 0, last = 0, W = 0, H = 0
    const fit = () => {
      const d = Math.min(2, window.devicePixelRatio || 1)
      const r = cv.getBoundingClientRect()
      W = r.width; H = r.height
      cv.width = Math.round(W * d); cv.height = Math.round(H * d)
      ctx.setTransform(d, 0, 0, d, 0, 0)
    }
    fit()
    const V = view.current
    const NB = 3   // depth buckets
    const paint = (t, dt) => {
      const lit = litRef.current || {}
      for (let k = 0; k < REGIONS.length; k++) {
        const want = lit[REGIONS[k].id] || 0
        V.act[k] += (want - V.act[k]) * (reduced ? 1 : Math.min(1, dt * 2.5))
      }
      // the brain sways about a three-quarter side view (it reads as a brain from the side, not as a ball)
      if (!reduced && !V.drag) { const d = Math.sin(t * (idle ? 0.06 : 0.1)) * 0.6 - V.sway; V.sway += d; V.yaw += d }
      ctx.clearRect(0, 0, W, H)
      const cx = W / 2, cy = H * 0.47, sc = Math.min(W * 0.5, H * 0.74)
      // the cloud: base points by depth bucket, then lit points per region and bucket, each one fill
      const base = [[], [], []], hot = REGIONS.map(() => [[], [], []])
      const ps = small ? 1.1 : 1.3
      for (let i = 0; i < B.n; i++) {
        const [sx, sy, z, p] = project(B.X[i], B.Y[i], B.Z[i], V.yaw, V.pitch, cx, cy, sc)
        const b = z > 0.15 ? 2 : z > -0.15 ? 1 : 0
        const a = V.act[B.R[i]]
        // a lit region shimmers: each point is on for part of the time, more of it the brighter the region
        const on = a > 0.02 && (reduced || ((B.W[i] * 7.3 + t * 0.6 * B.W[i]) % 1) < 0.35 + a * 0.6)
        ;(on ? hot[B.R[i]][b] : base[b]).push(sx, sy, ps * p * (0.7 + 0.5 * B.W[i]))
      }
      const fillSet = (arr, color, alpha) => {
        if (!arr.length) return
        ctx.globalAlpha = alpha; ctx.fillStyle = color; ctx.beginPath()
        for (let j = 0; j < arr.length; j += 3) ctx.rect(arr[j], arr[j + 1], arr[j + 2], arr[j + 2])
        ctx.fill()
      }
      const depthA = [0.16, 0.3, 0.5]
      for (let b = 0; b < NB; b++) fillSet(base[b], colors.ink, depthA[b] * (idle ? 0.75 : 0.6))
      ctx.globalCompositeOperation = 'lighter'
      for (let k = 0; k < REGIONS.length; k++) for (let b = 0; b < NB; b++) fillSet(hot[k][b], toneOf(REGIONS[k].id, colors), Math.min(1, (0.35 + depthA[b]) * (0.5 + V.act[k])))
      // tracts from the centre to each lit region, a bead travelling along each
      const c0 = REGIONS[REGION_IDX.centre].at
      const pc = project(c0[0], c0[1], c0[2], V.yaw, V.pitch, cx, cy, sc)
      ctx.lineWidth = 1
      for (let k = 0; k < REGIONS.length; k++) {
        if (k === REGION_IDX.centre || V.act[k] < 0.05) continue
        const a = REGIONS[k].at
        const pa = project(a[0], a[1], a[2], V.yaw, V.pitch, cx, cy, sc)
        const mx = (pc[0] + pa[0]) / 2, my = Math.min(pc[1], pa[1]) - 0.08 * sc
        const tone = toneOf(REGIONS[k].id, colors)
        ctx.globalAlpha = 0.18 + 0.4 * V.act[k]; ctx.strokeStyle = tone
        ctx.beginPath(); ctx.moveTo(pc[0], pc[1]); ctx.quadraticCurveTo(mx, my, pa[0], pa[1]); ctx.stroke()
        if (!reduced) {
          for (let q = 0; q < 2; q++) {
            const u = (t * 0.45 + k * 0.137 + q * 0.5) % 1, v = 1 - u
            const bx = v * v * pc[0] + 2 * v * u * mx + u * u * pa[0], by = v * v * pc[1] + 2 * v * u * my + u * u * pa[1]
            ctx.globalAlpha = 0.9 * V.act[k]; ctx.fillStyle = tone
            ctx.beginPath(); ctx.arc(bx, by, 1.8, 0, Math.PI * 2); ctx.fill()
          }
        }
      }
      // rings where events land (1.4 s); with reduced motion a steady ring for the same time
      const now = performance.now()
      pulsesRef.current = (pulsesRef.current || []).filter(pl => now - pl.t0 < 1400)
      for (const pl of pulsesRef.current) {
        const k = REGION_IDX[pl.region]
        if (k === undefined) continue
        const a = REGIONS[k].at
        const pa = project(a[0], a[1], a[2], V.yaw, V.pitch, cx, cy, sc)
        const e = (now - pl.t0) / 1400
        const r = reduced ? 14 : 4 + (1 - Math.pow(1 - e, 3)) * 34
        ctx.globalAlpha = reduced ? 0.6 : 0.8 * (1 - e); ctx.strokeStyle = toneOf(REGIONS[k].id, colors); ctx.lineWidth = 1.2
        ctx.beginPath(); ctx.arc(pa[0], pa[1], r, 0, Math.PI * 2); ctx.stroke()
      }
      ctx.globalCompositeOperation = 'source-over'
      // labels: every region named faintly, lit ones in ink with their count; on a phone only lit ones
      const labels = labelsRef.current || {}
      ctx.font = `${small ? 9 : 10}px ${fam}`
      ctx.textBaseline = 'middle'
      const placed = []
      for (let k = 0; k < REGIONS.length; k++) {
        const L = labels[REGIONS[k].id]
        const litk = V.act[k] > 0.05
        if (small && !litk) continue
        const a = REGIONS[k].at
        const pa = project(a[0], a[1], a[2], V.yaw, V.pitch, cx, cy, sc)
        const right = pa[0] >= cx
        const lx = pa[0] + (right ? 1 : -1) * (small ? 14 : 26), ly = pa[1] - (small ? 8 : 14)
        ctx.globalAlpha = litk ? 0.9 : 0.4; ctx.strokeStyle = litk ? toneOf(REGIONS[k].id, colors) : colors.dim; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(pa[0], pa[1]); ctx.lineTo(lx, ly); ctx.stroke()
        ctx.fillStyle = litk ? colors.ink : colors.dim
        ctx.globalAlpha = litk ? 1 : 0.7
        const text = L ? L : REGIONS[k].name
        // keep the label inside the canvas and off the labels already placed
        const tw = ctx.measureText(text).width
        let x0 = right ? lx + 4 : lx - 4 - tw
        x0 = Math.max(4, Math.min(W - 4 - tw, x0))
        let y0 = ly
        for (let guard = 0; guard < 6 && placed.some(r => x0 < r[0] + r[2] && r[0] < x0 + tw && Math.abs(r[1] - y0) < 12); guard++) y0 += 12
        placed.push([x0, y0, tw])
        ctx.textAlign = 'left'
        ctx.fillText(text, x0, y0)
      }
      ctx.globalAlpha = 1
    }
    const loop = (ts) => {
      const dt = Math.min(0.05, last ? (ts - last) / 1000 : 0.016)
      last = ts
      paint(ts / 1000, dt)
      raf = document.visibilityState === 'visible' ? requestAnimationFrame(loop) : 0
    }
    const start = () => { if (!raf) { last = 0; raf = requestAnimationFrame(loop) } }
    const onVis = () => { if (document.visibilityState === 'visible') start(); else if (raf) { cancelAnimationFrame(raf); raf = 0 } }
    // with reduced motion the loop still runs (labels and lights follow the data) but nothing drifts
    start()
    const onResize = () => fit()
    window.addEventListener('resize', onResize)
    document.addEventListener('visibilitychange', onVis)
    // drag to turn the brain (pointer capture, so it keeps turning when the pointer leaves the canvas)
    const down = (e) => { V.drag = { x: e.clientX, y: e.clientY, yaw: V.yaw, pitch: V.pitch }; try { cv.setPointerCapture(e.pointerId) } catch {} }
    const move = (e) => { if (!V.drag) return; V.yaw = V.drag.yaw + (e.clientX - V.drag.x) * 0.008; V.pitch = Math.max(-0.9, Math.min(0.9, V.drag.pitch + (e.clientY - V.drag.y) * 0.006)) }
    const up = () => { V.drag = null }
    cv.addEventListener('pointerdown', down); cv.addEventListener('pointermove', move)
    cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up)
    return () => {
      if (raf) cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('visibilitychange', onVis)
      cv.removeEventListener('pointerdown', down); cv.removeEventListener('pointermove', move)
      cv.removeEventListener('pointerup', up); cv.removeEventListener('pointercancel', up)
    }
  }, [reduced, idle])
  return <canvas ref={ref} aria-label="The brain: lit regions are the work running now" role="img"
                 style={{ width: '100%', height: '100%', display: 'block', touchAction: 'none', cursor: 'grab' }} />
}

// Three slices through the cloud (axial from above, coronal from the front, sagittal from the side),
// drawn when the lights change, not every frame.
const SLICES = [
  { id: 'axial', name: 'axial', from: 'from above', pick: (x, y) => Math.abs(y - 0.06) < 0.07, u: (x, y, z) => x, v: (x, y, z) => -z },
  { id: 'coronal', name: 'coronal', from: 'from the front', pick: (x, y, z) => Math.abs(z - 0.1) < 0.08, u: (x) => x, v: (x, y) => -y },
  { id: 'sagittal', name: 'sagittal', from: 'from the side', pick: (x) => Math.abs(x - 0.2) < 0.08, u: (x, y, z) => -z, v: (x, y) => -y },
]
function Slice({ s, lit }) {
  const ref = useRef(null)
  const B = useMemo(() => makeBrain(9000), [])
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    const d = Math.min(2, window.devicePixelRatio || 1)
    const r = cv.getBoundingClientRect()
    cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d)
    ctx.setTransform(d, 0, 0, d, 0, 0)
    const colors = readColors()
    ctx.clearRect(0, 0, r.width, r.height)
    const sc = Math.min(r.width, r.height) * 0.62
    for (let i = 0; i < B.n; i++) {
      const x = B.X[i], y = B.Y[i], z = B.Z[i]
      if (!s.pick(x, y, z)) continue
      const id = REGIONS[B.R[i]].id
      const a = (lit && lit[id]) || 0
      ctx.globalAlpha = a > 0.02 ? 0.5 + 0.5 * a : 0.32
      ctx.fillStyle = a > 0.02 ? toneOf(id, colors) : colors.ink
      ctx.fillRect(r.width / 2 + s.u(x, y, z) * sc, r.height / 2 + s.v(x, y, z) * sc, 1.4, 1.4)
    }
    ctx.globalAlpha = 1
  }, [lit, B, s])
  return (
    <div style={{ border: `1px solid ${C.line}`, borderRadius: '8px', padding: '6px 8px', minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={cap}>{s.name}</span><span className="cx-from" style={{ ...mono, fontSize: '10px', color: C.dim }}>{s.from}</span></div>
      <canvas ref={ref} aria-hidden="true" style={{ width: '100%', height: '96px', display: 'block' }} />
    </div>
  )
}

function Counter({ label, value, tone, title }) {
  return (
    <div title={title} style={{ padding: '8px 10px', borderRight: `1px solid ${C.line}`, borderBottom: `1px solid ${C.line}`, minWidth: 0 }}>
      <div style={{ ...cap, fontSize: '9px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
      <div className="cx-num" style={{ fontSize: '22px', fontWeight: 300, lineHeight: 1.25, color: value && tone ? tone : value === '·' ? C.dim : C.ink }}>{value}</div>
    </div>
  )
}

export default function Cortex() {
  const [board, setBoard] = useState(null)       // null: not read yet; false: the bridge did not answer
  const [agents, setAgents] = useState(null)
  const [health, setHealth] = useState(null)
  const [systems, setSystems] = useState(null)
  const [desk, setDesk] = useState(null)
  const [events, setEvents] = useState([])
  const [mode, setMode] = useState('role')
  const [now, setNow] = useState(0)
  const [reduced, setReduced] = useState(false)
  const spiders = useSpidersOn()
  const prev = useRef(null)
  const litRef = useRef({}), pulsesRef = useRef([]), labelsRef = useRef({})

  useEffect(() => {
    const mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
    const read = () => setReduced(!!(mq && mq.matches))
    read()
    if (mq && mq.addEventListener) mq.addEventListener('change', read)
    try { const m = window.localStorage.getItem('bf-cortex-mode'); if (m === 'system' || m === 'role') setMode(m) } catch {}
    return () => { if (mq && mq.removeEventListener) mq.removeEventListener('change', read) }
  }, [])

  // the board every 3 s; the rest every 15 s; nothing while the tab is hidden
  useEffect(() => {
    const getJson = (u) => fetch(u, { cache: 'no-store' }).then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    const loadBoard = () => getJson('/cc/board').then(d => {
      if (!d || !Array.isArray(d.tiles)) throw new Error('shape')
      const evs = boardEvents(prev.current, d, Date.now())
      prev.current = d
      if (evs.length) {
        setEvents(e => [...e, ...evs].slice(-60))
        const t0 = performance.now()
        pulsesRef.current = [...(pulsesRef.current || []), ...evs.filter(x => !x.seed && x.region).map(x => ({ region: x.region, t0 }))].slice(-24)
      }
      setBoard(d); setNow(Date.now())
    }).catch(() => setBoard(b => (b ? b : false)))
    const loadSlow = () => {
      getJson('/cc/agents').then(d => setAgents(d && Array.isArray(d.agents) ? d : false)).catch(() => setAgents(false))
      getJson('/cc/systems').then(d => setSystems(d && Array.isArray(d.tiles) ? d : false)).catch(() => setSystems(false))
      getJson('/cc/health').then(h => {
        setHealth(h || false)
        // the owner's desk board (court and next-box counts), where the bridge keeps its out folder
        if (h && h.out) getJson('/cc/files/raw' + String(h.out).replace(/\/+$/, '') + '/board/board.json').then(d => setDesk(d && d.counts ? d : false)).catch(() => setDesk(false))
        else setDesk(false)
      }).catch(() => { setHealth(false); setDesk(false) })
    }
    let fast = null, slow = null
    const start = () => { if (!fast) { loadBoard(); loadSlow(); fast = setInterval(loadBoard, 3000); slow = setInterval(loadSlow, 15000) } }
    const stop = () => { if (fast) { clearInterval(fast); clearInterval(slow); fast = null; slow = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [])
  useEffect(() => { const t = setInterval(() => { if (document.visibilityState === 'visible') setNow(Date.now()) }, 1000); return () => clearInterval(t) }, [])

  const role = useMemo(() => roleActivity(board || null), [board])
  const sys = useMemo(() => systemActivity(systems || null), [systems])
  const lit = useMemo(() => {
    if (mode === 'system') return Object.fromEntries(sys.map(s => [s.region, s.level]))
    return role.level
  }, [mode, role, sys])
  const labels = useMemo(() => {
    if (mode === 'system') return Object.fromEntries(sys.map(s => [s.region, `${s.system}${s.running ? ` · ${s.running} running` : s.moving ? ` · ${s.moving} moving` : ''}`]))
    return Object.fromEntries(REGIONS.map(r => [r.id, role.count[r.id] ? `${r.role} · ${r.id === 'occipital' ? `${role.count[r.id]} steps` : role.count[r.id]}` : r.name]))
  }, [mode, role, sys])
  litRef.current = lit
  labelsRef.current = labels

  const n = counters({ board: board || null, agents: agents || null, health: health || null, desk: desk || null })
  const tiles = (board && board.tiles) || []
  const live = tiles.filter(t => t.state === 'answering' || t.state === 'waiting')
  const idle = !!board && live.length === 0
  const bins = hourly(board || null)
  const binMax = Math.max(1, ...bins)
  const lastDone = tiles.filter(t => t.ago_s !== null && t.ago_s !== undefined).sort((a, b) => a.ago_s - b.ago_s)[0]
  const stepRuns = live.filter(t => (t.steps || 0) > 0 || t.kind === 'run').slice(0, 8)
  const stepMax = Math.max(1, ...stepRuns.map(t => t.steps || 0))
  const setModeKeep = (m) => { setMode(m); try { window.localStorage.setItem('bf-cortex-mode', m) } catch {} }
  const status = board === false ? 'The bridge is not answering at /cc/board; the brain stays dark until it does.'
    : board === null ? 'Reading the board.'
    : idle ? `Nothing runs right now.${lastDone ? ` The last work finished ${ago(lastDone.ago_s)}.` : ''}`
    : [n.running ? `${n.running} running` : '', n.waiting ? `${n.waiting} waiting for your yes` : '', n.subagents ? `${n.subagents} subagents out` : ''].filter(Boolean).join(' · ')
  const runningJobs = live.filter(t => t.kind === 'job').length
  const turns = live.filter(t => t.kind === 'run').length

  return (
    <>
      <Head><title>Cortex · BrainFoundry</title></Head>
      <style>{LIGHT_CSS}</style>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      {/* one large spider per turn answering, one small per running job and per subagent */}
      <Spiders count={turns} small={runningJobs + (n.subagents || 0)} />
      <div className="cx-wrap" style={{ minHeight: 'calc(100vh - var(--nav-h, 52px))', backgroundColor: C.bg, boxSizing: 'border-box', padding: '12px 14px 40px', color: C.ink }}>
        <header style={{ display: 'flex', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap', padding: '0 2px 10px' }}>
          <h1 style={{ margin: 0, fontSize: '22px', fontWeight: 300, letterSpacing: '-0.01em' }}>Cortex</h1>
          <span style={{ fontSize: '13px', color: idle || !board ? C.dim : C.ink, flex: '1 1 280px' }}>{status}</span>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Chip on={mode === 'role'} onClick={() => setModeKeep('role')} title="Each region is a kind of work: turns, jobs, agents, subagents, tool calls, cards, just filed, failed">by role</Chip>
            <Chip on={mode === 'system'} onClick={() => setModeKeep('system')} title="Each region is one system from the systems board, busiest first">by system</Chip>
            <Chip on={spiders} onClick={() => spidersSet(!spiders)} title={reduced ? 'Your system asks for reduced motion, so no spider walks' : 'A spider walks the page for each turn answering; small ones for jobs and subagents. Here and in the chat.'}>{spiders ? 'spiders on' : 'spiders off'}</Chip>
            <a href="/board" className="cx-chip" style={{ ...mono, fontSize: '11px', color: C.dim, padding: '4px 4px' }}>board</a>
            <a href="/agents" className="cx-chip" style={{ ...mono, fontSize: '11px', color: C.dim, padding: '4px 4px' }}>agents</a>
            <a href="/systems" className="cx-chip" style={{ ...mono, fontSize: '11px', color: C.dim, padding: '4px 4px' }}>systems</a>
          </div>
        </header>

        <div className="cx-counters" style={{ border: `1px solid ${C.line}`, borderRight: 'none', borderBottom: 'none', borderRadius: '10px', overflow: 'hidden', marginBottom: '12px', backgroundColor: C.surface }}>
          <Counter label="running" value={kNum(n.running)} tone={C.gold} title="Turns and jobs answering now (GET /cc/board)" />
          <Counter label="your yes" value={kNum(n.waiting)} tone={C.warn} title="Turns and permits waiting on a card (GET /cc/board)" />
          <Counter label="jobs" value={kNum(n.jobs)} tone={LIGHT.job} title="Background jobs running on the box (GET /cc/health)" />
          <Counter label="standing agents" value={kNum(n.standing)} title="Standing agents switched on (GET /cc/agents)" />
          <Counter label="subagents" value={kNum(n.subagents)} title="Subagents the live turns fanned out to (GET /cc/board)" />
          <Counter label="tool calls" value={kNum(n.steps)} title="Steps the live turns have taken so far (GET /cc/board)" />
          <Counter label="tokens 24 h" value={kNum(n.tokens)} title="Tokens in and out of the conversations on the board, last 24 h (GET /cc/board)" />
          <Counter label="done 24 h" value={kNum(n.done)} tone={C.ok} title="Conversations and jobs finished in the last 24 h (GET /cc/board)" />
          <Counter label="failed" value={kNum(n.failed)} tone={C.bad} title="Failed and not dismissed (GET /cc/board)" />
          <Counter label="court" value={kNum(n.court)} title="Rulings waiting in the owner's court (board.json)" />
          <Counter label="next box" value={kNum(n.next)} title="Open rows in the next box (board.json)" />
        </div>

        <div className="cx-grid">
            <section style={{ gridArea: 'stage', position: 'relative', border: `1px solid ${C.line}`, borderRadius: '10px', backgroundColor: C.surface, overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: '10px', left: '12px', right: '12px', display: 'flex', gap: '8px', pointerEvents: 'none', zIndex: 1 }}>
                <span style={{ ...cap, color: C.ink }}>{mode === 'role' ? 'by role' : 'by system'}</span>
                <span style={{ flex: 1 }} />
                <span style={{ ...mono, fontSize: '10px', color: C.dim }}>{Object.values(lit).filter(v => v > 0.05).length} of {REGIONS.length} regions lit</span>
              </div>
              <div className="cx-stage"><Stage litRef={litRef} pulsesRef={pulsesRef} labelsRef={labelsRef} reduced={reduced} idle={idle || !board} /></div>
              <div style={{ position: 'absolute', bottom: '8px', left: '12px', right: '12px', display: 'flex', gap: '8px', pointerEvents: 'none' }}>
                <span style={{ ...mono, fontSize: '10px', color: C.dim }}>drag to turn</span>
                <span style={{ flex: 1 }} />
                <span style={{ ...mono, fontSize: '10px', color: C.dim }}>{board ? `read ${board.now ? board.now.slice(11, 19) : ''} UTC · every 3 s` : ''}</span>
              </div>
            </section>
          <div style={{ gridArea: 'extra', display: 'grid', gap: '12px', minWidth: 0 }}>
            <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
              {SLICES.map(s => <Slice key={s.id} s={s} lit={lit} />)}
            </div>
            <div className="cx-low">
              <Panel title="finished per hour" right={`${bins.reduce((a, b) => a + b, 0)} in 24 h`}>
                <svg viewBox="0 0 240 64" preserveAspectRatio="none" style={{ width: '100%', height: '72px', display: 'block' }} role="img" aria-label="Work finished per hour over the last 24 hours">
                  {bins.map((v, i) => <rect key={i} x={i * 10 + 1} y={60 - (v / binMax) * 56} width="8" height={Math.max(v ? 2 : 0.6, (v / binMax) * 56)} rx="1" fill={v ? '#7fc99c' : '#6b5f52'} opacity={v ? 0.85 : 0.35} />)}
                </svg>
                <div style={{ display: 'flex', justifyContent: 'space-between', ...mono, fontSize: '10px', color: C.dim }}><span>24 h ago</span><span>now</span></div>
              </Panel>
              <Panel title="steps per live run" right={stepRuns.length ? `${n.steps} in all` : 'none live'}>
                {stepRuns.length === 0 && <p style={{ fontSize: '12px', color: C.dim, margin: '4px 0', lineHeight: 1.5 }}>When a turn runs, each one gets a bar here with the tool calls it has made.</p>}
                {stepRuns.map(t => {
                  const { tag, rest } = tagOf(t.title)
                  return (
                    <div key={t.key} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 9rem) minmax(0, 1fr) 2.5rem', gap: '8px', alignItems: 'center', margin: '4px 0' }}>
                      <span style={{ ...mono, fontSize: '11px', color: C.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={t.title}>{tag || rest}</span>
                      <span style={{ height: '6px', borderRadius: '3px', backgroundColor: C.line, overflow: 'hidden' }}>
                        <span style={{ display: 'block', height: '100%', width: `${((t.steps || 0) / stepMax) * 100}%`, backgroundColor: C.gold, borderRadius: '3px', transition: 'width 300ms cubic-bezier(0.23,1,0.32,1)' }} />
                      </span>
                      <span className="cx-num" style={{ ...mono, fontSize: '11px', color: C.dim, textAlign: 'right' }}>{t.steps || 0}</span>
                    </div>
                  )
                })}
              </Panel>
            </div>
          </div>

          <div style={{ gridArea: 'side', display: 'grid', gap: '12px', minWidth: 0 }}>
            <Panel title="running" right={live.length ? `${live.length} live` : ''}>
              {board && live.length === 0 && <p style={{ fontSize: '13px', color: C.dim, margin: '2px 0 4px', lineHeight: 1.55 }}>Nothing runs. A turn you start, a job or a standing agent on its run appears here by its tag.</p>}
              {board === false && <p style={{ fontSize: '13px', color: C.dim, margin: '2px 0 4px' }}>No answer from the bridge.</p>}
              <div style={{ display: 'grid', gap: '2px', margin: '0 -6px' }}>
                {live.map(t => {
                  const { tag, rest } = tagOf(t.title)
                  const color = t.state === 'waiting' ? C.warn : t.kind === 'job' ? (t.agent ? LIGHT.agent : LIGHT.job) : LIGHT.turn
                  const el = t.started ? Math.max(t.elapsed_s || 0, (now - Date.parse(t.started)) / 1000) : (t.elapsed_s || 0)
                  return (
                    <div key={t.key} className="cx-row" role={t.href ? 'link' : undefined} tabIndex={t.href ? 0 : undefined}
                         onClick={() => openHref(t.href)} onKeyDown={(e) => { if (e.key === 'Enter') openHref(t.href) }}
                         style={{ display: 'grid', gridTemplateColumns: '8px minmax(0, 1fr) auto', gap: '8px', alignItems: 'baseline', padding: '6px', borderRadius: '6px', cursor: t.href ? 'pointer' : 'default' }}>
                      <span className={t.state === 'answering' ? 'cc-light-on' : undefined} style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: color, alignSelf: 'center' }} />
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '13px' }} title={t.title}>
                          {tag && <span style={{ ...mono, fontSize: '11px', color, marginRight: '6px' }}>{tag}</span>}{rest}
                        </span>
                        {t.last && <span style={{ display: 'block', fontSize: '11px', color: C.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.last}</span>}
                      </span>
                      <span className="cx-num" style={{ ...mono, fontSize: '11px', color: C.dim, whiteSpace: 'nowrap' }}>{t.state === 'waiting' ? 'your yes' : clock(el)}</span>
                    </div>
                  )
                })}
              </div>
            </Panel>
            <Panel title="tail" right={events.length ? `${events.length} events` : ''}>
              <div className="cx-tail" role="log" aria-live="polite" style={{ maxHeight: '360px', overflowY: 'auto', display: 'flex', flexDirection: 'column-reverse' }}>
                <div>
                  {events.length === 0 && <p style={{ fontSize: '12px', color: C.dim, margin: '2px 0', lineHeight: 1.5 }}>{board === false ? 'No events: the bridge does not answer.' : 'No events in the last day yet. Each start, line, card and finish lands here as it happens.'}</p>}
                  {events.map((e, i) => (
                    <div key={`${e.ts}-${i}`} className={e.seed ? undefined : 'cx-ev'} onClick={() => openHref(e.href)}
                         style={{ display: 'grid', gridTemplateColumns: '4.6rem minmax(0, 1fr)', gap: '8px', padding: '3px 0', cursor: e.href ? 'pointer' : 'default', opacity: e.seed ? 0.7 : 1 }}>
                      <span className="cx-num" style={{ ...mono, fontSize: '10px', color: C.dim }}>{hhmm(e.ts)}</span>
                      <span style={{ ...mono, fontSize: '11px', lineHeight: 1.45, color: e.kind === 'failed' ? C.bad : e.kind === 'waiting' ? C.warn : C.ink, wordBreak: 'break-word' }}>
                        <span style={{ color: e.region ? toneOf(e.region, { accent: 'var(--accent)' }) : C.dim }}>{e.region ? REGIONS[REGION_IDX[e.region]].name : 'board'}</span> {e.text}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
            <Panel title="regions" right={mode === 'role' ? 'by role' : 'by system'}>
              <div style={{ display: 'grid', gap: '3px' }}>
                {(mode === 'role' ? REGIONS.map(r => ({ id: r.id, a: r.name, b: r.what, c: role.count[r.id] })) : sys.map(s => ({ id: s.region, a: s.system, b: REGIONS[REGION_IDX[s.region]].name, c: s.running }))).map(r => (
                  <div key={r.id} style={{ display: 'grid', gridTemplateColumns: '8px minmax(0, 7.5rem) minmax(0, 1fr) 2rem', gap: '8px', alignItems: 'baseline', fontSize: '11px' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: toneOf(r.id, { accent: 'var(--accent)' }), opacity: (lit[r.id] || 0) > 0.05 ? 1 : 0.3, alignSelf: 'center' }} />
                    <span style={{ ...mono, color: C.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.a}</span>
                    <span style={{ color: C.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.b}</span>
                    <span className="cx-num" style={{ ...mono, color: r.c ? C.ink : C.dim, textAlign: 'right' }}>{r.c || 0}</span>
                  </div>
                ))}
                {mode === 'system' && sys.length === 0 && <p style={{ fontSize: '12px', color: C.dim, margin: 0 }}>{systems === false ? 'The systems board does not answer at /cc/systems.' : 'Reading the systems board.'}</p>}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </>
  )
}
