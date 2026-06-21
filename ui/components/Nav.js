import Link from 'next/link'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'

// Static fallback nav. Renders pre-fetch and on /apps/list fetch failure so
// the brain stays usable even if the api is unreachable. Keep in sync with
// BUILTIN_TABS in api/apps.py — drift = a visible flicker on first paint.
const FALLBACK_NAV = [
  { id: '_dashboard',  href: '/',           label: 'Dashboard'  },
  { id: '_chat',       href: '/chat',       label: 'Chat'       },
  { id: '_persona',    href: '/persona',    label: 'Persona'    },
  { id: '_knowledge',  href: '/upload',     label: 'Knowledge'  },
  { id: '_apps',       href: '/apps',       label: 'Apps'       },
  { id: '_tasks',      href: '/tasks',      label: 'Tasks'      },
  { id: '_federation', href: '/federation', label: 'Federation' },
  { id: '_research',   href: '/research',   label: 'Research'    },
  { id: '_integrations', href: '/integrations', label: 'Integrations' },
  { id: '_economy',    href: '/economy',    label: 'Economy'    },
  { id: '_trace',      href: '/trace',      label: 'Trace'      },
  { id: '_settings',   href: '/settings',   label: 'Settings'   },
  { id: '_update',     href: '/update',     label: 'Update'     },
  { id: '_future',     href: '/future',     label: 'Future'     },
]

// The /apps/list response shape:
//   { tabs: [{ id, label, route, order, builtin }, ...], apps: [...] }
// Nav renders only `tabs` (built-ins). Installed apps live behind the
// `_apps` hub at /apps which lists them as cards; each is reachable at
// /apps/<id> via ui/pages/apps/[id].js.
function tabsFromApi(apiTabs) {
  return apiTabs.map(t => ({ id: t.id, href: t.route, label: t.label }))
}

function isActive(router, tab) {
  if (tab.href === '/apps') {
    // The Apps hub is "active" both at /apps (the index) and inside any
    // installed-app iframe shell at /apps/<id>.
    return router.pathname === '/apps' || router.pathname === '/apps/[id]'
  }
  return router.pathname === tab.href
}

// Bounds for the drag-resize handle on the nav's bottom edge. The
// handle mirrors the sidebar/messages resize bars elsewhere in the UI.
// Lower bound buys vertical real estate on small screens; upper bound
// keeps the nav from eating the message column.
const NAV_H_MIN = 36
const NAV_H_MAX = 88

export default function Nav() {
  const router = useRouter()
  const [tabs, setTabs] = useState(FALLBACK_NAV)
  // Owner-set menu header (appearance plane); null => fall back to brand name.
  const [menuTitle, setMenuTitle] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/bf/apps/list')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        if (cancelled) return
        // The /apps/list response already has hidden/reordered tabs applied
        // server-side from the appearance config, so the Nav reflects them
        // without any client-side filter logic.
        if (data && Array.isArray(data.tabs)) setTabs(tabsFromApi(data.tabs))
        if (data && typeof data.menuTitle === 'string') setMenuTitle(data.menuTitle)
      })
      .catch(() => { /* keep FALLBACK_NAV on any error */ })
    return () => { cancelled = true }
  }, [])

  // Drag-handle: mouse + touch. Both update --nav-h live during the
  // drag so the user sees the layout respond instantly; on release we
  // persist the final pixel value to localStorage. Document-level
  // listeners (not handle-element) so a fast drag past the handle
  // doesn't get lost.
  const startDrag = (clientY, isTouch) => {
    // safe-area-inset-top can be non-zero in PWA standalone mode;
    // subtract it so the effective drag origin lines up with the
    // visible nav baseline.
    const cs = getComputedStyle(document.documentElement)
    const safeTop = parseFloat(cs.getPropertyValue('--safe-area-top') || '0') || 0
    const apply = (y) => {
      const next = Math.max(NAV_H_MIN, Math.min(NAV_H_MAX, Math.round(y - safeTop)))
      document.documentElement.style.setProperty('--nav-h', `${next}px`)
    }
    apply(clientY)
    const moveEvt = isTouch ? 'touchmove' : 'mousemove'
    const endEvt = isTouch ? 'touchend' : 'mouseup'
    const onMove = (e) => {
      const y = isTouch ? (e.touches[0] && e.touches[0].clientY) : e.clientY
      if (y != null) apply(y)
      e.preventDefault()
    }
    const onEnd = () => {
      window.removeEventListener(moveEvt, onMove)
      window.removeEventListener(endEvt, onEnd)
      const cs2 = getComputedStyle(document.documentElement)
      const finalH = parseInt(cs2.getPropertyValue('--nav-h') || '52', 10)
      if (Number.isFinite(finalH)) {
        localStorage.setItem('bf-nav-h', String(finalH))
      }
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    window.addEventListener(moveEvt, onMove, { passive: false })
    window.addEventListener(endEvt, onEnd)
  }

  return (
    <nav className="bf-nav" style={{
      backgroundColor: 'var(--bg)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      height: 'var(--nav-h, 52px)',
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
          {menuTitle || process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain'}
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

      {/* Drag handle — sits on the nav's bottom edge, pulls up or down
          to resize the nav height. Matches the sidebar/messages resize
          bar styling (4px tall, brightens on hover via the same accent).
          Double-click resets to the 52px default. */}
      <div
        onMouseDown={(e) => { e.preventDefault(); startDrag(e.clientY, false) }}
        onTouchStart={(e) => { if (e.touches[0]) startDrag(e.touches[0].clientY, true) }}
        onDoubleClick={() => {
          document.documentElement.style.removeProperty('--nav-h')
          localStorage.removeItem('bf-nav-h')
        }}
        title="Drag to resize header · double-click to reset"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: -2,
          height: '4px',
          cursor: 'ns-resize',
          background: 'transparent',
          transition: 'background 0.15s ease',
          zIndex: 101,
        }}
        onMouseOver={(e) => { e.currentTarget.style.background = 'var(--accent)' }}
        onMouseOut={(e) => { e.currentTarget.style.background = 'transparent' }}
      />
    </nav>
  )
}
