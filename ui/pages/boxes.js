import Head from 'next/head'
import { useEffect, useState } from 'react'

// Boxes: the map of the brain's body (2026-10-12, hbar: "a map, a diagram of all the spokes and all the
// parts ... every server needs a visual surface"). 2D first; 3D once the data stays true. The facts are
// the owner's file (world: ops/box-map/boxes.json); online state is read live from the tailnet by the
// bridge (GET /cc/boxmap). Rings: 0 this box, 1 own devices and ships on the tailnet, 2 other brains
// (HTTPS doors), 3 providers. Click a box for its card; "look inside" opens what the console can show.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim)', faint: 'var(--muted)', line: 'var(--border)', card: 'var(--surface)', gold: 'var(--accent)', ok: '#7fc99c', warn: '#d4b86a', alert: '#d49a9a' }
const DOOR = { 'ssh-key': '#8fb3d9', https: '#7fc99c', tailscale: '#c9a7e8', telegram: '#e8c07f', vpn: '#d49a9a' }
const W = 760, H = 560, CX = W / 2, CY = H / 2, R = [0, 150, 225, 265]

function layout(boxes) {
  const byRing = {}
  boxes.forEach((b) => { const r = Math.max(0, Math.min(3, b.ring || 0)); (byRing[r] = byRing[r] || []).push(b) })
  const pos = {}
  Object.entries(byRing).forEach(([r, list]) => {
    const ring = Number(r)
    list.forEach((b, i) => {
      if (ring === 0) { pos[b.id] = { x: CX, y: CY }; return }
      const off = ring === 2 ? 0.35 : ring === 3 ? -0.35 : 0
      const a = (2 * Math.PI * i) / list.length - Math.PI / 2 + off
      pos[b.id] = { x: CX + R[ring] * Math.cos(a) * (ring === 3 ? 1.35 : 1), y: CY + R[ring] * Math.sin(a) * (ring === 3 ? 0.95 : 1) }
    })
  })
  return pos
}

const dot = (b) => (b.online === true ? T.ok : b.online === false ? T.faint : T.warn)

export default function Boxes() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(null)
  const load = async () => {
    try {
      const r = await fetch('/cc/boxmap', { cache: 'no-store' })
      if (!r.ok) { setErr(`the bridge answered ${r.status}`); return }
      setData(await r.json()); setErr('')
    } catch { setErr('the bridge is not answering') }
  }
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t) }, [])
  const boxes = (data && data.boxes) || []
  const pos = layout(boxes)
  const center = boxes.find((b) => (b.ring || 0) === 0)
  const target = (b, d) => (boxes.find((x) => x.id === d.to) || center)
  const cur = boxes.find((b) => b.id === sel)
  return (
    <div style={{ padding: '20px 24px', color: T.ink }}>
      <Head><title>Boxes</title></Head>
      <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 4px 0' }}>Boxes · the body map</p>
      <p style={{ color: T.dim, margin: '0 0 10px 0', fontSize: '14px', maxWidth: '760px' }}>
        Every box and spoke, how it is reached and who may reach it. Green is online now, grey offline, amber unknown from here. A dashed line is a box with no door from the brain.
      </p>
      {err ? <p style={{ ...mono, color: T.alert, fontSize: '12px' }}>{err}</p> : null}
      <div style={{ display: 'flex', gap: '18px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ border: `1px solid ${T.line}`, borderRadius: '12px', background: T.card, maxWidth: '100%' }}>
          {[1, 2].map((r) => <circle key={r} cx={CX} cy={CY} r={R[r]} fill="none" stroke="var(--border)" strokeDasharray="2 6" />)}
          {boxes.filter((b) => (b.ring || 0) > 0).map((b) => {
            const p = pos[b.id]
            const doors = b.doors || []
            if (!doors.length && center) {
              const c = pos[center.id]
              return <line key={b.id + '-none'} x1={c.x} y1={c.y} x2={p.x} y2={p.y} stroke="var(--muted)" strokeDasharray="4 5" strokeWidth="1" />
            }
            return doors.map((d, i) => {
              const t = target(b, d); const q = t ? pos[t.id] : null
              if (!q) return null
              return <line key={b.id + i} x1={q.x} y1={q.y} x2={p.x} y2={p.y} stroke={DOOR[d.type] || 'var(--muted)'} strokeWidth="1.6" opacity="0.85" />
            })
          })}
          {boxes.map((b) => {
            const p = pos[b.id]; const on = sel === b.id; const r0 = (b.ring || 0) === 0
            return (
              <g key={b.id} onClick={() => setSel(on ? null : b.id)} style={{ cursor: 'pointer' }}>
                <circle cx={p.x} cy={p.y} r={r0 ? 26 : 13} fill="var(--surface)" stroke={on ? 'var(--accent)' : dot(b)} strokeWidth={on ? 3 : 2} />
                <circle cx={p.x} cy={p.y} r={r0 ? 6 : 4} fill={dot(b)} />
                <text x={p.x} y={p.y + (r0 ? 42 : 27)} textAnchor="middle" style={{ ...mono, fontSize: '10px', fill: 'var(--text)' }}>{b.label}</text>
              </g>
            )
          })}
        </svg>
        <div style={{ flex: '1 1 300px', minWidth: '280px', maxWidth: '420px' }}>
          {!cur ? (
            <div style={{ ...mono, fontSize: '11px', color: T.dim }}>
              <p style={{ margin: '0 0 8px 0' }}>click a box for its card</p>
              {Object.entries(DOOR).map(([k, c]) => <div key={k}><span style={{ color: c }}>---</span> {k}</div>)}
              <div><span style={{ color: 'var(--muted)' }}>- - -</span> no door from the brain</div>
              {data && !data.tailnet ? <p style={{ color: T.warn }}>tailnet not readable: online states unknown</p> : null}
            </div>
          ) : (
            <div style={{ border: `1px solid ${T.line}`, borderRadius: '10px', background: T.card, padding: '12px 14px' }}>
              <p style={{ margin: '0 0 2px 0', fontSize: '16px' }}>{cur.label}</p>
              <p style={{ ...mono, fontSize: '11px', color: dot(cur), margin: '0 0 8px 0' }}>
                {cur.online === true ? 'online' : cur.online === false ? 'offline' : 'state unknown'}{cur.tailnet_ip ? ` · tailnet ${cur.tailnet_ip}` : ''}{cur.public_ip ? ` · public ${cur.public_ip}` : ''}
              </p>
              {cur.host ? <p style={{ fontSize: '12px', color: T.dim, margin: '0 0 8px 0' }}>{cur.host}</p> : null}
              {[['runs', cur.runs], ['users', cur.users], ['data', cur.data], ['gaps', cur.gaps]].map(([k, v]) => (v && v.length ? (
                <div key={k} style={{ marginBottom: '8px' }}>
                  <p style={{ ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: k === 'gaps' ? T.warn : T.faint, margin: '0 0 2px 0' }}>{k}</p>
                  {v.map((x, i) => <p key={i} style={{ fontSize: '12px', margin: '0 0 2px 0' }}>{x}</p>)}
                </div>) : null))}
              {(cur.doors || []).length ? (
                <div style={{ marginBottom: '8px' }}>
                  <p style={{ ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: T.faint, margin: '0 0 2px 0' }}>doors</p>
                  {cur.doors.map((d, i) => <p key={i} style={{ fontSize: '12px', margin: '0 0 2px 0' }}><span style={{ color: DOOR[d.type] || T.dim }}>{d.type}</span> to {d.to}: {d.who}</p>)}
                </div>) : null}
              <p style={{ ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: T.faint, margin: '0 0 2px 0' }}>look inside</p>
              {(cur.inside || []).length ? cur.inside.map((x, i) => (
                <p key={i} style={{ margin: '0 0 2px 0' }}><a href={x.pane} style={{ color: T.gold, fontSize: '12px' }}>{x.label}</a></p>
              )) : <p style={{ fontSize: '12px', color: T.dim, margin: 0 }}>no live view from the console yet; the gaps above say which door is missing</p>}
              {cur.source ? <p style={{ ...mono, fontSize: '10px', color: T.faint, margin: '10px 0 0 0' }}>source: {cur.source}</p> : null}
            </div>
          )}
        </div>
      </div>
      <p style={{ ...mono, fontSize: '10px', color: T.faint, marginTop: '14px' }}>facts: world/ops/box-map/boxes.json (edit in place) · online: tailnet, refreshed every minute</p>
    </div>
  )
}
