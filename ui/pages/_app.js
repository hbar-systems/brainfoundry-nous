import Link from 'next/link'
import { useRouter } from 'next/router'
import Head from 'next/head'

const NAV = [
  { href: '/', label: 'Dashboard' },
  { href: '/chat', label: 'Chat' },
  { href: '/upload', label: 'Knowledge' },
  { href: '/settings', label: 'Settings' },
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

  return (
    <>
      <Head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400;1,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet" />
        <style>{`
          * { box-sizing: border-box; }
          body { margin: 0; background: #0e0c0b; }
          ::-webkit-scrollbar { width: 6px; }
          ::-webkit-scrollbar-track { background: #0e0c0b; }
          ::-webkit-scrollbar-thumb { background: #2a2420; border-radius: 3px; }
        `}</style>
      </Head>
      <nav style={{
        backgroundColor: '#0e0c0b',
        borderBottom: '1px solid #2a2420',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        gap: '32px',
        height: '52px',
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
      }}>
        <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px', color: '#c9a96e', fontWeight: 400, lineHeight: 1 }}>{process.env.NEXT_PUBLIC_BRAIN_SYMBOL || 'ℏ'}</span>
          <span style={{
            fontFamily: 'Lora, Georgia, serif',
            fontWeight: 600,
            fontSize: '15px',
            color: '#e8e0d5',
            letterSpacing: '0.01em',
          }}>
            {process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain'}
          </span>
        </Link>
        <div style={{ display: 'flex', gap: '2px' }}>
          {NAV.map(n => (
            <Link key={n.href} href={n.href} style={{
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
