import { useEffect, useState } from 'react'

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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '32px' }}>
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '48px' }}>
        {[
          { href: '/chat', label: 'Chat', desc: 'Talk to your brain. RAG-backed, session-aware, model-selectable.' },
          { href: '/docs', label: 'Knowledge', desc: 'Browse and search your ingested documents across all tiers.' },
          { href: '/kernel', label: 'Kernel', desc: 'Issue governance commands. PROPOSE / CONFIRM flow.' },
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
