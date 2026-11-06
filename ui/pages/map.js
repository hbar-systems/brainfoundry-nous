import Head from 'next/head'
import React, { useEffect, useMemo, useRef, useState } from 'react'

// The map (2026-11-06, hbar: "a single MAP so we keep track visually of seeing AI agents, and the
// different tasks etc. that are happening in real time"; autonomy eval E12). Live lanes, his
// pick after the first ring version: "time left to right, now line, bars per run and job, waiting
// blinks at the now line, queue past now".
//
// One lane per conversation of the window, newest work on top after anything waiting on you. Time
// runs left to right up to the now line; a run is a bar from when it started to when it ended, or
// to now while it answers; the jobs and agents a conversation started are thinner bars under it.
// What waits on you reaches the now line and blinks there. Past the now line is what has not
// happened yet: your open tasks, finished job reports that ask you something, and next-box
// candidates. Click a bar for its line, its time, its last line, any card with its buttons, and
// the conversation. Same reads as the board (GET /cc/board, /cc/actions, /api/bf/tasks), every
// three seconds, none while the tab is hidden. Nothing here writes except the card buttons, which
// are the board's own (POST /cc/permits/<approve|deny>).

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
const RANK = { waiting: 0, answering: 1, failed: 2, done: 3 }
const WINDOWS = [[3600, '1 h'], [6 * 3600, '6 h'], [24 * 3600, '24 h']]
const NOW_AT = 0.76      // where the now line sits across the track; the queue lives to its right
const LABEL_W = 210

const clock = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` }
const ago = (s) => { s = Math.max(0, Math.round(s)); return s < 90 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago` }
const hhmm = (ms) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }

const CSS = `
@keyframes lane-blink { 0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(212,184,106,.7) } 50% { opacity: .35; box-shadow: 0 0 0 7px rgba(212,184,106,0) } }
@keyframes lane-stripes { to { background-position: 28px 0 } }
@keyframes lane-glow { 0%,100% { opacity: .55 } 50% { opacity: 1 } }
.lane-blink { animation: lane-blink 1.1s ease-in-out infinite }
.lane-run { background-image: repeating-linear-gradient(-45deg, rgba(255,255,255,.18) 0 7px, transparent 7px 14px); background-size: 28px 100%; animation: lane-stripes 1s linear infinite }
.lane-now { animation: lane-glow 2.4s ease-in-out infinite }
.lane-row:hover { background-color: var(--surface2) }
@media (prefers-reduced-motion: reduce) { .lane-blink, .lane-run, .lane-now { animation: none } }
`

// When a tile began and ended, in ms. A live tile ends now. A finished conversation's tile carries
// its last moment in ago_s and its length in elapsed_s; a live run or job carries started.
export function span(t, now) {
  const live = t.state === 'answering' || t.state === 'waiting'
  const started = t.started ? Date.parse(t.started) : NaN
  let end
  if (live) end = now
  else if (t.ago_s !== null && t.ago_s !== undefined) end = now - t.ago_s * 1000
  else if (!Number.isNaN(started)) end = started + (t.elapsed_s || 0) * 1000
  else end = now
  let begin = live && !Number.isNaN(started) ? started : end - (t.elapsed_s || 0) * 1000
  if (Number.isNaN(begin) || begin > end) begin = end
  return { begin, end, live }
}

// Lanes: a conversation's own tile is the lane, its jobs and cards ride under it. Jobs and
// permits with no known conversation get a lane of their own.
export function buildLanes(board, now) {
  const tiles = (board && board.tiles) || []
  const lanes = new Map()
  for (const t of tiles) {
    if (t.kind !== 'run' && t.kind !== 'thread') continue
    const k = t.thread || t.key
    const l = lanes.get(k)
    if (!l) lanes.set(k, { key: k, head: t, bars: [t], subs: [] })
    else {
      l.bars.push(t)
      if ((RANK[t.state] ?? 9) < (RANK[l.head.state] ?? 9)) l.head = t
    }
  }
  for (const t of tiles) {
    if (t.kind === 'run' || t.kind === 'thread') continue
    const l = t.thread ? lanes.get(t.thread) : null
    if (l) l.subs.push(t)
    else lanes.set(t.key, { key: t.key, head: t, bars: [t], subs: [] })
  }
  const last = (l) => Math.max(...[...l.bars, ...l.subs].map(t => span(t, now).end))
  return [...lanes.values()].sort((a, b) => ((RANK[a.head.state] ?? 9) - (RANK[b.head.state] ?? 9)) || (last(b) - last(a)))
}

export function buildQueue(actions, tasks) {
  const q = []
  for (const a of ((actions && actions.jobs) || [])) q.push({ key: `ask:${a.id}`, kind: 'ask', state: 'ask', title: a.title || a.id, last: [a.status && `${a.status}:`, a.line].filter(Boolean).join(' '), href: a.thread ? `/talk?thread=${a.thread}` : '/board' })
  for (const t of (tasks || []).filter(x => !x.done)) q.push({ key: `task:${t.id}`, kind: 'task', state: 'task', title: t.text, last: t.due ? `due ${t.due}` : '', href: '/tasks' })
  for (const n of ((actions && actions.next) || [])) q.push({ key: `next:${n.id}`, kind: 'next', state: 'next', title: n.what, last: [n.why, n.cost && `cost ${n.cost}`].filter(Boolean).join(' · '), href: '/board' })
  return q
}

function Bar({ t, now, from, win, thin, sel, onPick }) {
  const { begin, end, live } = span(t, now)
  if (end < from) return null
  const st = STATE[t.state] || STATE.done
  const x0 = Math.max(0, (begin - from) / win) * NOW_AT * 100
  const x1 = Math.min(1, (end - from) / win) * NOW_AT * 100
  const w = Math.max(0.5, x1 - x0)
  const h = thin ? 6 : 14
  return (
    <div onClick={(e) => { e.stopPropagation(); onPick(t.key) }} title={t.title}
         className={t.state === 'answering' ? 'lane-run' : undefined}
         style={{ position: 'absolute', left: `${x0}%`, width: `calc(${w}% + 4px)`, top: '50%', height: h, marginTop: -h / 2, borderRadius: h / 2, cursor: 'pointer',
                  backgroundColor: st.color, opacity: t.state === 'done' ? 0.45 : 0.95,
                  outline: sel ? `2px solid ${C.ink}` : 'none', outlineOffset: 2 }}>
      {live && t.state === 'waiting' && (
        <span className="lane-blink" style={{ position: 'absolute', right: -6, top: '50%', width: h + 8, height: h + 8, marginTop: -(h + 8) / 2, borderRadius: '50%', backgroundColor: C.warn }} />
      )}
    </div>
  )
}

export default function MapPage() {
  const [board, setBoard] = useState(null)
  const [actions, setActions] = useState(null)
  const [tasks, setTasks] = useState(null)
  const [sel, setSel] = useState(null)
  const [now, setNow] = useState(Date.now())
  const [win, setWin] = useState(3600)
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
  // the bars grow between two readings of the board
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])

  const winMs = win * 1000
  const from = now - winMs
  const lanesAll = useMemo(() => buildLanes(board, now), [board, now])
  const lanes = lanesAll.filter(l => [...l.bars, ...l.subs].some(t => span(t, now).end >= from))
  const earlier = lanesAll.length - lanes.length
  const queue = useMemo(() => buildQueue(actions, tasks), [actions, tasks])
  const items = {}
  lanesAll.forEach(l => [...l.bars, ...l.subs].forEach(t => { items[t.key] = t }))
  queue.forEach(q => { items[q.key] = q })
  const picked = sel ? items[sel] : null
  const waiting = lanesAll.filter(l => l.head.state === 'waiting' || l.subs.some(s => s.state === 'waiting'))
  const counts = { waiting: 0, answering: 0, failed: 0, done: 0 }
  lanes.forEach(l => { if (counts[l.head.state] !== undefined) counts[l.head.state] += 1 })

  const ticks = []
  const step = win <= 3600 ? 10 * 60e3 : win <= 6 * 3600 ? 3600e3 : 4 * 3600e3
  for (let t = Math.ceil(from / step) * step; t <= now; t += step) ticks.push(t)

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
    if (!t || !t.kind || ['task', 'next', 'ask'].includes(t.kind)) return t && t.kind === 'task' ? 'not done yet' : ''
    const { begin, end, live } = span(t, now)
    return live ? `running ${clock((now - begin) / 1000)}, since ${hhmm(begin)}` : `took ${clock((end - begin) / 1000)} · ended ${ago((now - end) / 1000)}`
  }
  const kindWord = (t) => ({ run: 'conversation', thread: 'conversation', job: t.agent ? 'agent' : 'background job', permit: 'proposed action', task: 'task', next: 'next-box candidate', ask: 'job report' }[t.kind] || t.kind)
  const nowPct = `${NOW_AT * 100}%`

  return (
    <>
      <Head><title>Map · BrainFoundry</title></Head>
      <style>{CSS}</style>
      <div onClick={() => setSel(null)}
           style={{ position: 'relative', height: 'calc(100vh - var(--nav-h, 52px))', backgroundColor: C.bg, color: C.ink, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '10px 14px 6px' }}>
          <span style={{ ...mono, color: C.gold, fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase' }}>map</span>
          {['waiting', 'answering', 'failed', 'done'].map(k => (
            <span key={k} style={{ ...mono, fontSize: 11, color: counts[k] ? STATE[k].color : C.dim, opacity: counts[k] ? 1 : 0.6 }}>{counts[k]} {STATE[k].word}</span>
          ))}
          {waiting.length > 0 && (
            <button onClick={(e) => { e.stopPropagation(); const l = waiting[0]; setSel(l.head.state === 'waiting' ? l.head.key : l.subs.find(s => s.state === 'waiting').key) }}
                    className="lane-blink"
                    style={{ ...mono, fontSize: 12, padding: '4px 12px', borderRadius: 8, border: `1px solid ${C.warn}`, backgroundColor: 'transparent', color: C.warn, cursor: 'pointer' }}>
              {waiting.length} waiting on you
            </button>
          )}
          <span style={{ flex: 1 }} />
          {WINDOWS.map(([s, label]) => (
            <button key={s} onClick={(e) => { e.stopPropagation(); setWin(s) }}
                    style={{ ...mono, fontSize: 11, padding: '3px 9px', borderRadius: 6, cursor: 'pointer', backgroundColor: 'transparent',
                             border: `1px solid ${win === s ? C.gold : C.line}`, color: win === s ? C.gold : C.dim }}>{label}</button>
          ))}
          <a href="/board" style={{ ...mono, fontSize: 11, color: C.dim }}>board</a>
          <a href="/talk?thread=new" style={{ ...mono, fontSize: 11, color: C.gold }}>+ new</a>
        </div>
        {note && <p style={{ ...mono, fontSize: 12, color: C.bad, margin: '0 14px 6px' }}>{note}</p>}

        {/* the time axis */}
        <div style={{ display: 'flex', borderBottom: `1px solid ${C.line}`, height: 22, flexShrink: 0 }}>
          <div style={{ width: LABEL_W, flexShrink: 0 }} />
          <div style={{ position: 'relative', flex: 1, marginRight: 14 }}>
            {ticks.map(t => (
              <span key={t} style={{ ...mono, position: 'absolute', left: `${((t - from) / winMs) * NOW_AT * 100}%`, transform: 'translateX(-50%)', top: 3, fontSize: 10, color: C.dim }}>{hhmm(t)}</span>
            ))}
            <span style={{ ...mono, position: 'absolute', left: nowPct, transform: 'translateX(-50%)', top: 3, fontSize: 10, color: C.gold, letterSpacing: '0.1em' }}>NOW</span>
            <span style={{ ...mono, position: 'absolute', left: `calc(${nowPct} + 14px)`, top: 3, fontSize: 10, color: C.dim, letterSpacing: '0.1em' }}>NEXT</span>
          </div>
        </div>

        <div style={{ position: 'relative', flex: 1, overflowY: 'auto' }}>
          {/* the now line runs through every lane */}
          <div className="lane-now" style={{ position: 'absolute', top: 0, bottom: 0, left: `calc(${LABEL_W}px + (100% - ${LABEL_W}px - 14px) * ${NOW_AT})`, width: 2, backgroundColor: C.gold, pointerEvents: 'none', zIndex: 1 }} />
          <div style={{ display: 'flex', minHeight: '100%' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              {board === false && <p style={{ fontSize: 13, color: C.dim, margin: '24px 14px' }}>The bridge is not answering at /cc/board. The map fills by itself once it does.</p>}
              {board && lanes.length === 0 && <p style={{ fontSize: 13, color: C.dim, margin: '24px 14px', maxWidth: 420 }}>Nothing ran in this window. Widen it above, or start a conversation.</p>}
              {lanes.map(l => {
                const st = STATE[l.head.state] || STATE.done
                const rows = [{ key: l.key, label: l.head.title, bars: l.bars, thin: false }, ...l.subs.map(s => ({ key: s.key, label: s.title, bars: [s], thin: true }))]
                return (
                  <div key={l.key} style={{ borderBottom: `1px solid ${C.line}`, padding: '2px 0' }}>
                    {rows.map(r => (
                      <div key={r.key} className="lane-row" onClick={(e) => { e.stopPropagation(); setSel(r.bars[r.bars.length - 1].key) }}
                           style={{ display: 'flex', alignItems: 'center', height: r.thin ? 20 : 30, cursor: 'pointer' }}>
                        <div style={{ width: LABEL_W, flexShrink: 0, padding: r.thin ? '0 8px 0 26px' : '0 8px 0 14px', boxSizing: 'border-box', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                      fontSize: r.thin ? 11 : 13, color: r.thin ? C.dim : l.head.state === 'done' ? C.dim : C.ink, ...(r.thin ? mono : {}) }} title={r.label}>
                          {!r.thin && <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', backgroundColor: st.color, marginRight: 7, verticalAlign: 'middle' }} />}
                          {r.label}
                        </div>
                        <div style={{ position: 'relative', flex: 1, height: '100%', marginRight: 14 }}>
                          {r.bars.map(t => <Bar key={t.key} t={t} now={now} from={from} win={winMs} thin={r.thin} sel={sel === t.key} onPick={setSel} />)}
                        </div>
                      </div>
                    ))}
                  </div>
                )
              })}
              {earlier > 0 && <p style={{ ...mono, fontSize: 11, color: C.dim, margin: '10px 14px' }}>{earlier} more ended before this window</p>}
            </div>
          </div>
          {/* the queue: what has not happened yet, past the now line */}
          <div style={{ position: 'absolute', top: 8, right: 14, width: `calc((100% - ${LABEL_W}px - 14px) * ${1 - NOW_AT} - 22px)`, display: 'flex', flexDirection: 'column', gap: 6, zIndex: 2 }}>
            {queue.slice(0, 30).map(q => {
              const st = STATE[q.state]
              return (
                <div key={q.key} onClick={(e) => { e.stopPropagation(); setSel(q.key) }} title={q.title}
                     style={{ padding: '5px 8px', borderRadius: 7, border: `1px ${q.kind === 'next' ? 'dashed' : 'solid'} ${sel === q.key ? C.ink : st.color}`, backgroundColor: C.bg, cursor: 'pointer',
                              fontSize: 11.5, lineHeight: 1.3, color: q.kind === 'next' ? C.dim : C.ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span style={{ ...mono, fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase', color: st.color, marginRight: 6 }}>{q.kind}</span>{q.title}
                </div>
              )
            })}
            {queue.length > 30 && <span style={{ ...mono, fontSize: 10, color: C.dim }}>+{queue.length - 30} more on the board and tasks</span>}
          </div>
        </div>

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
                  {(picked.links || []).slice(0, 4).map(lk => (
                    <a key={lk.href} href={lk.href} target={lk.kind === 'url' ? '_blank' : undefined} rel={lk.kind === 'url' ? 'noreferrer' : undefined}
                       style={{ ...mono, fontSize: 12, color: C.dim }}>{lk.label}</a>
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
