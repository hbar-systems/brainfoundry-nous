import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// Panes: several conversations with the brain side by side, like terminal windows (2026-10-06).
//
// Each pane is the CC page itself in an iframe, opened as /cc?pane=<n>&thread=<brain id | new>,
// so every pane keeps everything the page does (streaming, cards, voice, files, remarks). A pane
// holds its own thread and never moves the box's current thread. The pane tells this page which
// thread it shows (postMessage 'cc-pane-thread'), so the layout comes back after a reload.
// The box answers up to CC_MAX_RUNS conversations at once (3 by default); a fourth pane waits.

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)',
  line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const KEY = 'cc.panes'
const MAX = 4

function Chip({ children, onClick, on, title }) {
  return (
    <button onClick={onClick} title={title}
      style={{ ...mono, fontSize: '11px', padding: '3px 9px', borderRadius: '6px', cursor: 'pointer',
               border: `1px solid ${on ? C.gold : C.line}`, backgroundColor: on ? C.gold : 'transparent',
               color: on ? C.onAccent : C.dim }}>
      {children}
    </button>
  )
}

let seq = 0
const fresh = (thread = 'new') => ({ id: `p${Date.now()}-${seq++}`, src: thread, thread })

function load() {
  try {
    const raw = localStorage.getItem(KEY)
    const v = raw ? JSON.parse(raw) : null
    if (Array.isArray(v) && v.length) return v.slice(0, MAX).map(p => fresh(p.thread || 'new'))
  } catch {}
  return [fresh(), fresh()]
}

export default function Panes() {
  const [panes, setPanes] = useState([])
  const [threads, setThreads] = useState([])
  const [running, setRunning] = useState({})
  const [picker, setPicker] = useState(null)     // pane id whose thread list is open
  const [narrow, setNarrow] = useState(false)
  const [front, setFront] = useState(0)           // the pane shown on a narrow screen
  const frames = useRef({})

  useEffect(() => { setPanes(load()) }, [])
  useEffect(() => {
    if (!panes.length) return
    try { localStorage.setItem(KEY, JSON.stringify(panes.map(p => ({ thread: p.thread })))) } catch {}
  }, [panes])

  // a pane names its thread once it has one (a new conversation gets its id after the first turn)
  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== window.location.origin || !e.data || e.data.type !== 'cc-pane-thread') return
      const src = Object.entries(frames.current).find(([, el]) => el && el.contentWindow === e.source)
      if (!src) return
      setPanes(ps => ps.map(p => (p.id === src[0] && p.thread !== e.data.thread ? { ...p, thread: e.data.thread } : p)))
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  useEffect(() => {
    const measure = () => setNarrow(window.innerWidth < 900)
    measure(); window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const loadThreads = () => fetch('/cc/threads', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
    .then(d => { if (d) setThreads(d.threads || []) }).catch(() => {})
  // the panes stay quiet about cards; this page notifies once for all of them
  const cardsSeen = useRef(0)
  const loadRuns = () => fetch('/cc/health', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
    .then(h => {
      const m = {}; ((h && h.runs) || []).forEach(r => { if (r.thread) m[r.thread] = true }); setRunning(m)
      const n = (h && h.cards_waiting) || 0
      if (n > cardsSeen.current) {
        try {
          if (typeof Notification !== 'undefined') {
            if (Notification.permission === 'granted') new Notification('Your brain needs a yes', { body: n === 1 ? 'A card waits for you.' : `${n} cards wait for you.` })
            else if (Notification.permission !== 'denied') Notification.requestPermission()
          }
        } catch {}
      }
      cardsSeen.current = n
    }).catch(() => {})
  useEffect(() => {
    loadThreads(); loadRuns()
    const t = setInterval(() => { loadRuns(); loadThreads() }, 8000)
    return () => clearInterval(t)
  }, [])

  const title = (thread) => {
    if (!thread || thread === 'new') return 'new conversation'
    const th = threads.find(x => x.brain === thread)
    return (th && th.title) || 'untitled'
  }
  const setCount = (n) => setPanes(ps => (n <= ps.length ? ps.slice(0, n) : [...ps, ...Array.from({ length: n - ps.length }, () => fresh())]))
  const open = (id, thread) => { setPanes(ps => ps.map(p => (p.id === id ? { ...p, src: thread, thread } : p))); setPicker(null) }
  const close = (id) => { setPanes(ps => (ps.length > 1 ? ps.filter(p => p.id !== id) : ps)); setFront(0) }
  const shown = narrow ? panes.slice(front, front + 1) : panes
  const cols = shown.length <= 3 ? shown.length : 2

  return (
    <>
      <Head><title>Panes · BrainFoundry</title></Head>
      <div style={{ height: 'calc(100vh - var(--nav-h, 52px))', display: 'flex', flexDirection: 'column', backgroundColor: C.bg, boxSizing: 'border-box', padding: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '2px 4px 8px', flexWrap: 'wrap' }}>
          <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>side by side</span>
          {!narrow && [1, 2, 3, 4].map(n => <Chip key={n} on={panes.length === n} onClick={() => setCount(n)} title={`${n} pane${n > 1 ? 's' : ''}`}>{n}</Chip>)}
          {narrow && panes.map((p, i) => (
            <Chip key={p.id} on={front === i} onClick={() => setFront(i)} title={title(p.thread)}>
              {i + 1}{running[p.thread] ? ' ·' : ''}
            </Chip>
          ))}
          {narrow && panes.length < MAX && <Chip onClick={() => { setPanes(ps => [...ps, fresh()]); setFront(panes.length) }}>+</Chip>}
          <span style={{ flex: 1 }} />
          <a href="/cc" style={{ ...mono, fontSize: '11px', color: C.dim }}>one conversation</a>
        </div>
        <div style={{ flex: 1, minHeight: 0, display: 'grid', gap: '8px',
                      gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: 'minmax(0, 1fr)' }}>
          {shown.map((p) => {
            const i = panes.indexOf(p)
            return (
              <div key={p.id} style={{ display: 'flex', flexDirection: 'column', minHeight: 0, border: `1px solid ${running[p.thread] ? C.gold : C.line}`, borderRadius: '10px', overflow: 'hidden', position: 'relative' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 10px', borderBottom: `1px solid ${C.line}`, backgroundColor: C.card }}>
                  <span style={{ ...mono, fontSize: '11px', color: running[p.thread] ? C.gold : C.dim }}>{i + 1}</span>
                  <a onClick={() => { setPicker(picker === p.id ? null : p.id); loadThreads() }} title="Choose the conversation this pane shows"
                     style={{ flex: 1, minWidth: 0, fontSize: '12px', color: C.ink, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {title(p.thread)} <span style={{ color: C.dim }}>▾</span>
                  </a>
                  {running[p.thread] && <span style={{ ...mono, fontSize: '10px', color: C.gold }}>answering</span>}
                  <a onClick={() => open(p.id, 'new')} style={{ ...mono, fontSize: '10px', color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>new</a>
                  {p.thread !== 'new' && <a href={`/cc?thread=${encodeURIComponent(p.thread)}`} target="_top" title="This conversation alone, full width" style={{ ...mono, fontSize: '10px', color: C.dim, textDecoration: 'underline' }}>alone</a>}
                  {panes.length > 1 && <a onClick={() => close(p.id)} title="Close this pane; the conversation stays in threads" style={{ ...mono, fontSize: '12px', color: C.dim, cursor: 'pointer' }}>×</a>}
                </div>
                {picker === p.id && (
                  <div style={{ position: 'absolute', top: '32px', left: '8px', right: '8px', maxHeight: '55%', overflowY: 'auto', zIndex: 10,
                                backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '8px', padding: '4px' }}>
                    {threads.length === 0 && <p style={{ ...mono, fontSize: '11px', color: C.dim, margin: '8px' }}>no earlier conversations</p>}
                    {threads.map(th => (
                      <a key={th.brain} onClick={() => open(p.id, th.brain)}
                         style={{ display: 'flex', gap: '8px', padding: '6px 8px', borderRadius: '6px', cursor: 'pointer', fontSize: '12px',
                                  color: C.ink, backgroundColor: th.brain === p.thread ? 'var(--surface)' : 'transparent' }}>
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{th.pinned ? '· ' : ''}{th.title || 'untitled'}</span>
                        {running[th.brain] && <span style={{ ...mono, fontSize: '10px', color: C.gold }}>answering</span>}
                      </a>
                    ))}
                  </div>
                )}
                <iframe ref={el => { frames.current[p.id] = el }} key={`${p.id}:${p.src}`} title={`pane ${i + 1}`}
                        src={`/cc?pane=1&thread=${encodeURIComponent(p.src)}`}
                        allow="microphone; clipboard-write"
                        style={{ flex: 1, minHeight: 0, width: '100%', border: 'none', backgroundColor: C.bg }} />
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
