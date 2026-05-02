import { useEffect, useRef, useState } from 'react'
import Head from 'next/head'

const MAX_HISTORY = 10

export default function Home() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return

    const next = [...messages, { role: 'user', content: text }].slice(-MAX_HISTORY)
    setMessages(next)
    setInput('')
    setLoading(true)
    setError(null)

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({
          message: text,
          history: messages,
        }),
      })

      const ct = r.headers.get('content-type') || ''
      if (!r.ok || !ct.includes('text/event-stream')) {
        const data = await r.json().catch(() => ({}))
        if (r.status === 429) {
          setError(data.error || 'Too many requests. Please wait a minute and try again.')
        } else {
          setError(data.error || `Error ${r.status}`)
        }
        return
      }

      // SSE consume: append tokens to the assistant message as they arrive.
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assembled = ''
      let assistantPushed = false

      const upsertAssistant = (content) => {
        if (!assistantPushed) {
          assistantPushed = true
          setLoading(false)
          setMessages((prev) => [...prev, { role: 'assistant', content }].slice(-MAX_HISTORY))
        } else {
          setMessages((prev) => {
            const out = prev.slice()
            out[out.length - 1] = { role: 'assistant', content }
            return out
          })
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // SSE events are separated by a blank line (\n\n).
        const events = buffer.split('\n\n')
        buffer = events.pop() // last (possibly incomplete) event stays buffered
        for (const evt of events) {
          const dataLine = evt.split('\n').find((l) => l.startsWith('data: '))
          if (!dataLine) continue
          let payload
          try {
            payload = JSON.parse(dataLine.slice(6))
          } catch {
            continue
          }
          if (typeof payload.token === 'string') {
            assembled += payload.token
            upsertAssistant(assembled)
          } else if (payload.done) {
            // Final marker — nothing to render, the stream will close.
          } else if (payload.error) {
            const msg = `Error: ${payload.error}`
            if (assistantPushed) {
              upsertAssistant(`${assembled}${assembled ? '\n\n' : ''}${msg}`)
            } else {
              setError(msg)
            }
          }
        }
      }
    } catch (e) {
      setError(`Network error: ${e.message}`)
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <>
      <Head>
        <title>Nous — public demo</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="robots" content="noindex" />
      </Head>
      <div style={{
        minHeight: '100vh',
        backgroundColor: '#0e0c0b',
        color: '#e8e0d5',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <header style={{
          padding: '20px 24px',
          borderBottom: '1px solid #2a2420',
          display: 'flex',
          alignItems: 'baseline',
          gap: '12px',
        }}>
          <span style={{ fontSize: '20px', color: '#c9a96e', fontFamily: 'Lora, Georgia, serif' }}>ℏ Nous</span>
          <span style={{ fontSize: '12px', color: '#6b5f52' }}>public demo brain</span>
        </header>

        <main style={{
          flex: 1,
          maxWidth: '760px',
          width: '100%',
          margin: '0 auto',
          padding: '24px 20px 0',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}>
          {messages.length === 0 && !loading && (
            <div style={{ textAlign: 'center', marginTop: '80px' }}>
              <div style={{ fontSize: '40px', marginBottom: '20px', color: '#c9a96e', opacity: 0.3 }}>ℏ</div>
              <div style={{
                fontFamily: 'Lora, Georgia, serif',
                fontStyle: 'italic',
                fontSize: '18px',
                color: '#6b5f52',
              }}>
                Ask me anything about brains, BrainFoundry, or what it means to own your cognition.
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '78%',
                padding: '12px 16px',
                borderRadius: '14px',
                background: m.role === 'user' ? '#e8d5b0' : '#13100e',
                color: m.role === 'user' ? '#1a1210' : '#c4b8a8',
                border: m.role === 'user' ? 'none' : '1px solid #2a2420',
                fontSize: '14px',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}>
                <div style={{ fontSize: '11px', opacity: 0.55, marginBottom: '6px' }}>
                  {m.role === 'user' ? 'you' : 'Nous'}
                </div>
                {m.content}
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{
                padding: '12px 16px',
                borderRadius: '14px',
                background: '#13100e',
                border: '1px solid #2a2420',
                color: '#4a3f36',
                fontSize: '14px',
              }}>
                <div style={{ fontSize: '11px', opacity: 0.55, marginBottom: '6px' }}>Nous</div>
                thinking...
              </div>
            </div>
          )}

          {error && (
            <div style={{
              backgroundColor: '#1a0a0a',
              border: '1px solid #ff6b6b30',
              borderRadius: '10px',
              padding: '10px 14px',
              color: '#ff6b6b',
              fontSize: '13px',
            }}>
              {error}
            </div>
          )}

          <div ref={endRef} />
        </main>

        <div style={{
          maxWidth: '760px',
          width: '100%',
          margin: '0 auto',
          padding: '12px 20px 8px',
          display: 'flex',
          gap: '10px',
          alignItems: 'flex-end',
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Message Nous..."
            disabled={loading}
            rows={1}
            style={{
              flex: 1,
              padding: '12px 14px',
              borderRadius: '10px',
              border: '1px solid #2a2420',
              backgroundColor: '#161310',
              color: '#e8e0d5',
              fontSize: '14px',
              resize: 'none',
              fontFamily: 'inherit',
              outline: 'none',
              minHeight: '44px',
              maxHeight: '160px',
              lineHeight: '1.5',
            }}
            onInput={(e) => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
            }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            style={{
              padding: '12px 18px',
              background: (!input.trim() || loading) ? '#161310' : '#c9a96e',
              color: (!input.trim() || loading) ? '#3a2e26' : '#0e0c0b',
              border: '1px solid #2a2420',
              borderRadius: '10px',
              cursor: (!input.trim() || loading) ? 'not-allowed' : 'pointer',
              fontSize: '14px',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {loading ? '...' : 'Send'}
          </button>
        </div>

        <footer style={{
          padding: '12px 20px 20px',
          textAlign: 'center',
          fontSize: '12px',
          color: '#4a3f36',
          fontFamily: 'DM Mono, monospace',
        }}>
          Public demo of Nous. Want your own brain?{' '}
          <a href="https://brainfoundry.ai" style={{ color: '#c9a96e', textDecoration: 'none' }}>
            brainfoundry.ai
          </a>
        </footer>
      </div>
    </>
  )
}
