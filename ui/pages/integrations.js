import Head from 'next/head'
import { useEffect, useState } from 'react'

const API = '/api/bf'

async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...opts,
  })
  if (!r.ok) {
    let detail = ''
    try {
      const body = JSON.parse(await r.text())
      detail = body?.error?.details?.detail ?? body?.detail ?? ''
    } catch {}
    throw new Error(detail || `HTTP ${r.status}`)
  }
  return r.json()
}

function Cap({ label, desc, tool, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0' }}>
      <span style={{ width: 16, color: active ? '#1f9d55' : '#5a5046', flexShrink: 0 }}>{active ? '✓' : '○'}</span>
      <div>
        <div style={{ fontSize: 13, color: '#e8e0d5' }}>{label} <span style={{ color: '#6b5f52', fontFamily: 'var(--font-mono, monospace)', fontSize: 11 }}>{tool}</span></div>
        <div style={{ fontSize: 12, color: '#9a8c7a', marginTop: 1 }}>{desc}</div>
      </div>
    </div>
  )
}

function EmailCard() {
  const [status, setStatus] = useState(null)
  const [user, setUser] = useState('')
  const [pass, setPass] = useState('')
  const [host, setHost] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api('/integrations/email/status').then(setStatus).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/integrations/email/account', {
        method: 'POST',
        body: JSON.stringify({ user: user.trim(), password: pass.trim(), host: host.trim() }),
      })
      if (r.ok) { setStatus(r); setPass('') }
      else { setErr(r.error || 'Could not connect'); setStatus(r) }
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const disconnect = async () => {
    setBusy(true); setErr(null)
    try { await api('/integrations/email/disconnect', { method: 'POST' }); await load() }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const connected = status?.configured
  const inp = { background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }
  const btnGhost = { background: 'transparent', color: '#c9a96e', border: '1px solid #3a3128', padding: '9px 18px', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }

  return (
    <div style={{ border: '1px solid #1c1814', borderRadius: 12, background: '#120f0c', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <span style={{ fontSize: 26 }} aria-hidden>✉️</span>
          <div>
            <div style={{ fontSize: 15, color: '#f0e8da', fontWeight: 600 }}>Email <span style={{ fontSize: 11, color: '#6b5f52', fontWeight: 400 }}>· IMAP, any provider</span></div>
            <div style={{ fontSize: 12.5, color: connected ? '#1f9d55' : '#9a8c7a', marginTop: 2 }}>
              {connected ? `Connected · ${status.user} (${status.host})` : 'Not connected'}
            </div>
          </div>
        </div>
        {connected && <button onClick={disconnect} disabled={busy} style={btnGhost}>Disconnect</button>}
      </div>

      {connected && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <Cap label="Inbox" desc="read recent / unread mail, search" tool="inbox_read" active />
        </div>
      )}

      {!connected && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Connect with an app password — no OAuth
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 460 }}>
            <input value={user} onChange={e => setUser(e.target.value)} placeholder="you@gmail.com" style={inp} />
            <input value={pass} onChange={e => setPass(e.target.value)} placeholder="app password (16 chars for Gmail)" type="password" style={inp} />
            <input value={host} onChange={e => setHost(e.target.value)} placeholder="IMAP host (auto-detected for Gmail/Outlook/iCloud…)" style={inp} />
            <div>
              <button onClick={save} disabled={busy || !user.trim() || !pass.trim()}
                style={{ background: (user.trim() && pass.trim()) ? '#c9a96e' : '#221c16', color: (user.trim() && pass.trim()) ? '#1a1510' : '#6b5f52', border: 'none', padding: '8px 16px', borderRadius: 8, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
                {busy ? 'Connecting…' : 'Connect email'}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, color: '#6b5f52', fontSize: 12, lineHeight: 1.6 }}>
            Gmail: turn on 2-step verification → <b>App passwords</b> → generate one → paste it above
            (not your normal password). Read-only; your brain treats every email as untrusted data.
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, color: '#c0392b', fontSize: 12 }}>{err}</div>}
    </div>
  )
}

function CalendarCard() {
  const [status, setStatus] = useState(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api('/integrations/calendar/status').then(setStatus).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/integrations/calendar/ics', { method: 'POST', body: JSON.stringify({ url: url.trim() }) })
      if (r.ok) { setStatus(r); setUrl('') } else { setErr(r.error || 'Could not read that calendar'); setStatus(r) }
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const disconnect = async () => {
    setBusy(true); setErr(null)
    try { await api('/integrations/calendar/ics', { method: 'POST', body: JSON.stringify({ url: '' }) }); await load() }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const connected = status?.configured
  const inp = { background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }
  const btnGhost = { background: 'transparent', color: '#c9a96e', border: '1px solid #3a3128', padding: '9px 18px', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }

  return (
    <div style={{ border: '1px solid #1c1814', borderRadius: 12, background: '#120f0c', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <span style={{ fontSize: 26 }} aria-hidden>📅</span>
          <div>
            <div style={{ fontSize: 15, color: '#f0e8da', fontWeight: 600 }}>Calendar <span style={{ fontSize: 11, color: '#6b5f52', fontWeight: 400 }}>· iCal link, any provider</span></div>
            <div style={{ fontSize: 12.5, color: connected ? '#1f9d55' : '#9a8c7a', marginTop: 2 }}>
              {connected ? `Connected · ${status.host || 'ICS feed'}` : 'Not connected'}
            </div>
          </div>
        </div>
        {connected && <button onClick={disconnect} disabled={busy} style={btnGhost}>Disconnect</button>}
      </div>

      {connected && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <Cap label="Schedule" desc="read upcoming events" tool="calendar_read" active />
        </div>
      )}

      {!connected && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Paste your private iCal (ICS) link — no OAuth
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 520 }}>
            <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://calendar.google.com/calendar/ical/…/private-…/basic.ics" style={inp} />
            <div>
              <button onClick={save} disabled={busy || !url.trim()}
                style={{ background: url.trim() ? '#c9a96e' : '#221c16', color: url.trim() ? '#1a1510' : '#6b5f52', border: 'none', padding: '8px 16px', borderRadius: 8, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
                {busy ? 'Connecting…' : 'Connect calendar'}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, color: '#6b5f52', fontSize: 12, lineHeight: 1.6 }}>
            Google Calendar → Settings → your calendar → <b>“Secret address in iCal format”</b> → copy that
            URL. (Outlook/iCloud have the same “publish/secret ICS” option.) Read-only.
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, color: '#c0392b', fontSize: 12 }}>{err}</div>}
    </div>
  )
}

function GoogleCard() {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [cid, setCid] = useState('')
  const [csecret, setCsecret] = useState('')

  const load = () => api('/integrations/google/status').then(setStatus).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const saveClient = async () => {
    setBusy(true); setErr(null)
    try {
      const s = await api('/integrations/google/client', {
        method: 'POST',
        body: JSON.stringify({ client_id: cid.trim(), client_secret: csecret.trim() }),
      })
      setStatus(s); setCsecret('')
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const connect = async () => {
    setBusy(true); setErr(null)
    try {
      const { auth_url } = await api('/integrations/google/auth-url', { method: 'POST' })
      window.open(auth_url, '_blank', 'noopener')
      let tries = 0
      const iv = setInterval(async () => {
        tries++
        try {
          const s = await api('/integrations/google/status')
          if (s.connected) { setStatus(s); clearInterval(iv); setBusy(false) }
        } catch {}
        if (tries > 45) { clearInterval(iv); setBusy(false); load() }
      }, 2000)
    } catch (e) { setErr(e.message); setBusy(false) }
  }

  const disconnect = async () => {
    setBusy(true); setErr(null)
    try { await api('/integrations/google/disconnect', { method: 'POST' }); await load() }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const connected = status?.connected
  const configured = status?.configured
  const caps = status?.capabilities || [
    { key: 'calendar', label: 'Calendar', tool: 'calendar_read', desc: 'upcoming events' },
    { key: 'gmail', label: 'Gmail', tool: 'gmail_read', desc: 'recent mail (with search)' },
    { key: 'drive', label: 'Drive', tool: 'drive_search', desc: 'find files by name or content' },
  ]
  const btnPrimary = { background: '#c9a96e', color: '#1a1510', border: 'none', padding: '9px 18px', borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }
  const btnGhost = { background: 'transparent', color: '#c9a96e', border: '1px solid #3a3128', padding: '9px 18px', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }
  const btnDisabled = { ...btnPrimary, background: '#221c16', color: '#6b5f52', cursor: 'default' }

  return (
    <div style={{ border: '1px solid #1c1814', borderRadius: 12, background: '#120f0c', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <span style={{ fontSize: 26 }} aria-hidden>🗂️</span>
          <div>
            <div style={{ fontSize: 15, color: '#f0e8da', fontWeight: 600 }}>Google Drive <span style={{ fontSize: 11, color: '#6b5f52', fontWeight: 400 }}>· optional</span></div>
            <div style={{ fontSize: 12.5, color: connected ? '#1f9d55' : '#9a8c7a', marginTop: 2 }}>
              {!configured ? 'Only needed for Drive file search — email & calendar are already set up above without OAuth'
                : connected ? `Connected${status.email ? ' · ' + status.email : ''}`
                  : 'Configured — not connected yet'}
            </div>
          </div>
        </div>
        {connected
          ? <button onClick={disconnect} disabled={busy} style={btnGhost}>Disconnect</button>
          : <button onClick={connect} disabled={busy || !configured} style={configured ? btnPrimary : btnDisabled}>{busy ? 'Connecting…' : 'Connect Google'}</button>}
      </div>

      <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
        <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
          One connection · three capabilities (read-only)
        </div>
        {caps.map(c => <Cap key={c.key} label={c.label} desc={c.desc} tool={c.tool} active={connected} />)}
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: '#6b5f52', lineHeight: 1.6 }}>
        Your email, invites, and files enter as <b>untrusted data</b> — the brain reasons over them but
        never obeys instructions hidden inside them. Read-only: there is no send, modify, or delete path.
      </div>

      {!configured && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Operator setup — paste your Google OAuth client
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 460 }}>
            <input value={cid} onChange={e => setCid(e.target.value)} placeholder="Client ID (…apps.googleusercontent.com)"
              style={{ background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }} />
            <input value={csecret} onChange={e => setCsecret(e.target.value)} placeholder="Client Secret" type="password"
              style={{ background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }} />
            <div>
              <button onClick={saveClient} disabled={busy || !cid.trim() || !csecret.trim()}
                style={{ background: (cid.trim() && csecret.trim()) ? '#c9a96e' : '#221c16', color: (cid.trim() && csecret.trim()) ? '#1a1510' : '#6b5f52', border: 'none', padding: '8px 16px', borderRadius: 8, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
                {busy ? 'Saving…' : 'Save client'}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, color: '#6b5f52', fontSize: 12, lineHeight: 1.6 }}>
            In Google Cloud: enable Gmail + Calendar + Drive APIs, add yourself as an OAuth test user,
            and create an OAuth <b>Web</b> client with this exact redirect URI:
            <br /><code style={{ color: '#9a8c7a' }}>{status?.redirect_uri || '<api>/integrations/google/callback'}</code>
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, color: '#c0392b', fontSize: 12 }}>{err}</div>}
    </div>
  )
}

function TelegramCard() {
  const [status, setStatus] = useState(null)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api('/integrations/telegram/status').then(setStatus).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const connect = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/integrations/telegram/connect', { method: 'POST', body: JSON.stringify({ token: token.trim() }) })
      if (r.ok) { setToken(''); await load() } else { setErr(r.error || 'Could not connect') }
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const disconnect = async () => {
    setBusy(true); setErr(null)
    try { await api('/integrations/telegram/disconnect', { method: 'POST' }); await load() }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const connected = status?.configured
  const inp = { background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }
  const btnGhost = { background: 'transparent', color: '#c9a96e', border: '1px solid #3a3128', padding: '9px 18px', borderRadius: 8, fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }

  return (
    <div style={{ border: '1px solid #1c1814', borderRadius: 12, background: '#120f0c', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <span style={{ fontSize: 26 }} aria-hidden>💬</span>
          <div>
            <div style={{ fontSize: 15, color: '#f0e8da', fontWeight: 600 }}>Telegram <span style={{ fontSize: 11, color: '#6b5f52', fontWeight: 400 }}>· chat your brain from your phone</span></div>
            <div style={{ fontSize: 12.5, color: connected ? '#1f9d55' : '#9a8c7a', marginTop: 2 }}>
              {connected ? `Connected · @${status.username} — open it and say hi` : 'Not connected'}
            </div>
          </div>
        </div>
        {connected && <button onClick={disconnect} disabled={busy} style={btnGhost}>Disconnect</button>}
      </div>

      {!connected && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #1c1814' }}>
          <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            Paste your bot token from @BotFather
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 520 }}>
            <input value={token} onChange={e => setToken(e.target.value)} placeholder="123456789:ABCdef… (from @BotFather)" type="password" style={inp} />
            <div>
              <button onClick={connect} disabled={busy || !token.trim()}
                style={{ background: token.trim() ? '#c9a96e' : '#221c16', color: token.trim() ? '#1a1510' : '#6b5f52', border: 'none', padding: '8px 16px', borderRadius: 8, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
                {busy ? 'Connecting…' : 'Connect Telegram'}
              </button>
            </div>
          </div>
          <div style={{ marginTop: 12, color: '#6b5f52', fontSize: 12, lineHeight: 1.6 }}>
            In Telegram, message <b>@BotFather</b> → <code style={{ color: '#9a8c7a' }}>/newbot</code> → name it → copy the
            token. The first chat that messages your bot becomes its owner; strangers are refused.
          </div>
        </div>
      )}
      {err && <div style={{ marginTop: 12, color: '#c0392b', fontSize: 12 }}>{err}</div>}
    </div>
  )
}

function McpCard() {
  const [status, setStatus] = useState(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [auth, setAuth] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api('/integrations/mcp/status').then(setStatus).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const connect = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/integrations/mcp/connect', { method: 'POST', body: JSON.stringify({ name: name.trim(), url: url.trim(), auth: auth.trim() }) })
      if (r.ok) { setName(''); setUrl(''); setAuth(''); await load() } else { setErr(r.error || 'Could not connect') }
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const disconnect = async (srv) => {
    setBusy(true); setErr(null)
    try { await api('/integrations/mcp/disconnect', { method: 'POST', body: JSON.stringify({ name: srv }) }); await load() }
    catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const servers = status?.servers || []
  const inp = { background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 7, color: '#e8e0d5', padding: '8px 10px', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }
  const btnGhost = { background: 'transparent', color: '#c9a96e', border: '1px solid #3a3128', padding: '6px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }

  return (
    <div style={{ border: '1px solid #1c1814', borderRadius: 12, background: '#120f0c', padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
        <span style={{ fontSize: 26 }} aria-hidden>🔌</span>
        <div>
          <div style={{ fontSize: 15, color: '#f0e8da', fontWeight: 600 }}>MCP servers <span style={{ fontSize: 11, color: '#6b5f52', fontWeight: 400 }}>· connect any tool</span></div>
          <div style={{ fontSize: 12.5, color: servers.length ? '#1f9d55' : '#9a8c7a', marginTop: 2 }}>
            {servers.length ? `${servers.length} connected` : 'None connected'}
          </div>
        </div>
      </div>

      {servers.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #1c1814', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {servers.map(s => (
            <div key={s.name} style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
              <div>
                <div style={{ fontSize: 13, color: '#e8e0d5' }}>{s.name} <span style={{ color: '#6b5f52', fontSize: 11 }}>{s.tools.length} tool{s.tools.length === 1 ? '' : 's'}</span></div>
                <div style={{ fontSize: 11.5, color: '#9a8c7a', marginTop: 2, fontFamily: 'var(--font-mono, monospace)' }}>{s.tools.slice(0, 8).join(', ')}</div>
              </div>
              <button onClick={() => disconnect(s.name)} disabled={busy} style={btnGhost}>Remove</button>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #1c1814' }}>
        <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Add a server (HTTP)</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 520 }}>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="name (e.g. github)" style={inp} />
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://…/mcp  (server endpoint URL)" style={inp} />
          <input value={auth} onChange={e => setAuth(e.target.value)} placeholder="Authorization header (optional, e.g. Bearer …)" type="password" style={inp} />
          <div>
            <button onClick={connect} disabled={busy || !url.trim()}
              style={{ background: url.trim() ? '#c9a96e' : '#221c16', color: url.trim() ? '#1a1510' : '#6b5f52', border: 'none', padding: '8px 16px', borderRadius: 8, fontWeight: 600, fontSize: 12.5, cursor: 'pointer', fontFamily: 'inherit' }}>
              {busy ? 'Connecting…' : 'Connect server'}
            </button>
          </div>
        </div>
        <div style={{ marginTop: 12, color: '#6b5f52', fontSize: 12, lineHeight: 1.6 }}>
          The server's tools become available to your brain in agentic mode. Tool output is treated as
          untrusted. You connect servers — the model can't add them.
        </div>
      </div>
      {err && <div style={{ marginTop: 12, color: '#c0392b', fontSize: 12 }}>{err}</div>}
    </div>
  )
}

function ComingSoon({ icon, name, detail }) {
  return (
    <div style={{ border: '1px dashed #221c16', borderRadius: 12, background: '#0e0c0a', padding: 20, opacity: 0.7 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <span style={{ fontSize: 26 }} aria-hidden>{icon}</span>
          <div>
            <div style={{ fontSize: 15, color: '#cabfb0', fontWeight: 600 }}>{name}</div>
            <div style={{ fontSize: 12.5, color: '#6b5f52', marginTop: 2 }}>{detail}</div>
          </div>
        </div>
        <span style={{ fontSize: 11, color: '#6b5f52', border: '1px solid #2a2420', borderRadius: 6, padding: '3px 9px' }}>planned</span>
      </div>
    </div>
  )
}

export default function Integrations() {
  return (
    <>
      <Head><title>Integrations · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '780px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>
        <h1 style={{ fontSize: 26, color: '#f0e8da', margin: '0 0 6px 0' }}>Integrations</h1>
        <p style={{ color: '#9a8c7a', fontSize: 14, lineHeight: 1.6, margin: '0 0 26px 0' }}>
          Connect your tools so your brain can act on your real world — read-only, untrusted by default.
          Ask it "what's on my schedule?", "summarize my unread email", or "find my deck about X".
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <EmailCard />
          <CalendarCard />
          <TelegramCard />
          <McpCard />
          <GoogleCard />
          <ComingSoon icon="📅" name="Microsoft" detail="Outlook mail + calendar — a separate connection." />
        </div>
      </div>
    </>
  )
}
