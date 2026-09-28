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
function raw(p) { return '/cc/files/raw' + p.split('/').map(encodeURIComponent).join('/') }

export default function Files() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [sel, setSel] = useState(null)         // selected file info {path, kind, size}
  const [text, setText] = useState(null)
  const [recent, setRecent] = useState([])
  // Edit and save (2026-09-28): a text file inside the world, out or in becomes a textarea; Save posts
  // it to the bridge, which refuses secrets, .git and the brain repo. A stale copy is a conflict.
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveNote, setSaveNote] = useState(null)   // {ok, text}
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
    fetch('/cc/files/recent', { cache: 'no-store' }).then(r => r.json()).then(d => setRecent(d.recent || [])).catch(() => {})
  }, [])
  function readText() {
    fetch(raw(sel.path), { cache: 'no-store' }).then(r => r.text()).then(setText).catch(() => setText('(could not read)'))
  }
  useEffect(() => {
    setText(null); setEditing(false); setSaveNote(null)
    if (sel && sel.kind === 'text' && sel.size < 400000) readText()
  }, [sel && sel.path])
  const editable = (p) => /\/(world|out|in)\//.test('/' + p + '/')
  const dirty = editing && draft !== text
  function startEdit() { setDraft(text || ''); setEditing(true); setSaveNote(null) }
  function cancelEdit() { setEditing(false); setDraft(''); setSaveNote(null) }
  async function save() {
    if (!sel || saving) return
    setSaving(true); setSaveNote(null)
    try {
      const r = await fetch('/cc/files/write', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: sel.path, text: draft, mtime: sel.mtime }) })
      const d = await r.json().catch(() => ({}))
      if (r.ok && d.ok) {
        setText(draft); setSel(s => ({ ...s, size: d.size, mtime: d.mtime })); setEditing(false)
        setSaveNote({ ok: true, text: `saved ${new Date().toLocaleTimeString()}` })
        load(sel.path.slice(0, sel.path.lastIndexOf('/')) || '/')
      } else {
        setSaveNote({ ok: false, text: d.error || `could not save (${r.status})`, conflict: !!d.conflict, mtime: d.mtime })
      }
    } catch { setSaveNote({ ok: false, text: 'the bridge did not answer' }) }
    setSaving(false)
  }
  function reloadAfterConflict() {
    // take the newer copy from disk, keep the draft in the box so nothing typed is lost
    fetch(`/cc/files?path=${encodeURIComponent(sel.path)}`, { cache: 'no-store' }).then(r => r.json()).then(d => {
      if (d.file) setSel(s => ({ ...s, size: d.size, mtime: d.mtime }))
      readText(); setSaveNote({ ok: true, text: 'reloaded; the file below is the newer copy, your draft is unchanged' })
    }).catch(() => {})
  }
  function onKey(e) { if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (editing) save() } }

  function ask(p) {
    const t = `About the file ${p}: `
    if (embedded) { try { window.parent.postMessage({ type: 'cc-ask', text: t }, window.location.origin) } catch {} }
    else window.location.href = `/?ask=${encodeURIComponent(t)}`
  }
  // "file this": the desk (out, in) is not the archive; the reasoner moves the artifact into the
  // world where it belongs and commits, on the person's word. Sent as a message, so it goes
  // through the same cards as any other action (2026-09-24).
  function fileThis(p) {
    const t = `File this into the world where it belongs and commit (do not push): ${p}`
    if (embedded) { try { window.parent.postMessage({ type: 'cc-send', text: t }, window.location.origin) } catch {} }
    else window.location.href = `/?ask=${encodeURIComponent(t)}`
  }
  const onDesk = (p) => /\/(out|in)\//.test('/' + p + '/') && !/\/world\//.test('/' + p + '/')

  const crumbs = data && data.path ? data.path.split('/').filter(Boolean) : []
  return (
    <>
      <Head><title>Files · BrainFoundry</title></Head>
      <div style={{ display: 'flex', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '480px', color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
        <div style={{ width: sel ? '42%' : '100%', minWidth: '280px', borderRight: sel ? `1px solid ${T.line}` : 0, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.line}`, display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <a onClick={() => { setData(d => ({ ...(d || {}), path: null, entries: [] })); fetch('/cc/files/recent', { cache: 'no-store' }).then(r => r.json()).then(d => setRecent(d.recent || [])).catch(() => {}) }} style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, cursor: 'pointer' }}>Files</a>
            <a onClick={() => { setData(d => ({ ...(d || {}), path: null, entries: [] })) }} style={{ ...mono, fontSize: '12px', color: data && !data.path ? T.ink : T.dim, cursor: 'pointer', textDecoration: 'underline' }}>newest</a>
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
            {data && !data.path && (
              <div>
                <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.dim, padding: '12px 16px 4px' }}>newest, made by the brain</p>
                {recent.length === 0 && <p style={{ padding: '4px 16px 12px', fontSize: '13px', color: T.dim }}>Nothing yet. out is what the reasoner made, in is what you gave it, work is your repositories, world is the read-only mirror, brain is the brain's own code.</p>}
                {recent.map(e => (
                  <div key={e.path} onClick={() => { setSel({ path: e.path, kind: e.kind, size: e.size, mtime: e.mtime }); load(e.dir) }}
                    style={{ display: 'flex', gap: '12px', alignItems: 'baseline', padding: '6px 16px', cursor: 'pointer', borderBottom: `1px solid ${T.line}` }}>
                    <span style={{ ...mono, fontSize: '10px', color: T.faint, width: '44px', flexShrink: 0 }}>{e.kind}</span>
                    <span style={{ fontSize: '14px', color: T.ink, flex: 1, wordBreak: 'break-all' }}>{e.name}<span style={{ ...mono, fontSize: '10px', color: T.faint, marginLeft: '8px' }}>{e.dir.split('/').slice(-2).join('/')}</span></span>
                    <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{fmtWhen(e.mtime)}</span>
                  </div>
                ))}
              </div>
            )}
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
              {sel.kind === 'text' && text !== null && editable(sel.path) && !editing && <a onClick={startEdit} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>edit</a>}
              {editing && <a onClick={save} style={{ ...mono, fontSize: '12px', color: dirty ? T.gold : T.dim, textDecoration: 'underline', cursor: 'pointer', fontWeight: dirty ? 600 : 400 }}>{saving ? 'saving…' : dirty ? 'save' : 'saved'}</a>}
              {editing && <a onClick={cancelEdit} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>{dirty ? 'discard' : 'done'}</a>}
              {saveNote && <span style={{ ...mono, fontSize: '11px', color: saveNote.ok ? T.dim : '#d49a9a' }}>{saveNote.text}{saveNote.conflict ? <> · <a onClick={reloadAfterConflict} style={{ color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>reload</a></> : null}</span>}
              {onDesk(sel.path) && <a onClick={() => fileThis(sel.path)} title="move it into the world where it belongs and commit" style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>file this</a>}
              <a onClick={() => setSel(null)} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>close</a>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {sel.kind === 'audio' && <audio controls preload="metadata" src={raw(sel.path)} style={{ width: '100%' }} />}
              {sel.kind === 'video' && <video controls preload="metadata" src={raw(sel.path)} style={{ width: '100%', maxHeight: '70vh', backgroundColor: '#000' }} />}
              {sel.kind === 'image' && <img src={raw(sel.path)} alt={sel.path} style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain' }} />}
              {(sel.kind === 'pdf' || sel.kind === 'html') && <iframe src={raw(sel.path)} title={sel.path} style={{ flex: 1, minHeight: '70vh', border: 0, backgroundColor: sel.kind === 'html' ? '#fff' : 'transparent' }} />}
              {sel.kind === 'text' && (text === null ? <p style={{ color: T.dim, fontSize: '13px' }}>{sel.size >= 400000 ? 'Too large to show here; download it.' : 'reading…'}</p>
                : editing ? <textarea value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKey} spellCheck={false} autoFocus
                    style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, flex: 1, minHeight: '60vh', width: '100%', boxSizing: 'border-box', resize: 'vertical', padding: '10px', color: T.ink, backgroundColor: T.card, border: `1px solid ${dirty ? T.gold : T.line}`, borderRadius: '8px', outline: 'none' }} />
                : <pre onDoubleClick={() => { if (editable(sel.path)) startEdit() }} style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, color: T.ink }}>{text}</pre>)}
              {sel.kind === 'other' && <p style={{ color: T.dim, fontSize: '13px' }}>No preview for this type. Download it, or ask the brain what it is.</p>}
              <p style={{ ...mono, fontSize: '11px', color: T.faint, margin: 0, wordBreak: 'break-all' }}>{sel.path}</p>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
