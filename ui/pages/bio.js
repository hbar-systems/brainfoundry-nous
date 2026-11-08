import Head from 'next/head'
import React, { useEffect, useState } from 'react'

// Bio (2026-11-08): one card per brain, who it is in one read. Name, role and domain, id, model,
// key, tags and its organs (api, db, model, memory) from /api/bio, which only passes public
// /identity fields and /health status words. No money here; the economy page comes later.

const C = { ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', line: 'var(--border)', bg: 'var(--bg)', bad: '#c0605a' }
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const label = { ...mono, fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.dim, margin: '0 0 4px 0' }

const UP = new Set(['healthy', 'up', 'ok'])

function Row({ k, v }) {
  if (v == null || v === '') return null
  return (
    <div style={{ marginBottom: '14px' }}>
      <div style={label}>{k}</div>
      <div style={{ ...mono, fontSize: '13px', color: C.ink, wordBreak: 'break-all' }}>{v}</div>
    </div>
  )
}

function Organ({ name, status }) {
  const up = UP.has(String(status || '').toLowerCase())
  return (
    <span title={status || 'no answer'}
      style={{ ...mono, fontSize: '12px', fontWeight: 300, padding: '5px 12px', marginRight: '8px', marginBottom: '8px', display: 'inline-block',
               border: `1px solid ${up ? C.gold : C.line}`, color: up ? C.gold : C.bad }}>{name} {up ? 'up' : 'down'}</span>
  )
}

export default function BioPage() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    fetch('/api/bio', { cache: 'no-store' }).then(r => r.json().then(j => (r.ok ? j : Promise.reject(new Error(j.error || 'the brain did not answer')))))
      .then(setD).catch(e => setErr(String(e.message || e)))
  }, [])
  if (!d) return <div style={{ ...mono, color: C.dim, padding: '40px', fontSize: '13px' }}>{err || 'reading the bio'}</div>

  const s = d.state || {}
  return (
    <div style={{ maxWidth: '560px', margin: '0 auto', padding: '28px 22px 80px', color: C.ink, backgroundColor: C.bg, minHeight: '100vh', fontWeight: 300 }}>
      <Head><title>{d.name ? `${d.name} - bio` : 'Bio'}</title></Head>
      <div style={{ ...mono, fontSize: '11px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.gold }}>bio</div>
      <div style={{ border: `1px solid ${C.line}`, padding: '22px 22px 10px', marginTop: '14px' }}>
        <div style={{ fontSize: '26px', color: C.ink, marginBottom: '4px' }}>{d.name || 'unnamed brain'}</div>
        <div style={{ ...mono, fontSize: '12px', color: C.dim, marginBottom: '22px' }}>
          {[d.role, d.domain].filter(Boolean).join(' / ')}
          {!d.name ? <> . Name it at <a href="/persona" style={{ color: C.gold }}>/persona</a>.</> : null}
        </div>
        <Row k="brain id" v={d.brain_id} />
        <Row k="model" v={d.model} />
        <Row k="version" v={d.version} />
        <Row k="public key" v={d.public_key} />
        {d.tags.length > 0 && <div style={{ marginBottom: '14px' }}>
          <div style={label}>tags</div>
          <div style={{ ...mono, fontSize: '12px', color: C.dim }}>{d.tags.join(' . ')}</div>
        </div>}
        <div style={{ ...label, marginTop: '6px', marginBottom: '8px' }}>organs</div>
        {d.state
          ? <div><Organ name="api" status={s.api} /><Organ name="db" status={s.db} /><Organ name="model" status={s.model} /><Organ name="memory" status={s.memory} /></div>
          : <div style={{ ...mono, fontSize: '12px', color: C.bad, marginBottom: '14px' }}>health did not answer</div>}
      </div>
    </div>
  )
}
