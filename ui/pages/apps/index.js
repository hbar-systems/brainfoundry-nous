import Link from 'next/link'
import { useEffect, useState } from 'react'

// Apps hub — the brain-app surface. A brain-app installs straight from a
// GitHub URL here (no Settings detour), shows up as a card, and is managed
// inline. Settings keeps only a quiet pointer back to this page.
//
// Created: 2026-05-09
// 2026-05-19: install + management moved here from Settings -> Apps.

const API = '/api/bf'

// Compact error-aware fetch. The brain wraps HTTPException(detail) as
// body.error.details.detail; plain FastAPI errors arrive as body.detail.
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
      } catch { detail = text }
      detail = String(detail).replace(/\s+/g, ' ').trim().slice(0, 400)
    } catch { detail = `HTTP ${r.status}` }
    throw new Error(detail || `HTTP ${r.status}`)
  }
  if (r.status === 204) return null
  return r.json()
}

const INPUT = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
  padding: '10px 14px',
  fontSize: 13,
  fontFamily: 'var(--font-mono, DM Mono, monospace)',
  outline: 'none',
}
const BTN = {
  background: 'var(--accent)',
  color: 'var(--bg)',
  border: 'none',
  borderRadius: 8,
  padding: '10px 18px',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
}
const GHOST_BTN = {
  background: 'transparent',
  color: 'var(--accent)',
  border: '1px solid var(--border)',
  borderRadius: 6,
  padding: '6px 12px',
  fontSize: 12,
  cursor: 'pointer',
}

export default function AppsIndex() {
  const [apps, setApps] = useState(null) // null = loading, [] = empty, [...] = loaded
  const [err, setErr] = useState(null)
  const [repoUrl, setRepoUrl] = useState('')
  const [preview, setPreview] = useState(null)        // { manifest, commit_sha }
  const [busy, setBusy] = useState(null)              // 'preview' | 'install' | 'uninstall:<id>' | 'toggle:<id>'
  const [justInstalled, setJustInstalled] = useState(null) // { id, app_token }
  const [updatePreview, setUpdatePreview] = useState(null) // re-approval card for a scope-changing update
  const [notice, setNotice] = useState(null)               // { kind, text } — transient success line

  const load = () =>
    api('/apps/list')
      .then(d => setApps(Array.isArray(d?.apps) ? d.apps : []))
      .catch(e => setErr(String(e.message || e)))
  useEffect(() => { load() }, [])

  const doPreview = async () => {
    if (!repoUrl.trim()) return
    setBusy('preview'); setErr(null); setPreview(null)
    try {
      setPreview(await api('/apps/install/preview', {
        method: 'POST',
        body: JSON.stringify({ repo_url: repoUrl.trim() }),
      }))
    } catch (e) { setErr(`Preview failed: ${e.message}`) }
    setBusy(null)
  }

  const doInstall = async () => {
    if (!preview) return
    setBusy('install'); setErr(null)
    try {
      const r = await api('/apps/install', {
        method: 'POST',
        body: JSON.stringify({ repo_url: repoUrl.trim() }),
      })
      setJustInstalled({ id: r.id, app_token: r.app_token })
      setPreview(null); setRepoUrl('')
      await load()
    } catch (e) { setErr(`Install failed: ${e.message}`) }
    setBusy(null)
  }

  const doUninstall = async (id) => {
    if (!confirm(`Uninstall ${id}? This deletes the app's clone and removes its tab.`)) return
    setBusy(`uninstall:${id}`); setErr(null)
    try {
      await api(`/apps/${id}/uninstall`, { method: 'POST' })
      await load()
    } catch (e) { setErr(`Uninstall failed: ${e.message}`) }
    setBusy(null)
  }

  const doToggle = async (id, enabled) => {
    setBusy(`toggle:${id}`); setErr(null)
    try {
      await api(`/apps/${id}/${enabled ? 'disable' : 'enable'}`, { method: 'POST' })
      await load()
    } catch (e) { setErr(`Toggle failed: ${e.message}`) }
    setBusy(null)
  }

  // Update: check repo HEAD. Already-latest -> a notice. Scope unchanged ->
  // apply silently (one click). Scope changed -> raise the re-approval card.
  const doUpdate = async (id) => {
    setBusy(`update:${id}`); setErr(null); setNotice(null); setUpdatePreview(null)
    try {
      const pv = await api(`/apps/${id}/update/preview`, { method: 'POST' })
      if (pv.up_to_date) {
        setNotice({ kind: 'ok', text: `${id} is already at the latest commit.` })
      } else if (pv.scope_changed) {
        setUpdatePreview(pv)
      } else {
        await applyUpdate(id, false)
        return
      }
    } catch (e) { setErr(`Update check failed: ${e.message}`) }
    setBusy(null)
  }

  const applyUpdate = async (id, acceptScope) => {
    setBusy(`update:${id}`); setErr(null)
    try {
      const r = await api(`/apps/${id}/update`, {
        method: 'POST',
        body: JSON.stringify({ accept_scope_change: !!acceptScope }),
      })
      setUpdatePreview(null)
      setNotice({ kind: 'ok', text: `${id} updated to ${r.commit_sha.slice(0, 12)}.` })
      await load()
    } catch (e) { setErr(`Update failed: ${e.message}`) }
    setBusy(null)
  }

  return (
    <div style={{ padding: '40px 32px', maxWidth: 980, margin: '0 auto' }}>
      <h1 style={{
        fontFamily: 'var(--font-display, Lora, Georgia, serif)',
        fontSize: 32,
        fontWeight: 600,
        margin: '0 0 6px 0',
        color: 'var(--text)',
      }}>Apps</h1>
      <p style={{ color: 'var(--muted)', fontStyle: 'italic', margin: '0 0 24px 0', lineHeight: 1.6 }}>
        Brain-apps are sandboxed iframes that add tabs to your brain. Install one
        from a GitHub repo below — it declares which memory layers and permissions
        it needs, and you approve the scope before it runs.
      </p>

      {/* Install bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
        <input
          type="text"
          value={repoUrl}
          onChange={e => setRepoUrl(e.target.value)}
          placeholder="https://github.com/owner/app-repo"
          style={{ ...INPUT, flex: 1 }}
          onKeyDown={e => { if (e.key === 'Enter') doPreview() }}
        />
        <button
          style={{ ...BTN, opacity: (busy === 'preview' || !repoUrl.trim()) ? 0.5 : 1 }}
          disabled={busy === 'preview' || !repoUrl.trim()}
          onClick={doPreview}
        >
          {busy === 'preview' ? 'Reading…' : 'Preview'}
        </button>
      </div>

      {/* Preview / approval card */}
      {preview && (
        <div style={{
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--accent)',
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
        }}>
          <div style={{ fontSize: 15, color: 'var(--text)', marginBottom: 4 }}>
            <b>{preview.manifest.name}</b>{' '}
            <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono, DM Mono, monospace)', fontSize: 12 }}>
              v{preview.manifest.version}
            </span>
          </div>
          <div style={{ fontSize: 13, color: 'var(--muted)', fontStyle: 'italic', marginBottom: 12 }}>
            {preview.manifest.description}
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, fontFamily: 'var(--font-mono, DM Mono, monospace)' }}>
            commit {preview.commit_sha.slice(0, 12)} · license {preview.manifest.license}
          </div>

          {Array.isArray(preview.manifest.permissions) && preview.manifest.permissions.length > 0 && (
            <ScopeRow label="Permissions" value={preview.manifest.permissions.join(', ')} />
          )}
          {Array.isArray(preview.manifest.requires_layers) && preview.manifest.requires_layers.length > 0 && (
            <ScopeRow label="Memory layers" value={preview.manifest.requires_layers.map(l => `${l.layer}:${l.mode}`).join(', ')} />
          )}
          {Array.isArray(preview.manifest.requires_endpoints) && preview.manifest.requires_endpoints.length > 0 && (
            <ScopeRow label="Brain endpoints called" value={preview.manifest.requires_endpoints.join('  ')} />
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
            <button style={{ ...BTN, opacity: busy === 'install' ? 0.5 : 1 }} disabled={busy === 'install'} onClick={doInstall}>
              {busy === 'install' ? 'Installing…' : 'Approve & install'}
            </button>
            <button style={GHOST_BTN} disabled={busy === 'install'} onClick={() => setPreview(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Just-installed token reveal — shown ONCE, never again */}
      {justInstalled && (
        <div style={{
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--accent)',
          borderRadius: 8,
          padding: 14,
          marginBottom: 16,
        }}>
          <div style={{ fontSize: 13, color: 'var(--text)', marginBottom: 8 }}>
            <b>{justInstalled.id}</b> installed. App token (shown once, never again —
            copy it if you need it for debugging):
          </div>
          <div style={{
            fontFamily: 'var(--font-mono, DM Mono, monospace)',
            fontSize: 11,
            color: 'var(--accent)',
            backgroundColor: 'var(--bg)',
            padding: '8px 10px',
            borderRadius: 4,
            wordBreak: 'break-all',
            marginBottom: 8,
          }}>
            {justInstalled.app_token}
          </div>
          <button style={GHOST_BTN} onClick={() => setJustInstalled(null)}>Dismiss</button>
        </div>
      )}

      {/* Update re-approval card — shown only when an update changes scope */}
      {updatePreview && (
        <div style={{
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--accent)',
          borderRadius: 8,
          padding: 16,
          marginBottom: 16,
        }}>
          <div style={{ fontSize: 15, color: 'var(--text)', marginBottom: 4 }}>
            Update <b>{updatePreview.manifest.name}</b>{' '}
            <span style={{ color: 'var(--muted)', fontFamily: 'var(--font-mono, DM Mono, monospace)', fontSize: 12 }}>
              v{updatePreview.manifest.version}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, fontFamily: 'var(--font-mono, DM Mono, monospace)' }}>
            {updatePreview.current_sha.slice(0, 12)} → {updatePreview.commit_sha.slice(0, 12)}
          </div>
          <div style={{ fontSize: 13, color: '#d9a066', marginBottom: 10 }}>
            This update changes what the app can access. Review the scope below
            before approving.
          </div>
          {updatePreview.scope_diff.added_permissions.length > 0 && (
            <ScopeRow label="+ Permissions added" value={updatePreview.scope_diff.added_permissions.join(', ')} />
          )}
          {updatePreview.scope_diff.removed_permissions.length > 0 && (
            <ScopeRow label="− Permissions removed" value={updatePreview.scope_diff.removed_permissions.join(', ')} />
          )}
          {updatePreview.scope_diff.added_layers.length > 0 && (
            <ScopeRow label="+ Memory layers added" value={updatePreview.scope_diff.added_layers.join(', ')} />
          )}
          {updatePreview.scope_diff.removed_layers.length > 0 && (
            <ScopeRow label="− Memory layers removed" value={updatePreview.scope_diff.removed_layers.join(', ')} />
          )}
          <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
            <button
              style={{ ...BTN, opacity: busy === `update:${updatePreview.id}` ? 0.5 : 1 }}
              disabled={busy === `update:${updatePreview.id}`}
              onClick={() => applyUpdate(updatePreview.id, true)}
            >
              {busy === `update:${updatePreview.id}` ? 'Updating…' : 'Approve & update'}
            </button>
            <button style={GHOST_BTN} onClick={() => setUpdatePreview(null)}>Cancel</button>
          </div>
        </div>
      )}

      {notice && (
        <div style={{ color: 'var(--accent)', fontSize: 13, marginBottom: 16 }}>
          {notice.text}
        </div>
      )}

      {err && (
        <div style={{ color: '#d97777', fontSize: 13, marginBottom: 16 }}>
          {err}
        </div>
      )}

      {apps === null && !err && (
        <div style={{ color: 'var(--muted)', fontSize: 13, fontStyle: 'italic' }}>
          Loading…
        </div>
      )}

      {apps && apps.length === 0 && (
        <div style={{
          backgroundColor: 'var(--surface)',
          border: '1px dashed var(--border)',
          borderRadius: 10,
          padding: '28px 22px',
          textAlign: 'center',
          color: 'var(--muted)',
          fontSize: 14,
          fontStyle: 'italic',
        }}>
          Your brain wears no apps yet.
          <br />
          Paste a GitHub repo above to install your first one.
        </div>
      )}

      {apps && apps.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 16,
        }}>
          {apps
            .slice()
            .sort((a, b) => (a?.tab?.order ?? 100) - (b?.tab?.order ?? 100))
            .map(app => (
              <AppCard
                key={app.id}
                app={app}
                busy={busy}
                onUpdate={doUpdate}
                onToggle={doToggle}
                onUninstall={doUninstall}
              />
            ))}
        </div>
      )}
    </div>
  )
}

function ScopeRow({ label, value }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 12, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono, DM Mono, monospace)' }}>
        {value}
      </div>
    </div>
  )
}

function AppCard({ app, busy, onUpdate, onToggle, onUninstall }) {
  const enabled = app.enabled !== false
  return (
    <div style={{
      backgroundColor: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '20px 22px',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      opacity: enabled ? 1 : 0.55,
    }}>
      <Link
        href={enabled ? `/apps/${app.id}` : '#'}
        style={{
          textDecoration: 'none',
          pointerEvents: enabled ? 'auto' : 'none',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          flexGrow: 1,
        }}
      >
        <div style={{
          fontFamily: 'var(--font-display, Lora, Georgia, serif)',
          fontSize: 18,
          fontWeight: 600,
          color: 'var(--text)',
        }}>
          {app?.tab?.label || app.name}
        </div>
        <div style={{
          fontSize: 12,
          color: 'var(--muted)',
          fontFamily: 'var(--font-mono, DM Mono, monospace)',
        }}>
          {app.name} · v{app.version}{enabled ? '' : ' · disabled'}
        </div>
        <div style={{
          fontSize: 13,
          color: 'var(--text)',
          lineHeight: 1.5,
          marginTop: 4,
          flexGrow: 1,
        }}>
          {app.description}
        </div>
      </Link>
      <div style={{
        fontSize: 11,
        color: 'var(--muted)',
        fontFamily: 'var(--font-mono, DM Mono, monospace)',
        marginTop: 4,
      }}>
        /apps/{app.id}
      </div>
      <div style={{
        display: 'flex',
        gap: 8,
        flexWrap: 'wrap',
        marginTop: 6,
        paddingTop: 10,
        borderTop: '1px solid var(--border)',
      }}>
        <button
          style={{ ...GHOST_BTN, opacity: busy === `update:${app.id}` ? 0.5 : 1 }}
          disabled={busy === `update:${app.id}`}
          onClick={() => onUpdate(app.id)}
        >
          {busy === `update:${app.id}` ? '…' : 'Update'}
        </button>
        <button
          style={{ ...GHOST_BTN, opacity: busy === `toggle:${app.id}` ? 0.5 : 1 }}
          disabled={busy === `toggle:${app.id}`}
          onClick={() => onToggle(app.id, enabled)}
        >
          {busy === `toggle:${app.id}` ? '…' : (enabled ? 'Disable' : 'Enable')}
        </button>
        <button
          style={{ ...GHOST_BTN, opacity: busy === `uninstall:${app.id}` ? 0.5 : 1 }}
          disabled={busy === `uninstall:${app.id}`}
          onClick={() => onUninstall(app.id)}
        >
          {busy === `uninstall:${app.id}` ? '…' : 'Uninstall'}
        </button>
      </div>
    </div>
  )
}
