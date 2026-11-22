import Head from 'next/head'
import { useEffect, useState } from 'react'
import { wake } from '../lib/presses'

// Usage (USAGE-1, 2026-11-22): what the console's private usage log holds, as counts per control for
// the last 7 and 30 days. Read from the bridge (GET /cc/presses); the log is one file on the box
// (scripts/cc/cc_presses.py). The switch and "delete the log" are the owner's; nothing here leaves the box.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim)', faint: 'var(--muted)', line: 'var(--border)', card: 'var(--surface)', gold: 'var(--accent)', alert: '#d49a9a' }
const KIND_LABEL = { nav: 'menu', surface: 'page', pane: 'pane', choice: 'choice', slash: 'slash' }
const when = (ts) => (ts ? ts.replace('T', ' ').slice(0, 16) : '')
const shown = (r) => (r.kind === 'slash' ? (r.name === 'other' ? 'other (sent to the reasoner)' : '/' + r.name) : r.name)

function Chip({ on, children, onClick, title }) {
  return (
    <button onClick={onClick} title={title} style={{ ...mono, fontSize: '11px', padding: '4px 10px', borderRadius: '999px', cursor: 'pointer',
      border: `1px solid ${on ? T.gold : T.line}`, background: on ? 'rgba(212,184,106,0.12)' : 'transparent', color: on ? T.ink : T.dim }}>
      {children}
    </button>
  )
}

export default function Usage() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [kind, setKind] = useState('')
  const [days, setDays] = useState('d30')
  const [sure, setSure] = useState(false)
  const take = async (r) => { if (!r.ok) { setErr(`the bridge answered ${r.status}`); return } setD(await r.json()); setErr('') }
  const load = () => fetch('/cc/presses', { cache: 'no-store' }).then(take).catch(() => setErr('the bridge is not answering'))
  const post = (route, body) => fetch(route, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(take).then(() => wake()).catch(() => setErr('the bridge is not answering'))
  useEffect(() => { load() }, [])
  const rows = ((d && d.controls) || []).filter(r => (!kind || r.kind === kind) && r[days] > 0)
    .sort((a, b) => b[days] - a[days])
  const top = rows.length ? rows[0][days] : 1
  return (
    <div style={{ padding: '20px 24px', color: T.ink, maxWidth: '900px' }}>
      <Head><title>Usage</title></Head>
      <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 4px 0' }}>Usage · what you press</p>
      <p style={{ color: T.dim, margin: '0 0 12px 0', fontSize: '14px', lineHeight: 1.6 }}>{d ? d.what : 'Counts of what you press in the console, kept on this box.'}</p>
      {err ? <p style={{ ...mono, color: T.alert, fontSize: '12px' }}>{err}</p> : null}
      {d ? (
        <>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '10px' }}>
            <Chip on={d.on} onClick={() => post('/cc/presses/switch', { on: !d.on })} title="Turn the usage log on or off. Off: nothing is written.">{d.on ? 'logging: on' : 'logging: off'}</Chip>
            {sure
              ? <><Chip on onClick={() => { setSure(false); post('/cc/presses/clear', {}) }}>yes, delete {d.events} event{d.events === 1 ? '' : 's'}</Chip><Chip onClick={() => setSure(false)}>keep</Chip></>
              : (d.events > 0 ? <Chip onClick={() => setSure(true)} title="Delete the log file on the box">delete the log</Chip> : null)}
            <span style={{ ...mono, fontSize: '11px', color: T.faint }}>
              {d.events} event{d.events === 1 ? '' : 's'}{d.since ? ` since ${when(d.since)} UTC` : ''} · 7 days: {d.d7} in {d.threads7} thread{d.threads7 === 1 ? '' : 's'} · 30 days: {d.d30} in {d.threads30}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '14px' }}>
            {[['d7', '7 days'], ['d30', '30 days']].map(([k, l]) => <Chip key={k} on={days === k} onClick={() => setDays(k)}>{l}</Chip>)}
            <span style={{ color: T.faint }}>·</span>
            <Chip on={kind === ''} onClick={() => setKind('')}>all</Chip>
            {(d.kinds || []).map(k => <Chip key={k} on={kind === k} onClick={() => setKind(k)}>{KIND_LABEL[k] || k}</Chip>)}
          </div>
          {!rows.length ? <p style={{ color: T.dim, fontSize: '14px' }}>{d.on ? 'Nothing counted in this window yet.' : 'The log is off; nothing is being counted.'}</p> : null}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {rows.map(r => (
              <div key={r.kind + ' ' + r.name} style={{ display: 'grid', gridTemplateColumns: '64px minmax(120px, 1.2fr) 2fr 52px 52px', gap: '10px', alignItems: 'center', border: `1px solid ${T.line}`, borderRadius: '8px', background: T.card, padding: '7px 10px' }}>
                <span style={{ ...mono, fontSize: '10px', color: T.faint, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{KIND_LABEL[r.kind] || r.kind}</span>
                <span style={{ ...mono, fontSize: '12px', color: T.ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`last ${when(r.last)} UTC`}>{shown(r)}</span>
                <span style={{ height: '6px', borderRadius: '3px', background: 'var(--surface2)', overflow: 'hidden' }}>
                  <span style={{ display: 'block', height: '100%', width: `${Math.max(2, Math.round(100 * r[days] / top))}%`, background: T.gold, opacity: 0.75 }} />
                </span>
                <span style={{ ...mono, fontSize: '12px', textAlign: 'right', color: days === 'd7' ? T.ink : T.dim }} title="last 7 days">{r.d7}</span>
                <span style={{ ...mono, fontSize: '12px', textAlign: 'right', color: days === 'd30' ? T.ink : T.dim }} title="last 30 days">{r.d30}</span>
              </div>
            ))}
          </div>
          <p style={{ ...mono, fontSize: '10px', color: T.faint, marginTop: '18px', wordBreak: 'break-all' }}>
            Columns: 7 days, 30 days. A choice is counted as how it was sent and where it stood (reply-1, agent-2). The file: {d.file}
          </p>
        </>
      ) : null}
    </div>
  )
}
