import Link from 'next/link'
import { useEffect, useState } from 'react'

// Apps hub. Lists installed brain apps as cards. Each card opens the
// app's iframe via /apps/[id]. Disabled apps are dimmed and not clickable.
//
// Install + uninstall happen in Settings → Apps; this page is read-only.
//
// Created: 2026-05-09

export default function AppsIndex() {
  const [apps, setApps] = useState(null) // null = loading, [] = empty, [...] = loaded
  const [err, setErr] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/bf/apps/list')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        if (cancelled) return
        setApps(Array.isArray(data?.apps) ? data.apps : [])
      })
      .catch(e => { if (!cancelled) setErr(String(e)) })
    return () => { cancelled = true }
  }, [])

  return (
    <div style={{ padding: '40px 32px', maxWidth: 980, margin: '0 auto' }}>
      <h1 style={{
        fontFamily: 'var(--font-display, Lora, Georgia, serif)',
        fontSize: 32,
        fontWeight: 600,
        margin: '0 0 6px 0',
        color: 'var(--text)',
      }}>Apps</h1>
      <p style={{ color: 'var(--muted)', fontStyle: 'italic', margin: '0 0 28px 0' }}>
        Sandboxed extensions installed into your brain. Install and remove
        from <Link href="/settings" style={{ color: 'var(--accent)' }}>Settings → Apps</Link>.
      </p>

      {err && (
        <div style={{ color: '#d97777', fontSize: 13, marginBottom: 16 }}>
          Could not load apps: {err}
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
          No apps installed yet.
          <br />
          Head to <Link href="/settings" style={{ color: 'var(--accent)', fontStyle: 'normal' }}>Settings → Apps</Link> to install one from a GitHub URL.
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
              <AppCard key={app.id} app={app} />
            ))}
        </div>
      )}
    </div>
  )
}

function AppCard({ app }) {
  const enabled = app.enabled !== false
  const card = (
    <div style={{
      backgroundColor: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '20px 22px',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      opacity: enabled ? 1 : 0.45,
      cursor: enabled ? 'pointer' : 'default',
      transition: 'border-color 0.15s ease',
    }}>
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
      <div style={{
        fontSize: 11,
        color: 'var(--muted)',
        fontFamily: 'var(--font-mono, DM Mono, monospace)',
        marginTop: 8,
      }}>
        /apps/{app.id}
      </div>
    </div>
  )

  if (!enabled) return <div>{card}</div>
  return (
    <Link href={`/apps/${app.id}`} style={{ textDecoration: 'none' }}>
      {card}
    </Link>
  )
}
