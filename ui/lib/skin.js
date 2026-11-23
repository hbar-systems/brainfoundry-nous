// The console's skin and font, shared by every page.
//
// SKIN-2 (2026-11-23) kept the skin on screen in one browser key (bf-theme-now) that every open tab and pane
// followed live, so a skin picked in one thread repainted every other thread open beside it (SKIN-3, hbar
// 2026-11-23: "it should be independent but they all change when i change on any single thread!?").
//
// SKIN-3: two levels, both kept.
//   the console default  bf-theme (skin) and bf-font (font) in this browser: what a thread with no choice of
//                        its own opens in, and every page that is not a thread (apps, tasks, systems, the pages
//                        the brain builds). Other tabs and panes follow a change of the default live (storage
//                        event), except where a thread has its own choice.
//   a thread's own       skin and font kept with the thread on the box (its `style`, /cc/threads/update), drawn
//                        only in the document that shows that thread (showOwn). Never written to a shared key,
//                        so it never reaches another tab or pane.
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
const fontFamily = (f) => { const x = FONT_SHAPES.find(s => s.value === f); return x ? x.family : null }

function get(k) { try { return localStorage.getItem(k) } catch { return null } }
function set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch {} }
const changed = () => { try { window.dispatchEvent(new CustomEvent('bf-skin')) } catch {} }

// The console default.
function consoleTheme() { const t = get('bf-theme'); return okSkin(t) ? t : 'gold' }
function consoleFont() {
  const s = get('bf-font') || 'system'
  const f = FONT_MIGRATION[s] || s
  return okFont(f) ? f : 'system'
}

// This document's own choice (the thread it shows), in memory only. One per document: a pane is its own document.
const own = { theme: null, font: null }
let ownRoot = null
function currentTheme() { return own.theme || consoleTheme() }
function currentFont() { return own.font || consoleFont() }
function draw(root) {
  const r = root || ownRoot
  if (!r) return
  r.dataset.theme = currentTheme()
  r.dataset.font = currentFont()
}

// A thread page: draw this thread's own skin and font here, and nowhere else. null = follow the default.
function showOwn(choice, root) {
  own.theme = choice && okSkin(choice.skin) ? choice.skin : null
  own.font = choice && okFont(choice.font) ? choice.font : null
  if (root) ownRoot = root
  draw(root)
  changed()
}
// The console default skin and font (Settings, the Chat tab, the tool line set to "default").
function setConsoleTheme(t, root) {
  if (!okSkin(t)) return
  set('bf-theme', t)
  draw(root)
  changed()
}
function setFont(f, root) {
  if (!okFont(f)) return
  set('bf-font', f)
  draw(root)
  changed()
}

// _app.js: put the default skin and font on <html> before paint, then follow a change of the default made in
// another tab or pane. A thread page's own choice (showOwn) wins over the default in its own document only.
function watchSkin(root) {
  if (typeof window === 'undefined' || !root) return () => {}
  ownRoot = root
  set('bf-theme-now', null)   // SKIN-2's shared "skin on screen" key, retired
  const legacy = get('bf-font')
  if (legacy && FONT_MIGRATION[legacy]) set('bf-font', FONT_MIGRATION[legacy])
  draw(root)
  const on = (e) => {
    if (!e || e.key === 'bf-theme' || e.key === 'bf-font' || e.key === null) { draw(root); changed() }
  }
  window.addEventListener('storage', on)
  return () => window.removeEventListener('storage', on)
}

module.exports = { SKINS, FONT_SHAPES, fontFamily, consoleTheme, consoleFont, currentTheme, currentFont, showOwn, setConsoleTheme, setFont, watchSkin }
