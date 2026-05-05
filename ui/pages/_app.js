import Link from 'next/link'
import { useRouter } from 'next/router'
import Head from 'next/head'
import { useEffect } from 'react'

const NAV = [
  { href: '/', label: 'Dashboard' },
  { href: '/chat', label: 'Chat' },
  { href: '/upload', label: 'Knowledge' },
  { href: '/federation', label: 'Federation' },
  { href: '/trace', label: 'Trace' },
  { href: '/settings', label: 'Settings' },
  { href: '/update', label: 'Update' },
  { href: '/future', label: 'Future' },
]

// Warm academic palette
// bg: #0e0c0b — aged paper in darkness
// surface: #161310 — walnut desk
// surface2: #1c1814 — slightly lifted
// text: #e8e0d5 — warm off-white
// muted: #6b5f52 — warm gray
// accent: #c9a96e — muted amber
// border: #2a2420 — warm dark border

export default function App({ Component, pageProps }) {
  const router = useRouter()

  // Service worker registration (PWA). Best-effort — silent if unavailable.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!('serviceWorker' in navigator)) return
    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') return
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }, [])

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <meta name="theme-color" content="#0e0c0b" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="brain" />
        <link rel="manifest" href="/manifest.json" />
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/icon-192.png" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400;1,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet" />
        <style>{`
          * { box-sizing: border-box; }
          html, body { margin: 0; background: #0e0c0b; -webkit-text-size-adjust: 100%; }
          body { overflow-x: hidden; }
          ::-webkit-scrollbar { width: 6px; }
          ::-webkit-scrollbar-track { background: #0e0c0b; }
          ::-webkit-scrollbar-thumb { background: #2a2420; border-radius: 3px; }

          .bf-nav { padding: 0 24px; gap: 32px; }
          .bf-nav-links { display: flex; gap: 2px; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
          .bf-nav-links::-webkit-scrollbar { display: none; }
          .bf-nav-link { white-space: nowrap; }
          .bf-brand-name { display: inline; }

          @media (max-width: 768px) {
            .bf-nav { padding: 0 12px; gap: 12px; }
            .bf-nav-link { padding: 6px 10px !important; font-size: 12px !important; }
          }
          @media (max-width: 480px) {
            .bf-brand-name { display: none; }
          }
        `}</style>
      </Head>
      <nav className="bf-nav" style={{
        backgroundColor: '#0e0c0b',
        borderBottom: '1px solid #2a2420',
        display: 'flex',
        alignItems: 'center',
        height: '52px',
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
      }}>
        <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <span style={{ fontSize: '18px', color: '#c9a96e', fontWeight: 400, lineHeight: 1 }}>{process.env.NEXT_PUBLIC_BRAIN_SYMBOL || 'ℏ'}</span>
          <span className="bf-brand-name" style={{
            fontFamily: 'Lora, Georgia, serif',
            fontWeight: 600,
            fontSize: '15px',
            color: '#e8e0d5',
            letterSpacing: '0.01em',
          }}>
            {process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain'}
          </span>
        </Link>
        <div className="bf-nav-links">
          {NAV.map(n => (
            <Link key={n.href} href={n.href} className="bf-nav-link" style={{
              padding: '6px 14px',
              borderRadius: '6px',
              fontSize: '13px',
              textDecoration: 'none',
              fontFamily: 'system-ui, sans-serif',
              color: router.pathname === n.href ? '#e8e0d5' : '#6b5f52',
              backgroundColor: router.pathname === n.href ? '#1c1814' : 'transparent',
              fontWeight: router.pathname === n.href ? 600 : 400,
              transition: 'color 0.15s ease',
            }}>
              {n.label}
            </Link>
          ))}
        </div>
      </nav>
      <div style={{
        paddingTop: '52px',
        minHeight: '100vh',
        backgroundColor: '#0e0c0b',
        color: '#e8e0d5',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}>
        <Component {...pageProps} />
      </div>
    </>
  )
}
