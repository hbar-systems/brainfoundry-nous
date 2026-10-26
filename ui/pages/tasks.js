import Head from 'next/head'
import { useEffect, useState } from 'react'

const API = '/api/bf'
async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, cache: 'no-store', ...opts })
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}

// The owner's standing actions (2026-10-26): open next-box rows and job reports that wait on the owner,
// through the console bridge (/cc/actions, owner token only). Without the bridge, or for anyone else,
// the page shows only the tasks.
async function cc(path, body) {
  const r = await fetch(`/cc${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' })
  const d = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(d.error || 'HTTP ' + r.status)
  return d
}

function Act({ children, onClick, primary, busy, title }) {
  return (
    <button onClick={onClick} disabled={busy} title={title}
      style={{ background: primary ? 'var(--accent)' : 'transparent', color: primary ? 'var(--bg)' : 'var(--text-dim)', border: primary ? 'none' : '1px solid var(--border)',
               borderRadius: 7, padding: '4px 11px', fontSize: 12, fontWeight: primary ? 600 : 400, cursor: busy ? 'default' : 'pointer', opacity: busy ? 0.5 : 1, fontFamily: 'inherit', whiteSpace: 'nowrap' }}>{children}</button>
  )
}

const label = { color: 'var(--muted)', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, margin: '26px 0 4px 0' }
const rowStyle = { display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--surface2)' }

function fmtDue(due) {
  if (!due) return ''
  try { return new Date(due).toLocaleString() } catch { return due }
}

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [text, setText] = useState('')
  const [due, setDue] = useState('')
  const [err, setErr] = useState(null)
  const [acts, setActs] = useState(null)   // { next: [], jobs: [] } from the bridge, null when it does not answer the owner
  const [busy, setBusy] = useState('')
  const [said, setSaid] = useState('')

  const load = () => api('/tasks?include_done=true').then(d => setTasks(d.tasks || [])).catch(e => setErr(e.message))
  const loadActs = () => cc('/actions').then(setActs).catch(() => setActs(null))
  useEffect(() => { load(); loadActs() }, [])

  const press = async (key, path, body) => {
    setBusy(key); setErr(null); setSaid('')
    try {
      const d = await cc(path, body)
      setSaid(d.line || (d.sent_to ? 'Sent to its thread; it starts there now.' : d.note || 'Done.'))
      await loadActs()
    } catch (e) { setErr(e.message) }
    setBusy('')
  }

  const add = async () => {
    if (!text.trim()) return
    setErr(null)
    try {
      const body = { text: text.trim() }
      if (due) body.due = new Date(due).toISOString()
      await api('/tasks', { method: 'POST', body: JSON.stringify(body) })
      setText(''); setDue(''); await load()
    } catch (e) { setErr(e.message) }
  }
  const toggle = async (t) => { try { await api(`/tasks/${t.id}/complete?done=${!t.done}`, { method: 'POST' }); await load() } catch (e) { setErr(e.message) } }
  const del = async (t) => { try { await api(`/tasks/${t.id}`, { method: 'DELETE' }); await load() } catch (e) { setErr(e.message) } }

  const open = tasks.filter(t => !t.done)
  const done = tasks.filter(t => t.done)
  const inp = { background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', padding: '10px 12px', fontSize: 14, fontFamily: 'inherit' }

  const Row = (t) => (
    <div key={t.id} style={{ ...rowStyle, alignItems: 'center' }}>
      <div style={{ flex: 1 }}>
        <div style={{ color: t.done ? 'var(--muted)' : 'var(--text)', fontSize: 14, textDecoration: t.done ? 'line-through' : 'none' }}>{t.text}</div>
        {t.due && <div style={{ color: 'var(--text-dim)', fontSize: 11.5, marginTop: 2 }}>⏰ {fmtDue(t.due)}{t.reminded ? ' · reminded' : ''}</div>}
        {t.source && <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>from {t.thread
          ? <a href={`/talk?thread=${encodeURIComponent(t.thread)}`} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{t.source}</a>
          : t.source}</div>}
      </div>
      <Act primary={!t.done} onClick={() => toggle(t)}>{t.done ? 'reopen' : 'done'}</Act>
      <Act onClick={() => del(t)} title="delete the task">drop</Act>
    </div>
  )

  return (
    <>
      <Head><title>Tasks · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '720px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>
        <h1 style={{ fontSize: 26, color: 'var(--text)', margin: '0 0 6px 0' }}>Tasks</h1>
        <p style={{ color: 'var(--text-dim)', fontSize: 14, lineHeight: 1.6, margin: '0 0 22px 0' }}>
          Your brain's reminders. Add them here, or just tell your brain "remind me to …" in chat or
          Telegram. With a due time, it pings your Telegram when it's due.
        </p>

        <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexWrap: 'wrap' }}>
          <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') add() }}
            placeholder="Add a task…" style={{ ...inp, flex: 1, minWidth: 200 }} />
          <input type="datetime-local" value={due} onChange={e => setDue(e.target.value)} style={inp} title="optional due time" />
          <button onClick={add} disabled={!text.trim()}
            style={{ background: text.trim() ? 'var(--accent)' : 'var(--surface2)', color: text.trim() ? 'var(--bg)' : 'var(--muted)', border: 'none', borderRadius: 8, padding: '0 22px', fontWeight: 600, fontSize: 14, cursor: 'pointer', fontFamily: 'inherit' }}>Add</button>
        </div>

        {err && <div style={{ color: '#c0392b', fontSize: 12, marginBottom: 12 }}>{err}</div>}
        {said && <div style={{ color: 'var(--text-dim)', fontSize: 12, marginBottom: 12 }}>{said}</div>}

        {acts && acts.jobs && acts.jobs.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <div style={label}>Reports waiting on you</div>
            {acts.jobs.map(j => (
              <div key={j.id} style={rowStyle}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--text)', fontSize: 14 }}>{j.title || j.id}</div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 12, marginTop: 2 }}>{j.status}{j.line ? `: ${j.line}` : ''}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>job {j.id}{j.thread
                    ? <> · <a href={`/talk?thread=${encodeURIComponent(j.thread)}`} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{j.thread_title || 'its thread'}</a></>
                    : ' · no known thread, a ruling is only recorded'}</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                    {(j.options || []).map(o => (
                      <Act key={o} primary busy={!!busy} onClick={() => press(`j${j.id}`, '/actions/job', { id: j.id, act: 'rule', choice: o })}
                        title="send this ruling to the job's thread">{o}</Act>
                    ))}
                    <Act busy={!!busy} onClick={() => press(`j${j.id}`, '/actions/job', { id: j.id, act: 'done' })} title="settled; take it off this list">done</Act>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {open.length === 0 && done.length === 0 && <div style={{ color: 'var(--muted)', fontSize: 13 }}>No tasks yet.</div>}
        {open.map(Row)}
        {acts && acts.next_box && (
          <div style={{ marginTop: 8 }}>
            <div style={label}>Next, proposed by agents (nothing runs by itself)</div>
            {acts.next.length === 0 && <div style={{ color: 'var(--muted)', fontSize: 13, padding: '8px 0' }}>None open.</div>}
            {acts.next.map(n => (
              <div key={n.id} style={rowStyle}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: 'var(--text)', fontSize: 14 }}>{n.what}</div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 12, marginTop: 2 }}>{n.why}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>{n.id} · {n.repo}{n.cost ? ` · cost ${n.cost}` : ''} · {(n.ts || '').slice(0, 10)}</div>
                </div>
                <Act primary busy={!!busy} onClick={() => press(`n${n.id}`, '/actions/next', { id: n.id, act: 'take' })} title="mark it taken: you or the central thread start it">take</Act>
                <Act busy={!!busy} onClick={() => press(`n${n.id}`, '/actions/next', { id: n.id, act: 'drop' })}>drop</Act>
              </div>
            ))}
          </div>
        )}
        {done.length > 0 && (
          <div style={{ marginTop: 22 }}>
            <div style={{ color: 'var(--muted)', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>Done</div>
            {done.map(Row)}
          </div>
        )}
      </div>
    </>
  )
}
