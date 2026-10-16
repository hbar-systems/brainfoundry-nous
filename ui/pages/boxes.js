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

// Compute (2026-10-15): which models live on which machine, read live through the bridge (GET /cc/compute,
// which asks the brain api POST /compute/models). local = may read local-only memory (api/privacy.py rule);
// closed = a hosted API or anything in doubt. The shelf is the owner's file of ready agent kinds (GET /cc/shelf).
const PRIV = { local: T.ok, closed: T.warn }
const label = { ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: T.faint, margin: '0 0 2px 0' }
const gb = (n) => (typeof n === 'number' && n > 0 ? (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`) : '')
const chip = (on) => ({ ...mono, fontSize: '11px', padding: '3px 10px', borderRadius: '999px', cursor: 'pointer', border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`, background: on ? 'var(--accent)' : 'transparent', color: on ? 'var(--bg)' : 'var(--text-dim)' })

function ModelRow({ m }) {
  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'baseline', fontSize: '12px', margin: '0 0 2px 0' }}>
      <span style={{ ...mono, fontSize: '10px', color: PRIV[m.privacy] || T.dim, minWidth: '42px' }}>{m.privacy}</span>
      <span style={{ flex: 1, wordBreak: 'break-all' }}>{m.name}</span>
      {m.loaded ? <span style={{ ...mono, fontSize: '10px', color: T.ok }}>loaded</span> : null}
      {m.parameter_size ? <span style={{ ...mono, fontSize: '10px', color: T.faint }}>{m.parameter_size}</span> : null}
      {gb(m.size) ? <span style={{ ...mono, fontSize: '10px', color: T.faint }}>{gb(m.size)}</span> : null}
    </div>
  )
}

function Endpoint({ e }) {
  const roles = (e.roles || []).join(' + ')
  return (
    <div style={{ marginBottom: '6px' }}>
      <p style={{ ...mono, fontSize: '10px', color: e.online ? T.ok : T.faint, margin: '0 0 2px 0' }}>
        ollama {roles} · {e.online ? `online, ${(e.models || []).length} pulled` : 'offline'}{e.routed ? ' · the brain sends chat here' : ' · declared, the brain does not route chat here'}
      </p>
      {(e.models || []).map((m) => <ModelRow key={m.name} m={m} />)}
    </div>
  )
}

function Shelf({ shelf }) {
  const [leg, setLeg] = useState('')
  if (!shelf) return null
  const agents = shelf.agents || []
  if (!shelf.exists || !agents.length) {
    return (
      <p style={{ fontSize: '12px', color: T.dim, margin: 0 }}>
        {shelf.exists ? 'The shelf file has no valid agents yet.' : 'No shelf yet.'} Put the file at world/{shelf.rel || 'ops/agent-shelf/shelf.json'} on this box ({shelf.path}); the format is in templates/agent-shelf.example.json.
      </p>
    )
  }
  const legions = shelf.legions || []
  const shown = agents.filter((a) => !leg || a.legion === leg)
  const name = (id) => (legions.find((l) => l.id === id) || {}).name || id
  return (
    <div>
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '0 0 10px 0' }}>
        <button type="button" onClick={() => setLeg('')} style={chip(!leg)}>all {agents.length}</button>
        {legions.map((l) => (
          <button type="button" key={l.id} onClick={() => setLeg(leg === l.id ? '' : l.id)} style={chip(leg === l.id)}>
            {l.name} {agents.filter((a) => a.legion === l.id).length}
          </button>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '10px' }}>
        {shown.map((a) => (
          <div key={a.id} style={{ border: `1px solid ${T.line}`, borderRadius: '10px', background: T.card, padding: '10px 12px' }}>
            <p style={{ margin: '0 0 2px 0', fontSize: '14px' }}>{a.name}</p>
            <p style={{ ...mono, fontSize: '10px', color: T.faint, margin: '0 0 6px 0' }}>{name(a.legion)} · runs on {a.runs_on} · {a.model || a.model_class}</p>
            <p style={{ fontSize: '12px', margin: '0 0 6px 0' }}>{a.mission}</p>
            {(a.tools || []).length ? <p style={{ fontSize: '11px', color: T.dim, margin: '0 0 4px 0' }}><span style={{ ...mono, color: T.faint }}>tools </span>{a.tools.join(', ')}</p> : null}
            <p style={{ fontSize: '11px', color: T.dim, margin: '0 0 4px 0' }}><span style={{ ...mono, color: T.warn }}>always asks </span>{a.permit}</p>
            {a.cost ? <p style={{ fontSize: '11px', color: T.dim, margin: 0 }}><span style={{ ...mono, color: T.faint }}>cost </span>{a.cost}</p> : null}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Boxes() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(null)
  const [compute, setCompute] = useState(null)
  const [shelf, setShelf] = useState(null)
  const load = async () => {
    try {
      const r = await fetch('/cc/boxmap', { cache: 'no-store' })
      if (!r.ok) { setErr(`the bridge answered ${r.status}`); return }
      setData(await r.json()); setErr('')
    } catch { setErr('the bridge is not answering') }
    try { const r = await fetch('/cc/compute', { cache: 'no-store' }); if (r.ok) setCompute(await r.json()) } catch {}
    try { const r = await fetch('/cc/shelf', { cache: 'no-store' }); if (r.ok) setShelf(await r.json()) } catch {}
  }
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t) }, [])
  const boxes = (data && data.boxes) || []
  const eps = (compute && compute.endpoints) || []
  const epsOf = (id) => eps.filter((e) => (e.boxes || []).includes(id))
  const nModels = (id) => epsOf(id).reduce((n, e) => n + (e.models || []).length, 0)
  const loose = eps.filter((e) => !(e.boxes || []).some((id) => boxes.find((b) => b.id === id)))
  const hosted = (compute && compute.hosted) || []
  const sum = (compute && compute.summary) || {}
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
                {nModels(b.id) ? <text x={p.x} y={p.y + (r0 ? 54 : 39)} textAnchor="middle" style={{ ...mono, fontSize: '9px', fill: 'var(--muted)' }}>{nModels(b.id)} model{nModels(b.id) === 1 ? '' : 's'}</text> : null}
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
              {epsOf(cur.id).length ? (
                <div style={{ marginBottom: '8px' }}>
                  <p style={label}>models</p>
                  {epsOf(cur.id).map((e) => <Endpoint key={e.url} e={e} />)}
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
      <div style={{ border: `1px solid ${T.line}`, borderRadius: '10px', background: T.card, padding: '12px 14px', marginTop: '14px', maxWidth: '1200px' }}>
        <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 4px 0' }}>Reasoners · models per machine</p>
        {!compute ? <p style={{ fontSize: '12px', color: T.dim, margin: 0 }}>reading the models...</p> : compute.ok === false ? (
          <p style={{ ...mono, fontSize: '12px', color: T.warn, margin: 0 }}>{compute.error}</p>
        ) : (
          <div>
            <p style={{ fontSize: '12px', color: T.dim, margin: '0 0 8px 0' }}>
              {sum.online || 0} of {sum.endpoints || 0} Ollama endpoints online · <span style={{ color: PRIV.local }}>{sum.local || 0} local</span> may read local-only memory · <span style={{ color: PRIV.closed }}>{sum.closed || 0} closed</span> read open memory only · {sum.loaded || 0} loaded now
            </p>
            <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
              {eps.map((e) => (
                <div key={e.url} style={{ flex: '1 1 260px', minWidth: '240px', maxWidth: '380px' }}>
                  <p style={label}>{(e.boxes || []).map((id) => (boxes.find((b) => b.id === id) || {}).label || id).join(', ') || (e.roles || []).join(' + ')}</p>
                  <Endpoint e={e} />
                </div>
              ))}
              {hosted.map((h) => (
                <div key={h.provider} style={{ flex: '1 1 260px', minWidth: '240px', maxWidth: '380px' }}>
                  <p style={label}>{h.provider} · hosted, from your key</p>
                  {(h.models || []).map((m) => <ModelRow key={m.name} m={m} />)}
                </div>
              ))}
            </div>
            {loose.length ? <p style={{ ...mono, fontSize: '10px', color: T.faint, margin: '6px 0 0 0' }}>{loose.length} endpoint{loose.length === 1 ? '' : 's'} not tied to a box in the facts: add "ollama": "&lt;url&gt;" to that box</p> : null}
            <p style={{ ...mono, fontSize: '10px', color: T.faint, margin: '6px 0 0 0' }}>{compute.rule}{compute.at ? ` · read ${compute.at}${compute.cached ? ' (cached)' : ''}` : ''}</p>
          </div>
        )}
      </div>
      <div style={{ border: `1px solid ${T.line}`, borderRadius: '10px', background: T.card, padding: '12px 14px', marginTop: '14px', maxWidth: '1200px' }}>
        <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 4px 0' }}>Shelf · ready agents</p>
        {shelf && shelf.about ? <p style={{ fontSize: '12px', color: T.dim, margin: '0 0 8px 0' }}>{shelf.about}</p> : null}
        {shelf ? <Shelf shelf={shelf} /> : <p style={{ fontSize: '12px', color: T.dim, margin: 0 }}>reading the shelf...</p>}
        {shelf && (shelf.errors || []).length ? (
          <div style={{ marginTop: '8px' }}>
            <p style={{ ...label, color: T.warn }}>left off the shelf</p>
            {shelf.errors.map((x, i) => <p key={i} style={{ ...mono, fontSize: '11px', color: T.warn, margin: '0 0 2px 0' }}>{x}</p>)}
          </div>) : null}
      </div>
      <p style={{ ...mono, fontSize: '10px', color: T.faint, marginTop: '14px' }}>facts: world/ops/box-map/boxes.json (edit in place; a box may add "ollama": "&lt;url&gt;") · online: tailnet, refreshed every minute · models: read live, cached 20 s · shelf: world/ops/agent-shelf/shelf.json</p>
    </div>
  )
}
