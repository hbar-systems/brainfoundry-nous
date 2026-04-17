import { useEffect, useState } from 'react'

const API = '/api/bf'

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
  if (!r.ok) throw new Error(`${path} ${r.status}`)
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
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 14px 0' }}>
        Talk to your brain from your laptop terminal. One-time install, then
        <code> hbar chat </code> anywhere.
      </p>
      <pre style={{
        background: '#0e0c0b',
        border: '1px solid #2a2420',
        borderRadius: 6,
        padding: 14,
        color: '#e8e0d5',
        fontSize: 12,
        fontFamily: 'DM Mono, monospace',
        overflowX: 'auto',
      }}>
{`pip install hbar
export HBAR_ENDPOINT="${origin}"
export HBAR_API_KEY="<your api key>"
hbar chat "hello"`}
      </pre>
      <p style={{ color: '#6b5f52', fontSize: 12, marginTop: 10 }}>
        <code>hbar</code> is the BrainFoundry CLI — one binary for every brain.
        Configure it with your endpoint and API key above, and it talks to
        <em> your </em> brain only. Your API key is in your brain's <code>.env</code>
        file, or the "Console login password" line of your welcome email.
      </p>
    </div>
  )
}

// ---------- Advanced ----------
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

      <Section title="Keys" subtitle="Bring your own — Anthropic, OpenAI, Gemini, and more.">
        <KeysPanel />
      </Section>

      <Section title="Models" subtitle="Local Ollama is free. Cloud providers unlock when keyed.">
        <ModelsPanel />
      </Section>

      <Section title="Memory layers" subtitle="Your themed notebooks — the shape of what your brain knows.">
        <MemoryPanel />
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
