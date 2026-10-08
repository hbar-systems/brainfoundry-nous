import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// Panes: several conversations with the brain side by side, like terminal windows (2026-10-06).
//
// Each pane is the CC page itself in an iframe, opened as /talk?pane=<n>&thread=<brain id | new>
// (/talk, not /cc: Caddy sends a fresh load of /cc to the bridge),
// so every pane keeps everything the page does (streaming, cards, voice, files, remarks). A pane
// holds its own thread and never moves the box's current thread. The pane tells this page which
// thread it shows (postMessage 'cc-pane-thread'), so the layout comes back after a reload.
// The box answers up to CC_MAX_RUNS conversations at once (3 by default); a fourth pane waits.
//
// Reading space (2026-10-06, the operator at four panes: "not enough space to read"): the stream
// is the pane. Each pane has ONE header line here (number, state dot, title that renames on click,
// what it is doing, one menu); inside the frame there is only the stream and a one-line composer.
// What every pane used to repeat under its composer is shown once in this page's top bar: system
// warnings, voice, hands-free, actions that run without asking. A pane reports its own state
// ('cc-pane-state') and takes its menu's commands ('cc-pane-cmd': export, details).

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)',
  line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)', warn: '#d4b86a',
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
const link = { ...mono, fontSize: '11px', color: C.dim, cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }
const fmt = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? `${s} s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }

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
  const [running, setRunning] = useState({})       // thread -> { waiting } from the box
  const [states, setStates] = useState({})         // pane id -> what the pane says it is doing
  const [picker, setPicker] = useState(null)       // pane id whose thread list is open
  const [menu, setMenu] = useState(null)           // pane id whose menu is open
  const [renaming, setRenaming] = useState(null)   // pane id whose title is being renamed
  const [renameVal, setRenameVal] = useState('')
  const [wide, setWide] = useState(null)           // pane id shown alone in the grid; the others keep running
  const [narrow, setNarrow] = useState(false)
  const [front, setFront] = useState(0)            // the pane shown on a narrow screen
  const [health, setHealth] = useState(null)
  const [warn, setWarn] = useState([])
  const [speak, setSpeak] = useState(false)
  const [handsfree, setHandsfree] = useState(false)
  const [canTalk, setCanTalk] = useState(false)
  const [auto, setAuto] = useState([])
  const [showAuto, setShowAuto] = useState(false)
  const [, setTick] = useState(0)
  const frames = useRef({})

  useEffect(() => { setPanes(load()) }, [])
  useEffect(() => {
    if (!panes.length) return
    try { localStorage.setItem(KEY, JSON.stringify(panes.map(p => ({ thread: p.thread })))) } catch {}
  }, [panes])

  // a pane names its thread once it has one, and says what it is doing
  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== window.location.origin || !e.data) return
      const src = Object.entries(frames.current).find(([, el]) => el && el.contentWindow === e.source)
      if (!src) return
      if (e.data.type === 'cc-pane-thread') setPanes(ps => ps.map(p => (p.id === src[0] && p.thread !== e.data.thread ? { ...p, thread: e.data.thread } : p)))
      if (e.data.type === 'cc-pane-state') setStates(st => ({ ...st, [src[0]]: e.data }))
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  useEffect(() => {
    const measure = () => setNarrow(window.innerWidth < 900)
    measure(); window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])
  // the elapsed time in the title bars moves once a second while anything answers
  const anyBusy = Object.values(states).some(s => s && s.busy)
  useEffect(() => { if (!anyBusy) return; const t = setInterval(() => setTick(x => x + 1), 1000); return () => clearInterval(t) }, [anyBusy])
  // a click anywhere else closes an open menu or thread list
  useEffect(() => {
    if (!menu && !picker && !showAuto) return
    const close = () => { setMenu(null); setPicker(null); setShowAuto(false) }
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [menu, picker, showAuto])

  const loadThreads = () => fetch('/cc/threads', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
    .then(d => { if (d) setThreads(d.threads || []) }).catch(() => {})
  // the panes stay quiet about cards; this page notifies once for all of them
  const cardsSeen = useRef(0)
  const loadRuns = () => fetch('/cc/health', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
    .then(h => {
      setHealth(h || null)
      const m = {}; ((h && h.runs) || []).forEach(r => { if (r.thread) m[r.thread] = { waiting: r.waiting || 0 } }); setRunning(m)
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
  const loadAuto = () => fetch('/cc/permits', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setAuto(d.auto || []) }).catch(() => {})
  const loadWarn = async () => {
    const out = []
    try { const r = await fetch('/api/bf/admin/system'); if (r.ok) { const d = await r.json(); out.push(...(d.warnings || [])) } } catch {}
    try { const r = await fetch('/cc/system'); if (r.ok) { const d = await r.json(); out.push(...(d.warnings || [])) } } catch {}
    setWarn(out)
  }
  useEffect(() => {
    loadThreads(); loadRuns(); loadAuto(); loadWarn()
    const t = setInterval(() => { loadRuns(); loadThreads() }, 8000)
    const t2 = setInterval(() => { loadAuto(); loadWarn() }, 300000)
    try { setSpeak(localStorage.getItem('cc.speak') === '1'); setHandsfree(localStorage.getItem('cc.handsfree') === '1') } catch {}
    try { setCanTalk(!!(window.SpeechRecognition || window.webkitSpeechRecognition) || !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)) } catch {}
    return () => { clearInterval(t); clearInterval(t2) }
  }, [])
  // voice and hands-free are one choice for every pane: saved here, each pane hears the change
  const saveSpeak = (v) => { setSpeak(v); try { localStorage.setItem('cc.speak', v ? '1' : '0') } catch {} }
  const saveHandsfree = (v) => { setHandsfree(v); try { localStorage.setItem('cc.handsfree', v ? '1' : '0') } catch {} }
  const askAgain = async (a) => {
    try {
      const r = await fetch('/cc/permits/auto/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: a.platform, action_id: a.action_id }) })
      const d = await r.json().catch(() => ({})); setAuto(d.auto || [])
    } catch {}
  }

  const title = (thread) => {
    if (!thread || thread === 'new') return 'new conversation'
    const th = threads.find(x => x.brain === thread)
    return (th && th.title) || 'untitled'
  }
  const setCount = (n) => { setWide(null); setPanes(ps => (n <= ps.length ? ps.slice(0, n) : [...ps, ...Array.from({ length: n - ps.length }, () => fresh())])) }
  const open = (id, thread) => { setPanes(ps => ps.map(p => (p.id === id ? { ...p, src: thread, thread } : p))); setStates(st => ({ ...st, [id]: null })); setPicker(null); setMenu(null) }
  const swap = (from, to) => setPanes(ps => { const x = ps.findIndex(q => q.id === from), y = ps.findIndex(q => q.id === to); if (x < 0 || y < 0 || x === y) return ps; const n = ps.slice(); [n[x], n[y]] = [n[y], n[x]]; return n })
  const close = (id) => { setPanes(ps => (ps.length > 1 ? ps.filter(p => p.id !== id) : ps)); setFront(0); setMenu(null); if (wide === id) setWide(null) }
  const tell = (id, cmd) => { const el = frames.current[id]; try { if (el && el.contentWindow) el.contentWindow.postMessage({ type: 'cc-pane-cmd', cmd }, window.location.origin) } catch {} setMenu(null) }
  const startRename = (p) => { if (!p.thread || p.thread === 'new') return; setRenaming(p.id); setRenameVal(title(p.thread)); setMenu(null) }
  const finishRename = async (p) => {
    const t = renameVal.trim(); setRenaming(null)
    if (!t || t === title(p.thread)) return
    try { await fetch('/cc/threads/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brain: p.thread, title: t }) }) } catch {}
    loadThreads()
  }
  // one line of state per pane: its own, never another's
  const stateOf = (p) => {
    const s = states[p.id] || {}
    const box = running[p.thread]
    if (s.waiting || (box && box.waiting > 0)) return { kind: 'waiting', color: C.warn, text: 'waits for your yes' }
    if (s.busy || box) {
      const el = s.since ? fmt(Date.now() - s.since) : ''
      const what = s.steps ? `${s.steps} step${s.steps === 1 ? '' : 's'}` : (s.writing ? 'writing' : 'thinking')
      return { kind: 'busy', color: C.gold, text: ['answering', el, what].filter(Boolean).join(' · '), tip: s.last || '' }
    }
    return { kind: 'idle', color: C.line, text: s.lastMs ? `idle · last ${(s.lastMs / 1000).toFixed(0)} s` : '' }
  }

  const shown = narrow ? panes.slice(front, front + 1) : panes
  const visible = wide && !narrow ? shown.filter(p => p.id === wide) : shown
  const cols = visible.length <= 3 ? visible.length : 2
  const menuItem = { ...mono, display: 'block', padding: '6px 12px', fontSize: '12px', color: C.ink, cursor: 'pointer', whiteSpace: 'nowrap', borderRadius: '6px', textDecoration: 'none' }

  return (
    <>
      <Head><title>Panes · BrainFoundry</title></Head>
      <style>{`@keyframes panepulse { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } } .pane-menu a:hover { background: var(--surface); }`}</style>
      <div style={{ height: 'calc(100vh - var(--nav-h, 52px))', display: 'flex', flexDirection: 'column', backgroundColor: C.bg, boxSizing: 'border-box', padding: '6px 8px 8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 4px 6px', flexWrap: 'wrap', position: 'relative' }}>
          <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>side by side</span>
          {!narrow && [1, 2, 3, 4].map(n => <Chip key={n} on={panes.length === n} onClick={() => setCount(n)} title={`${n} pane${n > 1 ? 's' : ''}`}>{n}</Chip>)}
          {narrow && panes.map((p, i) => (
            <Chip key={p.id} on={front === i} onClick={() => setFront(i)} title={title(p.thread)}>
              {i + 1}{stateOf(p).kind !== 'idle' ? ' ·' : ''}
            </Chip>
          ))}
          {narrow && panes.length < MAX && <Chip onClick={() => { setPanes(ps => [...ps, fresh()]); setFront(panes.length) }}>+</Chip>}
          <span style={{ flex: 1 }} />
          {/* shown once for every pane: what each pane used to repeat under its composer */}
          {warn.length > 0 && <a href="/system" title={warn.join('\n')} style={{ ...link, color: C.warn }}>{warn[0]}{warn.length > 1 ? ` (+${warn.length - 1})` : ''}</a>}
          {health && health.voice && <a onClick={() => saveSpeak(!speak)} title="Read every answer aloud, in every pane" style={{ ...link, color: speak ? C.gold : C.dim }}>voice {speak ? 'on' : 'off'}{health.voice_name ? ` (${String(health.voice_name).split(' ')[0]})` : ''}</a>}
          {canTalk && <a onClick={() => saveHandsfree(!handsfree)} title="What you say sends by itself; after the answer has been spoken, listening restarts" style={{ ...link, color: handsfree ? C.gold : C.dim }}>hands-free {handsfree ? 'on' : 'off'}</a>}
          {auto.length > 0 && <a onClick={(e) => { e.stopPropagation(); setShowAuto(s => !s) }} style={link}>{auto.length} action{auto.length === 1 ? '' : 's'} run without asking</a>}
          <a href="/files" style={link}>files</a>
          <a href="/board" title="Mission control: one tile per run" style={link}>board</a>
          <a href="/talk" style={link}>one conversation</a>
          {showAuto && auto.length > 0 && (
            <div onClick={e => e.stopPropagation()} style={{ position: 'absolute', right: '4px', top: '100%', zIndex: 30, backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '8px', padding: '6px 10px', maxHeight: '50vh', overflowY: 'auto', minWidth: '320px' }}>
              {auto.map(a => (
                <div key={a.platform + a.action_id} style={{ ...mono, display: 'flex', gap: '10px', alignItems: 'baseline', padding: '3px 0', fontSize: '11px', color: C.dim }}>
                  <span style={{ flex: 1 }}>{a.platform} · {a.method || 'POST'} · {a.title || a.action_id}</span>
                  <a onClick={() => askAgain(a)} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>ask again</a>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0, display: 'grid', gap: '8px',
                      gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: 'minmax(0, 1fr)' }}>
          {shown.map((p) => {
            const i = panes.indexOf(p)
            const st = stateOf(p)
            const hidden = wide && !narrow && p.id !== wide
            return (
              <div key={p.id} style={{ display: hidden ? 'none' : 'flex', flexDirection: 'column', minHeight: 0, border: `1px solid ${st.kind === 'busy' ? C.gold : st.kind === 'waiting' ? C.warn : C.line}`, borderRadius: '10px', overflow: 'hidden', position: 'relative' }}>
                {/* the one header line: number, state, title (click renames), what it is doing, the menu */}
                <div draggable={!narrow && panes.length > 1 && renaming !== p.id}
                     onDragStart={e => { e.dataTransfer.setData('text/plain', p.id); e.dataTransfer.effectAllowed = 'move' }}
                     onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
                     onDrop={e => { e.preventDefault(); swap(e.dataTransfer.getData('text/plain'), p.id) }}
                     style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 8px 4px 10px', borderBottom: `1px solid ${C.line}`, backgroundColor: C.card, height: '28px', boxSizing: 'border-box', cursor: !narrow && panes.length > 1 ? 'grab' : 'default' }}>
                  <span style={{ ...mono, fontSize: '11px', color: C.dim }} title="Drag this bar onto another pane to swap places">{i + 1}</span>
                  <span title={st.kind === 'busy' ? 'answering' : st.kind === 'waiting' ? 'a card waits for your yes' : 'idle'}
                        style={{ width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0, backgroundColor: st.color, animation: st.kind === 'busy' ? 'panepulse 1.2s ease-in-out infinite' : 'none' }} />
                  {renaming === p.id
                    ? <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)} maxLength={80}
                             onKeyDown={e => { if (e.key === 'Enter') finishRename(p); else if (e.key === 'Escape') setRenaming(null) }} onBlur={() => finishRename(p)}
                             style={{ flex: 1, minWidth: 0, fontSize: '12px', color: C.ink, backgroundColor: 'transparent', border: 'none', borderBottom: `1px solid ${C.gold}`, outline: 'none', padding: '0 2px', fontFamily: 'inherit' }} />
                    : <a onClick={() => startRename(p)} title={p.thread === 'new' ? 'A new conversation; it gets its name from your first message' : 'Click to rename'}
                         style={{ flex: 1, minWidth: 0, fontSize: '12px', color: C.ink, cursor: p.thread === 'new' ? 'default' : 'text', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {title(p.thread)}
                      </a>}
                  {st.text && <span title={st.tip || ''} style={{ ...mono, fontSize: '10px', color: st.kind === 'idle' ? C.dim : st.color, whiteSpace: 'nowrap', flexShrink: 0 }}>{st.text}</span>}
                  <a onClick={(e) => { e.stopPropagation(); setPicker(null); setMenu(menu === p.id ? null : p.id) }} title="Threads, new thread, export, alone, details, wide" aria-label="pane menu"
                     style={{ ...mono, fontSize: '14px', lineHeight: 1, color: menu === p.id ? C.gold : C.dim, cursor: 'pointer', padding: '2px 6px', borderRadius: '6px', letterSpacing: '1px', flexShrink: 0 }}>···</a>
                </div>
                {menu === p.id && (
                  <div className="pane-menu" onClick={e => e.stopPropagation()} style={{ position: 'absolute', top: '30px', right: '6px', zIndex: 20, backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '8px', padding: '4px', minWidth: '170px', boxShadow: '0 6px 24px rgba(0,0,0,0.45)' }}>
                    <a style={menuItem} onClick={() => { setMenu(null); setPicker(p.id); loadThreads() }}>threads</a>
                    <a style={menuItem} onClick={() => open(p.id, 'new')}>new thread</a>
                    <a style={menuItem} onClick={() => tell(p.id, 'export')}>export</a>
                    {p.thread !== 'new' && <a style={menuItem} href={`/talk?thread=${encodeURIComponent(p.thread)}`} target="_top">alone</a>}
                    <a style={menuItem} onClick={() => tell(p.id, 'details')}>{(states[p.id] || {}).details ? 'hide details' : 'details'}</a>
                    {!narrow && panes.length > 1 && <a style={menuItem} onClick={() => { setWide(wide === p.id ? null : p.id); setMenu(null) }}>{wide === p.id ? 'back to side by side' : 'wide'}</a>}
                    {p.thread !== 'new' && <a style={menuItem} onClick={() => startRename(p)}>rename</a>}
                    {panes.length > 1 && <a style={{ ...menuItem, color: C.dim }} onClick={() => close(p.id)}>close this pane</a>}
                  </div>
                )}
                {picker === p.id && (
                  <div onClick={e => e.stopPropagation()} style={{ position: 'absolute', top: '30px', left: '8px', right: '8px', maxHeight: '60%', overflowY: 'auto', zIndex: 20,
                                backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '8px', padding: '4px', boxShadow: '0 6px 24px rgba(0,0,0,0.45)' }}>
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
                        src={`/talk?pane=1&thread=${encodeURIComponent(p.src)}`}
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
