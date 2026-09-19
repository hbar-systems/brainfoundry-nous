import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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

function Btn({ children, onClick, disabled, primary, small, title }) {
  const off = !!disabled
  return (
    <button onClick={onClick} disabled={off} title={title}
      style={{
        padding: small ? '6px 12px' : '10px 16px', borderRadius: '10px', cursor: off ? 'default' : 'pointer',
        border: primary ? 'none' : `1px solid ${C.line}`,
        backgroundColor: primary ? (off ? C.card : C.gold) : 'transparent',
        color: primary ? (off ? C.dim : C.onAccent) : C.dim,
        fontWeight: primary ? 600 : 400, fontSize: small ? '12px' : '14px', fontFamily: small ? mono.fontFamily : 'inherit',
      }}>{children}</button>
  )
}

function Md({ text }) {
  // The reasoner answers in markdown. Render it, but keep it plain: no raw HTML,
  // links open in a new tab, code stays monospace.
  return (
    <div className="cc-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
        components={{
          a: ({ node, ...props }) => <a {...props} target="_blank" rel="noreferrer" style={{ color: C.gold }} />,
          p: ({ node, ...props }) => <p {...props} style={{ margin: '0 0 8px 0' }} />,
          ul: ({ node, ...props }) => <ul {...props} style={{ margin: '0 0 8px 0', paddingLeft: '20px' }} />,
          ol: ({ node, ...props }) => <ol {...props} style={{ margin: '0 0 8px 0', paddingLeft: '20px' }} />,
          code: ({ node, inline, ...props }) => <code {...props} style={{ ...mono, fontSize: '12.5px', backgroundColor: C.codeBg, color: C.codeFg, padding: inline ? '1px 5px' : '8px 10px', borderRadius: '6px', display: inline ? 'inline' : 'block', whiteSpace: 'pre-wrap' }} />,
          table: ({ node, ...props }) => <table {...props} style={{ borderCollapse: 'collapse', fontSize: '13px', margin: '4px 0 8px 0' }} />,
          th: ({ node, ...props }) => <th {...props} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: `1px solid ${C.line}`, color: C.dim, fontWeight: 500 }} />,
          td: ({ node, ...props }) => <td {...props} style={{ padding: '4px 8px', borderBottom: `1px solid ${C.line}` }} />,
        }}>{text || ''}</ReactMarkdown>
    </div>
  )
}

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
  if (p.auto) {
    const ok = p.outcome && p.outcome.ok
    return (
      <div style={{ marginTop: '10px', padding: '10px 14px', borderRadius: '10px', border: `1px solid ${ok ? C.line : C.bad}`, backgroundColor: C.card }}>
        <p style={{ ...mono, color: C.dim, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
          {ok ? 'done without asking' : 'tried without asking, failed'} · {p.method || 'POST'} · {p.platform || ''}
        </p>
        <p style={{ margin: 0, color: C.ink, fontSize: '14px', lineHeight: 1.5 }}>{p.summary}</p>
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '6px 0 0 0' }}>you allowed this action earlier · permit {p.id}{ok ? '' : ` · ${(p.outcome && p.outcome.result && p.outcome.result.error) || 'error'}`}</p>
      </div>
    )
  }
  return (
    <div style={{ marginTop: '10px', padding: '12px 14px', borderRadius: '10px', border: `1px solid ${C.gold}`, backgroundColor: C.card }}>
      <p style={{ ...mono, color: C.gold, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
        proposed write · {p.method || 'POST'} · {p.platform || ''}
      </p>
      <p style={{ margin: '0 0 10px 0', color: C.ink, fontSize: '14px', lineHeight: 1.5 }}>{p.summary || 'an action in a connected app'}</p>
      {decided ? (
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: 0 }}>{decided === 'approve' ? 'sent' : 'cancelled'} · permit {p.id}</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <Btn primary onClick={() => onDecide(p.id, 'approve', remember)} disabled={p.busy}>{p.busy ? 'sending…' : 'Send'}</Btn>
            <Btn onClick={() => onDecide(p.id, 'deny')} disabled={p.busy}>Cancel</Btn>
            <span style={{ ...mono, color: C.faint, fontSize: '11px' }}>permit {p.id}{p.ttl_seconds ? ` · valid ${Math.round(p.ttl_seconds / 60)} min` : ''}</span>
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '10px', color: C.dim, fontSize: '12px', cursor: 'pointer' }}>
            <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} disabled={p.busy} style={{ accentColor: C.gold }} />
            don&apos;t ask again for this action ({p.platform}, {p.method || 'POST'}); still recorded in the audit, you can undo it below
          </label>
        </>
      )}
    </div>
  )
}

function Pane({ pane, onClose }) {
  // A summoned surface (D54): an existing console page, same origin and auth, shown
  // beside the conversation and dismissed with one click. Pages hide their own nav
  // when embedded (see _app.js). Narrow screens get it as an overlay; "wide" covers
  // the whole console; the page itself may go fullscreen (allowFullScreen).
  const [narrow, setNarrow] = useState(false)
  const [wide, setWide] = useState(false)
  useEffect(() => {
    const f = () => setNarrow(window.innerWidth < 960)
    f(); window.addEventListener('resize', f); return () => window.removeEventListener('resize', f)
  }, [])
  const box = (narrow || wide)
    ? { position: 'fixed', top: 'calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px))', right: 0, bottom: 0, left: 0, zIndex: 150, backgroundColor: C.brain, display: 'flex', flexDirection: 'column' }
    : { width: 'min(48vw, 760px)', flexShrink: 0, borderLeft: `1px solid ${C.line}`, backgroundColor: C.brain, display: 'flex', flexDirection: 'column' }
  return (
    <div style={box}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: `1px solid ${C.line}` }}>
        <span style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase' }}>{pane.title || pane.route}</span>
        <span style={{ display: 'flex', gap: '8px' }}>
          {!narrow && <Btn small onClick={() => setWide(x => !x)} title={wide ? 'Back beside the conversation' : 'Cover the whole console'}>{wide ? 'beside' : 'wide'}</Btn>}
          <Btn small onClick={onClose} title="Put it away">close</Btn>
        </span>
      </div>
      <iframe src={pane.route} title={pane.title || pane.route} allowFullScreen allow="fullscreen" style={{ flex: 1, width: '100%', border: 0, backgroundColor: C.brain }} />
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

export default function CC() {
  const [turns, setTurns] = useState([])       // { who: 'me' | 'brain', text, ms, error }
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)   // null unknown, false down, object ok
  const [pending, setPending] = useState([])    // permits proposed earlier, still waiting (survive reload)
  const [auto, setAuto] = useState([])          // actions the owner allowed to run without a card
  const [showAuto, setShowAuto] = useState(false)
  const [pane, setPane] = useState(null)         // a summoned surface beside the conversation (D54)
  const [firstRun, setFirstRun] = useState(null) // first-use steps from the api, until complete
  const [threads, setThreads] = useState([])       // CC threads the brain remembers
  const [showThreads, setShowThreads] = useState(false)
  const endRef = useRef(null)
  const boxRef = useRef(null)
  const freshRef = useRef(false)   // the next message must start a new thread, whatever happened to /cc/new

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
        setTurns(d.messages.map(m => ({ who: m.role === 'user' ? 'me' : 'brain', text: m.content })))
      })
      .catch(() => {})
  }
  const loadThreads = () =>
    fetch('/cc/threads', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (d) setThreads(d.threads || []) }).catch(() => {})
  useEffect(() => {
    fetch('/cc/health', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(h => { setHealth(h); if (h && h.brain_session_id) loadHistory(h.brain_session_id) })
      .catch(() => setHealth(false))
    loadPending(); loadFirstRun(); loadThreads()
  }, [])
  const openPane = (p) => { if (p && p.route) setPane(p) }

  // A pane may hand a question to the conversation (the graph's "ask the brain about this").
  useEffect(() => {
    const onMsg = (e) => {
      if (e.origin !== window.location.origin) return
      if (e.data && e.data.type === 'cc-ask' && typeof e.data.text === 'string') {
        setDraft(e.data.text)
        if (boxRef.current) boxRef.current.focus()
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  async function switchThread(th) {
    if (busy) return
    try {
      const r = await fetch('/cc/threads/switch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brain: th.brain }) })
      if (r.ok) { setTurns([]); setPane(null); loadHistory(th.brain); loadHealth() }
    } catch {}
    setShowThreads(false)
  }

  // The write gate: a proposal card's Send approves the permit and executes that one
  // action through One; Cancel denies it. Either way the audit log gets a line.
  async function decide(id, action, remember) {
    setTurns(t => t.map(x => (x.proposal && x.proposal.id === id ? { ...x, proposal: { ...x.proposal, busy: true } } : x)))
    let data = {}
    try {
      const r = await fetch(`/cc/permits/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, remember: !!remember }) })
      data = await r.json().catch(() => ({}))
    } catch (e) { data = { ok: false, error: 'the bridge did not answer' } }
    setPending(p => p.filter(x => x.id !== id))
    if (remember && data.ok) loadPending()
    setTurns(t => t.map(x => (x.proposal && x.proposal.id === id ? { ...x, proposal: { ...x.proposal, busy: false, decided: action } } : x)))
    if (action === 'approve') {
      const text = data.ok
        ? `Done: ${data.summary || 'the action ran'}.` + (data.result && data.result.status ? ` One answered ${data.result.status}.` : '')
        : `Not done. ${(data.result && data.result.error) || data.error || 'the write failed'}`
      setTurns(t => [...t, { who: 'brain', text, error: !data.ok }])
    } else {
      setTurns(t => [...t, { who: 'brain', text: 'Cancelled. Nothing was sent.' }])
    }
  }

  useEffect(() => {
    if (endRef.current) endRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns, busy])

  const loggedIn = !!(health && health.auth && health.auth.loggedIn)

  async function send() {
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    setTurns(t => [...t, { who: 'me', text }])
    setBusy(true)
    try {
      const r = await fetch('/cc/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text, new: freshRef.current }) })
      freshRef.current = false
      const data = await r.json().catch(() => ({}))
      const reply = data.reply || (r.ok ? '(no answer)' : `The bridge answered ${r.status}.`)
      setTurns(t => [...t, { who: 'brain', text: reply, ms: data.ms, error: !!data.error, proposal: data.proposal || null }])
      if (data.pane) openPane(data.pane)
      if (turns.length === 0) loadThreads()
    } catch (e) {
      setTurns(t => [...t, { who: 'brain', text: 'The bridge did not answer. Is cc-bridge running on the box?', error: true }])
    } finally {
      setBusy(false)
      if (boxRef.current) boxRef.current.focus()
    }
  }

  async function fresh() {
    if (busy) return
    freshRef.current = true
    try { await fetch('/cc/new', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }) } catch {}
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

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <>
      <Head><title>CC · BrainFoundry</title></Head>
      <div style={{ display: 'flex', alignItems: 'stretch', minHeight: 'calc(100vh - 60px)' }}>
      <div style={{ padding: '28px 32px 20px', maxWidth: pane ? 'none' : '860px', margin: pane ? 0 : '0 auto', flex: 1, minWidth: 0,
                    fontFamily: 'var(--font-display, serif)', display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 60px)' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
          <div>
            <p style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 4px 0' }}>
              cc · reasoning from inside the brain
            </p>
            <h1 style={{ fontSize: '26px', color: C.ink, margin: 0, fontWeight: 600 }}>Talk to your brain</h1>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', position: 'relative' }}>
            {threads.length > 0 && <Btn small onClick={() => { setShowThreads(s => !s); loadThreads() }} title="Earlier conversations the brain remembers">threads</Btn>}
            <Btn small onClick={fresh} disabled={busy} title="Start a new conversation">new thread</Btn>
            {showThreads && (
              <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', width: 'min(420px, 90vw)', maxHeight: '60vh', overflowY: 'auto', backgroundColor: C.card,
                            border: `1px solid ${C.line}`, borderRadius: '10px', padding: '6px', zIndex: 120 }}>
                {threads.map(th => (
                  <a key={th.brain} onClick={() => switchThread(th)}
                     style={{ display: 'block', padding: '8px 10px', borderRadius: '6px', cursor: 'pointer', textDecoration: 'none',
                              color: health && health.brain_session_id === th.brain ? C.ink : C.dim, fontSize: '13px', lineHeight: 1.4 }}>
                    {th.title || 'untitled'}
                    <span style={{ ...mono, color: C.faint, fontSize: '10px', marginLeft: '8px' }}>{(th.last || th.started || '').slice(0, 10)}</span>
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>

        {firstRun && !firstRun.complete && loggedIn && <FirstRun steps={firstRun.steps} onOpen={openPane} />}

        {health === false && (
          <div style={{ padding: '12px 16px', backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '10px', marginBottom: '14px' }}>
            <p style={{ margin: 0, color: C.dim, fontSize: '13px', lineHeight: 1.6 }}>
              The reasoner bridge is not answering at <code>/cc/health</code> on this console. The tab is on, the box side is not.
              On the server, run <code>bash scripts/cc/install.sh</code> in the brain directory (docs/CC.md), then reload.
            </p>
          </div>
        )}

        {health && !loggedIn && <SignIn health={health} onDone={loadHealth} onOpenPane={openPane} />}

        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 2px' }}>
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
          {turns.map((t, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: t.who === 'me' ? 'flex-end' : 'flex-start', margin: '8px 0' }}>
              <div style={{
                maxWidth: '78%', padding: '10px 14px', borderRadius: '12px', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                backgroundColor: t.who === 'me' ? C.me : C.brain, border: `1px solid ${t.error ? C.bad : C.line}`,
                color: t.who === 'me' ? C.meText : C.ink, fontSize: '14px', lineHeight: 1.6,
              }}>
                {t.who === 'brain' ? <Md text={t.text} /> : t.text}
                {t.proposal && <ProposalCard p={t.proposal} onDecide={decide} />}
                {t.who === 'brain' && typeof t.ms === 'number' && (
                  <div style={{ ...mono, color: C.faint, fontSize: '11px', marginTop: '6px' }}>{(t.ms / 1000).toFixed(1)} s</div>
                )}
              </div>
            </div>
          ))}
          {busy && <div style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '8px 0' }}>thinking on the box…</div>}
          <div ref={endRef} />
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', marginTop: '12px' }}>
          <textarea ref={boxRef} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={onKey} rows={2}
            placeholder={!loggedIn ? 'connect a reasoner first' : busy ? 'one turn at a time' : 'Ask your brain. Enter sends, Shift+Enter for a new line.'}
            disabled={busy || !loggedIn}
            style={{ flex: 1, resize: 'vertical', minHeight: '48px', padding: '10px 12px', borderRadius: '10px', backgroundColor: C.card, color: C.ink,
                     border: `1px solid ${C.line}`, fontFamily: 'inherit', fontSize: '14px', lineHeight: 1.5, outline: 'none' }} />
          <Btn primary onClick={send} disabled={busy || !draft.trim() || !loggedIn}>send</Btn>
        </div>
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: '10px 0 0 0', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <span>{health && health.session ? 'thread continues across reloads' : 'a new thread starts with your first message'}</span>
          {health && health.tools ? <span>read-only: {health.tools}</span> : null}
          {health && typeof health.memory === 'boolean' ? <span>memory {health.memory ? 'on' : 'off'}</span> : null}
          {health && health.hands ? <span>hands: {health.hands}{health.writes ? ' · writes need your Send' : ' · read only'}</span> : null}
          {loggedIn && health.auth.email ? <span>connected as {health.auth.email} · <a onClick={signOut} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>disconnect</a></span> : null}
          {auto.length > 0 ? <span><a onClick={() => setShowAuto(s => !s)} style={{ color: C.dim, cursor: 'pointer', textDecoration: 'underline' }}>{auto.length} action{auto.length === 1 ? '' : 's'} run without asking</a></span> : null}
        </p>
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
      {pane && <Pane pane={pane} onClose={() => { setPane(null); loadHealth() }} />}
      </div>
    </>
  )
}
