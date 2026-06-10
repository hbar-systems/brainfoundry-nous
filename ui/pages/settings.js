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

// Header height is a continuous pixel value; the drag handle on the nav
// writes the same localStorage key. 36..88 bounds match Nav.js.
const NAV_H_MIN = 36
const NAV_H_MAX = 88
const NAV_H_DEFAULT = 52

function AppearancePanel() {
  const [theme, setTheme] = useState('gold')
  const [font, setFont] = useState('system')
  const [navH, setNavH] = useState(NAV_H_DEFAULT)

  useEffect(() => {
    if (typeof window === 'undefined') return
    setTheme(localStorage.getItem('bf-theme') || 'gold')
    const storedFont = localStorage.getItem('bf-font') || 'system'
    setFont(FONT_MIGRATION[storedFont] || storedFont)
    const stored = parseInt(localStorage.getItem('bf-nav-h') || '', 10)
    setNavH(Number.isFinite(stored) ? stored : NAV_H_DEFAULT)
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

  const applyNavH = (val) => {
    const n = Math.max(NAV_H_MIN, Math.min(NAV_H_MAX, parseInt(val, 10) || NAV_H_DEFAULT))
    setNavH(n)
    if (typeof window === 'undefined') return
    localStorage.setItem('bf-nav-h', String(n))
    document.documentElement.style.setProperty('--nav-h', `${n}px`)
  }

  const resetNavH = () => {
    setNavH(NAV_H_DEFAULT)
    if (typeof window === 'undefined') return
    localStorage.removeItem('bf-nav-h')
    document.documentElement.style.removeProperty('--nav-h')
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
        <div style={{ fontSize: 12, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span>Header size</span>
          <span style={{ fontFamily: 'DM Mono, monospace', textTransform: 'none', letterSpacing: 0, color: '#c9a96e', fontSize: 11 }}>{navH}px</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 11, color: '#6b5f52' }}>{NAV_H_MIN}</span>
          <input
            type="range"
            min={NAV_H_MIN}
            max={NAV_H_MAX}
            step={1}
            value={navH}
            onChange={(e) => applyNavH(e.target.value)}
            style={{ flex: 1, accentColor: '#c9a96e' }}
          />
          <span style={{ fontSize: 11, color: '#6b5f52' }}>{NAV_H_MAX}</span>
          <button
            onClick={resetNavH}
            title="Reset to default (52px)"
            style={{ background: 'transparent', border: '1px solid #2a2420', color: '#8b7d6e', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontSize: 11, fontFamily: 'DM Mono, monospace' }}
          >
            reset
          </button>
        </div>
        <div style={{ fontSize: 11, color: '#6b5f52', marginTop: 6, fontStyle: 'italic' }}>
          Or drag the bottom edge of the header itself.
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

// ---------- Agentic tools + permission tiers ----------
const TIER_COLOR = { green: '#5fae6b', yellow: '#c9a96e', red: '#d97777' }

function AgenticToolsPanel() {
  const [enabled, setEnabled] = useState(false)
  const [tiers, setTiers] = useState([])
  const [tools, setTools] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => {
    api('/settings/agentic-tools').then(s => setEnabled(!!s.enabled)).catch(e => setErr(e.message))
    api('/tools/tiers').then(d => setTiers(d.tiers || [])).catch(() => {})
    api('/tools').then(d => setTools(d.tools || [])).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const toggle = async () => {
    setBusy(true); setErr(null)
    try {
      await api('/settings/agentic-tools', { method: 'POST', body: JSON.stringify({ enabled: !enabled }) })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 18px 0' }}>
        Let your brain decide for itself when to reach for a tool — search its own memory, or
        the open web — instead of you flipping a switch each message. Off by default. Works on
        cloud models (Claude, GPT, …) AND capable local models (llama3.3:70b, qwen2.5:72b, …) —
        federation never requires a cloud model. A very small local model may just answer without
        calling tools. Every tool call is gated by its permission tier and recorded on the Trace page.
      </p>

      {/* Permission tiers — what green / yellow / red mean (from /tools/tiers). */}
      <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 13 }}>
        <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1 }}>
          What green · yellow · red mean
        </div>
        {tiers.map(t => (
          <div key={t.tier} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: TIER_COLOR[t.tier] || '#888', marginTop: 5, flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: 12.5, color: '#e8e0d5' }}>
                {t.label} — <span style={{ color: TIER_COLOR[t.tier] }}>{t.rule}</span>
              </div>
              <div style={{ fontSize: 12, color: '#9a8c7a', lineHeight: 1.65, marginTop: 2 }}>{t.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Enable toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #1c1814' }}>
        <div style={{ fontSize: 13, color: '#e8e0d5' }}>
          Agentic mode
          <div style={{ fontSize: 12, color: '#6b5f52', marginTop: 2 }}>
            {enabled ? 'On — your brain calls tools on its own judgment.' : 'Off — tools run only when you ask (manual 🌐 toggle).'}
          </div>
        </div>
        <button style={enabled ? BTN : BTN_GHOST} disabled={busy} onClick={toggle}>
          {busy ? '…' : (enabled ? 'On' : 'Off')}
        </button>
      </div>

      {/* Registered tools, dotted by tier */}
      {tools.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ color: '#6b5f52', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Tools your brain can call</div>
          {tools.map(t => (
            <div key={t.name} style={{ display: 'flex', gap: 9, alignItems: 'baseline', padding: '5px 0' }}>
              <span title={t.tier} style={{ width: 8, height: 8, borderRadius: '50%', background: TIER_COLOR[t.tier] || '#888', flexShrink: 0, alignSelf: 'center' }} />
              <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#e8e0d5' }}>{t.name}</span>
              <span style={{ fontSize: 12, color: '#9a8c7a', lineHeight: 1.5 }}>{t.description}</span>
            </div>
          ))}
        </div>
      )}

      {err && <div style={{ color: '#d97777', fontSize: 12, marginTop: 10 }}>{err}</div>}
    </div>
  )
}

// ---------- Web search (tools) ----------
function WebSearchPanel() {
  const [state, setState] = useState({ enabled: false, key_set: false, key_masked: null, budget: 1000, usage_this_month: 0 })
  const [draftKey, setDraftKey] = useState('')
  const [draftBudget, setDraftBudget] = useState('')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const [showHow, setShowHow] = useState(false)

  const load = () => api('/settings/web-search').then(s => { setState(s); setDraftBudget(String(s.budget)) }).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

  const toggle = async () => {
    setBusy('toggle'); setErr(null)
    try {
      await api('/settings/web-search', { method: 'POST', body: JSON.stringify({ enabled: !state.enabled }) })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  const saveKey = async () => {
    setBusy('key'); setErr(null)
    try {
      await api('/settings/web-search/key', { method: 'POST', body: JSON.stringify({ provider: 'brave', key: draftKey }) })
      setDraftKey('')
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  const clearKey = async () => {
    setBusy('key'); setErr(null)
    try {
      await api('/settings/web-search/key', { method: 'POST', body: JSON.stringify({ provider: 'brave', key: '' }) })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  const saveBudget = async () => {
    setBusy('budget'); setErr(null)
    try {
      await api('/settings/web-search', { method: 'POST', body: JSON.stringify({ budget: parseInt(draftBudget, 10) || 0 }) })
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(null)
  }

  return (
    <div style={{ paddingTop: 16 }}>
      <p style={{ color: '#6b5f52', fontSize: 13, lineHeight: 1.6, margin: '0 0 18px 0' }}>
        Let your brain read the open web (Brave Search). A yellow-tier tool: external,
        read-only, off by default. Results enter chat as <em>untrusted</em> reference data —
        cited by URL, never followed as instructions. Get a key at{' '}
        <a href="https://brave.com/search/api/" target="_blank" rel="noreferrer" style={{ color: '#c9a96e' }}>brave.com/search/api</a>;
        it stays on your brain under your own billing.
      </p>

      {/* How it works — collapsed teaching block. Sentence-per-line so each
          idea lands on its own; covers what / safety / corroboration / cost. */}
      <div style={{ marginBottom: 18 }}>
        <button
          onClick={() => setShowHow(v => !v)}
          style={{ background: 'transparent', border: 'none', color: '#c9a96e', cursor: 'pointer', padding: 0, fontSize: 12, fontFamily: 'inherit' }}
        >
          {showHow ? '▾' : '▸'} How it works
        </button>
        {showHow && (
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[
              {
                h: 'What it is',
                lines: [
                  'Your brain can read the live web through Brave Search.',
                  'It stays off until you enable it here.',
                  'It only searches a message when you flip the 🌐 toggle in the chat composer.',
                ],
              },
              {
                h: 'How it stays safe',
                lines: [
                  'Web results enter the conversation as untrusted reference data.',
                  'Your brain reasons over them and cites the source URLs.',
                  'It never follows instructions hidden inside a page.',
                ],
              },
              {
                h: 'Corroboration score',
                lines: [
                  'Each web answer shows a measured corroboration percentage.',
                  'It counts how many independent, trusted sources actually agree.',
                  'It is a measurement of agreement, not a verdict on what is true.',
                ],
              },
              {
                h: 'Cost and control',
                lines: [
                  'Each search is one Brave request; the free tier covers about 1,000 a month.',
                  'The monthly cap below bounds what your brain can spend.',
                  'Every search is recorded in the tool audit trail.',
                ],
              },
            ].map((sec) => (
              <div key={sec.h}>
                <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 5 }}>{sec.h}</div>
                {sec.lines.map((ln, li) => (
                  <div key={li} style={{ color: '#9a8c7a', fontSize: 12.5, lineHeight: 1.7 }}>{ln}</div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Enable toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #1c1814' }}>
        <div style={{ fontSize: 13, color: '#e8e0d5' }}>
          Web search
          <div style={{ fontSize: 12, color: '#6b5f52', marginTop: 2 }}>
            {state.enabled ? 'Enabled — the 🌐 toggle is live in chat.' : 'Disabled.'}
            {state.enabled && !state.key_set && <span style={{ color: '#d9a777' }}> Add a key below to use it.</span>}
          </div>
        </div>
        <button style={state.enabled ? BTN : BTN_GHOST} disabled={busy === 'toggle'} onClick={toggle}>
          {busy === 'toggle' ? '…' : (state.enabled ? 'On' : 'Off')}
        </button>
      </div>

      {/* Brave key */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 90px 90px', gap: 10, alignItems: 'center', padding: '12px 0', borderBottom: '1px solid #1c1814' }}>
        <div style={{ fontSize: 13, color: '#e8e0d5' }}>Brave API key</div>
        <div>
          {state.key_set ? (
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#c9a96e' }}>{state.key_masked}</span>
          ) : (
            <input type="password" value={draftKey} onChange={e => setDraftKey(e.target.value)} placeholder="paste Brave key…" style={{ ...INPUT, width: '100%' }} />
          )}
        </div>
        {!state.key_set
          ? <button style={BTN} disabled={busy === 'key' || !draftKey} onClick={saveKey}>{busy === 'key' ? '…' : 'Save'}</button>
          : <span />}
        {state.key_set && <button style={BTN_GHOST} disabled={busy === 'key'} onClick={clearKey}>Clear</button>}
      </div>

      {/* Monthly budget */}
      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr 90px', gap: 10, alignItems: 'center', padding: '12px 0' }}>
        <div style={{ fontSize: 13, color: '#e8e0d5' }}>
          Monthly cap
          <div style={{ fontSize: 12, color: '#6b5f52', marginTop: 2 }}>{state.usage_this_month} used this month</div>
        </div>
        <input type="number" min={0} value={draftBudget} onChange={e => setDraftBudget(e.target.value)} style={{ ...INPUT, width: 120 }} />
        <button style={BTN} disabled={busy === 'budget'} onClick={saveBudget}>{busy === 'budget' ? '…' : 'Save'}</button>
      </div>

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
  // "Brain proposes scheme" — modal state. proposal holds the LLM-derived
  // taxonomy returned from POST /memory/layers/propose-scheme. Operator
  // accepts (replaces or merges layers), rejects (closes), or edits in
  // place (selective per-layer checkboxes).
  const [proposeOpen, setProposeOpen] = useState(false)
  const [proposeLoading, setProposeLoading] = useState(false)
  const [proposeError, setProposeError] = useState(null)
  const [proposal, setProposal] = useState(null)
  const [proposalSelected, setProposalSelected] = useState({})

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

  // Ask the brain to read the corpus and propose a taxonomy. POSTs to
  // /memory/layers/propose-scheme which samples ~30 most-recent docs +
  // calls the active model with a librarian prompt. Modal opens with the
  // returned scheme; operator picks accept-all / accept-selected / reject.
  const proposeScheme = async () => {
    setProposeOpen(true)
    setProposeLoading(true)
    setProposeError(null)
    setProposal(null); setProposalSelected({})
    try {
      const r = await api('/memory/layers/propose-scheme', { method: 'POST' })
      setProposal(r)
      // All proposed layers selected by default — operator can uncheck.
      const sel = {}
      for (const l of (r.layers || [])) sel[l.name] = true
      setProposalSelected(sel)
    } catch (e) {
      setProposeError(e.message)
    } finally {
      setProposeLoading(false)
    }
  }

  const closeProposal = () => {
    setProposeOpen(false); setProposal(null); setProposalSelected({}); setProposeError(null)
  }

  // Apply: merge the checked proposed layers into the existing list.
  // Skip duplicates (by name) so a previously-added layer keeps its
  // current description.
  const acceptProposal = async () => {
    if (!proposal) return
    const toAdd = (proposal.layers || []).filter(l => proposalSelected[l.name])
    const merged = [...layers]
    for (const l of toAdd) {
      if (!merged.find(x => x.name === l.name)) {
        merged.push({ name: l.name, description: l.description || '' })
      }
    }
    try {
      await save(merged)
      closeProposal()
    } catch (e) { setProposeError(e.message) }
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

      {/* Differentiator surface: after the brain has read enough of your
          corpus to form a model of you, ask IT to propose how the layers
          should be organized. Most AI tools impose structure; we ask first. */}
      <div style={{ marginBottom: 18, padding: '10px 14px', background: '#13110d', border: '1px solid #2a2420', borderRadius: 8 }}>
        <div style={{ fontSize: 12, color: '#c9a96e', marginBottom: 4, fontFamily: 'DM Mono, monospace' }}>
          Let the brain propose a scheme
        </div>
        <div style={{ fontSize: 12, color: '#6b5f52', lineHeight: 1.6, marginBottom: 8 }}>
          Reads up to 30 of your most recently stored documents, then proposes a
          set of themed-notebook layers that fit what you've actually written and
          collected. You pick which to accept.
        </div>
        <button
          onClick={proposeScheme}
          style={{
            background: 'transparent',
            border: '1px solid rgba(201, 169, 110, 0.38)',
            color: '#c9a96e',
            borderRadius: 8,
            padding: '6px 14px',
            cursor: 'pointer',
            fontSize: 12,
            fontFamily: 'DM Mono, monospace',
            letterSpacing: '0.04em',
          }}
        >
          Suggest a scheme →
        </button>
      </div>

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

      {/* Proposal modal — brain's suggested taxonomy. Operator picks which
          to accept via checkboxes, then clicks "Accept selected" to merge
          into existing layers. Rejecting just closes the modal; nothing
          is applied. The "brain proposes, operator confirms" pattern
          from hbar.brain's Store-this spec applies here too. */}
      {proposeOpen && (
        <div style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 200, padding: 20,
        }}>
          <div style={{
            background: '#161310', border: '1px solid #2a2420', borderRadius: 12,
            padding: 24, width: 'min(640px, 100%)', maxHeight: '90vh', overflowY: 'auto',
            color: '#e8e0d5',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h2 style={{ fontSize: 15, fontFamily: 'Lora, Georgia, serif', margin: 0 }}>
                Brain's proposed memory-layer scheme
              </h2>
              <button onClick={closeProposal} style={{ background: 'none', border: 'none', color: '#6b5f52', cursor: 'pointer', fontSize: 18 }}>×</button>
            </div>

            {proposeLoading && !proposal && (
              <div style={{ color: '#6b5f52', fontSize: 13, padding: '20px 0' }}>
                Reading your corpus, drafting a scheme…
              </div>
            )}

            {proposeError && (
              <div style={{ background: '#1a0a0a', border: '1px solid #ff6b6b30', borderRadius: 8, padding: 12, color: '#ff6b6b', fontSize: 12, marginBottom: 12 }}>
                {proposeError}
              </div>
            )}

            {proposal && proposal.empty && (
              <div style={{ color: '#8b7d6e', fontSize: 13, lineHeight: 1.6 }}>
                {proposal.rationale}
              </div>
            )}

            {proposal && !proposal.empty && (
              <>
                <div style={{ fontSize: 12, color: '#8b7d6e', fontStyle: 'italic', marginBottom: 14, lineHeight: 1.5 }}>
                  {proposal.rationale}
                </div>

                <div style={{ marginBottom: 16 }}>
                  {(proposal.layers || []).map(l => (
                    <label
                      key={l.name}
                      style={{
                        display: 'flex', alignItems: 'flex-start', gap: 10,
                        padding: '10px 12px',
                        background: proposalSelected[l.name] ? '#1f1a14' : 'transparent',
                        border: `1px solid ${proposalSelected[l.name] ? '#c9a96e66' : '#2a2420'}`,
                        borderRadius: 8,
                        marginBottom: 8,
                        cursor: 'pointer',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={!!proposalSelected[l.name]}
                        onChange={(e) => setProposalSelected(prev => ({ ...prev, [l.name]: e.target.checked }))}
                        style={{ marginTop: 3, accentColor: '#c9a96e' }}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: '#c9a96e', fontFamily: 'DM Mono, monospace', marginBottom: 4 }}>
                          {l.name}
                          {layers.find(x => x.name === l.name) && (
                            <span style={{ marginLeft: 8, fontSize: 10, color: '#6b5f52', textTransform: 'uppercase', letterSpacing: 1 }}>already added</span>
                          )}
                        </div>
                        <div style={{ fontSize: 12, color: '#8b7d6e', lineHeight: 1.5, marginBottom: 4 }}>{l.description}</div>
                        {(l.example_docs || []).length > 0 && (
                          <div style={{ fontSize: 11, color: '#6b5f52', fontFamily: 'DM Mono, monospace' }}>
                            e.g. {l.example_docs.slice(0, 3).join(', ')}
                          </div>
                        )}
                      </div>
                    </label>
                  ))}
                </div>

                <div style={{ fontSize: 11, color: '#6b5f52', marginBottom: 14, fontStyle: 'italic' }}>
                  Sample size: {proposal.sample_size} most-recent docs · model: {proposal.model}
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button
                    onClick={closeProposal}
                    style={{ background: 'transparent', border: '1px solid #2a2420', color: '#6b5f52', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 12 }}
                  >
                    Reject
                  </button>
                  <button
                    onClick={acceptProposal}
                    disabled={!Object.values(proposalSelected).some(Boolean)}
                    style={{
                      background: Object.values(proposalSelected).some(Boolean) ? '#c9a96e' : '#2a2420',
                      border: 'none',
                      color: Object.values(proposalSelected).some(Boolean) ? '#0e0c0b' : '#6b5f52',
                      borderRadius: 8, padding: '8px 14px',
                      cursor: Object.values(proposalSelected).some(Boolean) ? 'pointer' : 'not-allowed',
                      fontSize: 12, fontWeight: 600,
                    }}
                  >
                    Accept selected
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
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

      <Section title="Web search" subtitle="Give your brain eyes on the open web — read-only, untrusted, off by default.">
        <WebSearchPanel />
      </Section>

      <Section title="Agentic tools" subtitle="Let your brain decide when to use tools — and what green / yellow / red permission tiers mean.">
        <AgenticToolsPanel />
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
