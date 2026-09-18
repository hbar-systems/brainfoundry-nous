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
        const W = st.w || 800, H = st.h || 600
        st.nodes = (d.nodes || []).map((n, i) => {
          const a = st.anchors[n.layer] ? st.anchors[n.layer].a : 0
          return { ...n, x: W / 2 + Math.cos(a) * W * 0.3 + (Math.random() - 0.5) * W * 0.3, y: H / 2 + Math.sin(a) * H * 0.3 + (Math.random() - 0.5) * H * 0.3,
                   vx: 0, vy: 0, r: 2.5 + Math.sqrt(n.chunks || 1) * 1.1 }
        })
        st.byId = Object.fromEntries(st.nodes.map(n => [n.id, n]))
        st.edges = (d.edges || []).filter(e => st.byId[e.s] && st.byId[e.t])
        // Closeness relative to this graph: raw cosine sits in a narrow band, so rescale to 0..1.
        const ws = st.edges.map(e => e.w); const lo = Math.min(...ws), hi = Math.max(...ws)
        for (const e of st.edges) e.rel = hi > lo ? (e.w - lo) / (hi - lo) : 1
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
      const st = stateRef.current
      if (st.w && st.h && st.nodes.length) {
        const sx = rect.width / st.w, sy = rect.height / st.h
        for (const n of st.nodes) { n.x *= sx; n.y *= sy }
      }
      st.w = rect.width; st.h = rect.height
    }
    resize(); window.addEventListener('resize', resize)

    const step = () => {
      const st = stateRef.current
      const { nodes, edges, w, h } = st
      if (nodes.length && st.alpha > 0.004) {
        const cx = w / 2, cy = h / 2
        // Layer anchors sit on an ellipse that follows the pane's shape, so a tall
        // pane stacks the regions vertically and a wide one lays them side by side.
        const RX = w * 0.30, RY = h * 0.30
        const K = st.alpha
        // Each dot should get about this much room; repulsion is scaled to it.
        const s = Math.sqrt((w * h) / Math.max(1, nodes.length))
        const rep = 0.35 * s * s
        const cut2 = (2.5 * s) * (2.5 * s)
        for (let i = 0; i < nodes.length; i++) {
          const a = nodes[i]
          for (let j = i + 1; j < nodes.length; j++) {
            const b = nodes[j]
            let dx = a.x - b.x, dy = a.y - b.y
            let d2 = dx * dx + dy * dy
            if (d2 < 1) { dx = (Math.random() - 0.5); dy = (Math.random() - 0.5); d2 = 1 }
            if (d2 > cut2) continue
            const f = Math.min(1.5, (rep * K) / d2)
            const d = Math.sqrt(d2)
            const fx = (dx / d) * f, fy = (dy / d) * f
            a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
          }
        }
        // Springs along edges toward a resting length; closer meaning pulls a little harder.
        for (const e of edges) {
          const a = st.byId[e.s], b = st.byId[e.t]
          const dx = b.x - a.x, dy = b.y - a.y
          const d = Math.sqrt(dx * dx + dy * dy) + 0.01
          const want = s * (1.6 - 0.7 * (e.rel || 0))
          const f = (d - want) * 0.01 * K
          const fx = (dx / d) * f, fy = (dy / d) * f
          a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
        }
        // Layer regions and a gentle pull to the centre; damping; a velocity cap.
        const m = 24   // soft margin: a push back inward, not a wall
        for (const n of nodes) {
          const an = st.anchors[n.layer]
          const ax = an ? cx + Math.cos(an.a) * RX : cx, ay = an ? cy + Math.sin(an.a) * RY : cy
          n.vx += (ax - n.x) * 0.02 * K; n.vy += (ay - n.y) * 0.02 * K
          if (n.x < m) n.vx += (m - n.x) * 0.05; if (n.x > w - m) n.vx -= (n.x - (w - m)) * 0.05
          if (n.y < m) n.vy += (m - n.y) * 0.05; if (n.y > h - m) n.vy -= (n.y - (h - m)) * 0.05
          n.vx *= 0.8; n.vy *= 0.8
          const sp = Math.sqrt(n.vx * n.vx + n.vy * n.vy)
          if (sp > 5) { n.vx *= 5 / sp; n.vy *= 5 / sp }
          n.x = Math.min(w - 4, Math.max(4, n.x + n.vx)); n.y = Math.min(h - 4, Math.max(4, n.y + n.vy))
        }
        st.alpha *= 0.992
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
      ctx.strokeStyle = strong ? 'rgba(201,169,110,0.7)' : `rgba(160,150,135,${0.05 + (e.rel || 0) * 0.22})`
      ctx.lineWidth = strong ? 1.4 : 0.7
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
    }
    // nodes
    for (const n of nodes) {
      const x = n.x, y = n.y
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
      const x = hv.x, y = hv.y
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
      const dx = n.x - px, dy = n.y - py
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
    const neigh = st.edges.filter(x => x.s === n.id || x.t === n.id).map(x => ({ id: x.s === n.id ? x.t : x.s, w: x.rel != null ? x.rel : x.w })).sort((a, b) => b.w - a.w)
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
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '10px 16px 6px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
            <div>
            <p style={{ ...mono, color: 'var(--accent)', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: 0 }}>memory · what the brain holds</p>
            {meta && <p style={{ ...mono, color: 'var(--muted)', fontSize: '11px', margin: '4px 0 0 0' }}>{meta.shown} of {meta.total_docs} documents · {meta.edges} links · rings: what the last turn retrieved</p>}
            {!meta && !error && <p style={{ ...mono, color: 'var(--muted)', fontSize: '11px', margin: '4px 0 0 0' }}>reading the memory…</p>}
            {error && <p style={{ color: '#d08a7a', fontSize: '13px', margin: '6px 0 0 0' }}>{error}</p>}
            </div>
            <button onClick={() => { const el = document.documentElement; if (document.fullscreenElement) document.exitFullscreen(); else if (el.requestFullscreen) el.requestFullscreen().catch(() => {}) }}
              style={{ ...mono, background: 'transparent', color: 'var(--muted)', border: '1px solid var(--border)', borderRadius: '6px', padding: '4px 10px', fontSize: '11px', cursor: 'pointer', flexShrink: 0 }}
              title="Fill the screen (Esc to leave)">fullscreen</button>
          </div>
          <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
            <canvas ref={canvasRef} onMouseMove={onMove} onClick={onClick} style={{ display: 'block', cursor: 'crosshair', position: 'absolute', inset: 0 }} />
          </div>
          {meta && (
            <div style={{ padding: '6px 16px 10px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
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
              <p style={{ ...mono, color: 'var(--muted)', fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '18px 0 6px 0' }}>nearest by meaning · closeness relative to this graph</p>
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
