import { useEffect, useState } from 'react'
import Link from 'next/link'

function FirstLoginTour() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!localStorage.getItem('brain_tour_seen')) setShow(true)
  }, [])
  const dismiss = () => {
    localStorage.setItem('brain_tour_seen', '1')
    setShow(false)
  }
  if (!show) return null
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20,
    }}>
      <div style={{
        background: '#161310',
        border: '1px solid #2a2420',
        borderRadius: 12,
        maxWidth: 520,
        width: '100%',
        padding: 32,
        color: '#e8e0d5',
      }}>
        <div style={{ color: '#c9a96e', fontSize: 24, marginBottom: 8 }}>ℏ</div>
        <h2 style={{ fontFamily: 'Lora, Georgia, serif', fontSize: 24, margin: '0 0 14px 0' }}>
          Welcome to your brain.
        </h2>
        <p style={{ color: '#e8e0d5', fontSize: 14, lineHeight: 1.7, margin: '0 0 12px 0' }}>
          This isn't a chat product. It's an instance you own — running on your
          server, remembering what you teach it, answering only to you.
        </p>
        <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.7, margin: '0 0 16px 0' }}>
          Three things to do first:
        </p>
        <ol style={{ color: '#e8e0d5', fontSize: 14, lineHeight: 1.8, paddingLeft: 20, margin: '0 0 20px 0' }}>
          <li>Open <Link href="/settings" style={{ color: '#c9a96e' }}>Settings</Link> and add an API key (or skip — local Ollama works out of the box).</li>
          <li>Set up your memory layers — start blank, or pick presets.</li>
          <li>Upload something via <Link href="/upload" style={{ color: '#c9a96e' }}>Knowledge</Link>. Your brain learns from what you give it.</li>
        </ol>
        <button onClick={dismiss} style={{
          background: '#c9a96e', color: '#0e0c0b',
          border: 'none', borderRadius: 6, padding: '10px 20px',
          fontSize: 13, fontWeight: 600, cursor: 'pointer',
        }}>Got it</button>
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
      <FirstLoginTour />

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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px', marginBottom: '48px' }}>
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
