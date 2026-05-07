import Link from 'next/link'
import { useRouter } from 'next/router'

// Hardcoded nav for now. The brain-apps work replaces this with a fetch from
// /api/bf/apps/list so installed apps and built-ins render through the same
// path. Until then, behavior is byte-identical to the prior inline nav in
// _app.js.
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

export default function Nav() {
  const router = useRouter()

  return (
    <nav className="bf-nav" style={{
      backgroundColor: '#0e0c0b',
      borderBottom: '1px solid #2a2420',
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
  )
}
