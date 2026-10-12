import Head from 'next/head'
import { useEffect, useState } from 'react'

// Permits: the history of every permit on this brain (2026-10-12, hbar: "a place where we can see the
// historic record of all the permits, so we can inspect what was actually allowed"). Read-only, from
// the bridge (GET /cc/permits/history): permitd's append-only audit joined with who decided.
// Newest first; filter by outcome, search the text, page by 50.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim)', faint: 'var(--muted)', line: 'var(--border)', card: 'var(--surface)', gold: 'var(--accent)', ok: '#7fc99c', warn: '#d4b86a', alert: '#d49a9a' }
const tone = (d) => (d && d.startsWith('allowed') ? (d.includes('failed') ? T.warn : T.ok) : d === 'refused' ? T.alert : T.faint)
const when = (ts) => (ts ? ts.replace('T', ' ').slice(0, 19) : '')
const PAGE = 50

function Chip({ on, children, onClick }) {
  return (
    <button onClick={onClick} style={{ ...mono, fontSize: '11px', padding: '4px 10px', borderRadius: '999px', cursor: 'pointer',
      border: `1px solid ${on ? T.gold : T.line}`, background: on ? 'rgba(212,184,106,0.12)' : 'transparent', color: on ? T.ink : T.dim }}>
      {children}
    </button>
  )
}

export default function Permits() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [decision, setDecision] = useState('')
  const [q, setQ] = useState('')
  const [qLive, setQLive] = useState('')
  const [offset, setOffset] = useState(0)
  const load = async () => {
    const p = new URLSearchParams({ offset: String(offset), limit: String(PAGE) })
    if (decision) p.set('decision', decision)
    if (q) p.set('q', q)
    try {
      const r = await fetch(`/cc/permits/history?${p.toString()}`, { cache: 'no-store' })
      if (!r.ok) { setErr(`the bridge answered ${r.status}`); return }
      setData(await r.json()); setErr('')
    } catch { setErr('the bridge is not answering') }
  }
  useEffect(() => { load() }, [decision, q, offset])
  useEffect(() => { const t = setTimeout(() => { setOffset(0); setQ(qLive.trim()) }, 350); return () => clearTimeout(t) }, [qLive])
  const items = (data && data.items) || []
  const total = (data && data.total) || 0
  return (
    <div style={{ padding: '20px 24px', color: T.ink, maxWidth: '1100px' }}>
      <Head><title>Permits</title></Head>
      <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 4px 0' }}>Permits · the record</p>
      <p style={{ color: T.dim, margin: '0 0 14px 0', fontSize: '14px' }}>
        Every action the reasoner asked to take on the box or in a connected app, how it ended, and who decided. Append-only; nothing here can be edited.
      </p>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '14px' }}>
        {[['', 'all'], ['allowed', 'allowed'], ['refused', 'refused'], ['pending', 'pending']].map(([v, l]) => (
          <Chip key={l} on={decision === v} onClick={() => { setOffset(0); setDecision(v) }}>{l}</Chip>
        ))}
        <input value={qLive} onChange={(e) => setQLive(e.target.value)} placeholder="search commands and files"
          style={{ ...mono, fontSize: '12px', flex: '1 1 220px', padding: '6px 10px', borderRadius: '8px', border: `1px solid ${T.line}`, background: T.card, color: T.ink, outline: 'none' }} />
        <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{total} {total === 1 ? 'permit' : 'permits'}</span>
      </div>
      {err ? <p style={{ ...mono, color: T.alert, fontSize: '12px' }}>{err}</p> : null}
      {data && !items.length && !err ? <p style={{ color: T.dim }}>No permits match.</p> : null}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {items.map((r, i) => (
          <div key={(r.id || 'x') + i} style={{ border: `1px solid ${T.line}`, borderRadius: '10px', background: T.card, padding: '10px 12px' }}>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
              <span style={{ ...mono, fontSize: '11px', color: tone(r.decision), minWidth: '110px' }}>{r.decision}</span>
              <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{when(r.ts)}</span>
              <span style={{ ...mono, fontSize: '11px', color: T.dim }}>{r.platform === 'box' ? r.method : (r.platform || r.tool)}</span>
              <span style={{ ...mono, fontSize: '11px', color: T.faint }}>by {r.by}{r.thread ? ` · thread ${r.thread.slice(0, 8)}` : ''}</span>
            </div>
            <p style={{ ...mono, fontSize: '12px', margin: '6px 0 0 0', color: T.ink, wordBreak: 'break-word' }}>{r.summary || '(no summary recorded)'}</p>
            {r.why ? <p style={{ fontSize: '12px', margin: '4px 0 0 0', color: T.dim }}>{r.why}</p> : null}
          </div>
        ))}
      </div>
      {total > PAGE ? (
        <div style={{ display: 'flex', gap: '8px', marginTop: '14px', alignItems: 'center' }}>
          <Chip on={false} onClick={() => setOffset(Math.max(0, offset - PAGE))}>newer</Chip>
          <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{offset + 1} to {Math.min(total, offset + PAGE)} of {total}</span>
          <Chip on={false} onClick={() => { if (offset + PAGE < total) setOffset(offset + PAGE) }}>older</Chip>
        </div>
      ) : null}
      <p style={{ ...mono, fontSize: '10px', color: T.faint, marginTop: '18px' }}>
        "who decided" is recorded from 2026-10-12 on; older permits say "not recorded". Strings shaped like keys or tokens are hidden.
      </p>
    </div>
  )
}
