// The sign-in screen for a person who has never seen a terminal (MEMBERS-14 2026-11-23). MEMBERS-13 measured the old
// card at 45% alone on a laptop and 10% on a phone: an API-key box first, a full terminal beside it, English only.
// Now: one screen in the console language, three numbered steps with one button each.
//   1 Open the sign-in page: the link Claude Code's own `claude auth login` printed in the door below
//     (GET /cc/login/door-url, the link only); until it is there, the door's own link is the way.
//   2 Paste the code: focuses the dark box, which is the terminal door running Claude Code itself; the code is
//     typed there and never passes through this page (ops/legal/claude-code-terms-2026-09-19.md, point 3).
//   3 Done: this page looks every few seconds and goes on by itself; a start pressed before runs then.
// The other doors (an API key, ChatGPT) stay one press away, under "Other ways to sign in".
import { useEffect, useRef, useState } from 'react'
import { signinWords, shortStart } from '../lib/signinText'

export default function SignInSteps({ lang = 'en', bare, loggedIn, onRecheck, pendingStart, other }) {
  const T = signinWords(lang)
  const [url, setUrl] = useState(null)
  const [waited, setWaited] = useState(0)
  const [opened, setOpened] = useState(false)
  const [pasting, setPasting] = useState(false)
  const [round, setRound] = useState(0)
  const [showOther, setShowOther] = useState(false)
  const box = useRef(null)
  const wrap = useRef(null)

  // the door's link: asked every 1.5 s until it is there (a new round asks again)
  useEffect(() => {
    let on = true, n = 0
    setUrl(null); setWaited(0)
    const ask = () => fetch('/cc/login/door-url', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
      if (!on) return
      if (d && typeof d.url === 'string' && /^https:\/\//.test(d.url)) { setUrl(d.url); clearInterval(t) } else setWaited(++n)
    }).catch(() => { if (on) setWaited(++n) })
    const t = setInterval(ask, 1500)
    setTimeout(ask, 600)
    return () => { on = false; clearInterval(t) }
  }, [round])
  // step 3 looks by itself: a fresh sign-in check every 4 s once the page was opened, every 10 s before
  useEffect(() => {
    if (loggedIn || !onRecheck) return
    const t = setInterval(() => onRecheck(), opened ? 4000 : 10000)
    return () => clearInterval(t)
  }, [loggedIn, opened, onRecheck])
  // a start pressed before the sign-in brings this screen into view
  useEffect(() => { if (pendingStart && wrap.current) { try { wrap.current.scrollIntoView({ behavior: 'smooth', block: 'start' }) } catch {} } }, [pendingStart])

  const focusBox = () => {
    setPasting(true)
    const f = box.current
    if (!f) return
    try { f.scrollIntoView({ behavior: 'smooth', block: 'center' }) } catch {}
    try {
      // same origin (/claude/ behind the same login): only focus is set; nothing is read from the door
      const ta = f.contentWindow && f.contentWindow.document.querySelector('textarea')
      if (ta) ta.focus(); else f.focus()
    } catch { try { f.focus() } catch {} }
  }
  const again = () => { setOpened(false); setPasting(false); setRound(r => r + 1) }
  const noLink = !url && waited >= 6
  const now = loggedIn ? 3 : pasting ? 3 : opened ? 2 : 1

  return (
    <section className="si" ref={wrap} data-signin-steps={now} aria-label={T.head}>
      {!bare && <h2 className="si-head">{T.head}</h2>}
      {pendingStart && <p className="si-pending" data-pending-start>{T.pending(shortStart(pendingStart))}</p>}
      <ol className="si-steps">
        <li className={`si-step${now === 1 ? ' si-now' : ''}${opened ? ' si-done' : ''}`}>
          <span className="si-n">{opened ? '✓' : 1}</span>
          <div className="si-body">
            {url ? (
              <a className="si-btn si-primary" href={url} target="_blank" rel="noreferrer" onClick={() => setOpened(true)}>{T.s1}</a>
            ) : noLink ? (
              <button type="button" className="si-btn si-primary" onClick={() => { setOpened(true); focusBox(); setPasting(false) }}>{T.s1}</button>
            ) : (
              <button type="button" className="si-btn si-primary" disabled>{T.s1wait}</button>
            )}
            <p className="si-sub">{noLink ? T.s1box : T.s1sub}</p>
          </div>
        </li>
        <li className={`si-step${now === 2 ? ' si-now' : ''}${pasting ? ' si-done' : ''}`}>
          <span className="si-n">{pasting ? '✓' : 2}</span>
          <div className="si-body">
            <button type="button" className={`si-btn${now === 2 ? ' si-primary' : ''}`} onClick={focusBox}>{T.s2btn}</button>
            <p className="si-sub">{T.s2sub}</p>
          </div>
        </li>
        <li className={`si-step${now === 3 ? ' si-now' : ''}${loggedIn ? ' si-done' : ''}`}>
          <span className="si-n">{loggedIn ? '✓' : 3}</span>
          <div className="si-body">
            <p className="si-title">{T.s3}{loggedIn ? '' : <span className="si-wait"> · {T.s3wait}</span>}</p>
            <p className="si-sub">{loggedIn ? T.s3ok : T.s3sub}</p>
          </div>
        </li>
      </ol>
      <div className="si-boxwrap">
        <p className="si-boxlabel">{T.box}</p>
        <iframe key={round} ref={box} className="si-box" title={T.box} src={`/claude/?arg=login&arg=${encodeURIComponent(lang)}`} />
      </div>
      <p className="si-phone">{T.phone}</p>
      <div className="si-more">
        <button type="button" className="si-link" onClick={again}>{T.again}</button>
        {other ? <button type="button" className="si-link" aria-expanded={showOther} onClick={() => setShowOther(o => !o)}>{T.other} {showOther ? '▴' : '▾'}</button> : null}
      </div>
      {showOther && other}
      <style jsx>{`
        .si { margin: 4px 0 24px; max-width: 46em; }
        .si-head { margin: 0 0 12px; font-family: var(--font-display); font-weight: 600; font-size: 24px; color: var(--text); }
        .si-pending { margin: 0 0 14px; padding: 12px 14px; border-left: 2px solid var(--accent); font-size: 16px; line-height: 1.5; color: var(--text); overflow-wrap: anywhere; }
        .si-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
        .si-step { display: flex; gap: 14px; align-items: flex-start; padding: 14px 16px; border: 1px solid var(--border); border-radius: 14px; opacity: 0.72; }
        .si-now { opacity: 1; border-color: var(--text); }
        .si-done { opacity: 0.85; }
        .si-n { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 999px; border: 1px solid var(--border); font-family: var(--font-mono, ui-monospace, monospace); font-size: 14px; color: var(--text); }
        .si-done .si-n { border-color: #9cbf8a; color: #9cbf8a; }
        .si-body { flex: 1 1 auto; min-width: 0; }
        .si-title { margin: 4px 0 2px; font-size: 18px; font-weight: 600; color: var(--text); }
        .si-wait { font-weight: 400; color: var(--text-dim, var(--muted)); font-size: 15px; }
        .si-sub { margin: 8px 0 0; font-size: 16px; line-height: 1.5; color: var(--text-dim, var(--muted)); }
        .si-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 52px; padding: 0 22px; border-radius: 12px; font: inherit; font-size: 18px; line-height: 1.2;
          cursor: pointer; background: transparent; color: var(--text); border: 1px solid var(--border); text-decoration: none; max-width: 100%; text-align: center; }
        .si-primary { background: var(--text); color: var(--bg); border-color: var(--text); }
        .si-btn:disabled { opacity: 0.6; cursor: default; }
        .si-btn:focus-visible, .si-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
        .si-boxwrap { margin: 14px 0 0; }
        .si-boxlabel { margin: 0 0 6px; font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim, var(--muted)); }
        .si-box { display: block; width: 100%; height: 200px; border: 1px solid var(--border); border-radius: 12px; background: #0f0e0c; }
        .si-phone { margin: 12px 0 0; font-size: 15px; line-height: 1.5; color: var(--text-dim, var(--muted)); }
        .si-more { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 10px 0 0; }
        .si-link { font: inherit; font-size: 15px; background: none; border: none; padding: 6px 0; color: var(--text-dim, var(--muted)); text-decoration: underline; cursor: pointer; }
        @media (max-width: 520px) { .si-step { padding: 12px; gap: 10px; } .si-btn { width: 100%; } .si-box { height: 230px; } }
      `}</style>
    </section>
  )
}
