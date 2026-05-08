import { useEffect, useState } from 'react'
import MessageRenderer from '../lib/MessageRenderer'

// Use-from-terminal page. Renders endpoint + API key (hidden by default,
// reveal/copy buttons), plus example curl commands. Embedded console
// (run Claude Code or hbar CLI directly inside the brain UI) is the
// follow-on step — flagged here as "coming soon" so operator knows it's
// scoped, not forgotten.

const CLI_INTRO = `
# Use this brain from your terminal

Your brain exposes an OpenAI-compatible HTTP API. Anything that talks to OpenAI — \`curl\`, the official Anthropic SDK with a custom base-URL, your own scripts, an LLM agent harness — can talk to this brain by pointing at the brain's endpoint and presenting its API key.

The same brain that answers in this UI is what answers your terminal. RAG, persona, federation — all of it applies.
`

const SECURITY_NOTE = `
> **Treat the API key like a password.** Anyone with this key can read your brain, write to it, and run inference on your behalf (which costs whatever your provider charges). Don't paste it in chat with a third party, don't commit it to git, don't share screenshots of this page un-redacted.
`

export default function CLI() {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [copiedItem, setCopiedItem] = useState(null)

  useEffect(() => {
    fetch('/api/cli-info')
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setInfo)
      .catch(e => setError(e.message))
  }, [])

  const copy = async (key, text) => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return
    try {
      await navigator.clipboard.writeText(text)
      setCopiedItem(key)
      setTimeout(() => setCopiedItem(c => c === key ? null : c), 1500)
    } catch {}
  }

  const apiKeyDisplay = info?.api_key
    ? (revealed ? info.api_key : info.api_key.slice(0, 4) + '…'.padEnd(Math.max(0, info.api_key.length - 8), '•') + info.api_key.slice(-4))
    : '—'

  const endpoint = info?.endpoint || '…'

  const curlChat = `curl ${endpoint}/chat/completions \\
  -H "Authorization: Bearer $BRAIN_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Hello brain."}],
    "stream": false
  }'`

  const curlList = `curl ${endpoint}/health`

  const exportEnv = `export BRAIN_ENDPOINT="${endpoint}"
export BRAIN_API_KEY="<paste-your-key>"`

  return (
    <div style={{
      maxWidth: '880px',
      margin: '0 auto',
      padding: '40px 32px 80px',
      color: 'var(--text)',
      fontFamily: 'var(--font-body)',
      lineHeight: 1.6,
    }}>
      <MessageRenderer content={CLI_INTRO} />

      {error && (
        <div style={{
          padding: '12px 16px',
          margin: '16px 0',
          background: 'var(--surface)',
          border: '1px solid #c87878',
          borderRadius: '8px',
          color: '#c87878',
          fontSize: '13px',
        }}>
          Couldn't load CLI info: {error}. The page below uses placeholders.
        </div>
      )}

      {/* Endpoint card */}
      <div style={{ ...card, marginTop: '24px' }}>
        <Label>Endpoint</Label>
        <Row>
          <code style={codeStyle}>{endpoint}</code>
          <SmallButton onClick={() => copy('endpoint', endpoint)}>
            {copiedItem === 'endpoint' ? 'copied' : 'copy'}
          </SmallButton>
        </Row>
      </div>

      {/* API key card */}
      <div style={{ ...card, marginTop: '12px' }}>
        <Label>API key</Label>
        <Row>
          <code style={{ ...codeStyle, fontFamily: 'var(--font-mono)' }}>{apiKeyDisplay}</code>
          <SmallButton onClick={() => setRevealed(r => !r)} disabled={!info?.api_key}>
            {revealed ? 'hide' : 'reveal'}
          </SmallButton>
          <SmallButton onClick={() => copy('apikey', info?.api_key || '')} disabled={!info?.api_key}>
            {copiedItem === 'apikey' ? 'copied' : 'copy'}
          </SmallButton>
        </Row>
        {!info?.api_key_configured && (
          <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--muted)' }}>
            No API key set on this brain. Configure <code style={inlineCode}>BRAIN_API_KEY</code> in the api container's environment.
          </div>
        )}
      </div>

      <MessageRenderer content={SECURITY_NOTE} />

      {/* Quickstart */}
      <h2 style={h2Style}>Quickstart</h2>
      <p>1. Set environment variables in your shell:</p>
      <CodeBlock language="bash" content={exportEnv} onCopy={() => copy('env', exportEnv)} copied={copiedItem === 'env'} />

      <p>2. Hit <code style={inlineCode}>/health</code> to verify reachability:</p>
      <CodeBlock language="bash" content={curlList} onCopy={() => copy('health', curlList)} copied={copiedItem === 'health'} />

      <p>3. Send a chat completion (operator chat, OpenAI-compatible):</p>
      <CodeBlock language="bash" content={curlChat} onCopy={() => copy('curl', curlChat)} copied={copiedItem === 'curl'} />

      {/* Coming soon */}
      <div style={{
        ...card,
        marginTop: '32px',
        borderStyle: 'dashed',
      }}>
        <Label>Coming next: embedded console</Label>
        <div style={{ fontSize: '14px', color: 'var(--muted)' }}>
          Drop a Claude Code session (or any agent harness) directly into a tab inside the brain UI, scoped to this brain's API. No SSH, no local terminal — the console runs in-page and logs every command for audit. Scoped for the next UI pass.
        </div>
      </div>
    </div>
  )
}

// ---- helpers ----------------------------------------------------------

const card = {
  padding: '16px 20px',
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: '10px',
}

const codeStyle = {
  flex: 1,
  fontFamily: 'var(--font-mono)',
  fontSize: '13px',
  background: 'var(--code-bg)',
  color: 'var(--code-fg)',
  padding: '8px 12px',
  borderRadius: '6px',
  border: '1px solid var(--border)',
  overflowX: 'auto',
  whiteSpace: 'nowrap',
}

const inlineCode = {
  fontFamily: 'var(--font-mono)',
  fontSize: '0.9em',
  padding: '1px 6px',
  borderRadius: '4px',
  background: 'rgba(0,0,0,0.18)',
}

const h2Style = {
  fontFamily: 'var(--font-display)',
  fontSize: '1.2em',
  fontWeight: 600,
  margin: '36px 0 12px',
}

function Label({ children }) {
  return (
    <div style={{
      fontSize: '11px',
      fontWeight: 600,
      color: 'var(--muted)',
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      marginBottom: '8px',
    }}>{children}</div>
  )
}

function Row({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>{children}</div>
  )
}

function SmallButton({ onClick, disabled, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        background: 'none',
        border: '1px solid var(--border)',
        color: disabled ? 'var(--muted)' : 'var(--accent)',
        padding: '4px 10px',
        borderRadius: '4px',
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background 0.12s ease',
      }}
      onMouseOver={e => { if (!disabled) e.currentTarget.style.background = 'var(--bg)' }}
      onMouseOut={e => { e.currentTarget.style.background = 'none' }}
    >{children}</button>
  )
}

function CodeBlock({ content, onCopy, copied }) {
  return (
    <div style={{
      position: 'relative',
      margin: '8px 0 16px',
    }}>
      <pre style={{
        background: 'var(--code-bg)',
        color: 'var(--code-fg)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '14px 16px',
        margin: 0,
        overflowX: 'auto',
        fontFamily: 'var(--font-mono)',
        fontSize: '13px',
        lineHeight: 1.5,
      }}>{content}</pre>
      <button
        type="button"
        onClick={onCopy}
        style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          color: 'var(--accent)',
          padding: '3px 9px',
          borderRadius: '4px',
          fontSize: '11px',
          fontFamily: 'var(--font-mono)',
          cursor: 'pointer',
        }}
      >{copied ? 'copied' : 'copy'}</button>
    </div>
  )
}
