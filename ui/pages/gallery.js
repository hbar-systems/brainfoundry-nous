import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'
import { mergeCards, indexOfThread, step, windowIndices, slot, keyAction, wheelAction } from '../lib/gallery'

// Gallery (2026-10-09): the conversations as a deck. The front card is a whole, readable CC page;
// the one before and the one after sit behind it, offset, blurred and dimmed. Scroll, arrow keys
// ([ and ] too) or a click on a blurred neighbour slide the deck; Esc leaves.
//
// Built the way /panes is: each card is the CC page itself in an iframe (/talk?pane=1&thread=..),
// so every card is live with nothing new to keep in step: its own stream, its own state, its queue
// of waiting messages, its permission cards. A card's message nodes live in its own document, so
// sliding the deck is only a CSS transform on the card; nothing inside a conversation is remounted
// (the memoized Md and the press-to-underline code are untouched). Only the front card takes the
// pointer and the keyboard: the others are inert, a click on them brings them forward.
// At most 5 cards are mounted (front, two each side); the rest are unmounted and come back
// reloaded (a turn that was answering keeps running on the box and is followed again).
// Card geometry, ordering and the window are pure functions in ui/lib/gallery.js.

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)',
  line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)', warn: '#d4b86a',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const link = { ...mono, fontSize: '11px', color: C.dim, cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }
const FKEY = 'cc.gallery.front'
const MS = 200   // slide time; 0 under prefers-reduced-motion

let seq = 0
const mkUid = () => `g${Date.now()}-${seq++}`

export default function Gallery() {
  const [cards, setCards] = useState([])
  const [front, setFront] = useState(0)
  const [threads, setThreads] = useState([])
  const [running, setRunning] = useState({})      // thread -> { waiting } from the box
  const [states, setStates] = useState({})        // card uid -> what its page says it is doing
  const [narrow, setNarrow] = useState(false)
  const [reduced, setReduced] = useState(false)
  const [ready, setReady] = useState(false)
  const frames = useRef({})
  const srcs = useRef({})                          // uid -> the thread its frame was opened on (frozen while mounted)
  const cardsRef = useRef([]); cardsRef.current = cards
  const frontRef = useRef(0); frontRef.current = front
  const lastWheel = useRef(0)
  const wanted = useRef(null)                      // thread to bring forward once the list is in
  const stripRef = useRef(null)

  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search).get('thread')
      wanted.current = q || localStorage.getItem(FKEY) || null
    } catch {}
    try { const mq = window.matchMedia('(prefers-reduced-motion: reduce)'); setReduced(mq.matches); const f = () => setReduced(mq.matches); mq.addEventListener && mq.addEventListener('change', f) } catch {}
    const measure = () => setNarrow(window.innerWidth < 900)
    measure(); window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [])

  const loadThreads = () => fetch('/cc/threads', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
    if (!d) return
    setThreads(d.threads || [])
    const prev = cardsRef.current
    const next = mergeCards(prev, d.threads || [], mkUid)
    const cur = prev[frontRef.current]
    setCards(next)
    if (!prev.length) {
      setFront(wanted.current ? indexOfThread(next, wanted.current) : 0); setReady(true)
    } else if (cur) {
      const i = next.findIndex(c => c.uid === cur.uid)
      setFront(i < 0 ? Math.min(frontRef.current, Math.max(0, next.length - 1)) : i)
    }
  }).catch(() => {})
  const loadRuns = () => fetch('/cc/health', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(h => {
    const m = {}; ((h && h.runs) || []).forEach(r => { if (r.thread) m[r.thread] = { waiting: r.waiting || 0 } }); setRunning(m)
  }).catch(() => {})
  useEffect(() => {
    loadThreads(); loadRuns()
    const t = setInterval(() => { if (!document.hidden) { loadThreads(); loadRuns() } }, 5000)
    return () => clearInterval(t)
  }, [])

  // what each page says (thread named, state); the same messages /panes listens to
  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== window.location.origin || !e.data) return
      const src = Object.entries(frames.current).find(([, el]) => el && el.contentWindow === e.source)
      if (!src) return
      const uid = src[0]
      if (e.data.type === 'cc-pane-thread') setCards(cs => cs.map(c => (c.uid === uid && c.thread !== e.data.thread ? { ...c, thread: e.data.thread } : c)))
      else if (e.data.type === 'cc-pane-state') setStates(st => ({ ...st, [uid]: e.data }))
      else if (e.data.type === 'cc-pane-key') act(e.data.key)   // keys typed inside the front card, outside its text fields
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  const leave = () => { const c = cardsRef.current[frontRef.current]; window.location.href = c && c.thread !== 'new' ? `/talk?thread=${encodeURIComponent(c.thread)}` : '/talk' }
  const go = (i) => setFront(f => { const n = cardsRef.current.length; return Math.min(n - 1, Math.max(0, i)) })
  const move = (d) => setFront(f => step(f, d, cardsRef.current.length))
  function act(key) {
    if (key === 'Escape') { leave(); return }
    const d = keyAction(key); if (d) move(d)
  }
  useEffect(() => {
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      if (typing && e.key !== 'Escape') return
      if (e.key === 'Escape' || keyAction(e.key)) { e.preventDefault(); act(e.key) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // remember the front card; keep the strip's chip for it in view
  const frontCard = cards[front]
  useEffect(() => { if (frontCard && frontCard.thread !== 'new') { try { localStorage.setItem(FKEY, frontCard.thread) } catch {} } }, [frontCard && frontCard.thread])
  useEffect(() => {
    const el = stripRef.current && frontCard ? stripRef.current.querySelector(`[data-uid="${frontCard.uid}"]`) : null
    try { if (el) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: reduced ? 'auto' : 'smooth' }) } catch {}
  }, [frontCard && frontCard.uid, ready])

  const win = windowIndices(cards.length, front)
  // a frame opens on the card's thread as it is when it mounts, and keeps that address while mounted
  const live = new Set(win.map(i => cards[i].uid))
  Object.keys(srcs.current).forEach(u => { if (!live.has(u)) delete srcs.current[u] })
  const srcOf = (c) => (srcs.current[c.uid] = srcs.current[c.uid] || c.thread)
  // only the front frame takes focus and pointer
  useEffect(() => { Object.entries(frames.current).forEach(([uid, el]) => { try { if (el) el.inert = !(frontCard && uid === frontCard.uid) } catch {} }) })

  const titleOf = (c) => {
    if (!c.thread || c.thread === 'new') return 'new conversation'
    const th = threads.find(x => x.brain === c.thread)
    return (th && th.title) || 'untitled'
  }
  // the state of a card: its own page's word when it is mounted, the box's run list always
  const stateOf = (c) => {
    const s = (live.has(c.uid) && states[c.uid]) || {}
    const box = running[c.thread]
    if (s.waiting || (box && box.waiting > 0)) return { kind: 'waiting', color: C.warn, text: 'waits for your yes' }
    if (s.busy || box) return { kind: 'busy', color: C.gold, text: s.steps ? `answering · ${s.steps} step${s.steps === 1 ? '' : 's'}` : 'answering' }
    return { kind: 'idle', color: C.line, text: '' }
  }
  const newCard = () => {
    const c = { uid: mkUid(), thread: 'new' }
    setCards(cs => [c, ...cs]); setFront(0)
  }
  const onWheel = (e) => {
    const d = wheelAction(e, lastWheel.current, Date.now())
    if (d) { lastWheel.current = Date.now(); move(d) }
  }

  const cardW = narrow ? '94%' : 'min(920px, 78%)'
  const tr = reduced ? 'none' : `transform ${MS}ms ease, filter ${MS}ms ease, opacity ${MS}ms ease`

  return (
    <>
      <Head><title>Gallery · BrainFoundry</title></Head>
      <style>{`@keyframes gpulse { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } } @media (prefers-reduced-motion: reduce) { .gdot { animation: none !important } }`}</style>
      <div style={{ height: 'calc(100vh - var(--nav-h, 52px))', display: 'flex', flexDirection: 'column', backgroundColor: C.bg, boxSizing: 'border-box', padding: '6px 8px 8px', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 4px 6px' }}>
          <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>gallery</span>
          <span style={{ ...mono, fontSize: '11px', color: C.dim }}>{cards.length ? `${front + 1} / ${cards.length}` : ''}</span>
          <span style={{ flex: 1 }} />
          <a onClick={newCard} title="A new conversation in front" style={link}>new thread</a>
          <a href="/panes" title="Several conversations side by side" style={link}>side by side</a>
          <a href="/board" title="Mission control: one tile per run" style={link}>board</a>
          <a onClick={leave} title="Esc" style={link}>one conversation</a>
        </div>
        <div ref={stripRef} onWheel={onWheel} role="tablist" aria-label="conversations"
             style={{ display: 'flex', gap: '6px', overflowX: 'auto', padding: '0 4px 8px', scrollbarWidth: 'none' }}>
          {cards.map((c, i) => {
            const st = stateOf(c)
            return (
              <button key={c.uid} data-uid={c.uid} role="tab" aria-selected={i === front} onClick={() => go(i)} title={titleOf(c)}
                style={{ ...mono, display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0, maxWidth: '200px', fontSize: '11px', padding: '3px 9px', borderRadius: '6px', cursor: 'pointer',
                         border: `1px solid ${i === front ? C.gold : C.line}`, backgroundColor: i === front ? C.gold : 'transparent', color: i === front ? C.onAccent : C.dim }}>
                {st.kind !== 'idle' && <span className="gdot" style={{ width: '6px', height: '6px', borderRadius: '50%', flexShrink: 0, backgroundColor: i === front ? C.onAccent : st.color, animation: st.kind === 'busy' ? 'gpulse 1.2s ease-in-out infinite' : 'none' }} />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{titleOf(c)}</span>
              </button>
            )
          })}
        </div>
        <div style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
          {ready && cards.length === 0 && <p style={{ ...mono, fontSize: '12px', color: C.dim, margin: '24px' }}>no conversations yet. <a onClick={newCard} style={{ ...link, color: C.gold }}>start one</a></p>}
          {win.map(i => {
            const c = cards[i]
            const d = i - front
            const s = slot(d)
            const st = stateOf(c)
            const isFront = d === 0
            return (
              <div key={c.uid} aria-hidden={!isFront}
                   style={{ position: 'absolute', top: 0, bottom: 0, left: '50%', width: cardW, zIndex: s.z, opacity: s.opacity,
                            transform: `translateX(${-50 + s.x * 100}%) scale(${s.scale})`, transition: tr, willChange: 'transform',
                            display: 'flex', flexDirection: 'column', borderRadius: '10px', overflow: 'hidden', backgroundColor: C.bg,
                            border: `1px solid ${st.kind === 'busy' ? C.gold : st.kind === 'waiting' ? C.warn : C.line}`,
                            boxShadow: isFront ? '0 10px 40px rgba(0,0,0,0.6)' : 'none' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 10px', borderBottom: `1px solid ${C.line}`, backgroundColor: C.card, height: '28px', boxSizing: 'border-box', flexShrink: 0 }}>
                  <span className="gdot" title={st.kind === 'busy' ? 'answering' : st.kind === 'waiting' ? 'a card waits for your yes' : 'idle'}
                        style={{ width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0, backgroundColor: st.color, animation: st.kind === 'busy' ? 'gpulse 1.2s ease-in-out infinite' : 'none' }} />
                  <span style={{ flex: 1, minWidth: 0, fontSize: '12px', color: C.ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{titleOf(c)}</span>
                  {st.text && <span style={{ ...mono, fontSize: '10px', color: st.color, whiteSpace: 'nowrap' }}>{st.text}</span>}
                </div>
                <div style={{ position: 'relative', flex: 1, minHeight: 0 }}>
                  {/* the blur and the dimming are on the frame, so the last lines of the conversation stay what blurs */}
                  <iframe ref={el => { frames.current[c.uid] = el }} title={`conversation ${i + 1}`} tabIndex={isFront ? 0 : -1}
                          src={`/talk?pane=1&thread=${encodeURIComponent(srcOf(c))}`} allow="microphone; clipboard-write"
                          style={{ width: '100%', height: '100%', border: 'none', backgroundColor: C.bg, display: 'block',
                                   filter: isFront ? 'none' : `blur(${s.blur}px) brightness(${s.bright})`, transition: tr,
                                   pointerEvents: isFront ? 'auto' : 'none' }} />
                  {!isFront && <div onClick={() => go(i)} onWheel={onWheel} title={`${titleOf(c)}: bring forward`} style={{ position: 'absolute', inset: 0, cursor: 'pointer' }} />}
                </div>
              </div>
            )
          })}
        </div>
        <p style={{ ...mono, fontSize: '10px', color: C.dim, margin: '6px 4px 0', textAlign: 'center' }}>left / right or [ ] switch · scroll over the sides · click a side card · esc leaves</p>
      </div>
    </>
  )
}
