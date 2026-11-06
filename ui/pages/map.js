import Head from 'next/head'
import React, { useEffect, useMemo, useRef, useState } from 'react'

// The map (2026-11-06, hbar: "a single MAP so we keep track visually of seeing AI agents, and the
// different tasks etc. that are happening in real time"; autonomy eval E12).
//
// /board lists runs as tiles; this draws how they hang together. The brain sits at the centre,
// every conversation of the last day is a light on the ring around it, and the background jobs a
// conversation started hang off that conversation. Your open tasks, the next-box candidates and
// finished jobs whose report asks you something sit on the outer orbit. Colour is state: answering
// pulses in the accent, waiting on you burns amber and is the brightest thing on screen, failed is
// red, done is quiet. Click a light for its line, its time, its last line, any card with its
// buttons, and a link to the conversation. Same reads as the board (GET /cc/board, /cc/actions,
// /api/bf/tasks), every three seconds, none while the tab is hidden. Nothing here writes except
// the card buttons, which are the board's own (POST /cc/permits/<approve|deny>).

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)', surface: 'var(--surface)',
  line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)', warn: '#d4b86a', bad: '#c0605a', ok: '#7fc99c',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const STATE = {
  waiting: { color: C.warn, word: 'waiting on you' },
  failed: { color: C.bad, word: 'failed' },
  answering: { color: C.gold, word: 'answering' },
  done: { color: C.ok, word: 'done' },
  task: { color: C.warn, word: 'your task' },
  next: { color: C.dim, word: 'proposed next' },
  ask: { color: C.warn, word: 'report asks you' },
}
const RANK = { waiting: 0, failed: 1, answering: 2, done: 3 }
const W = 1000, H = 720, CX = 500, CY = 360, R = 215, R_OUT = 330
const OUTER_MAX = 14

const clock = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` }
const ago = (s) => { s = Math.max(0, Math.round(s)); return s < 90 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago` }
const cut = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s }

const CSS = `
@keyframes map-breathe { 0%,100% { opacity: .55 } 50% { opacity: 1 } }
@keyframes map-halo { 0% { transform: scale(1); opacity: .55 } 100% { transform: scale(2.6); opacity: 0 } }
@keyframes map-flow { to { stroke-dashoffset: -24 } }
@keyframes map-drift { 0%,100% { transform: translate(0,0) } 50% { transform: translate(0,-3px) } }
.map-node { transition: transform .9s cubic-bezier(.2,.8,.2,1); cursor: pointer }
.map-breathe { animation: map-breathe 2.2s ease-in-out infinite }
.map-halo { transform-box: fill-box; transform-origin: center; animation: map-halo 1.8s ease-out infinite }
.map-flow { stroke-dasharray: 4 8; animation: map-flow 1.2s linear infinite }
.map-drift { animation: map-drift 6s ease-in-out infinite }
@media (prefers-reduced-motion: reduce) { .map-breathe, .map-halo, .map-flow, .map-drift { animation: none } }
`

// Groups the board's tiles by conversation: the conversation's own tile is the hub, its jobs and
// cards are satellites. Jobs and permits with no known conversation hang off the brain directly.
export function buildMap(board, actions, tasks) {
  const tiles = (board && board.tiles) || []
  const hubs = new Map()
  const loose = []
  for (const t of tiles) {
    if (t.kind === 'run' || t.kind === 'thread') {
      const k = t.thread || t.key
      const h = hubs.get(k)
      // a live run outranks the same conversation's finished record
      if (!h || (RANK[t.state] ?? 9) < (RANK[h.tile.state] ?? 9)) hubs.set(k, { key: k, tile: t, sats: h ? h.sats : [] })
    }
  }
  for (const t of tiles) {
    if (t.kind === 'run' || t.kind === 'thread') continue
    const h = t.thread ? hubs.get(t.thread) : null
    if (h) h.sats.push(t)
    else loose.push(t)
  }
  // the loose jobs and permits ride the ring as their own lights
  for (const t of loose) hubs.set(t.key, { key: t.key, tile: t, sats: [] })
  const ring = [...hubs.values()].sort((a, b) => String(a.tile.started || '').localeCompare(String(b.tile.started || '')) || a.key.localeCompare(b.key))
  const outer = []
  for (const a of ((actions && actions.jobs) || [])) outer.push({ key: `ask:${a.id}`, kind: 'ask', state: 'ask', title: a.title || a.id, last: [a.status && `${a.status}:`, a.line].filter(Boolean).join(' '), href: a.thread ? `/talk?thread=${a.thread}` : '/board', raw: a })
  for (const t of (tasks || []).filter(x => !x.done)) outer.push({ key: `task:${t.id}`, kind: 'task', state: 'task', title: t.text, last: t.due ? `due ${t.due}` : '', href: '/tasks', raw: t })
  for (const n of ((actions && actions.next) || [])) outer.push({ key: `next:${n.id}`, kind: 'next', state: 'next', title: n.what, last: [n.why, n.cost && `cost ${n.cost}`].filter(Boolean).join(' · '), href: '/board', raw: n })
  return { ring, outer: outer.slice(0, OUTER_MAX), outerMore: Math.max(0, outer.length - OUTER_MAX) }
}

// Fixed places: the ring spreads evenly from the top, satellites fan outward from their hub.
export function layout(ring, outer) {
  const pos = {}
  const n = Math.max(ring.length, 1)
  ring.forEach((h, i) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2
    pos[h.key] = { x: CX + Math.cos(a) * R, y: CY + Math.sin(a) * R * 0.86, a }
    const m = h.sats.length
    h.sats.forEach((s, j) => {
      const off = m === 1 ? 0 : (j / (m - 1) - 0.5) * Math.min(0.5, 0.16 * m)
      pos[s.key] = { x: CX + Math.cos(a + off) * (R + 62), y: CY + Math.sin(a + off) * (R + 62) * 0.86, a: a + off, hub: h.key }
    })
  })
  const k = Math.max(outer.length, 1)
  outer.forEach((o, i) => {
    // the outer orbit fills the lower half, left to right, out of the ring's way
    const a = Math.PI * (0.12 + 0.76 * (k === 1 ? 0.5 : i / (k - 1)))
    pos[o.key] = { x: CX + Math.cos(Math.PI - a) * R_OUT * 1.18, y: CY + Math.sin(a) * R_OUT * 0.95, a: Math.PI - a }
  })
  return pos
}

function Node({ id, p, state, kind, r, label, sel, onPick, showLabel, below }) {
  const st = STATE[state] || STATE.done
  const live = state === 'answering'
  const hot = state === 'waiting' || state === 'ask'
  const right = Math.cos(p.a || 0) >= -0.05
  return (
    <g className="map-node" style={{ transform: `translate(${p.x}px, ${p.y}px)` }} onClick={(e) => { e.stopPropagation(); onPick(id) }}>
      <circle r={r + 14} style={{ fill: 'transparent' }} />
      {hot && <circle r={r} className="map-halo" style={{ fill: 'none', stroke: st.color, strokeWidth: 2 }} />}
      {live && <circle r={r + 5} className="map-breathe" style={{ fill: 'none', stroke: st.color, strokeWidth: 1, opacity: 0.6 }} />}
      {kind === 'next'
        ? <rect x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} transform="rotate(45)" style={{ fill: C.bg, stroke: st.color, strokeWidth: sel ? 2.4 : 1.2 }} />
        : <circle r={r} className={live ? 'map-breathe' : undefined}
                  style={{ fill: state === 'done' ? C.bg : st.color, fillOpacity: state === 'done' ? 1 : hot ? 0.95 : 0.85, stroke: sel ? C.ink : st.color, strokeWidth: sel ? 2.4 : 1.3 }} />}
      {showLabel && (
        <text x={below ? 0 : right ? r + 7 : -(r + 7)} y={below ? r + 15 : 4} textAnchor={below ? 'middle' : right ? 'start' : 'end'}
              style={{ ...mono, fontSize: hot ? 12 : 11, fill: hot ? st.color : state === 'done' ? C.dim : C.ink, pointerEvents: 'none' }}>{label}</text>
      )}
    </g>
  )
}

export default function MapPage() {
  const [board, setBoard] = useState(null)
  const [actions, setActions] = useState(null)
  const [tasks, setTasks] = useState(null)
  const [sel, setSel] = useState(null)
  const [now, setNow] = useState(Date.now())
  const [busy, setBusy] = useState(null)
  const [note, setNote] = useState(null)
  const timer = useRef(null)

  const load = () => {
    fetch('/cc/board', { cache: 'no-store' }).then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => setBoard(d && Array.isArray(d.tiles) ? d : false)).catch(() => setBoard(b => (b ? b : false)))
    fetch('/cc/actions', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => setActions(d)).catch(() => {})
    fetch('/api/bf/tasks', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => setTasks(d && d.tasks ? d.tasks : [])).catch(() => {})
  }
  useEffect(() => {
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])

  const { ring, outer, outerMore } = useMemo(() => buildMap(board, actions, tasks), [board, actions, tasks])
  const pos = useMemo(() => layout(ring, outer), [ring, outer])
  const items = useMemo(() => {
    const m = {}
    ring.forEach(h => { m[h.key] = h.tile; h.sats.forEach(s => { m[s.key] = s }) })
    outer.forEach(o => { m[o.key] = o })
    return m
  }, [ring, outer])
  const picked = sel ? items[sel] : null
  const waiting = Object.entries(items).filter(([, t]) => t.state === 'waiting')
  const counts = { answering: 0, waiting: 0, failed: 0, done: 0 }
  Object.values(items).forEach(t => { if (counts[t.state] !== undefined) counts[t.state] += 1 })

  const decide = async (id, action) => {
    setBusy(id); setNote(null)
    try {
      const r = await fetch(`/cc/permits/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setNote(d.error || `the bridge answered ${r.status}`)
    } catch { setNote('the bridge did not answer') }
    setBusy(null); load()
  }

  const timeLine = (t) => {
    if (!t) return ''
    const live = t.state === 'answering' || t.state === 'waiting'
    if (live && t.started) return `running ${clock(Math.max(t.elapsed_s || 0, (now - Date.parse(t.started)) / 1000))}`
    return [t.elapsed_s ? `took ${clock(t.elapsed_s)}` : '', t.ago_s !== null && t.ago_s !== undefined ? ago(t.ago_s) : ''].filter(Boolean).join(' · ')
  }
  const kindWord = (t) => ({ run: 'conversation', thread: 'conversation', job: t.agent ? 'agent' : 'background job', permit: 'proposed action', task: 'task', next: 'next-box candidate', ask: 'job report' }[t.kind] || t.kind)

  return (
    <>
      <Head><title>Map · BrainFoundry</title></Head>
      <style>{CSS}</style>
      <div onClick={() => setSel(null)}
           style={{ position: 'relative', height: 'calc(100vh - var(--nav-h, 52px))', backgroundColor: C.bg, color: C.ink, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 14, top: 10, right: 14, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', zIndex: 2 }}>
          <span style={{ ...mono, color: C.gold, fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase' }}>map</span>
          {['waiting', 'answering', 'failed', 'done'].map(k => (
            <span key={k} style={{ ...mono, fontSize: 11, color: counts[k] ? STATE[k].color : C.dim, opacity: counts[k] ? 1 : 0.6 }}>{counts[k]} {STATE[k].word}</span>
          ))}
          <span style={{ flex: 1 }} />
          <a href="/board" style={{ ...mono, fontSize: 11, color: C.dim }}>board</a>
          <a href="/tasks" style={{ ...mono, fontSize: 11, color: C.dim }}>tasks</a>
          <a href="/talk?thread=new" style={{ ...mono, fontSize: 11, color: C.gold }}>+ new</a>
        </div>
        {waiting.length > 0 && (
          <button onClick={(e) => { e.stopPropagation(); setSel(waiting[0][0]) }}
                  style={{ ...mono, position: 'absolute', left: '50%', transform: 'translateX(-50%)', top: 40, zIndex: 2, fontSize: 12, padding: '6px 14px', borderRadius: 8,
                           border: `1px solid ${C.warn}`, backgroundColor: 'transparent', color: C.warn, cursor: 'pointer' }}>
            {waiting.length} waiting on you: {cut(waiting[0][1].title, 48)}
          </button>
        )}
        {note && <p style={{ ...mono, position: 'absolute', left: 14, top: 34, fontSize: 12, color: C.bad, zIndex: 2 }}>{note}</p>}
        {board === false && <p style={{ position: 'absolute', left: 14, top: 40, fontSize: 13, color: C.dim, zIndex: 2 }}>The bridge is not answering at /cc/board. The map fills by itself once it does.</p>}
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" style={{ width: '100%', height: '100%', display: 'block' }}>
          <g className="map-drift">
            <ellipse cx={CX} cy={CY} rx={R} ry={R * 0.86} style={{ fill: 'none', stroke: C.line, strokeOpacity: 0.5 }} />
            {ring.map(h => {
              const p = pos[h.key], st = STATE[h.tile.state] || STATE.done
              const live = h.tile.state === 'answering' || h.tile.state === 'waiting'
              return (
                <g key={'e' + h.key}>
                  <line x1={CX} y1={CY} x2={p.x} y2={p.y} className={live ? 'map-flow' : undefined}
                        style={{ stroke: live ? st.color : C.line, strokeOpacity: live ? 0.8 : 0.45, strokeWidth: live ? 1.4 : 1 }} />
                  {h.sats.map(s => {
                    const q = pos[s.key], ss = STATE[s.state] || STATE.done, sl = s.state === 'answering' || s.state === 'waiting'
                    return <line key={'e' + s.key} x1={p.x} y1={p.y} x2={q.x} y2={q.y} className={sl ? 'map-flow' : undefined}
                                 style={{ stroke: sl ? ss.color : C.line, strokeOpacity: sl ? 0.8 : 0.4 }} />
                  })}
                </g>
              )
            })}
            {outer.map(o => {
              const q = pos[o.key]
              return <line key={'e' + o.key} x1={CX} y1={CY} x2={q.x} y2={q.y} style={{ stroke: C.line, strokeOpacity: 0.18, strokeDasharray: '2 6' }} />
            })}
            <circle cx={CX} cy={CY} r={34} className="map-breathe" style={{ fill: C.gold, fillOpacity: 0.12 }} />
            <circle cx={CX} cy={CY} r={13} style={{ fill: C.gold }} />
            <text x={CX} y={CY + 34} textAnchor="middle" style={{ ...mono, fontSize: 11, letterSpacing: '0.14em', fill: C.dim }}>BRAIN</text>
            {ring.map(h => (
              <React.Fragment key={h.key}>
                <Node id={h.key} p={pos[h.key]} state={h.tile.state} kind={h.tile.kind} r={h.tile.state === 'waiting' ? 11 : 9}
                      label={cut(h.tile.title, ring.length > 14 ? 22 : 30)} sel={sel === h.key} onPick={setSel} showLabel below />
                {h.sats.map(s => (
                  <Node key={s.key} id={s.key} p={pos[s.key]} state={s.state} kind={s.kind} r={s.state === 'waiting' ? 8 : 5.5}
                        label={cut(s.title, 22)} sel={sel === s.key} onPick={setSel} showLabel={sel === s.key || s.state === 'waiting' || s.state === 'answering'} />
                ))}
              </React.Fragment>
            ))}
            {outer.map(o => (
              <Node key={o.key} id={o.key} p={pos[o.key]} state={o.state} kind={o.kind} r={o.kind === 'next' ? 5 : 6}
                    label={cut(o.title, 26)} sel={sel === o.key} onPick={setSel} showLabel />
            ))}
            {outerMore > 0 && <text x={W - 20} y={H - 16} textAnchor="end" style={{ ...mono, fontSize: 11, fill: C.dim }}>+{outerMore} more on the board and tasks</text>}
            {board && ring.length === 0 && <text x={CX} y={CY - 60} textAnchor="middle" style={{ fontSize: 14, fill: C.dim }}>Nothing ran in the last day.</text>}
          </g>
        </svg>
        <div onClick={e => e.stopPropagation()}
             style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 'min(380px, 92vw)', padding: '44px 20px 20px', boxSizing: 'border-box',
                      backgroundColor: C.surface, borderLeft: `1px solid ${C.line}`, overflowY: 'auto', zIndex: 3,
                      transform: picked ? 'none' : 'translateX(105%)', transition: 'transform .4s cubic-bezier(.2,.8,.2,1)' }}>
          {picked && (() => {
            const st = STATE[picked.state] || STATE.done
            return (
              <>
                <a onClick={() => setSel(null)} aria-label="close" style={{ position: 'absolute', right: 16, top: 12, cursor: 'pointer', color: C.dim, fontSize: 18 }}>×</a>
                <div style={{ ...mono, fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: st.color }}>{picked.word || st.word} · {kindWord(picked)}</div>
                <div style={{ fontSize: 17, lineHeight: 1.35, margin: '8px 0 6px' }}>{picked.title}</div>
                <div style={{ ...mono, fontSize: 11, color: C.dim }}>{timeLine(picked)}</div>
                {picked.last && <p style={{ fontSize: 13.5, lineHeight: 1.5, color: picked.state === 'failed' ? C.bad : C.dim, margin: '12px 0' }}>{picked.last}</p>}
                {(picked.cards || []).map(c => (
                  <div key={c.id} style={{ border: `1px solid ${C.warn}`, borderRadius: 10, padding: '8px 10px', margin: '10px 0' }}>
                    <div style={{ ...mono, fontSize: 12, lineHeight: 1.45, wordBreak: 'break-word' }}>{c.summary || 'an action waits for your yes'}</div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button disabled={busy === c.id} onClick={() => decide(c.id, 'approve')}
                              style={{ ...mono, fontSize: 12, padding: '6px 14px', borderRadius: 8, border: 'none', backgroundColor: C.gold, color: C.onAccent, cursor: 'pointer' }}>{c.platform === 'box' ? 'Allow' : 'Send'}</button>
                      <button disabled={busy === c.id} onClick={() => decide(c.id, 'deny')}
                              style={{ ...mono, fontSize: 12, padding: '6px 14px', borderRadius: 8, border: `1px solid ${C.line}`, backgroundColor: 'transparent', color: C.dim, cursor: 'pointer' }}>{c.platform === 'box' ? 'Refuse' : 'Cancel'}</button>
                    </div>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 12 }}>
                  {picked.href && <a href={picked.href} style={{ ...mono, fontSize: 12, color: C.gold }}>{picked.kind === 'run' || picked.kind === 'thread' ? 'open the conversation' : 'open'}</a>}
                  {(picked.links || []).slice(0, 4).map(l => (
                    <a key={l.href} href={l.href} target={l.kind === 'url' ? '_blank' : undefined} rel={l.kind === 'url' ? 'noreferrer' : undefined}
                       style={{ ...mono, fontSize: 12, color: C.dim }}>{l.label}</a>
                  ))}
                </div>
              </>
            )
          })()}
        </div>
      </div>
    </>
  )
}
