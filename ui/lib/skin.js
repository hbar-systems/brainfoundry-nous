// The console's skin and font, shared by every page.
//
// SKIN-2 (2026-11-23) kept the skin on screen in one browser key (bf-theme-now) that every open tab and pane
// followed live, so a skin picked in one thread repainted every other thread open beside it (SKIN-3, hbar
// 2026-11-23: "it should be independent but they all change when i change on any single thread!?").
//
// SKIN-4 (2026-11-24, hbar: "I WANT SKINS TO CHANGE INDIVIDUALLY BY THREAD AND STOP RECHANGING COLOR WHEN I OPEN
// NEW THREAD, OR RELOAD THE PAGE OR ANYTHING ELSE AS SUCH."): the thread id is the key everywhere, the box is the
// one source of truth, this browser only caches.
//   the console default  on the box (GET/POST /cc/skin, scripts/cc/cc_skin.py), cached here in bf-theme (skin)
//                        and bf-font (font): what a thread with no choice of its own wears, and every page that
//                        is not a thread (apps, tasks, systems, the pages the brain builds). Other tabs and panes
//                        follow a change of the default live (storage event), except where a thread has its own.
//   a thread's own       on the box with the thread (its `style`, read by id at /cc/threads/style, written at
//                        /cc/threads/update), cached here under bf-skin.<thread id>, drawn only in the document
//                        that shows that thread (showOwn). The cache key carries the thread id, so no other
//                        thread reads it; a reload paints the thread's own skin from the first frame (PREPAINT,
//                        in _app.js's <Head>), never the default first.
//   the layout file      its colours (/cc/layout `resolved.vars`) belong to the default level: a document that
//                        shows a thread with its own skin drops them, so the layout never paints over a thread.
// The palettes and the font families themselves are the [data-theme] and [data-font] blocks in _app.js.

const { applyStyle, clearStyle } = require('./layout')

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
// a thread id the box knows (a brand new conversation is 'new:<n>' until the bridge names it)
const knownThread = (t) => typeof t === 'string' && /^[\w:-]{1,120}$/.test(t) && !t.startsWith('new:')
const THREAD_KEY = 'bf-skin.'
// what a thread opened from another thread takes from it (scripts/cc/cc_skin.py INHERITED)
const INHERITED = ['skin', 'font', 'accent', 'tint']
function childLook(look) {
  const out = {}
  for (const k of INHERITED) if (look && look[k] != null) out[k] = look[k]
  return out
}

function get(k) { try { return localStorage.getItem(k) } catch { return null } }
function set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v) } catch {} }
const changed = () => { try { window.dispatchEvent(new CustomEvent('bf-skin')) } catch {} }

// The console default (the cache of the box's /cc/skin).
function consoleTheme() { const t = get('bf-theme'); return okSkin(t) ? t : 'gold' }
function consoleFont() {
  const s = get('bf-font') || 'system'
  const f = FONT_MIGRATION[s] || s
  return okFont(f) ? f : 'system'
}

// One thread's look as last read from the box, kept under its own id. null when this browser has none.
function cachedLook(thread) {
  if (!knownThread(thread)) return null
  try { const v = JSON.parse(get(THREAD_KEY + thread) || 'null'); return v && typeof v === 'object' && !Array.isArray(v) ? v : null } catch { return null }
}
function cacheLook(thread, look) {
  if (!knownThread(thread)) return
  set(THREAD_KEY + thread, JSON.stringify(look && typeof look === 'object' ? look : {}))
}

// This document's own choice (the thread it shows), in memory only. One per document: a pane is its own document.
const own = { theme: null, font: null }
let ownRoot = null
let layoutResolved = null
function currentTheme() { return own.theme || consoleTheme() }
function currentFont() { return own.font || consoleFont() }
function draw(root) {
  const r = root || ownRoot
  if (!r) return
  r.dataset.theme = currentTheme()
  r.dataset.font = currentFont()
  // the layout file's colours are the default level: a thread with its own skin wears the skin's own colours
  try {
    const body = typeof document !== 'undefined' ? document.body : null
    clearStyle(r, body)
    if (layoutResolved) applyStyle(own.theme ? { ...layoutResolved, vars: {} } : layoutResolved, r, body)
  } catch {}
}

// A thread page: draw this thread's own skin and font here, and nowhere else. null = follow the default.
function showOwn(choice, root) {
  own.theme = choice && okSkin(choice.skin) ? choice.skin : null
  own.font = choice && okFont(choice.font) ? choice.font : null
  if (root) ownRoot = root
  draw(root)
  changed()
}
// _app.js: the owner's layout file (/cc/layout `resolved`), drawn under the rules above.
function setLayoutLook(resolved, root) {
  layoutResolved = resolved && typeof resolved === 'object' ? resolved : null
  draw(root)
}

// The console default skin and font (Settings, the Chat tab, the tool line set to "default"): cached here at
// once, kept on the box so every device and every brain page opens in it.
function pushDefault(body) {
  try { fetch('/cc/skin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).catch(() => {}) } catch {}
}
function setConsoleTheme(t, root) {
  if (!okSkin(t)) return
  set('bf-theme', t)
  draw(root)
  changed()
  pushDefault({ skin: t })
}
function setFont(f, root) {
  if (!okFont(f)) return
  set('bf-font', f)
  draw(root)
  changed()
  pushDefault({ font: f })
}
// Read the default from the box once per page. A box with none yet takes this browser's (the default lived only
// in the browser before SKIN-4); a brain without the bridge (404) keeps the browser's.
function syncDefault(root) {
  if (typeof fetch === 'undefined') return Promise.resolve(null)
  return fetch('/cc/skin', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
    if (!d || typeof d !== 'object') return null
    if (!okSkin(d.skin) && !okFont(d.font)) {
      const mine = {}
      if (okSkin(get('bf-theme'))) mine.skin = get('bf-theme')
      if (okFont(get('bf-font'))) mine.font = get('bf-font')
      if (Object.keys(mine).length) pushDefault(mine)
      return d
    }
    let moved = false
    if (okSkin(d.skin) && d.skin !== get('bf-theme')) { set('bf-theme', d.skin); moved = true }
    if (okFont(d.font) && d.font !== get('bf-font')) { set('bf-font', d.font); moved = true }
    if (moved) { draw(root); changed() }
    return d
  }).catch(() => null)
}

// _app.js: put the default skin and font on <html>, then follow a change of the default made in another tab or
// pane. A thread page's own choice (showOwn) wins over the default in its own document only.
function watchSkin(root) {
  if (typeof window === 'undefined' || !root) return () => {}
  ownRoot = root
  set('bf-theme-now', null)   // SKIN-2's shared "skin on screen" key, retired
  set('cc.skinScope', null)   // SKIN-3's remembered "default" switch, retired: it made a press in any thread a default change
  const legacy = get('bf-font')
  if (legacy && FONT_MIGRATION[legacy]) set('bf-font', FONT_MIGRATION[legacy])
  // a thread page reloaded: wear its cached skin from the start, never the default first
  try {
    const c = cachedLook(new URLSearchParams(window.location.search).get('thread'))
    if (c && !own.theme && !own.font) { own.theme = okSkin(c.skin) ? c.skin : null; own.font = okFont(c.font) ? c.font : null }
  } catch {}
  draw(root)
  syncDefault(root)
  const on = (e) => {
    if (!e || e.key === 'bf-theme' || e.key === 'bf-font' || e.key === null) { draw(root); changed() }
  }
  window.addEventListener('storage', on)
  return () => window.removeEventListener('storage', on)
}

// Runs in <head> before the first paint (a string, so it needs no bundle): the default from the cache and, on a
// thread page (?thread=<id>), that thread's own cached skin and font. Same keys and same lists as above.
const PREPAINT = `(function(){try{var S=${JSON.stringify(SKINS)},F=${JSON.stringify(FONT_SHAPES.map(f => f.value))},M=${JSON.stringify(FONT_MIGRATION)},L=localStorage,h=document.documentElement;`
  + `var t=L.getItem('bf-theme'),f=L.getItem('bf-font');f=M[f]||f;`
  + `var q=new URLSearchParams(location.search).get('thread');if(q&&/^[\\w:-]{1,120}$/.test(q)&&q.indexOf('new:')!==0){var c=JSON.parse(L.getItem('${THREAD_KEY}'+q)||'null');if(c){if(S.indexOf(c.skin)>=0)t=c.skin;if(F.indexOf(c.font)>=0)f=c.font}}`
  + `h.setAttribute('data-theme',S.indexOf(t)>=0?t:'gold');h.setAttribute('data-font',F.indexOf(f)>=0?f:'system')}catch(e){}})()`

module.exports = { SKINS, FONT_SHAPES, THREAD_KEY, PREPAINT, fontFamily, knownThread, childLook, consoleTheme, consoleFont, currentTheme, currentFont, cachedLook, cacheLook, showOwn, setLayoutLook, setConsoleTheme, setFont, syncDefault, watchSkin }
