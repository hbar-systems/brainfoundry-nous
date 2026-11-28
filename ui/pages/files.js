import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'
import MdView from '../components/MdView'
import { uploadFiles } from '../lib/bigUpload'

// Files: what the reasoner made, what you gave it, and the repositories it works in,
// browsed and played inside the console. Served by the bridge (/cc/files), which only
// reaches its fixed roots. Audio and video stream with range requests, so they seek.
// Added 2026-09-22 (session 2 of "replace the laptop").
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim)', faint: 'var(--muted)', line: 'var(--border)', card: 'var(--surface)', gold: 'var(--accent)' }

function fmtSize(n) { if (n < 1024) return `${n} B`; if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`; if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`; return `${(n / 1073741824).toFixed(2)} GB` }
function fmtWhen(ts) { const d = new Date(ts * 1000); return d.toISOString().slice(0, 16).replace('T', ' ') }
const isMdPath = (p) => /\.(md|markdown)$/i.test(p || '')
// The sidecar view is hand-made html; it runs in a sandbox that has scripts but no forms (hbar 2026-10-09).
// audit 2026-11-13 (app-files-save-html-runs-unsandboxed-on-console-origin): desk HTML runs in an opaque
// origin (no allow-same-origin), so a page saved by an app or a job can never read the console's owner key.
const VIEW_SANDBOX = 'allow-scripts allow-popups allow-downloads'
function raw(p) { return '/cc/files/raw' + p.split('/').map(encodeURIComponent).join('/') }
// Archives (FILES-ARCHIVE-1 2026-11-28, hbar: "No preview for this type" on regularization-arxiv.tar.gz): the pane
// lists what is inside; one member streams out of the archive through /cc/files/member, nothing is unpacked.
function memberUrl(p, name) { return '/cc/files/member?path=' + encodeURIComponent(p) + '&name=' + encodeURIComponent(name) }
// the archive's flat names as a folded tree: {dirs: {name: node}, files: [entry]}, sizes summed per folder
function archiveTree(entries) {
  const root = { dirs: {}, files: [], size: 0, count: 0 }
  for (const e of entries || []) {
    const parts = String(e.name || '').split('/').filter(Boolean)
    if (!parts.length) continue
    let node = root
    const upto = e.dir ? parts.length : parts.length - 1
    for (let i = 0; i < upto; i++) {
      node.dirs[parts[i]] = node.dirs[parts[i]] || { dirs: {}, files: [], size: 0, count: 0 }
      node = node.dirs[parts[i]]
      if (!e.dir) { node.size += e.size || 0; node.count += 1 }
    }
    if (!e.dir) node.files.push({ ...e, leaf: parts[parts.length - 1] })
  }
  return root
}

// An image in a folder shows itself (1127-b34fb2, hbar 2026-11-27: "i don't see any of these PNG's"): a small
// thumbnail, loaded lazily from the raw door, cropped to fill; until it loads (or if it cannot) the kind word stays.
function Thumb({ path, kind, size = 40 }) {
  const [bad, setBad] = useState(false)
  if (kind !== 'image' || bad) return <span style={{ ...mono, fontSize: '10px', color: T.faint, width: '44px', flexShrink: 0 }}>{kind}</span>
  return <img src={raw(path)} alt="" loading="lazy" decoding="async" onError={() => setBad(true)}
    style={{ width: `${size}px`, height: `${size}px`, objectFit: 'cover', borderRadius: '6px', backgroundColor: T.card, border: `1px solid ${T.line}`, flexShrink: 0, alignSelf: 'center', marginRight: '4px' }} />
}

export default function Files() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [sel, setSel] = useState(null)         // selected file info {path, kind, size}
  const [text, setText] = useState(null)
  const [arc, setArc] = useState(null)          // the open archive's listing {files, bytes, entries} or {error}
  const [member, setMember] = useState(null)    // the archive member open in the pane {name, kind, size}
  const [unfold, setUnfold] = useState({})      // archive folders unfolded, by path
  const deepMember = useRef(null)               // files?path=<archive>&member=<name> opens that member once listed
  // The md is the input, a visual is the output (2026-10-09): a note opens as its view, the source is one click away.
  const [mode, setMode] = useState('view')
  const [recent, setRecent] = useState([])
  // Edit and save (2026-09-28): a text file inside the world, out or in becomes a textarea; Save posts
  // it to the bridge, which refuses secrets, .git and the brain repo. A stale copy is a conflict.
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveNote, setSaveNote] = useState(null)   // {ok, text}
  // Drop a file anywhere on this page, or press "upload" (VIDEO-DOOR-1 2026-11-24, hbar: "GIVE ME A NORMAL PLACE
  // I CAN DRAG AND DROP THE VIDEO INTO!"). Any size up to the box's cap: big files go in resumable pieces
  // (ui/lib/bigUpload.js) into in/<date>/; one line says "412 of 640 MB", then where it landed.
  const pickRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [upLine, setUpLine] = useState(null)       // {busy, text, error}
  async function takeFiles(list) {
    const fs = Array.from(list || [])
    if (!fs.length || (upLine && upLine.busy)) return
    setUpLine({ busy: true, text: 'starting' })
    const d = await uploadFiles(fs, (line) => setUpLine({ busy: true, text: line }))
    if (!d.ok) { setUpLine({ error: true, text: 'Could not upload: ' + d.error }); return }
    const f = d.files[d.files.length - 1]
    setUpLine({ text: d.files.length === 1 ? `saved ${f.path}${f.sha256 ? ' · sha256 ' + f.sha256.slice(0, 12) : ''}` : `saved ${d.files.length} files in ${f.path.slice(0, f.path.lastIndexOf('/'))}`, path: f.path })
    load(f.path.slice(0, f.path.lastIndexOf('/')))
  }
  const dropProps = {
    onDragOver: (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) { e.preventDefault(); if (!dragging) setDragging(true) } },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false) },
    onDrop: (e) => { if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) { e.preventDefault(); setDragging(false); takeFiles(e.dataTransfer.files) } },
  }
  const embedded = typeof window !== 'undefined' && window.self !== window.top
  // Full screen (hbar 2026-10-13): a visual fills the whole screen, no list, no toolbar; files?path=..&full=1 opens it so.
  const [full, setFull] = useState(false)
  // A hand-made visual goes full screen alone; every other file view (2026-10-13) goes full screen with its toolbar.
  const visualOnly = (s) => s && (s.kind === 'html' || (isMdPath(s.path) && s.view && mode === 'view' && !editing))
  // In a narrow pane the list and the open file do not fit side by side (hbar's screenshot 2026-10-13:
  // the file's title squeezed to one letter a line, the body pushed out of sight): the file takes the pane.
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    const f = () => setNarrow(window.innerWidth < 760)
    f(); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f)
  }, [])
  function goFull(on) {
    setFull(on)
    try { const u = new URL(window.location.href); if (on) u.searchParams.set('full', '1'); else u.searchParams.delete('full'); window.history.replaceState(null, '', u.toString()) } catch {}
    try { if (on && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {}); else if (!on && document.fullscreenElement) document.exitFullscreen() } catch {}
  }
  useEffect(() => {
    // Escape leaves this page's full screen first, then the pane's (the console listens for cc-pane-esc)
    const k = (e) => {
      if (e.key !== 'Escape') return
      if (full) goFull(false)
      else if (embedded) { try { window.parent.postMessage({ type: 'cc-pane-esc' }, window.location.origin) } catch {} }
    }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [full])

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
    const sp = new URLSearchParams(window.location.search), q = sp.get('path')
    if (sp.get('full') === '1') setFull(true)
    if (sp.get('member')) deepMember.current = sp.get('member')
    load(q || null)
    fetch('/cc/files/recent', { cache: 'no-store' }).then(r => r.json()).then(d => setRecent(d.recent || [])).catch(() => {})
  }, [])
  function readText() {
    fetch(raw(sel.path), { cache: 'no-store' }).then(r => r.text()).then(setText).catch(() => setText('(could not read)'))
  }
  useEffect(() => {
    setText(null); setEditing(false); setSaveNote(null); setMode('view')
    if (sel && sel.kind === 'text' && sel.size < 400000) readText()
    setArc(null); setUnfold({}); setMember(null)
    if (sel && sel.kind === 'archive') {
      fetch('/cc/files/archive?path=' + encodeURIComponent(sel.path), { cache: 'no-store' })
        .then(r => r.json()).then(d => setArc(d)).catch(() => setArc({ error: 'the bridge did not answer' }))
    }
  }, [sel && sel.path])
  // a deep link (?member=) opens its member once the listing names its kind
  useEffect(() => {
    const want = deepMember.current
    if (!want || !arc || !arc.entries) return
    deepMember.current = null
    const e = arc.entries.find(x => x.name === want)
    if (e && !e.dir && e.kind !== 'link' && !e.unsafe) setMember({ name: e.name, kind: e.kind, size: e.size })
  }, [arc])
  const [mtext, setMtext] = useState(null)
  useEffect(() => {
    setMtext(null)
    if (!deepMember.current) { try { const u = new URL(window.location.href); if (member && member.name) u.searchParams.set('member', member.name); else u.searchParams.delete('member'); window.history.replaceState(null, '', u.toString()) } catch {} }
    if (member && sel && member.kind === 'text' && member.size < 400000) {
      fetch(memberUrl(sel.path, member.name), { cache: 'no-store' }).then(r => (r.ok ? r.text() : r.json().then(d => '(' + (d.error || 'could not read') + ')'))).then(setMtext).catch(() => setMtext('(could not read)'))
    }
  }, [member && member.name, member && member.kind, sel && sel.path])
  function openMember(e) {
    if (e.kind === 'link' || e.unsafe) return
    setMember({ name: e.name, kind: e.kind, size: e.size })
  }
  function folders(node, prefix, depth) {
    const rows = []
    const pad = { paddingLeft: `${16 + depth * 16}px` }
    for (const d of Object.keys(node.dirs).sort((a, b) => a.localeCompare(b))) {
      const key = prefix + d + '/', open = !!unfold[key], n = node.dirs[d]
      rows.push(
        <div key={'d:' + key} onClick={() => setUnfold(u => ({ ...u, [key]: !open }))} style={{ display: 'flex', gap: '10px', alignItems: 'baseline', padding: '7px 16px', ...pad, cursor: 'pointer', borderBottom: `1px solid ${T.line}` }}>
          <span style={{ ...mono, fontSize: '11px', color: T.gold, width: '12px', flexShrink: 0 }}>{open ? '\u25be' : '\u25b8'}</span>
          <span style={{ fontSize: '14px', color: T.ink, flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>{d}/</span>
          <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{n.count} {n.count === 1 ? 'file' : 'files'} · {fmtSize(n.size)}</span>
        </div>)
      if (open) rows.push(...folders(n, key, depth + 1))
    }
    for (const e of node.files.slice().sort((a, b) => a.leaf.localeCompare(b.leaf))) {
      const off = e.kind === 'link' || e.unsafe
      rows.push(
        <div key={'f:' + e.name} onClick={() => openMember(e)} title={off ? 'a link or an unsafe name; never opened from here' : e.name}
          style={{ display: 'flex', gap: '10px', alignItems: 'baseline', padding: '7px 16px', ...pad, cursor: off ? 'default' : 'pointer', borderBottom: `1px solid ${T.line}`, opacity: off ? 0.5 : 1 }}>
          <span style={{ width: '12px', flexShrink: 0 }} />
          <span style={{ fontSize: '14px', color: T.ink, flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>{e.leaf}</span>
          <span style={{ ...mono, fontSize: '10px', color: T.faint, flexShrink: 0 }}>{off ? 'link' : e.kind === 'other' ? '' : e.kind}</span>
          <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0, minWidth: '56px', textAlign: 'right' }}>{fmtSize(e.size || 0)}</span>
        </div>)
    }
    return rows
  }
  const editable = (p) => /\/(world|out|in)\//.test('/' + p + '/')
  const dirty = editing && draft !== text
  function startEdit() { setDraft(text || ''); setEditing(true); setMode('source'); setSaveNote(null) }
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
      <div {...dropProps} style={{ position: 'relative', display: 'flex', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '480px', color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
        {dragging && <div style={{ position: 'absolute', inset: '10px', zIndex: 5, border: `2px dashed ${T.gold}`, borderRadius: '14px', background: 'color-mix(in srgb, var(--surface) 88%, transparent)', display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none', fontSize: '18px', color: T.ink }}>Drop to put it on the box</div>}
        <div style={{ width: sel ? '42%' : '100%', minWidth: '280px', borderRight: sel ? `1px solid ${T.line}` : 0, display: sel && narrow ? 'none' : 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.line}`, display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <a onClick={() => { setData(d => ({ ...(d || {}), path: null, entries: [] })); fetch('/cc/files/recent', { cache: 'no-store' }).then(r => r.json()).then(d => setRecent(d.recent || [])).catch(() => {}) }} style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, cursor: 'pointer' }}>Files</a>
            <a onClick={() => { setData(d => ({ ...(d || {}), path: null, entries: [] })) }} style={{ ...mono, fontSize: '12px', color: data && !data.path ? T.ink : T.dim, cursor: 'pointer', textDecoration: 'underline' }}>newest</a>
            {data && data.roots && data.roots.map(r => (
              <a key={r.path} onClick={() => load(r.path)} style={{ ...mono, fontSize: '12px', color: data.path && data.path.startsWith(r.path) ? T.ink : T.dim, cursor: 'pointer', textDecoration: 'underline' }}>{r.label}</a>
            ))}
            <a onClick={() => pickRef.current && pickRef.current.click()} title="or drop a file anywhere on this page; any size, it lands in in/ under today's date" style={{ ...mono, fontSize: '12px', color: T.gold, cursor: 'pointer', textDecoration: 'underline', marginLeft: 'auto' }}>upload</a>
            <input ref={pickRef} type="file" multiple style={{ display: 'none' }} onChange={e => { takeFiles(e.target.files); e.target.value = '' }} />
          </div>
          {upLine && (
            <div style={{ ...mono, fontSize: '12px', padding: '8px 16px', borderBottom: `1px solid ${T.line}`, color: upLine.error ? 'var(--danger, #c0533a)' : upLine.busy ? T.ink : T.dim, overflowWrap: 'anywhere', display: 'flex', gap: '10px', alignItems: 'baseline' }}>
              <span style={{ flex: 1 }}>{upLine.busy ? 'uploading ' : ''}{upLine.text}</span>
              {!upLine.busy && <a onClick={() => setUpLine(null)} style={{ cursor: 'pointer', color: T.faint }}>x</a>}
            </div>
          )}
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
                  <div key={e.path} onClick={() => { setSel({ path: e.path, kind: e.kind, size: e.size, mtime: e.mtime, view: e.view }); load(e.dir) }}
                    style={{ display: 'flex', gap: '12px', alignItems: 'baseline', padding: '6px 16px', cursor: 'pointer', borderBottom: `1px solid ${T.line}` }}>
                    <Thumb path={e.path} kind={e.kind} />
                    <span style={{ fontSize: '14px', color: T.ink, flex: 1, wordBreak: 'break-all' }}>{e.name}{e.view && <span style={{ ...mono, fontSize: '9px', letterSpacing: '0.12em', textTransform: 'uppercase', color: T.gold, border: `1px solid ${T.gold}`, borderRadius: '8px', padding: '0 6px', marginLeft: '8px' }}>view</span>}<span style={{ ...mono, fontSize: '10px', color: T.faint, marginLeft: '8px' }}>{e.dir.split('/').slice(-2).join('/')}</span></span>
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
                <div key={e.name} onClick={() => (e.dir ? load(full) : setSel({ path: full, kind: e.kind, size: e.size, mtime: e.mtime, view: e.view }))}
                  style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px', alignItems: 'baseline', padding: '6px 16px', cursor: 'pointer', backgroundColor: active ? T.card : 'transparent', borderBottom: `1px solid ${T.line}` }}>
                  <Thumb path={full} kind={e.dir ? 'dir' : e.kind} />
                  <span style={{ fontSize: '14px', color: T.ink, flex: '1 1 160px', minWidth: 0, overflowWrap: 'anywhere' }}>{e.name}{e.dir ? '/' : ''}{e.view && <span title="a hand-made view sits beside this note; it opens first" style={{ ...mono, fontSize: '9px', letterSpacing: '0.12em', textTransform: 'uppercase', color: T.gold, border: `1px solid ${T.gold}`, borderRadius: '8px', padding: '0 6px', marginLeft: '8px' }}>view</span>}</span>
                  <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{e.dir ? '' : fmtSize(e.size)}</span>
                  <span style={{ ...mono, fontSize: '11px', color: T.faint, flexShrink: 0 }}>{fmtWhen(e.mtime)}</span>
                </div>
              )
            })}
            {data && data.entries && data.entries.length === 0 && <p style={{ padding: '16px', fontSize: '13px', color: T.dim }}>Empty.</p>}
          </div>
        </div>
        {sel && (
          <div style={full && !visualOnly(sel) ? { position: 'fixed', inset: 0, zIndex: 1000, backgroundColor: 'var(--bg)', display: 'flex', flexDirection: 'column' } : { flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            <div style={{ padding: '10px 16px', borderBottom: `1px solid ${T.line}`, display: 'flex', gap: '6px 12px', alignItems: 'baseline', flexWrap: 'wrap' }}>
              {narrow && !full && <a onClick={() => setSel(null)} title="back to the list" style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>list</a>}
              <span style={{ fontSize: '14px', color: T.ink, overflowWrap: 'anywhere', flex: '1 1 220px', minWidth: 0 }}>{sel.path.split('/').pop()}</span>
              <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{fmtSize(sel.size)}</span>
              {isMdPath(sel.path) && sel.kind === 'text' && !editing && (
                <span style={{ ...mono, fontSize: '12px', display: 'inline-flex', gap: '8px', alignItems: 'baseline' }} title="the md is the input; the view is the output">
                  <a onClick={() => setMode('view')} style={{ color: mode === 'view' ? T.gold : T.dim, textDecoration: mode === 'view' ? 'none' : 'underline', cursor: 'pointer', borderBottom: mode === 'view' ? `1px solid ${T.gold}` : 0 }}>{sel.view ? 'view' : 'view (auto)'}</a>
                  <a onClick={() => setMode('source')} style={{ color: mode === 'source' ? T.gold : T.dim, textDecoration: mode === 'source' ? 'none' : 'underline', cursor: 'pointer', borderBottom: mode === 'source' ? `1px solid ${T.gold}` : 0 }}>source</a>
                </span>
              )}
              <a onClick={() => goFull(!full)} title={full ? 'back (Escape)' : 'the whole screen; Escape comes back'} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>{full ? 'exit full screen' : 'full screen'}</a>
              <a href={raw(sel.path)} download style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline' }}>download</a>
              <a onClick={() => ask(sel.path)} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>ask the brain</a>
              {sel.kind === 'text' && text !== null && editable(sel.path) && !editing && <a onClick={startEdit} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>edit</a>}
              {editing && <a onClick={save} style={{ ...mono, fontSize: '12px', color: dirty ? T.gold : T.dim, textDecoration: 'underline', cursor: 'pointer', fontWeight: dirty ? 600 : 400 }}>{saving ? 'saving…' : dirty ? 'save' : 'saved'}</a>}
              {editing && <a onClick={cancelEdit} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>{dirty ? 'discard' : 'done'}</a>}
              {saveNote && <span style={{ ...mono, fontSize: '11px', color: saveNote.ok ? T.dim : '#d49a9a' }}>{saveNote.text}{saveNote.conflict ? <> · <a onClick={reloadAfterConflict} style={{ color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>reload</a></> : null}</span>}
              {onDesk(sel.path) && <a onClick={() => fileThis(sel.path)} title="move it into the world where it belongs and commit" style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>file this</a>}
              <a onClick={() => setSel(null)} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline', cursor: 'pointer' }}>close</a>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: full ? '24px max(24px, calc((100% - 1100px) / 2))' : '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {sel.kind === 'audio' && <audio controls preload="metadata" src={raw(sel.path)} style={{ width: '100%' }} />}
              {sel.kind === 'video' && <video controls preload="metadata" src={raw(sel.path)} style={{ width: '100%', maxHeight: '70vh', backgroundColor: '#000' }} />}
              {sel.kind === 'image' && <img src={raw(sel.path)} alt={sel.path} style={{ maxWidth: '100%', maxHeight: '80vh', objectFit: 'contain' }} />}
              {(sel.kind === 'pdf' || sel.kind === 'html') && <iframe src={raw(sel.path)} title={sel.path} sandbox={sel.kind === 'html' ? VIEW_SANDBOX : undefined} style={{ flex: 1, minHeight: '70vh', border: 0, backgroundColor: sel.kind === 'html' ? '#fff' : 'transparent' }} />}
              {sel.kind === 'text' && isMdPath(sel.path) && mode === 'view' && !editing && (sel.view
                ? <iframe key={sel.view} src={raw(sel.view)} title={sel.view} sandbox={VIEW_SANDBOX} allow="fullscreen" allowFullScreen style={{ flex: 1, minHeight: '70vh', border: 0, backgroundColor: '#fff' }} />
                : (text === null ? <p style={{ color: T.dim, fontSize: '13px' }}>{sel.size >= 400000 ? 'Too large for the view; open the source or download it.' : 'reading…'}</p>
                  : <MdView key={sel.path + ':' + sel.mtime} text={text} path={sel.path} open={load} />))}
              {sel.kind === 'text' && !(isMdPath(sel.path) && mode === 'view' && !editing) && (text === null ? <p style={{ color: T.dim, fontSize: '13px' }}>{sel.size >= 400000 ? 'Too large to show here; download it.' : 'reading…'}</p>
                : editing ? <textarea value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKey} spellCheck={false} autoFocus
                    style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, flex: 1, minHeight: '60vh', width: '100%', boxSizing: 'border-box', resize: 'vertical', padding: '10px', color: T.ink, backgroundColor: T.card, border: `1px solid ${dirty ? T.gold : T.line}`, borderRadius: '8px', outline: 'none' }} />
                : <pre onDoubleClick={() => { if (editable(sel.path)) startEdit() }} style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, color: T.ink }}>{text}</pre>)}
              {sel.kind === 'other' && <p style={{ color: T.dim, fontSize: '13px' }}>No preview for this type. Download it, or ask the brain what it is.</p>}
              {sel.kind === 'archive' && !member && (
                !arc ? <p style={{ color: T.dim, fontSize: '13px' }}>reading the archive…</p>
                : arc.error ? <p style={{ color: 'var(--danger, #c0533a)', fontSize: '13px' }}>{arc.error}</p>
                : <div style={{ margin: '-16px -16px 0' }}>
                    <p style={{ ...mono, fontSize: '12px', color: T.dim, margin: 0, padding: '10px 16px', borderBottom: `1px solid ${T.line}` }}>{arc.files} {arc.files === 1 ? 'file' : 'files'}, {fmtSize(arc.bytes)}{arc.more ? ` · first ${arc.entries.length} shown` : ''}</p>
                    {folders(archiveTree(arc.entries), '', 0)}
                  </div>
              )}
              {sel.kind === 'archive' && member && (<>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'baseline', flexWrap: 'wrap' }}>
                  <a onClick={() => setMember(null)} style={{ ...mono, fontSize: '12px', color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>{'\u2190'} back to the list</a>
                  <span style={{ fontSize: '14px', color: T.ink, overflowWrap: 'anywhere', flex: '1 1 160px', minWidth: 0 }}>{member.name}</span>
                  <span style={{ ...mono, fontSize: '11px', color: T.faint }}>{fmtSize(member.size || 0)}</span>
                  <a href={memberUrl(sel.path, member.name)} download={member.name.split('/').pop()} style={{ ...mono, fontSize: '12px', color: T.dim, textDecoration: 'underline' }}>download this</a>
                </div>
                {member.kind === 'audio' && <audio controls preload="metadata" src={memberUrl(sel.path, member.name)} style={{ width: '100%' }} />}
                {member.kind === 'video' && <video controls preload="metadata" src={memberUrl(sel.path, member.name)} style={{ width: '100%', maxHeight: '70vh', backgroundColor: '#000' }} />}
                {member.kind === 'image' && <img src={memberUrl(sel.path, member.name)} alt={member.name} style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain', alignSelf: 'flex-start' }} />}
                {(member.kind === 'pdf' || member.kind === 'html') && <iframe src={memberUrl(sel.path, member.name)} title={member.name} sandbox={member.kind === 'html' ? VIEW_SANDBOX : undefined} style={{ flex: 1, minHeight: '70vh', border: 0, backgroundColor: member.kind === 'html' ? '#fff' : 'transparent' }} />}
                {member.kind === 'text' && (member.size >= 400000 ? <p style={{ color: T.dim, fontSize: '13px' }}>Too large to show here; download it.</p>
                  : mtext === null ? <p style={{ color: T.dim, fontSize: '13px' }}>reading…</p>
                  : isMdPath(member.name) ? <MdView key={member.name} text={mtext} path={member.name} open={() => {}} />
                  : <pre style={{ ...mono, fontSize: '12.5px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0, color: T.ink }}>{mtext}</pre>)}
                {(member.kind === 'other' || member.kind === 'office' || member.kind === 'archive') && <p style={{ color: T.dim, fontSize: '13px' }}>No preview for this type inside an archive. Download it with the link above.</p>}
              </>)}
              {sel.kind === 'office' && (<>
                {(() => { const pdf = sel.path.replace(/\.[^./]+$/, '.pdf'); return (data && (data.entries || []).some(e => e.name && (sel.path.slice(0, sel.path.lastIndexOf('/') + 1) + e.name) === pdf)) ? <p style={{ ...mono, fontSize: '12px', margin: '0 0 8px 0' }}><a onClick={() => setSel({ ...sel, path: pdf, kind: 'pdf' })} style={{ color: T.gold, textDecoration: 'underline', cursor: 'pointer' }}>open the PDF beside it</a> <span style={{ color: T.faint }}>(the exact layout)</span></p> : null })()}
                <iframe src={'/cc/files/office?path=' + encodeURIComponent(sel.path)} title={sel.path} sandbox="" style={{ flex: 1, minHeight: '70vh', border: 0, backgroundColor: '#e9e6e1', borderRadius: '6px' }} />
              </>)}
              <p style={{ ...mono, fontSize: '11px', color: T.faint, margin: 0, wordBreak: 'break-all' }}>{sel.path}</p>
            </div>
          </div>
        )}
      </div>
      {full && visualOnly(sel) && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, backgroundColor: '#000' }}>
          <iframe src={raw(sel.kind === 'html' ? sel.path : sel.view)} title={sel.path} sandbox={VIEW_SANDBOX} allow="fullscreen" allowFullScreen style={{ width: '100%', height: '100%', border: 0, display: 'block' }} />
          <a onClick={() => goFull(false)} title="back to the files (Escape)" style={{ ...mono, position: 'fixed', top: '10px', right: '12px', fontSize: '11px', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.45)', backgroundColor: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '12px', padding: '3px 10px', cursor: 'pointer' }}>exit</a>
        </div>
      )}
    </>
  )
}
