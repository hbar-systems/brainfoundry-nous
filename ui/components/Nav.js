import Link from 'next/link'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'

// Static fallback nav. Renders pre-fetch and on /apps/list fetch failure so
// the brain stays usable even if the api is unreachable. Keep in sync with
// BUILTIN_TABS in api/apps.py — drift = a visible flicker on first paint.
const FALLBACK_NAV = [
  { id: '_dashboard',    href: '/',             label: 'Dashboard',    builtin: true },
  { id: '_chat',         href: '/chat',         label: 'Chat',         builtin: true },
  { id: '_knowledge',    href: '/upload',       label: 'Knowledge',    builtin: true },
  { id: '_architecture', href: '/architecture', label: 'Architecture', builtin: true },
  { id: '_cli',          href: '/cli',          label: 'CLI',          builtin: true },
  { id: '_federation',   href: '/federation',   label: 'Federation',   builtin: true },
  { id: '_trace',        href: '/trace',        label: 'Trace',        builtin: true },
  { id: '_settings',     href: '/settings',     label: 'Settings',     builtin: true },
  { id: '_update',       href: '/update',       label: 'Update',       builtin: true },
  { id: '_future',       href: '/future',       label: 'Future',       builtin: true },
]

// The /apps/list response shape:
//   { tabs: [{ id, label, route, order, builtin, ... }], apps: [...] }
// For built-ins, href = tab.route. For installed apps, href = `/apps/${id}`
// (the iframe host shell at ui/pages/apps/[id].js — landed in task #7).
function tabsFromApi(apiTabs) {
  return apiTabs.map(t => ({
    id: t.id,
    href: t.builtin ? t.route : `/apps/${t.id}`,
    label: t.label,
    builtin: !!t.builtin,
  }))
}

function isActive(router, tab) {
  if (tab.builtin) return router.pathname === tab.href
  // Installed-app tab: pages/apps/[id].js handles all installed apps.
  return router.pathname === '/apps/[id]' && router.query.id === tab.id
}

export default function Nav() {
  const router = useRouter()
  const [tabs, setTabs] = useState(FALLBACK_NAV)

  useEffect(() => {
    let cancelled = false
    fetch('/api/bf/apps/list')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        if (cancelled) return
        if (data && Array.isArray(data.tabs)) setTabs(tabsFromApi(data.tabs))
      })
      .catch(() => { /* keep FALLBACK_NAV on any error */ })
    return () => { cancelled = true }
  }, [])

  return (
    <nav className="bf-nav" style={{
      backgroundColor: 'var(--bg)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      height: '52px',
      // PWA safe-area: in standalone mode the iOS status bar / dynamic
      // island sits at the top of the viewport. Pad the nav by the
      // OS-reported inset so the nav content drops below it. In browser
      // mode env() resolves to 0 — no impact. content-box override is
      // required because the global * { box-sizing: border-box } would
      // otherwise eat the padding into the 52px height.
      paddingTop: 'env(safe-area-inset-top, 0px)',
      boxSizing: 'content-box',
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      zIndex: 100,
    }}>
      <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        <span style={{ fontSize: '18px', color: 'var(--accent)', fontWeight: 400, lineHeight: 1 }}>{process.env.NEXT_PUBLIC_BRAIN_SYMBOL || 'ℏ'}</span>
        <span className="bf-brand-name" style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: '15px',
          color: 'var(--text)',
          letterSpacing: '0.01em',
        }}>
          {process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain'}
        </span>
      </Link>
      <div className="bf-nav-links">
        {tabs.map(t => {
          const active = isActive(router, t)
          return (
            <Link key={t.id || t.href} href={t.href} className="bf-nav-link" style={{
              padding: '6px 14px',
              borderRadius: '6px',
              fontSize: '13px',
              textDecoration: 'none',
              fontFamily: 'var(--font-body)',
              color: active ? 'var(--text)' : 'var(--muted)',
              backgroundColor: active ? 'var(--surface2)' : 'transparent',
              fontWeight: active ? 600 : 400,
              transition: 'color 0.15s ease',
            }}>
              {t.label}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
