import Head from 'next/head'
import { useEffect } from 'react'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/atom-one-dark.css'
import Nav from '../components/Nav'

// Theme palette tokens defined as CSS custom properties below. Each theme is a
// [data-theme] block on :root; chat-header switcher writes localStorage and
// document.documentElement.dataset.theme. Default = "gold". Fonts work the
// same way via [data-font] (ui / serif / mono).

export default function App({ Component, pageProps }) {
  // Service worker registration (PWA). Best-effort — silent if unavailable.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!('serviceWorker' in navigator)) return
    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') return
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }, [])

  // Theme + font init: read localStorage, apply to <html> dataset before paint.
  // Switcher in chat header keeps these in sync on change.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const theme = localStorage.getItem('bf-theme') || 'gold'
    const font = localStorage.getItem('bf-font') || 'ui'
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.font = font
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
          /* Theme tokens — six palettes selectable via [data-theme] on <html>.
             Token names: --bg page, --surface card, --surface2 lifted card,
             --text primary, --muted secondary, --accent highlights/links,
             --border dividers, --user-bg/--user-text user bubble,
             --assistant-bg/--assistant-text assistant bubble,
             --code-bg/--code-fg fenced code. */

          :root {
            /* gold — warm academic, current default */
            --bg: #0e0c0b;
            --surface: #161310;
            --surface2: #1c1814;
            --text: #e8e0d5;
            --muted: #6b5f52;
            --accent: #c9a96e;
            --border: #2a2420;
            --user-bg: #e8d5b0;
            --user-text: #1a1210;
            --assistant-bg: #13100e;
            --assistant-text: #c4b8a8;
            --code-bg: #0e0c0b;
            --code-fg: #c4b8a8;

            /* font tokens — overridden by [data-font]. --font-mono is fixed. */
            --font-body: system-ui, -apple-system, sans-serif;
            --font-display: Lora, Georgia, serif;
            --font-mono: "DM Mono", ui-monospace, monospace;
          }

          [data-theme="paper"] {
            --bg: #f4ede0;
            --surface: #ebe2d2;
            --surface2: #e0d6c2;
            --text: #1a1812;
            --muted: #6b5f52;
            --accent: #8a6e3c;
            --border: #c9b896;
            --user-bg: #1a1812;
            --user-text: #f4ede0;
            --assistant-bg: #ebe2d2;
            --assistant-text: #1a1812;
            --code-bg: #1a1812;
            --code-fg: #c4b8a8;
          }

          [data-theme="sapphire"] {
            --bg: #0a0e1a;
            --surface: #11172a;
            --surface2: #1a2138;
            --text: #d8e0f0;
            --muted: #5a6680;
            --accent: #6b8cce;
            --border: #2a3450;
            --user-bg: #b8c8e8;
            --user-text: #0a0e1a;
            --assistant-bg: #11172a;
            --assistant-text: #c8d0e8;
            --code-bg: #0a0e1a;
            --code-fg: #c8d0e8;
          }

          [data-theme="forest"] {
            --bg: #0c100c;
            --surface: #131a13;
            --surface2: #1a221a;
            --text: #d8e0d0;
            --muted: #5a6650;
            --accent: #88a868;
            --border: #2a3528;
            --user-bg: #c8d8b0;
            --user-text: #0c100c;
            --assistant-bg: #131a13;
            --assistant-text: #c0c8b8;
            --code-bg: #0c100c;
            --code-fg: #c0c8b8;
          }

          [data-theme="crimson"] {
            --bg: #100808;
            --surface: #1a0e0e;
            --surface2: #221414;
            --text: #e8d0d0;
            --muted: #806060;
            --accent: #c87878;
            --border: #3a2222;
            --user-bg: #e8c8c8;
            --user-text: #100808;
            --assistant-bg: #1a0e0e;
            --assistant-text: #d8c0c0;
            --code-bg: #100808;
            --code-fg: #d8c0c0;
          }

          [data-theme="mono"] {
            --bg: #0a0a0a;
            --surface: #161616;
            --surface2: #1f1f1f;
            --text: #e0e0e0;
            --muted: #707070;
            --accent: #b0b0b0;
            --border: #2a2a2a;
            --user-bg: #d0d0d0;
            --user-text: #0a0a0a;
            --assistant-bg: #161616;
            --assistant-text: #c0c0c0;
            --code-bg: #0a0a0a;
            --code-fg: #c0c0c0;
          }

          [data-font="serif"] {
            --font-body: Lora, Georgia, serif;
            --font-display: Lora, Georgia, serif;
          }

          [data-font="mono"] {
            --font-body: "DM Mono", ui-monospace, monospace;
            --font-display: "DM Mono", ui-monospace, monospace;
          }

          * { box-sizing: border-box; }
          html, body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font-body); -webkit-text-size-adjust: 100%; }
          body { overflow-x: hidden; }
          ::-webkit-scrollbar { width: 6px; }
          ::-webkit-scrollbar-track { background: var(--bg); }
          ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

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
        backgroundColor: 'var(--bg)',
        color: 'var(--text)',
        fontFamily: 'var(--font-body)',
      }}>
        <Component {...pageProps} />
      </div>
    </>
  )
}
