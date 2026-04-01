import { useEffect, useRef, useState } from 'react'

export default function Chat() {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [messages, setMessages] = useState([])
  const [inputMessage, setInputMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [showNameModal, setShowNameModal] = useState(false)
  const [newChatName, setNewChatName] = useState('')
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetch('/api/bf/models')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        const claude = { name: 'claude-sonnet-4-6' }
        const ollama = (d.models || []).filter(m => !m.name.includes('claude'))
        const list = [claude, ...ollama]
        setModels(list)
        setSelectedModel('claude-sonnet-4-6')
      })
      .catch(e => setError(`Models: ${e.message}`))

    fetchSessions()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const fetchSessions = () => {
    fetch('/api/bf/sessions')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setSessions(d.sessions || []))
      .catch(console.error)
  }

  const loadSessionMessages = sessionId => {
    fetch(`/api/bf/sessions/${sessionId}/messages`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        setMessages(d.messages || [])
        setCurrentSessionId(sessionId)
      })
      .catch(console.error)
  }

  const createNewSession = async (title = 'New Chat') => {
    if (!selectedModel) { setError('Select a model first'); return }
    setIsCreatingSession(true)
    try {
      const r = await fetch('/api/bf/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: selectedModel, title }),
      })
      if (r.ok) {
        const s = await r.json()
        setCurrentSessionId(s.session_id)
        setMessages([])
        fetchSessions()
      }
    } catch (e) {
      setError('Failed to create session')
    } finally {
      setIsCreatingSession(false)
    }
  }

  const deleteSession = async sessionId => {
    try {
      const r = await fetch(`/api/bf/sessions/${sessionId}`, { method: 'DELETE' })
      if (r.ok) {
        if (currentSessionId === sessionId) { setCurrentSessionId(null); setMessages([]) }
        fetchSessions()
      }
    } catch (e) {
      setError('Failed to delete session')
    }
  }

  const sendMessage = async () => {
    if (!inputMessage.trim() || !selectedModel || isLoading) return

    let sessionId = currentSessionId
    if (!sessionId) {
      setIsCreatingSession(true)
      try {
        const r = await fetch('/api/bf/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_name: selectedModel, title: 'New Chat' }),
        })
        if (r.ok) {
          const s = await r.json()
          sessionId = s.session_id
          setCurrentSessionId(sessionId)
          fetchSessions()
        }
      } catch (e) {
        setError('Failed to create session')
        setIsCreatingSession(false)
        return
      }
      setIsCreatingSession(false)
    }

    const userMessage = { role: 'user', content: inputMessage.trim() }
    const updated = [...messages, userMessage]
    setMessages(updated)
    setInputMessage('')
    setIsLoading(true)
    setError(null)

    try {
      const permitRes = await fetch('/api/permit', { method: 'POST' })
      const permitData = await permitRes.json()
      if (!permitData.permit_id) {
        setError('Failed to get loop permit')
        setIsLoading(false)
        return
      }

      const r = await fetch('/api/bf/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          messages: updated,
          session_id: sessionId,
          max_tokens: 1000,
          permit_id: permitData.permit_id,
        }),
      })
      if (r.ok) {
        const data = await r.json()
        setMessages([...updated, { role: 'assistant', content: data.choices[0].message.content }])
        fetchSessions()
      } else {
        const err = await r.json().catch(() => ({}))
        setError(`API error: ${err.detail || r.status}`)
      }
    } catch (e) {
      setError(`Network error: ${e.message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  const formatDate = dateString => {
    if (!dateString) return ''
    const d = new Date(dateString)
    const diff = Math.floor((Date.now() - d) / 86400000)
    if (diff === 0) return 'Today'
    if (diff === 1) return 'Yesterday'
    if (diff < 7) return `${diff}d ago`
    return d.toLocaleDateString()
  }

  return (
    <div style={{
      height: 'calc(100vh - 52px)',
      backgroundColor: '#0a0a0a',
      color: '#e5e5e5',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      display: 'flex',
    }}>

      {/* Sidebar */}
      <div style={{
        width: sidebarOpen ? '280px' : '0',
        flexShrink: 0,
        backgroundColor: '#0f0f0f',
        borderRight: '1px solid #1e1e1e',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '16px',
          borderBottom: '1px solid #1e1e1e',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: '13px', fontWeight: '600', color: '#555', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Sessions
          </span>
          <button
            onClick={() => { setNewChatName(''); setShowNameModal(true) }}
            disabled={isCreatingSession || !selectedModel}
            style={{
              background: '#e5e5e5',
              color: '#0a0a0a',
              border: 'none',
              borderRadius: '6px',
              padding: '5px 10px',
              fontSize: '13px',
              cursor: isCreatingSession || !selectedModel ? 'not-allowed' : 'pointer',
              opacity: isCreatingSession || !selectedModel ? 0.4 : 1,
            }}
          >
            + New
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {sessions.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#333', padding: '40px 16px', fontSize: '13px' }}>
              No sessions yet
            </div>
          ) : (
            sessions.map(s => (
              <div
                key={s.session_id}
                onClick={() => loadSessionMessages(s.session_id)}
                style={{
                  padding: '10px 12px',
                  margin: '2px 0',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  backgroundColor: currentSessionId === s.session_id ? '#667eea15' : 'transparent',
                  border: `1px solid ${currentSessionId === s.session_id ? '#667eea30' : 'transparent'}`,
                  transition: 'all 0.15s ease',
                }}
                onMouseOver={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = '#1a1a1a' }}
                onMouseOut={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                  <div style={{ fontSize: '13px', fontWeight: '500', color: '#ccc', flex: 1, marginRight: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title || 'Untitled'}
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); deleteSession(s.session_id) }}
                    style={{ background: 'none', border: 'none', color: '#333', cursor: 'pointer', fontSize: '16px', padding: '0 2px', lineHeight: 1, flexShrink: 0 }}
                    onMouseOver={e => e.target.style.color = '#ff6b6b'}
                    onMouseOut={e => e.target.style.color = '#333'}
                  >
                    ×
                  </button>
                </div>
                <div style={{ fontSize: '11px', color: '#444' }}>
                  {s.message_count || 0} msgs &middot; {formatDate(s.created_at)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Chat header */}
        <div style={{
          backgroundColor: '#0f0f0f',
          borderBottom: '1px solid #1e1e1e',
          padding: '12px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          flexShrink: 0,
        }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ background: 'none', border: '1px solid #222', color: '#666', padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>

          <select
            value={selectedModel}
            onChange={e => setSelectedModel(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #1e1e1e',
              backgroundColor: '#1a1a1a',
              color: '#e5e5e5',
              fontSize: '13px',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="">Select model</option>
            {models.map(m => (
              <option key={m.name} value={m.name}>
                {m.name}{m.size ? ` (${(m.size / 1e9).toFixed(1)}GB)` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#333', marginTop: '80px', fontSize: '14px' }}>
              {currentSessionId ? 'Ready.' : 'Start a conversation or select a session.'}
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '72%',
                padding: '14px 18px',
                borderRadius: '16px',
                background: msg.role === 'user'
                  ? '#e5e5e5'
                  : '#131313',
                color: msg.role === 'user' ? '#0a0a0a' : '#ccc',
                border: msg.role === 'user' ? 'none' : '1px solid #1e1e1e',
                fontSize: '14px',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px', fontWeight: '500' }}>
                  {msg.role === 'user' ? 'You' : (selectedModel || 'Brain')}
                </div>
                {msg.content}
              </div>
            </div>
          ))}

          {isLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ padding: '14px 18px', borderRadius: '16px', backgroundColor: '#131313', border: '1px solid #1e1e1e', color: '#555', fontSize: '14px' }}>
                <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px' }}>{selectedModel || 'Brain'}</div>
                <span>thinking...</span>
              </div>
            </div>
          )}

          {error && (
            <div style={{ backgroundColor: '#1a0a0a', border: '1px solid #ff6b6b20', borderRadius: '10px', padding: '12px 16px', color: '#ff6b6b', fontSize: '13px' }}>
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{ backgroundColor: '#0f0f0f', borderTop: '1px solid #1e1e1e', padding: '16px 20px', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
            <textarea
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={selectedModel ? 'Message... (Enter to send)' : 'Select a model first'}
              disabled={!selectedModel || isLoading}
              rows={1}
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '10px',
                border: '1px solid #1e1e1e',
                backgroundColor: '#1a1a1a',
                color: '#e5e5e5',
                fontSize: '14px',
                resize: 'none',
                fontFamily: 'inherit',
                outline: 'none',
                minHeight: '44px',
                maxHeight: '140px',
                lineHeight: '1.5',
              }}
              onInput={e => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
              }}
            />
            <button
              onClick={sendMessage}
              disabled={!inputMessage.trim() || !selectedModel || isLoading}
              style={{
                padding: '12px 20px',
                background: (!inputMessage.trim() || !selectedModel || isLoading) ? '#1a1a1a' : '#e5e5e5',
                color: (!inputMessage.trim() || !selectedModel || isLoading) ? '#444' : '#0a0a0a',
                border: '1px solid #1e1e1e',
                borderRadius: '10px',
                cursor: (!inputMessage.trim() || !selectedModel || isLoading) ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: '600',
                transition: 'all 0.15s ease',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {isLoading ? '...' : 'Send'}
            </button>
          </div>
        </div>
      </div>

      {/* New session modal */}
      {showNameModal && (
        <div style={{
          position: 'fixed', inset: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 200,
        }}>
          <div style={{
            backgroundColor: '#111',
            border: '1px solid #1e1e1e',
            borderRadius: '14px',
            padding: '28px',
            width: '380px',
            maxWidth: '90vw',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#e5e5e5' }}>New session</h2>
              <button onClick={() => setShowNameModal(false)} style={{ background: 'none', border: 'none', color: '#444', fontSize: '20px', cursor: 'pointer' }}>×</button>
            </div>
            <form onSubmit={async e => {
              e.preventDefault()
              const title = newChatName.trim() || 'New Chat'
              setShowNameModal(false)
              await createNewSession(title)
            }}>
              <input
                type="text"
                value={newChatName}
                onChange={e => setNewChatName(e.target.value)}
                placeholder="Session name (optional)"
                autoFocus
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  backgroundColor: '#1a1a1a',
                  border: '1px solid #1e1e1e',
                  borderRadius: '8px',
                  color: '#e5e5e5',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  marginBottom: '16px',
                }}
              />
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowNameModal(false)} style={{ padding: '8px 16px', backgroundColor: 'transparent', border: '1px solid #1e1e1e', borderRadius: '8px', color: '#888', cursor: 'pointer', fontSize: '14px' }}>
                  Cancel
                </button>
                <button type="submit" style={{ padding: '8px 16px', background: '#e5e5e5', border: 'none', borderRadius: '8px', color: '#0a0a0a', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
