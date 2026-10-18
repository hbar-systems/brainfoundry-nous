import Head from 'next/head'
import React, { useEffect, useState } from 'react'

// Profile (2026-10-18): how the brain talks to its owner. The interview's answers waiting for a yes,
// each card showing the "How to talk to me" section it would write into the persona, and the answers
// as chips and short text lines (change one, press apply). Read from and written to the bridge
// (/cc/profile...); the bridge validates, cleans the free text and writes through the api's persona
// writer, inside the managed block only. The posture is shown as a recommendation, never set here.

const C = { ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', line: 'var(--border)', bg: 'var(--bg)', bad: '#c0605a' }
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const label = { ...mono, fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.dim, margin: '28px 0 10px 0' }

function Chip({ on, children, onClick, title }) {
  return (
    <span onClick={onClick} title={title} role="button"
      style={{ ...mono, fontSize: '12px', fontWeight: 300, padding: '5px 12px', marginRight: '8px', marginBottom: '8px', display: 'inline-block', cursor: 'pointer',
               border: `1px solid ${on ? C.gold : C.line}`, color: on ? C.gold : C.dim, backgroundColor: 'transparent' }}>{children}</span>
  )
}
function Btn({ children, onClick, primary, disabled, title }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      style={{ ...mono, fontSize: '12px', fontWeight: 300, padding: '6px 14px', marginRight: '8px', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
               border: `1px solid ${primary ? C.gold : C.line}`, backgroundColor: 'transparent', color: primary ? C.gold : C.dim }}>{children}</button>
  )
}
function Posture({ want, now }) {
  if (!want) return null
  return (
    <div style={{ ...mono, fontSize: '11px', color: C.dim, margin: '0 0 10px 0', lineHeight: 1.7 }}>
      recommended posture: <span style={{ color: C.gold }}>{want}</span>{now ? ` (now ${now})` : ''}. Apply does not change it; you set it in the <a href="/cc" style={{ color: C.gold }}>console</a> tool line, under tools, then posture.
    </div>
  )
}

export default function ProfilePage() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [ans, setAns] = useState({})

  const take = (j) => { setD(j); setAns(j.answers || {}) }
  const load = () => fetch('/cc/profile', { cache: 'no-store' }).then(r => (r.ok ? r.json() : Promise.reject(new Error('the bridge did not answer'))))
    .then(j => take(j)).catch(e => setErr(String(e.message || e)))
  useEffect(() => { load() }, [])
  const post = async (path, body) => {
    setErr('')
    try {
      const r = await fetch('/cc' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) { setErr(j.error || 'refused'); return null }
      if (j.questions) take(j)
      return j
    } catch { setErr('the bridge did not answer'); return null }
  }
  if (!d) return <div style={{ ...mono, color: C.dim, padding: '40px', fontSize: '13px' }}>{err || 'reading your profile'}</div>

  const set = (id, v) => setAns(a => { const n = { ...a, [id]: v }; if (v === '' || v == null) delete n[id]; return n })
  const want = ans.ask ? d.postures[ans.ask] : null

  return (
    <div style={{ maxWidth: '760px', margin: '0 auto', padding: '28px 22px 80px', color: C.ink, backgroundColor: C.bg, minHeight: '100vh', fontWeight: 300 }}>
      <Head><title>Profile</title></Head>
      <div style={{ ...mono, fontSize: '11px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.gold }}>profile</div>
      <p style={{ fontSize: '14px', lineHeight: 1.7, color: C.dim, margin: '10px 0 0 0' }}>
        How your brain talks to you, kept as a short section of its persona between two markers. Nothing outside that section changes.{' '}
        {d.set === null ? 'The brain did not answer just now.' : d.set ? 'A profile is set.' : 'None is set yet: ask your brain to set up how it talks to you, or answer below.'}
        {d.named === false ? ' Name your brain first (at /persona); apply waits until it has a name.' : ''}
      </p>
      {err ? <p style={{ ...mono, fontSize: '12px', color: C.bad }}>{err}</p> : null}

      {d.proposals.length > 0 && <>
        <div style={label}>waiting for your yes</div>
        {d.proposals.map(p => (
          <div key={p.id} style={{ border: `1px solid ${C.line}`, padding: '12px 14px', marginBottom: '10px' }}>
            <div style={{ ...mono, fontSize: '11px', color: C.dim }}>{p.source}</div>
            <pre style={{ ...mono, fontSize: '12px', lineHeight: 1.7, whiteSpace: 'pre-wrap', color: C.ink, margin: '8px 0 10px 0' }}>{p.persona_md}</pre>
            <Posture want={p.posture} now={d.posture} />
            <Btn primary onClick={() => post('/profile/approve', { id: p.id })}>apply</Btn>
            <Btn onClick={() => post('/profile/dismiss', { id: p.id })}>dismiss</Btn>
          </div>
        ))}
        <div style={{ ...mono, fontSize: '11px', color: C.dim }}>Applying replaces the previous profile section of your persona.</div>
      </>}

      <div style={label}>your answers</div>
      {d.questions.map(q => (
        <div key={q.id} style={{ marginBottom: '12px' }}>
          <div style={{ fontSize: '14px', color: C.ink, marginBottom: '6px' }}>{q.ask}</div>
          {q.options
            ? q.options.map(([v, w]) => <Chip key={v} on={ans[q.id] === v} onClick={() => set(q.id, ans[q.id] === v ? '' : v)}>{w}</Chip>)
            : <input value={ans[q.id] || ''} maxLength={q.max} onChange={e => set(q.id, e.target.value.slice(0, q.max))}
                style={{ ...mono, fontSize: '12px', fontWeight: 300, width: '90%', padding: '6px 10px', color: C.ink, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 0, outline: 'none' }} />}
        </div>
      ))}
      <Posture want={want} now={d.posture} />
      <Btn primary onClick={() => post('/profile/answers', { answers: ans })} disabled={Object.keys(ans).length === 0 || d.named === false}>apply answers</Btn>
      <Btn onClick={() => setAns(d.answers || {})}>revert</Btn>
    </div>
  )
}
