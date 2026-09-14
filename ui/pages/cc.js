import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'

// CC — a plain chat surface backed by a reasoner running on the brain's own box.
//
// The page talks to a small bridge served on the SAME origin as the console at
// /cc/* (see hbar.world ops/2026-09-14_claude-code-tab/cc-bridge.py). The
// bridge runs one headless reasoner turn per message inside the brain repo,
// keeps the conversation id, and answers as the brain. Nothing here names a
// vendor; the person is talking to their brain.
//
// The tab is opt-in per brain: BRAIN_CC_ENABLED=true in .env makes the api
// list the `_cc` tab (api/apps.py). Without the bridge the page says so.

const C = {
  ink: '#e8e0d5', dim: '#8b7d6e', faint: '#6b5f52', gold: '#c9a96e',
  card: '#1c1814', line: '#c9a96e40', me: '#231d18', brain: '#15120f',
}

export default function CC() {
  const [turns, setTurns] = useState([])       // { who: 'me' | 'brain', text, ms }
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)   // null = unknown, false = down, object = ok
  const endRef = useRef(null)
  const boxRef = useRef(null)

  useEffect(() => {
    fetch('/cc/health', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setHealth)
      .catch(() => setHealth(false))
  }, [])

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, busy])

  async function send() {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    setTurns(t => [...t, { who: 'me', text }])
    setBusy(true)
    try {
      const r = await fetch('/cc/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      const data = await r.json().catch(() => ({}))
      const reply = data.reply || (r.ok ? '(no answer)' : `The bridge answered ${r.status}.`)
      setTurns(t => [...t, { who: 'brain', text: reply, ms: data.ms, error: !!data.error }])
    } catch (e) {
      setTurns(t => [...t, { who: 'brain', text: 'The bridge did not answer. Is cc-bridge running on the box?', error: true }])
    } finally {
      setBusy(false)
      if (boxRef.current) boxRef.current.focus()
    }
  }

  async function fresh() {
    if (busy) return
    try { await fetch('/cc/new', { method: 'POST' }) } catch {}
    setTurns([])
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <>
      <Head><title>CC · BrainFoundry</title></Head>
      <div style={{ padding: '28px 32px 20px', maxWidth: '860px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif',
                    display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 60px)' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
          <div>
            <p style={{ color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', margin: '0 0 4px 0' }}>
              cc · reasoning from inside the brain
            </p>
            <h1 style={{ fontSize: '26px', color: C.ink, margin: 0, fontWeight: 600 }}>Talk to your brain</h1>
          </div>
          <button onClick={fresh} disabled={busy} title="Start a new conversation"
                  style={{ background: 'transparent', color: C.dim, border: `1px solid ${C.line}`, borderRadius: '8px',
                           padding: '6px 12px', fontSize: '12px', cursor: busy ? 'default' : 'pointer', fontFamily: 'DM Mono, monospace' }}>
            new thread
          </button>
        </div>

        {health === false && (
          <div style={{ padding: '12px 16px', backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '10px', marginBottom: '14px' }}>
            <p style={{ margin: 0, color: C.dim, fontSize: '13px', lineHeight: 1.6 }}>
              The reasoner bridge is not answering at <code>/cc/health</code> on this console.
              The tab is on, the box side is not. Install the bridge on the box (operator runbook), then reload.
            </p>
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 2px' }}>
          {turns.length === 0 && (
            <p style={{ color: C.faint, fontSize: '14px', lineHeight: 1.7, margin: '24px 0' }}>
              This surface reasons over the brain&apos;s own files on its own server. Ask what the brain knows about itself,
              what changed recently, or what a document says. It reads; it does not change anything from here.
              {health && health.session ? ' The previous thread continues.' : ''}
            </p>
          )}
          {turns.map((t, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: t.who === 'me' ? 'flex-end' : 'flex-start', margin: '8px 0' }}>
              <div style={{
                maxWidth: '78%', padding: '10px 14px', borderRadius: '12px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                backgroundColor: t.who === 'me' ? C.me : C.brain,
                border: `1px solid ${t.error ? '#7a3a2e' : C.line}`,
                color: C.ink, fontSize: '14px', lineHeight: 1.6,
              }}>
                {t.text}
                {t.who === 'brain' && typeof t.ms === 'number' && (
                  <div style={{ color: C.faint, fontSize: '11px', marginTop: '6px', fontFamily: 'DM Mono, monospace' }}>{(t.ms / 1000).toFixed(1)} s</div>
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '8px 0' }}>thinking on the box…</div>
          )}
          <div ref={endRef} />
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', marginTop: '12px' }}>
          <textarea
            ref={boxRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={onKey}
            rows={2}
            placeholder={busy ? 'one turn at a time' : 'Ask your brain. Enter sends, Shift+Enter for a new line.'}
            disabled={busy}
            style={{ flex: 1, resize: 'vertical', minHeight: '48px', padding: '10px 12px', borderRadius: '10px',
                     backgroundColor: C.card, color: C.ink, border: `1px solid ${C.line}`, fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5, outline: 'none' }}
          />
          <button onClick={send} disabled={busy || !draft.trim()}
                  style={{ padding: '12px 18px', borderRadius: '10px', border: 'none', cursor: busy ? 'default' : 'pointer',
                           backgroundColor: busy || !draft.trim() ? '#3a3520' : C.gold, color: busy || !draft.trim() ? C.dim : '#141210',
                           fontWeight: 600, fontSize: '14px', fontFamily: 'inherit' }}>
            send
          </button>
        </div>
        <p style={{ color: C.faint, fontSize: '11px', margin: '10px 0 0 0', fontFamily: 'DM Mono, monospace' }}>
          {health && health.session ? 'thread continues across reloads' : 'a new thread starts with your first message'}
          {health && health.tools ? ` · read-only: ${health.tools}` : ''}
        </p>
      </div>
    </>
  )
}
