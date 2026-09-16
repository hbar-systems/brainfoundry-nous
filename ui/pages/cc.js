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

const C = {
  ink: '#e8e0d5', dim: '#8b7d6e', faint: '#6b5f52', gold: '#c9a96e',
  card: '#1c1814', line: '#c9a96e40', me: '#231d18', brain: '#15120f', bad: '#7a3a2e',
}
const mono = { fontFamily: 'DM Mono, monospace' }

function Btn({ children, onClick, disabled, primary, small, title }) {
  const off = !!disabled
  return (
    <button onClick={onClick} disabled={off} title={title}
      style={{
        padding: small ? '6px 12px' : '10px 16px', borderRadius: '10px', cursor: off ? 'default' : 'pointer',
        border: primary ? 'none' : `1px solid ${C.line}`,
        backgroundColor: primary ? (off ? '#3a3520' : C.gold) : 'transparent',
        color: primary ? (off ? C.dim : '#141210') : C.dim,
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
          code: ({ node, inline, ...props }) => <code {...props} style={{ ...mono, fontSize: '12.5px', backgroundColor: '#0f0e0c', padding: inline ? '1px 5px' : '8px 10px', borderRadius: '6px', display: inline ? 'inline' : 'block', whiteSpace: 'pre-wrap' }} />,
          table: ({ node, ...props }) => <table {...props} style={{ borderCollapse: 'collapse', fontSize: '13px', margin: '4px 0 8px 0' }} />,
          th: ({ node, ...props }) => <th {...props} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: `1px solid ${C.line}`, color: C.dim, fontWeight: 500 }} />,
          td: ({ node, ...props }) => <td {...props} style={{ padding: '4px 8px', borderBottom: `1px solid ${C.line}20` }} />,
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
  const decided = p.decided
  return (
    <div style={{ marginTop: '10px', padding: '12px 14px', borderRadius: '10px', border: `1px solid ${C.gold}80`, backgroundColor: '#1a1610' }}>
      <p style={{ ...mono, color: C.gold, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 6px 0' }}>
        proposed write · {p.method || 'POST'} · {p.platform || ''}
      </p>
      <p style={{ margin: '0 0 10px 0', color: C.ink, fontSize: '14px', lineHeight: 1.5 }}>{p.summary || 'an action in a connected app'}</p>
      {decided ? (
        <p style={{ ...mono, color: C.faint, fontSize: '11px', margin: 0 }}>{decided === 'approve' ? 'sent' : 'cancelled'} · permit {p.id}</p>
      ) : (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Btn primary onClick={() => onDecide(p.id, 'approve')} disabled={p.busy}>{p.busy ? 'sending…' : 'Send'}</Btn>
          <Btn onClick={() => onDecide(p.id, 'deny')} disabled={p.busy}>Cancel</Btn>
          <span style={{ ...mono, color: C.faint, fontSize: '11px' }}>permit {p.id}{p.ttl_seconds ? ` · valid ${Math.round(p.ttl_seconds / 60)} min` : ''}</span>
        </div>
      )}
    </div>
  )
}

function SignIn({ onDone, health }) {
  const [state, setState] = useState({ phase: 'idle' })
  const [code, setCode] = useState('')
  const [method, setMethod] = useState(null)
  const timer = useRef(null)

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

      {state.phase === 'idle' || state.phase === 'error' ? (
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <Btn primary onClick={() => start('claudeai')}>Sign in with a Claude subscription</Btn>
          <Btn onClick={() => start('console')}>Sign in with an Anthropic Console account</Btn>
        </div>
      ) : null}

      {state.phase === 'starting' && (
        <p style={{ color: C.dim, fontSize: '13px', fontStyle: 'italic', margin: '8px 0 0 0' }}>preparing the sign-in link…</p>
      )}

      {(state.phase === 'url' || state.phase === 'code_sent') && state.url && (
        <div style={{ marginTop: '6px' }}>
          <ol style={{ color: C.dim, fontSize: '14px', lineHeight: 1.7, paddingLeft: '20px', margin: '0 0 12px 0' }}>
            <li>Open the sign-in page and log in to your account.
              <div style={{ margin: '8px 0' }}>
                <a href={state.url} target="_blank" rel="noreferrer"
                   style={{ display: 'inline-block', padding: '10px 16px', borderRadius: '10px', backgroundColor: C.gold, color: '#141210', fontWeight: 600, textDecoration: 'none', fontSize: '14px' }}>
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
        {method === 'console' ? 'billed per use to your own Console account' : method === 'claudeai' ? 'uses your own subscription; this is your account on your server' : 'either door works; both are your own account'}
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
  const endRef = useRef(null)
  const boxRef = useRef(null)

  const loadHealth = () =>
    fetch('/cc/health', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setHealth)
      .catch(() => setHealth(false))
  const loadPending = () =>
    fetch('/cc/permits', { cache: 'no-store' }).then(r => r.ok ? r.json() : { pending: [] }).then(d => setPending(d.pending || [])).catch(() => {})
  useEffect(() => { loadHealth(); loadPending() }, [])

  // The write gate: a proposal card's Send approves the permit and executes that one
  // action through One; Cancel denies it. Either way the audit log gets a line.
  async function decide(id, action) {
    setTurns(t => t.map(x => (x.proposal && x.proposal.id === id ? { ...x, proposal: { ...x.proposal, busy: true } } : x)))
    let data = {}
    try {
      const r = await fetch(`/cc/permits/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) })
      data = await r.json().catch(() => ({}))
    } catch (e) { data = { ok: false, error: 'the bridge did not answer' } }
    setPending(p => p.filter(x => x.id !== id))
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
      const r = await fetch('/cc/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) })
      const data = await r.json().catch(() => ({}))
      const reply = data.reply || (r.ok ? '(no answer)' : `The bridge answered ${r.status}.`)
      setTurns(t => [...t, { who: 'brain', text: reply, ms: data.ms, error: !!data.error, proposal: data.proposal || null }])
    } catch (e) {
      setTurns(t => [...t, { who: 'brain', text: 'The bridge did not answer. Is cc-bridge running on the box?', error: true }])
    } finally {
      setBusy(false)
      if (boxRef.current) boxRef.current.focus()
    }
  }

  async function fresh() {
    if (busy) return
    try { await fetch('/cc/new', { method: 'POST' }) } catch {}
    setTurns([])
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
      <div style={{ padding: '28px 32px 20px', maxWidth: '860px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif',
                    display: 'flex', flexDirection: 'column', minHeight: 'calc(100vh - 60px)' }}>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '12px', marginBottom: '14px' }}>
          <div>
            <p style={{ ...mono, color: C.gold, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', margin: '0 0 4px 0' }}>
              cc · reasoning from inside the brain
            </p>
            <h1 style={{ fontSize: '26px', color: C.ink, margin: 0, fontWeight: 600 }}>Talk to your brain</h1>
          </div>
          <Btn small onClick={fresh} disabled={busy} title="Start a new conversation">new thread</Btn>
        </div>

        {health === false && (
          <div style={{ padding: '12px 16px', backgroundColor: C.card, border: `1px solid ${C.line}`, borderRadius: '10px', marginBottom: '14px' }}>
            <p style={{ margin: 0, color: C.dim, fontSize: '13px', lineHeight: 1.6 }}>
              The reasoner bridge is not answering at <code>/cc/health</code> on this console. The tab is on, the box side is not.
              On the server, run <code>bash scripts/cc/install.sh</code> in the brain directory (docs/CC.md), then reload.
            </p>
          </div>
        )}

        {health && !loggedIn && <SignIn health={health} onDone={loadHealth} />}

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
                color: C.ink, fontSize: '14px', lineHeight: 1.6,
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
        </p>
      </div>
    </>
  )
}
