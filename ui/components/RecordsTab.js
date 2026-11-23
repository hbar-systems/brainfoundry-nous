// The records tab (A2A-2, 2026-11-23): signed records from pinned peer brains, and the owner's
// press on each. api/federation_record.py keeps them; this page only lists and presses.
// Confirm needs the exact text the sender set, typed here; decline needs "decline".
import { useEffect, useState } from 'react'

const mono = { fontFamily: 'DM Mono, monospace' }

function BodyLines({ body }) {
  const entries = Object.entries(body || {})
  if (!entries.length) return null
  return (
    <div style={{ margin: '6px 0 8px 0' }}>
      {entries.map(([k, v]) => (
        <div key={k} style={{ fontSize: '13px', color: 'var(--text)' }}>
          <span style={{ ...mono, color: 'var(--muted)', fontSize: '11px' }}>{k}</span>{' '}
          {typeof v === 'object' ? JSON.stringify(v) : String(v)}
        </div>
      ))}
    </div>
  )
}

function Press({ rec, onDone }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async (decline) => {
    setBusy(true); setErr('')
    try {
      const r = await fetch('/api/bf/v1/federation/records/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ peer: rec.from, rid: rec.rid, typed: decline ? 'decline' : typed, decline }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) setErr(d.detail || `failed (${r.status})`)
      else onDone(d.delivery || (decline ? 'declined, signed and sent' : 'confirmed, signed and sent'))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const ok = typed === rec.confirm_text && !busy
  return (
    <div style={{ marginTop: '10px' }}>
      <p style={{ ...mono, fontSize: '11px', color: 'var(--muted)', margin: '0 0 6px 0' }}>
        to confirm, type exactly: <span style={{ color: 'var(--text)' }}>{rec.confirm_text}</span>
      </p>
      <div style={{ display: 'flex', gap: '8px' }}>
        <input value={typed} onChange={e => setTyped(e.target.value)} disabled={busy} aria-label="confirm text"
          style={{ flex: 1, padding: '8px 10px', background: 'var(--surface)', border: '1px solid var(--border)',
                   borderRadius: '8px', color: 'var(--text)', fontSize: '13px', ...mono, outline: 'none' }} />
        <button onClick={() => go(false)} disabled={!ok}
          style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px',
                   background: ok ? 'var(--accent)' : 'var(--surface)', color: ok ? 'var(--bg)' : 'var(--muted)',
                   cursor: ok ? 'pointer' : 'not-allowed' }}>Confirm</button>
        <button onClick={() => go(true)} disabled={busy}
          style={{ padding: '8px 14px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px',
                   background: 'transparent', color: 'var(--muted)', cursor: 'pointer' }}>Decline</button>
      </div>
      {err && <p style={{ ...mono, fontSize: '11px', color: '#c98080', margin: '6px 0 0 0' }}>{err}</p>}
    </div>
  )
}

export default function RecordsTab({ onStatus }) {
  const [records, setRecords] = useState(null)
  const load = () => {
    fetch('/api/bf/v1/federation/records')
      .then(r => r.ok ? r.json() : null)
      .then(d => setRecords(d && Array.isArray(d.records) ? d.records : []))
      .catch(() => setRecords([]))
  }
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])
  if (records === null) return null
  const shown = records.filter(r => !r.kind.startsWith('record.') && !r.kind.startsWith('help.')).reverse() // help lives in its own tab
  if (!shown.length) {
    return (
      <p style={{ color: 'var(--muted)', fontSize: '13px', fontStyle: 'italic' }}>
        No records yet. When a pinned brain sends this brain a signed record, it waits here for your press.
      </p>
    )
  }
  return (
    <div>
      {shown.map(r => (
        <div key={r.key} style={{ padding: '16px 18px', marginBottom: '10px', borderRadius: '8px',
          background: r.answerable ? 'var(--surface2)' : 'var(--surface)',
          border: r.answerable ? '1px solid #c9a96e60' : '1px solid var(--border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ ...mono, color: 'var(--accent)', fontSize: '13px' }}>
              {r.dir === 'in' ? r.from : `→ ${r.to}`} · {r.kind}
            </span>
            <span style={{ ...mono, color: 'var(--muted)', fontSize: '11px' }}>
              {r.answer ? `${r.answer}ed` : r.receipted ? (r.dir === 'in' ? 'kept, countersigned' : 'delivered, countersigned') : `pending${r.last_error ? ': ' + r.last_error : ''}`}
            </span>
          </div>
          <BodyLines body={r.body} />
          {r.answerable && <Press rec={r} onDone={(m) => { onStatus && onStatus({ ok: true, message: m }); load() }} />}
        </div>
      ))}
    </div>
  )
}
