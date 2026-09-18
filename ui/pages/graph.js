import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'

// The memory graph (D54, the second pane): what the brain remembers, drawn as a map.
// Documents are nodes sized by how much the brain holds of them; layers gather into
// regions; edges join each document to its nearest documents by meaning (mean chunk
// embedding, from GET /graph). The documents retrieved for the current CC turn light
// up (GET /cc/health.last_sources, polled). Hover names a document, click shows its
// neighbours and lets you ask the brain about it. Drawn on a canvas with a small force
// layout of our own: no graph library, no motion for its own sake.

const LAYER_HUES = { identity: 42, thinking: 200, projects: 120, writings: 300, episodic: 20, poker: 260, unlayered: 0 }
function layerColor(layer, alpha = 1) {
  const h = LAYER_HUES[layer] != null ? LAYER_HUES[layer] : (Math.abs(hash(layer)) % 360)
  return `hsla(${h}, 45%, 62%, ${alpha})`
}
function hash(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h }
const mono = { fontFamily: 'var(--font-mono, monospace)' }

export default function Graph() {
  const canvasRef = useRef(null)
  const stateRef = useRef({ nodes: [], edges: [], byId: {}, hover: null, selected: null, lit: new Set(), alpha: 1, w: 0, h: 0, anchors: {} })
  const [meta, setMeta] = useState(null)      // { total_docs, layers, generated_at, k }
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)
  const [litNames, setLitNames] = useState([])

  // Load the graph once; poll the bridge for the current turn's sources.
  useEffect(() => {
    fetch('/api/bf/graph?limit=300&k=3', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => {
        const st = stateRef.current
        const layers = d.layers || []
        // One anchor per layer around a circle: layers become regions.
        layers.forEach((l, i) => { const a = (i / Math.max(1, layers.length)) * Math.PI * 2; st.anchors[l] = { a } })
        st.nodes = (d.nodes || []).map((n, i) => {
          const a = st.anchors[n.layer] ? st.anchors[n.layer].a : 0
          const r0 = 0.28 + Math.random() * 0.12
          return { ...n, x: 0.5 + Math.cos(a) * r0 + (Math.random() - 0.5) * 0.08, y: 0.5 + Math.sin(a) * r0 + (Math.random() - 0.5) * 0.08,
                   vx: 0, vy: 0, r: 2.5 + Math.sqrt(n.chunks || 1) * 1.1 }
        })
        st.byId = Object.fromEntries(st.nodes.map(n => [n.id, n]))
        st.edges = (d.edges || []).filter(e => st.byId[e.s] && st.byId[e.t])
        st.alpha = 1
        setMeta({ total_docs: d.total_docs, layers, generated_at: d.generated_at, k: d.k, shown: st.nodes.length, edges: st.edges.length })
      })
      .catch(e => setError(`The graph endpoint did not answer (${e}). Is the brain on 0.13.0 or later?`))
    const poll = () => fetch('/cc/health', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(h => {
      const names = (h && h.last_sources) || []
      stateRef.current.lit = new Set(names); setLitNames(names)
    }).catch(() => {})
    poll(); const iv = setInterval(poll, 4000)
    return () => clearInterval(iv)
  }, [])

  // The layout and drawing loop.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let raf = 0
    const resize = () => {
      const dpr = window.devicePixelRatio || 1
      const rect = canvas.parentElement.getBoundingClientRect()
      canvas.width = Math.floor(rect.width * dpr); canvas.height = Math.floor(rect.height * dpr)
      canvas.style.width = rect.width + 'px'; canvas.style.height = rect.height + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      stateRef.current.w = rect.width; stateRef.current.h = rect.height
    }
    resize(); window.addEventListener('resize', resize)

    const step = () => {
      const st = stateRef.current
      const { nodes, edges, w, h } = st
      if (nodes.length && st.alpha > 0.005) {
        const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.36
        const K = st.alpha
        // Repulsion (all pairs; n <= 300 keeps this cheap)
        for (let i = 0; i < nodes.length; i++) {
          const a = nodes[i]
          for (let j = i + 1; j < nodes.length; j++) {
            const b = nodes[j]
            let dx = (a.x - b.x) * w, dy = (a.y - b.y) * h
            let d2 = dx * dx + dy * dy + 1
            const f = (900 * K) / d2
            const fx = dx * f, fy = dy * f
            a.vx += fx / w; a.vy += fy / h; b.vx -= fx / w; b.vy -= fy / h
          }
        }
        // Springs along edges
        for (const e of edges) {
          const a = st.byId[e.s], b = st.byId[e.t]
          const dx = (b.x - a.x) * w, dy = (b.y - a.y) * h
          const d = Math.sqrt(dx * dx + dy * dy) + 0.01
          const want = 46
          const f = ((d - want) / d) * 0.02 * K * (0.5 + e.w)
          a.vx += dx * f / w; a.vy += dy * f / h; b.vx -= dx * f / w; b.vy -= dy * f / h
        }
        // Layer gravity (regions) and centering
        for (const n of nodes) {
          const an = st.anchors[n.layer]
          const ax = an ? cx + Math.cos(an.a) * R : cx, ay = an ? cy + Math.sin(an.a) * R : cy
          n.vx += ((ax / w) - n.x) * 0.012 * K; n.vy += ((ay / h) - n.y) * 0.012 * K
          n.vx += (0.5 - n.x) * 0.002 * K; n.vy += (0.5 - n.y) * 0.002 * K
          n.vx *= 0.82; n.vy *= 0.82
          n.x = Math.min(0.97, Math.max(0.03, n.x + n.vx)); n.y = Math.min(0.97, Math.max(0.03, n.y + n.vy))
        }
        st.alpha *= 0.985
      }
      draw(ctx, st)
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize) }
  }, [])

  function draw(ctx, st) {
    const { nodes, edges, w, h } = st
    ctx.clearRect(0, 0, w, h)
    const sel = st.selected ? st.byId[st.selected] : null
    const near = new Set(sel ? edges.filter(e => e.s === sel.id || e.t === sel.id).map(e => (e.s === sel.id ? e.t : e.s)) : [])
    // edges
    for (const e of edges) {
      const a = st.byId[e.s], b = st.byId[e.t]
      const strong = sel && (e.s === sel.id || e.t === sel.id)
      ctx.strokeStyle = strong ? 'rgba(201,169,110,0.7)' : `rgba(160,150,135,${0.06 + e.w * 0.18})`
      ctx.lineWidth = strong ? 1.4 : 0.8
      ctx.beginPath(); ctx.moveTo(a.x * w, a.y * h); ctx.lineTo(b.x * w, b.y * h); ctx.stroke()
    }
    // nodes
    for (const n of nodes) {
      const x = n.x * w, y = n.y * h
      const lit = st.lit.has(n.id)
      const dim = sel && !(n.id === sel.id || near.has(n.id))
      if (lit) {
        ctx.beginPath(); ctx.arc(x, y, n.r + 7, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(201,169,110,0.16)'; ctx.fill()
        ctx.beginPath(); ctx.arc(x, y, n.r + 3, 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(201,169,110,0.9)'; ctx.lineWidth = 1.2; ctx.stroke()
      }
      ctx.beginPath(); ctx.arc(x, y, n.r, 0, Math.PI * 2)
      ctx.fillStyle = layerColor(n.layer, dim ? 0.25 : 0.9); ctx.fill()
      if (sel && n.id === sel.id) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke() }
    }
    // hover label
    const hv = st.hover ? st.byId[st.hover] : null
    if (hv) {
      const x = hv.x * w, y = hv.y * h
      ctx.font = '12px var(--font-mono, monospace)'
      const label = hv.id.length > 60 ? hv.id.slice(0, 57) + '…' : hv.id
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(20,18,16,0.92)'; ctx.fillRect(x + 10, y - 22, tw + 12, 20)
      ctx.fillStyle = '#e8e0d5'; ctx.fillText(label, x + 16, y - 8)
    }
  }

  function nodeAt(clientX, clientY) {
    const st = stateRef.current
    const rect = canvasRef.current.getBoundingClientRect()
    const px = clientX - rect.left, py = clientY - rect.top
    let best = null, bd = 1e9
    for (const n of st.nodes) {
      const dx = n.x * st.w - px, dy = n.y * st.h - py
      const d = dx * dx + dy * dy
      if (d < bd && d < (n.r + 6) * (n.r + 6)) { bd = d; best = n }
    }
    return best
  }
  const onMove = (e) => { const n = nodeAt(e.clientX, e.clientY); stateRef.current.hover = n ? n.id : null }
  const onClick = (e) => {
    const n = nodeAt(e.clientX, e.clientY)
    const st = stateRef.current
    st.selected = n ? n.id : null
    st.alpha = Math.max(st.alpha, 0.05)
    if (!n) { setSelected(null); return }
    const neigh = st.edges.filter(x => x.s === n.id || x.t === n.id).map(x => ({ id: x.s === n.id ? x.t : x.s, w: x.w })).sort((a, b) => b.w - a.w)
    setSelected({ ...n, neigh })
  }
  const ask = (n) => {
    const text = `What do you remember from "${n.id}", and how does it connect to the rest?`
    try { window.parent.postMessage({ type: 'cc-ask', text }, window.location.origin) } catch {}
  }

  return (
    <>
      <Head><title>Memory graph · BrainFoundry</title></Head>
      <div style={{ display: 'flex', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '480px', fontFamily: 'var(--font-display, serif)', color: 'var(--text)' }}>
        <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
          <canvas ref={canvasRef} onMouseMove={onMove} onClick={onClick} style={{ display: 'block', cursor: 'crosshair' }} />
          <div style={{ position: 'absolute', left: 16, top: 12, pointerEvents: 'none' }}>
            <p style={{ ...mono, color: 'var(--accent)', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: 0 }}>memory · what the brain holds</p>
            {meta && <p style={{ ...mono, color: 'var(--muted)', fontSize: '11px', margin: '4px 0 0 0' }}>{meta.shown} of {meta.total_docs} documents · {meta.edges} links · lit: what the last turn retrieved</p>}
            {error && <p style={{ color: '#d08a7a', fontSize: '13px', margin: '6px 0 0 0' }}>{error}</p>}
          </div>
          {meta && (
            <div style={{ position: 'absolute', left: 16, bottom: 12, display: 'flex', gap: '12px', flexWrap: 'wrap', pointerEvents: 'none' }}>
              {meta.layers.map(l => (
                <span key={l} style={{ ...mono, color: 'var(--muted)', fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 4, background: layerColor(l), display: 'inline-block' }} />{l}
                </span>
              ))}
            </div>
          )}
        </div>
        <div style={{ width: '300px', flexShrink: 0, borderLeft: '1px solid var(--border)', padding: '16px', overflowY: 'auto', backgroundColor: 'var(--surface)' }}>
          {selected ? (
            <>
              <p style={{ ...mono, color: 'var(--accent)', fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>{selected.layer} · {selected.chunks} chunk{selected.chunks === 1 ? '' : 's'}</p>
              <p style={{ margin: '0 0 12px 0', fontSize: '15px', lineHeight: 1.4, wordBreak: 'break-word' }}>{selected.id}</p>
              <button onClick={() => ask(selected)} style={{ padding: '8px 12px', borderRadius: '8px', border: 'none', background: 'var(--accent)', color: 'var(--bg)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', fontSize: '13px' }}>ask the brain about this</button>
              <p style={{ ...mono, color: 'var(--muted)', fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '18px 0 6px 0' }}>nearest by meaning</p>
              {selected.neigh.map(n => (
                <p key={n.id} style={{ margin: '0 0 6px 0', fontSize: '13px', color: 'var(--muted)', lineHeight: 1.4, wordBreak: 'break-word' }}>
                  <span style={{ ...mono, color: 'var(--accent)', fontSize: '10px', marginRight: '6px' }}>{Math.round(n.w * 100)}%</span>{n.id}
                </p>
              ))}
            </>
          ) : (
            <>
              <p style={{ margin: '0 0 10px 0', fontSize: '14px', lineHeight: 1.6, color: 'var(--muted)' }}>
                Every dot is a document the brain remembers. Size is how much of it the brain holds. Colour is its layer. Lines join documents that mean similar things. Rings mark what the brain just read for the current conversation.
              </p>
              <p style={{ margin: 0, fontSize: '13px', lineHeight: 1.6, color: 'var(--muted)' }}>Hover to name one. Click to see its neighbours and ask the brain about it.</p>
              {litNames.length > 0 && (
                <>
                  <p style={{ ...mono, color: 'var(--muted)', fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '18px 0 6px 0' }}>lit now</p>
                  {litNames.map(n => <p key={n} style={{ margin: '0 0 4px 0', fontSize: '12px', color: 'var(--text)', wordBreak: 'break-word' }}>{n}</p>)}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
