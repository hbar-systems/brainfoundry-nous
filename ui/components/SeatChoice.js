// Three seats on the sign-in screen (SEAT-3 2026-11-23, hbar: "maybe a third sign in option/seat should be private gpu brain").
//   Claude        the member's own Claude subscription: the three steps below (SignInSteps), the best answers
//   ChatGPT       the member's own ChatGPT: OpenAI's device sign-in in the pane beside (the Codex seat)
//   Private brain no account anywhere: an open model on this server (cc_private.py), free, slower, simpler;
//                 it reads, and a change it wants comes as a card like every other seat
// The private seat is offered, never taken by itself: the press here writes the bridge's private.json.
// sk, de, el and rue are the assistant's words: one native read each before a handover, Rusyn most of all.
import { useState } from 'react'

const W = {
  en: { head: 'How should your brain think?', claude: 'Claude', claudeSub: 'Your own Claude subscription. The best answers. Sign in once, below.',
    gpt: 'ChatGPT', gptSub: 'Your own ChatGPT subscription. Sign in once, in the panel beside.',
    priv: 'Private brain', privSub: 'No account needed. A small open model on this server: free and private, but slower and simpler. It reads your files; it changes nothing until you press.',
    privBtn: 'Use the private brain', privOff: 'Not on this brain yet. Ask hbar to turn it on.', chosen: 'chosen', later: 'You can sign in with Claude or ChatGPT later; the brain then answers with that.' },
  ru: { head: 'Чем будет думать ваш мозг?', claude: 'Claude', claudeSub: 'Ваша подписка Claude. Лучшие ответы. Войдите один раз, ниже.',
    gpt: 'ChatGPT', gptSub: 'Ваша подписка ChatGPT. Войдите один раз, в окне рядом.',
    priv: 'Свой мозг', privSub: 'Без аккаунта. Небольшая открытая модель на этом сервере: бесплатно и приватно, но медленнее и проще. Она читает ваши файлы и ничего не меняет, пока вы не нажмёте.',
    privBtn: 'Включить свой мозг', privOff: 'На этом мозге его пока нет. Попросите hbar включить.', chosen: 'выбрано', later: 'Войти через Claude или ChatGPT можно и потом; тогда мозг будет отвечать через них.' },
  sk: { head: 'Ako má tvoj mozog myslieť?', claude: 'Claude', claudeSub: 'Tvoje vlastné predplatné Claude. Najlepšie odpovede. Prihlás sa raz, nižšie.',
    gpt: 'ChatGPT', gptSub: 'Tvoje vlastné predplatné ChatGPT. Prihlás sa raz, v okne vedľa.',
    priv: 'Súkromný mozog', privSub: 'Bez účtu. Malý otvorený model na tomto serveri: zadarmo a súkromne, ale pomalší a jednoduchší. Číta tvoje súbory; nič nezmení, kým nestlačíš.',
    privBtn: 'Použiť súkromný mozog', privOff: 'Na tomto mozgu ešte nie je. Popros hbar, nech ho zapne.', chosen: 'zvolené', later: 'Prihlásiť sa cez Claude alebo ChatGPT môžeš aj neskôr; mozog potom odpovedá cez ne.' },
  de: { head: 'Womit soll dein Brain denken?', claude: 'Claude', claudeSub: 'Dein eigenes Claude-Abo. Die besten Antworten. Einmal anmelden, unten.',
    gpt: 'ChatGPT', gptSub: 'Dein eigenes ChatGPT-Abo. Einmal anmelden, im Feld daneben.',
    priv: 'Privates Brain', privSub: 'Kein Konto nötig. Ein kleines offenes Modell auf diesem Server: kostenlos und privat, aber langsamer und einfacher. Es liest deine Dateien; es ändert nichts, bis du drückst.',
    privBtn: 'Privates Brain nutzen', privOff: 'Auf diesem Brain noch nicht da. Bitte hbar, es einzuschalten.', chosen: 'gewählt', later: 'Mit Claude oder ChatGPT anmelden geht auch später; dann antwortet das Brain damit.' },
  el: { head: 'Με τι να σκέφτεται ο εγκέφαλός σου;', claude: 'Claude', claudeSub: 'Η δική σου συνδρομή Claude. Οι καλύτερες απαντήσεις. Σύνδεση μία φορά, παρακάτω.',
    gpt: 'ChatGPT', gptSub: 'Η δική σου συνδρομή ChatGPT. Σύνδεση μία φορά, στο διπλανό πλαίσιο.',
    priv: 'Ιδιωτικός εγκέφαλος', privSub: 'Χωρίς λογαριασμό. Ένα μικρό ανοιχτό μοντέλο σε αυτόν τον διακομιστή: δωρεάν και ιδιωτικό, αλλά πιο αργό και πιο απλό. Διαβάζει τα αρχεία σου· δεν αλλάζει τίποτα μέχρι να πατήσεις.',
    privBtn: 'Χρήση του ιδιωτικού εγκεφάλου', privOff: 'Δεν υπάρχει ακόμα σε αυτόν τον εγκέφαλο. Ζήτα από τον hbar να τον ανοίξει.', chosen: 'επιλέχθηκε', later: 'Μπορείς να συνδεθείς με Claude ή ChatGPT και αργότερα· τότε ο εγκέφαλος απαντά με αυτά.' },
  rue: { head: 'Як мать думати твій мозок?', claude: 'Claude', claudeSub: 'Твоє власне передплатне Claude. Найлїпшы одповіди. Приголось ся раз, долов.',
    gpt: 'ChatGPT', gptSub: 'Твоє власне передплатне ChatGPT. Приголось ся раз, в окнї побіч.',
    priv: 'Свій мозок', privSub: 'Без конта. Малый отвореный модел на тім серверї: задарьмо і приватно, але помалшый і простїшый. Чітать твої файлы; ніч не змінить, покы не стиснеш.',
    privBtn: 'Хосновати свій мозок', privOff: 'На тім мозку го іщі нє. Попрос hbar, жебы го запнув.', chosen: 'выбране', later: 'Приголосити ся через Claude або ChatGPT можеш і пізнїше; мозок потім одповідать через нї.' },
}
export const seatWords = (lang) => W[lang] || W.en

export default function SeatChoice({ lang = 'en', local, codex, onOpenPane, codexLogin, onChosen, children }) {
  const T = seatWords(lang)
  const [pick, setPick] = useState('claude')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const privOn = !!(local && local.configured)
  const gptOn = !!(codex && codex.installed && !codex.signedIn)

  async function usePrivate() {
    setBusy(true); setErr(null)
    try {
      const r = await fetch('/cc/seat/private', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on: true }) })
      const d = await r.json().catch(() => ({}))
      if (r.ok && d.ok) onChosen && onChosen(d.local); else setErr(d.error || 'not accepted')
    } catch { setErr('the bridge did not answer') }
    setBusy(false)
  }

  return (
    <section className="sc" data-seat-choice={pick} aria-label={T.head}>
      <h2 className="sc-head">{T.head}</h2>
      <div className="sc-row" role="radiogroup">
        <button type="button" role="radio" aria-checked={pick === 'claude'} className={`sc-card${pick === 'claude' ? ' sc-on' : ''}`} onClick={() => setPick('claude')}>
          <span className="sc-name">{T.claude}</span><span className="sc-sub">{T.claudeSub}</span>
        </button>
        <button type="button" role="radio" aria-checked={pick === 'gpt'} disabled={!gptOn && !(codex && codex.signedIn)}
          className={`sc-card${pick === 'gpt' ? ' sc-on' : ''}`} onClick={() => { setPick('gpt'); if (gptOn && onOpenPane && codexLogin) onOpenPane(codexLogin) }}>
          <span className="sc-name">{T.gpt}</span><span className="sc-sub">{T.gptSub}</span>
        </button>
        <button type="button" role="radio" aria-checked={pick === 'private'} className={`sc-card${pick === 'private' ? ' sc-on' : ''}`} onClick={() => setPick('private')} data-seat-private>
          <span className="sc-name">{T.priv}</span><span className="sc-sub">{T.privSub}</span>
          {local && local.model ? <span className="sc-meta">{local.model}</span> : null}
        </button>
      </div>
      {pick === 'private' && (
        <div className="sc-private">
          {privOn
            ? <button type="button" className="sc-btn" disabled={busy} onClick={usePrivate} data-seat-private-use>{T.privBtn}</button>
            : <p className="sc-off">{T.privOff}</p>}
          <p className="sc-later">{T.later}</p>
          {err && <p className="sc-err">{err}</p>}
        </div>
      )}
      {pick === 'claude' && children}
      <style jsx>{`
        .sc { margin: 4px 0 18px; max-width: 46em; }
        .sc-head { margin: 0 0 12px; font-family: var(--font-display); font-weight: 600; font-size: 24px; color: var(--text); }
        .sc-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 0 0 16px; }
        .sc-card { display: flex; flex-direction: column; gap: 6px; text-align: left; padding: 14px 16px; border: 1px solid var(--border); border-radius: 14px;
          background: transparent; color: var(--text); font: inherit; cursor: pointer; opacity: 0.8; }
        .sc-card:disabled { opacity: 0.45; cursor: default; }
        .sc-on { opacity: 1; border-color: var(--text); }
        .sc-name { font-size: 18px; font-weight: 600; }
        .sc-sub { font-size: 14px; line-height: 1.45; color: var(--text-dim, var(--muted)); }
        .sc-meta { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; color: var(--text-dim, var(--muted)); }
        .sc-card:focus-visible, .sc-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
        .sc-private { margin: 0 0 16px; }
        .sc-btn { display: inline-flex; align-items: center; justify-content: center; min-height: 52px; padding: 0 22px; border-radius: 12px; font: inherit; font-size: 18px;
          cursor: pointer; background: var(--text); color: var(--bg); border: 1px solid var(--text); }
        .sc-btn:disabled { opacity: 0.6; cursor: default; }
        .sc-off, .sc-later { margin: 10px 0 0; font-size: 15px; line-height: 1.5; color: var(--text-dim, var(--muted)); }
        .sc-err { margin: 8px 0 0; font-size: 14px; color: #d08a7a; }
        @media (max-width: 640px) { .sc-row { grid-template-columns: 1fr; } .sc-btn { width: 100%; } }
      `}</style>
    </section>
  )
}
