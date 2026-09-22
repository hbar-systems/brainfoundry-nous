import Head from 'next/head'
import { useEffect, useState } from 'react'

// Files: what the reasoner made, what you gave it, and the repositories it works in,
// browsed and played inside the console. Served by the bridge (/cc/files), which only
// reaches its fixed roots. Audio and video stream with range requests, so they seek.
// Added 2026-09-22 (session 2 of "replace the laptop").
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim, #9a8f82)', faint: 'var(--text-faint, #6b5f52)', line: 'var(--line, #2a2621)', card: 'var(--card, #16140f)', gold: 'var(--accent, #c9a96e)' }

function fmtSize(n) { if (n < 1024) return `${n} B`; if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`; if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`; return `${(n / 1073741824).toFixed(2)} GB` }
function fmtWhen(ts) { const d = new Date(ts * 1000); return d.toISOString().slice(0, 16).replace('T', ' ') }
function raw(p) { return `/cc/files/raw?path=${encodeURIComponent(p)}` }

export default function Files() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [sel, setSel] = useState(null)         // selected file info {path, kind, size}
  const [text, setText] = useState(null)
  const embedded = typeof window !== 'undefined' && window.self !== window.top

  function load(path) {
    setError(null)
    fetch(`/cc/files${path ? `?path=${encodeURIComponent(path)}` : ''}`, { cache: 'no-store' })
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); return }
        if (d.file) { setSel(d); load(d.path.slice(0, d.path.lastIndexOf('/')) || '/'); return }
        setData(d)
        try { const u = new URL(window.location.href); if (path) u.searchParams.set('path', path); else u.searchParams.delete('path'); window.history.replaceState(null, '', u.toString()) } catch {}
      })
      .catch(() => setError('the bridge did not answer'))
  }
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get('path')
    load(q || null)
  }, [])
  useEffect(() => {
    setText(null)
    if (sel && sel.kind === 'text' && sel.size < 400000) {
      fetch(raw(sel.path), { cache: 'no-store' }).then(r => r.text()).then(setText).catch(() => setText('(could not read)'))
    }
  }, [sel && sel.path])

  function ask(p) {
    const t = `About the file ${p}: `
    if (embedded) { try { window.parent.postMessage({ type: 'cc-ask', text: t }, window.location.origin) } catch {} }
    else window.location.href = `/?ask=${encodeURIComponent(t)}`
  }

  const crumbs = data && data.path ? data.path.split('/').filter(Boolean) : []
  return (
    <>
      <Head><title>Files · BrainFoundry</title></Head>
      <div style={{ display: 'flex', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '480px', color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
        <div style={{ width: sel ? '42%' : '100%', minWidth: '280px', borderRight: sel ? `1px solid ${T.line}` : 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.line}`, display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <span style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold }}>Files</span>
            {data && data.roots && data.roots.map(r => (
              <a key={r.path} onClick={() => load(r.path)} style={{ ...mono, fontSize: '12px', color: data.path && data.path.startsWith(r.path) ? T.ink : T.dim, cursor: 'pointer', textDecoration: 'underline' }}>{r.label}</a>
            ))}
          </div>
          {data && data.path && (
            <div style={{ ...mono, fontSize: '12px', color: T.dim, padding: '8px 16px', borderBottom: `1px solid ${T.line}`, wordBreak: 'break-all' }}>
              {crumbs.map((c, i) => {
                const p = '/' + crumbs.slice(0, i + 1).join('/')
                return <span key={p}><a onClick={() => load(p)} style={{ cursor: 'pointer', color: i === crumbs.length - 1 ? T.ink : T.dim }}>{c}</a>{i < crumbs.length - 1 ? ' / ' : ''}</span>
              })}
            </div>
          )}
          {error && <p style={{ padding: '16px', color: '#d08a7a', fontSize: '13px' }}>{error}</p>}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {data && !data.path && <p style={{ padding: '16px', fontSize: '13px', color: T.dim }}>Pick a place above: out is what the reasoner made, in is what you gave it, work is your repositories, world is the read-only mirror, brain is the brain's own code.</p>}
            {data && data.parent && data.path !== data.parent && (
              <div onClick={() => load(data.parent)} style={{ ...mono, fontSize: '12px', padding: '6px 16px', cursor: 'pointer', color: T.dim }}>..</div>
            )}
            {data && data.entries && data.entries.map(e => {
              const full = `${data.path.replace(/\/$/, '')}/${e.name}`
              const active = sel && sel.path === full
              return (
                <div key={e.name} onClick={() => (e.dir ? load(full) : setSel({ path: full, kind: e.kind, size: e.size, mtime: e.mtime }))}
                  style={{ display: 'flex', gap: '12px', alignItems: 'baseline', padding: '6px 16px', cursor: 'pointer', backgroundColor: active ? T.card : 'transparent', borderBottom: `1px solid ${T.line}` }}>
                  <span style={{ ...mono, fontSize: '10px', color: T.faint, width: '44px', flexShrink: 0 }}>{e.dir ? 'dir' : e.kind}</span>
                  <span style={{ fontSize: '14px', color: T.ink, flex: 1, wordBreak: 'break-all' }}>{e.name}{e.dir ? '/' : ''}</span>
                  <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{e.dir ? '' : fmtSize(e.size)}</span>
                  <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{fmtWhen(e.mtime)}</span>
                </div>
              )
            })}
            {data && data.entries && data.entries.length === 0 && <p style={{ padding: '16px', fontSize: '13px', color: T.dim }}>Empty.</p>}
          </div>
        </div>
        {sel && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.line}`, display: 'flex', gap: '12px', alignItems: 'baseline', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '14px', color: T.ink, wordBreak: 'break-all', flex: 1 }}>{sel.path.split('/').pop()}</span>
              <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{fmtSize(sel.size)}</span>
              <a href={raw(sel.path)} download style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline' }}>download</a>
              <a onClick={() => ask(sel.path)} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>ask the brain</a>
              <a onClick={() => setSel(null)} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>close</a>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {sel.kind === 'audio' && <audio controls preload="metadata" src={raw(sel.path)} style={{ width: '100%' }} />}
              {sel.kind === 'video' && <video controls preload="metadata" src={raw(sel.path)} style={{ width: '100%', maxHeight: '70vh', backgroundColor: '#000' }} />}
              {sel.kind === 'image' && <img src={raw(sel.path)} alt={sel.path} style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain' }} />}
              {sel.kind === 'pdf' && <iframe src={raw(sel.path)} title={sel.path} style={{ flex: 1, minHeight: '70vh', border: 0 }} />}
              {sel.kind === 'text' && (text === null ? <p style={{ color: T.dim, fontSize: '13px' }}>{sel.size >= 400000 ? 'Too large to show here; download it.' : 'reading…'}</p>
                : <pre style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, color: T.ink }}>{text}</pre>)}
              {sel.kind === 'other' && <p style={{ color: T.dim, fontSize: '13px' }}>No preview for this type. Download it, or ask the brain what it is.</p>}
              <p style={{ ...mono, fontSize: '11px', color: T.faint, margin: 0, wordBreak: 'break-all' }}>{sel.path}</p>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
