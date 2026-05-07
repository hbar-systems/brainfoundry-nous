import { useEffect, useRef, useState } from 'react'
import MessageRenderer from '../lib/MessageRenderer'
import CustomSelect from '../lib/CustomSelect'

const THEME_OPTIONS = [
  { value: 'gold', label: 'gold', swatch: '#c9a96e' },
  { value: 'paper', label: 'paper', swatch: '#8a6e3c' },
  { value: 'sapphire', label: 'sapphire', swatch: '#6b8cce' },
  { value: 'forest', label: 'forest', swatch: '#88a868' },
  { value: 'crimson', label: 'crimson', swatch: '#c87878' },
  { value: 'mono', label: 'mono', swatch: '#b0b0b0' },
]

// Each option's optionStyle previews the font in the dropdown row itself,
// so the operator can see what they're picking before they apply it.
const FONT_OPTIONS = [
  { value: 'system', label: 'System sans', optionStyle: { fontFamily: 'system-ui, -apple-system, sans-serif' } },
  { value: 'inter', label: 'Inter', optionStyle: { fontFamily: '"Inter", system-ui, sans-serif' } },
  { value: 'lora', label: 'Lora', optionStyle: { fontFamily: 'Lora, Georgia, serif' } },
  { value: 'crimson', label: 'Crimson Pro', optionStyle: { fontFamily: '"Crimson Pro", Georgia, serif' } },
  { value: 'dm-mono', label: 'DM Mono', optionStyle: { fontFamily: '"DM Mono", ui-monospace, monospace' } },
  { value: 'jetbrains', label: 'JetBrains Mono', optionStyle: { fontFamily: '"JetBrains Mono", ui-monospace, monospace' } },
]

const FONT_MIGRATION = { ui: 'system', serif: 'lora', mono: 'dm-mono' }

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
  // On phone-width viewports default the sidebar closed so the message column
  // gets the full screen. Operator can still toggle via the existing button.
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches) {
      setSidebarOpen(false)
    }
  }, [])
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [showNameModal, setShowNameModal] = useState(false)
  const [newChatName, setNewChatName] = useState('')
  const [attachedImages, setAttachedImages] = useState([]) // [{base64, mediaType, name, dataUrl}]
  const [dragActive, setDragActive] = useState(false)
  const MAX_IMAGES = 10
  const [consolidating, setConsolidating] = useState(false)
  const [consolidateStatus, setConsolidateStatus] = useState(null) // {ok: bool, message: string} | null

  // Theme + font: state mirrors document.documentElement.dataset. Seeded
  // from localStorage on mount; change handlers write through to both
  // dataset and localStorage so any other page picks them up on next paint.
  const [theme, setTheme] = useState('gold')
  const [font, setFont] = useState('system')
  useEffect(() => {
    if (typeof window === 'undefined') return
    setTheme(localStorage.getItem('bf-theme') || 'gold')
    const stored = localStorage.getItem('bf-font') || 'system'
    setFont(FONT_MIGRATION[stored] || stored)
  }, [])
  const applyTheme = (val) => {
    setTheme(val)
    if (typeof window !== 'undefined') {
      localStorage.setItem('bf-theme', val)
      document.documentElement.dataset.theme = val
    }
  }
  const applyFont = (val) => {
    setFont(val)
    if (typeof window !== 'undefined') {
      localStorage.setItem('bf-font', val)
      document.documentElement.dataset.font = val
    }
  }

  const consolidateSession = async () => {
    if (!currentSessionId || consolidating) return
    if (messages.length < 2) { setConsolidateStatus({ ok: false, message: 'Chat too short to save (need at least one exchange).' }); return }
    setConsolidating(true)
    setConsolidateStatus(null)
    try {
      const permitRes = await fetch('/api/permit', { method: 'POST' })
      const permitData = await permitRes.json()
      if (!permitData.permit_id || !permitData.permit_token) {
        setConsolidateStatus({ ok: false, message: 'Permit failed — could not save.' })
        setConsolidating(false)
        return
      }
      const r = await fetch(`/api/bf/chat/sessions/${currentSessionId}/consolidate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          permit_id: permitData.permit_id,
          permit_token: permitData.permit_token,
        }),
      })
      if (r.ok) {
        const data = await r.json()
        setConsolidateStatus({ ok: true, message: `Saved to memory: ${data.chunks_stored} chunks in episodic layer.` })
      } else {
        const err = await r.json().catch(() => ({}))
        setConsolidateStatus({ ok: false, message: err.detail || `Failed (${r.status})` })
      }
    } catch (e) {
      setConsolidateStatus({ ok: false, message: e.message })
    } finally {
      setConsolidating(false)
      // auto-clear status after 6 sec
      setTimeout(() => setConsolidateStatus(null), 6000)
    }
  }

  const ingestImageFiles = (fileList) => {
    const incoming = Array.from(fileList || [])
    const onlyImages = incoming.filter(f => f.type.startsWith('image/'))
    if (incoming.length > onlyImages.length) {
      setError(`Skipped ${incoming.length - onlyImages.length} non-image file(s)`)
    }
    setAttachedImages(prev => {
      const room = MAX_IMAGES - prev.length
      if (room <= 0) {
        setError(`Already at max ${MAX_IMAGES} images — remove one to add more`)
        return prev
      }
      const accepted = onlyImages.slice(0, room).filter(f => f.size <= 5 * 1024 * 1024)
      const oversized = onlyImages.slice(0, room).length - accepted.length
      if (oversized > 0) setError(`${oversized} image(s) over 5MB — skipped`)
      if (onlyImages.length > room) setError(`Capped at ${MAX_IMAGES} images — extras ignored`)
      accepted.forEach(file => {
        const reader = new FileReader()
        reader.onload = () => {
          const dataUrl = reader.result
          const base64 = String(dataUrl).split(',')[1]
          setAttachedImages(curr => [...curr, { base64, mediaType: file.type, name: file.name, dataUrl }])
        }
        reader.onerror = () => setError(`Failed to read ${file.name}`)
        reader.readAsDataURL(file)
      })
      return prev
    })
  }

  const handleImageSelect = e => {
    ingestImageFiles(e.target.files)
    e.target.value = '' // allow re-selecting same file
  }

  const removeImageAt = (idx) => {
    setAttachedImages(prev => prev.filter((_, i) => i !== idx))
  }

  const handleChatDragOver = e => {
    e.preventDefault()
    e.stopPropagation()
    if (!dragActive) setDragActive(true)
  }
  const handleChatDragLeave = e => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }
  const handleChatDrop = e => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer?.files?.length) ingestImageFiles(e.dataTransfer.files)
  }
  const messagesEndRef = useRef(null)
  const messagesContainerRef = useRef(null)
  const [stickToBottom, setStickToBottom] = useState(true)

  useEffect(() => {
    fetch('/api/bf/models')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        const list = d.models || []
        setModels(list)
        setSelectedModel(list[0]?.name || '')
      })
      .catch(e => setError(`Models: ${e.message}`))

    fetchSessions()
  }, [])

  useEffect(() => {
    if (!stickToBottom) return
    const c = messagesContainerRef.current
    if (c) c.scrollTop = c.scrollHeight
  }, [messages, isLoading, stickToBottom])

  const fetchSessions = () => {
    fetch('/api/bf/sessions')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        // Only update state if the response is a confirmed array.
        // Don't wipe sidebar on malformed/empty/transient responses.
        if (d && Array.isArray(d.sessions)) {
          setSessions(d.sessions)
        } else if (d) {
          console.warn('sessions response missing sessions array:', d)
        }
      })
      .catch(console.error)
  }

  const loadSessionMessages = sessionId => {
    fetch(`/api/bf/sessions/${sessionId}/messages`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return
        // Same defensive pattern as fetchSessions — don't wipe messages
        // on malformed responses. Only update if messages is a real array.
        if (Array.isArray(d.messages)) {
          setMessages(d.messages)
          setCurrentSessionId(sessionId)
        } else {
          console.warn('messages response missing messages array:', d)
        }
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

    setStickToBottom(true)

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

    const userMessage = {
      role: 'user',
      content: inputMessage.trim(),
      imageDataUrls: attachedImages.map(i => i.dataUrl), // local render only, not sent to backend
    }
    const updated = [...messages, userMessage]
    const imagesForRequest = attachedImages // capture before clearing
    setMessages(updated)
    setInputMessage('')
    setAttachedImages([])
    setIsLoading(true)
    setError(null)
    const useStreaming = imagesForRequest.length === 0 // vision path is non-streaming in v0.7

    try {
      const permitRes = await fetch('/api/permit', { method: 'POST' })
      const permitData = await permitRes.json()
      if (!permitData.permit_id || !permitData.permit_token) {
        setError(`Permit failed: ${permitData.detail || permitData.error || 'NodeOS did not issue permit'}`)
        setIsLoading(false)
        return
      }

      // Strip image data URLs from messages sent to backend — server doesn't need them
      // and they'd bloat the request.
      const messagesForBackend = updated.map(m => {
        const { imageDataUrls, ...rest } = m
        return rest
      })

      const r = await fetch('/api/bf/chat/rag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: selectedModel,
          messages: messagesForBackend,
          session_id: sessionId,
          layers: ['identity', 'thinking', 'projects', 'writing', 'episodic'],
          search_limit: 5,
          stream: useStreaming,
          ...(imagesForRequest.length > 0 ? {
            images: imagesForRequest.map(i => ({ base64: i.base64, media_type: i.mediaType })),
          } : {}),
          permit_id: permitData.permit_id,
          permit_token: permitData.permit_token,
        }),
      })

      if (!r.ok) {
        const err = await r.json().catch(() => ({}))
        setError(`Error ${r.status}: ${err.detail || 'server error — check API logs'}`)
      } else if (!useStreaming) {
        // Vision path returns JSON
        const data = await r.json()
        setMessages([...updated, { role: 'assistant', content: data.choices[0].message.content }])
        fetchSessions()
      } else {
        // Streaming path consumes SSE
        setMessages([...updated, { role: 'assistant', content: '' }])

        const reader = r.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantContent = ''

        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const frames = buffer.split('\n\n')
          buffer = frames.pop()

          for (const frame of frames) {
            if (!frame.startsWith('data: ')) continue
            const data = frame.slice(6).trim()
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              const delta = parsed.choices?.[0]?.delta?.content
              if (delta) {
                assistantContent += delta
                setMessages(prev => {
                  const next = [...prev]
                  next[next.length - 1] = { role: 'assistant', content: assistantContent }
                  return next
                })
              } else if (parsed.error) {
                setError(`Stream error: ${parsed.error}`)
              }
            } catch {
              // Skip malformed frames silently.
            }
          }
        }
        fetchSessions()
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
      // Subtract nav height (52px content + PWA safe-area-top) so the
      // chat column fills exactly the viewport below the nav.
      height: 'calc(100vh - 52px - env(safe-area-inset-top, 0px))',
      backgroundColor: 'var(--bg)',
      color: 'var(--text)',
      fontFamily: 'var(--font-body)',
      display: 'flex',
    }}>

      {/* Sidebar */}
      <div style={{
        width: sidebarOpen ? '280px' : '0',
        flexShrink: 0,
        backgroundColor: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '16px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: '11px', fontWeight: '600', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Sessions
          </span>
          <button
            onClick={() => { setNewChatName(''); setShowNameModal(true) }}
            disabled={isCreatingSession || !selectedModel}
            style={{
              background: 'var(--accent)',
              color: 'var(--bg)',
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
            <div style={{ textAlign: 'center', padding: '40px 16px' }}>
              <div style={{ fontSize: '22px', marginBottom: '8px', color: 'var(--accent)', opacity: 0.4 }}>ℏ</div>
              <div style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6 }}>No sessions yet.<br />Click + New to begin.</div>
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
                  backgroundColor: currentSessionId === s.session_id ? 'rgba(201,169,110,0.1)' : 'transparent',
                  border: `1px solid ${currentSessionId === s.session_id ? 'rgba(201,169,110,0.2)' : 'transparent'}`,
                  transition: 'all 0.15s ease',
                }}
                onMouseOver={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = 'var(--surface2)' }}
                onMouseOut={e => { if (currentSessionId !== s.session_id) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                  <div style={{ fontSize: '13px', fontWeight: '500', color: 'var(--text)', flex: 1, marginRight: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.title || 'Untitled'}
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); deleteSession(s.session_id) }}
                    style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '16px', padding: '0 2px', lineHeight: 1, flexShrink: 0 }}
                    onMouseOver={e => e.target.style.color = '#c96e6e'}
                    onMouseOut={e => e.target.style.color = 'var(--muted)'}
                  >
                    ×
                  </button>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
                  {s.message_count || 0} msgs &middot; {formatDate(s.created_at)}
                </div>
              </div>
            ))
          )}
        </div>

        <div style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <button
            onClick={() => setSidebarOpen(false)}
            style={{
              width: '100%',
              background: 'none',
              border: '1px solid var(--border)',
              color: 'var(--muted)',
              padding: '8px 10px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}
            onMouseOver={e => { e.currentTarget.style.backgroundColor = 'var(--surface2)'; e.currentTarget.style.color = 'var(--text)' }}
            onMouseOut={e => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = 'var(--muted)' }}
          >
            <span>◀</span>
            <span>Hide sidebar</span>
          </button>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Chat header */}
        <div style={{
          backgroundColor: 'var(--surface)',
          borderBottom: '1px solid var(--border)',
          padding: '12px 20px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          flexShrink: 0,
        }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--muted)', padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>

          <CustomSelect
            value={selectedModel}
            onChange={setSelectedModel}
            title="Model"
            minWidth={180}
            options={[
              { value: '', label: 'Select model' },
              ...models.map(m => ({
                value: m.name,
                label: m.name + (m.size ? ` (${(m.size / 1e9).toFixed(1)}GB)` : ''),
              })),
            ]}
          />

          <CustomSelect
            value={theme}
            onChange={applyTheme}
            title="Theme"
            minWidth={120}
            options={THEME_OPTIONS}
          />

          <CustomSelect
            value={font}
            onChange={applyFont}
            title="Font"
            minWidth={160}
            options={FONT_OPTIONS}
          />

          {currentSessionId && messages.length >= 2 && (
            <button
              onClick={consolidateSession}
              disabled={consolidating}
              title="Save this conversation into your brain's long-term memory (episodic layer). Future chats will retrieve from it via RAG."
              style={{
                marginLeft: 'auto',
                padding: '8px 14px',
                background: consolidating ? 'var(--surface)' : 'transparent',
                color: consolidating ? 'var(--muted)' : 'var(--accent)',
                border: '1px solid rgba(201, 169, 110, 0.38)',
                borderRadius: '8px',
                cursor: consolidating ? 'wait' : 'pointer',
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.04em',
              }}
            >
              {consolidating ? 'saving...' : 'Save to memory'}
            </button>
          )}
        </div>

        {consolidateStatus && (
          <div style={{
            padding: '8px 20px',
            backgroundColor: consolidateStatus.ok ? '#1e3a26' : '#3a1e1e',
            color: consolidateStatus.ok ? '#7fc99c' : '#c98080',
            fontSize: '12px',
            borderBottom: '1px solid var(--border)',
            fontFamily: 'var(--font-mono)',
          }}>
            {consolidateStatus.message}
          </div>
        )}

        {/* Messages — also the drop zone for images */}
        <div
          ref={messagesContainerRef}
          onScroll={e => {
            const el = e.currentTarget
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
            setStickToBottom(nearBottom)
          }}
          onDragOver={handleChatDragOver}
          onDragLeave={handleChatDragLeave}
          onDrop={handleChatDrop}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px 28px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            position: 'relative',
            outline: dragActive ? '2px dashed var(--accent)' : 'none',
            outlineOffset: '-12px',
            backgroundColor: dragActive ? 'rgba(201,169,110,0.04)' : 'transparent',
            transition: 'background 0.15s ease',
          }}
        >
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: '100px' }}>
              <div style={{ fontSize: '32px', marginBottom: '20px', color: 'var(--accent)', opacity: 0.25 }}>ℏ</div>
              <div style={{
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '17px',
                color: 'var(--muted)',
                letterSpacing: '0.01em',
              }}>
                {currentSessionId ? 'Session ready.' : `${process.env.NEXT_PUBLIC_BRAIN_NAME || 'Your brain'} is ready.`}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '72%',
                padding: '14px 18px',
                borderRadius: '16px',
                background: msg.role === 'user' ? 'var(--user-bg)' : 'var(--assistant-bg)',
                color: msg.role === 'user' ? 'var(--user-text)' : 'var(--assistant-text)',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                fontSize: '14px',
                lineHeight: '1.6',
                whiteSpace: msg.role === 'user' ? 'pre-wrap' : 'normal',
                wordBreak: 'break-word',
              }}>
                <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px', fontWeight: '500' }}>
                  {msg.role === 'user' ? 'You' : (selectedModel || 'Brain')}
                </div>
                {msg.imageDataUrls && msg.imageDataUrls.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
                    {msg.imageDataUrls.map((url, ii) => (
                      <img
                        key={ii}
                        src={url}
                        alt={`attached ${ii + 1}`}
                        style={{ maxWidth: '160px', maxHeight: 160, objectFit: 'cover', borderRadius: '8px', display: 'block' }}
                      />
                    ))}
                  </div>
                )}
                {msg.role === 'assistant'
                  ? <MessageRenderer content={msg.content} />
                  : msg.content}
              </div>
            </div>
          ))}

          {isLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ padding: '14px 18px', borderRadius: '16px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)', fontSize: '14px' }}>
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

        {!stickToBottom && (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            padding: '6px 0',
            backgroundColor: 'var(--bg)',
            borderTop: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            <button
              onClick={() => {
                setStickToBottom(true)
                const c = messagesContainerRef.current
                if (c) c.scrollTop = c.scrollHeight
              }}
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                color: 'var(--accent)',
                padding: '6px 14px',
                borderRadius: '999px',
                cursor: 'pointer',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span>↓</span>
              <span>Jump to latest</span>
            </button>
          </div>
        )}

        {/* Input */}
        <div className="bf-chat-input-bar" style={{ backgroundColor: 'var(--surface)', borderTop: '1px solid var(--border)', padding: '16px 20px', flexShrink: 0, boxShadow: '0 -4px 24px rgba(0,0,0,0.4)', paddingBottom: 'calc(16px + env(safe-area-inset-bottom, 0px))' }}>
          {attachedImages.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '10px', padding: '10px 12px', backgroundColor: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: '8px' }}>
              <div style={{ width: '100%', fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-mono)', marginBottom: '4px' }}>
                {attachedImages.length} image{attachedImages.length > 1 ? 's' : ''} attached ({MAX_IMAGES} max)
              </div>
              {attachedImages.map((img, i) => (
                <div key={i} style={{ position: 'relative', width: 64, height: 64 }}>
                  <img src={img.dataUrl} alt={img.name} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: '6px' }} />
                  <button
                    onClick={() => removeImageAt(i)}
                    title="Remove"
                    style={{
                      position: 'absolute', top: -6, right: -6,
                      width: 18, height: 18,
                      background: '#3a1e1e', color: '#c98080',
                      border: '1px solid #6b3030', borderRadius: '50%',
                      cursor: 'pointer', fontSize: '11px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      padding: 0, lineHeight: 1,
                    }}
                  >×</button>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
            <label
              htmlFor="image-upload-input"
              title="Attach image (uses vision-capable model — Claude / GPT-4o)"
              style={{
                padding: '12px 14px',
                backgroundColor: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: '10px',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                color: 'var(--muted)',
                fontSize: '16px',
                userSelect: 'none',
                flexShrink: 0,
                lineHeight: '1',
              }}
            >📎</label>
            <input
              id="image-upload-input"
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageSelect}
              disabled={isLoading}
              style={{ display: 'none' }}
            />
            <textarea
              value={inputMessage}
              onChange={e => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedModel
                  ? (attachedImages.length > 0
                      ? `Ask about the image${attachedImages.length > 1 ? 's' : ''}...`
                      : (typeof window !== 'undefined' && window.matchMedia('(max-width: 480px)').matches
                          ? 'Message...'
                          : 'Message... (Enter to send, drop images here)'))
                  : 'Select a model first'
              }
              disabled={!selectedModel || isLoading}
              rows={1}
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: '10px',
                border: '1px solid var(--border)',
                backgroundColor: 'var(--surface)',
                color: 'var(--text)',
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
                background: (!inputMessage.trim() || !selectedModel || isLoading) ? 'var(--surface)' : 'var(--accent)',
                color: (!inputMessage.trim() || !selectedModel || isLoading) ? 'var(--muted)' : 'var(--bg)',
                border: '1px solid var(--border)',
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
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '14px',
            padding: '28px',
            width: '380px',
            maxWidth: '90vw',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: 'var(--text)' }}>New session</h2>
              <button onClick={() => setShowNameModal(false)} style={{ background: 'none', border: 'none', color: 'var(--muted)', fontSize: '20px', cursor: 'pointer' }}>×</button>
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
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  color: 'var(--text)',
                  fontSize: '14px',
                  outline: 'none',
                  boxSizing: 'border-box',
                  marginBottom: '16px',
                }}
              />
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setShowNameModal(false)} style={{ padding: '8px 16px', backgroundColor: 'transparent', border: '1px solid var(--border)', borderRadius: '8px', color: 'var(--muted)', cursor: 'pointer', fontSize: '14px' }}>
                  Cancel
                </button>
                <button type="submit" style={{ padding: '8px 16px', background: 'var(--accent)', border: 'none', borderRadius: '8px', color: 'var(--bg)', cursor: 'pointer', fontSize: '14px', fontWeight: '600' }}>
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
