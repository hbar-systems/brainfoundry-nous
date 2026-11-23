// Connect this computer, the first card of moving in (SWITCH-1, 2026-11-16). The spoke of docs/spoke.md as one
// press for a person who has never opened Terminal: Get the file -> one app downloads -> open it, press Allow
// where the Mac asks. Then: Look at it (counts only) -> Bring what is on it (a yes in place) -> the brain mints
// the home's survey token and runs MOVE-IN-2's helper over the spoke; the plan shows in the card above it,
// the same as after the pasted line. Bridge: GET /cc/spoke/state, POST /cc/spoke/bundle, /look, /move-in,
// /disconnect, GET /cc/spoke/move-in. Rendered inside MoveInCards' .mi block, so its mi- styles apply.
// Words and the step logic: ui/lib/connectComputer.js.
import { useEffect, useState } from 'react'
import { spokeStep, osOf, fmtBytes, connectWords } from '../lib/connectComputer'

const API = '/api/bf'
const post = async (u, body) => {
  const r = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
  const j = await r.json().catch(() => ({}))
  return { ok: r.ok && j.ok !== false, j }
}

function Mark() {
  // a laptop, drawn in one stroke
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="5" y="6" width="18" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 22h22" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export default function ConnectComputer({ lang = 'en', onState }) {
  const T = connectWords(lang)
  const [st, setSt] = useState(null)          // GET /cc/spoke/state, null until read
  const [os, setOs] = useState('mac')
  const [made, setMade] = useState(null)      // { url, fingerprint, expires } after Get the file
  const [busy, setBusy] = useState('')        // '' | 'get' | 'look' | 'move' | 'disc'
  const [err, setErr] = useState('')
  const [looked, setLooked] = useState(null)  // { files, bytes }
  const [asking, setAsking] = useState('')    // '' | 'move' | 'disc'
  const [moving, setMoving] = useState(false)

  const load = async () => {
    const j = await fetch('/cc/spoke/state', { cache: 'no-store' }).then(r => (r.ok ? r.json() : { ready: false })).catch(() => ({ ready: false }))
    setSt(j)
    return j
  }
  useEffect(() => {
    if (typeof navigator !== 'undefined') { const o = osOf(navigator.userAgent); setOs(o === 'windows' ? 'windows' : o === 'phone' ? 'phone' : 'mac') }
    load()
  }, [])
  const step = spokeStep(st, { made: !!made, looked: !!looked, moving })
  useEffect(() => { if (onState) onState({ step, ready: !!(st && st.ready !== false) }) }, [step])
  // waiting for the computer to appear, or for the list: look again every few seconds
  useEffect(() => {
    if (!(step === 'made' || step === 'asleep' || step === 'moving')) return undefined
    const t = setInterval(async () => {
      await load()
      if (step === 'moving') {
        const m = await fetch('/cc/spoke/move-in', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
        if (m && m.ok && !m.running) setMoving(false)
      }
    }, step === 'made' ? 4000 : 8000)
    return () => clearInterval(t)
  }, [step])

  if (st === null) return null
  const fail = (j) => setErr((j && (j.error || j.detail)) || T.failed)

  const getFile = async () => {
    setBusy('get'); setErr('')
    try {
      const { ok, j } = await post('/cc/spoke/bundle')
      if (!ok) { fail(j); return }
      setMade(j)
      // the download starts by itself; the link stays for a second press
      const a = document.createElement('a'); a.href = j.url; a.download = ''; document.body.appendChild(a); a.click(); a.remove()
    } catch { fail(null) } finally { setBusy('') }
  }
  const look = async () => {
    setBusy('look'); setErr('')
    try {
      const { ok, j } = await post('/cc/spoke/look')
      if (!ok) { fail(j); return }
      setLooked({ files: j.files, bytes: j.bytes }); load()
    } catch { fail(null) } finally { setBusy('') }
  }
  const bring = async () => {
    setBusy('move'); setErr(''); setAsking('')
    try {
      // the same survey token the pasted line uses, minted by the home through the brain's own route
      const r = await fetch(`${API}/documents/import-laptop/token`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ survey: true }) })
      const t = await r.json().catch(() => ({}))
      if (!r.ok || !t.token) { fail(t); return }
      const { ok, j } = await post('/cc/spoke/move-in', { token: t.token })
      if (!ok) { fail(j); return }
      setMoving(true)
      if (onState) onState({ step: 'moving', ready: true, started: true })
    } catch { fail(null) } finally { setBusy('') }
  }
  const disconnect = async () => {
    setBusy('disc'); setErr(''); setAsking('')
    try {
      const { ok, j } = await post('/cc/spoke/disconnect')
      if (!ok) { fail(j); return }
      setMade(null); setLooked(null); load()
    } catch { fail(null) } finally { setBusy('') }
  }

  const lap = st.status && st.status.laptop
  const seen = lap && lap.seen ? (() => { try { return new Date(lap.seen).toLocaleString(lang === 'ru' ? 'ru-RU' : [], { dateStyle: 'medium', timeStyle: 'short' }) } catch { return '' } })() : ''
  const pill = { off: T.off, get: T.stGet, made: T.stMade, asleep: T.stAsleep, look: T.stHere, looked: T.stHere, moving: T.stMoving }[step]
  if (step === 'off') return null   // the paste card above does the same; a dead second card confused (MEMBERS-13 walk 2026-11-23)
  const tone = step === 'off' || step === 'get' ? 'new' : (step === 'look' || step === 'looked') ? 'done' : 'wait'
  const mac = os === 'mac'

  return (
    <section className={`mi-card${tone === 'done' ? ' mi-done' : ''}`} data-card="connect" data-step={step}>
      <div className="mi-head">
        <span className="mi-mark"><Mark /></span>
        <h2 className="mi-title">{T.title}</h2>
      </div>
      <div className="mi-state"><span className={`mi-pill mi-pill-${tone}`}>{pill}</span></div>

      {step === 'off' && <p className="mi-sub">{T.offSub}</p>}

      {(step === 'get' || step === 'made') && (
        <>
          <p className="mi-sub">{T.sub}</p>
          <div className="mi-chips" role="radiogroup" aria-label={T.title}>
            {[['mac', T.mac], ['windows', T.windows]].map(([k, n]) => (
              <button key={k} type="button" role="radio" aria-checked={os === k} className={`mi-chip${os === k ? ' mi-chip-on' : ''}`} onClick={() => setOs(k)}>{n}</button>
            ))}
          </div>
          {os === 'windows' && <p className="mi-sub">{T.win}</p>}
          {os === 'phone' && <p className="mi-sub">{T.phone}</p>}
          {mac && (
            <>
              <p className="mi-sub">{T.stepsHead}</p>
              <ol className="mi-steps">{T.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              <p className="mi-note mi-dim">{T.why}</p>
              {made && made.fingerprint && <p className="mi-note">{T.once(made.fingerprint)}</p>}
            </>
          )}
        </>
      )}

      {step === 'asleep' && <p className="mi-sub">{T.asleep(seen)}</p>}
      {(step === 'look' || step === 'looked') && <p className="mi-sub">{T.here}</p>}
      {step === 'looked' && (
        <p className="mi-sub">{T.looked(looked && looked.files, looked && looked.bytes != null ? fmtBytes(looked.bytes) : '')}{' '}
          <a className="mi-link" href="/cc/spoke/inventory" target="_blank" rel="noreferrer">{T.page}</a></p>
      )}
      {asking === 'move' && <p className="mi-note" role="alert">{T.ask}</p>}
      {asking === 'disc' && <p className="mi-note" role="alert">{T.discAsk}</p>}
      {step === 'moving' && <p className="mi-sub">{T.moving}</p>}
      {err && <p className="mi-note mi-bad" role="alert">{err}</p>}

      <div className="mi-actions">
        {(step === 'get' || step === 'made') && mac && (
          made
            ? <><a className="mi-btn mi-primary" href={made.url} download>{T.get}</a><button type="button" className="mi-btn" disabled={!!busy} onClick={getFile}>{T.again}</button></>
            : <button type="button" className="mi-btn mi-primary" disabled={!!busy} onClick={getFile}>{busy === 'get' ? T.getting : T.get}</button>
        )}
        {step === 'look' && !asking && <button type="button" className="mi-btn mi-primary" disabled={!!busy} onClick={look}>{busy === 'look' ? T.looking : T.look}</button>}
        {step === 'looked' && !asking && <button type="button" className="mi-btn mi-primary" disabled={!!busy} onClick={() => setAsking('move')}>{T.bring}</button>}
        {asking === 'move' && <><button type="button" className="mi-btn mi-primary" disabled={!!busy} onClick={bring}>{T.yes}</button><button type="button" className="mi-btn" onClick={() => setAsking('')}>{T.no}</button></>}
        {asking === 'disc' && <><button type="button" className="mi-btn mi-primary" disabled={!!busy} onClick={disconnect}>{T.discYes}</button><button type="button" className="mi-btn" onClick={() => setAsking('')}>{T.no}</button></>}
        {(step === 'look' || step === 'looked' || step === 'asleep') && !asking && <button type="button" className="mi-link" onClick={() => setAsking('disc')}>{T.disconnect}</button>}
      </div>
    </section>
  )
}
