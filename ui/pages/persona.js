import { useEffect, useState } from 'react'

// Persona editor — the brain's system prompt, editable. The first-chat
// onboarding card promises "keep editing the persona document"; this is where.
export default function Persona() {
  const [persona, setPersona] = useState('')
  const [original, setOriginal] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null) // { ok, message } | null

  useEffect(() => {
    fetch('/api/bf/persona')
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (d) { setPersona(d.persona || ''); setOriginal(d.persona || '') }
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
  }, [])

  const dirty = persona !== original

  const save = async () => {
    setSaving(true)
    setStatus(null)
    try {
      const r = await fetch('/api/bf/persona', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ persona }),
      })
      if (r.ok) {
        const d = await r.json()
        setOriginal(d.persona ?? persona)
        setPersona(d.persona ?? persona)
        setStatus({ ok: true, message: 'Saved. The next message uses this persona.' })
      } else {
        const e = await r.json().catch(() => ({}))
        setStatus({ ok: false, message: e.detail || `Failed (${r.status})` })
      }
    } catch (e) {
      setStatus({ ok: false, message: e.message })
    } finally {
      setSaving(false)
      setTimeout(() => setStatus(null), 7000)
    }
  }

  const line = { margin: '0 0 6px 0', lineHeight: 1.6 }

  return (
    <div style={{
      padding: '40px 32px', maxWidth: '820px', margin: '0 auto',
      color: 'var(--text)', fontFamily: 'var(--font-body)',
    }}>
      <h1 style={{ fontSize: '26px', fontWeight: 700, margin: '0 0 14px 0' }}>Persona</h1>

      <div style={{ fontSize: '14px', color: 'var(--muted)', marginBottom: '20px' }}>
        <p style={line}>This document is your brain's system prompt.</p>
        <p style={line}>It is loaded on every turn — who the brain is, how it thinks, what it knows about you.</p>
        <p style={line}>Edit it freely. Saving takes effect on the very next message.</p>
      </div>

      {!loaded ? (
        <div style={{ color: 'var(--muted)', fontSize: '14px' }}>Loading persona…</div>
      ) : (
        <>
          <textarea
            value={persona}
            onChange={e => setPersona(e.target.value)}
            spellCheck={false}
            style={{
              width: '100%', minHeight: '460px', boxSizing: 'border-box',
              padding: '16px 18px', borderRadius: '10px',
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text)', fontSize: '13px', lineHeight: 1.65,
              fontFamily: 'var(--font-mono)', resize: 'vertical', outline: 'none',
            }}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginTop: '14px' }}>
            <button
              onClick={save}
              disabled={saving || !dirty}
              style={{
                padding: '10px 22px', fontSize: '14px', fontWeight: 600,
                borderRadius: '8px', border: 'none',
                background: (saving || !dirty) ? 'var(--surface2)' : 'var(--accent)',
                color: (saving || !dirty) ? 'var(--muted)' : 'var(--bg)',
                cursor: (saving || !dirty) ? 'not-allowed' : 'pointer',
              }}
            >
              {saving ? 'Saving…' : dirty ? 'Save persona' : 'Saved'}
            </button>
            {dirty && !saving && (
              <span style={{ fontSize: '12px', color: 'var(--muted)' }}>Unsaved changes.</span>
            )}
            {status && (
              <span style={{ fontSize: '13px', color: status.ok ? '#7fc99c' : '#c98080' }}>
                {status.message}
              </span>
            )}
          </div>
        </>
      )}

      <p style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '28px', lineHeight: 1.6 }}>
        Stored on the brain in <code style={{ fontFamily: 'var(--font-mono)' }}>api/brain_persona.local.md</code> —
        gitignored, so updating the brain never overwrites your persona.
      </p>
    </div>
  )
}
