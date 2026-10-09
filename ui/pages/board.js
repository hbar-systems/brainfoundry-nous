import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// Mission control: one board for all running work (2026-10-06).
//
// The operator's idea of 2026-10-05: "displays (like cmux except non-terminal style) for
// multi-parallel working processes". Side by side fits four conversations and shows chrome;
// this shows state. One tile per run, assembled by the bridge (GET /cc/board) from what it
// already tracks: every conversation that is answering, waiting on you, or finished in the
// last 24 h, the subagents a turn fanned out to, background jobs, and permits still waiting.
// A tile: the task in one line, the state as a colour and a word, elapsed time, cost so far,
// the last meaningful line, and any approval card with its buttons. A click opens the
// conversation alone. Order: waiting on you, failed (until dismissed), answering, done.
// Updates: one light request every three seconds, paused while the tab is hidden.

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
}
const link = { ...mono, fontSize: '11px', color: C.dim, cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }

const clock = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` }
const took = (s) => { s = Math.max(0, Math.round(s)); return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` }
const ago = (s) => { s = Math.max(0, Math.round(s)); return s < 90 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago` }
const kTok = (n) => { n = Number(n) || 0; return n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n) }

function Btn({ children, onClick, primary, disabled, title }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      style={{ ...mono, fontSize: '12px', padding: '6px 14px', borderRadius: '8px', cursor: disabled ? 'default' : 'pointer',
               border: primary ? 'none' : `1px solid ${C.line}`, backgroundColor: primary ? C.gold : 'transparent',
               color: primary ? C.onAccent : C.dim, fontWeight: primary ? 600 : 400, opacity: disabled ? 0.5 : 1 }}>
      {children}
    </button>
  )
}

function Tile({ t, now, onDecide, onDismiss, busyCard }) {
  const st = STATE[t.state] || STATE.done
  const live = t.state === 'answering' || t.state === 'waiting'
  // a live tile's clock moves between two readings of the board
  const elapsed = live && t.started ? Math.max(t.elapsed_s || 0, (now - Date.parse(t.started)) / 1000) : (t.elapsed_s || 0)
  const meta = []
  if (t.kind === 'job') meta.push('background job')
  if (t.kind === 'permit') meta.push('proposed action')
  if (t.steps) meta.push(`${t.steps} step${t.steps === 1 ? '' : 's'}`)
  if (t.agents) meta.push(`${t.agents} subagent${t.agents === 1 ? '' : 's'}`)
  if (t.cost !== null && t.cost !== undefined) meta.push(`$${Number(t.cost).toFixed(2)} today`)
  else if (t.tok) meta.push(`${kTok(t.tok)} tokens today`)
  if (t.via && t.via !== 'page') meta.push(`from ${t.via}`)
  const open = () => { if (t.href) window.location.href = t.href }
  return (
    <div onClick={open} role={t.href ? 'link' : undefined}
      style={{ display: 'flex', flexDirection: 'column', gap: '6px', padding: '12px 14px', borderRadius: '12px', backgroundColor: C.card,
               border: `1px solid ${t.state === 'waiting' ? C.warn : t.state === 'failed' ? C.bad : C.line}`, borderLeft: `3px solid ${st.color}`,
               cursor: t.href ? 'pointer' : 'default', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: st.color, flexShrink: 0, animation: t.state === 'answering' ? 'boardpulse 1.2s ease-in-out infinite' : 'none' }} />
        <span style={{ ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: st.color }}>{t.word || st.word}</span>
        <span style={{ flex: 1 }} />
        <span style={{ ...mono, fontSize: '11px', color: C.dim, whiteSpace: 'nowrap' }}>
          {live ? clock(elapsed) : [t.elapsed_s ? `took ${took(t.elapsed_s)}` : '', t.ago_s !== null && t.ago_s !== undefined ? ago(t.ago_s) : ''].filter(Boolean).join(' · ')}
        </span>
        {!live && <a onClick={(e) => { e.stopPropagation(); onDismiss(t.key) }} title="Take this tile off the board; the conversation stays in threads" aria-label="dismiss"
                     style={{ ...mono, fontSize: '14px', lineHeight: 1, color: C.dim, cursor: 'pointer', padding: '0 2px' }}>×</a>}
      </div>
      <div style={{ fontSize: '14px', color: C.ink, lineHeight: 1.35, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={t.title}>{t.title}</div>
      {meta.length > 0 && <div style={{ ...mono, fontSize: '11px', color: C.dim }}>{meta.join(' · ')}</div>}
      {t.last && <div style={{ fontSize: '13px', lineHeight: 1.45, color: t.state === 'failed' ? C.bad : C.dim, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', wordBreak: 'break-word' }}>{t.last}</div>}
      {(t.cards || []).map(c => (
        <div key={c.id} onClick={e => e.stopPropagation()} style={{ border: `1px solid ${C.warn}`, borderRadius: '10px', padding: '8px 10px', backgroundColor: C.bg, cursor: 'default' }}>
          <div style={{ ...mono, fontSize: '12px', lineHeight: 1.45, color: C.ink, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', wordBreak: 'break-word' }}>{c.summary || 'an action waits for your yes'}</div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
            <Btn primary disabled={busyCard === c.id} onClick={() => onDecide(c.id, 'approve')}>{c.platform === 'box' ? 'Allow' : 'Send'}</Btn>
            <Btn disabled={busyCard === c.id} onClick={() => onDecide(c.id, 'deny')}>{c.platform === 'box' ? 'Refuse' : 'Cancel'}</Btn>
            <span style={{ ...mono, fontSize: '10px', color: C.dim }}>permit {String(c.id || '').slice(-6)}</span>
          </div>
        </div>
      ))}
      {(t.links || []).length > 0 && (
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          {t.links.map(l => (
            <a key={l.href} href={l.href} target={l.kind === 'url' ? '_blank' : undefined} rel={l.kind === 'url' ? 'noreferrer' : undefined}
               onClick={e => e.stopPropagation()} title={l.path || l.href} style={{ ...link, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.label}</a>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Board() {
  const [board, setBoard] = useState(null)        // null: not read yet; false: the bridge did not answer
  const [now, setNow] = useState(Date.now())
  const [busyCard, setBusyCard] = useState(null)
  const [only, setOnly] = useState(null)          // a state shown alone, chosen from the counts
  const [note, setNote] = useState(null)
  const timer = useRef(null)

  const load = () => fetch('/cc/board', { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(d => { setBoard(d && Array.isArray(d.tiles) ? d : false); setNow(Date.now()) })
    .catch(() => setBoard(b => (b ? b : false)))

  // one light request every three seconds, none while the tab is hidden
  useEffect(() => {
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])

  const decide = async (id, action) => {
    setBusyCard(id); setNote(null)
    try {
      const r = await fetch(`/cc/permits/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.ok === false) setNote(d.error || `the bridge answered ${r.status}`)
    } catch { setNote('the bridge did not answer') }
    setBusyCard(null); load()
  }
  const dismiss = async (key) => {
    setBoard(b => (b ? { ...b, tiles: b.tiles.filter(t => t.key !== key) } : b))
    try { await fetch('/cc/board/dismiss', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) }) } catch {}
    load()
  }

  const tiles = (board && board.tiles) || []
  const shown = only ? tiles.filter(t => t.state === only) : tiles
  const counts = (board && board.counts) || {}
  return (
    <>
      <Head><title>Board · BrainFoundry</title></Head>
      <style>{`@keyframes boardpulse { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } }`}</style>
      <div style={{ minHeight: 'calc(100vh - var(--nav-h, 52px))', backgroundColor: C.bg, boxSizing: 'border-box', padding: '10px 12px 40px', color: C.ink }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 2px 10px', flexWrap: 'wrap' }}>
          <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>mission control</span>
          {['waiting', 'failed', 'answering', 'done'].map(k => (
            <button key={k} onClick={() => setOnly(only === k ? null : k)} title={only === k ? 'Show every tile' : `Show only: ${STATE[k].word}`}
              style={{ ...mono, fontSize: '11px', padding: '3px 9px', borderRadius: '6px', cursor: 'pointer', border: `1px solid ${only === k ? STATE[k].color : C.line}`,
                       backgroundColor: 'transparent', color: (counts[k] || 0) > 0 ? STATE[k].color : C.dim, opacity: (counts[k] || 0) > 0 || only === k ? 1 : 0.6 }}>
              {counts[k] || 0} {STATE[k].word}
            </button>
          ))}
          <span style={{ flex: 1 }} />
          {board && board.max_runs ? <span style={{ ...mono, fontSize: '11px', color: C.dim }}>up to {board.max_runs} answer at once</span> : null}
          <a href="/panes" style={link}>side by side</a>
          <a href="/gallery" style={link}>gallery</a>
          <a href="/talk" style={link}>one conversation</a>
          <a href="/files" style={link}>files</a>
        </div>
        {note && <p style={{ ...mono, fontSize: '12px', color: C.bad, margin: '0 2px 10px' }}>{note}</p>}
        {board === false && <p style={{ fontSize: '13px', color: C.dim, margin: '24px 2px' }}>The bridge is not answering at /cc/board. The board fills by itself once it does.</p>}
        {board && shown.length === 0 && (
          <p style={{ fontSize: '14px', color: C.dim, lineHeight: 1.7, margin: '24px 2px', maxWidth: '640px' }}>
            {only ? `Nothing is ${STATE[only].word} right now.` : 'Nothing has run in the last day. Every conversation you start here, side by side or from Telegram appears as a tile, with background jobs and anything that waits for your yes.'}
          </p>
        )}
        <div style={{ display: 'grid', gap: '10px', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', alignItems: 'start' }}>
          {shown.map(t => <Tile key={t.key} t={t} now={now} onDecide={decide} onDismiss={dismiss} busyCard={busyCard} />)}
        </div>
      </div>
    </>
  )
}
