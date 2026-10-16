// Wallpaper (2026-10-16, hbar: "upload your own image and the image becomes the background, like
// wallpaper on the iPhone"). The picture is scaled down in the browser (longest side 1920 px, JPEG)
// and kept in this browser only (localStorage 'bf-wall'); nothing is uploaded. A veil in the skin's
// own background colour sits over it so text stays readable; 'bf-wall-veil' is 40, 60 or 80.

export const VEILS = [40, 60, 80]
const KEY = 'bf-wall', VKEY = 'bf-wall-veil'

export function readWall() {
  try { return { image: localStorage.getItem(KEY) || '', veil: VEILS.includes(+localStorage.getItem(VKEY)) ? +localStorage.getItem(VKEY) : 60 } } catch { return { image: '', veil: 60 } }
}

export function applyWall() {
  if (typeof document === 'undefined') return
  const old = document.getElementById('bf-wall')
  if (old) old.remove()
  const { image, veil } = readWall()
  if (!image) return
  const shade = `color-mix(in srgb, var(--bg) ${veil}%, transparent)`
  const el = document.createElement('style')
  el.id = 'bf-wall'
  el.textContent = `.bf-page-wrap { background: linear-gradient(${shade}, ${shade}), url("${image}") center / cover fixed !important; }`
  document.head.appendChild(el)
}

const changed = () => { applyWall(); try { window.dispatchEvent(new CustomEvent('bf-wall')) } catch {} }

export function setVeil(v) { try { localStorage.setItem(VKEY, String(v)) } catch {}; changed() }
export function clearWall() { try { localStorage.removeItem(KEY) } catch {}; changed() }

// Reads a picked file, scales it, stores it. Resolves to '' or an error sentence.
export function setWallFromFile(file) {
  return new Promise((resolve) => {
    if (!file || !/^image\//.test(file.type)) { resolve('That is not an image.'); return }
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, 1920 / Math.max(img.width, img.height))
      const c = document.createElement('canvas')
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k)
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
      URL.revokeObjectURL(url)
      let data = c.toDataURL('image/jpeg', 0.82)
      if (data.length > 3500000) data = c.toDataURL('image/jpeg', 0.6)
      try { localStorage.setItem(KEY, data) } catch { resolve('The picture is too large for this browser to keep; try a smaller one.'); return }
      changed(); resolve('')
    }
    img.onerror = () => { URL.revokeObjectURL(url); resolve('This picture could not be read.') }
    img.src = url
  })
}

export function watchWall() {
  if (typeof window === 'undefined') return () => {}
  applyWall()
  const onStorage = (e) => { if (e.key === KEY || e.key === VKEY) applyWall() }
  window.addEventListener('storage', onStorage)
  return () => window.removeEventListener('storage', onStorage)
}
