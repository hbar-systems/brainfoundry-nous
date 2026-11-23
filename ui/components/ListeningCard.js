// "Bring your listening" on the quiet home (YT-2, 2026-11-23). The owner connects their own YouTube in One,
// reads what is read and why (the disclosure, from the bridge), and one press reads their likes and playlists
// into this brain: a list in its own folder and a taste note in its memory. Doors: GET /cc/listening,
// POST /cc/listening/read (scripts/cc/cc_listening.py). Nothing leaves the brain; nothing is written to YouTube.
import { useEffect, useState } from 'react'
import css from 'styled-jsx/css'

const ONE_URL = 'https://app.withone.ai/connections'
const n = (x) => Number(x || 0).toLocaleString('en').replace(/,/g, '\u202f')
const W = {
  en: {
    title: 'Bring your listening', none: 'Not connected', ready: 'Connected', reading: 'Reading', done: 'In your brain',
    noOne: 'This brain has no One door yet. The person who set up your brain adds its One key once; then this card opens.',
    steps: ['Open ' + ONE_URL + ' and sign in to the One account this brain uses.', 'Press Add connection, choose YouTube Data, and sign in with the Google account you listen on.', 'Come back here and press Check again.'],
    check: 'Check again', read: 'Read my listening', again: 'Read again', what: 'What is read, and why',
    accounts: (a) => 'YouTube: ' + a.map(x => x.channel || ('key ' + x.tail)).join(', '),
    wait: 'Reading your likes and playlists. Big playlists take a few minutes; you can leave this page.',
    last: (l) => `${n(l.records)} videos (${n(l.music)} music) from ${l.accounts.map(a => `${a.playlists} playlists and ${a.likes} likes on ${a.channel}`).join('; ')}, read ${l.at.slice(0, 10)}.`,
    taste: 'Your taste: ', kept: 'The taste note is in your memory.',
  },
  el: {
    title: 'Φέρε αυτά που ακούς', none: 'Δεν έχει συνδεθεί', ready: 'Συνδέθηκε', reading: 'Διαβάζει', done: 'Στον εγκέφαλό σου',
    noOne: 'Αυτός ο εγκέφαλος δεν έχει ακόμα πόρτα One. Όποιος έστησε τον εγκέφαλό σου βάζει μία φορά το κλειδί του One· μετά ανοίγει αυτή η κάρτα.',
    steps: ['Άνοιξε το ' + ONE_URL + ' και μπες στον λογαριασμό One που χρησιμοποιεί αυτός ο εγκέφαλος.', 'Πάτα Add connection, διάλεξε YouTube Data και μπες με τον λογαριασμό Google όπου ακούς.', 'Γύρνα εδώ και πάτα Έλεγξε ξανά.'],
    check: 'Έλεγξε ξανά', read: 'Διάβασε τι ακούω', again: 'Διάβασε ξανά', what: 'Τι διαβάζεται και γιατί',
    accounts: (a) => 'YouTube: ' + a.map(x => x.channel || ('κλειδί ' + x.tail)).join(', '),
    wait: 'Διαβάζει τα likes και τις λίστες σου. Οι μεγάλες λίστες θέλουν λίγα λεπτά· μπορείς να φύγεις από τη σελίδα.',
    last: (l) => `${n(l.records)} βίντεο (${n(l.music)} μουσική) από ${l.accounts.map(a => `${a.playlists} λίστες και ${a.likes} likes στο ${a.channel}`).join('· ')}, ${l.at.slice(0, 10)}.`,
    taste: 'Το γούστο σου: ', kept: 'Η σημείωση γούστου είναι στη μνήμη σου.',
  },
  ru: {
    title: 'Принесите то, что слушаете', none: 'Не подключено', ready: 'Подключено', reading: 'Читаю', done: 'В вашем мозге',
    noOne: 'У этого мозга ещё нет двери One. Тот, кто настроил ваш мозг, один раз добавляет ключ One; потом карточка откроется.',
    steps: ['Откройте ' + ONE_URL + ' и войдите в аккаунт One этого мозга.', 'Нажмите Add connection, выберите YouTube Data и войдите в Google-аккаунт, где вы слушаете.', 'Вернитесь сюда и нажмите «Проверить снова».'],
    check: 'Проверить снова', read: 'Прочитать, что я слушаю', again: 'Прочитать снова', what: 'Что читается и зачем',
    accounts: (a) => 'YouTube: ' + a.map(x => x.channel || ('ключ ' + x.tail)).join(', '),
    wait: 'Читаю лайки и плейлисты. Большие плейлисты занимают несколько минут; страницу можно закрыть.',
    last: (l) => `${n(l.records)} видео (${n(l.music)} музыка): ${l.accounts.map(a => `${a.playlists} плейлистов и ${a.likes} лайков на ${a.channel}`).join('; ')}, ${l.at.slice(0, 10)}.`,
    taste: 'Ваш вкус: ', kept: 'Заметка о вкусе в вашей памяти.',
  },
}

export default function ListeningCard({ lang = 'en' }) {
  const L = lang === 'el' || lang === 'ru' ? lang : 'en'
  const t = W[L]
  const [s, setS] = useState(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = () => fetch('/cc/listening', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(setS).catch(() => setS(null))
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!s || !s.running) return undefined
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [s && s.running])
  if (!s) return null
  const read = () => {
    setBusy(true)
    fetch('/cc/listening/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(() => load()).finally(() => setBusy(false))
  }
  const acc = s.accounts || []
  const last = s.last
  const pill = s.running ? ['wait', t.reading] : last ? ['done', t.done] : acc.length ? ['wait', t.ready] : ['new', t.none]
  const disclosure = (s.disclosure || {})[L] || (s.disclosure || {}).en || ''
  return (
    <div className="ls">
      <section className={`ls-card${last && !s.running ? ' ls-done' : ''}`}>
        <div className="ls-head">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <path d="M5 16v-2a9 9 0 0118 0v2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <rect x="4" y="16" width="5" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
            <rect x="19" y="16" width="5" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
          </svg>
          <h2 className="ls-title">{t.title}</h2>
          <span className={`ls-pill ls-pill-${pill[0]}`}>{pill[1]}</span>
        </div>
        {!s.one && <p className="ls-sub">{t.noOne}</p>}
        {s.one && !acc.length && (
          <ol className="ls-steps">
            {t.steps.map((x, i) => <li key={i}>{x.split(ONE_URL).flatMap((part, j) => (j ? [<a key={j} href={ONE_URL} target="_blank" rel="noreferrer">{ONE_URL}</a>, part] : [part]))}</li>)}
          </ol>
        )}
        {acc.length > 0 && <p className="ls-sub">{t.accounts(acc)}</p>}
        {s.running && <p className="ls-sub">{t.wait}</p>}
        {last && !s.running && (
          <>
            <p className="ls-sub">{t.last(last)}</p>
            {last.taste && last.taste.length > 0 && <p className="ls-sub">{t.taste}<b>{last.taste.join(', ')}</b></p>}
            {last.note && last.note.kept && <p className="ls-note">{t.kept}</p>}
            {last.note && !last.note.kept && last.note.why && <p className="ls-note ls-bad">{last.note.why}</p>}
          </>
        )}
        {s.error && !s.running && <p className="ls-note ls-bad">{s.error}</p>}
        {open && <p className="ls-disc">{disclosure}</p>}
        <div className="ls-actions">
          {s.one && !acc.length && <button className="ls-btn" onClick={load}>{t.check}</button>}
          {acc.length > 0 && !s.running && (
            <button className={`ls-btn${last ? '' : ' ls-primary'}`} disabled={busy} onClick={read}>{last ? t.again : t.read}</button>
          )}
          <button className="ls-link" onClick={() => setOpen(!open)} aria-expanded={open}>{t.what}</button>
        </div>
      </section>
      <style jsx>{lsStyles}</style>
    </div>
  )
}

const lsStyles = css`
  .ls { margin: 0 0 28px; }
  .ls :global(.ls-card) {
    padding: 26px 28px 24px; border-radius: 18px;
    background: color-mix(in srgb, var(--surface2) 88%, var(--accent) 12%);
    border: 1px solid color-mix(in srgb, var(--border) 60%, var(--accent) 40%);
  }
  .ls :global(.ls-card.ls-done) { background: var(--surface); border-color: var(--border); padding: 20px 28px; }
  .ls :global(.ls-head) { display: flex; align-items: center; gap: 14px; color: var(--accent); flex-wrap: wrap; }
  .ls :global(.ls-title) { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: 24px; line-height: 1.25; color: var(--text); }
  .ls :global(.ls-done .ls-title) { font-size: 19px; font-weight: 400; }
  .ls :global(.ls-pill) { font-size: 15px; padding: 5px 12px; border-radius: 999px; }
  .ls :global(.ls-pill-new) { color: var(--text-dim, var(--muted)); background: color-mix(in srgb, var(--bg) 55%, transparent); }
  .ls :global(.ls-pill-wait) { color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
  .ls :global(.ls-pill-done) { color: #9cbf8a; background: rgba(122,158,110,0.14); }
  .ls :global(.ls-sub) { margin: 14px 0 0 42px; font-size: 18px; line-height: 1.55; color: var(--text); opacity: 0.86; overflow-wrap: anywhere; }
  .ls :global(.ls-note) { margin: 12px 0 0 42px; font-size: 16px; line-height: 1.5; color: var(--text); }
  .ls :global(.ls-bad) { color: #d99a8a; }
  .ls :global(.ls-disc) { margin: 14px 0 0 42px; font-size: 15px; line-height: 1.55; color: var(--text); opacity: 0.8; max-width: 62ch; }
  .ls :global(.ls-steps) { margin: 18px 0 0 42px; padding: 0 0 0 22px; font-size: 18px; line-height: 1.55; color: var(--text); }
  .ls :global(.ls-steps li) { margin: 0 0 8px; padding-left: 6px; overflow-wrap: anywhere; }
  .ls :global(.ls-steps a), .ls :global(.ls-link) { color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
  .ls :global(.ls-actions) { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 18px; margin: 20px 0 0 42px; }
  .ls :global(.ls-btn) {
    font: inherit; font-size: 18px; min-height: 52px; padding: 0 24px; border-radius: 12px; cursor: pointer;
    color: var(--text); background: transparent; border: 1px solid color-mix(in srgb, var(--border) 50%, var(--text) 30%);
    transition: background-color 150ms ease-out, transform 120ms ease-out;
  }
  .ls :global(.ls-btn:hover:not(:disabled)) { background: color-mix(in srgb, var(--text) 7%, transparent); }
  .ls :global(.ls-btn:active:not(:disabled)) { transform: scale(0.98); }
  .ls :global(.ls-btn:disabled) { opacity: 0.6; cursor: default; }
  .ls :global(.ls-primary) { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
  .ls :global(.ls-link) { font-size: 16px; background: none; border: 0; padding: 0; cursor: pointer; font-family: inherit; }
  @media (max-width: 560px) {
    .ls :global(.ls-card) { padding: 20px 18px; border-radius: 16px; }
    .ls :global(.ls-sub), .ls :global(.ls-note), .ls :global(.ls-disc), .ls :global(.ls-steps), .ls :global(.ls-actions) { margin-left: 0; }
  }
`
