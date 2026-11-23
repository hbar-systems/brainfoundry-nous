// The console's skin and font, shared by every page (SKIN-2, 2026-11-23, hbar: "I'm seeing Apps right now
// and it's golden and brown. What if people want to make it a different kind of colour and style?"; "we
// don't have opportunity to change the font in tools").
//
// Before this, a skin picked on the tool line lived only on the conversation page: /apps, /tasks and every
// page opened in the pane beside the chat read the console skin (localStorage bf-theme) and stayed gold.
// Now the skin the console is showing is kept as bf-theme-now, read first by every page (_app.js), and
// pages already open (other tabs, the panes) follow it live through the browser's storage event.
//   bf-theme      the console skin (Settings, Chat tab, or the tool line with no thread skin)
//   bf-theme-now  the skin on screen right now: a thread's own skin, else bf-theme
//   bf-font       the font of the whole console, one of FONT_SHAPES
// The palettes and the font families themselves are the [data-theme] and [data-font] blocks in _app.js.

const SKINS = ['gold', 'paper', 'owl', 'dusk', 'ocean', 'rose', 'sage', 'sand', 'octopus', 'sapphire', 'forest', 'crimson', 'mono', 'fox']

// Six shapes, each chip drawn in its own font. `value` is the [data-font] token (unchanged since 2026-09-30).
const FONT_SHAPES = [
  { value: 'system', label: 'plain', family: 'system-ui, -apple-system, sans-serif', title: 'system sans, serif headings (the stock console)' },
  { value: 'inter', label: 'clean', family: '"Inter", system-ui, sans-serif', title: 'Inter, headings too' },
  { value: 'lora', label: 'book', family: 'Lora, Georgia, serif', title: 'Lora serif' },
  { value: 'crimson', label: 'classic', family: '"Crimson Pro", Georgia, serif', title: 'Crimson Pro serif' },
  { value: 'dm-mono', label: 'type', family: '"DM Mono", ui-monospace, monospace', title: 'DM Mono' },
  { value: 'jetbrains', label: 'code', family: '"JetBrains Mono", ui-monospace, monospace', title: 'JetBrains Mono' },
]
const FONT_MIGRATION = { ui: 'system', serif: 'lora', mono: 'dm-mono' }
const okSkin = (s) => SKINS.includes(s)
const okFont = (f) => FONT_SHAPES.some(x => x.value === f)

function get(k) { try { return localStorage.getItem(k) } catch { return null } }
function set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch {} }
const changed = () => { try { window.dispatchEvent(new CustomEvent('bf-skin')) } catch {} }

function consoleTheme() { const t = get('bf-theme'); return okSkin(t) ? t : 'gold' }
function currentTheme() { const t = get('bf-theme-now'); return okSkin(t) ? t : consoleTheme() }
function currentFont() {
  const s = get('bf-font') || 'system'
  const f = FONT_MIGRATION[s] || s
  return okFont(f) ? f : 'system'
}

// The skin on screen (a thread's own, or the console's when the thread has none).
function showTheme(t, root) {
  const v = okSkin(t) ? t : consoleTheme()
  set('bf-theme-now', v)
  if (root) root.dataset.theme = v
  changed()
  return v
}
// The console skin itself: what every thread without its own skin, and every page, opens in.
function setConsoleTheme(t, root) {
  if (!okSkin(t)) return
  set('bf-theme', t)
  showTheme(t, root)
}
function setFont(f, root) {
  if (!okFont(f)) return
  set('bf-font', f)
  if (root) root.dataset.font = f
  changed()
}

// _app.js: put the skin and font on <html> before paint, then follow changes made in other documents.
// A page inside a pane copies its parent's skin first (same origin), so it matches the thread beside it
// even before the parent has written bf-theme-now.
function watchSkin(root) {
  if (typeof window === 'undefined' || !root) return () => {}
  let theme = currentTheme(), font = currentFont()
  try {
    if (window.self !== window.top) {
      const p = window.parent.document.documentElement.dataset
      if (okSkin(p.theme)) theme = p.theme
      if (okFont(p.font)) font = p.font
    }
  } catch {}
  root.dataset.theme = theme
  root.dataset.font = font
  if (get('bf-font') !== font && get('bf-font')) set('bf-font', font)
  const on = (e) => {
    if (!e || e.key === 'bf-theme-now' || e.key === 'bf-theme') root.dataset.theme = currentTheme()
    if (!e || e.key === 'bf-font') root.dataset.font = currentFont()
  }
  window.addEventListener('storage', on)
  return () => window.removeEventListener('storage', on)
}

module.exports = { SKINS, FONT_SHAPES, consoleTheme, currentTheme, currentFont, showTheme, setConsoleTheme, setFont, watchSkin }
