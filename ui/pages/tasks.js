import Head from 'next/head'
import { useEffect, useState } from 'react'

const API = '/api/bf'
async function api(path, opts = {}) {
  const r = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, cache: 'no-store', ...opts })
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}

function fmtDue(due) {
  if (!due) return ''
  try { return new Date(due).toLocaleString() } catch { return due }
}

export default function Tasks() {
  const [tasks, setTasks] = useState([])
  const [text, setText] = useState('')
  const [due, setDue] = useState('')
  const [err, setErr] = useState(null)

  const load = () => api('/tasks?include_done=true').then(d => setTasks(d.tasks || [])).catch(e => setErr(e.message))
  useEffect(() => { load() }, [])

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
    <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--surface2)' }}>
      <input type="checkbox" checked={!!t.done} onChange={() => toggle(t)} style={{ accentColor: 'var(--accent)', width: 16, height: 16 }} />
      <div style={{ flex: 1 }}>
        <div style={{ color: t.done ? 'var(--muted)' : 'var(--text)', fontSize: 14, textDecoration: t.done ? 'line-through' : 'none' }}>{t.text}</div>
        {t.due && <div style={{ color: 'var(--text-dim)', fontSize: 11.5, marginTop: 2 }}>⏰ {fmtDue(t.due)}{t.reminded ? ' · reminded' : ''}</div>}
        {t.source && <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>from {t.thread
          ? <a href={`/talk?thread=${encodeURIComponent(t.thread)}`} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{t.source}</a>
          : t.source}</div>}
      </div>
      <button onClick={() => del(t)} style={{ background: 'transparent', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 15 }} title="delete">×</button>
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

        {open.length === 0 && done.length === 0 && <div style={{ color: 'var(--muted)', fontSize: 13 }}>No tasks yet.</div>}
        {open.map(Row)}
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
