import Head from 'next/head'
import { useEffect, useState } from 'react'

export default function Federation() {
  const [tab, setTab] = useState('inbox') // 'inbox' | 'outbox' | 'compose'
  const [inbox, setInbox] = useState([])
  const [outbox, setOutbox] = useState([])
  const [composeTo, setComposeTo] = useState('')
  const [composeMsg, setComposeMsg] = useState('')
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState(null) // {ok, message}

  const fetchInbox = () => {
    fetch('/api/bf/v1/federation/dm/inbox')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Array.isArray(d.messages)) setInbox(d.messages) })
      .catch(() => {})
  }
  const fetchOutbox = () => {
    fetch('/api/bf/v1/federation/dm/outbox')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Array.isArray(d.messages)) setOutbox(d.messages) })
      .catch(() => {})
  }

  useEffect(() => {
    fetchInbox()
    fetchOutbox()
    const t = setInterval(() => { fetchInbox(); fetchOutbox() }, 30000)
    return () => clearInterval(t)
  }, [])

  const sendDM = async () => {
    if (!composeTo.trim() || !composeMsg.trim() || sending) return
    setSending(true)
    setStatus(null)
    try {
      const r = await fetch('/api/bf/v1/federation/dm/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: composeTo.trim(), message: composeMsg.trim() }),
      })
      const data = await r.json()
      if (r.ok && data.delivered) {
        setStatus({ ok: true, message: `Delivered to ${composeTo} (id ${data.id})` })
        setComposeTo('')
        setComposeMsg('')
        fetchOutbox()
      } else if (r.ok) {
        setStatus({ ok: false, message: `Stored but not delivered: ${data.error || `code ${data.delivery_code}`}` })
        fetchOutbox()
      } else {
        setStatus({ ok: false, message: data.detail || `Failed (${r.status})` })
      }
    } catch (e) {
      setStatus({ ok: false, message: e.message })
    } finally {
      setSending(false)
      setTimeout(() => setStatus(null), 8000)
    }
  }

  const markRead = async (id) => {
    await fetch(`/api/bf/v1/federation/dm/inbox/${id}/read`, { method: 'POST' }).catch(() => {})
    fetchInbox()
  }

  const fmtTime = (iso) => {
    if (!iso) return ''
    const d = new Date(iso)
    const diff = Math.floor((Date.now() - d.getTime()) / 60000)
    if (diff < 1) return 'just now'
    if (diff < 60) return `${diff}m ago`
    if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
    return d.toLocaleDateString()
  }

  return (
    <>
      <Head><title>Federation · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '900px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>

        <p style={{ color: '#c9a96e', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', margin: '0 0 6px 0' }}>
          brainfoundry-nous · federation
        </p>
        <h1 style={{ fontSize: '32px', color: '#e8e0d5', margin: '0 0 6px 0', fontWeight: 600 }}>
          Federation
        </h1>
        <p style={{ color: '#8b7d6e', fontSize: '14px', margin: '0 0 28px 0' }}>
          Direct messages with other brains. Each message is signed by your brain&rsquo;s private key and verified by the recipient.
        </p>

        {/* Tab nav */}
        <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid #2a2420', marginBottom: '24px' }}>
          {['inbox', 'outbox', 'compose'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: '10px 16px',
                background: 'transparent',
                color: tab === t ? '#e8e0d5' : '#6b5f52',
                border: 'none',
                borderBottom: tab === t ? '2px solid #c9a96e' : '2px solid transparent',
                cursor: 'pointer',
                fontSize: '13px',
                fontFamily: 'DM Mono, monospace',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                marginBottom: '-1px',
              }}
            >
              {t}{t === 'inbox' && inbox.filter(m => !m.read_at).length > 0 ? ` (${inbox.filter(m => !m.read_at).length})` : ''}
            </button>
          ))}
        </div>

        {/* Status banner */}
        {status && (
          <div style={{
            padding: '10px 14px',
            backgroundColor: status.ok ? '#1e3a26' : '#3a1e1e',
            color: status.ok ? '#7fc99c' : '#c98080',
            fontSize: '12px',
            fontFamily: 'DM Mono, monospace',
            borderRadius: '6px',
            marginBottom: '20px',
          }}>
            {status.message}
          </div>
        )}

        {/* Inbox */}
        {tab === 'inbox' && (
          <div>
            {inbox.length === 0 && (
              <p style={{ color: '#6b5f52', fontSize: '13px', fontStyle: 'italic' }}>
                No messages yet. When another brain DMs you, it appears here.
              </p>
            )}
            {inbox.map(m => (
              <div
                key={m.id}
                onClick={() => !m.read_at && markRead(m.id)}
                style={{
                  padding: '16px 18px',
                  marginBottom: '10px',
                  background: m.read_at ? '#161310' : '#1c1814',
                  border: m.read_at ? '1px solid #2a2420' : '1px solid #c9a96e60',
                  borderRadius: '8px',
                  cursor: !m.read_at ? 'pointer' : 'default',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px' }}>
                  <span style={{ color: '#c9a96e', fontFamily: 'DM Mono, monospace', fontSize: '13px' }}>{m.from_brain}</span>
                  <span style={{ color: '#6b5f52', fontFamily: 'DM Mono, monospace', fontSize: '11px' }}>{fmtTime(m.received_at)}</span>
                </div>
                <p style={{ color: '#e8e0d5', fontSize: '14px', margin: '0 0 8px 0', whiteSpace: 'pre-wrap' }}>{m.message}</p>
                <p style={{ color: '#4a3f36', fontFamily: 'DM Mono, monospace', fontSize: '10px', margin: 0 }}>
                  pubkey {m.from_pubkey.slice(0, 12)}...{m.from_pubkey.slice(-6)} · sig verified
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Outbox */}
        {tab === 'outbox' && (
          <div>
            {outbox.length === 0 && (
              <p style={{ color: '#6b5f52', fontSize: '13px', fontStyle: 'italic' }}>
                No sent DMs yet. Switch to Compose to send one.
              </p>
            )}
            {outbox.map(m => (
              <div key={m.id} style={{
                padding: '16px 18px',
                marginBottom: '10px',
                background: '#161310',
                border: '1px solid #2a2420',
                borderRadius: '8px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px' }}>
                  <span style={{ color: '#c9a96e', fontFamily: 'DM Mono, monospace', fontSize: '13px' }}>→ {m.to_brain}</span>
                  <span style={{ color: '#6b5f52', fontFamily: 'DM Mono, monospace', fontSize: '11px' }}>{fmtTime(m.sent_at)}</span>
                </div>
                <p style={{ color: '#e8e0d5', fontSize: '14px', margin: '0 0 8px 0', whiteSpace: 'pre-wrap' }}>{m.message}</p>
                <p style={{
                  color: m.delivered ? '#7fc99c' : '#c98080',
                  fontFamily: 'DM Mono, monospace',
                  fontSize: '10px',
                  margin: 0,
                }}>
                  {m.delivered ? `delivered (${m.delivery_code})` : `not delivered: ${m.delivery_err || `code ${m.delivery_code}`}`}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Compose */}
        {tab === 'compose' && (
          <div>
            <p style={{ color: '#6b5f52', fontSize: '12px', marginBottom: '14px', fontStyle: 'italic' }}>
              Recipient is a brain handle (e.g. <code>yury</code>, <code>nous</code>). Their brain at <code>&lt;handle&gt;.brainfoundry.ai</code> must be online to receive.
            </p>
            <input
              type="text"
              value={composeTo}
              onChange={e => setComposeTo(e.target.value.toLowerCase())}
              placeholder="recipient handle"
              disabled={sending}
              style={{
                width: '100%',
                padding: '12px 14px',
                background: '#161310',
                border: '1px solid #2a2420',
                borderRadius: '8px',
                color: '#e8e0d5',
                fontSize: '14px',
                fontFamily: 'DM Mono, monospace',
                marginBottom: '12px',
                outline: 'none',
              }}
            />
            <textarea
              value={composeMsg}
              onChange={e => setComposeMsg(e.target.value)}
              placeholder="message..."
              disabled={sending}
              rows={6}
              style={{
                width: '100%',
                padding: '12px 14px',
                background: '#161310',
                border: '1px solid #2a2420',
                borderRadius: '8px',
                color: '#e8e0d5',
                fontSize: '14px',
                fontFamily: 'inherit',
                outline: 'none',
                resize: 'vertical',
                marginBottom: '12px',
              }}
            />
            <button
              onClick={sendDM}
              disabled={!composeTo.trim() || !composeMsg.trim() || sending}
              style={{
                padding: '10px 18px',
                background: (composeTo.trim() && composeMsg.trim() && !sending) ? '#c9a96e' : '#161310',
                color: (composeTo.trim() && composeMsg.trim() && !sending) ? '#0e0c0b' : '#3a2e26',
                border: '1px solid #2a2420',
                borderRadius: '8px',
                cursor: (composeTo.trim() && composeMsg.trim() && !sending) ? 'pointer' : 'not-allowed',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              {sending ? 'signing + delivering...' : 'Send'}
            </button>
            <p style={{ color: '#6b5f52', fontSize: '11px', marginTop: '14px', fontFamily: 'DM Mono, monospace' }}>
              Your brain signs the payload locally · ED25519 · delivered to {composeTo ? `${composeTo}.brainfoundry.ai` : '<recipient>.brainfoundry.ai'}/v1/federation/dm/receive
            </p>
          </div>
        )}

      </div>
    </>
  )
}
