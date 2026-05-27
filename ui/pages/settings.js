import { useEffect, useState } from 'react'

const API = '/api/bf'

// Theme + font lists kept in sync with chat.js (THEME_OPTIONS / FONT_OPTIONS).
// Same localStorage keys + data-attribute approach so a theme set from
// Settings persists to chat and vice versa.
const APPEARANCE_THEMES = [
  { value: 'gold',     label: 'gold',     swatch: '#c9a96e' },
  { value: 'paper',    label: 'paper',    swatch: '#8a6e3c' },
  { value: 'sapphire', label: 'sapphire', swatch: '#6b8cce' },
  { value: 'forest',   label: 'forest',   swatch: '#88a868' },
  { value: 'crimson',  label: 'crimson',  swatch: '#c87878' },
  { value: 'mono',     label: 'mono',     swatch: '#b0b0b0' },
  { value: 'fox',      label: 'fox',      swatch: '#d77a3a' },
  { value: 'octopus',  label: 'octopus',  swatch: '#3a9ea0' },
  { value: 'owl',      label: 'owl',      swatch: '#5b4d80' },
]

const APPEARANCE_FONTS = [
  { value: 'system',    label: 'System sans' },
  { value: 'inter',     label: 'Inter' },
  { value: 'lora',      label: 'Lora' },
  { value: 'crimson',   label: 'Crimson Pro' },
  { value: 'dm-mono',   label: 'DM Mono' },
  { value: 'jetbrains', label: 'JetBrains Mono' },
]
const FONT_MIGRATION = { ui: 'system', serif: 'lora', mono: 'dm-mono' }

const APPEARANCE_NAV_SIZES = [
  { value: 'compact',     label: 'compact',     note: '40px' },
  { value: 'normal',      label: 'normal',      note: '52px' },
  { value: 'comfortable', label: 'comfortable', note: '64px' },
]

function AppearancePanel() {
  const [theme, setTheme] = useState('gold')
  const [font, setFont] = useState('system')
  const [navSize, setNavSize] = useState('normal')

  useEffect(() => {
    if (typeof window === 'undefined') return
    setTheme(localStorage.getItem('bf-theme') || 'gold')
    const storedFont = localStorage.getItem('bf-font') || 'system'
    setFont(FONT_MIGRATION[storedFont] || storedFont)
    setNavSize(localStorage.getItem('bf-nav-size') || 'normal')
  }, [])

  const applyTheme = (val) => {
    setTheme(val)
    if (typeof window === 'undefined') return
    localStorage.setItem('bf-theme', val)
    document.documentElement.dataset.theme = val
  }

  const applyFont = (val) => {
    setFont(val)
    if (typeof window === 'undefined') return
    localStorage.setItem('bf-font', val)
    document.documentElement.dataset.font = val
  }

  const applyNavSize = (val) => {
    setNavSize(val)
    if (typeof window === 'undefined') return
    localStorage.setItem('bf-nav-size', val)
    document.documentElement.dataset.navSize = val
  }

  return (
    <div style={{ paddingTop: 14, color: '#8b7d6e', fontSize: 13, lineHeight: 1.6 }}>
      <p style={{ margin: '0 0 14px 0' }}>
        Set the chat surface's palette and typography. Saved per-browser
        (localStorage); chat picker stays in sync.
      </p>

      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 12, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
          Theme
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {APPEARANCE_THEMES.map(t => (
            <button
              key={t.value}
              onClick={() => applyTheme(t.value)}
              title={t.label}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 12px 6px 8px',
                background: theme === t.value ? '#1f1a14' : 'transparent',
                color: theme === t.value ? '#e8e0d5' : '#8b7d6e',
                border: `1px solid ${theme === t.value ? '#c9a96e66' : '#2a2420'}`,
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                fontFamily: 'DM Mono, monospace',
              }}
            >
              <span style={{
                width: 14, height: 14, borderRadius: '50%',
                background: t.swatch, border: '1px solid rgba(0,0,0,0.3)',
                display: 'inline-block',
              }} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 12, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
          Font
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {APPEARANCE_FONTS.map(f => (
            <button
              key={f.value}
              onClick={() => applyFont(f.value)}
              style={{
                padding: '6px 12px',
                background: font === f.value ? '#1f1a14' : 'transparent',
                color: font === f.value ? '#e8e0d5' : '#8b7d6e',
                border: `1px solid ${font === f.value ? '#c9a96e66' : '#2a2420'}`,
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontSize: 12, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
          Header size
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {APPEARANCE_NAV_SIZES.map(n => (
            <button
              key={n.value}
              onClick={() => applyNavSize(n.value)}
              style={{
                padding: '6px 12px',
                background: navSize === n.value ? '#1f1a14' : 'transparent',
                color: navSize === n.value ? '#e8e0d5' : '#8b7d6e',
                border: `1px solid ${navSize === n.value ? '#c9a96e66' : '#2a2420'}`,
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 13,
                display: 'flex', alignItems: 'baseline', gap: 6,
              }}
            >
              <span>{n.label}</span>
              <span style={{ fontSize: 11, color: '#6b5f52', fontFamily: 'DM Mono, monospace' }}>{n.note}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const PROVIDER_LABELS = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI (GPT, o-series)',
  gemini: 'Google Gemini',
  xai: 'xAI (Grok)',
  groq: 'Groq',
  openrouter: 'OpenRouter',
  together: 'Together.ai',
  mistral: 'Mistral',
}

// Sovereign/BYOK note: no key of yours ever leaves your brain.
// Your brain calls these providers directly; BrainFoundry is not in the path.

async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...opts,
  })
  if (!r.ok) {
    let detail = ''
    try {
      const text = await r.text()
      try {
        const body = JSON.parse(text)
        // Brain wraps HTTPException(detail) as body.error.details.detail.
        // Plain FastAPI errors arrive as body.detail. Try both.
        const inner = body?.error?.details?.detail ?? body?.detail
        if (typeof inner === 'string') {
          detail = inner
        } else if (inner && typeof inner === 'object') {
          const code = inner.error || inner.code || ''
          const msg = inner.stderr || inner.message
            || (Array.isArray(inner.issues) && JSON.stringify(inner.issues))
          detail = code && msg ? `${code}: ${msg}` : (code || msg || JSON.stringify(inner))
        } else {
          detail = body?.error?.message || text
        }
      } catch {
        detail = text
      }
      detail = String(detail).replace(/\s+/g, ' ').trim().slice(0, 400)
    } catch {
      // network error reading body — fall through to bare status
    }
    throw new Error(detail ? `${path} ${r.status}: ${detail}` : `${path} ${r.status}`)
  }
  return r.json()
}

function Section({ title, subtitle, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div style={{
      backgroundColor: '#161310',
      border: '1px solid #2a2420',
      borderRadius: 10,
      marginBottom: 16,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%',
          textAlign: 'left',
          background: 'transparent',
          border: 'none',
          padding: '18px 22px',
          cursor: 'pointer',
          color: '#e8e0d5',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <div style={{ fontFamily: 'Lora, Georgia, serif', fontSize: 18, fontWeight: 600 }}>
            {title}
          </div>
          {subtitle && (
            <div style={{ fontSize: 12, color: '#6b5f52', marginTop: 4, fontStyle: 'italic' }}>
              {subtitle}
            </div>
          )}
        </div>
        <span style={{ color: '#c9a96e', fontFamily: 'DM Mono, monospace', fontSize: 14 }}>
          {open ? '–' : '+'}
        </span>
      </button>
      {open && (
        <div style={{ padding: '0 22px 22px 22px', borderTop: '1px solid #2a2420' }}>
          {children}
        </div>
      )}
    </div>
  )
}

const INPUT = {
  background: '#0e0c0b',
  border: '1px solid #2a2420',
  borderRadius: 6,
  color: '#e8e0d5',
  padding: '8px 12px',
  fontSize: 13,
  fontFamily: 'DM Mono, monospace',
  outline: 'none',
}
const BTN = {
  background: '#c9a96e',
  color: '#0e0c0b',
  border: 'none',
  borderRadius: 6,
  padding: '8px 16px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  fontFamily: 'system-ui, sans-serif',
}
const BTN_GHOST = {
  ...BTN,
  background: 'transparent',
  color: '#c9a96e',
  border: '1px solid #2a2420',
}

// ---------- Keys ----------
function KeysPanel() {
  const [state, setState] = useState({ providers: [], keys: {} })
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  const load = () => api('/settings/keys').then(setState).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const save = async (provider) => {
    setBusy(provider); setErr(null)
    try {
      await api('/settings/keys', {
        method: 'POST',
        body: JSON.stringify({ provider, key: drafts[provider] || '' }),
      })
      setDrafts(d => ({ ...d, [provider]: '' }))
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  const clear = async (provider) => {
    setBusy(provider); setErr(null)
    try {
      await api('/settings/keys', {
        method: 'POST',
        body: JSON.stringify({ provider, key: '' }),
      })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 18px 0' }}>
        Your brain calls these providers directly. Keys are stored on your brain only —
        BrainFoundry never sees them. Paste the key, save, done — no container restart.
      </p>
      {state.providers.map(p => {
        const current = state.keys[p]
        return (
          <div key={p} style={{
            display: 'grid',
            gridTemplateColumns: '200px 1fr 90px 90px',
            gap: 10,
            alignItems: 'center',
            padding: '10px 0',
            borderBottom: '1px solid #1c1814',
          }}>
            <div style={{ fontSize: 13, color: '#e8e0d5' }}>{PROVIDER_LABELS[p] || p}</div>
            <div>
              {current ? (
                <span style={{
                  fontFamily: 'DM Mono, monospace',
                  fontSize: 12,
                  color: '#c9a96e',
                }}>{current}</span>
              ) : (
                <input
                  type="password"
                  value={drafts[p] || ''}
                  onChange={e => setDrafts(d => ({ ...d, [p]: e.target.value }))}
                  placeholder="paste key…"
                  style={{ ...INPUT, width: '100%' }}
                />
              )}
            </div>
            {!current ? (
              <button style={BTN} disabled={busy === p || !drafts[p]} onClick={() => save(p)}>
                {busy === p ? '…' : 'Save'}
              </button>
            ) : <span />}
            {current && (
              <button style={BTN_GHOST} disabled={busy === p} onClick={() => clear(p)}>
                Clear
              </button>
            )}
          </div>
        )
      })}
      {err && <div style={{ color: '#d97777', fontSize: 12, marginTop: 10 }}>{err}</div>}
    </div>
  )
}

// ---------- Models ----------
function ModelsPanel() {
  const [state, setState] = useState({ active: null, available: [] })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api('/settings/model').then(setState).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const pick = async (m) => {
    setBusy(true); setErr(null)
    try {
      await api('/settings/model', { method: 'POST', body: JSON.stringify({ model: m }) })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  const groups = state.available.reduce((acc, m) => {
    (acc[m.provider] = acc[m.provider] || []).push(m); return acc
  }, {})

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, margin: '0 0 10px 0' }}>
        Active: <span style={{ color: '#c9a96e', fontFamily: 'DM Mono, monospace' }}>
          {state.active || '(none)'}
        </span>
      </p>
      {Object.entries(groups).map(([provider, models]) => (
        <div key={provider} style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
            {provider}{provider === 'ollama' ? ' — local, free' : ' — cloud, metered'}
          </div>
          {models.map(m => (
            <button
              key={m.name}
              onClick={() => pick(m.name)}
              disabled={busy}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                marginBottom: 4,
                padding: '8px 12px',
                background: state.active === m.name ? '#1c1814' : 'transparent',
                border: `1px solid ${state.active === m.name ? '#c9a96e' : '#2a2420'}`,
                borderRadius: 6,
                color: '#e8e0d5',
                fontFamily: 'DM Mono, monospace',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              {m.name}
            </button>
          ))}
        </div>
      ))}
      {err && <div style={{ color: '#d97777', fontSize: 12, marginTop: 10 }}>{err}</div>}
    </div>
  )
}

// ---------- Memory layers ----------
function MemoryPanel() {
  const [layers, setLayers] = useState([])
  const [presets, setPresets] = useState([])
  const [stats, setStats] = useState({})
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [err, setErr] = useState(null)

  const loadStats = () => api('/documents/stats/by-layer').then(d => {
    const map = {}
    for (const row of (d.layers || [])) {
      if (row.layer) map[row.layer] = row
    }
    setStats(map)
  }).catch(() => {})

  const load = () => api('/settings/memory-layers').then(d => {
    setLayers(d.layers || []); setPresets(d.presets || [])
    loadStats()
  }).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const save = async (next) => {
    try {
      await api('/settings/memory-layers', {
        method: 'POST',
        body: JSON.stringify({ layers: next }),
      })
      await load()
    } catch (e) { setErr(e.message) }
  }

  const add = () => {
    if (!name.trim()) {
      setErr('Layer name is required — type a name in the left input, then click Add.')
      return
    }
    if (layers.find(l => l.name === name.trim())) {
      setErr(`Layer "${name.trim()}" already exists.`)
      return
    }
    setErr(null)
    save([...layers, { name: name.trim(), description: desc.trim() }])
    setName(''); setDesc('')
  }
  const remove = (i) => save(layers.filter((_, idx) => idx !== i))
  const addPreset = (p) => {
    if (layers.find(l => l.name === p.name)) return
    save([...layers, p])
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 14px 0' }}>
        Memory layers (also: "zones" or "collections") are how your brain organises
        what it knows about you. Each layer is a themed notebook. Start blank and
        build your mind, or start from a preset.
      </p>
      <p style={{ color: '#6b5f52', fontSize: 12, lineHeight: 1.6, margin: '0 0 14px 0', fontStyle: 'italic' }}>
        Layers are real now (v0.8). Choose a layer when uploading from
        Knowledge, and ask the brain scoped questions by passing
        <code> layers: ["thinking"] </code> in <code>/chat/rag</code>.
      </p>

      {presets.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 12, color: '#6b5f52', marginBottom: 8 }}>Presets:</div>
          {presets.map(p => {
            const already = layers.find(l => l.name === p.name)
            return (
              <button
                key={p.name}
                onClick={() => addPreset(p)}
                disabled={!!already}
                style={{
                  ...BTN_GHOST,
                  marginRight: 8,
                  marginBottom: 8,
                  opacity: already ? 0.35 : 1,
                  cursor: already ? 'default' : 'pointer',
                }}
              >+ {p.name}</button>
            )
          })}
        </div>
      )}

      {layers.map((l, i) => (
        <div key={i} style={{
          padding: '10px 14px',
          border: '1px solid #2a2420',
          borderRadius: 8,
          marginBottom: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ color: '#c9a96e', fontFamily: 'DM Mono, monospace', fontSize: 13 }}>{l.name}</div>
            {l.description && <div style={{ color: '#6b5f52', fontSize: 12, fontStyle: 'italic' }}>{l.description}</div>}
            {(() => {
              const s = stats[l.name]
              if (!s || !s.doc_count) return <div style={{ color: '#4a4038', fontSize: 11, marginTop: 4 }}>no documents yet</div>
              const last = s.last_ingested ? new Date(s.last_ingested).toLocaleDateString() : '—'
              return <div style={{ color: '#6b5f52', fontSize: 11, marginTop: 4 }}>{s.doc_count} doc{s.doc_count === 1 ? '' : 's'} · {s.chunk_count} chunks · last added {last}</div>
            })()}
          </div>
          <button onClick={() => remove(i)} style={BTN_GHOST}>Remove</button>
        </div>
      ))}

      <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '180px 1fr 90px', gap: 8 }}>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="layer name" style={INPUT} />
        <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="what goes in here (optional)" style={INPUT} />
        <button onClick={add} style={BTN}>Add</button>
      </div>
      {err && <div style={{ color: '#d97777', fontSize: 12, marginTop: 10 }}>{err}</div>}
    </div>
  )
}

// ---------- Security & Federation ----------
function SecurityPanel() {
  const [state, setState] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => { api('/settings/federation').then(setState).catch(e => setErr(e.message)) }, [])

  if (err) return <div style={{ color: '#d97777', fontSize: 12, paddingTop: 16 }}>{err}</div>
  if (!state) return null

  const Field = ({ label, value, mono = true, copyable = false }) => (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, color: '#6b5f52', marginBottom: 4 }}>{label}</div>
      <div style={{
        fontFamily: mono ? 'DM Mono, monospace' : 'inherit',
        fontSize: 13,
        color: '#e8e0d5',
        background: '#0e0c0b',
        border: '1px solid #2a2420',
        borderRadius: 6,
        padding: '8px 12px',
        wordBreak: 'break-all',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
      }}>
        <span>{value || '(not set)'}</span>
        {copyable && value && (
          <button style={BTN_GHOST} onClick={() => navigator.clipboard.writeText(value)}>Copy</button>
        )}
      </div>
    </div>
  )

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 18px 0' }}>
        Your brain has an identity. It signs assertions with an ED25519 keypair.
        Peers verify you by fetching your public key from <code>/identity</code>.
        Share the public key freely; never share your private key.
      </p>
      <Field label="Brain ID" value={state.brain_id} />
      <Field label="Public key (ED25519, base64url)" value={state.public_key} copyable />
      <Field label="Console API key configured" value={state.api_key_configured ? 'yes' : 'no'} mono={false} />
      <Field label="Federation HTTP route" value={state.federation_route} />
    </div>
  )
}

// ---------- CLI ----------
function CLIPanel() {
  const [info, setInfo] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [copied, setCopied] = useState(null) // 'key' | 'snippet' | null

  useEffect(() => {
    fetch('/api/cli-info')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setInfo(d))
      .catch(() => {})
  }, [])

  const endpoint = info?.endpoint || (typeof window !== 'undefined' ? `https://${window.location.hostname.replace('console.', '')}` : '')
  const apiKey = info?.api_key || ''
  const masked = apiKey ? '*'.repeat(Math.max(8, apiKey.length - 4)) + apiKey.slice(-4) : '<not configured>'

  const snippet = `pip install hbar
export HBAR_ENDPOINT="${endpoint}"
export HBAR_API_KEY="${revealed ? apiKey : '<paste your API key here — see above>'}"
hbar chat "hello"`

  const copyText = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(label)
      setTimeout(() => setCopied(null), 2000)
    } catch {}
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 14px 0' }}>
        Talk to your brain from your laptop terminal. One-time install, then
        <code> hbar chat </code> anywhere.
      </p>

      {/* Endpoint */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: '#6b5f52', fontFamily: 'DM Mono, monospace', minWidth: 90 }}>Endpoint:</span>
        <code style={{ flex: 1, fontSize: 12, color: '#e8e0d5', background: '#0e0c0b', border: '1px solid #2a2420', padding: '6px 10px', borderRadius: 4, fontFamily: 'DM Mono, monospace', overflowX: 'auto' }}>{endpoint}</code>
        <button onClick={() => copyText(endpoint, 'endpoint')} style={{ ...COPY_BTN, color: copied === 'endpoint' ? '#7fc99c' : '#c9a96e' }}>{copied === 'endpoint' ? 'copied' : 'copy'}</button>
      </div>

      {/* API key with reveal */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: '#6b5f52', fontFamily: 'DM Mono, monospace', minWidth: 90 }}>API key:</span>
        <code style={{ flex: 1, fontSize: 12, color: revealed ? '#e8e0d5' : '#6b5f52', background: '#0e0c0b', border: '1px solid #2a2420', padding: '6px 10px', borderRadius: 4, fontFamily: 'DM Mono, monospace', overflowX: 'auto' }}>{revealed ? apiKey : masked}</code>
        <button onClick={() => setRevealed(r => !r)} style={{ ...COPY_BTN }}>{revealed ? 'hide' : 'reveal'}</button>
        <button onClick={() => copyText(apiKey, 'key')} disabled={!apiKey} style={{ ...COPY_BTN, color: copied === 'key' ? '#7fc99c' : '#c9a96e', opacity: apiKey ? 1 : 0.4 }}>{copied === 'key' ? 'copied' : 'copy'}</button>
      </div>

      {/* Setup snippet */}
      <div style={{ position: 'relative' }}>
        <pre style={{
          background: '#0e0c0b',
          border: '1px solid #2a2420',
          borderRadius: 6,
          padding: 14,
          color: '#e8e0d5',
          fontSize: 12,
          fontFamily: 'DM Mono, monospace',
          overflowX: 'auto',
          margin: 0,
        }}>{snippet}</pre>
        <button
          onClick={() => copyText(snippet, 'snippet')}
          style={{ ...COPY_BTN, position: 'absolute', top: 8, right: 8, color: copied === 'snippet' ? '#7fc99c' : '#c9a96e' }}
        >{copied === 'snippet' ? 'copied' : 'copy block'}</button>
      </div>

      <p style={{ color: '#6b5f52', fontSize: 12, marginTop: 12, lineHeight: 1.55 }}>
        <code>hbar</code> is the BrainFoundry CLI — one binary for every brain.
        Configured with your endpoint + API key above, it talks to
        <em> your </em> brain only. Your API key never leaves your server unless
        you ssh and paste it elsewhere.
      </p>
    </div>
  )
}

const COPY_BTN = {
  padding: '5px 10px',
  background: 'transparent',
  color: '#c9a96e',
  border: '1px solid #c9a96e60',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: 11,
  fontFamily: 'DM Mono, monospace',
}

// ---------- Advanced ----------
// ---------- Apps ----------
// Brain-apps are installed and managed on the Apps page (/apps). This panel
// holds no controls by design — it is a quiet, faded pointer back there.
function AppsPanel() {
  return (
    <div style={{ paddingTop: 16, opacity: 0.68 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.7, margin: 0 }}>
        <span style={{ color: '#c9a96e', fontSize: 15, marginRight: 8 }}>◇</span>
        Brain-apps live on the{' '}
        <a href="/apps" style={{ color: '#c9a96e', textDecoration: 'none' }}>Apps page</a>.
        Install one from a GitHub repo, approve the memory layers and permissions
        it asks for, enable or remove it &mdash; all in one place.
      </p>
      <a href="/apps" style={{
        display: 'inline-block', marginTop: 12, fontSize: 13,
        color: '#c9a96e', textDecoration: 'none',
      }}>Open the Apps page &rarr;</a>
    </div>
  )
}

function AdvancedPanel() {
  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 10px 0' }}>
        The Governance Kernel enforces mutation policy — which changes require a
        permit, which are auto-approved, which are blocked. Most brains never
        touch this. If you know you need it, it's here.
      </p>
      <a href="/admin/kernel" style={{ ...BTN, textDecoration: 'none', display: 'inline-block' }}>
        Open Kernel console →
      </a>
    </div>
  )
}

// ---------- Page ----------
export default function Settings() {
  return (
    <div style={{ padding: '40px 32px', maxWidth: 860, margin: '0 auto' }}>
      <h1 style={{
        fontFamily: 'Lora, Georgia, serif',
        fontSize: 32,
        fontWeight: 600,
        margin: '0 0 6px 0',
        color: '#e8e0d5',
      }}>Settings</h1>
      <p style={{ color: '#6b5f52', fontStyle: 'italic', margin: '0 0 28px 0' }}>
        Your brain, your keys, your memory. Nothing here leaves this server
        without you telling it to.
      </p>

      <Section
        title="About your brain"
        subtitle="What this place is, one paragraph."
        defaultOpen={true}
      >
        <p style={{ color: '#e8e0d5', fontSize: 14, lineHeight: 1.7, paddingTop: 14 }}>
          This is <b>your brain</b>. Not a chat product — an instance you own,
          running on your server, answering to nobody but you. It remembers what
          you teach it (memory layers), it answers using models you pick
          (local or cloud), and it can vouch for you to other brains
          (federation). Build it up deliberately. What goes in shapes what comes
          out.
        </p>
      </Section>

      <Section title="Persona" subtitle="The brain's system prompt — who it is, how it thinks.">
        <div style={{ paddingTop: 14, color: '#8b7d6e', fontSize: 13, lineHeight: 1.7 }}>
          <div>Your persona is the document loaded on every chat turn.</div>
          <div>Edit it freely — saving takes effect on the next message.</div>
          <a href="/persona" style={{
            display: 'inline-block', marginTop: 12, padding: '8px 16px',
            color: '#0e0c0b', background: '#c9a96e', borderRadius: 8,
            textDecoration: 'none', fontSize: 13, fontWeight: 600,
          }}>Open the persona editor</a>
        </div>
      </Section>

      <Section title="Appearance" subtitle="Palette and typography for the chat surface.">
        <AppearancePanel />
      </Section>

      <Section title="Keys" subtitle="Bring your own — Anthropic, OpenAI, Gemini, and more.">
        <KeysPanel />
      </Section>

      <Section title="Models" subtitle="Local Ollama is free. Cloud providers unlock when keyed.">
        <ModelsPanel />
      </Section>

      <Section title="Memory layers" subtitle="Your themed notebooks — the shape of what your brain knows.">
        <MemoryPanel />
      </Section>

      <Section title="Apps" subtitle="Sandboxed iframe extensions that add tabs to your brain. Installed and managed on the Apps page.">
        <AppsPanel />
      </Section>

      <Section title="Security & Federation" subtitle="Brain identity, public key, how other brains verify you.">
        <SecurityPanel />
      </Section>

      <Section title="CLI access" subtitle="Talk to your brain from the terminal.">
        <CLIPanel />
      </Section>

      <Section title="Advanced: Governance Kernel" subtitle="Mutation policy. Most brains don't need this.">
        <AdvancedPanel />
      </Section>
    </div>
  )
}
