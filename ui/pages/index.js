import { useEffect, useState } from 'react'
import Link from 'next/link'

// First-run checklist — the cold-start fix. A live 3-step card on the
// dashboard: set persona → add knowledge → start a chat. Each step reflects
// real brain state and links to the right tab. Auto-hides once all three are
// done; dismissible. Replaces the old static welcome modal.
function FirstRunChecklist() {
  const [steps, setSteps] = useState(null) // { persona, knowledge, chat }
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (localStorage.getItem('brain_firstrun_dismissed')) { setDismissed(true); return }
    Promise.all([
      fetch('/api/bf/persona/status').then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/bf/documents/stats').then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch('/api/bf/sessions').then(r => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([p, d, s]) => {
      setSteps({
        persona: !!(p && p.configured),
        knowledge: !!(d && ((d.total_chunks || 0) > 0 || (d.unique_documents || 0) > 0)),
        chat: !!(s && Array.isArray(s.sessions) && s.sessions.length > 0),
      })
    })
  }, [])

  const dismiss = () => {
    if (typeof window !== 'undefined') localStorage.setItem('brain_firstrun_dismissed', '1')
    setDismissed(true)
  }

  if (dismissed || !steps) return null
  if (steps.persona && steps.knowledge && steps.chat) return null

  const rows = [
    { key: 'persona', done: steps.persona, label: 'Set your brain’s persona',
      sub: 'Who it is, how it thinks — the system prompt on every turn.', href: '/persona', cta: 'Persona' },
    { key: 'knowledge', done: steps.knowledge, label: 'Add your first knowledge',
      sub: 'Paste text or drop a file — the brain learns from what you give it.', href: '/upload', cta: 'Knowledge' },
    { key: 'chat', done: steps.chat, label: 'Start a chat',
      sub: 'Talk to your brain — it answers from your persona and knowledge.', href: '/chat', cta: 'Chat' },
  ]

  return (
    <div style={{ background: '#111', border: '1px solid #1e1e1e', borderRadius: 12, padding: 24, marginBottom: 32 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: '#e5e5e5', margin: 0 }}>Get your brain started</h2>
        <button onClick={dismiss} style={{ background: 'none', border: 'none', color: '#555', fontSize: 12, cursor: 'pointer' }}>
          Dismiss
        </button>
      </div>
      <p style={{ fontSize: 13, color: '#555', margin: '0 0 16px 0' }}>Three steps from a blank brain to a useful one.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {rows.map(r => (
          <div key={r.key} style={{ display: 'flex', alignItems: 'center', gap: 12, opacity: r.done ? 0.55 : 1 }}>
            <div style={{
              width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
              border: `1px solid ${r.done ? '#00d4aa55' : '#2a2a2a'}`,
              background: r.done ? 'rgba(0,212,170,0.12)' : 'transparent',
              color: '#00d4aa', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
            }}>{r.done ? '✓' : ''}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, color: '#e5e5e5', textDecoration: r.done ? 'line-through' : 'none' }}>{r.label}</div>
              <div style={{ fontSize: 12, color: '#555' }}>{r.sub}</div>
            </div>
            {!r.done && (
              <a href={r.href} style={{
                flexShrink: 0, fontSize: 12, fontWeight: 600, color: '#0e0c0b',
                background: '#c9a96e', borderRadius: 6, padding: '6px 14px', textDecoration: 'none',
              }}>{r.cta} &rarr;</a>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{
      backgroundColor: '#111',
      border: '1px solid #1e1e1e',
      borderRadius: '12px',
      padding: '24px',
    }}>
      <div style={{ fontSize: '12px', color: '#555', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </div>
      <div style={{ fontSize: '26px', fontWeight: '700', color: accent || '#e5e5e5', marginBottom: '4px' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: '13px', color: '#444' }}>{sub}</div>}
    </div>
  )
}

// Status badge for a retrieval architecture — live / coming / locked.
// Status badge for a retrieval architecture card.
function ArchBadge({ kind }) {
  const map = {
    active: { text: 'Active', color: '#00d4aa', bg: 'rgba(0,212,170,0.1)', border: '#00d4aa40' },
    select: { text: 'Select', color: '#888', bg: '#161616', border: '#2a2a2a' },
    coming: { text: 'Coming', color: '#888', bg: '#1a1a1a', border: '#2a2a2a' },
  }
  const s = map[kind] || map.select
  return (
    <span style={{
      fontSize: '10px', fontWeight: 600,
      textTransform: 'uppercase', letterSpacing: '0.06em',
      color: s.color, background: s.bg,
      border: `1px solid ${s.border}`,
      borderRadius: '999px', padding: '3px 8px',
      whiteSpace: 'nowrap', flexShrink: 0,
    }}>
      {s.text}
    </span>
  )
}

// The four retrieval architectures. `key` matches the backend setting; only
// `selectable` ones can be switched to. 'hybrid_routed' is described but not
// yet wired (it needs a query router) — it stays a Coming card.
const ARCHITECTURES = [
  { key: 'tiered', name: 'Tiered Retrieval', selectable: true,
    desc: 'Identity tier always on, then the thinking / projects / writing tiers, then the rest of the corpus. The default.' },
  { key: 'flat', name: 'Flat Similarity', selectable: true,
    desc: 'A single cosine-similarity sweep across the whole corpus at once, with no tier weighting.' },
  { key: 'layer_scoped', name: 'Layer-Scoped', selectable: true,
    desc: 'Retrieval restricted to a chosen subset of your memory layers.' },
  { key: 'hybrid_routed', name: 'Hybrid + Routed', selectable: false,
    desc: 'A router classifies each query, then picks the retrieval strategy turn by turn. Coming later.' },
]

// Front-page section beneath Chat and Knowledge — the brain's retrieval
// architecture (Track C3). Selecting one persists the choice (it survives
// restarts) and applies from the next chat turn.
function MindArchitecture() {
  const [active, setActive] = useState(null)
  const [layerScope, setLayerScope] = useState([])
  const [declaredLayers, setDeclaredLayers] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/bf/settings/retrieval-architecture')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        setActive(d.active)
        setLayerScope(d.layer_scope || [])
        setDeclaredLayers(d.declared_layers || [])
      })
      .catch(() => {})
  }, [])

  const post = async body => {
    setBusy(true)
    setError(null)
    try {
      const r = await fetch('/api/bf/settings/retrieval-architecture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (r.ok) {
        const d = await r.json()
        setActive(d.active)
        setLayerScope(d.layer_scope || [])
      } else {
        const e = await r.json().catch(() => ({}))
        setError(e.detail || `Failed (${r.status})`)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const selectArch = key => { if (!busy && key !== active) post({ architecture: key }) }
  const toggleLayer = name => {
    if (busy) return
    const next = layerScope.includes(name)
      ? layerScope.filter(x => x !== name)
      : [...layerScope, name]
    post({ architecture: 'layer_scoped', layer_scope: next })
  }

  return (
    <div style={{ marginBottom: '48px' }}>
      <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#e5e5e5', margin: '0 0 4px 0' }}>
        Mind Architecture
      </h2>
      <p style={{ fontSize: '13px', color: '#555', margin: '0 0 16px 0', lineHeight: 1.6 }}>
        How the brain retrieves from memory. Pick an architecture — the choice persists and applies from the next chat turn.
      </p>
      {error && (
        <div style={{
          backgroundColor: '#1a0a0a', border: '1px solid #ff6b6b30', borderRadius: '8px',
          padding: '8px 12px', marginBottom: '12px', color: '#ff6b6b', fontSize: '12px',
        }}>{error}</div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        {ARCHITECTURES.map(a => {
          const isActive = a.key === active
          const clickable = a.selectable && !isActive && !busy
          return (
            <div
              key={a.key}
              onClick={clickable ? () => selectArch(a.key) : undefined}
              style={{
                backgroundColor: '#111',
                border: `1px solid ${isActive ? '#00d4aa55' : '#1e1e1e'}`,
                borderRadius: '12px',
                padding: '24px',
                boxSizing: 'border-box',
                cursor: clickable ? 'pointer' : 'default',
                opacity: a.selectable ? 1 : 0.6,
                transition: 'border-color 0.15s ease',
              }}
              onMouseOver={clickable ? e => { e.currentTarget.style.borderColor = '#00d4aa55' } : undefined}
              onMouseOut={clickable ? e => { e.currentTarget.style.borderColor = '#1e1e1e' } : undefined}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '8px' }}>
                <div style={{ fontSize: '14px', fontWeight: '600', color: '#e5e5e5' }}>{a.name}</div>
                <ArchBadge kind={!a.selectable ? 'coming' : isActive ? 'active' : 'select'} />
              </div>
              <div style={{ fontSize: '13px', color: '#555', lineHeight: '1.6' }}>{a.desc}</div>

              {a.key === 'layer_scoped' && isActive && (
                <div style={{ marginTop: '14px' }} onClick={e => e.stopPropagation()}>
                  <div style={{ fontSize: '11px', color: '#555', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: '8px' }}>
                    Layers in scope{layerScope.length === 0 ? ' — all' : ''}
                  </div>
                  {declaredLayers.length === 0 ? (
                    <div style={{ fontSize: '12px', color: '#555', lineHeight: 1.6 }}>
                      No memory layers defined yet — Layer-Scoped behaves like Flat Similarity until you add layers in Settings.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {declaredLayers.map(name => {
                        const on = layerScope.includes(name)
                        return (
                          <button
                            key={name}
                            onClick={() => toggleLayer(name)}
                            disabled={busy}
                            style={{
                              fontSize: '11px', padding: '4px 10px', borderRadius: '999px',
                              cursor: busy ? 'wait' : 'pointer',
                              border: `1px solid ${on ? '#00d4aa55' : '#2a2a2a'}`,
                              background: on ? 'rgba(0,212,170,0.1)' : '#161616',
                              color: on ? '#00d4aa' : '#888',
                            }}
                          >{name}</button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [models, setModels] = useState([])
  const [sessionCount, setSessionCount] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(e => setError(e.message))

    fetch('/api/bf/models')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setModels(d.models || []))
      .catch(() => {})

    fetch('/api/bf/sessions')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setSessionCount((d.sessions || []).length))
      .catch(() => {})
  }, [])

  const isOnline = health && health.status !== 'error'
  const primaryModel = models.find(m => m.name && m.name.includes('claude')) || models[0]

  return (
    <div style={{ padding: '40px 32px', maxWidth: '920px', margin: '0 auto' }}>
      <div style={{ marginBottom: '40px' }}>
        <h1 style={{ fontSize: '26px', fontWeight: '700', margin: '0 0 6px 0', color: '#e5e5e5' }}>
          Console
        </h1>
        <p style={{ color: '#444', fontSize: '13px', margin: 0 }}>
          {process.env.NEXT_PUBLIC_BRAIN_NODE_ID || 'brain-node'} &middot; {process.env.NEXT_PUBLIC_BRAIN_HOST || 'localhost'}
        </p>
      </div>

      <FirstRunChecklist />

      {error && (
        <div style={{
          backgroundColor: '#1a0a0a',
          border: '1px solid #ff6b6b30',
          borderRadius: '10px',
          padding: '14px 16px',
          marginBottom: '24px',
          color: '#ff6b6b',
          fontSize: '13px',
        }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '32px' }}>
        <StatCard
          label="Brain Status"
          value={health === null ? '...' : isOnline ? 'Online' : 'Offline'}
          sub={health?.version || health?.model || ''}
          accent={health === null ? '#444' : isOnline ? '#00d4aa' : '#ff6b6b'}
        />
        <StatCard
          label="Active Model"
          value={primaryModel ? (primaryModel.name.split('/').pop().split(':')[0]) : '—'}
          sub={models.length > 1 ? `+${models.length - 1} available` : 'Anthropic API + Ollama'}
        />
        <StatCard
          label="Chat Sessions"
          value={sessionCount === null ? '...' : sessionCount}
          sub="stored in pgvector"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '48px' }}>
        {[
          { href: '/chat', label: 'Chat', desc: 'Talk to your brain. RAG-backed, session-aware, model-selectable.' },
          { href: '/docs', label: 'Knowledge', desc: 'Browse and search your ingested documents across all tiers.' },
        ].map(item => (
          <a key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
            <div
              style={{
                backgroundColor: '#111',
                border: '1px solid #1e1e1e',
                borderRadius: '12px',
                padding: '24px',
                cursor: 'pointer',
                transition: 'border-color 0.15s ease',
                height: '100%',
                boxSizing: 'border-box',
              }}
              onMouseOver={e => e.currentTarget.style.borderColor = '#667eea60'}
              onMouseOut={e => e.currentTarget.style.borderColor = '#1e1e1e'}
            >
              <div style={{ fontSize: '14px', fontWeight: '600', color: '#e5e5e5', marginBottom: '8px' }}>
                {item.label}
              </div>
              <div style={{ fontSize: '13px', color: '#555', lineHeight: '1.6' }}>
                {item.desc}
              </div>
            </div>
          </a>
        ))}
      </div>

      <MindArchitecture />

      {health && (
        <details style={{ marginTop: '8px' }}>
          <summary style={{ fontSize: '12px', color: '#333', cursor: 'pointer', userSelect: 'none' }}>
            Raw health response
          </summary>
          <pre style={{
            marginTop: '12px',
            backgroundColor: '#111',
            border: '1px solid #1e1e1e',
            borderRadius: '8px',
            padding: '16px',
            fontSize: '12px',
            color: '#666',
            overflow: 'auto',
            fontFamily: 'monospace',
            lineHeight: '1.5',
          }}>
            {JSON.stringify(health, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}
