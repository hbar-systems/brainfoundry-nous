import Head from 'next/head'
import { useEffect, useMemo, useState } from 'react'
import { fromSources, groupBy, counts, whenOf } from '../../lib/taskGroups'

// The tasks page (SKIN-2, 2026-11-23, hbar: "in the tasks it could be a little better in terms of UI").
// The page before it is kept at /tasks/v1 (feedback_archive_every_look).
// One list from three sources (ui/lib/taskGroups.js): his own tasks (/api/bf/tasks), the job reports that wait
// on him and the agents' next rows (/cc/actions, owner token only; without the bridge only the tasks show).
// Two views as chips: by time (past due, today, this week, later, no date) and by system. In every group the
// items only he can move come first, marked with a filled dot. One press closes: the ring on a task or a job.
// A next row is taken or dropped, one press each. A press on the text opens the detail in place.
// Look: the console skin's own colours and font (CSS variables of _app.js), few words at rest, no native
// date or select controls: the due time is a row of chips.

const API = '/api/bf'
async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, cache: 'no-store', ...opts })
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}
async function cc(path, body) {
  const r = await fetch(`/cc${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d.error || 'HTTP ' + r.status)
  return d
}

const VIEW_KEY = 'bf.tasks.view'

// Due chips: computed at press time in the browser's own day.
function dueAt(id) {
  const d = new Date()
  if (id === 'tonight') { d.setHours(19, 0, 0, 0); if (d < new Date()) d.setHours(d.getHours() + 3) }
  else if (id === 'tomorrow') { d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0) }
  else if (id === 'week') { d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); d.setHours(9, 0, 0, 0) }
  else return null
  return d.toISOString()
}
const DUES = [['none', 'no date'], ['tonight', 'tonight'], ['tomorrow', 'tomorrow 9:00'], ['week', 'next Monday']]

function whenWords(due) {
  if (!due) return ''
  const d = new Date(due); if (isNaN(d)) return ''
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const t = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return sameDay ? t : d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' }) + ' ' + t
}

const CSS = `
.tk{max-width:760px;margin:0 auto;padding:34px 22px 80px;font-family:var(--font-body);color:var(--text);box-sizing:border-box}
.tk *{box-sizing:border-box}
.tk h1{font-family:var(--font-display);font-weight:600;font-size:28px;margin:0 0 4px}
.tk .line{color:var(--text-dim);font-size:14px;margin:0 0 22px}
.tk .add{display:flex;gap:8px;align-items:center;background:var(--surface);border-radius:14px;padding:6px 6px 6px 14px}
.tk .add input{flex:1;min-width:0;background:transparent;border:0;outline:0;color:var(--text);font:inherit;font-size:15px;padding:8px 0}
.tk .add input::placeholder{color:var(--muted)}
.tk .go{background:var(--accent);color:var(--bg);border:0;border-radius:10px;padding:8px 16px;font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.tk .go:disabled{opacity:.35;cursor:default}
.tk .chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0}
.tk .chip{border:1px solid var(--border);background:transparent;color:var(--text-dim);border-radius:999px;padding:4px 11px;font:inherit;font-size:12.5px;cursor:pointer;white-space:nowrap}
.tk .chip.on{border-color:var(--accent);color:var(--accent);background:var(--surface)}
.tk .bar{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:30px 0 6px}
.tk .tally{font-size:13px;color:var(--text-dim)}
.tk .tally b{color:var(--accent);font-weight:600}
.tk .grp{margin:22px 0 0}
.tk .gh{display:flex;align-items:baseline;gap:8px;font-family:var(--font-mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 4px}
.tk .gh.past{color:#c9775e}
.tk .gh i{font-style:normal;opacity:.7}
.tk .row{display:flex;align-items:flex-start;gap:12px;padding:11px 4px;border-radius:10px;transition:background-color .15s}
.tk .row:hover{background:var(--surface)}
.tk .ring{flex:0 0 auto;width:22px;height:22px;margin-top:1px;border-radius:50%;border:1.5px solid var(--muted);background:transparent;cursor:pointer;padding:0;display:grid;place-items:center;color:var(--accent);font-size:12px}
.tk .ring:hover{border-color:var(--accent)}
.tk .ring.ok{border-color:var(--accent);background:var(--accent);color:var(--bg)}
.tk .ring.nx{border-style:dashed;cursor:default}
.tk .body{flex:1;min-width:0;cursor:pointer}
.tk .tx{font-size:15px;line-height:1.45;overflow-wrap:anywhere}
.tk .meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:3px;font-size:12px;color:var(--muted)}
.tk .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent)}
.tk .late{color:#c9775e}
.tk .sys{font-family:var(--font-mono);font-size:11px}
.tk .more{margin-top:8px;font-size:13px;color:var(--text-dim);line-height:1.5;overflow-wrap:anywhere}
.tk .more a{color:var(--accent)}
.tk .acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.tk .side{display:flex;gap:6px;flex:0 0 auto}
.tk .say{font-size:13px;color:var(--text-dim);margin:10px 0 0}
.tk .err{color:#c9775e}
.tk .empty{color:var(--muted);font-size:14px;padding:26px 4px}
.tk .done .tx{color:var(--muted);text-decoration:line-through}
@media (max-width:520px){.tk{padding:22px 14px 70px}.tk h1{font-size:24px}.tk .side .chip{padding:4px 9px}}
`

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [acts, setActs] = useState(null)
  const [text, setText] = useState('')
  const [due, setDue] = useState('none')
  const [view, setView] = useState('time')
  const [open, setOpen] = useState('')
  const [showDone, setShowDone] = useState(false)
  const [busy, setBusy] = useState('')
  const [said, setSaid] = useState('')
  const [err, setErr] = useState('')
  const [now, setNow] = useState(() => Date.now())

  const load = () => api('/tasks?include_done=true').then(d => setTasks(d.tasks || [])).catch(e => setErr(e.message))
  const loadActs = () => cc('/actions').then(setActs).catch(() => setActs(null))
  useEffect(() => {
    load(); loadActs()
    try { const v = localStorage.getItem(VIEW_KEY); if (v === 'system' || v === 'time') setView(v) } catch {}
    const iv = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(iv)
  }, [])
  const pickView = (v) => { setView(v); try { localStorage.setItem(VIEW_KEY, v) } catch {} }

  const items = useMemo(() => fromSources(tasks, acts), [tasks, acts])
  const groups = useMemo(() => groupBy(items, view, now), [items, view, now])
  const c = useMemo(() => counts(items, now), [items, now])
  const done = tasks.filter(t => t.done)

  const run = async (key, fn, line) => {
    setBusy(key); setErr(''); setSaid('')
    try { const d = await fn(); setSaid((d && (d.line || d.note)) || line || '') } catch (e) { setErr(e.message) }
    setBusy('')
  }
  const add = () => text.trim() && run('add', async () => {
    const body = { text: text.trim() }
    const at = dueAt(due); if (at) body.due = at
    await api('/tasks', { method: 'POST', body: JSON.stringify(body) })
    setText(''); setDue('none'); await load()
  }, 'Added.')
  const closeTask = (t, back) => run('t' + t.id, async () => { await api(`/tasks/${t.id}/complete?done=${!back}`, { method: 'POST' }); await load() }, back ? 'Reopened.' : 'Done.')
  const dropTask = (t) => run('t' + t.id, async () => { await api(`/tasks/${t.id}`, { method: 'DELETE' }); await load() }, 'Deleted.')
  const onBridge = (key, path, body) => run(key, async () => { const d = await cc(path, body); await loadActs(); return { line: d.line || (d.sent_to ? 'Sent to its thread; it starts there now.' : d.note || 'Done.') } })

  const close = (it) => {
    if (it.kind === 'task') return closeTask(it.raw)
    if (it.kind === 'job') return onBridge(it.key, '/actions/job', { id: it.raw.id, act: 'done' })
  }

  const Row = (it) => {
    const w = whenOf(it, now)
    const isOpen = open === it.key
    const b = busy === it.key
    return (
      <div key={it.key} className="row">
        {it.kind === 'next'
          ? <span className="ring nx" title="a next step an agent proposed; take it or drop it" />
          : <button className="ring" disabled={b} onClick={() => close(it)} title={it.kind === 'job' ? 'settled: take it off this list' : 'done'} aria-label="close" />}
        <div className="body" onClick={() => setOpen(isOpen ? '' : it.key)}>
          <div className="tx">{it.text}</div>
          <div className="meta">
            {it.hands ? <span className="dot" title="only you can move this" /> : null}
            {it.due && it.kind !== 'job' ? <span className={w === 'past' ? 'late' : ''}>{whenWords(it.due)}</span> : null}
            {it.kind === 'job' ? <span>a report asks you</span> : null}
            {view === 'time' ? <span className="sys">{it.system}</span> : null}
          </div>
          {isOpen && (
            <div className="more" onClick={e => e.stopPropagation()}>
              {it.sub ? <div>{it.sub}</div> : null}
              {it.kind === 'task' && it.raw.thread ? <div><a href={`/talk?thread=${encodeURIComponent(it.raw.thread)}`} target="_blank" rel="noreferrer">its thread</a></div> : null}
              {it.kind === 'job' ? <div>job {it.raw.id}{it.raw.thread ? <> · <a href={`/talk?thread=${encodeURIComponent(it.raw.thread)}`} target="_blank" rel="noreferrer">{it.raw.thread_title || 'its thread'}</a></> : ' · no known thread, a ruling is only recorded'}</div> : null}
              {it.kind === 'next' ? <div>{it.raw.id} · {it.raw.repo}{it.raw.cost ? ' · cost ' + it.raw.cost : ''} · {(it.raw.ts || '').slice(0, 10)}</div> : null}
              <div className="acts">
                {it.kind === 'job' && (it.raw.options || []).map(o => (
                  <button key={o} className="chip on" disabled={b} onClick={() => onBridge(it.key, '/actions/job', { id: it.raw.id, act: 'rule', choice: o })} title="send this ruling to the job's thread">{o}</button>
                ))}
                {it.kind === 'task' ? <button className="chip" disabled={b} onClick={() => dropTask(it.raw)} title="delete the task">delete</button> : null}
              </div>
            </div>
          )}
        </div>
        {it.kind === 'next' ? (
          <span className="side">
            <button className="chip on" disabled={b} onClick={() => onBridge(it.key, '/actions/next', { id: it.raw.id, act: 'take' })} title="mark it taken: you or the central thread start it">take</button>
            <button className="chip" disabled={b} onClick={() => onBridge(it.key, '/actions/next', { id: it.raw.id, act: 'drop' })} title="not doing it">drop</button>
          </span>
        ) : null}
      </div>
    )
  }

  return (
    <>
      <Head><title>Tasks · BrainFoundry</title></Head>
      <style>{CSS}</style>
      <div className="tk">
        <h1>Tasks</h1>
        <p className="line">Yours first. Tell your brain "remind me to …" anywhere, or add one here.</p>

        <div className="add">
          <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') add() }} placeholder="Add a task…" aria-label="new task" />
          <button className="go" disabled={!text.trim() || busy === 'add'} onClick={add}>Add</button>
        </div>
        {text.trim() ? (
          <div className="chips">
            {DUES.map(([id, l]) => <button key={id} className={'chip' + (due === id ? ' on' : '')} onClick={() => setDue(id)}>{l}</button>)}
          </div>
        ) : null}

        <div className="bar">
          <span className="tally">
            {c.all === 0 ? 'nothing open' : <><b>{c.hands}</b> for your hands{c.past ? <> · <span className="late">{c.past} past due</span></> : null}{c.today ? <> · {c.today} today</> : null}</>}
          </span>
          <span className="chips" style={{ margin: 0 }}>
            <button className={'chip' + (view === 'time' ? ' on' : '')} onClick={() => pickView('time')}>by time</button>
            <button className={'chip' + (view === 'system' ? ' on' : '')} onClick={() => pickView('system')}>by system</button>
          </span>
        </div>
        {said ? <p className="say">{said}</p> : null}
        {err ? <p className="say err">{err}</p> : null}

        {groups.length === 0 ? <div className="empty">No open tasks.</div> : groups.map(g => (
          <div key={g.id} className="grp">
            <div className={'gh' + (g.id === 'past' ? ' past' : '')}>{g.label}<i>{g.items.length}</i></div>
            {g.items.map(Row)}
          </div>
        ))}

        {done.length > 0 && (
          <div className="grp">
            <button className="chip" onClick={() => setShowDone(s => !s)}>{showDone ? 'hide done' : `done ${done.length}`}</button>
            {showDone && done.map(t => (
              <div key={t.id} className="row done">
                <button className="ring ok" onClick={() => closeTask(t, true)} title="reopen" aria-label="reopen">✓</button>
                <div className="body"><div className="tx">{t.text}</div></div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
