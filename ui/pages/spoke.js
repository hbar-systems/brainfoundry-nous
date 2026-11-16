import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'

// Spoke: your laptop, beside the conversation (SPOKE-2A, 2026-11-14; design docs/spoke.md). From the
// bridge: GET /cc/spoke/state (the laptop, its mode, the signing key's fingerprint), POST /cc/spoke/bundle
// (Make my download: a one-device network key that expires in an hour, in a zip signed by this brain),
// GET /cc/spoke/inventory (the last look, counts only, rendered by scripts/spoke/render_inventory.py),
// POST /cc/spoke/disconnect (the laptop's key line goes and it leaves this brain's network).
// The chat is the CC page itself in a pane frame; its thread is kept in localStorage ('cc.spoke.thread').
const mono = { fontFamily: 'var(--font-mono, ui-monospace, monospace)' }
const cap = { ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--text-dim)', margin: 0 }
const TKEY = 'cc.spoke.thread'

function Btn({ children, onClick, disabled, quiet, href }) {
  const st = {
    ...mono, fontSize: '12px', letterSpacing: '0.06em', padding: '9px 16px', borderRadius: '999px', cursor: disabled ? 'default' : 'pointer',
    border: '1px solid ' + (quiet ? 'var(--border)' : 'var(--text)'), background: quiet ? 'transparent' : 'var(--text)',
    color: quiet ? 'var(--text-dim)' : 'var(--bg)', opacity: disabled ? 0.45 : 1, textDecoration: 'none', display: 'inline-block',
  }
  if (href) return <a href={href} style={st}>{children}</a>
  return <button type="button" onClick={disabled ? undefined : onClick} disabled={disabled} style={st}>{children}</button>
}

function when(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

function laptopLine(st) {
  const l = st && st.status && st.status.laptop
  if (!l) return { dot: 'var(--muted)', text: 'No laptop has joined yet.' }
  if (l.state === 'online') return { dot: '#7fc99c', text: `Your laptop is here. Mode: ${st.status.mode === 'organise' ? 'organise' : 'look only'}.` }
  return { dot: 'var(--muted)', text: `Your laptop is asleep or away${l.seen ? ' since ' + when(l.seen) : ''}.` }
}

export default function Spoke() {
  const [st, setSt] = useState(null)
  const [err, setErr] = useState('')
  const [dl, setDl] = useState(null)
  const [busy, setBusy] = useState('')
  const [asking, setAsking] = useState(false)
  const [said, setSaid] = useState('')
  const [thread, setThread] = useState('new')
  const [narrow, setNarrow] = useState(false)
  const [side, setSide] = useState('laptop')
  const [invKey, setInvKey] = useState(0)
  const frame = useRef(null)

  const load = async () => {
    try {
      const r = await fetch('/cc/spoke/state', { cache: 'no-store' })
      if (!r.ok) { setErr(`the bridge answered ${r.status}`); return }
      setSt(await r.json()); setErr('')
    } catch { setErr('the bridge is not answering') }
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    try { const k = window.localStorage.getItem(TKEY); if (k) setThread(k) } catch {}
    const onMsg = (e) => {
      if (e.origin !== window.location.origin || !e.data || e.data.type !== 'cc-pane-thread') return
      if (frame.current && e.source !== frame.current.contentWindow) return
      try { window.localStorage.setItem(TKEY, e.data.thread) } catch {}
    }
    const onSize = () => setNarrow(window.innerWidth < 900)
    onSize()
    window.addEventListener('message', onMsg)
    window.addEventListener('resize', onSize)
    return () => { clearInterval(t); window.removeEventListener('message', onMsg); window.removeEventListener('resize', onSize) }
  }, [])

  const make = async () => {
    setBusy('make'); setDl(null); setSaid('')
    try {
      const r = await fetch('/cc/spoke/bundle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json()
      if (d.ok) setDl(d); else setSaid(d.error || 'no download was made')
    } catch { setSaid('the bridge is not answering') }
    setBusy('')
  }
  const disconnect = async () => {
    setBusy('leave'); setAsking(false); setSaid('')
    try {
      const r = await fetch('/cc/spoke/disconnect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const d = await r.json()
      setSaid(d.ok ? 'Disconnected. Your brain can no longer reach the laptop.' : (d.error || 'it did not answer'))
    } catch { setSaid('the bridge is not answering') }
    setBusy(''); load()
  }

  const ready = st && st.ready
  const line = laptopLine(st)
  const joined = st && st.status && st.status.laptop
  const fp = (dl && dl.fingerprint) || (st && st.fingerprint) || ''

  const laptop = (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '18px', minHeight: 0, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: line.dot, flex: '0 0 auto' }} />
        <span style={{ fontSize: '15px', fontWeight: 300 }}>{st ? (ready ? line.text : st.why) : 'Looking for your laptop...'}</span>
      </div>
      {err ? <p style={{ ...mono, fontSize: '12px', color: '#d49a9a', margin: 0 }}>{err}</p> : null}
      {ready ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
            {dl ? <Btn href={dl.url}>Download Join my brain</Btn> : <Btn onClick={make} disabled={busy === 'make'}>{busy === 'make' ? 'Making it...' : 'Make my download'}</Btn>}
            {joined && !asking ? <Btn quiet onClick={() => setAsking(true)} disabled={busy === 'leave'}>Disconnect laptop</Btn> : null}
            {asking ? (
              <span style={{ display: 'inline-flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-dim)' }}>The laptop leaves your brain's network.</span>
                <Btn onClick={disconnect}>Disconnect</Btn>
                <Btn quiet onClick={() => setAsking(false)}>Keep it</Btn>
              </span>
            ) : null}
          </div>
          {fp ? (
            <p style={{ ...mono, fontSize: '12px', color: 'var(--text-dim)', margin: 0, wordBreak: 'break-all' }}>
              Signing key {fp}{dl ? `. This link works once, until ${when(dl.expires)}.` : ''}
            </p>
          ) : null}
          {dl ? <p style={{ fontSize: '13px', color: 'var(--text-dim)', margin: 0, lineHeight: 1.5 }}>Open it in Downloads and double-click Join my brain. The window it opens shows the same key; if it does not, close it.</p> : null}
          {said ? <p style={{ fontSize: '13px', margin: 0 }}>{said}</p> : null}
        </div>
      ) : null}
      {ready ? (
        <div style={{ flex: 1, minHeight: '360px', display: 'flex', flexDirection: 'column', border: '1px solid var(--border)', borderRadius: '12px', overflow: 'hidden', background: 'var(--surface)' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
            <p style={cap}>What is on it</p>
            <span style={{ ...mono, fontSize: '11px', color: 'var(--muted)' }}>{st.status && st.status.inventory ? 'looked ' + when(st.status.inventory) : 'not looked yet'}</span>
            {st.inventory ? <span onClick={() => setInvKey(invKey + 1)} style={{ ...mono, fontSize: '11px', color: 'var(--text-dim)', marginLeft: 'auto', cursor: 'pointer' }}>refresh</span> : null}
          </div>
          {st.inventory ? (
            <iframe key={invKey} src="/cc/spoke/inventory" title="What is on your laptop" sandbox="allow-scripts" style={{ flex: 1, border: 0, width: '100%', background: 'var(--bg)' }} />
          ) : (
            <p style={{ padding: '18px 16px', margin: 0, fontSize: '14px', color: 'var(--text-dim)', lineHeight: 1.6 }}>
              When your laptop has joined, ask in the conversation: "look at my laptop". It counts files by kind, size and age. No names leave the laptop, nothing is opened, nothing moves.
            </p>
          )}
        </div>
      ) : null}
    </section>
  )
  const chat = (
    <iframe ref={frame} src={`/talk?pane=1&thread=${encodeURIComponent(thread)}`} title="The conversation"
      style={{ width: '100%', height: '100%', border: '1px solid var(--border)', borderRadius: '12px', background: 'var(--bg)' }} />
  )

  return (
    <>
      <Head><title>Spoke · your laptop</title></Head>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '560px', color: 'var(--text)', padding: narrow ? '14px' : '18px 24px', boxSizing: 'border-box', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', flexWrap: 'wrap' }}>
          <p style={cap}>Spoke · your laptop</p>
          <span style={{ fontSize: '13px', color: 'var(--text-dim)' }}>Your brain looks first and moves nothing without a plan you approve. It never deletes.</span>
        </div>
        {narrow ? (
          <div style={{ display: 'flex', gap: '8px' }}>
            {[['laptop', 'Laptop'], ['chat', 'Conversation']].map(([k, l]) => (
              <span key={k} onClick={() => setSide(k)} style={{ ...mono, fontSize: '11px', padding: '5px 12px', borderRadius: '999px', cursor: 'pointer',
                border: '1px solid ' + (side === k ? 'var(--text)' : 'var(--border)'), color: side === k ? 'var(--text)' : 'var(--text-dim)' }}>{l}</span>
            ))}
          </div>
        ) : null}
        <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: narrow ? '1fr' : 'minmax(380px, 5fr) 6fr', gap: '18px' }}>
          {!narrow || side === 'laptop' ? <div style={{ minHeight: 0, overflow: 'auto' }}>{laptop}</div> : null}
          {!narrow || side === 'chat' ? <div style={{ minHeight: narrow ? '520px' : 0 }}>{chat}</div> : null}
        </div>
      </div>
    </>
  )
}
