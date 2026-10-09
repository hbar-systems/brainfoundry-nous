import Head from 'next/head'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { splitPaths, isImagePath, rawUrl, hrefToPath, remarkPathLinks } from '../lib/pathlinks'

// CC — a plain chat surface backed by a reasoner running on the brain's own box.
//
// The page talks to a small bridge served on the SAME origin as the console at
// /cc/* (scripts/cc/cc-bridge.py, installed by scripts/cc/install.sh). The
// bridge runs one headless reasoner turn per message inside the brain repo,
// grounds it in the brain's persona and memory, keeps the conversation id, and
// answers as the brain. Nothing in the chat names a vendor; the person is
// talking to their brain.
//
// Sign-in happens here too, without a terminal: the bridge drives the CLI's
// login through a pseudo-terminal, hands us the sign-in URL, we hand back the
// code. The sign-in card has to name the account being signed into; that is
// the one place a vendor appears, because it is the person's own account.
//
// The tab is opt-in per brain: BRAIN_CC_ENABLED=true in .env makes the api
// list the `_cc` tab (api/apps.py). Without the bridge the page says so.

// The console's theme and font settings apply here too (Settings > appearance):
// every colour is a CSS variable set in _app.js, not a fixed palette.
const C = {
  ink: 'var(--text)', dim: 'var(--muted)', faint: 'var(--muted)', gold: 'var(--accent)',
  card: 'var(--surface2)', line: 'var(--border)', me: 'var(--user-bg)', meText: 'var(--user-text)', brain: 'var(--surface)', bad: '#7a3a2e',
  onAccent: 'var(--bg)', codeBg: 'var(--code-bg)', codeFg: 'var(--code-fg)',
}
const mono = { fontFamily: 'var(--font-mono, monospace)' }

function shortModel(m) { return String(m || '').replace(/^claude-/, '').replace(/-\d{8}$/, '') }
function kTok(n) { n = Number(n) || 0; return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n) }
const SLASH = [
  { c: '/new', d: 'start a new thread' },
  { c: '/stop', d: 'stop the answer in progress; the thread keeps everything up to here (Esc does the same)' },
  { c: '/model', d: 'pick the model: /model sonnet, /model opus, or a full id; /model alone for the default' },
  { c: '/posture', d: 'own-box actions: /posture cards (every edit and command asks), /posture auto (the vendor classifier decides), /posture judged (TypeSafe scores each action; harmless runs, the rest ask)' },
  { c: '/pane', d: 'open a pane beside the chat: /pane /graph' },
  { c: '/files', d: 'open the files pane: what the brain made, what you gave it, your repositories' },
  { c: '/guide', d: 'open the guide and the tutorial beside the chat' },
  { c: '/file', d: '/file <path> [where]: the reasoner moves an artifact from out/ or in/ into the world where it belongs and commits (no push)' },
  { c: '/voice', d: 'the brain reads its answers aloud: /voice on, /voice off, /voice list (click a name), /voice <name>' },
  { c: '/talk', d: 'speak instead of typing: /talk listens (a pause or a second /talk ends it); /talk free on|off is hands-free, what you say sends by itself and listening restarts after the answer' },
  { c: '/jobs', d: 'list jobs running on the box' },
  { c: '/help', d: 'this list' },
]

// The composer's buttons in a pane (2026-10-06): icons, one line high. Drawn here; never the browser's own look.
function IconBtn({ children, onClick, disabled, primary, on, title }) {
  const off = !!disabled
  return (
    <button onClick={onClick} disabled={off} title={title} aria-label={title}
      style={{ width: '34px', height: '34px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0, borderRadius: '9px',
               cursor: off ? 'default' : 'pointer', border: primary ? 'none' : `1px solid ${on ? C.gold : C.line}`,
               backgroundColor: primary ? (off ? C.card : C.gold) : 'transparent', color: primary ? (off ? C.dim : C.onAccent) : (on ? C.gold : C.dim) }}>{children}</button>
  )
}
const ico = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' }
const IcoClip = () => <svg {...ico}><path d="M21.4 11.1l-9.2 9.2a6 6 0 01-8.5-8.5l9.2-9.2a4 4 0 015.7 5.7l-9.2 9.2a2 2 0 01-2.8-2.8l8.5-8.5" /></svg>
const IcoMic = () => <svg {...ico}><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10v1a7 7 0 0014 0v-1M12 18v4" /></svg>
const IcoStop = () => <svg {...ico}><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
const IcoSend = () => <svg {...ico}><path d="M12 19V5M5 12l7-7 7 7" /></svg>

function Btn({ children, onClick, disabled, primary, small, title, accent }) {
  const off = !!disabled
  return (
    <button onClick={onClick} disabled={off} title={title}
      style={{
        padding: small ? '6px 12px' : '10px 16px', borderRadius: '10px', cursor: off ? 'default' : 'pointer',
        border: primary ? 'none' : `1px solid ${accent ? C.gold : C.line}`,
        backgroundColor: primary ? (off ? C.card : C.gold) : 'transparent',
        color: primary ? (off ? C.dim : C.onAccent) : (accent ? C.gold : C.dim),
        fontWeight: primary ? 600 : 400, fontSize: small ? '12px' : '14px', fontFamily: small ? mono.fontFamily : 'inherit',
      }}>{children}</button>
  )
}

// The text inside a rendered code block, for its copy button (react-markdown hands the hast node over).
function hastText(node) {
  if (!node) return ''
  if (node.type === 'text') return node.value || ''
  return (node.children || []).map(hastText).join('')
}
function copyText(text) { try { navigator.clipboard.writeText(text || '') } catch {} }
function CopyLink({ text, label, style }) {
  const [done, setDone] = useState(false)
  return <a onClick={(e) => { e.stopPropagation(); copyText(text); setDone(true); setTimeout(() => setDone(false), 1200) }} title="copy" style={{ ...mono, fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: done ? C.gold : C.faint, cursor: 'pointer', textDecoration: 'underline', ...(style || {}) }}>{done ? 'copied' : (label || 'copy')}</a>
}
// A path on the box in a message is a link (2026-10-09): click opens the Files pane (images shown
// there inline), hover on an image shows it small beside the link.
function openPath(p) { window.dispatchEvent(new CustomEvent('cc-open-path', { detail: p })) }
function PathLink({ path, children, style }) {
  const [hov, setHov] = useState(false)
  const img = isImagePath(path)
  return (
    <span style={{ position: 'relative', display: 'inline' }} onMouseEnter={() => img && setHov(true)} onMouseLeave={() => setHov(false)}>
      <a onClick={(e) => { e.stopPropagation(); openPath(path) }} title={`Open ${path}`} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline dotted', overflowWrap: 'anywhere', ...(style || {}) }}>{children || path}</a>
      {hov && <img src={rawUrl(path)} alt="" style={{ position: 'absolute', left: 0, top: '1.6em', zIndex: 40, maxWidth: '260px', maxHeight: '200px', objectFit: 'contain', backgroundColor: '#000', border: `1px solid ${C.line}`, borderRadius: '6px', pointerEvents: 'none' }} />}
    </span>
  )
}
// Plain text (the person's own messages) with its paths made into links.
function LinkedText({ text }) {
  const parts = useMemo(() => splitPaths(text), [text])
  if (parts.length === 1 && parts[0].t === 'text') return <>{text}</>
  return <>{parts.map((p, i) => (p.t === 'path' ? <PathLink key={i} path={p.v} /> : <React.Fragment key={i}>{p.v}</React.Fragment>))}</>
}
// A thumbnail for a file chosen in the composer (images only), made from the file itself, freed on removal.
function ChipThumb({ file }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    if (!file || !/^image\//.test(file.type || '')) return undefined
    const u = URL.createObjectURL(file); setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [file])
  if (!url) return null
  return <img src={url} alt="" style={{ width: '28px', height: '28px', objectFit: 'cover', borderRadius: '4px', verticalAlign: 'middle', marginRight: '6px', backgroundColor: '#000' }} />
}
// Selection snapped to the whole paragraph (2026-10-09). The renderer's `components` used to be
// written inline in Md: new function identities on every render, so React unmounted and rebuilt
// every <p>, <code>, <li> of every message on each render (the 2.5 s state poll, the pick popup's
// own setState, a stream chunk). The DOM nodes holding the selection's ends were destroyed and the
// browser moved the ends up to the parent, which selects the paragraph or several blocks above.
// Now the components are built once per `base` (useMemo) and Md is memoised on its text, so a
// message's DOM is reused in place and a dragged selection stays exactly as dragged.
function mdComponents(base) {
  return {
    a: ({ node, ...props }) => {
      // a path on the box (found in the text by remarkPathLinks, or written as a markdown link to a file)
      // opens in the Files pane; a web address opens in a new tab
      const cc = props['data-ccpath']
      const fp = cc || hrefToPath(props.href)
      if (fp) {
        const target = fp.startsWith('/') ? fp : (base && !fp.includes('/') ? `${base}/${fp}` : fp)
        return <PathLink path={target}>{props.children}</PathLink>
      }
      return <a {...props} target="_blank" rel="noreferrer" style={{ color: C.gold }} />
    },
    p: ({ node, ...props }) => <p {...props} style={{ margin: '0 0 8px 0' }} />,
    ul: ({ node, ...props }) => <ul {...props} style={{ margin: '0 0 8px 0', paddingLeft: '20px' }} />,
    ol: ({ node, ...props }) => <ol {...props} style={{ margin: '0 0 8px 0', paddingLeft: '20px' }} />,
    // react-markdown 9 no longer passes `inline`; a code block arrives wrapped in <pre>,
    // so the block look lives on pre and every <code> stays inline (observed 2026-09-20:
    // inline code rendered as full-width boxes and broke sentences apart).
    // every code block carries its own copy button (2026-09-29: "we need things to have a copyable button")
    pre: ({ node, ...props }) => (
      <div style={{ position: 'relative', margin: '4px 0 8px 0' }}>
        <pre {...props} style={{ ...mono, fontSize: '12.5px', backgroundColor: C.codeBg, color: C.codeFg, padding: '8px 52px 8px 10px', borderRadius: '6px', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowX: 'auto' }} />
        <CopyLink text={hastText(node)} style={{ position: 'absolute', top: '6px', right: '8px' }} />
      </div>
    ),
    code: ({ node, ...props }) => {
      // An absolute path on the box opens the Files pane at that file or folder.
      const s = typeof props.children === 'string' ? props.children : (Array.isArray(props.children) && typeof props.children[0] === 'string' ? props.children[0] : null)
      const isAbs = s && /^\/(home|opt|srv|var|tmp)\/[^\n]+$/.test(s.trim()) && s.length < 300
      // a bare name or a relative path (ops/x.md) with a file suffix: the folder last named in the
      // message if any, else the world (the bridge falls back to the world's root when the guess misses)
      const isFile = s && /^[\w][\w.\/ -]{0,200}\.[A-Za-z0-9]{1,5}$/.test(s.trim()) && !s.includes('..')
      if (isAbs || isFile) {
        const rel = s.trim()
        const target = isAbs ? rel.replace(/[.,:;)]+$/, '') : (base && !rel.includes('/') ? `${base}/${rel}` : rel)
        return <PathLink path={target} style={{ ...mono, fontSize: '12.5px', backgroundColor: C.codeBg, padding: '1px 5px', borderRadius: '4px' }}>{s}</PathLink>
      }
      return <code {...props} style={{ ...mono, fontSize: '12.5px', backgroundColor: C.codeBg, color: C.codeFg, padding: '1px 5px', borderRadius: '4px' }} />
    },
    table: ({ node, ...props }) => <table {...props} style={{ borderCollapse: 'collapse', fontSize: '13px', margin: '4px 0 8px 0' }} />,
    th: ({ node, ...props }) => <th {...props} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: `1px solid ${C.line}`, color: C.dim, fontWeight: 500 }} />,
    td: ({ node, ...props }) => <td {...props} style={{ padding: '4px 8px', borderBottom: `1px solid ${C.line}` }} />,
  }
}
const Md = React.memo(function Md({ text }) {
  // The reasoner answers in markdown. Render it, but keep it plain: no raw HTML,
  // links open in a new tab, code stays monospace.
  // The last absolute folder named in the message is the base for bare filenames in it,
  // so "index.html" next to "/home/cc/out/.../" opens as that file (2026-09-22).
  const dirs = (text || '').match(/\/(?:home|opt|srv|var|tmp)\/[^\s`'")]+\//g) || []
  const base = dirs.length ? dirs[dirs.length - 1].replace(/\/$/, '') : null
  const components = useMemo(() => mdComponents(base), [base])
  return (
    <div className="cc-md">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkPathLinks]} skipHtml urlTransform={(u) => (/^file:/i.test(u) ? u : defaultUrlTransform(u))} components={components}>{text || ''}</ReactMarkdown>
    </div>
  )
})

function ProposalCard({ p, onDecide }) {
  // One proposed write, waiting for the person. The summary names platform,
  // action and target; Send mints the permit and runs exactly that. Nothing
  // happens without the click; Cancel is audited too.
  if (p.error) {
    return (
      <div style={{ marginTop: '10px', padding: '10px 12px', borderRadius: '10px', border: `1px solid ${C.bad}`, color: '#d08a7a', fontSize: '13px' }}>
        Write refused: {p.error}
      </div>
    )
  }
  const [remember, setRemember] = useState(false)
  const decided = p.decided
  const box = p.platform === 'box'
  if (p.auto) {
    const ok = p.outcome && p.outcome.ok
    return (
      <div style={{ marginTop: '10px', padding: '10px 14px', borderRadius: '10px', border: `1px solid ${ok ? C.line : C.bad}`, backgroundColor: C.card }}>
        <p style={{ ...mono, color: C.dim, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
          {ok ? 'done without asking' : 'tried without asking, failed'} · {p.method || 'POST'} · {p.platform || ''}
        </p>
        <p style={{ margin: 0, color: C.ink, fontSize: '14px', lineHeight: 1.5 }}>{p.summary}</p>
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '6px 0 0 0' }}>{p.why || 'you allowed this action earlier'} · permit {p.id}{ok ? '' : ` · ${(p.outcome && p.outcome.result && p.outcome.result.error) || 'error'}`}</p>
      </div>
    )
  }
  return (
    <div style={{ marginTop: '10px', padding: '12px 14px', borderRadius: '10px', border: `1px solid ${C.gold}`, backgroundColor: C.card }}>
      <p style={{ ...mono, color: C.gold, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
        {box ? `on this box · ${p.method || 'action'}` : `proposed write · ${p.method || 'POST'} · ${p.platform || ''}`}
      </p>
      <p style={{ margin: '0 0 10px 0', color: C.ink, fontSize: '14px', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: box ? "'JetBrains Mono', ui-monospace, monospace" : 'inherit' }}>{p.summary || 'an action in a connected app'}</p>
      {decided ? (
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: 0 }}>{decided === 'approve' ? (box ? 'allowed' : 'sent') : (box ? 'refused' : 'cancelled')} · permit {p.id}</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Btn primary onClick={() => onDecide(p.id, 'approve', remember)} disabled={p.busy}>{p.busy ? '…' : (box ? 'Allow' : 'Send')}</Btn>
            <Btn onClick={() => onDecide(p.id, 'deny')} disabled={p.busy}>{box ? 'Refuse' : 'Cancel'}</Btn>
            <span style={{ ...mono, color: C.faint, fontSize: '11px' }}>permit {p.id}{p.ttl_seconds ? ` · valid ${Math.round(p.ttl_seconds / 60)} min` : ''}{p.judge ? ` · judged:${p.judge.safe != null ? ` safe ${p.judge.safe.toFixed(2)},` : ''} on request ${p.judge.intent.toFixed(2)}, risk ${p.judge.risk.toFixed(1)}` : ''}</span>
          </div>
          {p.held && <p style={{ ...mono, color: C.gold, fontSize: '11px', margin: '8px 0 0 0' }}>{p.held}</p>}
          {p.remember_ok !== false && (
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '10px', color: C.dim, fontSize: '12px', cursor: 'pointer' }}>
            <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} disabled={p.busy} style={{ accentColor: C.gold }} />
            {box ? (String(p.action_id || '').startsWith('exact:') ? `don't ask again for exactly this command; still recorded in the audit, you can undo it below` : `don't ask again for "${p.action_id}"; still recorded in the audit, you can undo it below`) : `don't ask again for this action (${p.platform}, ${p.method || 'POST'}); still recorded in the audit, you can undo it below`}
          </label>
          )}
        </>
      )}
    </div>
  )
}

function Pane({ pane, onClose, side, onSide }) {
  // A summoned surface (D54): an existing console page, same origin and auth, shown
  // beside the conversation and dismissed with one click. Pages hide their own nav
  // when embedded (see _app.js). Narrow screens get it as an overlay; "wide" covers
  // the whole console; the page itself may go fullscreen (allowFullScreen).
  const [narrow, setNarrow] = useState(false)
  const [wide, setWide] = useState(false)
  // The width is the owner's: drag the divider on the pane's inner edge. Remembered in cc.paneW (px).
  const [w, setW] = useState(null)
  const [drag, setDrag] = useState(false)
  useEffect(() => { try { const v = parseInt(localStorage.getItem('cc.paneW') || '', 10); if (v >= 280) setW(v) } catch {} }, [])
  const startDrag = (e) => {
    e.preventDefault()
    const x0 = e.clientX, w0 = w || Math.min(window.innerWidth * 0.48, 760), dir = side === 'left' ? 1 : -1
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch {}
    setDrag(true)
    let last = w0
    const move = (ev) => { last = Math.round(Math.max(280, Math.min(window.innerWidth - 320, w0 + dir * (ev.clientX - x0)))); setW(last) }
    const up = () => { setDrag(false); try { localStorage.setItem('cc.paneW', String(last)) } catch {}; window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up)
  }
  useEffect(() => {
    const f = () => setNarrow(window.innerWidth < 960)
    f(); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f)
  }, [])
  const box = (narrow || wide)
    ? { position: 'fixed', top: 'calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px))', right: 0, bottom: 0, left: 0, zIndex: 150, backgroundColor: C.brain, display: 'flex', flexDirection: 'column' }
    : { width: w ? `${w}px` : 'min(48vw, 760px)', flexShrink: 0, backgroundColor: C.brain, display: 'flex', flexDirection: 'column', position: 'relative' }
  const inline = !(narrow || wide)
  return (
    <div style={box}>
      {inline && <div onPointerDown={startDrag} onDoubleClick={() => { setW(null); try { localStorage.removeItem('cc.paneW') } catch {} }} title="Drag to resize; double-click to reset"
           style={{ position: 'absolute', top: 0, bottom: 0, [side === 'left' ? 'right' : 'left']: '-4px', width: '9px', cursor: 'col-resize', zIndex: 5, touchAction: 'none', display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '1px', height: '100%', backgroundColor: drag ? C.gold : C.line }} />
      </div>}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: `1px solid ${C.line}` }}>
        <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>{pane.title || pane.route}</span>
        <span style={{ display: 'flex', gap: '8px' }}>
          {inline && <Btn small onClick={onSide} title="Put it on the other side of the conversation">{side === 'left' ? 'to right' : 'to left'}</Btn>}
          {!narrow && <Btn small onClick={() => setWide(x => !x)} title={wide ? 'Back beside the conversation' : 'Cover the whole console'}>{wide ? 'beside' : 'wide'}</Btn>}
          <Btn small onClick={onClose} title="Put it away">close</Btn>
        </span>
      </div>
      <iframe src={pane.route} title={pane.title || pane.route} allowFullScreen allow="fullscreen" style={{ flex: 1, width: '100%', border: 0, backgroundColor: C.brain, pointerEvents: drag ? 'none' : 'auto' }} />
    </div>
  )
}

function FirstRun({ steps, onOpen }) {
  // The first-use steps as sentences from the brain, on the home screen (D54). The
  // reasoner sign-in card covers the key step, so it is not repeated here.
  const rows = (steps || []).filter(s => s.key !== 'key')
  if (rows.length === 0) return null
  return (
    <div style={{ margin: '0 0 16px 0' }}>
      {rows.map(s => (
        <p key={s.key} style={{ margin: '0 0 6px 0', color: s.done ? C.faint : C.dim, fontSize: '14px', lineHeight: 1.6 }}>
          {s.done ? '\u2713 ' : ''}{s.label}{!s.done && s.sub ? `. ${s.sub}` : ''}
          {!s.done && s.href ? <> <a onClick={() => onOpen({ route: s.href, title: s.cta || s.label })} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>{s.cta || 'open'}</a></> : null}
        </p>
      ))}
    </div>
  )
}

function SignIn({ onDone, health, onOpenPane }) {
  const [state, setState] = useState({ phase: 'idle' })
  const [code, setCode] = useState('')
  const [method, setMethod] = useState(null)
  const [apiKey, setApiKey] = useState('')
  const [apiErr, setApiErr] = useState(null)
  const timer = useRef(null)

  async function useKey() {
    setApiErr(null)
    try {
      const r = await fetch('/cc/login/apikey', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: apiKey.trim() }) })
      const d = await r.json().catch(() => ({}))
      if (r.ok && d.ok) { setApiKey(''); onDone() } else setApiErr(d.error || 'the key was not accepted')
    } catch { setApiErr('the bridge did not answer') }
  }

  const poll = async () => {
    try {
      const r = await fetch('/cc/login/state', { cache: 'no-store' })
      const s = await r.json()
      setState(s)
      if (s.phase === 'done' || s.loggedIn) { stop(); onDone() }
      if (s.phase === 'error') stop()
    } catch { /* keep polling */ }
  }
  const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
  useEffect(() => () => stop(), [])

  async function start(m) {
    setMethod(m); setCode('')
    setState({ phase: 'starting' })
    await fetch('/cc/login/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ method: m }) })
    stop(); timer.current = setInterval(poll, 1500)
  }
  async function finish() {
    if (!code.trim()) return
    await fetch('/cc/login/code', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: code.trim() }) })
    setState(s => ({ ...s, phase: 'code_sent' }))
  }

  const busy = state.phase === 'starting' || state.phase === 'code_sent'
  return (
    <div style={{ padding: '22px 24px', backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '12px', marginBottom: '16px' }}>
      <p style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>connect</p>
      <h2 style={{ fontSize: '20px', color: C.ink, margin: '0 0 8px 0', fontWeight: 600 }}>Give your brain a reasoner</h2>
      <p style={{ color: C.dim, fontSize: '14px', lineHeight: 1.6, margin: '0 0 16px 0' }}>
        This brain thinks with a reasoner that runs on your own server. It needs your own account, once.
        Your credentials stay on your server; this brain never sees your password.
      </p>

      {(state.phase === 'idle' || state.phase === 'error') && (
        <>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '12px' }}>
            <input value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="paste your Anthropic API key (sk-ant-…)" type="password"
                   style={{ flex: '1 1 280px', padding: '10px 12px', borderRadius: '10px', backgroundColor: C.brain, color: C.ink, border: `1px solid ${C.line}`, ...mono, fontSize: '13px', outline: 'none' }} />
            <Btn primary onClick={useKey} disabled={!apiKey.trim()}>Use this key</Btn>
          </div>
          <p style={{ color: C.faint, fontSize: '12px', lineHeight: 1.6, margin: '0 0 12px 0' }}>
            The key is stored on your server only and billed to your own account. Get one at console.anthropic.com.
          </p>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
            {health && health.signin_proxy ? (
              <>
                <Btn onClick={() => start('claudeai')}>Sign in with a Claude subscription</Btn>
                <Btn onClick={() => start('console')}>Sign in with an Anthropic Console account</Btn>
              </>
            ) : (
              <Btn onClick={() => onOpenPane && onOpenPane({ route: '/claude/?arg=login', title: 'Sign in' })}>Sign in with a Claude subscription</Btn>
            )}
          </div>
          {!(health && health.signin_proxy) && (
            <p style={{ color: C.faint, fontSize: '12px', lineHeight: 1.6, margin: '10px 0 0 0' }}>
              A subscription signs in through the provider's own flow, in a panel beside this one: open the link it shows, sign in, paste the code where it asks. Nothing about your account passes through this page; when it says done, close the panel and press reconnect.
            </p>
          )}
          {apiErr && <p style={{ color: '#d08a7a', fontSize: '13px', margin: '10px 0 0 0' }}>{apiErr}</p>}
        </>
      )}

      {state.phase === 'starting' && (
        <p style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '8px 0 0 0' }}>preparing the sign-in link…</p>
      )}

      {(state.phase === 'url' || state.phase === 'code_sent') && state.url && (
        <div style={{ marginTop: '6px' }}>
          <ol style={{ color: C.dim, fontSize: '14px', lineHeight: 1.7, paddingLeft: '20px', margin: '0 0 12px 0' }}>
            <li>Open the sign-in page and log in to your account.
              <div style={{ margin: '8px 0' }}>
                <a href={state.url} target="_blank" rel="noreferrer"
                   style={{ display: 'inline-block', padding: '10px 16px', borderRadius: '10px', backgroundColor: C.gold, color: C.onAccent, fontWeight: 600, textDecoration: 'none', fontSize: '14px' }}>
                  Open the sign-in page
                </a>
              </div>
            </li>
            <li>It shows a code. Paste it here and press Finish.</li>
          </ol>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <input value={code} onChange={e => setCode(e.target.value)} placeholder="paste the code" disabled={state.phase === 'code_sent'}
                   style={{ flex: '1 1 260px', padding: '10px 12px', borderRadius: '10px', backgroundColor: C.brain, color: C.ink, border: `1px solid ${C.line}`, ...mono, fontSize: '13px', outline: 'none' }} />
            <Btn primary onClick={finish} disabled={!code.trim() || state.phase === 'code_sent'}>Finish</Btn>
          </div>
          {state.phase === 'code_sent' && (
            <p style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '10px 0 0 0' }}>checking the sign-in…</p>
          )}
        </div>
      )}

      {state.phase === 'error' && (
        <p style={{ color: '#d08a7a', fontSize: '13px', margin: '12px 0 0 0' }}>
          {state.error || 'The sign-in did not complete.'} Try again, or use the terminal at <a href="/claude/" target="_blank" rel="noreferrer" style={{ color: C.gold }}>/claude/</a>.
        </p>
      )}
      {busy && state.tail && !state.url && (
        <pre style={{ ...mono, color: C.faint, fontSize: '11px', whiteSpace: 'pre-wrap', margin: '12px 0 0 0', maxHeight: '90px', overflow: 'hidden' }}>{state.tail.slice(-300)}</pre>
      )}
      <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '14px 0 0 0' }}>
        {method === 'console' ? 'billed per use to your own Console account' : method === 'claudeai' ? 'uses your own subscription; this is your account on your server' : 'your own key or your own subscription; nothing is ours'}
        {health && health.reasoner ? ` · ${health.reasoner}` : ''}
      </p>
    </div>
  )
}

function CC() {
  const [turns, setTurns] = useState([])       // { who: 'me' | 'brain', text, ms, error }
  const [draft, setDraft] = useState('')
  const [files, setFiles] = useState([])            // attachments chosen for the next message
  // Margin remarks (2026-09-28): select a span in one of the brain's messages, a note opens in the
  // right margin anchored to that message (below it on a narrow screen), typed at leisure, kept
  // per thread in this browser, and sent with the next message as a structured block: which
  // message, the exact span, the remark. Replaces retyping quotes into the composer.
  const [notes, setNotes] = useState([])            // { id, turn, quote, text }
  const [pick, setPick] = useState(null)            // a selection waiting for its "remark" button: { turn, quote, x, y }
  const [room, setRoom] = useState(false)           // is there a margin to the right of the column?
  const notesKeyRef = useRef('cc.notes.new')
  const [jobs, setJobs] = useState([])              // recent jobs on the box (cc-job)
  const [latest, setLatest] = useState([])          // the newest files the brain made, shown above the composer
  const loadLatest = () => fetch('/cc/files/recent', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setLatest((d.recent || []).slice(0, 4)) }).catch(() => {})
  const fileRef = useRef(null)
  const [busy, setBusy] = useState(false)
  // The state line (2026-09-29): "is it working right now?" answered above the composer and in the
  // tab title: a dot, how long the thread shown has been answering, its step count and last step.
  const [busySince, setBusySince] = useState(null)
  const [tick, setTick] = useState(0)
  // The bridge's own answer to "is it working" (2026-10-09): polled every 2.5 s for the thread shown.
  // `busy` alone is what THIS page started or follows; a turn started elsewhere (another tab, a pane,
  // Telegram, a queued message that just began) or a stream a proxy cut left the line saying idle
  // while the bridge refused the next message. The line, the dot and the composer read `active`.
  const [srv, setSrv] = useState(null)                // { running, run:{seconds,steps,agents,last}, queue:[{id,message}] }
  const srvAtRef = useRef(0)
  const pollRef = useRef(null)
  const srvRunning = !!(srv && srv.running)
  const active = busy || srvRunning
  useEffect(() => { if (!active) { setBusySince(null); return } setBusySince(Date.now()); const t = setInterval(() => setTick(x => x + 1), 1000); return () => clearInterval(t) }, [active])
  useEffect(() => { try { document.title = (active ? '● ' : '') + 'CC · BrainFoundry' } catch {} }, [active])
  const fmtElapsed = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s` }
  // The brain speaks (2026-09-23): when the bridge has a voice, answers are read aloud as
  // they finish while this is on. Remembered per browser. One player at a time.
  const [speak, setSpeak] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const audioRef = useRef(null)
  const sayRef = useRef(0)
  const speechQ = useRef({ run: 0, items: [], playing: false })
  const spokenRef = useRef(0)
  const cueRef = useRef(null)   // the "thinking" cue: spoken when voice is on and no words have come after a few seconds (2026-09-29)
  useEffect(() => { try { setSpeak(localStorage.getItem('cc.speak') === '1') } catch {} }, [])
  const setSpeakSaved = (v) => { setSpeak(v); try { localStorage.setItem('cc.speak', v ? '1' : '0') } catch {} }
  const stopSpeaking = () => { sayRef.current++; if (speechQ.current) { speechQ.current.run++; speechQ.current.items = []; speechQ.current.playing = false } const a = audioRef.current; if (a) { try { a.pause() } catch {} audioRef.current = null } setSpeaking(false) }
  // Streamed speech (2026-09-26): while the answer is still arriving, each finished paragraph
  // (or a long enough run of sentences) is sent for speech at once and played in order, so
  // the brain starts talking a second or two after it starts writing, not after it finishes.
  const playUrl2 = (url) => new Promise((resolve) => {
    const a = new Audio(url)
    audioRef.current = a
    a.onended = () => resolve(true)
    a.onerror = () => resolve(false)
    a.play().catch(() => resolve(false))
  })
  const drainSpeech = async (run) => {
    const q = speechQ.current
    q.playing = true; setSpeaking(true)
    while (q.items.length && q.run === run) {
      const it = q.items.shift()
      const url = await it.p
      if (!url || q.run !== run) continue
      await playUrl2(url)
      URL.revokeObjectURL(url)
    }
    q.playing = false
    if (q.run === run) { audioRef.current = null; setSpeaking(false) }
  }
  const enqueueSpeech = (fragment) => {
    const f = (fragment || '').trim()
    if (!f) return
    const q = speechQ.current
    const p = fetch('/cc/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: f, part: 0 }) })
      .then(async r => (r.ok ? URL.createObjectURL(await r.blob()) : null)).catch(() => null)
    q.items.push({ p })
    if (!q.playing) drainSpeech(q.run)
  }
  // Given the text so far, speak what is complete beyond what was already spoken.
  const speakProgress = (full, final) => {
    let from = spokenRef.current
    if (from >= full.length) return
    const rest = full.slice(from)
    let cut = -1
    if (final) cut = rest.length
    else {
      const para = rest.lastIndexOf('\n\n')
      if (para > 40) cut = para
      else if (rest.length > 320) { const m = rest.slice(0, 320).lastIndexOf('. '); if (m > 60) cut = m + 1 }
    }
    if (cut <= 0) return
    // never cut inside a code block or a pane tag
    const piece = rest.slice(0, cut)
    if ((piece.split('```').length - 1) % 2 === 1 || (piece.includes('<pane>') && !piece.includes('</pane>'))) return
    spokenRef.current = from + cut
    enqueueSpeech(piece)
  }
  const say = async (text) => {
    // Speech arrives a part at a time: the first part plays while the next is fetched, so a
    // long answer starts within a couple of seconds instead of after the whole was made.
    if (!text) return
    stopSpeaking()
    const run = ++sayRef.current
    setSpeaking(true)
    const fetchPart = async (i) => {
      const r = await fetch('/cc/speak', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, part: i }) })
      if (!r.ok) return null
      return { n: Number(r.headers.get('X-Speak-Parts') || 1), url: URL.createObjectURL(await r.blob()) }
    }
    const playUrl = (url) => new Promise((resolve) => {
      const a = new Audio(url)
      audioRef.current = a
      a.onended = () => resolve(true)
      a.onerror = () => resolve(false)
      a.play().catch(() => resolve(false))
    })
    try {
      let next = fetchPart(0)
      for (let i = 0; ; i++) {
        const cur = await next
        if (!cur || run !== sayRef.current) break
        if (i + 1 < cur.n) next = fetchPart(i + 1); else next = null
        await playUrl(cur.url)
        URL.revokeObjectURL(cur.url)
        if (!next || run !== sayRef.current) break
      }
    } catch {}
    if (run === sayRef.current) { audioRef.current = null; setSpeaking(false) }
  }
  const chooseVoice = async (name) => {
    const r = await fetch('/cc/voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ voice: name }) })
    const d = await r.json().catch(() => ({}))
    setTurns(t => [...t, { who: 'brain', text: r.ok ? `Voice on: ${d.voice}. Answers are read aloud from now; /voice off to stop.` : (d.error || 'not set'), error: !r.ok }])
    if (r.ok) { setSpeakSaved(true); say(`This is ${d.voice}. I will read your answers in this voice.`) }
    loadHealth()
  }
  const [showTools, setShowTools] = useState(false)
  // The footer is one line by default (2026-09-27: "I don't want to see all these things");
  // thread, tools, memory, hands, posture and the account sit behind "details".
  const [showDetails, setShowDetails] = useState(false)
  // The width of the conversation (2026-09-28): the column was capped at 860px whatever the screen.
  // Three widths, chosen from the footer, kept in this browser; the default stays 860.
  const WIDTHS = ['860px', '1180px', 'none']
  const [width, setWidth] = useState('860px')
  useEffect(() => { try { const w = localStorage.getItem('cc.width'); if (w && WIDTHS.includes(w)) setWidth(w) } catch {} }, [])
  // Layout the owner chose (2026-10-09): hide the title block or the hints, put the side pane left or right.
  // Saved in the browser; "reset layout" in the footer line clears all of it (and the pane width).
  const [hidden, setHidden] = useState({})           // { hero: true, hint: true }
  const [paneSide, setPaneSide] = useState('right')
  useEffect(() => { try { setHidden(JSON.parse(localStorage.getItem('cc.hidden') || '{}') || {}); if (localStorage.getItem('cc.paneSide') === 'left') setPaneSide('left') } catch {} }, [])
  const hide = (k, v) => setHidden(h => { const n = { ...h, [k]: v }; if (!v) delete n[k]; try { localStorage.setItem('cc.hidden', JSON.stringify(n)) } catch {}; return n })
  const flipSide = () => setPaneSide(s => { const n = s === 'left' ? 'right' : 'left'; try { localStorage.setItem('cc.paneSide', n) } catch {}; return n })
  const resetLayout = () => { setHidden({}); setPaneSide('right'); setWidth('860px'); try { ['cc.hidden', 'cc.paneSide', 'cc.paneW', 'cc.width', 'cc.panes.layout'].forEach(k => localStorage.removeItem(k)) } catch {}; if (pane) { const p = pane; setPane(null); setTimeout(() => setPane(p), 0) } }
  const layoutChanged = Object.keys(hidden).length > 0 || paneSide === 'left'
  const cycleWidth = () => { const w = WIDTHS[(WIDTHS.indexOf(width) + 1) % WIDTHS.length]; setWidth(w); try { localStorage.setItem('cc.width', w) } catch {} }
  // The font of the conversation (2026-09-30): the Chat tab's six fonts, offered under "details";
  // each row of the picker is drawn in its own font, so the choice is seen before it is made.
  // Kept in this browser under cc.font; the default stays the theme's display font.
  const FONTS = [
    { value: 'system', label: 'System sans', family: 'system-ui, -apple-system, sans-serif' },
    { value: 'inter', label: 'Inter', family: '"Inter", system-ui, sans-serif' },
    { value: 'lora', label: 'Lora', family: 'Lora, Georgia, serif' },
    { value: 'crimson', label: 'Crimson Pro', family: '"Crimson Pro", Georgia, serif' },
    { value: 'dm-mono', label: 'DM Mono', family: '"DM Mono", ui-monospace, monospace' },
    { value: 'jetbrains', label: 'JetBrains Mono', family: '"JetBrains Mono", ui-monospace, monospace' },
  ]
  const [font, setFont] = useState('')
  const [showFonts, setShowFonts] = useState(false)
  useEffect(() => { try { const f = localStorage.getItem('cc.font'); if (f && FONTS.some(x => x.value === f)) setFont(f) } catch {} }, [])
  const setFontSaved = (v) => { setFont(v); setShowFonts(false); try { if (v) localStorage.setItem('cc.font', v); else localStorage.removeItem('cc.font') } catch {} }
  const fontPick = FONTS.find(x => x.value === font)
  const fontFamily = fontPick ? fontPick.family : 'var(--font-display, serif)'
  // The technical surface's warnings, one line in the footer (2026-09-24): the api's view
  // (disk, memory, load, containers, backups) and the host's (failed services, units).
  const [sysWarn, setSysWarn] = useState([])
  useEffect(() => {
    let on = true
    const load = async () => {
      const out = []
      try { const r = await fetch('/api/bf/admin/system'); if (r.ok) { const d = await r.json(); out.push(...(d.warnings || [])) } } catch {}
      try { const r = await fetch('/cc/system'); if (r.ok) { const d = await r.json(); out.push(...(d.warnings || [])) } } catch {}
      if (on) setSysWarn(out)
    }
    load(); const t = setInterval(load, 300000)
    return () => { on = false; clearInterval(t) }
  }, [])
  const queueRef = useRef([])                      // messages typed while a NEW thread's first turn runs (it has no id to queue on yet): [{ qid, text }]
  const sendRef = useRef(null)
  const [health, setHealth] = useState(null)   // null unknown, false down, object ok
  const [usage, setUsage] = useState(null)        // today's totals for the footer (2026-09-29; declared 2026-10-01, the footer read it undeclared and crashed under details)
  const [pending, setPending] = useState([])    // permits proposed earlier, still waiting (survive reload)
  const [auto, setAuto] = useState([])          // actions the owner allowed to run without a card
  const [showAuto, setShowAuto] = useState(false)
  const [pane, setPane] = useState(null)         // a summoned surface beside the conversation (D54)
  const [firstRun, setFirstRun] = useState(null) // first-use steps from the api, until complete
  const [threads, setThreads] = useState([])       // CC threads the brain remembers
  const [showThreads, setShowThreads] = useState(false)
  // The shape of threads (2026-09-30): pinned on top, then day groups; rename, pin, archive on
  // each row; archived ones hidden until "show". `renaming` is the brain id whose title is an
  // input right now ('header' for the line under the page title).
  const [archivedCount, setArchivedCount] = useState(0)
  const [showArchived, setShowArchived] = useState(false)
  const showArchivedRef = useRef(false)
  const [renaming, setRenaming] = useState(null)
  const [renameVal, setRenameVal] = useState('')
  const endRef = useRef(null)
  const boxRef = useRef(null)
  const freshRef = useRef(false)   // the next message must start a new thread, whatever happened to /cc/new
  // Several conversations at once (2026-09-28). `cur` is the thread this page shows (a brain
  // session id, or a temporary key while a new thread's first turn runs). A stream updates the
  // page only while its thread is the one shown; switching away detaches it, switching back
  // attaches through /cc/live, which replays the whole turn so far. `running` is what this
  // browser knows to be answering, by thread key.
  const [cur, setCur] = useState(null)
  const curRef = useRef(null)
  // Side by side (2026-10-06): /panes tiles this page in iframes, each opened as
  // /cc?pane=<n>&thread=<brain id | new>. A pane holds its own thread: it never moves the
  // box's current thread (no /cc/threads/switch, no /cc/new), so panes do not pull each other.
  const paneModeRef = useRef(null)
  const [paneMode, setPaneMode] = useState(null)
  // Reading space in a pane (2026-10-06): the stream is the pane. The pane's title bar on /panes
  // carries the title, the state and the one menu; this page tells it its state and takes its
  // commands (export, details). The rows of links under the composer open only with "details".
  const [paneDetails, setPaneDetails] = useState(false)
  const exportRef = useRef(null)
  const runningRef = useRef({})
  const runIdRef = useRef({})     // thread key -> run id from the stream's 'begin', to re-follow a broken stream
  const showThread = (key) => {
    curRef.current = key; setCur(key); setBusy(!!runningRef.current[key])
    // a pane on /panes tells its host which thread it shows, so the layout survives a reload
    if (paneModeRef.current && key && !String(key).startsWith('new:')) { try { window.parent.postMessage({ type: 'cc-pane-thread', pane: paneModeRef.current, thread: key }, window.location.origin) } catch {} }
  }
  // notes follow the thread shown
  useEffect(() => {
    notesKeyRef.current = `cc.notes.${cur && !String(cur).startsWith('new:') ? cur : 'new'}`
    try { const raw = localStorage.getItem(notesKeyRef.current); setNotes(raw ? JSON.parse(raw) : []) } catch { setNotes([]) }
  }, [cur])
  useEffect(() => { try { if (notes.length) localStorage.setItem(notesKeyRef.current, JSON.stringify(notes)); else localStorage.removeItem(notesKeyRef.current) } catch {} }, [notes])
  useEffect(() => {
    const measure = () => { try { const w = convRef.current ? convRef.current.getBoundingClientRect().right : 0; setRoom(window.innerWidth - w >= 300) } catch { setRoom(false) } }
    measure(); window.addEventListener('resize', measure); const t = setInterval(measure, 2000)
    return () => { window.removeEventListener('resize', measure); clearInterval(t) }
  }, [])
  function onPick() {
    // a mouse-up inside the conversation: a non-empty selection inside one of the brain's messages offers a remark
    try {
      const sel = window.getSelection(); const q = sel ? sel.toString().replace(/\s+/g, ' ').trim() : ''
      if (!q || !sel.rangeCount) { setPick(null); return }
      let node = sel.anchorNode; if (node && node.nodeType === 3) node = node.parentElement
      const host = node && node.closest ? node.closest('[data-turn]') : null
      if (!host || !convRef.current) { setPick(null); return }
      const i = parseInt(host.getAttribute('data-turn'), 10)
      if (!(turns[i] && turns[i].who === 'brain')) { setPick(null); return }
      const r = sel.getRangeAt(0).getBoundingClientRect(); const c = convRef.current.getBoundingClientRect()
      setPick({ turn: i, quote: q.slice(0, 400), raw: sel.toString(), x: Math.max(8, r.left - c.left), y: Math.max(0, r.top - c.top + convRef.current.scrollTop - 30) })
    } catch { setPick(null) }
  }
  function addNote() {
    if (!pick) return
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    setNotes(n => [...n, { id, turn: pick.turn, quote: pick.quote, text: '' }])
    setPick(null); try { window.getSelection().removeAllRanges() } catch {}
    setTimeout(() => { const el = document.getElementById(`note-${id}`); if (el) el.focus() }, 30)
  }
  const setNote = (id, text) => setNotes(n => n.map(x => (x.id === id ? { ...x, text } : x)))
  const dropNote = (id) => setNotes(n => n.filter(x => x.id !== id))
  // the block the reasoner receives: which message, the exact span, the remark
  function notesBlock() {
    const live = notes.filter(n => n.text.trim())
    if (!live.length) return ''
    const lines = live.map((n, k) => {
      const t = turns[n.turn]; const head = t ? (t.text || '').replace(/\s+/g, ' ').trim().slice(0, 60) : ''
      return `${k + 1}. your message #${n.turn + 1}${head ? ` ("${head}${head.length >= 60 ? '…' : ''}")` : ''}, the span I marked: "${n.quote}"\n   my remark: ${n.text.trim()}`
    })
    return `[remarks in the margin, each on a span I selected in one of your earlier messages]\n${lines.join('\n')}`
  }
  const noteCard = (n) => (
      <div key={n.id} style={{ width: room ? '250px' : '100%', border: `1px solid ${C.gold}55`, borderLeft: `3px solid ${C.gold}`, borderRadius: '8px', backgroundColor: C.card, padding: '8px 10px', boxSizing: 'border-box' }}>
        <p style={{ margin: '0 0 6px 0', fontSize: '12px', color: C.dim, fontStyle: 'italic', lineHeight: 1.4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>“{n.quote}”</p>
        <textarea id={`note-${n.id}`} value={n.text} onChange={e => setNote(n.id, e.target.value)} rows={2} placeholder="your remark on this span"
          onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); boxRef.current && boxRef.current.focus() } }}
          style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', fontSize: '13px', lineHeight: 1.5, color: C.ink, backgroundColor: 'transparent', border: `1px solid ${C.line}`, borderRadius: '6px', padding: '6px 8px', outline: 'none', fontFamily: 'inherit' }} />
        <a onClick={() => dropNote(n.id)} style={{ ...mono, fontSize: '10px', color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>remove</a>
      </div>
  )
  const flushLocal = () => { const next = queueRef.current.shift(); if (!next) return; setTurns(t => t.filter(x => x.qid !== next.qid)); setTimeout(() => sendRef.current && sendRef.current(next.text), 0) }
  const markRunning = (key, on) => { if (on) runningRef.current[key] = true; else delete runningRef.current[key]; if (curRef.current === key) setBusy(!!on) }

  // Poll the bridge for the thread shown. If it is answering and this page is not following, follow
  // it (replays the turn so far). Queued messages are the bridge's, shown from here.
  useEffect(() => {
    let stop = false
    const tick = async () => {
      const k = curRef.current
      if (!k || String(k).startsWith('new:')) { if (!stop) setSrv(null); return }
      try {
        const r = await fetch(`/cc/state?thread=${encodeURIComponent(k)}`, { cache: 'no-store' })
        const d = r.ok ? await r.json() : null
        if (stop || !d || curRef.current !== k) return
        srvAtRef.current = Date.now(); setSrv(d)
        if (d.running && !runningRef.current[k]) attach(k)
      } catch {}
    }
    pollRef.current = tick
    setSrv(null)
    tick()
    const iv = setInterval(tick, 2500)
    return () => { stop = true; clearInterval(iv) }
  }, [cur])

  // A card that waited unanswered for 15 minutes on 2026-09-27 because the owner had left the
  // page: the footer now says so within 20 s and the browser shows a notification once per card.
  const cardsSeenRef = useRef(0)
  useEffect(() => {
    loadUsage()
    const t = setInterval(() => { loadHealth(); loadThreads(); loadUsage() }, 20000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    const n = (health && health.cards_waiting) || 0
    // side by side: the panes stay quiet, /panes notifies once for all of them
    if (n > cardsSeenRef.current && !paneModeRef.current) {
      try {
        if (typeof Notification !== 'undefined') {
          if (Notification.permission === 'granted') new Notification('Your brain needs a yes', { body: n === 1 ? 'A card waits for you.' : `${n} cards wait for you.` })
          else if (Notification.permission !== 'denied') Notification.requestPermission()
        }
      } catch {}
    }
    cardsSeenRef.current = n
  }, [health && health.cards_waiting])
  const loadUsage = () => fetch('/cc/usage', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setUsage(d) }).catch(() => {})
  const loadHealth = () =>
    fetch('/cc/health', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setHealth)
      .catch(() => setHealth(false))
  const loadPending = () =>
    fetch('/cc/permits', { cache: 'no-store' }).then(r => r.ok ? r.json() : { pending: [] }).then(d => { setPending(d.pending || []); setAuto(d.auto || []) }).catch(() => {})
  const loadFirstRun = () =>
    fetch('/api/bf/onboarding/first-use', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => setFirstRun(d && Array.isArray(d.steps) ? d : null)).catch(() => {})
  // History: the current thread's turns come from the brain's own record, so a reload
  // shows the conversation instead of an empty screen.
  const loadHistory = (brainId) => {
    if (!brainId) return
    fetch(`/api/bf/sessions/${encodeURIComponent(brainId)}/messages`, { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!d || !Array.isArray(d.messages)) return
        // a hand-back is recorded as a bracketed line ("[agent report received: ...]"); it shows as a small line again
        setTurns(d.messages.map(m => (m.role !== 'user' && /^\[agent report received[^\]]*\]$/.test((m.content || '').trim())
          ? { who: 'note', text: m.content.trim().slice(1, -1) }
          : { who: m.role === 'user' ? 'me' : 'brain', text: m.content })))
      })
      .catch(() => {})
  }
  const loadThreads = () =>
    fetch('/cc/threads' + (showArchivedRef.current ? '?archived=1' : ''), { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) { setThreads(d.threads || []); setArchivedCount(d.archived_count || 0) } }).catch(() => {})
  const toggleArchived = () => { showArchivedRef.current = !showArchivedRef.current; setShowArchived(showArchivedRef.current); loadThreads() }
  // rename, pin, unpin, archive, unarchive: one call, then the list is read again (2026-09-30)
  async function updateThread(brain, patch) {
    try {
      await fetch('/cc/threads/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brain, ...patch }) })
    } catch {}
    loadThreads()
  }
  const startRename = (key, current) => { setRenaming(key); setRenameVal(current || '') }
  const finishRename = (brain) => { const t = renameVal.trim(); setRenaming(null); if (t) updateThread(brain, { title: t }) }
  const curThread = threads.find(t => t.brain === cur) || null
  // day groups for the dropdown: pinned first, then today, yesterday, then the date
  const dayLabel = (ts) => {
    if (!ts) return 'earlier'
    const d = new Date(ts); if (isNaN(d)) return 'earlier'
    const k = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
    const now = new Date(); const y = new Date(now); y.setDate(now.getDate() - 1)
    const key = k(d)
    return key === k(now) ? 'today' : key === k(y) ? 'yesterday' : key
  }
  const clock = (ts) => { try { const d = new Date(ts); return isNaN(d) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' } }
  const threadGroups = (() => {
    const groups = []; const at = {}
    for (const th of threads) {
      const label = th.pinned ? 'pinned' : dayLabel(th.last || th.started)
      if (!(label in at)) { at[label] = groups.length; groups.push({ label, items: [] }) }
      groups[at[label]].items.push(th)
    }
    return groups
  })()
  useEffect(() => {
    let pin = null
    try {
      const q = new URLSearchParams(window.location.search)
      if (q.get('pane')) { paneModeRef.current = q.get('pane'); setPaneMode(q.get('pane')) }
      pin = q.get('thread')
    } catch {}
    fetch('/cc/health', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(h => {
        setHealth(h)
        if (pin === 'new') { freshRef.current = true }
        else if (pin) {
          showThread(pin); loadHistory(pin)
          if ((h.runs || []).some(r => r.thread === pin)) attach(pin)
        } else if (h && h.brain_session_id) {
          showThread(h.brain_session_id); loadHistory(h.brain_session_id)
          // the box's current thread may be answering already (another tab, the phone): follow it
          if ((h.runs || []).some(r => r.thread === h.brain_session_id)) attach(h.brain_session_id)
        }
      })
      .catch(() => setHealth(false))
    loadPending(); loadFirstRun(); loadThreads(); loadLatest()
    try { const q = new URLSearchParams(window.location.search).get('ask'); if (q) setDraft(q) } catch {}
  }, [])
  const openPane = (p) => { if (!p) return; if (typeof p === 'string') p = { route: p, title: p.replace(/^\//, '').split('?')[0] || 'pane' }; if (p.route) setPane(p) }

  // Jobs that outlive a turn: poll while any runs; a finished one lands as a small card.
  useEffect(() => {
    let stop = false
    const tick = async () => {
      try {
        const r = await fetch('/cc/jobs?take=1', { cache: 'no-store' })
        const d = r.ok ? await r.json() : null
        if (!d || stop) return
        setJobs(d.jobs || [])
        for (const j of (d.finished || [])) {
          setTurns(t => [...t, { who: 'brain', job: j, text: '' }])
        }
      } catch {}
    }
    tick()
    const iv = setInterval(tick, 15000)
    return () => { stop = true; clearInterval(iv) }
  }, [])

  // A pane may hand a question to the conversation (the graph's "ask the brain about this").
  useEffect(() => {
    const onPath = (e) => { if (e.detail) openPane({ route: '/files?path=' + encodeURIComponent(e.detail), title: 'Files' }) }
    window.addEventListener('cc-open-path', onPath)
    const onMsg = (e) => {
      if (e.origin !== window.location.origin) return
      if (e.data && e.data.type === 'cc-ask' && typeof e.data.text === 'string') {
        setDraft(e.data.text)
        if (boxRef.current) boxRef.current.focus()
      }
      if (e.data && e.data.type === 'cc-send' && typeof e.data.text === 'string' && sendRef.current) {
        sendRef.current(e.data.text)
      }
      // the pane's own menu on /panes (2026-10-06)
      if (e.data && e.data.type === 'cc-pane-cmd') {
        if (e.data.cmd === 'export' && exportRef.current) exportRef.current()
        if (e.data.cmd === 'details') { setShowDetails(true); setPaneDetails(v => !v) }
        if (e.data.cmd === 'focus' && boxRef.current) boxRef.current.focus()
      }
    }
    window.addEventListener('message', onMsg)
    // voice and hands-free are chosen once on /panes; the other panes hear the change
    const onStore = (e) => {
      if (e.key === 'cc.speak') setSpeak(e.newValue === '1')
      if (e.key === 'cc.handsfree') setHandsfree(e.newValue === '1')
    }
    window.addEventListener('storage', onStore)
    return () => { window.removeEventListener('message', onMsg); window.removeEventListener('cc-open-path', onPath); window.removeEventListener('storage', onStore) }
  }, [])

  // the whole conversation as markdown: copied, and downloaded as a file (the header's button, or the pane's menu)
  function exportThread() {
    const md = turns.filter(x => x.text).map(x => (x.who === 'note' ? `_${x.text}_` : `**${x.who === 'me' ? 'me' : 'brain'}**\n\n${x.text}`)).join('\n\n---\n\n')
    if (!md) return
    copyText(md)
    try { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' })); a.download = `cc-thread-${new Date().toISOString().slice(0, 10)}.md`; a.click() } catch {}
  }
  exportRef.current = exportThread

  async function switchThread(th) {
    // Allowed while another thread answers: that stream keeps running on the box and detaches
    // from this page; this thread's own turn, if one is in flight, is followed through /cc/live.
    if (th.brain === curRef.current) { setShowThreads(false); return }
    setTurns([]); setPane(null); showThread(th.brain); loadHistory(th.brain)
    if (!paneModeRef.current) {
      try {
        await fetch('/cc/threads/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brain: th.brain }) })
      } catch {}
    }
    if (th.running || runningRef.current[th.brain]) attach(th.brain)
    loadHealth()
    setShowThreads(false)
  }

  // Read one server-sent stream (a turn just sent, or one followed through /cc/live) into the
  // live bubble, while `key` is the thread shown. Returns the "done" payload, or null.
  async function consume(r, key, withBegin) {
    const mine = () => curRef.current === key
    // the live bubble is the LAST LIVE turn, not the last turn: a message queued behind it sits below it (a reply was lost to that on 2026-09-28)
    const liveIdx = c => { for (let i = c.length - 1; i >= 0; i--) if (c[i].live) return i; return -1 }
    const upd = f => { if (!mine()) return; setTurns(t => { const c = t.slice(); const i = liveIdx(c); if (i >= 0) c[i] = f(c[i]); return c }) }
    // Every assistant text block of a run is its own bubble, kept in order, never replaced by a later
    // one (2026-10-09: a long report vanished when a subagent handed back and the run's LAST text
    // became the whole reply). `runId` tags the run's bubbles so a replay (re-attach, the poll, a
    // broken stream followed through /cc/live) swaps them for the same ones instead of doubling them.
    let runId = null
    let curText = ''   // the text of the block being written, for the voice
    const newLive = model => ({ who: 'brain', text: '', live: true, steps: [], run: runId, model })
    if (!withBegin && mine()) setTurns(t => [...t, newLive()])
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = ''; let data = null
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2)
        const ev = (chunk.match(/^event: (.*)$/m) || [])[1]; const dl = (chunk.match(/^data: (.*)$/m) || [])[1]
        if (!ev || !dl) continue
        let pl = {}; try { pl = JSON.parse(dl) } catch { continue }
        if (ev === 'begin') {
          if (pl.run) { runIdRef.current[key] = pl.run; runId = pl.run }
          if (withBegin && mine()) setTurns(t => {
            const mineOfRun = x => x.live || (runId && x.run === runId)
            const at = t.findIndex(mineOfRun)
            const rest = t.filter(x => !mineOfRun(x))
            const pos = at >= 0 ? at : rest.length
            const before = pos > 0 ? rest[pos - 1] : null
            const lastMe = before && before.who === 'me' && before.text === (pl.message || '')
            return [...rest.slice(0, pos), ...(lastMe ? [] : [{ who: 'me', text: pl.message || '' }]), newLive(), ...rest.slice(pos)]
          })
          else if (mine()) upd(x => ({ ...x, run: runId }))
        }
        else if (ev === 'start') {
          if (mine()) {
            spokenRef.current = 0; stopSpeaking()
            clearTimeout(cueRef.current)
            if (speak && health && health.voice) cueRef.current = setTimeout(() => { if (mine() && spokenRef.current === 0) enqueueSpeech('Thinking.') }, 3000)
          }
          upd(x => ({ ...x, model: pl.model }))
        }
        else if (ev === 'text') {
          clearTimeout(cueRef.current)
          curText += (pl.t || '')
          if (speak && health && health.voice && mine()) speakProgress(curText, false)
          upd(x => ({ ...x, text: x.text + (pl.t || '') }))
        }
        else if (ev === 'block') {
          // a new assistant text block: the one written so far stays as it is, the next gets its own bubble
          if (speak && health && health.voice && curText && mine()) speakProgress(curText, true)
          curText = ''; if (mine()) spokenRef.current = 0
          if (mine()) setTurns(t => {
            const c = t.slice(); const i = liveIdx(c)
            if (i < 0 || !c[i].text) return c
            c[i] = { ...c[i], live: false }
            c.splice(i + 1, 0, newLive(c[i].model))
            return c
          })
        }
        else if (ev === 'note') {
          // a hand-back (a background subagent reported in): a small labelled line, not the person's message
          if (mine()) setTurns(t => {
            const c = t.slice(); const i = liveIdx(c)
            const note = { who: 'note', text: pl.label || 'agent report received', run: runId }
            if (i < 0) { c.push(note); return c }
            if (c[i].text) { c[i] = { ...c[i], live: false }; c.splice(i + 1, 0, note, newLive(c[i].model)) }
            else c.splice(i, 0, note)
            return c
          })
          curText = ''; if (mine()) spokenRef.current = 0
        }
        else if (ev === 'tool') upd(x => ({ ...x, steps: [...x.steps, pl.brief || pl.name] }))
        else if (ev === 'ask') upd(x => ({ ...x, asks: [...(x.asks || []), pl] }))
        else if (ev === 'done') data = pl
      }
    }
    if (!data && !withBegin) {
      // the stream broke before "done" (a proxy closed it during a long silent tool run): the turn
      // goes on in the bridge; follow it through /cc/live, which replays and finishes it
      try {
        const r2 = await fetch(`/cc/live?${key.startsWith('new:') ? 'run=' + encodeURIComponent(runIdRef.current[key] || '') : 'thread=' + encodeURIComponent(key)}`, { cache: 'no-store' })
        if (r2.ok && r2.body) return await consume(r2, key, true)
      } catch {}
    }
    if (!data) {
      // the stream broke but the bridge may still be answering: say nothing, the poll re-attaches and replays it
      try { const rs = await fetch(`/cc/state?thread=${encodeURIComponent(key)}`, { cache: 'no-store' }); const ds = rs.ok ? await rs.json() : null; if (ds && ds.running) return null } catch {}
      data = { reply: 'The stream ended without an answer.', error: true }
    }
    const reply = data.reply || '(no answer)'
    if (mine()) {
      setTurns(t => {
        const c = t.slice(); const i = liveIdx(c); if (i < 0) return c
        const cur = c[i]
        const fin = { live: false, ms: data.ms, error: !!data.error, proposal: data.proposal || null, meta: data.meta || null, sources: data.sources || [] }
        // The reply is the run's LAST text. Earlier blocks stay as streamed; only the last bubble is
        // settled to the reply (it has the proposal and pane markers cut out). A stopped turn adds its note.
        if (!cur.text && !data.error && !data.stopped) {
          // the run ended with nothing written after the last hand-back: the reply is already the bubble above
          let k = i - 1
          while (k >= 0 && !(c[k].who === 'brain' && c[k].run && c[k].run === cur.run)) k--
          if (k >= 0) {
            c[k] = { ...c[k], ...fin, steps: [...(c[k].steps || []), ...(cur.steps || [])], asks: [...(c[k].asks || []), ...(cur.asks || [])] }
            c.splice(i, 1)
            return c
          }
        }
        const text = data.stopped && cur.text ? (cur.text + '\n\n(stopped by you)').trim() : reply
        c[i] = { ...cur, ...fin, text }
        return c
      })
      if (speak && health && health.voice && !data.error) { if (spokenRef.current > 0) speakProgress(reply, true); else say(reply) }
      spokenRef.current = 0
      if (data.pane) openPane(data.pane)
    }
    return data
  }

  // Follow a turn already in flight for `thread`: the bridge replays what happened, then streams.
  async function attach(thread) {
    if (runningRef.current[thread] === 'attached') return
    runningRef.current[thread] = 'attached'; if (curRef.current === thread) setBusy(true)
    try {
      const r = await fetch(`/cc/live?thread=${encodeURIComponent(thread)}`, { cache: 'no-store' })
      if (r.ok && r.body) await consume(r, thread, true)
      else if (r.status === 404 && curRef.current === thread) loadHistory(thread)
    } catch {}
    markRunning(thread, false)
    loadThreads(); loadLatest()
    if (curRef.current === thread && queueRef.current.length) flushLocal()
    setTimeout(() => pollRef.current && pollRef.current(), 400)
  }

  // The write gate: a proposal card's Send approves the permit and executes that one
  // action through One; Cancel denies it. Either way the audit log gets a line.
  function markCard(id, patch) {
    setTurns(t => t.map(x => {
      let y = x
      if (x.proposal && x.proposal.id === id) y = { ...y, proposal: { ...x.proposal, ...patch } }
      if (x.asks && x.asks.some(a => a.id === id)) y = { ...y, asks: x.asks.map(a => (a.id === id ? { ...a, ...patch } : a)) }
      return y
    }))
  }

  async function decide(id, action, remember) {
    const isBox = turns.some(x => (x.asks || []).some(a => a.id === id && a.platform === 'box')) || pending.some(p => p.id === id && p.platform === 'box')
    markCard(id, { busy: true })
    let data = {}
    try {
      const r = await fetch(`/cc/permits/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, remember: !!remember }) })
      data = await r.json().catch(() => ({}))
    } catch (e) { data = { ok: false, error: 'the bridge did not answer' } }
    setPending(p => p.filter(x => x.id !== id))
    if (remember && data.ok) loadPending()
    markCard(id, { busy: false, decided: action })
    if (isBox) return   // the reasoner continues in the same live answer; nothing more to say here
    if (action === 'approve') {
      const text = data.ok
        ? `Done: ${data.summary || 'the action ran'}.` + (data.result && data.result.status ? ` One answered ${data.result.status}.` : '')
        : `Not done. ${(data.result && data.result.error) || data.error || 'the write failed'}`
      setTurns(t => [...t, { who: 'brain', text, error: !data.ok }])
    } else {
      setTurns(t => [...t, { who: 'brain', text: 'Cancelled. Nothing was sent.' }])
    }
  }

  // Scrolling (2026-09-26, the operator's complaint: "I have to scroll up"). The conversation is
  // its own scroll area under a fixed composer. A message of yours scrolls to the end; the brain's
  // answer scrolls so that its top is in view and stays there while it streams; you read down.
  const convRef = useRef(null)
  const lastCountRef = useRef(0)
  useEffect(() => {
    const el = convRef.current
    if (!el) return
    const n = turns.length
    if (n === lastCountRef.current) return
    const before = lastCountRef.current
    lastCountRef.current = n
    const last = turns[n - 1]
    if (!last) return
    if (paneModeRef.current && before === 0 && n > 1) {
      // a pane opening on an existing conversation shows its latest exchange, at once (2026-10-06)
      const bottom = () => { el.scrollTop = el.scrollHeight }
      bottom(); requestAnimationFrame(bottom); setTimeout(bottom, 120)
      return
    }
    if (last.who === 'brain') {
      const nodes = el.querySelectorAll('[data-turn]')
      const node = nodes[nodes.length - 1]
      if (node) el.scrollTo({ top: node.offsetTop - el.offsetTop - 8, behavior: 'smooth' })
    } else if (endRef.current) {
      endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [turns])

  const loggedIn = !!(health && health.auth && health.auth.loggedIn)
  // A pane tells the page that holds it what it is doing, for the one-line title bar (2026-10-06).
  useEffect(() => {
    if (!paneMode) return
    const live = [...turns].reverse().find(x => x.live)
    const lastDone = [...turns].reverse().find(x => x.who === 'brain' && !x.live && x.ms)
    const waiting = pending.length > 0 || turns.some(x => (x.asks || []).some(a => !a.decided && !a.auto))
    try {
      window.parent.postMessage({ type: 'cc-pane-state', busy: active, since: busySince, steps: live && live.steps ? live.steps.length : 0,
        last: live && live.steps && live.steps.length ? String(live.steps[live.steps.length - 1]).slice(0, 120) : '', writing: !!(live && live.text),
        waiting, lastMs: lastDone ? lastDone.ms : null, details: paneDetails, turns: turns.length }, window.location.origin)
    } catch {}
  }, [paneMode, active, busySince, turns, pending, paneDetails])
  // In a pane the composer is one line that grows with what is typed, up to six.
  useEffect(() => {
    if (!paneMode || !boxRef.current) return
    const el = boxRef.current
    el.style.height = 'auto'
    el.style.height = Math.min(132, Math.max(34, el.scrollHeight)) + 'px'
  }, [draft, paneMode])

  // Talking to the brain (2026-09-27): the owner speaks and the composer fills as the words
  // come. Chrome and Safari on iOS recognise speech in the browser and nothing leaves the
  // phone; a browser without that (Firefox) records a clip and the bridge transcribes it
  // (POST /cc/transcribe). Hands-free: a final result sends by itself and, once the answer has
  // finished speaking, listening restarts, so a conversation needs no touch. Listening never
  // starts while the brain is speaking; it would hear itself.
  const [srOk, setSrOk] = useState(false)       // the browser has SpeechRecognition
  const [recOk, setRecOk] = useState(false)     // the browser can record a clip (MediaRecorder)
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [talkNote, setTalkNote] = useState('')
  // The microphone meter (2026-09-29): Safari on the Mac hands words over only at the end, and a
  // recorded clip shows nothing until it is transcribed, so a level bar and a timer show that the
  // page is hearing you while you speak. Its own capture, closed when listening ends.
  const [mic, setMic] = useState({ level: 0, since: 0, tick: 0 })
  const meterRef = useRef(null)
  const startMeter = async () => {
    if (meterRef.current) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const an = ctx.createAnalyser(); an.fftSize = 512; ctx.createMediaStreamSource(stream).connect(an)
      const buf = new Uint8Array(an.fftSize); const since = Date.now()
      const timer = setInterval(() => {
        an.getByteTimeDomainData(buf)
        let sum = 0; for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v }
        setMic({ level: Math.min(1, Math.sqrt(sum / buf.length) * 6), since, tick: Date.now() })
      }, 120)
      meterRef.current = { stream, ctx, timer }
    } catch { meterRef.current = null }
  }
  const stopMeter = () => {
    const m = meterRef.current; meterRef.current = null
    if (!m) return
    try { clearInterval(m.timer) } catch {}
    try { m.stream.getTracks().forEach(t => t.stop()) } catch {}
    try { m.ctx.close() } catch {}
    setMic({ level: 0, since: 0, tick: 0 })
  }
  useEffect(() => { if (listening) startMeter(); else stopMeter(); return () => {} }, [listening])   // eslint-disable-line react-hooks/exhaustive-deps
  const [handsfree, setHandsfree] = useState(false)
  const recRef = useRef(null)                   // the SpeechRecognition run while listening
  const mediaRef = useRef(null)                 // the MediaRecorder run while recording
  const pauseRef = useRef(null)                 // the 1.5 s pause timer after a final result
  const talkRef = useRef({ base: '', finals: '', cancel: false, err: '' })
  const armedRef = useRef(false)                // hands-free: listen again once the answer is done
  const listeningRef = useRef(false)
  const handsfreeRef = useRef(false); handsfreeRef.current = handsfree
  const speakingRef = useRef(false); speakingRef.current = speaking
  useEffect(() => {
    try { setSrOk(!!(window.SpeechRecognition || window.webkitSpeechRecognition)) } catch {}
    try { setRecOk(!!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)) } catch {}
    try { setHandsfree(localStorage.getItem('cc.handsfree') === '1') } catch {}
  }, [])
  const canTalk = srOk || (recOk && !!(health && health.voice))
  const whyNoTalk = srOk ? '' : !recOk ? 'this browser cannot listen: no speech recognition and no microphone recording'
    : !(health && health.voice) ? 'this browser has no speech recognition; with ELEVENLABS_API_KEY in the bridge env the brain would transcribe a recording' : ''
  const setHandsfreeSaved = (v) => {
    setHandsfree(v); handsfreeRef.current = v
    try { localStorage.setItem('cc.handsfree', v ? '1' : '0') } catch {}
    if (v) armedRef.current = true
    else { armedRef.current = false; if (listeningRef.current) stopListening(true) }
  }
  const clearPause = () => { if (pauseRef.current) { clearTimeout(pauseRef.current); pauseRef.current = null } }
  // A run ended with `text`: it stays in the composer, or hands-free sends it at once.
  const finishTalk = (text) => {
    const st = talkRef.current
    if (st.cancel) { st.cancel = false; return }
    const t = (text || '').trim()
    setDraft(t)
    if (!handsfreeRef.current) return
    const bad = st.err === 'not-allowed' || st.err === 'service-not-allowed' || st.err === 'audio-capture'
    if (t) { setDraft(''); armedRef.current = true; sendRef.current && sendRef.current(t) }
    else if (!bad) armedRef.current = true   // silence: keep waiting for the owner
  }
  const stopRecording = () => { const m = mediaRef.current; if (!m) return; try { m.recorder.stop() } catch {} }
  const stopListening = (cancel) => {
    talkRef.current.cancel = !!cancel
    clearPause()
    if (recRef.current) { try { cancel ? recRef.current.abort() : recRef.current.stop() } catch {} return }
    if (mediaRef.current) stopRecording()
  }
  const startRecording = async (base) => {
    // No recogniser in this browser: record until a pause (or 60 s), then the bridge transcribes.
    if (!recOk || !(health && health.voice)) { setTalkNote(whyNoTalk || 'this browser cannot listen'); return }
    if (speakingRef.current) stopSpeaking()
    let stream
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) } catch { setTalkNote('the microphone is not allowed for this page'); return }
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => { try { return MediaRecorder.isTypeSupported(t) } catch { return false } })
    let recorder
    try { recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream) } catch { stream.getTracks().forEach(t => t.stop()); setTalkNote('could not start recording'); return }
    const chunks = []
    const st = talkRef.current; st.base = base || ''; st.cancel = false; st.err = ''
    const m = { recorder, stream, ctx: null, timer: null, cap: null, heard: false, quiet: 0 }
    try {
      // a pause of about 1.5 s after speech ends the clip, as the recogniser does
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an)
      const buf = new Uint8Array(an.fftSize)
      m.ctx = ctx
      m.timer = setInterval(() => {
        an.getByteTimeDomainData(buf)
        let sum = 0; for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v }
        if (Math.sqrt(sum / buf.length) > 0.02) { m.heard = true; m.quiet = 0 }
        else if (m.heard) { m.quiet += 200; if (m.quiet >= 1500) stopRecording() }
      }, 200)
    } catch {}
    m.cap = setTimeout(stopRecording, 60000)
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data) }
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      if (m.timer) clearInterval(m.timer)
      if (m.cap) clearTimeout(m.cap)
      if (m.ctx) { try { m.ctx.close() } catch {} }
      mediaRef.current = null; listeningRef.current = false; setListening(false)
      if (st.cancel || !chunks.length) { st.cancel = false; return }
      const blob = new Blob(chunks, { type: recorder.mimeType || mime || 'audio/webm' })
      if (blob.size > 10 * 1024 * 1024) { setTalkNote('the clip is too long (over 10 MB)'); return }
      const ext = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm'
      const fd = new FormData(); fd.append('file', blob, 'clip.' + ext)
      setTranscribing(true); setTalkNote('')
      try {
        const r = await fetch('/cc/transcribe', { method: 'POST', body: fd })
        const d = await r.json().catch(() => ({}))
        if (!r.ok || !d.ok) { setTalkNote(d.error || `the bridge answered ${r.status}`); return }
        if (!d.text) setTalkNote('heard nothing')
        finishTalk([st.base, d.text || ''].filter(Boolean).join(' '))
      } catch { setTalkNote('the bridge did not answer') }
      finally { setTranscribing(false) }
    }
    mediaRef.current = m; listeningRef.current = true; setListening(true); setTalkNote('')
    try { recorder.start(250) } catch { mediaRef.current = null; listeningRef.current = false; setListening(false); setTalkNote('could not start recording') }
  }
  const startListening = (base) => {
    if (listeningRef.current || transcribing) return
    const SR = (typeof window !== 'undefined') && (window.SpeechRecognition || window.webkitSpeechRecognition)
    if (!SR) { startRecording(base); return }
    if (speakingRef.current) stopSpeaking()
    const rec = new SR()
    rec.continuous = true; rec.interimResults = true
    try { rec.lang = navigator.language || 'en-US' } catch {}
    const st = talkRef.current; st.base = (base || '').trim(); st.finals = ''; st.cancel = false; st.err = ''
    rec.onresult = (e) => {
      let finals = '', interim = ''
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i]; const t = (r[0] && r[0].transcript) || ''
        if (r.isFinal) finals += t + ' '; else interim += t
      }
      st.finals = finals.trim()
      setDraft([st.base, st.finals, interim.trim()].filter(Boolean).join(' '))
      clearPause()
      // a pause of about 1.5 s after a final result ends the run
      if (st.finals && !interim.trim()) pauseRef.current = setTimeout(() => { pauseRef.current = null; try { rec.stop() } catch {} }, 1500)
    }
    rec.onerror = (e) => {
      const k = (e && e.error) || ''
      st.err = k
      if (k === 'not-allowed' || k === 'service-not-allowed') setTalkNote('the microphone is not allowed for this page')
      else if (k === 'audio-capture') setTalkNote('no microphone found')
      else if (k === 'no-speech') setTalkNote('heard nothing')
      else if (k === 'network') setTalkNote('the browser\'s speech service did not answer')
      else if (k && k !== 'aborted') setTalkNote('listening failed: ' + k)
    }
    rec.onend = () => {
      clearPause(); recRef.current = null; listeningRef.current = false; setListening(false)
      finishTalk([st.base, st.finals].filter(Boolean).join(' '))
    }
    recRef.current = rec; listeningRef.current = true; setListening(true); setTalkNote('')
    try { rec.start() } catch { recRef.current = null; listeningRef.current = false; setListening(false); setTalkNote('could not start listening') }
  }
  const toggleTalk = (base) => {
    if (listening) { stopListening(false); return }
    if (transcribing) return
    if (!canTalk) { setTalkNote(whyNoTalk || 'this browser cannot listen'); return }
    startListening(base)
  }
  // Hands-free: once armed, listen again as soon as nothing is being said or thought.
  useEffect(() => {
    if (!handsfree || !armedRef.current || !loggedIn) return
    if (speaking || active || listening || transcribing) return
    const t = setTimeout(() => {
      if (!handsfreeRef.current || !armedRef.current || listeningRef.current || speakingRef.current) return
      armedRef.current = false
      startListening('')
    }, 400)
    return () => clearTimeout(t)
  }, [handsfree, speaking, active, listening, transcribing, loggedIn])  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { clearPause(); const r = recRef.current; if (r) { try { r.abort() } catch {} } const m = mediaRef.current; if (m) { try { m.recorder.stop() } catch {} } }, [])

  // Typed with a slash: a few things the page handles itself, like the CLI's own commands.
  // Anything else starting with a slash goes to the reasoner (its custom commands still work).
  async function slash(text) {
    const [cmd, ...rest] = text.slice(1).split(/\s+/); const arg = rest.join(' ').trim()
    if (cmd === 'new') { fresh(); return true }
    if (cmd === 'stop') { await stopTurn(); return true }
    if (cmd === 'posture') {
      const r = await fetch('/cc/posture', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ posture: arg }) })
      const d = await r.json().catch(() => ({}))
      const said = d.posture === 'auto' ? 'Posture: auto. Ordinary edits and commands on this box run without a card; sudo and connected-app writes still ask. From the next turn.'
        : d.posture === 'judged' ? 'Posture: judged. Each action is scored by TypeSafe: safe, on request, risk. Above the thresholds it runs and the card shows the numbers; below, it asks. sudo always asks. From the next turn.'
        : 'Posture: cards. Every edit and command on this box asks. From the next turn.'
      setTurns(t => [...t, { who: 'brain', text: r.ok ? said : (d.error || 'not set'), error: !r.ok }])
      loadHealth(); return true
    }
    if (cmd === 'model') {
      const r = await fetch('/cc/model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: arg }) })
      const d = await r.json().catch(() => ({}))
      setTurns(t => [...t, { who: 'brain', text: r.ok ? `Model: ${d.model || 'the reasoner\'s default'}. Takes effect on the next turn.` : (d.error || 'not set'), error: !r.ok }])
      loadHealth(); return true
    }
    if (cmd === 'pane' && arg) { openPane(arg.startsWith('/') ? arg : '/' + arg); return true }
    if (cmd === 'file') {
      if (!arg) { setTurns(t => [...t, { who: 'brain', text: 'Say which file: /file <path> [where it should go]. The Files pane has a "file this" link on anything under out or in.' }]); return true }
      const [p0, ...rest] = arg.trim().split(/\s+/)
      send(`File this into the world where it belongs and commit (do not push): ${p0}${rest.length ? ` (put it under ${rest.join(' ')})` : ''}`)
      return true
    }
    if (cmd === 'voice') {
      if (!(health && health.voice)) { setTurns(t => [...t, { who: 'brain', text: 'This brain has no voice yet: enter ELEVENLABS_API_KEY in the bridge env on the box and restart the bridge.' }]); return true }
      const a0 = (arg || '').trim()
      if (a0.toLowerCase() === 'list') {
        const r = await fetch('/cc/voices'); const d = await r.json().catch(() => ({}))
        if (!(d.voices || []).length) { setTurns(t => [...t, { who: 'brain', text: 'No voices listed; is the key valid?' }]); return true }
        setTurns(t => [...t, { who: 'brain', text: `Voices on your ElevenLabs account, model ${d.model}. Click one to use it:`, voices: d.voices, currentVoice: d.current_name }])
        return true
      }
      // "/voice <name>", "/voice on <name>", "/voice use <name>": choose by name, turn on, introduce
      const low = a0.toLowerCase()
      const nameArg = low.startsWith('use ') ? a0.slice(4).trim() : low.startsWith('on ') ? a0.slice(3).trim() : (a0 && !['on', 'off', 'list'].includes(low) ? a0 : '')
      if (nameArg) { await chooseVoice(nameArg); return true }
      const on = a0 ? low !== 'off' : !speak
      if (!on) stopSpeaking()
      setSpeakSaved(on)
      setTurns(t => [...t, { who: 'brain', text: on ? 'Voice on. Answers are read aloud as they finish; "listen" under any answer replays it, "stop" stops it.' : 'Voice off.' }])
      return true
    }
    if (cmd === 'talk') {
      const a0 = (arg || '').trim().toLowerCase()
      if (a0.startsWith('free') || a0.startsWith('hands')) {
        if (!canTalk) { setTurns(t => [...t, { who: 'brain', text: whyNoTalk || 'This browser cannot listen.' }]); return true }
        const w = a0.split(/\s+/)[1]; const on = w ? w !== 'off' : !handsfree
        setHandsfreeSaved(on)
        setTurns(t => [...t, { who: 'brain', text: on ? 'Hands-free on. What you say sends by itself; when the answer has finished I listen again. /talk free off to stop.' : 'Hands-free off.' }])
        return true
      }
      if (!canTalk) { setTurns(t => [...t, { who: 'brain', text: whyNoTalk || 'This browser cannot listen.' }]); return true }
      toggleTalk(''); return true
    }
    if (cmd === 'guide') { openPane({ route: '/guide' + (arg ? '?tab=' + encodeURIComponent(arg) : ''), title: 'Guide' }); return true }
    if (cmd === 'files') { openPane({ route: '/files' + (arg ? '?path=' + encodeURIComponent(arg) : (health && health.out ? '?path=' + encodeURIComponent(health.out) : '')), title: 'Files' }); return true }
    if (cmd === 'jobs') {
      const running = jobs.filter(j => j.ended === null), done = jobs.filter(j => j.ended !== null).slice(0, 5)
      setTurns(t => [...t, { who: 'brain', text: (running.length ? running.map(j => `running: ${j.id} ${j.title}`).join('\n') : 'No job running.') + (done.length ? '\n\nRecent: ' + done.map(j => `${j.id} exit ${j.rc}, ${j.title}`).join('; ') : '') }])
      return true
    }
    if (cmd === 'help' || cmd === '') {
      setTurns(t => [...t, { who: 'brain', text: 'Here: /new (new thread), /model sonnet|opus|<id> (or /model alone for the default), /posture cards|auto|judged (how much your own box asks), /files, /jobs, /talk (speak instead of typing; /talk free on for hands-free), /voice on|off|list, /guide (the guide and tutorial), /pane /graph (open a pane), /help. Other slash commands go to the reasoner.' }])
      return true
    }
    return false
  }

  async function send(forced) {
    let text = (typeof forced === 'string' ? forced : draft).trim()
    const block = typeof forced === 'string' ? '' : notesBlock()
    if (!text && files.length === 0 && !block) return
    if (text.startsWith('/') && await slash(text)) { setDraft(''); return }
    if (block) { text = (text ? text + '\n\n' : '') + block; setNotes([]) }
    if (typeof forced !== 'string' && files.length > 0) {
      // Attachments go to the box first (in/<date>/), then the message names them.
      const fd = new FormData(); files.forEach(f => fd.append('file', f, f.name))
      let saved = []
      try {
        const r = await fetch('/cc/upload', { method: 'POST', body: fd })
        const d = await r.json().catch(() => ({}))
        if (!r.ok || !d.ok) { setTurns(t => [...t, { who: 'brain', text: `Could not attach: ${d.error || r.status}`, error: true }]); return }
        saved = d.files || []
      } catch { setTurns(t => [...t, { who: 'brain', text: 'Could not attach: the bridge did not answer.', error: true }]); return }
      setFiles([])
      text = (text || 'Look at the attached file.') + '\n\nAttached on the box: ' + saved.map(f => f.path).join(', ')
    }
    // A message sent while the thread answers is accepted by the bridge and queued there (2026-10-09):
    // delivered as the next turn the moment the running one ends, in order, cancellable below.
    const realKey = curRef.current && !String(curRef.current).startsWith('new:') && !freshRef.current ? curRef.current : null
    const queueOnServer = async (key) => {
      try {
        const rq = await fetch('/cc/queue', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ thread: key, message: text }) })
        if (rq.status !== 202) return false
        const dq = await rq.json().catch(() => ({}))
        srvAtRef.current = Date.now(); setSrv(s0 => ({ ...(s0 || { running: true }), queue: dq.queue || [] }))
        return true
      } catch { return false }
    }
    if ((busy || srvRunning) && realKey) {
      if (await queueOnServer(realKey)) { if (typeof forced !== 'string') setDraft(''); return }
    }
    if (busy && !realKey) { const qid = `q${Date.now()}`; queueRef.current.push({ qid, text }); if (typeof forced !== 'string') setDraft(''); setTurns(t => [...t, { who: 'me', text, queued: true, qid }]); return }
    if (typeof forced !== 'string') setDraft('')
    setTurns(t => [...t, { who: 'me', text }])
    // The thread this turn belongs to: the one shown, or a fresh one under a temporary key until
    // the bridge names it in "done".
    const isNew = freshRef.current || !curRef.current
    const key = isNew ? `new:${Date.now()}` : curRef.current
    if (isNew) showThread(key)
    markRunning(key, true)
    try {
      const r = await fetch('/cc/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ message: text, new: isNew, thread: isNew ? null : key, stream: true }) })
      freshRef.current = false
      let data = null
      if (r.ok && (r.headers.get('content-type') || '').includes('text/event-stream') && r.body) {
        // The bridge streams: text as it forms, one line per tool call, then "done" with
        // the same payload a plain answer carries. The live bubble is the last turn.
        data = await consume(r, key, false)
      } else {
        data = await r.json().catch(() => ({}))
        if (!isNew && (r.status === 202 || (r.status === 409 && data.error === 'busy'))) {
          // the page thought the thread idle, the bridge says it answers: queue instead of refusing
          if (r.status === 202 || await queueOnServer(key)) {
            setTurns(t => (t.length && t[t.length - 1].who === 'me' && t[t.length - 1].text === text ? t.slice(0, -1) : t))
            if (r.status === 202) { srvAtRef.current = Date.now(); setSrv(s0 => ({ ...(s0 || { running: true }), queue: data.queue || [] })) }
            return
          }
        }
        const reply = data.reply || (r.ok ? '(no answer)' : `The bridge answered ${r.status}.`)
        if (curRef.current === key) setTurns(t => [...t, { who: 'brain', text: reply, ms: data.ms, error: !!data.error, proposal: data.proposal || null, meta: data.meta || null }])
        if (data.pane && curRef.current === key) openPane(data.pane)
      }
      if (isNew && data && data.thread) {
        // the new thread has its name now; the page shown under the temporary key follows it
        delete runningRef.current[key]
        if (curRef.current === key) showThread(data.thread)
      }
      loadLatest()
      loadThreads()
    } catch (e) {
      if (curRef.current === key) setTurns(t => [...t, { who: 'brain', text: 'The bridge did not answer. Is cc-bridge running on the box?', error: true }])
    } finally {
      markRunning(key, false)
      if (curRef.current === key && queueRef.current.length) flushLocal()
      setTimeout(() => pollRef.current && pollRef.current(), 400)
      if (boxRef.current) boxRef.current.focus()
    }
  }

  async function fresh() {
    // Allowed while a thread answers: it goes on by itself; this page turns to a blank one.
    freshRef.current = true
    showThread(null)
    if (!paneModeRef.current) { try { await fetch('/cc/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }) } catch {} }
    setTurns([])
    setPane(null)
    loadHealth()
    loadThreads()
  }

  async function askAgain(a) {
    try {
      const r = await fetch('/cc/permits/auto/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ platform: a.platform, action_id: a.action_id }) })
      const d = await r.json().catch(() => ({}))
      setAuto(d.auto || [])
    } catch {}
  }

  async function signOut() {
    if (busy) return
    try { await fetch('/cc/logout', { method: 'POST' }) } catch {}
    loadHealth()
  }

  sendRef.current = send
  // Stop and interrupt (2026-10-06). Esc or "stop" ends the answer in progress; the thread keeps
  // what was said and every finished step, and the next message resumes it. "send now" (or
  // Cmd/Ctrl+Enter while it answers) queues the message and stops the turn, so the message goes
  // in the moment the turn ends: the terminal's interrupt, one turn at a time.
  async function stopTurn() {
    const key = curRef.current
    if (!key || !(runningRef.current[key] || srvRunning)) return false
    const body = String(key).startsWith('new:') ? { run: runIdRef.current[key] || '' } : { thread: key }
    try {
      const r = await fetch('/cc/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      return r.ok
    } catch { return false }
  }
  async function cancelQueued(id) {
    const key = curRef.current
    try {
      const r = await fetch('/cc/queue/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ thread: key, id }) })
      const d = await r.json().catch(() => ({}))
      if (d && d.queue) setSrv(s0 => ({ ...(s0 || {}), queue: d.queue }))
    } catch {}
  }
  async function sendNow() {
    await send()
    await stopTurn()
  }

  function onKey(e) {
    if (e.key === 'Escape' && active) { e.preventDefault(); stopTurn(); return }
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && active && draft.trim()) { e.preventDefault(); sendNow(); return }
    if (e.key === 'Tab' && draft.startsWith('/') && !/\s/.test(draft)) {
      const m = SLASH.find(s => s.c.startsWith(draft))
      if (m) { e.preventDefault(); setDraft(m.c + ' '); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <>
      <Head><title>CC · BrainFoundry</title></Head>
      <div style={{ display: 'flex', flexDirection: paneSide === 'left' ? 'row-reverse' : 'row', alignItems: 'stretch', minHeight: paneMode ? '100vh' : 'calc(100vh - 60px)' }}>
      <div style={{ padding: paneMode ? '6px 10px 8px' : '28px 32px 20px', maxWidth: pane || paneMode ? 'none' : width, margin: pane ? 0 : '0 auto', flex: 1, minWidth: 0,
                    fontFamily, display: 'flex', flexDirection: 'column', height: paneMode ? '100vh' : 'calc(100vh - 60px)', boxSizing: 'border-box' }}>

        <div style={{ display: paneMode ? 'none' : 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
          <div style={{ minWidth: 0 }}>
            {!paneMode && !hidden.hero && <>
            <p style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 4px 0' }}>
              cc · reasoning from inside the brain
              <a onClick={() => hide('hero', true)} title="Hide this title; it comes back with reset layout" style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline', marginLeft: '12px', textTransform: 'none', letterSpacing: 0 }}>hide</a>
            </p>
            <h1 style={{ fontSize: '22px', color: C.ink, margin: 0, fontWeight: 600 }}>Talk to your brain</h1>
            </>}
            {paneMode && !curThread && <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: 0 }}>new conversation</p>}
            {curThread && (
              <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '4px 0 0 0', display: 'flex', gap: '8px', alignItems: 'baseline', flexWrap: 'wrap' }}>
                {renaming === 'header'
                  ? <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)} maxLength={80}
                           onKeyDown={e => { if (e.key === 'Enter') finishRename(curThread.brain); else if (e.key === 'Escape') setRenaming(null) }}
                           onBlur={() => setRenaming(null)}
                           style={{ ...mono, fontSize: '11px', color: C.ink, backgroundColor: 'transparent', border: 'none', borderBottom: `1px solid ${C.line}`, outline: 'none', padding: '0 2px', minWidth: '240px' }} />
                  : <span style={{ color: C.dim, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60vw' }}>{curThread.title || 'untitled'}</span>}
                {renaming !== 'header' && <a onClick={() => startRename('header', curThread.title)} style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline', fontSize: '10px' }}>rename</a>}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', position: 'relative' }}>
            {(threads.length > 0 || archivedCount > 0) && <Btn small onClick={() => { setShowThreads(s => !s); loadThreads() }} title="Earlier conversations the brain remembers">threads</Btn>}
            <Btn small onClick={fresh} title={busy ? 'Start another conversation; this one keeps answering' : 'Start a new conversation'}>new thread</Btn>
            {!paneMode && <Btn small onClick={() => { window.location.href = '/panes' }} title="Several conversations side by side, like terminal windows">side by side</Btn>}
            {!paneMode && <Btn small onClick={() => { window.location.href = '/board' }} title="Mission control: one tile per run, with its state, its last line and any card that waits for you">board</Btn>}
            {turns.length > 0 && <Btn small title="the whole conversation as markdown: copied, and downloaded as a file" onClick={exportThread}>export</Btn>}
            {showThreads && (
              <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', width: 'min(420px, 90vw)', maxHeight: '60vh', overflowY: 'auto', backgroundColor: C.card,
                            border: `1px solid ${C.line}`, borderRadius: '10px', padding: '6px', zIndex: 120 }}>
                {threadGroups.map(g => (
                  <div key={g.label}>
                    <p style={{ ...mono, color: C.faint, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', margin: '6px 10px 2px' }}>{g.label}</p>
                    {g.items.map(th => {
                      const act = { ...mono, color: C.faint, fontSize: '10px', cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }
                      return (
                        <div key={th.brain} style={{ display: 'flex', alignItems: 'baseline', gap: '8px', padding: '6px 10px', borderRadius: '6px' }}>
                          {renaming === th.brain
                            ? <input autoFocus value={renameVal} onChange={e => setRenameVal(e.target.value)} maxLength={80}
                                     onKeyDown={e => { if (e.key === 'Enter') finishRename(th.brain); else if (e.key === 'Escape') setRenaming(null) }}
                                     onBlur={() => setRenaming(null)} onClick={e => e.stopPropagation()}
                                     style={{ flex: 1, fontSize: '13px', color: C.ink, backgroundColor: 'transparent', border: 'none', borderBottom: `1px solid ${C.line}`, outline: 'none', padding: '0 2px', fontFamily: 'inherit' }} />
                            : <a onClick={() => switchThread(th)}
                                 style={{ flex: 1, minWidth: 0, cursor: 'pointer', textDecoration: 'none', color: cur === th.brain ? C.ink : (th.archived ? C.faint : C.dim), fontSize: '13px', lineHeight: 1.4 }}>
                                {th.running ? <span style={{ ...mono, color: C.gold, fontSize: '10px', marginRight: '8px' }}>{th.waiting ? 'waits for you' : 'answering'}</span> : null}{th.title || 'untitled'}
                                <span style={{ ...mono, color: C.faint, fontSize: '10px', marginLeft: '8px' }}>{th.pinned ? (th.last || th.started || '').slice(0, 10) : clock(th.last || th.started)}{th.archived ? ' · archived' : ''}</span>
                              </a>}
                          {renaming !== th.brain && (
                            <span style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                              <a onClick={() => startRename(th.brain, th.title)} style={act}>rename</a>
                              <a onClick={() => updateThread(th.brain, { pinned: !th.pinned })} style={act}>{th.pinned ? 'unpin' : 'pin'}</a>
                              <a onClick={() => updateThread(th.brain, { archived: !th.archived })} style={act}>{th.archived ? 'unarchive' : 'archive'}</a>
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ))}
                {(archivedCount > 0 || showArchived) && (
                  <p style={{ ...mono, color: C.faint, fontSize: '10px', margin: '8px 10px 4px', borderTop: `1px solid ${C.line}`, paddingTop: '8px' }}>
                    {archivedCount} archived · <a onClick={toggleArchived} style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>{showArchived ? 'hide' : 'show'}</a>
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {!paneMode && !hidden.hint && firstRun && !firstRun.complete && loggedIn && <FirstRun steps={firstRun.steps} onOpen={openPane} />}
        {!paneMode && !hidden.hint && loggedIn && turns.length === 0 && (
          <p style={{ margin: '0 0 16px 0', color: C.faint, fontSize: '13px' }}>
            New here? <a onClick={() => openPane({ route: '/guide', title: 'Guide' })} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>The guide</a> explains what this brain can do, with a seven-step tutorial that checks itself. Or type /help.
            <a onClick={() => hide('hint', true)} style={{ ...mono, fontSize: '11px', marginLeft: '12px', cursor: 'pointer', textDecoration: 'underline' }}>hide</a>
          </p>
        )}

        {health === false && (
          <div style={{ padding: '12px 16px', backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '10px', marginBottom: '14px' }}>
            <p style={{ margin: 0, color: C.dim, fontSize: '13px', lineHeight: 1.6 }}>
              The reasoner bridge is not answering at <code>/cc/health</code> on this console. The tab is on, the box side is not.
              On the server, run <code>bash scripts/cc/install.sh</code> in the brain directory (docs/CC.md), then reload.
            </p>
          </div>
        )}

        {health && !loggedIn && <SignIn health={health} onDone={loadHealth} onOpenPane={openPane} />}

        <div ref={convRef} onMouseUp={onPick} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '4px 2px', position: 'relative' }}>
          {pick && (
            <span style={{ position: 'absolute', left: pick.x, top: pick.y, zIndex: 50, display: 'inline-flex', gap: '4px' }}>
              {[['remark', 'a note in the margin on the selected span; it goes with your next message', () => addNote()],
                ['copy', 'copy the selected words', () => { try { navigator.clipboard.writeText(pick.raw || pick.quote) } catch {} setPick(null) }],
                ['ask', 'put the selected words into the composer to ask about them', () => { setDraft(d => (d ? d + '\n' : '') + `About this: "${pick.quote}" `); setPick(null); if (boxRef.current) boxRef.current.focus() }]].map(([label, title, fn]) => (
                <a key={label} onMouseDown={e => { e.preventDefault(); fn() }} title={title}
                   style={{ ...mono, fontSize: '11px', letterSpacing: '0.1em', textTransform: 'uppercase', color: label === 'remark' ? '#141210' : C.ink, backgroundColor: label === 'remark' ? C.gold : C.card, border: `1px solid ${C.gold}`, padding: '4px 9px', borderRadius: '6px', cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.4)' }}>{label}</a>
              ))}
            </span>
          )}
          {pending.map(p => (
            <div key={p.id} style={{ display: 'flex', justifyContent: 'flex-start', margin: '8px 0' }}>
              <div style={{ maxWidth: '78%', padding: '10px 14px', borderRadius: '12px', backgroundColor: C.brain, border: `1px solid ${C.line}`, color: C.ink, fontSize: '14px', lineHeight: 1.6 }}>
                <span style={{ color: C.dim }}>Still waiting for your decision:</span>
                <ProposalCard p={p} onDecide={decide} />
              </div>
            </div>
          ))}
          {turns.length === 0 && loggedIn && pending.length === 0 && (
            <p style={{ color: C.faint, fontSize: '14px', lineHeight: 1.7, margin: '24px 0' }}>
              This surface reasons over what the brain remembers and over its own files on its own server.
              Ask what the brain knows about you, what changed recently, or what a document says. It reads; it does not change anything from here.
              {health.session ? ' The previous thread continues.' : ''}
            </p>
          )}
          {turns.map((t, i) => (t.who === 'note' ? (
            <div key={i} data-turn={i} style={{ display: 'flex', justifyContent: 'flex-start', margin: paneMode ? '3px 0' : '4px 0' }}>
              <span style={{ ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: C.faint, padding: '0 4px' }}>· {t.text}</span>
            </div>
          ) : (
            <div key={i} data-turn={i} style={{ display: 'flex', flexWrap: room ? 'nowrap' : 'wrap', justifyContent: t.who === 'me' ? 'flex-end' : 'flex-start', margin: paneMode ? '5px 0' : '8px 0', position: 'relative' }}>
              {notes.some(n => n.turn === i) && (
                <div style={room ? { position: 'absolute', left: 'calc(100% + 14px)', top: 0, display: 'flex', flexDirection: 'column', gap: '8px', width: '250px' }
                                  : { order: 2, width: '100%', display: 'flex', flexDirection: 'column', gap: '8px', margin: '6px 0 0 0' }}>
                  {notes.filter(n => n.turn === i).map(noteCard)}
                </div>
              )}
              <div style={{
                maxWidth: paneMode ? '94%' : '78%', padding: paneMode ? '6px 11px' : '10px 14px', borderRadius: paneMode ? '10px' : '12px', whiteSpace: paneMode && t.who === 'brain' && t.text && !t.job ? 'normal' : 'pre-wrap', wordBreak: 'break-word',
                backgroundColor: t.who === 'me' ? C.me : C.brain, border: `1px solid ${t.error ? C.bad : C.line}`,
                color: t.who === 'me' ? C.meText : C.ink, fontSize: '14px', lineHeight: 1.6, opacity: t.queued ? 0.55 : 1,
              }}>
                {t.job && (
                  <div>
                    <p style={{ ...mono, color: t.job.rc === 0 ? C.dim : '#d08a7a', fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>job finished · {t.job.rc === 0 ? 'ok' : `exit ${t.job.rc}`} · {Math.round(((t.job.ended || 0) - t.job.started) / 60)} min</p>
                    <p style={{ margin: '0 0 8px 0', color: C.ink, fontSize: '14px' }}>{t.job.title}</p>
                    <pre style={{ ...mono, fontSize: '11px', color: C.faint, whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: '0 0 8px 0', maxHeight: '120px', overflow: 'auto' }}>{(t.job.tail || '').trim().split('\n').slice(-6).join('\n')}</pre>
                    <Btn small onClick={() => send(`Read the log of job ${t.job.id} (${t.job.log}) and tell me the result in a few lines; if it made files, open them beside the chat.`)}>ask the brain about it</Btn>
                  </div>
                )}
                {t.queued && <div style={{ ...mono, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', color: C.gold, margin: '0 0 4px 0' }}>queued · <a onClick={() => { queueRef.current = queueRef.current.filter(x => x.qid !== t.qid); setTurns(ts => ts.filter(x => x.qid !== t.qid)) }} style={{ cursor: 'pointer', textDecoration: 'underline' }}>cancel</a></div>}
                {t.who === 'brain' ? (t.text ? <Md text={t.text} /> : (t.live ? <span style={{ color: C.dim, fontStyle: 'italic' }}>working{t.model ? ` with ${shortModel(t.model)}` : ''}…</span> : null)) : (t.who === 'me' && t.text ? <LinkedText text={t.text} /> : t.text)}
                {t.voices && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                    {t.voices.map(v => (
                      <a key={v.id} onClick={() => chooseVoice(v.name)} title={v.labels || ''} style={{ ...mono, fontSize: '12px', padding: '4px 10px', borderRadius: '14px', border: `1px solid ${v.name === (health && health.voice_name) ? C.gold : C.line}`, color: v.name === (health && health.voice_name) ? C.gold : C.dim, cursor: 'pointer' }}>{v.name}</a>
                    ))}
                  </div>
                )}
                {t.asks && t.asks.map(a => <ProposalCard key={a.id} p={a} onDecide={decide} />)}
                {t.proposal && <ProposalCard p={t.proposal} onDecide={decide} />}
                {t.who === 'brain' && t.steps && t.steps.length > 0 && (
                  <div style={{ ...mono, color: C.faint, fontSize: '11px', marginTop: '6px', lineHeight: 1.6 }}>
                    {(t.live ? t.steps.slice(-3) : t.steps.slice(-6)).map((s, j) => <div key={j}>{s}</div>)}
                    {!t.live && t.steps.length > 6 ? <div>and {t.steps.length - 6} more</div> : null}
                  </div>
                )}
                {t.who === 'brain' && typeof t.ms === 'number' && (
                  <div style={{ ...mono, color: C.faint, fontSize: '11px', marginTop: '6px' }}>
                    {(t.ms / 1000).toFixed(1)} s{t.meta && t.meta.model ? ` · ${shortModel(t.meta.model)}` : ''}{t.meta && (t.meta.in || t.meta.cached) ? ` · ${kTok(t.meta.in)} in${t.meta.cached ? ` (+${kTok(t.meta.cached)} cached)` : ''} · ${kTok(t.meta.out)} out` : ''}{t.meta && t.meta.steps > 1 ? ` · ${t.meta.steps} steps` : ''}{t.sources && t.sources.length ? <span title={t.sources.join('\n')}> · <a onClick={() => openPane({ route: '/graph', title: 'Memory' })} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>{t.sources.length} memor{t.sources.length === 1 ? 'y' : 'ies'} used</a></span> : null} · <CopyLink text={t.text} label="copy" style={{ fontSize: 'inherit', letterSpacing: 'normal', textTransform: 'none' }} />
                    {health && health.voice && t.text ? <> · <a onClick={() => (speaking ? stopSpeaking() : say(t.text))} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>{speaking ? 'stop' : 'listen'}</a></> : null}
                  </div>
                )}
              </div>
            </div>
          )))}
          {srv && srv.queue && srv.queue.map(q => (
            <div key={q.id} style={{ display: 'flex', justifyContent: 'flex-end', margin: paneMode ? '5px 0' : '8px 0' }}>
              <div style={{ maxWidth: paneMode ? '94%' : '78%', padding: paneMode ? '6px 11px' : '10px 14px', borderRadius: paneMode ? '10px' : '12px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', backgroundColor: C.me, border: `1px solid ${C.line}`, color: C.meText, fontSize: '14px', lineHeight: 1.6, opacity: 0.55 }}>
                <div style={{ ...mono, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', color: C.gold, margin: '0 0 4px 0' }}>queued · <a onClick={() => cancelQueued(q.id)} style={{ cursor: 'pointer', textDecoration: 'underline' }}>cancel</a></div>
                {q.message}
              </div>
            </div>
          ))}
          {active && !(turns.length && turns[turns.length - 1].live) && <div style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '8px 0' }}>thinking on the box…</div>}
          <div ref={endRef} />
        </div>

        {draft.startsWith('/') && !/\s/.test(draft) && SLASH.some(s => s.c.startsWith(draft)) && (
          <div style={{ ...mono, marginTop: '12px', border: `1px solid ${C.line}`, borderRadius: '10px', backgroundColor: C.card, padding: '6px 0', fontSize: '12px' }}>
            {SLASH.filter(s => s.c.startsWith(draft)).map(s => (
              <div key={s.c} onClick={() => { setDraft(s.c + ' '); boxRef.current && boxRef.current.focus() }}
                style={{ display: 'flex', gap: '14px', padding: '5px 12px', cursor: 'pointer', color: C.ink }}>
                <span style={{ color: C.gold, minWidth: '64px' }}>{s.c}</span><span style={{ color: C.dim }}>{s.d}</span>
              </div>
            ))}
            <div style={{ padding: '4px 12px 0', color: C.faint, fontSize: '11px' }}>Tab completes. Other slash commands go to the reasoner.</div>
          </div>
        )}
        {!paneMode && (() => {
          const live = [...turns].reverse().find(x => x.live)
          const last = [...turns].reverse().find(x => x.who === 'brain' && !x.live && x.ms)
          return (
            <p style={{ ...mono, fontSize: '11px', margin: '12px 0 0 0', color: active ? C.gold : C.faint, display: 'flex', gap: '10px', alignItems: 'baseline' }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: active ? C.gold : C.line, animation: active ? 'ccpulse 1.2s ease-in-out infinite' : 'none' }} />
              {active
                ? (() => {
                    // elapsed and steps come from the bridge when it reports the run (it knows turns started elsewhere, and subagents), else from this page
                    const sr = srvRunning && srv.run ? srv.run : null
                    const ms = sr ? sr.seconds * 1000 + (Date.now() - srvAtRef.current) : (busySince ? Date.now() - busySince : null)
                    const nSteps = sr ? sr.steps : (live && live.steps ? live.steps.length : 0)
                    const lastStep = sr ? sr.last : (live && live.steps && live.steps.length ? String(live.steps[live.steps.length - 1]) : '')
                    const nq = srv && srv.queue ? srv.queue.length : 0
                    return <span>answering{ms !== null ? ` for ${fmtElapsed(ms)}` : ''}{nSteps ? ` · ${nSteps} step${nSteps === 1 ? '' : 's'}` : (live && live.text ? ' · writing' : ' · thinking')}{sr && sr.agents ? ` · ${sr.agents} subagent${sr.agents === 1 ? '' : 's'}` : ''}{nq ? ` · ${nq} queued` : ''}{lastStep ? ` · last: ${lastStep.slice(0, 90)}` : ''}</span>
                  })()
                : <span>idle{last ? ` · last answer ${(last.ms / 1000).toFixed(1)} s${last.meta && last.meta.steps > 1 ? `, ${last.meta.steps} steps` : ''}` : ''}</span>}
              <style>{`@keyframes ccpulse { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } }`}</style>
            </p>
          )
        })()}
        {notes.filter(n => n.text.trim()).length > 0 && (
          <p style={{ ...mono, color: C.gold, fontSize: '11px', margin: '12px 0 0 0' }}>{notes.filter(n => n.text.trim()).length} remark{notes.filter(n => n.text.trim()).length === 1 ? '' : 's'} in the margin go with your next message · <a onClick={() => setNotes([])} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>clear</a></p>
        )}
        {latest.length > 0 && (!paneMode || paneDetails) && (
          <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '12px 0 0 0', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <span>latest:</span>
            {latest.map(f => (
              <a key={f.path} onClick={() => openPane({ route: '/files?path=' + encodeURIComponent(f.path), title: 'Files' })} title={f.path}
                style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</a>
            ))}
          </p>
        )}
        {/* The composer wraps on a phone (360 px): the textarea takes the first row, the buttons the next. */}
        <div style={{ display: 'flex', flexWrap: paneMode ? 'nowrap' : 'wrap', gap: paneMode ? '6px' : '8px', alignItems: 'flex-end', marginTop: paneMode ? '6px' : '12px' }}>
          <textarea ref={boxRef} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKey} rows={paneMode ? 1 : 2}
            placeholder={paneMode && loggedIn && !listening ? (active ? 'answering; Enter queues, Cmd+Enter sends now' : 'Ask your brain') : !loggedIn ? 'connect a reasoner first' : listening ? (srOk ? 'listening; a pause ends it, or press stop' : 'recording; a pause ends it, or press stop') : active ? 'thinking; Enter queues for when it ends, Cmd/Ctrl+Enter or "send now" interrupts, Esc stops.' : 'Ask your brain. Enter sends, Shift+Enter for a new line. / for commands.'}
            disabled={!loggedIn}
            onDragOver={e => { e.preventDefault() }} onDrop={e => { e.preventDefault(); setFiles(f => [...f, ...Array.from(e.dataTransfer.files || [])]) }}
            style={{ flex: paneMode ? '1 1 auto' : '1 1 240px', minWidth: 0, resize: paneMode ? 'none' : 'vertical', minHeight: paneMode ? '34px' : '48px', maxHeight: paneMode ? '132px' : undefined, padding: paneMode ? '6px 10px' : '10px 12px', borderRadius: '10px', backgroundColor: C.card, color: C.ink,
                     border: `1px solid ${listening ? C.gold : C.line}`, fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5, outline: 'none' }} />
          <input ref={fileRef} type="file" multiple style={{ display: 'none' }} onChange={e => { setFiles(f => [...f, ...Array.from(e.target.files || [])]); e.target.value = '' }} />
          {!paneMode && (
          <div style={{ display: 'flex', gap: '8px', flex: '0 0 auto', marginLeft: 'auto' }}>
            <Btn onClick={() => fileRef.current && fileRef.current.click()} disabled={!loggedIn} title="Attach files; they land on your box and the brain reads them there">attach</Btn>
            <Btn onClick={() => toggleTalk(draft)} disabled={!loggedIn || transcribing} accent={listening}
              title={listening ? 'Stop listening' : canTalk ? (srOk ? 'Speak; the words appear here as you talk' : 'Record; the bridge transcribes the clip') : (whyNoTalk || 'this browser cannot listen')}>
              {listening ? 'stop' : transcribing ? 'hearing' : 'talk'}
            </Btn>
            {active && <Btn onClick={stopTurn} title="Stop the answer in progress (Esc). The thread keeps everything up to here.">stop</Btn>}
            {active && (draft.trim() || files.length > 0) && <Btn onClick={sendNow} title="Stop the answer and send this now (Cmd/Ctrl+Enter)">send now</Btn>}
            <Btn primary onClick={send} disabled={(!draft.trim() && files.length === 0) || !loggedIn}>{active && draft.trim() ? 'queue' : 'send'}</Btn>
          </div>
          )}
          {paneMode && (
            <div style={{ display: 'flex', gap: '4px', flex: '0 0 auto', alignItems: 'flex-end' }}>
              <IconBtn onClick={() => fileRef.current && fileRef.current.click()} disabled={!loggedIn} title="Attach files; they land on your box and the brain reads them there"><IcoClip /></IconBtn>
              <IconBtn onClick={() => toggleTalk(draft)} disabled={!loggedIn || transcribing} on={listening}
                title={listening ? 'Stop listening' : canTalk ? (srOk ? 'Speak; the words appear here as you talk' : 'Record; the bridge transcribes the clip') : (whyNoTalk || 'this browser cannot listen')}><IcoMic /></IconBtn>
              {active && <IconBtn onClick={stopTurn} title="Stop the answer in progress (Esc). The thread keeps everything up to here."><IcoStop /></IconBtn>}
              <IconBtn primary onClick={active && (draft.trim() || files.length > 0) ? sendNow : send} disabled={(!draft.trim() && files.length === 0) || !loggedIn}
                title={active ? 'Stop the answer and send this now (Cmd/Ctrl+Enter); Enter alone queues it' : 'Send (Enter)'}><IcoSend /></IconBtn>
            </div>
          )}
        </div>
        {(listening || transcribing || talkNote) && (
          <p style={{ ...mono, color: listening ? C.gold : C.faint, fontSize: '11px', margin: '6px 0 0 0' }}>
            {listening ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <span>{(srOk ? 'listening' : 'recording') + (handsfree ? ' (hands-free)' : '')}</span>
                <span style={{ display: 'inline-flex', gap: '2px', alignItems: 'flex-end', height: '12px' }}>
                  {[0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92].map((th, i) => <span key={i} style={{ width: '4px', height: `${4 + i * 1.2}px`, borderRadius: '1px', backgroundColor: mic.level >= th ? C.gold : C.line, transition: 'background-color 80ms' }} />)}
                </span>
                <span style={{ color: mic.level > 0.08 ? C.gold : C.faint }}>{mic.level > 0.08 ? 'hearing you' : 'quiet'}</span>
                {mic.since ? <span style={{ color: C.faint }}>{Math.floor((mic.tick - mic.since) / 1000)} s</span> : null}
                {!srOk ? <span style={{ color: C.faint }}>· the words appear when you stop</span> : null}
              </span>
            ) : transcribing ? 'the bridge is transcribing the clip' : talkNote}
          </p>
        )}
        {files.length > 0 && (
          <p style={{ ...mono, color: C.dim, fontSize: '11px', margin: '8px 0 0 0', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            {files.map((f, i) => <span key={i} style={{ border: `1px solid ${C.line}`, borderRadius: '8px', padding: '2px 8px', display: 'inline-flex', alignItems: 'center' }}><ChipThumb file={f} />{f.name} · {(f.size / 1024).toFixed(0)} KB <a onClick={() => setFiles(x => x.filter((_, j) => j !== i))} style={{ cursor: 'pointer', color: C.faint }}>x</a></span>)}
          </p>
        )}
        <div style={paneMode ? { display: paneDetails ? 'block' : 'none', maxHeight: '45vh', overflowY: 'auto', borderTop: `1px solid ${C.line}`, marginTop: '6px', paddingBottom: '4px' } : undefined}>
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '10px 0 0 0', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          {showDetails && <span>{health && health.session ? 'thread continues across reloads' : 'a new thread starts with your first message'}</span>}
          {showDetails && health && health.tools ? <span><a onClick={() => setShowTools(s => !s)} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>{health.tools.split(',').length} tools without a card</a></span> : null}
          {showDetails && health && typeof health.memory === 'boolean' ? <span>memory {health.memory ? 'on' : 'off'}</span> : null}
          {!paneMode && sysWarn.length > 0 ? <span><a onClick={() => openPane({ route: '/system', title: 'System' })} style={{ color: '#d4b86a', cursor: 'pointer', textDecoration: 'underline' }}>{sysWarn[0]}{sysWarn.length > 1 ? ` (+${sysWarn.length - 1})` : ''}</a></span> : null}
          {!paneMode && health && health.voice ? <span><a onClick={() => { if (speak) stopSpeaking(); setSpeakSaved(!speak) }} style={{ color: speak ? C.gold : C.dim, cursor: 'pointer', textDecoration: 'underline' }}>voice {speak ? 'on' : 'off'}</a>{health.voice_name ? ` (${health.voice_name})` : ''}</span> : null}
          {!paneMode && loggedIn && canTalk ? <span><a onClick={() => setHandsfreeSaved(!handsfree)} title="What you say sends by itself; after the answer has finished speaking, listening restarts" style={{ color: handsfree ? C.gold : C.dim, cursor: 'pointer', textDecoration: 'underline' }}>hands-free {handsfree ? 'on' : 'off'}</a></span> : null}
          {showDetails && usage && usage.today ? <span><a onClick={() => openPane({ route: '/system', title: 'System' })} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>today {usage.today.turns} turn{usage.today.turns === 1 ? '' : 's'} · {kTok(usage.today.in)} in · {kTok(usage.today.out)} out{usage.today.cost !== null && usage.today.cost !== undefined ? ` · $${usage.today.cost.toFixed(2)}` : ''}</a></span> : null}
          {showDetails && health && health.hands ? <span>hands: {health.hands}{health.writes ? ' · writes need your Send' : ' · read only'}</span> : null}
          {showDetails && health && health.box ? <span>this box: {health.posture === 'auto' ? 'auto posture, sudo and app writes ask' : health.posture === 'judged' ? 'judged posture, TypeSafe scores each action' : 'edits and commands need your Allow'}</span> : null}
          {!paneMode && health && (health.runs || []).some(r => r.thread !== cur) ? <span><a onClick={() => { setShowThreads(true); loadThreads() }} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>{(() => { const n = (health.runs || []).filter(r => r.thread !== cur).length; return n === 1 ? 'another conversation is answering' : `${n} other conversations are answering` })()}</a></span> : null}
          {health && health.cards_waiting > 0 ? <span><a onClick={() => { if (endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' }) }} style={{ color: '#d4b86a', cursor: 'pointer', textDecoration: 'underline', fontWeight: 600 }}>{health.cards_waiting === 1 ? 'a card waits for you' : `${health.cards_waiting} cards wait for you`}</a></span> : null}
          {health && health.ingest && health.ingest.pending > 0 ? <span><a onClick={() => openPane({ route: '/upload', title: 'Knowledge' })} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>{health.ingest.pending} document{health.ingest.pending === 1 ? '' : 's'} wait for your approval</a></span> : null}
          {health && health.out ? <span><a onClick={() => openPane({ route: '/files?path=' + encodeURIComponent(health.out), title: 'Files' })} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>files</a>{jobs.some(j => j.ended === null) ? ` · ${jobs.filter(j => j.ended === null).length} job${jobs.filter(j => j.ended === null).length === 1 ? '' : 's'} running` : ''}</span> : null}
          {showDetails && loggedIn && health.auth.email ? <span>connected as {health.auth.email} · <a onClick={signOut} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>disconnect</a></span> : null}
          <span><a onClick={() => (paneMode ? setPaneDetails(false) : setShowDetails(s => !s))} style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>{paneMode ? 'close details' : showDetails ? 'less' : 'details'}</a></span>
          {showDetails ? <span><a onClick={() => setShowFonts(s => !s)} title="the font of the conversation" style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>font{fontPick ? `: ${fontPick.label}` : ''}</a></span> : null}
          {!paneMode && (layoutChanged || pane || width !== '860px') ? <span><a onClick={resetLayout} title="Show every block again, put the side pane back on the right at its usual width" style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>reset layout</a></span> : null}
          {!paneMode && hidden.hero ? <span><a onClick={() => hide('hero', false)} style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>show title</a></span> : null}
          {!pane && !paneMode ? <span><a onClick={cycleWidth} title="the width of the conversation: narrow, wide, full" style={{ color: C.faint, cursor: 'pointer', textDecoration: 'underline' }}>{width === '860px' ? 'narrow' : width === '1180px' ? 'wide' : 'full width'}</a></span> : null}
          {!paneMode && auto.length > 0 ? <span><a onClick={() => setShowAuto(s => !s)} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>{auto.length} action{auto.length === 1 ? '' : 's'} run without asking</a></span> : null}
        </p>
        {showTools && health && health.tools && (
          <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '6px 0 0 0', lineHeight: 1.6, wordBreak: 'break-word', maxHeight: '84px', overflowY: 'auto' }}>{health.tools.split(',').join('  ')}</p>
        )}
        {showDetails && showFonts && (
          <p style={{ color: C.faint, fontSize: '12px', margin: '6px 0 0 0', display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'baseline' }}>
            <a onClick={() => setFontSaved('')} style={{ color: !fontPick ? C.gold : C.dim, cursor: 'pointer', textDecoration: 'underline', fontFamily: 'var(--font-display, serif)' }}>default</a>
            {FONTS.map(f => <a key={f.value} onClick={() => setFontSaved(f.value)} style={{ color: font === f.value ? C.gold : C.dim, cursor: 'pointer', textDecoration: 'underline', fontFamily: f.family }}>{f.label}</a>)}
          </p>
        )}
        {showAuto && auto.length > 0 && (
          <ul style={{ ...mono, listStyle: 'none', padding: '8px 0 0 0', margin: 0, color: C.dim, fontSize: '11px' }}>
            {auto.map(a => (
              <li key={a.platform + a.action_id} style={{ display: 'flex', gap: '10px', alignItems: 'baseline', padding: '3px 0' }}>
                <span>{a.platform} · {a.method || 'POST'} · {a.title || a.action_id}</span>
                <a onClick={() => askAgain(a)} style={{ color: C.gold, cursor: 'pointer', textDecoration: 'underline' }}>ask again</a>
              </li>
            ))}
          </ul>
        )}
        </div>
      </div>
      {pane && <Pane pane={pane} side={paneSide} onSide={flipSide} onClose={() => { setPane(null); loadHealth() }} />}
      </div>
    </>
  )
}


// A crash inside the page shows its reason here, with a reload and a copy, instead of Next's blank
// "Application error" (2026-10-01: a client-side exception under "details" in Firefox could not be
// read from the box). The error text is also logged to the bridge's audit through /cc/client-error.
class CCBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null, info: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err, info) {
    this.setState({ info })
    try {
      fetch('/cc/client-error', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: String(err && err.message || err), stack: String(err && err.stack || '').slice(0, 4000), component: String(info && info.componentStack || '').slice(0, 2000), ua: navigator.userAgent }) }).catch(() => {})
    } catch {}
  }
  render() {
    if (!this.state.err) return this.props.children
    const text = `${String(this.state.err && this.state.err.message || this.state.err)}\n\n${String(this.state.err && this.state.err.stack || '')}\n${String(this.state.info && this.state.info.componentStack || '')}`
    return (
      <div style={{ padding: '40px 32px', color: '#e8e0d5', fontFamily: 'var(--font-display, serif)', maxWidth: '860px', margin: '0 auto' }}>
        <p style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: '#c9a96e', margin: '0 0 10px 0' }}>CC · the page hit an error</p>
        <p style={{ fontSize: '14px', lineHeight: 1.6, margin: '0 0 12px 0' }}>{String(this.state.err && this.state.err.message || this.state.err)}</p>
        <p style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: '12px', margin: '0 0 16px 0' }}>
          <a onClick={() => window.location.reload()} style={{ color: '#c9a96e', cursor: 'pointer', textDecoration: 'underline' }}>reload</a>
          {'  '}<a onClick={() => { try { navigator.clipboard.writeText(text) } catch {} }} style={{ color: '#9a8f82', cursor: 'pointer', textDecoration: 'underline' }}>copy the error</a>
          {'  '}<a onClick={() => { try { localStorage.removeItem('cc.font'); localStorage.removeItem('cc.width') } catch {}; window.location.reload() }} style={{ color: '#9a8f82', cursor: 'pointer', textDecoration: 'underline' }}>reset the page's saved choices and reload</a>
        </p>
        <pre style={{ fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: '11px', color: '#6b5f52', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{text.slice(0, 3000)}</pre>
        <p style={{ fontSize: '12px', color: '#6b5f52' }}>The error is recorded on the box; the operator's seat reads it from there.</p>
      </div>
    )
  }
}

export default function CCPage() { return <CCBoundary><CC /></CCBoundary> }
