// Moving in, on the quiet home (PARENTS-HOME-1 addendum 2, 2026-11-15; two doors since MOVE-IN-2,
// 2026-11-16: the chats from every AI with "Continue here", and the whole computer by survey). Two cards, first on the home
// until both are done: the ChatGPT (or Claude) export zip, and the person's documents. Each card is its
// own drop target, shows its state (not started / waiting for the email / N waiting for your yes /
// N moved in on <day>), and remembers through one press. The doors are the Knowledge page's own:
// POST /documents/import-chats, /api/permit + POST /documents/upload, POST /documents/approve-all.
// When both are in, the cards fold into one quiet line. Words and rules: ui/lib/moveIn.js.
import { useEffect, useRef, useState } from 'react'
import css from 'styled-jsx/css'
import { HOME_NEWEST, chatState, docState, folded, MOVE_WAIT_KEY, MOVE_DOCS_KEY, day, moveWords, importAnswer } from '../lib/moveIn'
import { defaultPicks, pickTotals, overCaps, pullState, surveyStep, fmtBytes, surveyCommands, helperCommands, agentUrls, vendorsOf, continueHref, planWords } from '../lib/moveInPlan'
import { AI_EXPORTS } from '../lib/aiExports'
import ConnectComputer from './ConnectComputer'

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

// Custom chips (never a native select): one row of choices, the chosen one inked.
function Chips({ items, value, onPick, label }) {
  return (
    <div className="mi-chips" role="radiogroup" aria-label={label}>
      {items.map(it => (
        <button key={it.key} type="button" role="radio" aria-checked={value === it.key}
          className={`mi-chip${value === it.key ? ' mi-chip-on' : ''}`} onClick={() => onPick(it.key)}>{it.name}</button>
      ))}
    </div>
  )
}

// A yes-or-no box drawn in the card's ink.
function Tick({ on }) {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="1.5" y="1.5" width="19" height="19" rx="5" stroke="currentColor" strokeWidth="1.5" fill={on ? 'currentColor' : 'none'} />
      {on && <path d="M6.5 11.2l3 3 6-6.4" stroke="var(--bg)" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />}
    </svg>
  )
}

const fmtClock = (s) => { try { return new Date(s * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' } }

// Door 1: bring in this computer, the member's main path (SPOKE-3). Start mints a survey token; the one line runs
// the dial-out agent from this brain (bash on a Mac, PowerShell on Windows, no Python, no app); the plan comes
// back grouped; one yes per group or all proposed; the same agent run pulls them, closes the key and is gone.
// Below the line, folded: the Python helper line (MOVE-IN-2) as the fallback. spoke (SWITCH-1): the Connect this
// computer card below this one is the advanced path; a run the spoke started has no window on the computer.
function WholeComputer({ lang, W, P, busy, onFiles, docBusy, docLine, remember, spoke }) {
  const [mint, setMint] = useState(null)        // null | { busy } | { token, expires_at } | { error }
  const [os, setOs] = useState('mac')
  const [copied, setCopied] = useState(false)
  const [st, setSt] = useState(null)            // GET /documents/import-laptop/status
  const [picks, setPicks] = useState(null)
  const [all, setAll] = useState(false)
  const [sending, setSending] = useState(null)  // null | 'busy' | { error }
  const base = typeof window === 'undefined' ? '' : `${window.location.origin}${API}`
  useEffect(() => { if (typeof navigator !== 'undefined' && /Windows/i.test(navigator.userAgent || '')) setOs('windows') }, [])
  const status = async () => {
    const j = await fetch(`${API}/documents/import-laptop/status`, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
    if (j) setSt(j)
    return j
  }
  useEffect(() => { status() }, [])
  const run = st && st.run
  const survey = st && st.survey
  const step = surveyStep(run, survey, !!(mint && mint.token))
  useEffect(() => {
    if (!(step === 'line' || step === 'plan' || step === 'pulling')) return undefined
    const t = setInterval(status, 3000)
    return () => clearInterval(t)
  }, [step])
  useEffect(() => { if (survey && survey.groups && picks === null) setPicks(defaultPicks(survey.groups)) }, [survey && survey.at])
  const start = async () => {
    setMint({ busy: true }); setCopied(false); setPicks(null)
    try {
      const r = await fetch(`${API}/documents/import-laptop/token`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ survey: true }) })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) { setMint({ error: j.detail || W.failed }); return }
      setMint({ token: j.token, expires_at: j.expires_at })
      status()
    } catch { setMint({ error: W.failed }) }
  }
  const cmd = mint && mint.token ? surveyCommands(base, mint.token, lang)[os] : ''
  const readUrl = base ? agentUrls(base, lang)[os] : ''
  const helperCmd = mint && mint.token ? helperCommands(base, mint.token)[os] : ''
  const groups = (survey && survey.groups) || []
  const t = pickTotals(groups, picks || {})
  const over = overCaps(t, run)
  const choose = async () => {
    setSending('busy')
    try {
      const take = t.proposed ? 'proposed' : groups.filter(g => picks && picks[g.id]).map(g => g.id)
      const r = await fetch(`${API}/documents/import-laptop/plan`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ take }) })
      const j = await r.json().catch(() => ({}))
      setSending(r.ok ? null : { error: j.detail || W.failed })
      status()
    } catch { setSending({ error: W.failed }) }
  }
  const pull = pullState(run, survey)
  const shown = all ? groups : groups.slice(0, 10)
  const viaSpoke = !!(spoke && spoke.started)
  const label = step === 'pulled' ? P.pulled(pull.docs, pull.kept) : step === 'pulling' ? (viaSpoke ? P.pullingSpoke(pull.done, pull.total) : P.pulling(pull.done, pull.total))
    : step === 'plan' ? P.compPlan(groups.length, groups.reduce((s, g) => s + g.files, 0), fmtBytes(groups.reduce((s, g) => s + g.bytes, 0)))
      : step === 'line' ? P.compWaiting : W.state.new
  return (
    <Card title={P.compTitle} state={label} tone={step === 'pulled' ? 'done' : step === 'start' ? 'new' : 'wait'} onFiles={onFiles} multiple busy={busy} dropLabel={W.dropHere}>
      {step === 'start' && (
        <>
          <p className="mi-sub">{P.compSub}</p>
          <p className="mi-sub">{P.compAgents}</p>
          <p className="mi-sub">{P.compNever}</p>
          <p className="mi-note mi-dim">{P.compNoApp}</p>
        </>
      )}
      {step === 'line' && mint && mint.token && (
        <div className="mi-line">
          <Chips items={[{ key: 'mac', name: 'Mac' }, { key: 'windows', name: 'Windows' }]} value={os} onPick={(k) => { setOs(k); setCopied(false) }} label="computer" />
          <p className="mi-sub">{os === 'mac' ? P.compMacHow : P.compWinHow}</p>
          <pre className="mi-cmd">{cmd}</pre>
          <p className="mi-note mi-dim">{P.compOnce(fmtClock(mint.expires_at))}</p>
          {os === 'mac' && <p className="mi-note mi-dim">{P.compMacAllow}</p>}
          <p className="mi-note mi-dim">{P.compNever}{' '}<a className="mi-link mi-read" href={readUrl} target="_blank" rel="noreferrer">{P.compRead}</a></p>
          <details className="mi-helper">
            <summary className="mi-link">{P.compHelper}</summary>
            <p className="mi-note mi-dim">{P.compHelperSub}</p>
            <pre className="mi-cmd">{helperCmd}</pre>
          </details>
        </div>
      )}
      {step === 'line' && !(mint && mint.token) && <p className="mi-sub">{P.compWaiting}</p>}
      {step === 'plan' && (
        <ul className="mi-groups">
          {shown.map(g => {
            const on = !!(picks && picks[g.id])
            return (
              <li key={g.id}>
                <button type="button" className={`mi-group${on ? ' mi-group-on' : ''}`} aria-pressed={on}
                  onClick={() => setPicks(p => ({ ...(p || {}), [g.id]: !on }))}>
                  <Tick on={on} />
                  <span className="mi-gname">{g.folder}</span>
                  <span className="mi-gmeta">{P.files(g.files)}, {fmtBytes(g.bytes)} · {g.proposal === 'leave' ? `${P.kind.leave}: ${P.why[g.why] || g.why}` : `${P.kind[g.kind]} (${P.why[g.why] || g.why})`}</span>
                </button>
              </li>
            )
          })}
          {groups.length > shown.length && (
            <li><button type="button" className="mi-link" onClick={() => setAll(true)}>{P.showAll(groups.length)}</button></li>
          )}
        </ul>
      )}
      {step === 'plan' && over && run && <p className="mi-note mi-bad" role="alert">{P.overCaps(run.max_files, fmtBytes(run.max_bytes))}</p>}
      {sending && sending.error && <p className="mi-note mi-bad" role="alert">{sending.error}</p>}
      {mint && mint.error && <p className="mi-note mi-bad" role="alert">{mint.error}</p>}
      {docBusy && docBusy.error && <p className="mi-note mi-bad" role="alert">{docBusy.error}</p>}
      <div className="mi-actions">
        {step === 'start' && (
          <button type="button" className="mi-btn mi-primary" disabled={!!(mint && mint.busy)} onClick={start}>{mint && mint.busy ? P.compStarting : P.compStart}</button>
        )}
        {step === 'line' && mint && mint.token && (
          <>
            <button type="button" className="mi-btn mi-primary" onClick={async () => { try { await navigator.clipboard.writeText(cmd); setCopied(true) } catch { setCopied(false) } }}>{copied ? P.compCopied : P.compCopy}</button>
            <button type="button" className="mi-btn" onClick={start}>{P.compNew}</button>
          </>
        )}
        {/* MEMBERS-13 walk: in another browser or after a reload the line is gone (the token is not shown twice); a new line, not a stuck wait */}
        {step === 'line' && !(mint && mint.token) && <button type="button" className="mi-btn mi-primary" onClick={start}>{P.compNew}</button>}
        {step === 'plan' && (
          <button type="button" className="mi-btn mi-primary" disabled={sending === 'busy' || !t.files || over} onClick={choose}>
            {t.proposed ? P.bringProposed(t.files, fmtBytes(t.bytes)) : P.bringChosen(t.files, fmtBytes(t.bytes))}
          </button>
        )}
        {docLine}
        {step === 'pulled' && <button type="button" className="mi-btn" onClick={start}>{P.compNew}</button>}
      </div>
      {(step === 'start' || step === 'pulled') && <p className="mi-note mi-dim">{P.compPhone} {P.dropOr}</p>}
    </Card>
  )
}

// Door 2: the chats from every AI. Pick where the export is (chips), drop the file as it came, or paste.
function AiChats({ lang, W, P, chat, chatBusy, approving, onFile, onPaste, remember, chatIds, onAsked }) {
  const [vendor, setVendor] = useState('chatgpt')
  const [paste, setPaste] = useState(null)   // null | text
  const input = useRef(null)
  const v = AI_EXPORTS.find(x => x.key === vendor) || AI_EXPORTS[0]
  const ap = approving && approving.which === 'chat'
  return (
    <Card title={P.chatsTitle} state={chat.step === 'done' ? W.state.chatDone(chat.n, day(lang, chat.at)) : chat.step === 'pending' ? W.state.pending(chat.waitingYes) : chat.step === 'waiting' ? W.state.waiting(day(lang, chat.at)) : W.state.new}
      tone={chat.step === 'done' ? 'done' : chat.step === 'new' ? 'new' : 'wait'} onFiles={onFile} busy={!!(chatBusy && chatBusy.reading) || ap} dropLabel={W.dropHere}>
      {chat.step !== 'pending' && (
        <>
          <p className="mi-sub">{P.chatsWhich}</p>
          <Chips items={AI_EXPORTS.map(x => (x.key === 'pasted' ? { ...x, name: P.otherAI } : x))} value={vendor}
            onPick={(k) => { setVendor(k); if (k === 'pasted' && paste === null) setPaste('') }} label={P.chatsWhich} />
          <p className="mi-sub">{v.steps[lang === 'ru' ? 'ru' : 'en']}{v.url && <>{' '}<a href={v.url} target="_blank" rel="noreferrer">{v.url.replace(/^https:\/\//, '')}</a></>}</p>
          {!v.verified && <p className="mi-note mi-dim">{P.chatsUnverified}</p>}
          <p className="mi-note mi-dim">{P.chatsDrop}</p>
        </>
      )}
      {chatBusy && chatBusy.found != null && <p className="mi-note">{W.chatFound(chatBusy.found, chatBusy.took)}</p>}
      {chatBusy && chatBusy.ignored && chatBusy.ignored.length > 0 && <p className="mi-note mi-dim">{W.chatIgnored(chatBusy.ignored.join(', '))}</p>}
      {chatBusy && chatBusy.error && <p className="mi-note mi-bad" role="alert">{chatBusy.error}</p>}
      {chatBusy && chatBusy.links && chatBusy.links.length > 0 && (
        <ul className="mi-links">
          {chatBusy.links.map(l => <li key={l.url}><a href={l.url} target="_blank" rel="noreferrer noopener">{l.name}</a></li>)}
        </ul>
      )}
      {chatBusy && chatBusy.noLink && <p className="mi-note mi-dim">{chatBusy.noLink}</p>}
      {paste !== null && (
        <div className="mi-paste">
          <textarea value={paste} onChange={e => setPaste(e.target.value)} placeholder={P.chatsPasteHint} rows={6} aria-label={P.chatsPasteHint} />
        </div>
      )}
      <div className="mi-actions">
        {chat.waitingYes > 0 ? (
          <button type="button" className="mi-btn mi-primary" disabled={!!approving} onClick={() => remember('chat', chatIds())}>
            {ap ? W.remembering(approving.done, approving.total) : W.remember(chat.waitingYes)}
          </button>
        ) : paste !== null ? (
          <button type="button" className="mi-btn mi-primary" disabled={!paste.trim() || !!(chatBusy && chatBusy.reading)} onClick={async () => { await onPaste(paste); setPaste(null) }}>{P.chatsPasteGo}</button>
        ) : (
          <button type="button" className="mi-btn mi-primary" disabled={!!(chatBusy && chatBusy.reading)} onClick={() => input.current && input.current.click()}>
            {chatBusy && chatBusy.reading ? W.chatReading(chatBusy.reading) : P.chatsPick}
          </button>
        )}
        {chat.step === 'new' && paste === null && <button type="button" className="mi-btn" onClick={onAsked}>{W.chatAsked}</button>}
        {paste === null && chat.waitingYes === 0 && <button type="button" className="mi-link" onClick={() => setPaste('')}>{P.chatsPaste}</button>}
        <input ref={input} type="file" accept=".zip,.json,.jsonl,.html,.htm,.csv,.txt,.md,.pdf,application/zip,application/json,text/html,text/csv,text/plain,application/pdf" hidden
          onChange={(e) => { const f = Array.from(e.target.files || []); e.target.value = ''; onFile(f) }} />
      </div>
      <p className="mi-note mi-dim">{P.chatsSeat}</p>
    </Card>
  )
}

// "Your chats from ChatGPT and Claude": every imported conversation with Continue here.
function ChatList({ lang, P, rows }) {
  const [all, setAll] = useState(false)
  if (!rows || !rows.length) return null
  const shown = all ? rows : rows.slice(0, 6)
  return (
    <section className="mi-list" aria-label={P.listTitle(vendorsOf(rows))}>
      <h2 className="mi-list-title">{P.listTitle(vendorsOf(rows))}</h2>
      <ul>
        {shown.map(r => (
          <li key={r.name} className="mi-chat">
            <div className="mi-chat-text">
              <span className="mi-chat-title">{r.title || r.name}</span>
              <span className="mi-chat-meta">{[r.vendor, day(lang, r.last_at || r.started), r.turns ? P.turns(r.turns) : null, r.state === 'waiting' ? P.waitingYes : null].filter(Boolean).join(' · ')}</span>
            </div>
            <a className="mi-btn mi-cont" href={continueHref(r.name, lang)}>{P.cont}</a>
          </li>
        ))}
      </ul>
      {rows.length > shown.length && <button type="button" className="mi-link" onClick={() => setAll(true)}>{P.showAll(rows.length)}</button>}
    </section>
  )
}

export default function MoveInCards({ lang = 'en', onMoved }) {
  const W = moveWords(lang)
  const P = planWords(lang)
  const [docs, setDocs] = useState(null)        // GET /documents rows, null until read
  const [pending, setPending] = useState([])    // [{ proposal_id, filename }]
  const [asked, setAsked] = useState(null)
  const [docMark, setDocMark] = useState(null)
  const [chatBusy, setChatBusy] = useState(null) // null | { reading } | { found, took } | { error }
  const [docBusy, setDocBusy] = useState(null)   // null | { i, n } | { error }
  const [approving, setApproving] = useState(null) // null | { which, done, total }
  const [reopen, setReopen] = useState(false)
  const [chats, setChats] = useState([])        // GET /documents/chats rows
  const [spoke, setSpoke] = useState(null)      // the Connect this computer card's { step, ready, started }

  const load = async () => {
    const j = (u) => fetch(u, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
    const [d, p, c] = await Promise.all([j(`${API}/documents?limit=10000`), j(`${API}/memory/proposals?status=PENDING&limit=1000`), j(`${API}/documents/chats`)])
    setDocs(d && Array.isArray(d.documents) ? d.documents : [])
    const items = p && Array.isArray(p.proposals) ? p.proposals : []
    setPending(items.filter(x => x.memory_type === 'document_embedding' && x.proposal_id)
      .map(x => ({ proposal_id: x.proposal_id, filename: (x.source_refs && x.source_refs.filename) || '' })))
    setChats(c && Array.isArray(c.chats) ? c.chats : [])
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

  // any AI's export as it came (zip, json, html, csv), or pasted text: the import detects which
  const importChats = async (files, text) => {
    const f = files && files[0]
    if (!f && !text) return
    setChatBusy({ reading: f ? f.name : '...' })
    const fd = new FormData()
    if (f) fd.append('file', f); else fd.append('text', text)
    fd.append('newest', String(HOME_NEWEST))
    try {
      const r = await fetch(`${API}/documents/import-chats`, { method: 'POST', body: fd })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) { const a = importAnswer(j, W); setChatBusy({ error: a.message, links: a.links, noLink: a.noLink }); return }
      setChatBusy({ found: j.conversations || 0, took: j.selected || 0, ignored: j.ignored || [] })
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
      const failed = []
      for (let i = 0; i < files.length; i++) {
        setDocBusy({ i: i + 1, n: files.length })
        const fd = new FormData()
        fd.append('file', files[i])
        fd.append('permit_id', permit_id)
        const r = await fetch(`${API}/documents/upload`, { method: 'POST', body: fd }).catch(() => null)
        if (!r || !r.ok) failed.push(files[i].name)
      }
      setDocBusy(failed.length ? { error: W.docFailed(failed.slice(0, 3).join(', ') + (failed.length > 3 ? ` +${failed.length - 3}` : '')) } : null)
      await load()
    } catch { setDocBusy({ error: W.failed }) }
  }

  if (docs === null) return null
  const list = <ChatList lang={lang} P={P} rows={chats} />
  if (folded(chat, doc) && !reopen) {
    return (
      <div className="mi">
        <p className="mi-folded" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', margin: '8px 0 8px', fontSize: '16px', color: 'var(--text-dim, var(--muted))' }}>
          <span style={{ color: '#9cbf8a', display: 'inline-flex' }}><DoneMark /></span> <span>{W.folded(chat.n, doc.n)}</span>{' '}
          <button type="button" onClick={() => setReopen(true)}
            style={{ color: 'var(--accent)', background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit', textDecoration: 'underline', textUnderlineOffset: '3px' }}>{W.foldedMore}</button>
        </p>
        {list}
        <style jsx>{miStyles}</style>
      </div>
    )
  }

  const ap = (which) => approving && approving.which === which
  const docLine = doc.waitingYes > 0 ? (
    <button type="button" className="mi-btn mi-primary" disabled={!!approving} onClick={() => remember('doc', docIds())}>
      {ap('doc') ? W.remembering(approving.done, approving.total) : W.remember(doc.waitingYes)}
    </button>
  ) : (docBusy && docBusy.n ? <span className="mi-note">{W.docSending(docBusy.i, docBusy.n)}</span> : null)

  return (
    <div className="mi">
      <WholeComputer lang={lang} W={W} P={P} busy={!!(docBusy && docBusy.n) || ap('doc')} onFiles={sendDocs}
        docBusy={docBusy} docLine={docLine} remember={remember} spoke={spoke} />
      <ConnectComputer lang={lang} onState={(x) => setSpoke(s => ({ ...(s || {}), ...x, started: !!((s && s.started) || x.started) }))} />
      <AiChats lang={lang} W={W} P={P} chat={chat} chatBusy={chatBusy} approving={approving}
        onFile={(fs) => importChats(fs, null)} onPaste={(t) => importChats(null, t)} remember={remember} chatIds={chatIds}
        onAsked={() => { const d = todayIso(); ls.set(MOVE_WAIT_KEY, d); setAsked(d) }} />
      {list}
      <style jsx>{miStyles}</style>
    </div>
  )
}

const miStyles = css`
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
        .mi :global(.mi-links) { margin: 8px 0 0 42px; padding: 0; list-style: none; font-size: 17px; line-height: 1.7; }
        .mi :global(.mi-links a) { color: var(--text); text-decoration: underline; text-underline-offset: 3px; overflow-wrap: anywhere; }
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
          .mi :global(.mi-state), .mi :global(.mi-steps), .mi :global(.mi-sub), .mi :global(.mi-note), .mi :global(.mi-links), .mi :global(.mi-actions) { margin-left: 0; }
          .mi :global(.mi-steps) { font-size: 17px; }
          .mi :global(.mi-btn) { width: 100%; }
        }
      
        .mi :global(.mi-sub a) { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; overflow-wrap: anywhere; }
        .mi :global(.mi-dim) { opacity: 0.72; font-size: 16px; }
        .mi :global(.mi-chips) { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 0 42px; }
        .mi :global(.mi-chip) { font: inherit; font-size: 16px; min-height: 40px; padding: 0 16px; border-radius: 999px; cursor: pointer; color: var(--text); background: transparent; border: 1px solid color-mix(in srgb, var(--border) 50%, var(--text) 25%); transition: background-color 150ms ease-out, border-color 150ms ease-out; }
        .mi :global(.mi-chip:hover) { background: color-mix(in srgb, var(--text) 7%, transparent); }
        .mi :global(.mi-chip-on) { color: var(--bg); background: var(--accent); border-color: var(--accent); }
        .mi :global(.mi-chip:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
        .mi :global(.mi-helper) { margin: 12px 0 0; }
        .mi :global(.mi-helper > summary) { list-style: none; cursor: pointer; }
        .mi :global(.mi-helper > summary::-webkit-details-marker) { display: none; }
        .mi :global(.mi-helper .mi-cmd), .mi :global(.mi-helper .mi-note) { margin-left: 0; }
        .mi :global(.mi-cmd) { margin: 12px 0 0 42px; padding: 14px 16px; border-radius: 12px; white-space: pre-wrap; word-break: break-all; font-family: var(--font-mono, ui-monospace, monospace); font-size: 14px; line-height: 1.5; color: var(--text); background: color-mix(in srgb, var(--bg) 70%, transparent); border: 1px solid var(--border); }
        .mi :global(.mi-groups) { list-style: none; margin: 16px 0 0 42px; padding: 0; display: grid; gap: 8px; }
        .mi :global(.mi-group) { width: 100%; display: grid; grid-template-columns: auto 1fr; column-gap: 12px; row-gap: 2px; align-items: center; text-align: left; font: inherit; padding: 12px 14px; border-radius: 12px; cursor: pointer; color: var(--text-dim, var(--muted)); background: transparent; border: 1px solid var(--border); transition: border-color 150ms ease-out, background-color 150ms ease-out; }
        .mi :global(.mi-group-on) { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 55%, var(--border)); background: color-mix(in srgb, var(--accent) 7%, transparent); }
        .mi :global(.mi-gname) { color: var(--text); font-size: 17px; overflow-wrap: anywhere; }
        .mi :global(.mi-gmeta) { grid-column: 2; font-size: 15px; color: var(--text-dim, var(--muted)); }
        .mi :global(.mi-paste textarea) { box-sizing: border-box; width: calc(100% - 42px); margin: 14px 0 0 42px; padding: 12px 14px; border-radius: 12px; font: inherit; font-size: 16px; color: var(--text); background: color-mix(in srgb, var(--bg) 70%, transparent); border: 1px solid var(--border); resize: vertical; }
        .mi :global(.mi-list) { margin: 6px 0 0; }
        .mi :global(.mi-list-title) { margin: 0 0 10px; font-family: var(--font-display); font-weight: 400; font-size: 19px; color: var(--text); }
        .mi :global(.mi-list ul) { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
        .mi :global(.mi-chat) { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 16px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); }
        .mi :global(.mi-chat-text) { min-width: 0; display: grid; gap: 2px; }
        .mi :global(.mi-chat-title) { font-size: 17px; color: var(--text); overflow-wrap: anywhere; }
        .mi :global(.mi-chat-meta) { font-size: 14px; color: var(--text-dim, var(--muted)); }
        .mi :global(.mi-cont) { display: inline-flex; align-items: center; flex-shrink: 0; min-height: 44px; font-size: 16px; text-decoration: none; }
        @media (max-width: 560px) {
          .mi :global(.mi-chips), .mi :global(.mi-cmd), .mi :global(.mi-groups) { margin-left: 0; }
          .mi :global(.mi-paste textarea) { width: 100%; margin-left: 0; }
          .mi :global(.mi-chat) { flex-direction: column; align-items: stretch; }
          .mi :global(.mi-cont) { justify-content: center; width: auto; }
        }
`
