import Head from 'next/head'
import React, { useEffect, useState } from 'react'

// Agents (2026-10-17): standing agents you create here and that then run on their own.
//
// The operator's ask: "an army of agents operating on hbar.systems", made visually, running 24/7.
// An agent is a charter: name, mission, the ground it may write in, a schedule, a budget per run and
// an optional model. The bridge (GET/POST /cc/agents, scripts/cc/cc_agents.py) keeps one file per
// agent and checks every minute which ones are due; each run is a background job, a tile on the
// board, and ends with a sitrep shown here. Writes outside its ground, sudo, and anything that
// leaves the brain still wait for your press on a card; push, rm -rf and .env are refused.

const C = {
  ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', card: 'var(--surface2)', surface: 'var(--surface)',
  line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)', bad: '#c0605a', ok: '#7fc99c',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const link = { ...mono, fontSize: '11px', color: C.dim, cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }
const EVERY = [['on call', 0], ['30 min', 30], ['hourly', 60], ['every 6 h', 360], ['daily', 1440], ['weekly', 10080]]
const BUDGET = [0.5, 1, 2, 5, 10, 20]
// Autonomy levels: 0 propose, 1 branch (default), 2 ship (its own branch onto main of its own repo; never force).
const LEVELS = [[0, 'propose'], [1, 'branch'], [2, 'ship']]
// Institution codes: the letters of the tag (LAW-1, ENG-2). Any 2 to 4 letters can be typed.
const CODES = [['CMD', 'Command'], ['SLF', 'Self-knowledge'], ['ENG', 'Engineering'], ['MEM', 'Memory intake'], ['LOG', 'Logistics and treasury'], ['ECO', 'Economy'], ['MKT', 'Market'], ['COM', 'Foreign commerce'], ['LAW', 'Law'], ['DEF', 'Defence'], ['CEN', 'Census'], ['ADM', 'Admission'], ['SUP', 'Support'], ['PAR', 'Parliament'], ['DIP', 'Diplomacy'], ['SCI', 'Science'], ['EDU', 'Education'], ['HEA', 'Health'], ['PRS', 'Press'], ['CUL', 'Culture']]
// Suggested posts (the units of the order of battle); any other name can be typed.
const POSTS = ['Command', 'I Hands', 'II Studio', 'III Media', 'IV Science', 'V Doors', 'VI Agency', 'VII Legal', 'J2 Intelligence', 'J4 Logistics']
const everyWord = (m) => (EVERY.find(e => e[1] === m) || [`every ${m} min`])[0]
const when = (s) => { if (!s) return 'never'; const d = (Date.parse(s) - Date.now()) / 1000; const a = Math.abs(d); const w = a < 90 ? 'now' : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${Math.round(a / 3600)} h` : `${Math.round(a / 86400)} d`; return w === 'now' ? 'now' : d > 0 ? `in ${w}` : `${w} ago` }

function Btn({ children, onClick, primary, disabled, title }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      style={{ ...mono, fontSize: '12px', padding: '6px 14px', borderRadius: '8px', cursor: disabled ? 'default' : 'pointer',
               border: primary ? 'none' : `1px solid ${C.line}`, backgroundColor: primary ? C.gold : 'transparent',
               color: primary ? C.onAccent : C.dim, fontWeight: primary ? 600 : 400, opacity: disabled ? 0.5 : 1 }}>
      {children}
    </button>
  )
}

function Chip({ on, children, onClick }) {
  return (
    <button onClick={onClick}
      style={{ ...mono, fontSize: '12px', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', marginRight: '6px', marginBottom: '6px',
               border: `1px solid ${on ? C.gold : C.line}`, backgroundColor: 'transparent', color: on ? C.gold : C.dim }}>
      {children}
    </button>
  )
}

const field = { width: '100%', boxSizing: 'border-box', backgroundColor: C.surface, color: C.ink, border: `1px solid ${C.line}`,
                borderRadius: '8px', padding: '8px 10px', fontSize: '14px', fontFamily: 'inherit' }
const label = { ...mono, fontSize: '11px', color: C.dim, letterSpacing: '0.08em', textTransform: 'uppercase', margin: '12px 0 6px' }

async function post(path, body) {
  const r = await fetch(`/cc${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  let d = {}
  try { d = await r.json() } catch {}
  if (!r.ok || d.ok === false) throw new Error(d.error || `HTTP ${r.status}`)
  return d
}

function NewAgent({ onMade, posts }) {
  const [name, setName] = useState('')
  const [callsign, setCallsign] = useState('')
  const [code, setCode] = useState('')
  const [post, setPost] = useState('')
  const [mission, setMission] = useState('')
  const [ground, setGround] = useState('')
  const [every, setEvery] = useState(1440)
  const [budget, setBudget] = useState(1)
  const [model, setModel] = useState('')
  const [level, setLevel] = useState(1)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const make = async () => {
    setBusy(true); setErr('')
    try {
      await post('/agents', { name, callsign, code, post, level, mission, ground, every_minutes: every, budget_usd: budget, model })
      setName(''); setCallsign(''); setCode(''); setMission(''); setGround(''); setModel('')
      onMade()
    } catch (e) { setErr(String(e.message || e)) }
    setBusy(false)
  }
  return (
    <div style={{ backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '12px', padding: '14px 16px', maxWidth: '720px' }}>
      <div style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>new agent</div>
      <div style={label}>name</div>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Disk watch" style={field} />
      <div style={label}>callsign (optional nickname; the number is given automatically, A-001, A-002, ...)</div>
      <input value={callsign} onChange={e => setCallsign(e.target.value)} placeholder="Sentinel" style={field} />
      <div style={label}>institution: the letters of its tag; the number is given automatically (LAW-1, LAW-2, ...)</div>
      <div>{CODES.map(([c, n]) => <Chip key={c} on={code === c} onClick={() => setCode(code === c ? '' : c)}>{c} {n}</Chip>)}</div>
      <div style={label}>post: the unit it serves under</div>
      <div>{(posts || []).map(p => <Chip key={p} on={post === p} onClick={() => setPost(post === p ? '' : p)}>{p}</Chip>)}</div>
      <input value={post} onChange={e => setPost(e.target.value)} placeholder="I Hands" style={field} />
      <div style={label}>mission: what it does each time it runs</div>
      <textarea value={mission} onChange={e => setMission(e.target.value)} rows={4} style={{ ...field, resize: 'vertical' }}
        placeholder="Check the box's disk, the desk folders and the backups; if anything is over its limit, say what and propose the fix." />
      <div style={label}>ground: folders it may write in, one per line (empty = it only reports)</div>
      <textarea value={ground} onChange={e => setGround(e.target.value)} rows={2} style={{ ...field, ...mono, fontSize: '13px', resize: 'vertical' }}
        placeholder="/home/hands/world/ops/posts" />
      <div style={label}>runs</div>
      <div>{EVERY.map(([w, m]) => <Chip key={m} on={every === m} onClick={() => setEvery(m)}>{w}</Chip>)}</div>
      <div style={label}>budget per run (USD)</div>
      <div>{BUDGET.map(b => <Chip key={b} on={budget === b} onClick={() => setBudget(b)}>{b}</Chip>)}</div>
      <div style={label}>autonomy: propose = changes only as proposals; branch = commits on its own branch, never pushed; ship = may push its branch onto main of its own repo when tests pass</div>
      <div>{LEVELS.map(([v, w]) => <Chip key={v} on={level === v} onClick={() => setLevel(v)}>{v} {w}</Chip>)}</div>
      <div style={label}>model (optional; empty = the default reasoner)</div>
      <input value={model} onChange={e => setModel(e.target.value)} placeholder="" style={{ ...field, ...mono, fontSize: '13px' }} />
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '14px' }}>
        <Btn primary onClick={make} disabled={busy || !name.trim() || mission.trim().length < 10}>{busy ? 'creating' : 'create agent'}</Btn>
        {err && <span style={{ ...mono, fontSize: '12px', color: C.bad }}>{err}</span>}
      </div>
      <p style={{ fontSize: '12px', color: C.dim, lineHeight: 1.6, margin: '12px 0 0' }}>
        It first runs about a minute after you create it, then on its schedule. Each run is a tile on the board and ends with a sitrep here.
        Writes outside its ground, sudo, and anything that leaves the brain wait for your press; push, rm -rf and .env are refused.
      </p>
    </div>
  )
}

// A face for each agent (2026-10-17): drawn from its tag, the same every time, no image service.
// Unit colour ring, a field with its institution letters, and rank marks: a star for the General,
// two bars for a captain. The pattern behind is a 5x5 mirrored grid seeded by the serial.
function hashOf(str) { let h = 2166136261; for (const ch of String(str)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) } return h >>> 0 }
function Face({ a, size = 46 }) {
  const h = hashOf(a.post || 'none'), g = hashOf(`${a.serial}-${a.callsign}`)
  const hue = h % 360, hue2 = (hue + 40 + (g % 80)) % 360
  const cells = []
  for (let y = 0; y < 5; y++) for (let x = 0; x < 3; x++) if ((g >> (y * 3 + x)) & 1) { cells.push([x, y]); if (x < 2) cells.push([4 - x, y]) }
  const general = (a.code || '') === 'CMD' || /general/i.test(a.name || '')
  const letters = (a.code || (a.callsign || a.name || '?').slice(0, 2)).toUpperCase()
  return (
    <svg width={size} height={size} viewBox="0 0 50 50" style={{ flex: 'none', alignSelf: 'center' }} aria-label={`face of ${a.tag}`}>
      <circle cx="25" cy="25" r="23.5" fill={`hsl(${hue2} 35% 16%)`} stroke={`hsl(${hue} 55% 55%)`} strokeWidth="3" />
      <g opacity="0.55">{cells.map(([x, y], i) => <rect key={i} x={12.5 + x * 5} y={9 + y * 5} width="5" height="5" fill={`hsl(${hue2} 50% 45%)`} />)}</g>
      <text x="25" y="41.5" textAnchor="middle" fontSize="8.5" fontFamily="monospace" fill={`hsl(${hue} 70% 80%)`}>{letters}</text>
      {general
        ? <polygon points="25,3 27,8 32,8 28,11 30,16 25,13 20,16 22,11 18,8 23,8" fill="#d4b86a" />
        : <g fill="#d4b86a"><rect x="19" y="4" width="12" height="2" /><rect x="19" y="7.5" width="12" height="2" /></g>}
    </svg>
  )
}

function Agent({ a, reload }) {
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)
  const act = async (what, path, body) => {
    setBusy(what); setErr('')
    try { await post(path, body); reload() } catch (e) { setErr(String(e.message || e)) }
    setBusy('')
  }
  const on = !!a.enabled
  return (
    <div style={{ backgroundColor: C.card, border: `1px solid ${on ? C.line : C.line}`, borderLeft: `3px solid ${on ? C.ok : C.dim}`, borderRadius: '10px', padding: '12px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
        <Face a={a} />
        <span style={{ ...mono, fontSize: '13px', color: C.gold }}>{a.tag}</span>
        <span style={{ ...mono, fontSize: '10px', color: C.dim }}>A-{String(a.serial || 0).padStart(3, '0')}</span>
        <span style={{ fontSize: '15px', color: C.ink, fontWeight: 600 }}>{a.name}</span>
        <span style={{ ...mono, fontSize: '11px', color: on ? C.ok : C.dim }}>{on ? 'on' : 'paused'}</span>
        <span style={{ ...mono, fontSize: '11px', color: C.dim }}>{everyWord(a.every_minutes)} · up to {a.budget_usd} USD a run{a.model ? ` · ${a.model}` : ''}</span>
      </div>
      <p style={{ fontSize: '13px', color: C.ink, lineHeight: 1.55, margin: '6px 0' }}>{a.mission}</p>
      <div style={{ ...mono, fontSize: '11px', color: C.dim, lineHeight: 1.7 }}>
        ground: {(a.ground || []).length ? a.ground.join(', ') : 'none (reports only)'}<br />
        last run: {when(a.last_run)}{a.last_job ? ` (job ${a.last_job})` : ''} · next: {!on ? 'paused' : a.every_minutes ? when(a.next_due) : 'on call'} · runs: {a.runs || 0}
        {a.last_error ? <><br /><span style={{ color: C.bad }}>last start failed: {a.last_error}</span></> : null}
      </div>
      {a.sitrep && (
        <div style={{ marginTop: '8px' }}>
          <a onClick={() => setOpen(!open)} style={link}>{open ? 'hide' : 'show'} last sitrep ({a.sitrep.name})</a>
          {open && <pre style={{ ...mono, fontSize: '12px', color: C.ink, whiteSpace: 'pre-wrap', backgroundColor: C.surface, border: `1px solid ${C.line}`, borderRadius: '8px', padding: '10px', margin: '6px 0 0' }}>{a.sitrep.text}</pre>}
        </div>
      )}
      <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        <Btn onClick={() => act('run', '/agents/run', { id: a.id })} disabled={!!busy}>{busy === 'run' ? 'starting' : 'run now'}</Btn>
        <span style={{ ...mono, fontSize: '11px', color: C.dim }}>autonomy</span>
        {LEVELS.map(([v, w]) => <Chip key={v} on={(a.level ?? 1) === v} onClick={() => { if ((a.level ?? 1) !== v && (v < 2 || window.confirm(`${a.tag} may push its own branch onto main of its repo when tests pass. Grant ship?`))) act('level', '/agents/update', { id: a.id, level: v }) }}>{w}</Chip>)}
        <Btn onClick={() => act('toggle', '/agents/update', { id: a.id, enabled: !on })} disabled={!!busy}>{on ? 'pause' : 'resume'}</Btn>
        <Btn onClick={() => { if (window.confirm(`Retire ${a.name}? Its file is kept in the agents folder's .trash; its sitreps stay.`)) act('delete', '/agents/delete', { id: a.id }) }} disabled={!!busy}>retire</Btn>
        <a href="/board" style={link}>board</a>
        {err && <span style={{ ...mono, fontSize: '12px', color: C.bad }}>{err}</span>}
      </div>
    </div>
  )
}

export default function Agents() {
  const [data, setData] = useState(null)
  const [note, setNote] = useState('')
  const load = () => fetch('/cc/agents', { cache: 'no-store' })
    .then(r => r.json().then(d => ({ ok: r.ok, d })))
    .then(({ ok, d }) => { if (ok && d.agents) { setData(d); setNote('') } else { setNote(d.error || 'the bridge did not answer'); setData(data || false) } })
    .catch(() => { setNote('the bridge did not answer at /cc/agents'); setData(data || false) })
  useEffect(() => {
    load()
    const t = setInterval(() => { if (!document.hidden) load() }, 15000)
    return () => clearInterval(t)
  }, [])
  const agents = (data && data.agents) || []
  const groups = Object.entries(agents.reduce((g, a) => { (g[a.post || ''] = g[a.post || ''] || []).push(a); return g }, {}))
    .sort(([x], [y]) => (x === '') - (y === '') || x.localeCompare(y))
  return (
    <>
      <Head><title>Agents · BrainFoundry</title></Head>
      <div style={{ minHeight: 'calc(100vh - var(--nav-h, 52px))', backgroundColor: C.bg, boxSizing: 'border-box', padding: '10px 12px 40px', color: C.ink }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '0 2px 10px', flexWrap: 'wrap' }}>
          <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>agents</span>
          <span style={{ ...mono, fontSize: '11px', color: C.dim }}>{agents.filter(a => a.enabled).length} on · {agents.length} in all</span>
          <span style={{ flex: 1 }} />
          <a href="/board" style={link}>board</a>
          <a href="/talk" style={link}>one conversation</a>
        </div>
        {note && <p style={{ ...mono, fontSize: '12px', color: C.bad, margin: '0 2px 10px' }}>{note}</p>}
        <div style={{ display: 'grid', gap: '14px', gridTemplateColumns: 'minmax(0, 1fr)', maxWidth: '900px' }}>
          <NewAgent onMade={load} posts={POSTS.concat(agents.map(a => a.post).filter(p => p && !POSTS.includes(p))).filter((p, i, l) => l.indexOf(p) === i)} />
          {data && agents.length === 0 && (
            <p style={{ fontSize: '14px', color: C.dim, lineHeight: 1.7, margin: '6px 2px' }}>No agents yet. The first one you create starts within about a minute.</p>
          )}
          {groups.map(([post, list]) => (
            <div key={post || '_none'}>
              <div style={{ ...mono, fontSize: '11px', color: C.dim, letterSpacing: '0.12em', textTransform: 'uppercase', margin: '6px 2px 8px' }}>
                {post || 'no post'} · {list.filter(a => a.enabled).length} on of {list.length}
              </div>
              <div style={{ display: 'grid', gap: '10px' }}>{list.map(a => <Agent key={a.id} a={a} reload={load} />)}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
