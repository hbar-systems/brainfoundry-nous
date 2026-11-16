// The first sign-in order on a member brain's quiet home (SWITCH-1, 2026-11-16), once, then never again:
// sign in (the seat), the ways of working (the surfaces pick-list), move in (connect this computer, bring AI
// chats), the quiet home. Each step has Skip; the state is the bridge's (GET/POST /cc/first-run). The seat's own
// sign-in panel stays the console's SignIn (rendered by cc.js above this while no seat is signed in); this adds
// the step's words and the honest line about the shared small model. Words and logic: ui/lib/firstRun.js.
import { useEffect, useState } from 'react'
import MoveInCards from './MoveInCards'
import { ORDER, currentStep, startPicks, togglePick, firstWords } from '../lib/firstRun'

const post = (u, body) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
  .then(r => (r.ok ? r.json() : null)).catch(() => null)

function Ways({ lang, F, onDone, onSkip }) {
  const [d, setD] = useState(null)       // GET /cc/layout
  const [picks, setPicks] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    fetch('/cc/layout', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null).then(j => {
      setD(j || {})
      const q = j && (j.questions || []).find(x => x.id === 'surfaces')
      setPicks(startPicks(j && j.layout, q ? q.options.map(o => o[0]) : []))
    })
  }, [])
  if (!d) return null
  const q = (d.questions || []).find(x => x.id === 'surfaces')
  const all = q ? q.options.map(o => o[0]) : []
  const keep = async () => {
    setBusy(true)
    if (q && picks) {
      // the layout page's own save (ui/pages/layout.js applySurf): the saved layout with this one key changed
      const base = JSON.parse(JSON.stringify(d.layout || d.default || {}))
      base.surfaces = picks
      const answers = { ...(d.answers || {}), surfaces: picks }
      await post('/cc/layout/save', { layout: base, answers })
    }
    setBusy(false); onDone()
  }
  return (
    <>
      <h2 className="fr-title">{F.waysTitle}</h2>
      <p className="fr-sub">{F.waysSub}</p>
      <ul className="fr-ways">
        {(q ? q.options : []).map(([v, name]) => {
          const on = !!(picks && picks.includes(v))
          const ru = lang === 'ru' && F.about[v]
          const about = ru ? ru[1] : ((q.about && q.about[v]) || '')
          return (
            <li key={v}>
              <button type="button" className={`fr-way${on ? ' fr-way-on' : ''}`} aria-pressed={on} disabled={v === 'chat'}
                onClick={() => setPicks(p => togglePick(p || [], v, all))}>
                <span className="fr-box" aria-hidden="true">{on ? '●' : '○'}</span>
                <span className="fr-wname">{ru ? ru[0] : name}{v === 'chat' ? <span className="fr-dim"> · {F.waysAlways}</span> : null}</span>
                <span className="fr-wabout">{about}</span>
              </button>
            </li>
          )
        })}
      </ul>
      <div className="fr-actions">
        <button type="button" className="fr-btn fr-primary" disabled={busy} onClick={keep}>{F.waysKeep}</button>
        <button type="button" className="fr-btn" onClick={onSkip}>{F.skip}</button>
      </div>
    </>
  )
}

export default function FirstRun({ lang = 'en', state, loggedIn, onChange }) {
  const F = firstWords(lang)
  const step = currentStep(state, loggedIn)
  const mark = async (k, how) => { const j = await post('/cc/first-run', { step: k, state: how }); if (j && onChange) onChange(j) }
  // a seat signed in (here or in another tab) is the first step done
  useEffect(() => { if (state && loggedIn && !(state.steps || {}).seat) mark('seat', 'done') }, [loggedIn, state && (state.steps || {}).seat])
  if (!step) return null
  const n = ORDER.indexOf(step) + 1
  const s = (state && state.steps) || {}
  return (
    <div className="fr" data-first-run={step}>
      <ol className="fr-dots" aria-label={F.stepOf(n)}>
        {ORDER.map((k, i) => {
          const done = k === 'seat' && loggedIn ? 'done' : s[k]
          return (
            <li key={k} className={`fr-dot${k === step ? ' fr-now' : ''}${done ? ' fr-' + done : ''}`} aria-current={k === step ? 'step' : undefined}>
              <span className="fr-n">{done === 'done' ? '✓' : i + 1}</span><span className="fr-dname">{F.names[k]}</span>
            </li>
          )
        })}
      </ol>
      <p className="fr-of">{F.stepOf(n)}</p>

      {step === 'seat' && (
        <>
          <h2 className="fr-title">{F.seatTitle}</h2>
          <p className="fr-sub">{F.seatSub}</p>
          <p className="fr-note">{F.seatLocal}</p>
          <div className="fr-actions"><button type="button" className="fr-btn" onClick={() => mark('seat', 'skipped')}>{F.skip}</button></div>
        </>
      )}
      {step === 'ways' && <Ways lang={lang} F={F} onDone={() => mark('ways', 'done')} onSkip={() => mark('ways', 'skipped')} />}
      {step === 'movein' && (
        <>
          <h2 className="fr-title">{F.moveTitle}</h2>
          <p className="fr-sub">{F.moveSub}</p>
          <MoveInCards lang={lang} />
          <div className="fr-actions">
            <button type="button" className="fr-btn fr-primary" onClick={() => mark('movein', 'done')}>{F.moveDone}</button>
            <button type="button" className="fr-btn" onClick={() => mark('movein', 'skipped')}>{F.skip}</button>
          </div>
        </>
      )}
      {step === 'home' && (
        <>
          <h2 className="fr-title">{F.homeTitle}</h2>
          <p className="fr-sub">{F.homeSub}</p>
          <div className="fr-actions"><button type="button" className="fr-btn fr-primary" onClick={() => mark('home', 'done')}>{F.homeGo}</button></div>
        </>
      )}
      <style jsx>{`
        .fr { margin: 8px 0 28px; }
        .fr :global(.fr-dots) { list-style: none; display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 0 0 6px; padding: 0; }
        .fr :global(.fr-dot) { display: inline-flex; align-items: center; gap: 8px; font-size: 15px; color: var(--text-dim, var(--muted)); opacity: 0.7; }
        .fr :global(.fr-dot.fr-now) { color: var(--text); opacity: 1; }
        .fr :global(.fr-dot.fr-done) { opacity: 0.85; }
        .fr :global(.fr-n) { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 999px; border: 1px solid var(--border); font-family: var(--font-mono, ui-monospace, monospace); font-size: 12px; }
        .fr :global(.fr-now .fr-n) { border-color: var(--text); }
        .fr :global(.fr-done .fr-n) { border-color: #9cbf8a; color: #9cbf8a; }
        .fr :global(.fr-of) { margin: 10px 0 4px; font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; color: var(--text-dim, var(--muted)); }
        .fr :global(.fr-title) { margin: 6px 0 8px; font-family: var(--font-display); font-weight: 600; font-size: 26px; line-height: 1.25; color: var(--text); text-wrap: balance; }
        .fr :global(.fr-sub) { margin: 0 0 12px; font-size: 18px; line-height: 1.55; color: var(--text); opacity: 0.88; max-width: 44em; }
        .fr :global(.fr-note) { margin: 0 0 12px; font-size: 16px; line-height: 1.5; color: var(--text-dim, var(--muted)); max-width: 44em; padding: 12px 14px; border-left: 2px solid var(--border); }
        .fr :global(.fr-dim) { color: var(--text-dim, var(--muted)); font-size: 14px; }
        .fr :global(.fr-ways) { list-style: none; margin: 0 0 6px; padding: 0; display: grid; gap: 8px; }
        .fr :global(.fr-way) { width: 100%; text-align: left; display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; padding: 14px 16px; border-radius: 14px; cursor: pointer;
          background: var(--surface, transparent); color: var(--text); border: 1px solid var(--border); font: inherit; opacity: 0.75; }
        .fr :global(.fr-way-on) { border-color: var(--text); opacity: 1; }
        .fr :global(.fr-way:disabled) { cursor: default; }
        .fr :global(.fr-way:focus-visible), .fr :global(.fr-btn:focus-visible) { outline: 2px solid var(--accent); outline-offset: 3px; }
        .fr :global(.fr-box) { font-size: 14px; width: 1em; }
        .fr :global(.fr-wname) { font-size: 18px; min-width: 10em; }
        .fr :global(.fr-wabout) { font-size: 15px; line-height: 1.45; color: var(--text-dim, var(--muted)); flex: 1 1 16em; min-width: 0; }
        .fr :global(.fr-actions) { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0 0; }
        .fr :global(.fr-btn) { font: inherit; font-size: 18px; line-height: 1.2; min-height: 52px; padding: 0 24px; border-radius: 12px; cursor: pointer; background: transparent; color: var(--text); border: 1px solid var(--border); }
        .fr :global(.fr-primary) { background: var(--text); color: var(--bg); border-color: var(--text); }
        .fr :global(.fr-btn:disabled) { opacity: 0.5; cursor: default; }
      `}</style>
    </div>
  )
}
