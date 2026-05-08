import { useEffect, useRef, useState } from 'react'
import DOMPurify from 'dompurify'

// Mermaid is heavy (~800 KB). Load it once per browser tab, lazily, the
// first time a mermaid block needs to render. Subsequent diagrams reuse
// the resolved promise.
let mermaidPromise = null
const loadMermaid = () => {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(m => {
      m.default.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'strict',
        fontFamily: 'inherit',
      })
      return m.default
    })
  }
  return mermaidPromise
}

let diagramIdCounter = 0

const triggerDownload = (data, filename, mimeType) => {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function DiagramBlock({ kind, source }) {
  const [svg, setSvg] = useState(null)
  const [error, setError] = useState(null)
  const renderId = useRef(0)

  useEffect(() => {
    let cancelled = false
    renderId.current += 1
    const myId = renderId.current

    const trimmed = (source || '').trim()
    if (!trimmed) {
      setSvg(null)
      setError(null)
      return
    }

    if (kind === 'mermaid') {
      (async () => {
        try {
          const mermaid = await loadMermaid()
          const id = `bf-mermaid-${++diagramIdCounter}`
          const { svg: rendered } = await mermaid.render(id, trimmed)
          if (!cancelled && renderId.current === myId) {
            setSvg(rendered)
            setError(null)
          }
        } catch (e) {
          if (!cancelled && renderId.current === myId) {
            setError(e?.message || 'Mermaid parse error')
            setSvg(null)
          }
        }
      })()
    } else if (kind === 'svg') {
      try {
        const clean = DOMPurify.sanitize(trimmed, {
          USE_PROFILES: { svg: true, svgFilters: true },
        })
        if (!cancelled && renderId.current === myId) {
          setSvg(clean)
          setError(null)
        }
      } catch (e) {
        if (!cancelled && renderId.current === myId) {
          setError(e?.message || 'SVG sanitize error')
          setSvg(null)
        }
      }
    }

    return () => { cancelled = true }
  }, [kind, source])

  const saveSvg = () => {
    if (!svg) return
    triggerDownload(svg, `${kind}-${Date.now()}.svg`, 'image/svg+xml')
  }

  const savePng = async () => {
    if (!svg) return
    try {
      // Mermaid (and many SVG sources) declare a viewBox but no width/height
      // attributes. Browsers render those into <img> at zero pixels, which
      // then rasterizes to an empty canvas. Parse the SVG, extract dimensions
      // from viewBox if needed, and force explicit width/height attrs before
      // rasterizing.
      const parser = new DOMParser()
      const doc = parser.parseFromString(svg, 'image/svg+xml')
      const svgEl = doc.documentElement
      const parseErr = doc.querySelector('parsererror')
      if (parseErr) throw new Error('SVG parse error')

      let w = parseFloat(svgEl.getAttribute('width')) || 0
      let h = parseFloat(svgEl.getAttribute('height')) || 0
      if (!w || !h) {
        const vb = (svgEl.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number)
        if (vb.length === 4 && vb.every(n => !isNaN(n))) {
          w = w || vb[2]
          h = h || vb[3]
        }
      }
      if (!w || !h) { w = 800; h = 600 }
      svgEl.setAttribute('width', String(w))
      svgEl.setAttribute('height', String(h))
      if (!svgEl.getAttribute('xmlns')) {
        svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
      }
      const serialized = new XMLSerializer().serializeToString(svgEl)
      const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n', serialized], { type: 'image/svg+xml;charset=utf-8' })
      const objectUrl = URL.createObjectURL(blob)

      const img = new window.Image()
      await new Promise((resolve, reject) => {
        img.onload = resolve
        img.onerror = () => reject(new Error('Failed to load SVG into <img>'))
        img.src = objectUrl
      })

      const scale = 2
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(w * scale)
      canvas.height = Math.ceil(h * scale)
      const ctx = canvas.getContext('2d')
      // White background — PNGs without bg look broken on light surfaces.
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.scale(scale, scale)
      ctx.drawImage(img, 0, 0, w, h)
      URL.revokeObjectURL(objectUrl)

      const pngBlob = await new Promise((resolve, reject) => {
        canvas.toBlob(b => b ? resolve(b) : reject(new Error('canvas.toBlob returned null')), 'image/png')
      })
      triggerDownload(pngBlob, `${kind}-${Date.now()}.png`, 'image/png')
    } catch (e) {
      console.error('[bf] PNG export failed:', e)
      if (typeof window !== 'undefined') {
        window.alert('PNG export failed (see console). The SVG is still available via the SVG button.')
      }
    }
  }

  const copySource = async () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return
    try { await navigator.clipboard.writeText(source) } catch {}
  }

  if (error) {
    // Common during streaming: closing ``` hasn't arrived yet, so the
    // partial source can't parse. Render as code text and the parent
    // re-renders when more tokens arrive.
    return (
      <pre style={{
        background: 'var(--code-bg)',
        color: 'var(--code-fg)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '12px 14px',
        margin: '0.5em 0',
        overflowX: 'auto',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.88em',
        lineHeight: 1.5,
      }}>
        <code>{source}</code>
      </pre>
    )
  }

  if (!svg) {
    return (
      <div style={{
        padding: '12px 14px',
        margin: '0.5em 0',
        color: 'var(--muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.85em',
        border: '1px dashed var(--border)',
        borderRadius: '8px',
      }}>
        rendering {kind}…
      </div>
    )
  }

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: '8px',
      margin: '0.5em 0',
      overflow: 'hidden',
      background: 'var(--surface)',
    }}>
      <div
        style={{ padding: '14px 16px', overflowX: 'auto' }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
      <div style={{
        display: 'flex',
        gap: '6px',
        padding: '6px 10px',
        borderTop: '1px solid var(--border)',
        backgroundColor: 'var(--surface2)',
        alignItems: 'center',
      }}>
        <ToolButton onClick={saveSvg}>↓ SVG</ToolButton>
        <ToolButton onClick={savePng}>↓ PNG</ToolButton>
        <ToolButton onClick={copySource}>copy source</ToolButton>
      </div>
    </div>
  )
}

function ToolButton({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: 'none',
        border: '1px solid var(--border)',
        color: 'var(--accent)',
        padding: '3px 9px',
        borderRadius: '4px',
        fontSize: '11px',
        fontFamily: 'var(--font-mono)',
        cursor: 'pointer',
        transition: 'background 0.12s ease, border-color 0.12s ease',
      }}
      onMouseOver={e => { e.currentTarget.style.background = 'var(--bg)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseOut={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {children}
    </button>
  )
}
