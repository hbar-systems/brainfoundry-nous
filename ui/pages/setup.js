// The setup period, the member's own screen (STEWARD-1, 2026-11-27; docs/STEWARD.md).
// While the helper works: until when, the last thing it did, one Done press that ends it now.
// After it: the guided screen for the member's own new console password (the api keeps a hash only;
// the switch on the box is the operator's press). No token, command or path is ever shown here.
import Head from 'next/head'
import { useEffect, useState } from 'react'

const API = '/api/bf'

const WORDS = {
  en: {
    title: 'Setup',
    working: (d) => `Your setup helper is finishing your move-in, until ${d}.`,
    sees: 'It sees counts, never your files or chats. It cannot change your words or delete what you kept.',
    last: 'Last',
    nothing: 'Nothing done yet.',
    done: 'Done, stop the helper now',
    sure: 'Stop it now? Anything still reading carries on by itself.',
    yes: 'Stop it', no: 'Keep it',
    ended: 'The setup helper has finished. Your brain is yours.',
    never: 'No setup helper is working on this brain.',
    letIn: 'Let the helper finish my setup',
    pwTitle: 'Choose your password',
    pwSub: 'Only you will know it. Ten characters or more.',
    pw: 'New password', again: 'The same again',
    save: 'Save', saving: 'Saving...',
    saved: 'Saved. It takes over when hbar switches it on; until then your old password still works.',
    chosen: 'Your new password is chosen. It takes over when hbar switches it on.',
    differ: 'The two are not the same.',
    failed: 'That did not work. Try again in a minute.',
    actions: { 'key minted': 'started', 'cleared copies': 'cleared copies that came twice', 'reading what the person chose': 'started reading what you chose', 'setup ended': 'finished', 'new console password chosen': 'you chose a new password' },
  },
  de: {
    title: 'Einrichtung',
    working: (d) => `Dein Einrichtungshelfer macht deinen Umzug fertig, bis ${d}.`,
    sees: 'Er sieht nur Zahlen, nie deine Dateien oder Chats. Er kann deine Worte nicht ändern und nichts löschen, was du behalten hast.',
    last: 'Zuletzt',
    nothing: 'Noch nichts getan.',
    done: 'Fertig, Helfer jetzt beenden',
    sure: 'Jetzt beenden? Was noch eingelesen wird, läuft von selbst weiter.',
    yes: 'Beenden', no: 'Weiterlaufen lassen',
    ended: 'Der Einrichtungshelfer ist fertig. Dein Gehirn gehört dir.',
    never: 'Auf diesem Gehirn arbeitet kein Einrichtungshelfer.',
    letIn: 'Den Helfer meine Einrichtung fertig machen lassen',
    pwTitle: 'Wähle dein Passwort',
    pwSub: 'Nur du kennst es. Zehn Zeichen oder mehr.',
    pw: 'Neues Passwort', again: 'Noch einmal',
    save: 'Speichern', saving: 'Speichere...',
    saved: 'Gespeichert. Es gilt, sobald hbar es einschaltet; bis dahin gilt dein altes Passwort.',
    chosen: 'Dein neues Passwort ist gewählt. Es gilt, sobald hbar es einschaltet.',
    differ: 'Die beiden sind nicht gleich.',
    failed: 'Das hat nicht geklappt. Versuch es in einer Minute noch einmal.',
    actions: { 'key minted': 'begonnen', 'cleared copies': 'doppelt Angekommenes entfernt', 'reading what the person chose': 'begonnen, dein Gewähltes einzulesen', 'setup ended': 'fertig', 'new console password chosen': 'du hast ein neues Passwort gewählt' },
  },
  ru: {
    title: 'Настройка',
    working: (d) => `Помощник настройки заканчивает твой переезд, до ${d}.`,
    sees: 'Он видит только числа, никогда твои файлы или чаты. Он не может менять твои слова или удалять то, что ты оставил(а).',
    last: 'Последнее',
    nothing: 'Пока ничего.',
    done: 'Готово, остановить помощника',
    sure: 'Остановить сейчас? То, что ещё читается, продолжится само.',
    yes: 'Остановить', no: 'Пусть работает',
    ended: 'Помощник настройки закончил. Твой мозг твой.',
    never: 'На этом мозге помощник настройки не работает.',
    letIn: 'Пусть помощник закончит настройку',
    pwTitle: 'Выбери свой пароль',
    pwSub: 'Его будешь знать только ты. Десять символов или больше.',
    pw: 'Новый пароль', again: 'Ещё раз',
    save: 'Сохранить', saving: 'Сохраняю...',
    saved: 'Сохранено. Он заработает, когда hbar его включит; до тех пор действует старый пароль.',
    chosen: 'Новый пароль выбран. Он заработает, когда hbar его включит.',
    differ: 'Пароли не совпадают.',
    failed: 'Не получилось. Попробуй через минуту.',
    actions: { 'key minted': 'начал', 'cleared copies': 'убрал то, что пришло дважды', 'reading what the person chose': 'начал читать то, что ты выбрал(а)', 'setup ended': 'закончил', 'new console password chosen': 'ты выбрал(а) новый пароль' },
  },
}

const when = (ts, lang) => {
  if (!ts) return ''
  try { return new Date(ts * 1000).toLocaleString(lang === 'ru' ? 'ru-RU' : lang === 'de' ? 'de-DE' : 'en-GB', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }) } catch { return '' }
}

export default function SetupPage() {
  const [lang, setLang] = useState('en')
  const [st, setSt] = useState(undefined)     // undefined while loading; null when the api did not answer
  const [ask, setAsk] = useState(false)
  const [pw, setPw] = useState({ a: '', b: '', state: null })
  const [offer, setOffer] = useState(null)   // GET /setup/consent: the line, when no period was ever opened
  const W = WORDS[lang] || WORDS.en
  const load = () => fetch(`${API}/setup/status`, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(setSt).catch(() => setSt(null))
  useEffect(() => {
    fetch('/cc/layout', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(j => { if (j && WORDS[j.lang]) setLang(j.lang) }).catch(() => {})
    load()
    fetch(`${API}/setup/consent`, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(setOffer).catch(() => {})
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [])
  const stop = async () => {
    await fetch(`${API}/setup/revoke`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ by: 'member', why: 'Done pressed' }) }).catch(() => null)
    setAsk(false); load()
  }
  // a brain already moved in never shows the move-in card's line again: the same yes, here (docs/STEWARD.md)
  const letIn = async () => {
    const c = await fetch(`${API}/setup/consent?lang=${lang}`, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)
    if (!c) return
    await fetch(`${API}/setup/key`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ consent: true, lang: c.lang, text_sha: c.sha, by: 'member' }) }).catch(() => null)
    load()
  }
  const save = async () => {
    if (pw.a !== pw.b) { setPw({ ...pw, state: 'differ' }); return }
    setPw({ ...pw, state: 'busy' })
    const r = await fetch(`${API}/setup/handover/password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw.a, again: pw.b }) }).catch(() => null)
    const j = r ? await r.json().catch(() => ({})) : {}
    if (r && r.ok) { setPw({ a: '', b: '', state: 'saved' }); load() } else setPw({ ...pw, state: { error: (j && j.detail) || W.failed } })
  }
  const last = st && (st.last_steward_action || st.last_action)
  const active = st && st.active
  const ever = st && st.minted_at
  return (
    <main className="stp">
      <Head><title>{W.title}</title></Head>
      <span className="stp-k">{W.title}</span>
      {st === null && <p className="stp-big">{W.never}</p>}
      {st === undefined && <p className="stp-big" aria-busy="true">&nbsp;</p>}
      {active && (
        <>
          <p className="stp-big">{W.working(when(st.expires_at, lang))}</p>
          <p className="stp-dim">{W.sees}</p>
          <p className="stp-line"><span className="stp-k">{W.last}</span>{last ? `${(W.actions[last.action] || last.action)}, ${when(last.at, lang)}` : W.nothing}</p>
          {!ask && <button type="button" className="stp-btn" onClick={() => setAsk(true)}>{W.done}</button>}
          {ask && (
            <div className="stp-ask">
              <p>{W.sure}</p>
              <button type="button" className="stp-btn stp-primary" onClick={stop}>{W.yes}</button>
              <button type="button" className="stp-btn" onClick={() => setAsk(false)}>{W.no}</button>
            </div>
          )}
        </>
      )}
      {st && !active && !ever && <p className="stp-big">{W.never}</p>}
      {st && !active && !ever && offer && offer.text && (
        <>
          <p className="stp-dim">{offer.text}</p>
          <button type="button" className="stp-btn stp-primary" onClick={letIn}>{W.letIn}</button>
        </>
      )}
      {st && !active && ever && <p className="stp-big">{W.ended}</p>}
      {st && ever && (
        <section className="stp-pw">
          <span className="stp-k">{W.pwTitle}</span>
          {st.password_chosen && pw.state !== 'saved' ? <p>{W.chosen}</p> : pw.state === 'saved' ? <p>{W.saved}</p> : (
            <>
              <p className="stp-dim">{W.pwSub}</p>
              <label className="stp-field"><span>{W.pw}</span><input type="password" autoComplete="new-password" value={pw.a} onChange={e => setPw({ ...pw, a: e.target.value, state: null })} /></label>
              <label className="stp-field"><span>{W.again}</span><input type="password" autoComplete="new-password" value={pw.b} onChange={e => setPw({ ...pw, b: e.target.value, state: null })} /></label>
              {pw.state === 'differ' && <p className="stp-bad" role="alert">{W.differ}</p>}
              {pw.state && pw.state.error && <p className="stp-bad" role="alert">{pw.state.error}</p>}
              <button type="button" className="stp-btn stp-primary" disabled={pw.state === 'busy' || pw.a.length < 10} onClick={save}>{pw.state === 'busy' ? W.saving : W.save}</button>
            </>
          )}
        </section>
      )}
      <style jsx>{`
        .stp { max-width: 640px; margin: 0 auto; padding: 56px 24px 80px; color: var(--text, #EBEBE6); font-family: 'Inter Tight', system-ui, sans-serif; font-weight: 300; }
        .stp-k { display: inline-block; font: 400 11px/1 'IBM Plex Mono', monospace; letter-spacing: .14em; text-transform: uppercase; color: var(--text-dim, #8A8A85); margin-right: 12px; }
        .stp-big { font-weight: 200; font-size: 30px; line-height: 1.2; margin: 14px 0 12px; }
        .stp-dim { color: var(--text-dim, #8A8A85); font-size: 15px; line-height: 1.5; }
        .stp-line { border-top: 1px solid var(--border, #22221f); padding-top: 12px; margin: 22px 0; overflow-wrap: anywhere; }
        .stp-btn { font: inherit; font-size: 15px; color: var(--text, #EBEBE6); background: transparent; border: 1px solid var(--border, #33332f); border-radius: 999px; padding: 9px 18px; margin: 6px 8px 0 0; cursor: pointer; }
        .stp-btn:hover { border-color: var(--text-dim, #8A8A85); }
        .stp-btn:disabled { opacity: .45; cursor: default; }
        .stp-primary { background: var(--text, #EBEBE6); color: var(--bg, #000); border-color: transparent; }
        .stp-ask { border: 1px solid var(--border, #22221f); border-radius: 14px; padding: 14px 16px; margin-top: 8px; }
        .stp-pw { margin-top: 40px; border-top: 1px solid var(--border, #22221f); padding-top: 18px; }
        .stp-field { display: block; margin: 12px 0; }
        .stp-field span { display: block; font-size: 13px; color: var(--text-dim, #8A8A85); margin-bottom: 6px; }
        .stp-field input { width: 100%; font: inherit; color: var(--text, #EBEBE6); background: transparent; border: 1px solid var(--border, #33332f); border-radius: 12px; padding: 11px 14px; outline: none; }
        .stp-field input:focus { border-color: var(--text-dim, #8A8A85); }
        .stp-bad { color: #E8A07A; font-size: 14px; }
        @media (max-width: 480px) { .stp { padding-top: 36px; } .stp-big { font-size: 24px; } }
      `}</style>
    </main>
  )
}
