// The help tab (MEMBERS-14, 2026-11-23): help requests from member brains, each a card the owner
// answers. A member pressed "Something wrong? Ask hbar" in their console; their brain signed a
// help.request (their words, the screen, the last press names, their console language) and this
// brain kept and countersigned it (api/federation_help.py). Send signs a help.answer that goes back
// through the same door and shows under the member's help button.
import { useEffect, useState } from 'react'

const mono = { fontFamily: 'DM Mono, monospace' }

export function useHelpInbox() {
  const [data, setData] = useState({ requests: [], open: 0 })
  const load = () => {
    fetch('/api/bf/v1/help/inbox', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d && Array.isArray(d.requests)) setData(d) })
      .catch(() => {})
  }
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])
  return [data, load]
}

function Answer({ req, onDone }) {
  const [words, setWords] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    if (!words.trim() || busy) return
    setBusy(true); setErr('')
    try {
      const r = await fetch('/api/bf/v1/help/answer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ peer: req.from, rid: req.rid, words: words.trim() }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) setErr(d.detail || `failed (${r.status})`)
      else onDone(d.delivery || `answer signed and sent to ${req.from}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const ok = words.trim() && !busy
  return (
    <div style={{ marginTop: '10px' }}>
      <textarea value={words} onChange={e => setWords(e.target.value)} rows={3} disabled={busy} maxLength={2000}
        placeholder="your answer, in plain words" aria-label="your answer"
        style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', background: 'var(--surface)',
                 border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--text)', fontSize: '14px',
                 fontFamily: 'inherit', outline: 'none', resize: 'vertical' }} />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px' }}>
        <button onClick={go} disabled={!ok}
          style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid var(--border)', fontSize: '13px',
                   background: ok ? 'var(--accent)' : 'var(--surface)', color: ok ? 'var(--bg)' : 'var(--muted)',
                   cursor: ok ? 'pointer' : 'not-allowed' }}>{busy ? 'sending' : 'Send'}</button>
      </div>
      {err && <p style={{ ...mono, fontSize: '11px', color: '#c98080', margin: '6px 0 0 0' }}>{err}</p>}
    </div>
  )
}

export default function HelpTab({ data, reload, onStatus }) {
  const reqs = (data && data.requests) || []
  if (!reqs.length) {
    return (
      <p style={{ color: 'var(--muted)', fontSize: '13px', fontStyle: 'italic' }}>
        No help asked yet. When a member presses &ldquo;Ask hbar&rdquo; on a brain that names this one as its helper, it lands here.
      </p>
    )
  }
  return (
    <div>
      {reqs.map(q => (
        <div key={`${q.from}/${q.rid}`} style={{ padding: '16px 18px', marginBottom: '10px', borderRadius: '8px',
          background: q.answered ? 'var(--surface)' : 'var(--surface2)',
          border: q.answered ? '1px solid var(--border)' : '1px solid #c9a96e60' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
            <span style={{ ...mono, color: 'var(--accent)', fontSize: '13px' }}>{q.from}</span>
            <span style={{ ...mono, color: 'var(--muted)', fontSize: '11px' }}>
              {q.at} · {q.answered ? (q.answer_delivered ? 'answered, delivered' : `answered, not delivered yet${q.answer_error ? ': ' + q.answer_error : ''}`) : 'waiting for you'}
            </span>
          </div>
          <p style={{ color: 'var(--text)', fontSize: '15px', margin: '8px 0', whiteSpace: 'pre-wrap' }}>{q.words}</p>
          <p style={{ ...mono, color: 'var(--muted)', fontSize: '11px', margin: 0 }}>
            screen {q.screen} · pressed {q.pressed && q.pressed.length ? q.pressed.join(', ') : 'nothing noted'} · {q.lang} · console {q.console_version}
          </p>
          {q.answered
            ? <p style={{ color: 'var(--text)', fontSize: '14px', margin: '10px 0 0 0', whiteSpace: 'pre-wrap' }}><b>you:</b> {q.answer_words}</p>
            : <Answer req={q} onDone={(msg) => { onStatus && onStatus({ ok: true, message: msg }); reload() }} />}
          {q.answered && !q.answer_delivered && (
            <button onClick={() => fetch('/api/bf/v1/help/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ peer: q.from, rid: q.rid, words: q.answer_words }) }).catch(() => {}).then(reload)}
              style={{ marginTop: '8px', padding: '6px 12px', borderRadius: '8px', border: '1px solid var(--border)',
                       background: 'transparent', color: 'var(--muted)', fontSize: '12px', cursor: 'pointer' }}>try again</button>
          )}
        </div>
      ))}
    </div>
  )
}
