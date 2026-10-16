// Light (2026-10-16): lifts a dark skin toward a mid tone without redesigning it. hbar: the
// gold, paper, octopus and owl skins read well; the others are too dark. Level 0 to 4 is kept
// in this browser (localStorage 'bf-lift'); 0 removes it. The current skin's own tokens are
// read, mixed toward white and written into one <style> tag, so the owner's layout file (inline
// custom properties on <html>) still wins. Light skins (paper, owl) are left as they are.

const SURFACES = ['--bg', '--surface', '--surface2', '--assistant-bg', '--border', '--code-bg']
const LABELS = ['--muted', '--text-dim']
const AMOUNT = [0, 0.07, 0.13, 0.2, 0.28]
export const LIFT_LEVELS = [0, 1, 2, 3, 4]

function hexRgb(v) {
  const m = /^#?([0-9a-f]{6}|[0-9a-f]{3})$/i.exec(String(v || '').trim())
  if (!m) return null
  let h = m[1]
  if (h.length === 3) h = h.split('').map(c => c + c).join('')
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16))
}
const rgbHex = (rgb) => '#' + rgb.map(x => Math.round(Math.max(0, Math.min(255, x))).toString(16).padStart(2, '0')).join('')
const mix = (rgb, t) => rgb.map(x => x + (255 - x) * t)
const luma = (rgb) => (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255

export function readLift() {
  try { const n = parseInt(localStorage.getItem('bf-lift') || '0', 10); return LIFT_LEVELS.includes(n) ? n : 0 } catch { return 0 }
}

export function applyLift(level) {
  if (typeof document === 'undefined') return
  const old = document.getElementById('bf-lift')
  if (old) old.remove()
  const n = LIFT_LEVELS.includes(level) ? level : 0
  if (!n) return
  const cs = getComputedStyle(document.documentElement)
  const bg = hexRgb(cs.getPropertyValue('--bg'))
  if (!bg || luma(bg) > 0.5) return
  const t = AMOUNT[n]
  const lines = []
  for (const k of SURFACES) { const c = hexRgb(cs.getPropertyValue(k)); if (c) lines.push(`${k}: ${rgbHex(mix(c, t))};`) }
  // labels move up with the background so they keep their contrast
  for (const k of LABELS) { const c = hexRgb(cs.getPropertyValue(k)); if (c) lines.push(`${k}: ${rgbHex(mix(c, t * 1.4))};`) }
  const el = document.createElement('style')
  el.id = 'bf-lift'
  el.textContent = `html[data-theme] { ${lines.join(' ')} }`
  document.head.appendChild(el)
}

export function setLift(level) {
  try { if (level) localStorage.setItem('bf-lift', String(level)); else localStorage.removeItem('bf-lift') } catch {}
  applyLift(level)
  try { window.dispatchEvent(new CustomEvent('bf-lift', { detail: level })) } catch {}
}

// Re-applies when the skin changes (settings, a conversation's own skin) or another tab moves it.
export function watchLift() {
  if (typeof window === 'undefined') return () => {}
  applyLift(readLift())
  const obs = new MutationObserver(() => applyLift(readLift()))
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  const onStorage = (e) => { if (e.key === 'bf-lift') applyLift(readLift()) }
  window.addEventListener('storage', onStorage)
  return () => { obs.disconnect(); window.removeEventListener('storage', onStorage) }
}
