import Head from 'next/head'
import { useEffect } from 'react'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/atom-one-dark.css'
import Nav from '../components/Nav'

// Warm academic palette
// bg: #0e0c0b — aged paper in darkness
// surface: #161310 — walnut desk
// surface2: #1c1814 — slightly lifted
// text: #e8e0d5 — warm off-white
// muted: #6b5f52 — warm gray
// accent: #c9a96e — muted amber
// border: #2a2420 — warm dark border

export default function App({ Component, pageProps }) {
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
            .bf-chat-input-bar { padding-left: 12px !important; padding-right: 12px !important; }
          }
        `}</style>
      </Head>
      <Nav />
      <div style={{
        // Match the nav's actual rendered height (52px content + safe-area
        // padding-top) so page content starts below the fixed nav in both
        // browser mode and PWA standalone mode.
        paddingTop: 'calc(52px + env(safe-area-inset-top, 0px))',
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
