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

  // Theme + font + nav-size init: read localStorage, apply to <html>
  // dataset before paint. Switchers in chat header / settings page keep
  // these in sync on change. Old font tokens (ui/serif/mono) migrate to
  // new names on read.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const theme = localStorage.getItem('bf-theme') || 'gold'
    const fontMigration = { ui: 'system', serif: 'lora', mono: 'dm-mono' }
    const stored = localStorage.getItem('bf-font') || 'system'
    const font = fontMigration[stored] || stored
    if (font !== stored) localStorage.setItem('bf-font', font)
    const navSize = localStorage.getItem('bf-nav-size') || 'normal'
    document.documentElement.dataset.theme = theme
    document.documentElement.dataset.font = font
    document.documentElement.dataset.navSize = navSize
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
        <link href="https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600&family=DM+Mono:wght@400;500&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Lora:ital,wght@0,400;0,600;1,400;1,600&display=swap" rel="stylesheet" />
        <style>{`
          /* Theme tokens — six palettes selectable via [data-theme] on <html>.
             Token names: --bg page, --surface card, --surface2 lifted card,
             --text primary, --muted secondary, --accent highlights/links,
             --border dividers, --user-bg/--user-text user bubble,
             --assistant-bg/--assistant-text assistant bubble,
             --code-bg/--code-fg fenced code. */

          :root {
            /* Nav size — overridden by [data-nav-size] on <html>. Default
               52px matches the historical fixed height; compact / comfortable
               are operator-selectable from Settings → Appearance. Every
               place that previously hardcoded "52px" (Nav, page padding-top,
               chat panel height calc) now reads var(--nav-h). */
            --nav-h: 52px;

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

          /* fox — burnt copper, autumnal warmth */
          [data-theme="fox"] {
            --bg: #1a0d08;
            --surface: #221308;
            --surface2: #2a1810;
            --text: #f0d8c0;
            --muted: #7a5a40;
            --accent: #d77a3a;
            --border: #3a2218;
            --user-bg: #f0c896;
            --user-text: #1a0d08;
            --assistant-bg: #221308;
            --assistant-text: #d8c0a8;
            --code-bg: #1a0d08;
            --code-fg: #d8c0a8;
          }

          /* octopus — deep teal abyss, cool but distinct from sapphire */
          [data-theme="octopus"] {
            --bg: #051818;
            --surface: #0c2424;
            --surface2: #143030;
            --text: #c8e0e0;
            --muted: #4a7070;
            --accent: #3a9ea0;
            --border: #1f3838;
            --user-bg: #a8d8d8;
            --user-text: #051818;
            --assistant-bg: #0c2424;
            --assistant-text: #b0c8c8;
            --code-bg: #051818;
            --code-fg: #b0c8c8;
          }

          /* owl — moonlit pale on slate, the second light theme alongside paper */
          [data-theme="owl"] {
            --bg: #f0eef5;
            --surface: #e6e3ee;
            --surface2: #d8d4e2;
            --text: #1a1825;
            --muted: #6a6478;
            --accent: #5b4d80;
            --border: #b8b0c8;
            --user-bg: #2a2438;
            --user-text: #f0eef5;
            --assistant-bg: #e6e3ee;
            --assistant-text: #1a1825;
            --code-bg: #2a2438;
            --code-fg: #d8d4e2;
          }

          /* Six font sets — three sans/serif body fonts, one each from
             two mono families. --font-display follows body for serif/mono
             so headings feel cohesive; for sans body it stays Lora so
             markdown headings still read as book chapters. */

          [data-font="system"] {
            --font-body: system-ui, -apple-system, sans-serif;
            --font-display: Lora, Georgia, serif;
          }

          [data-font="inter"] {
            --font-body: "Inter", system-ui, sans-serif;
            --font-display: Lora, Georgia, serif;
          }

          [data-font="lora"] {
            --font-body: Lora, Georgia, serif;
            --font-display: Lora, Georgia, serif;
          }

          [data-font="crimson"] {
            --font-body: "Crimson Pro", Georgia, serif;
            --font-display: "Crimson Pro", Georgia, serif;
          }

          [data-font="dm-mono"] {
            --font-body: "DM Mono", ui-monospace, monospace;
            --font-display: "DM Mono", ui-monospace, monospace;
          }

          [data-font="jetbrains"] {
            --font-body: "JetBrains Mono", ui-monospace, monospace;
            --font-display: "JetBrains Mono", ui-monospace, monospace;
          }

          /* Nav size variants — override --nav-h. Compact buys more
             vertical real estate on small screens; comfortable is friendlier
             touch target on tablets. */
          [data-nav-size="compact"]     { --nav-h: 40px; }
          [data-nav-size="comfortable"] { --nav-h: 64px; }

          * { box-sizing: border-box; }
          html, body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font-body); -webkit-text-size-adjust: 100%; }
          body { overflow-x: hidden; }
          ::-webkit-scrollbar { width: 6px; }
          ::-webkit-scrollbar-track { background: var(--bg); }
          ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

          /* Resize handle for react-resizable-panels — visible bar between
             panels, brightens on hover and while actively dragged. Default
             is vertical (column resize, 4px wide). The --horizontal modifier
             swaps axes for row resize (4px tall). The ::after pseudo extends
             the hit zone ±4px on the cross axis without changing visuals. */
          .bf-resize-handle {
            width: 4px;
            background: var(--border);
            transition: background 0.15s ease;
            position: relative;
          }
          .bf-resize-handle--horizontal {
            width: auto;
            height: 4px;
          }
          .bf-resize-handle:hover,
          .bf-resize-handle[data-resize-handle-active] {
            background: var(--accent);
          }
          .bf-resize-handle::after {
            content: '';
            position: absolute;
            top: 0;
            bottom: 0;
            left: -4px;
            right: -4px;
          }
          .bf-resize-handle--horizontal::after {
            top: -4px;
            bottom: -4px;
            left: 0;
            right: 0;
          }

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
        // Match the nav's actual rendered height (--nav-h content + safe-
        // area padding-top) so page content starts below the fixed nav in
        // both browser mode and PWA standalone mode. --nav-h is set on
        // <html> from localStorage by the hydration effect above; falls
        // back to 52px by the :root default.
        paddingTop: 'calc(var(--nav-h) + env(safe-area-inset-top, 0px))',
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
