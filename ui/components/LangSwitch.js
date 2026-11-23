// The language switch (MEMBERS-14 2026-11-23, hbar: "all the brains should have in their own language and somewhere
// an opportunity to choose English"). Two chips in the top bar, the same place on every screen: the member's own
// language and English, the current one marked. Shown only when the console has a language of its own
// (GET /cc/layout lang_home). A press sets the console language (POST /cc/layout/lang) and reloads the page.
import { useEffect, useState } from 'react'
import { NATIVE } from '../lib/consoleText'

export default function LangSwitch() {
  const [st, setSt] = useState(null)   // { lang, home }
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let on = true
    fetch('/cc/layout', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => {
      if (on && d && d.lang_home && NATIVE[d.lang_home]) setSt({ lang: d.lang || 'en', home: d.lang_home })
    }).catch(() => {})
    return () => { on = false }
  }, [])
  if (!st) return null
  const pick = async (l) => {
    if (busy || l === st.lang) return
    setBusy(true)
    try {
      const r = await fetch('/cc/layout/lang', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang: l }) })
      if (r.ok) { window.location.reload(); return }
    } catch {}
    setBusy(false)
  }
  return (
    <div className="bf-lang" role="group" aria-label={`${NATIVE[st.home]} / English`} data-lang-switch={st.lang}>
      {[st.home, 'en'].map(l => (
        <button key={l} type="button" lang={l} aria-pressed={st.lang === l} disabled={busy}
          className={`bf-lang-chip${st.lang === l ? ' bf-lang-on' : ''}`} onClick={() => pick(l)}>{NATIVE[l]}</button>
      ))}
      <style jsx>{`
        .bf-lang { display: inline-flex; gap: 4px; margin: 0 10px 0 0; flex-shrink: 0; }
        .bf-lang-chip { font: inherit; font-size: 12px; line-height: 1; padding: 6px 10px; border-radius: 999px; cursor: pointer; white-space: nowrap;
          background: transparent; color: var(--muted); border: 1px solid var(--border); }
        .bf-lang-on { color: var(--text); border-color: var(--text); }
        .bf-lang-chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
        @media (max-width: 420px) { .bf-lang-chip { padding: 6px 8px; font-size: 11px; } }
      `}</style>
    </div>
  )
}
