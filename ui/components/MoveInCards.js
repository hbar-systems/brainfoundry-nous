// Moving in, on the quiet home (PARENTS-HOME-1 addendum 2, 2026-11-15). Two cards, first on the home
// until both are done: the ChatGPT (or Claude) export zip, and the person's documents. Each card is its
// own drop target, shows its state (not started / waiting for the email / N waiting for your yes /
// N moved in on <day>), and remembers through one press. The doors are the Knowledge page's own:
// POST /documents/import-chats, /api/permit + POST /documents/upload, POST /documents/approve-all.
// When both are in, the cards fold into one quiet line. Words and rules: ui/lib/moveIn.js.
import { useEffect, useRef, useState } from 'react'
import { HOME_NEWEST, chatState, docState, folded, MOVE_WAIT_KEY, MOVE_DOCS_KEY, day, moveWords } from '../lib/moveIn'

const API = '/api/bf'
const ls = {
  get(k) { try { return localStorage.getItem(k) } catch { return null } },
  set(k, v) { try { localStorage.setItem(k, v) } catch {} },
}
const todayIso = () => new Date().toISOString().slice(0, 10)

// The drawn mark for a drop: a tray with an arrow into it (one stroke, the card's ink).
function DropMark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M14 4v12m0 0l-5-5m5 5l5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17v4.5A2.5 2.5 0 006.5 24h15a2.5 2.5 0 002.5-2.5V17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
function DoneMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="8" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5.5 9.2l2.3 2.3 4.7-4.9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Pill({ tone, children }) {
  return <span className={`mi-pill mi-pill-${tone}`}>{tone === 'done' && <DoneMark />}{children}</span>
}

// One card: a drop target with a heading, its state, a body and its buttons.
function Card({ title, state, tone, onFiles, accept, multiple, busy, children, dropLabel }) {
  const [over, setOver] = useState(false)
  const depth = useRef(0)
  const on = {
    onDragEnter: (e) => { e.preventDefault(); depth.current += 1; setOver(true) },
    onDragOver: (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' },
    onDragLeave: () => { depth.current = Math.max(0, depth.current - 1); if (!depth.current) setOver(false) },
    onDrop: (e) => {
      e.preventDefault(); depth.current = 0; setOver(false)
      if (busy) return
      const fs = Array.from((e.dataTransfer && e.dataTransfer.files) || [])
      if (fs.length) onFiles(multiple ? fs : fs.slice(0, 1))
    },
  }
  return (
    <section className={`mi-card${over ? ' mi-over' : ''}${tone === 'done' ? ' mi-done' : ''}`} {...on} data-accept={accept}>
      <div className="mi-head">
        <span className="mi-mark"><DropMark /></span>
        <h2 className="mi-title">{title}</h2>
      </div>
      <div className="mi-state"><Pill tone={tone}>{state}</Pill></div>
      {children}
      {over && <div className="mi-overlay" aria-hidden="true"><DropMark size={40} /><span>{dropLabel}</span></div>}
    </section>
  )
}

export default function MoveInCards({ lang = 'en', onMoved }) {
  const W = moveWords(lang)
  const [docs, setDocs] = useState(null)        // GET /documents rows, null until read
  const [pending, setPending] = useState([])    // [{ proposal_id, filename }]
  const [asked, setAsked] = useState(null)
  const [docMark, setDocMark] = useState(null)
  const [chatBusy, setChatBusy] = useState(null) // null | { reading } | { found, took } | { error }
  const [docBusy, setDocBusy] = useState(null)   // null | { i, n } | { error }
  const [approving, setApproving] = useState(null) // null | { which, done, total }
  const [reopen, setReopen] = useState(false)
  const chatInput = useRef(null)
  const docInput = useRef(null)

  const load = async () => {
    const j = (u) => fetch(u, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
    const [d, p] = await Promise.all([j(`${API}/documents?limit=10000`), j(`${API}/memory/proposals?status=PENDING&limit=1000`)])
    setDocs(d && Array.isArray(d.documents) ? d.documents : [])
    const items = p && Array.isArray(p.proposals) ? p.proposals : []
    setPending(items.filter(x => x.memory_type === 'document_embedding' && x.proposal_id)
      .map(x => ({ proposal_id: x.proposal_id, filename: (x.source_refs && x.source_refs.filename) || '' })))
  }
  useEffect(() => {
    setAsked(ls.get(MOVE_WAIT_KEY))
    try { setDocMark(JSON.parse(ls.get(MOVE_DOCS_KEY) || 'null')) } catch { setDocMark(null) }
    load()
  }, [])

  const chat = chatState(docs, pending, asked)
  const doc = docState(docMark, pending)

  // one press remembers what waits; the server ingests (approve-all), this card follows its count
  const remember = async (which, ids) => {
    if (!ids.length) return
    setApproving({ which, done: 0, total: ids.length })
    try {
      const r = await fetch(`${API}/documents/approve-all`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ proposal_ids: ids }) })
      if (!r.ok) throw new Error(String(r.status))
      for (let k = 0; k < 900; k++) {
        await new Promise(res => setTimeout(res, 2000))
        const s = await fetch(`${API}/documents/approve-all/status`, { cache: 'no-store' }).then(x => (x.ok ? x.json() : null)).catch(() => null)
        if (!s) continue
        setApproving({ which, done: s.done || 0, total: s.total || ids.length })
        if (!s.running) break
      }
      if (which === 'doc') {
        const m = { n: ((docMark && docMark.n) || 0) + ids.length, at: todayIso() }
        ls.set(MOVE_DOCS_KEY, JSON.stringify(m)); setDocMark(m)
      }
      if (onMoved) onMoved(which)
    } catch {
      if (which === 'chat') setChatBusy({ error: W.failed }); else setDocBusy({ error: W.failed })
    }
    setApproving(null)
    load()
  }
  const chatIds = () => pending.filter(p => chatState([], [p], null).step === 'pending').map(p => p.proposal_id)
  const docIds = () => pending.filter(p => docState(null, [p]).step === 'pending').map(p => p.proposal_id)

  const importZip = async (files) => {
    const f = files[0]
    if (!f) return
    if (!/\.zip$/i.test(f.name)) { setChatBusy({ error: W.notZip }); return }
    setChatBusy({ reading: f.name })
    const fd = new FormData()
    fd.append('file', f)
    fd.append('newest', String(HOME_NEWEST))
    try {
      const r = await fetch(`${API}/documents/import-chats`, { method: 'POST', body: fd })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) { setChatBusy({ error: (j.error && j.error.message) || j.detail || W.failed }); return }
      setChatBusy({ found: j.conversations || 0, took: j.selected || 0 })
      await load()
    } catch { setChatBusy({ error: W.failed }) }
  }

  const sendDocs = async (files) => {
    if (!files.length) return
    setDocBusy({ i: 0, n: files.length })
    try {
      const pr = await fetch('/api/permit', { method: 'POST' })
      if (!pr.ok) throw new Error('permit')
      const { permit_id } = await pr.json()
      for (let i = 0; i < files.length; i++) {
        setDocBusy({ i: i + 1, n: files.length })
        const fd = new FormData()
        fd.append('file', files[i])
        fd.append('permit_id', permit_id)
        await fetch(`${API}/documents/upload`, { method: 'POST', body: fd }).catch(() => null)
      }
      setDocBusy(null)
      await load()
    } catch { setDocBusy({ error: W.failed }) }
  }

  if (docs === null) return null
  if (folded(chat, doc) && !reopen) {
    return (
      <p className="mi-folded" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', margin: '8px 0 24px', fontSize: '16px', color: 'var(--text-dim, var(--muted))' }}>
        <span style={{ color: '#9cbf8a', display: 'inline-flex' }}><DoneMark /></span> <span>{W.folded(chat.n, doc.n)}</span>{' '}
        <button type="button" onClick={() => setReopen(true)}
          style={{ color: 'var(--accent)', background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit', textDecoration: 'underline', textUnderlineOffset: '3px' }}>{W.foldedMore}</button>
      </p>
    )
  }

  const tone = (s) => (s.step === 'done' ? 'done' : s.step === 'new' ? 'new' : 'wait')
  const label = (s, kind) => (
    s.step === 'done' ? W.state[kind === 'chat' ? 'chatDone' : 'docDone'](s.n, day(lang, s.at))
      : s.step === 'pending' ? W.state.pending(s.waitingYes)
        : s.step === 'waiting' ? W.state.waiting(day(lang, s.at))
          : W.state.new
  )
  const ap = (which) => approving && approving.which === which

  return (
    <div className="mi">
      <Card title={W.chatTitle} state={label(chat, 'chat')} tone={tone(chat)} onFiles={importZip} accept=".zip"
        busy={!!(chatBusy && chatBusy.reading) || ap('chat')} dropLabel={W.dropHere}>
        {chat.step !== 'done' && chat.step !== 'pending' && (
          <ol className="mi-steps">
            {W.chatSteps.map((s, i) => (
              <li key={i}>{s.length === 3 ? <>{s[0]}<a href="https://chatgpt.com/#settings/DataControls" target="_blank" rel="noreferrer">{s[1]}</a>{s[2]}</> : s[0]}</li>
            ))}
          </ol>
        )}
        {chatBusy && chatBusy.found != null && <p className="mi-note">{W.chatFound(chatBusy.found, chatBusy.took)}</p>}
        {chatBusy && chatBusy.error && <p className="mi-note mi-bad" role="alert">{chatBusy.error}</p>}
        <div className="mi-actions">
          {chat.waitingYes > 0 ? (
            <button type="button" className="mi-btn mi-primary" disabled={!!approving} onClick={() => remember('chat', chatIds())}>
              {ap('chat') ? W.remembering(approving.done, approving.total) : W.remember(chat.waitingYes)}
            </button>
          ) : chat.step !== 'done' && (
            <>
              <button type="button" className="mi-btn mi-primary" disabled={!!(chatBusy && chatBusy.reading)} onClick={() => chatInput.current && chatInput.current.click()}>
                {chatBusy && chatBusy.reading ? W.chatReading(chatBusy.reading) : W.chatPick}
              </button>
              {chat.step === 'new' && (
                <button type="button" className="mi-btn" onClick={() => { const d = todayIso(); ls.set(MOVE_WAIT_KEY, d); setAsked(d) }}>{W.chatAsked}</button>
              )}
            </>
          )}
          <input ref={chatInput} type="file" accept=".zip,application/zip" hidden
            onChange={(e) => { const f = Array.from(e.target.files || []); e.target.value = ''; importZip(f) }} />
        </div>
      </Card>

      <Card title={W.docTitle} state={label(doc, 'doc')} tone={tone(doc)} onFiles={sendDocs} multiple
        busy={!!(docBusy && docBusy.n) || ap('doc')} dropLabel={W.dropHere}>
        {doc.step !== 'done' && <p className="mi-sub">{W.docSub}</p>}
        {docBusy && docBusy.error && <p className="mi-note mi-bad" role="alert">{docBusy.error}</p>}
        <div className="mi-actions">
          {doc.waitingYes > 0 ? (
            <button type="button" className="mi-btn mi-primary" disabled={!!approving} onClick={() => remember('doc', docIds())}>
              {ap('doc') ? W.remembering(approving.done, approving.total) : W.remember(doc.waitingYes)}
            </button>
          ) : (
            <button type="button" className={doc.step === 'done' ? 'mi-btn' : 'mi-btn mi-primary'} disabled={!!(docBusy && docBusy.n)} onClick={() => docInput.current && docInput.current.click()}>
              {docBusy && docBusy.n ? W.docSending(docBusy.i, docBusy.n) : W.docPick}
            </button>
          )}
          <a className="mi-link" href="/upload#laptop">{W.docWhole}</a>
          <input ref={docInput} type="file" multiple hidden
            onChange={(e) => { const f = Array.from(e.target.files || []); e.target.value = ''; sendDocs(f) }} />
        </div>
      </Card>

      <style jsx>{`
        .mi { display: grid; gap: 16px; margin: 8px 0 28px; }
        .mi :global(.mi-card) {
          position: relative; padding: 26px 28px 24px; border-radius: 18px;
          background: color-mix(in srgb, var(--surface2) 88%, var(--accent) 12%);
          border: 1px solid color-mix(in srgb, var(--border) 60%, var(--accent) 40%);
          box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 28px -14px rgba(0,0,0,0.55);
          transition: border-color 180ms cubic-bezier(.2,.8,.2,1), background-color 180ms cubic-bezier(.2,.8,.2,1);
        }
        .mi :global(.mi-card.mi-done) { background: var(--surface); border-color: var(--border); box-shadow: none; padding: 20px 28px; }
        .mi :global(.mi-card.mi-over) { border-color: var(--accent); background: color-mix(in srgb, var(--surface2) 75%, var(--accent) 25%); }
        .mi :global(.mi-head) { display: flex; align-items: center; gap: 14px; color: var(--accent); }
        .mi :global(.mi-title) { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: 24px; line-height: 1.25; color: var(--text); text-wrap: balance; }
        .mi :global(.mi-done .mi-title) { font-size: 19px; font-weight: 400; }
        .mi :global(.mi-state) { margin: 10px 0 0 42px; }
        .mi :global(.mi-pill) { display: inline-flex; align-items: center; gap: 7px; font-size: 15px; line-height: 1.3; padding: 5px 12px; border-radius: 999px; }
        .mi :global(.mi-pill-new) { color: var(--text-dim, var(--muted)); background: color-mix(in srgb, var(--bg) 55%, transparent); }
        .mi :global(.mi-pill-wait) { color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
        .mi :global(.mi-pill-done) { color: #9cbf8a; background: rgba(122,158,110,0.14); }
        .mi :global(.mi-steps) { margin: 18px 0 0 42px; padding: 0 0 0 22px; font-size: 18px; line-height: 1.55; color: var(--text); }
        .mi :global(.mi-steps li) { padding-left: 6px; margin: 0 0 8px; }
        .mi :global(.mi-steps li::marker) { color: var(--accent); font-weight: 600; }
        .mi :global(.mi-steps a), .mi :global(.mi-link) { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; }
        .mi :global(.mi-sub) { margin: 14px 0 0 42px; font-size: 18px; line-height: 1.55; color: var(--text); opacity: 0.86; }
        .mi :global(.mi-note) { margin: 14px 0 0 42px; font-size: 17px; line-height: 1.5; color: var(--text); }
        .mi :global(.mi-bad) { color: #d99a8a; }
        .mi :global(.mi-actions) { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 18px; margin: 20px 0 0 42px; }
        .mi :global(.mi-done .mi-actions) { margin-top: 14px; }
        .mi :global(.mi-btn) {
          font: inherit; font-size: 18px; line-height: 1.2; min-height: 52px; padding: 0 24px; border-radius: 12px; cursor: pointer;
          color: var(--text); background: transparent; border: 1px solid color-mix(in srgb, var(--border) 50%, var(--text) 30%);
          transition: background-color 150ms ease-out, transform 120ms ease-out, border-color 150ms ease-out;
        }
        .mi :global(.mi-btn:hover:not(:disabled)) { background: color-mix(in srgb, var(--text) 7%, transparent); }
        .mi :global(.mi-btn:active:not(:disabled)) { transform: scale(0.98); }
        .mi :global(.mi-btn:disabled) { opacity: 0.6; cursor: default; }
        .mi :global(.mi-btn:focus-visible), .mi :global(.mi-link:focus-visible) { outline: 2px solid var(--accent); outline-offset: 3px; }
        .mi :global(.mi-primary) { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
        .mi :global(.mi-primary:hover:not(:disabled)) { background: color-mix(in srgb, var(--accent) 88%, var(--text) 12%); }
        .mi :global(.mi-link) { font-size: 16px; background: none; border: 0; padding: 0; cursor: pointer; font-family: inherit; }
        .mi :global(.mi-overlay) {
          position: absolute; inset: 0; border-radius: 18px; display: flex; align-items: center; justify-content: center; gap: 14px;
          font-size: 22px; color: var(--accent); background: color-mix(in srgb, var(--bg) 70%, transparent); border: 2px dashed var(--accent); pointer-events: none;
        }
        @media (max-width: 560px) {
          .mi :global(.mi-card) { padding: 20px 18px 20px; border-radius: 16px; }
          .mi :global(.mi-card.mi-done) { padding: 16px 18px; }
          .mi :global(.mi-title) { font-size: 21px; }
          .mi :global(.mi-state), .mi :global(.mi-steps), .mi :global(.mi-sub), .mi :global(.mi-note), .mi :global(.mi-actions) { margin-left: 0; }
          .mi :global(.mi-steps) { font-size: 17px; }
          .mi :global(.mi-btn) { width: 100%; }
        }
      `}</style>
    </div>
  )
}
