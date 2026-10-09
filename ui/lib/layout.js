// Layout file glue (2026-10-09). Pure functions, no DOM beyond what is passed in: the page code in
// ui/pages/_app.js, cc.js and layout.js calls these; tests/test_cc_layout.py runs them under node.
//
// The layout itself is validated on the box (scripts/cc/cc_layout.py). The page trusts only what the
// bridge returns: `layout` (normalized) and `resolved` ({vars, zoom, weight}). Nothing here builds CSS
// text from the layout; style is set one custom property at a time through setProperty, and the names
// are checked against the same short list again.

const VAR_RE = /^--(accent|bg|surface|surface2|text|muted|border|user-bg|user-text|code-bg)$/
const VAL_RE = /^#[0-9a-fA-F]{6}$/
const PANEL_KEYS = ['hero', 'hint', 'handsfree', 'files', 'board', 'gallery', 'sidebyside']
const COLUMN_PX = { narrow: '860px', wide: '1180px', full: 'none' }
const PX_COLUMN = { '860px': 'narrow', '1180px': 'wide', none: 'full' }

// The browser's localStorage keys the layout maps to (the ones the console already keeps).
//   cc.hidden {key:true}, cc.paneSide, cc.paneW, cc.width, cc.font, cc.speak, cc.handsfree
function localPlan(layout) {
  const set = {}
  const remove = []
  const hidden = {}
  for (const k of PANEL_KEYS) if (layout.panels && layout.panels[k] === false) hidden[k] = true
  if (Object.keys(hidden).length) set['cc.hidden'] = JSON.stringify(hidden); else remove.push('cc.hidden')
  if (layout.pane && layout.pane.side === 'left') set['cc.paneSide'] = 'left'; else remove.push('cc.paneSide')
  if (layout.pane && layout.pane.width) set['cc.paneW'] = String(layout.pane.width); else remove.push('cc.paneW')
  if (layout.column && layout.column !== 'narrow') set['cc.width'] = COLUMN_PX[layout.column]; else remove.push('cc.width')
  if (layout.font) set['cc.font'] = layout.font; else remove.push('cc.font')
  set['cc.speak'] = layout.voice && layout.voice.speak ? '1' : '0'
  set['cc.handsfree'] = layout.voice && layout.voice.handsfree ? '1' : '0'
  return { set, remove }
}

// How the console looks right now, as a layout: the browser's keys over the base layout (which keeps
// what the browser does not hold: name, theme, vars, size, weight, view).
function capture(get, base) {
  const lay = JSON.parse(JSON.stringify(base || { v: 1 }))
  let hidden = {}
  try { hidden = JSON.parse(get('cc.hidden') || '{}') || {} } catch (e) { hidden = {} }
  lay.panels = {}
  for (const k of PANEL_KEYS) lay.panels[k] = !hidden[k]
  lay.pane = { side: get('cc.paneSide') === 'left' ? 'left' : 'right', width: null }
  const w = parseInt(get('cc.paneW') || '', 10)
  if (w >= 280 && w <= 1400) lay.pane.width = w
  lay.column = PX_COLUMN[get('cc.width')] || 'narrow'
  const f = get('cc.font')
  lay.font = f || null
  lay.voice = { speak: get('cc.speak') === '1', handsfree: get('cc.handsfree') === '1' }
  return lay
}

// Set the colour variables, the zoom and the weight on an element-like root ({style:{setProperty,...}}).
// Returns the names it set. Anything not on the short list, or not a six-digit colour, is skipped.
function applyStyle(resolved, root, body) {
  const done = []
  const vars = (resolved && resolved.vars) || {}
  for (const k of Object.keys(vars)) {
    if (VAR_RE.test(k) && VAL_RE.test(vars[k])) { root.style.setProperty(k, vars[k]); done.push(k) }
  }
  const z = resolved && Number(resolved.zoom)
  if (z && z >= 0.8 && z <= 1.3 && z !== 1) { root.style.zoom = String(z); done.push('zoom') }
  if (resolved && (resolved.weight === 300) && body) { body.style.fontWeight = '300'; done.push('weight') }
  return done
}

// Take the colours/zoom/weight back off (stock console).
function clearStyle(root, body) {
  for (const k of ['--accent', '--bg', '--surface', '--surface2', '--text', '--muted', '--border', '--user-bg', '--user-text', '--code-bg']) root.style.removeProperty(k)
  root.style.zoom = ''
  if (body) body.style.fontWeight = ''
}

// Id of a layout for "applied once per browser": the bridge's proposal id is a hash of the layout;
// here a cheap stable string of the normalized layout is enough to tell "changed".
function stamp(layout) {
  const sort = (o) => (o && typeof o === 'object' && !Array.isArray(o)) ? Object.keys(o).sort().reduce((a, k) => { a[k] = sort(o[k]); return a }, {}) : o
  return JSON.stringify(sort(layout))
}

module.exports = { localPlan, capture, applyStyle, clearStyle, stamp, PANEL_KEYS, COLUMN_PX }
