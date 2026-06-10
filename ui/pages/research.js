import Head from 'next/head'
import { useState } from 'react'

function phaseLine(ev) {
  switch (ev.phase) {
    case 'planning': return '◆ Planning the research…'
    case 'plan': return '◆ Plan: ' + (ev.queries || []).join('  ·  ')
    case 'searching': return '🔎 Searching: ' + ev.query
    case 'reading': return '📄 Reading: ' + (ev.title || ev.url)
    case 'synthesizing': return '✍️ Writing report from ' + ev.source_count + ' sources…'
    case 'error': return '⚠ ' + ev.error
    default: return JSON.stringify(ev)
  }
}

export default function Research() {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [events, setEvents] = useState([])
  const [report, setReport] = useState('')
  const [sources, setSources] = useState([])

  const run = async () => {
    if (!q.trim() || busy) return
    setBusy(true); setEvents([]); setReport(''); setSources([])
    try {
      const r = await fetch('/api/bf/research', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q.trim() }),
      })
      if (!r.ok || !r.body) { setEvents([{ phase: 'error', error: 'HTTP ' + r.status }]); setBusy(false); return }
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = ''
      while (true) {
        const { done, value } = await reader.read(); if (done) break
        buf += dec.decode(value, { stream: true })
        let idx
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2)
          const line = chunk.split('\n').find(l => l.startsWith('data:'))
          if (!line) continue
          let ev; try { ev = JSON.parse(line.slice(5).trim()) } catch { continue }
          if (ev.phase === 'done') { setReport(ev.report || ''); setSources(ev.sources || []) }
          else setEvents(prev => [...prev, ev])
        }
      }
    } catch (e) { setEvents(prev => [...prev, { phase: 'error', error: String(e) }]) }
    setBusy(false)
  }

  return (
    <>
      <Head><title>Research · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '820px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>
        <h1 style={{ fontSize: 26, color: '#f0e8da', margin: '0 0 6px 0' }}>Deep Research</h1>
        <p style={{ color: '#9a8c7a', fontSize: 14, lineHeight: 1.6, margin: '0 0 22px 0' }}>
          Ask a question. Your brain plans searches, reads multiple sources, and writes a cited report —
          treating every page as untrusted reference, never as instructions.
        </p>

        <div style={{ display: 'flex', gap: 10, marginBottom: 22 }}>
          <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') run() }}
            placeholder="e.g. What are the most credible self-hosted AI assistant projects in 2026?"
            style={{ flex: 1, background: '#0e0c0a', border: '1px solid #2a2420', borderRadius: 8, color: '#e8e0d5', padding: '11px 13px', fontSize: 14, fontFamily: 'inherit' }} />
          <button onClick={run} disabled={busy || !q.trim()}
            style={{ background: (busy || !q.trim()) ? '#221c16' : '#c9a96e', color: (busy || !q.trim()) ? '#6b5f52' : '#1a1510', border: 'none', borderRadius: 8, padding: '0 22px', fontWeight: 600, fontSize: 14, cursor: busy ? 'default' : 'pointer', fontFamily: 'inherit' }}>
            {busy ? 'Researching…' : 'Research'}
          </button>
        </div>

        {events.length > 0 && (
          <div style={{ background: '#120f0c', border: '1px solid #1c1814', borderRadius: 10, padding: '14px 16px', marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 7 }}>
            {events.map((ev, i) => (
              <div key={i} style={{ color: ev.phase === 'error' ? '#c0392b' : '#9a8c7a', fontSize: 12.5, fontFamily: 'var(--font-mono, monospace)' }}>{phaseLine(ev)}</div>
            ))}
          </div>
        )}

        {report && (
          <div>
            <div style={{ color: '#f0e8da', fontSize: 14.5, lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>{report}</div>
            {sources.length > 0 && (
              <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid #1c1814' }}>
                <div style={{ color: '#c9a96e', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Sources</div>
                {sources.map((s, i) => (
                  <div key={i} style={{ fontSize: 12.5, marginBottom: 5 }}>
                    <span style={{ color: '#6b5f52' }}>[{i + 1}]</span>{' '}
                    <a href={s.url} target="_blank" rel="noreferrer" style={{ color: '#9a8c7a' }}>{s.title || s.url}</a>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
