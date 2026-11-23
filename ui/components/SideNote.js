// Talk in place (INLINE-1, 2026-11-23): a small note box on one item (a tree node in the chat). Typing
// sends one turn to a side conversation bound to the item, never a new thread in the list; the answer
// comes back folded, with a dot until it is opened. "send an agent" starts the agent from the same box;
// its report lands here and in the thread's card log. Doors: /cc/sides* (scripts/cc/cc_sides.py).
import { useEffect, useRef, useState } from 'react'
import { sayBody, busy, stateWord } from '../lib/sides'

const mono = { fontFamily: 'var(--font-mono, monospace)' }

export default function SideNote({ item }) {
  const [side, setSide] = useState(null)
  const [draft, setDraft] = useState(() => { try { return localStorage.getItem('cc.inline.draft.' + item.key) || '' } catch { return '' } })
  const [err, setErr] = useState('')
  const timer = useRef(null)
  const load = () => fetch('/cc/sides?keys=' + encodeURIComponent(item.key), { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null)).then(d => { const s = d && (d.sides || [])[0]; if (s) setSide(s); return s }).catch(() => null)
  useEffect(() => {
    let stop = false
    const tick = async () => { const s = await load(); if (!stop) timer.current = setTimeout(tick, busy(s) ? 4000 : 15000) }
    tick()
    return () => { stop = true; clearTimeout(timer.current) }
  }, [item.key])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { try { if (draft) localStorage.setItem('cc.inline.draft.' + item.key, draft); else localStorage.removeItem('cc.inline.draft.' + item.key) } catch {} }, [draft, item.key])
  const send = async (mode) => {
    const text = draft.trim()
    if (!text || busy(side)) return
    setErr(''); setDraft('')
    setSide(s => ({ ...(s || { key: item.key }), state: 'running', ready: false, turns: [...((s && s.turns) || []), { who: 'me', text, mode }] }))
    try {
      const r = await fetch('/cc/sides/say', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sayBody(item, text, mode)) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { setErr(d.error || 'the door answered ' + r.status); setDraft(text); load(); return }
      if (d.side) setSide(d.side)
      clearTimeout(timer.current); timer.current = setTimeout(function again() { load().then(s => { timer.current = setTimeout(again, busy(s) ? 4000 : 15000) }) }, 2500)
    } catch { setErr('the console did not answer'); setDraft(text) }
  }
  const read = () => {
    setSide(s => ({ ...s, ready: false }))
    fetch('/cc/sides/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: item.key }) }).catch(() => {})
  }
  const turns = (side && side.turns) || []
  const foldAt = side && side.ready ? turns.length - 1 : -1
  const word = stateWord(side)
  const btn = (accent) => ({ ...mono, fontSize: '12px', borderRadius: '14px', padding: '4px 12px', cursor: 'pointer',
    border: '1px solid ' + (accent ? 'var(--accent)' : 'var(--border)'), background: accent ? 'var(--accent)' : 'transparent',
    color: accent ? 'var(--bg)' : 'var(--text)', opacity: busy(side) ? 0.5 : 1 })
  return (
    <div data-sidenote={item.key} onClick={e => e.stopPropagation()} style={{ marginTop: '10px', padding: '10px 12px', borderRadius: '10px', border: '1px solid var(--border)', background: 'var(--surface)' }}>
      {turns.map((t, i) => (
        t.who === 'me'
          ? <p key={i} style={{ margin: '0 0 6px 0', fontSize: '13px', color: 'var(--text-dim)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{t.mode === 'agent' ? 'agent: ' : 'you: '}{t.text}</p>
          : i === foldAt
            ? <a key={i} data-sidenote-ready="1" onClick={read} style={{ ...mono, display: 'block', margin: '0 0 6px 0', fontSize: '12px', color: 'var(--accent)', cursor: 'pointer' }}>● answer ready, press to read</a>
            : <p key={i} style={{ margin: '0 0 8px 0', fontSize: '14px', color: 'var(--text)', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.45 }}>{t.text}</p>
      ))}
      {((side && side.cards) || []).map(c => (
        <div key={c.id} style={{ margin: '0 0 8px 0', padding: '4px 8px', borderLeft: '2px solid var(--accent)' }}>
          <p style={{ ...mono, margin: 0, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-dim)' }}>{c.kind === 'job' ? 'job finished' : 'report'} · {(c.data && (c.data.title || c.data.id)) || ''}</p>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{String((c.data && c.data.result && c.data.result.text) || ((c.data && c.data.lines) || []).join('\n')).split('\n').slice(0, 6).join('\n')}</p>
        </div>
      ))}
      {word && word !== 'answer ready' ? <p style={{ ...mono, margin: '0 0 6px 0', fontSize: '12px', color: side && side.state === 'failed' ? '#d08a7a' : 'var(--text-dim)' }}>{word}</p> : null}
      {err ? <p style={{ ...mono, margin: '0 0 6px 0', fontSize: '12px', color: '#d08a7a' }}>{err}</p> : null}
      <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={2}
        onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send('ask') } }}
        placeholder={turns.length ? 'continue, or send an agent' : 'a question, a clarification, or what an agent should do'}
        style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', background: 'transparent', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: '8px', padding: '7px 9px', font: 'inherit', fontSize: '14px' }} />
      <div style={{ display: 'flex', gap: '8px', marginTop: '6px', flexWrap: 'wrap' }}>
        <button type="button" onClick={() => send('ask')} disabled={busy(side)} style={btn(true)}>ask</button>
        <button type="button" onClick={() => send('agent')} disabled={busy(side)} style={btn(false)}>send an agent</button>
      </div>
    </div>
  )
}
