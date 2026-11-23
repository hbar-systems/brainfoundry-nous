// The sign-in screen's words (MEMBERS-14 2026-11-23, hbar: "Rebuild it for a person who has never seen a terminal").
// One table per console language (scripts/cc/cc_layout.py LANGS). sk, de, el and rue are the assistant's words,
// not a native speaker's: one native read each before a handover, Rusyn most of all.
// Shown on every brain whose subscription sign-in runs through the terminal door (no CC_SUBSCRIPTION_PROXY):
// the code is typed into Claude Code itself in the dark box, never into this page
// (ops/legal/claude-code-terms-2026-09-19.md in hbar.world, point 3).

const EN = {
  head: 'Sign in once',
  s1: 'Open the sign-in page', s1sub: 'Claude opens in a new tab. Sign in there as you always do.',
  s1wait: 'getting the sign-in page ready…', s1box: 'Press the blue link in the dark box below.',
  s2: 'Paste the code', s2sub: 'Claude shows a code. Copy it, come back to this tab, press the button, paste (Ctrl+V, on a Mac Cmd+V) and press Enter.',
  s2btn: 'Paste the code here',
  s3: 'Done', s3sub: 'This page sees the sign-in by itself and opens your brain.',
  s3wait: 'waiting for the sign-in…', s3ok: 'Signed in.',
  again: 'Start the sign-in again',
  pending: (t) => `Your start waits and runs by itself after the sign-in: "${t}"`,
  phone: 'A laptop is easiest: copying the code is one step there. On a phone it works too: copy the code, come back, hold your finger in the dark box and choose Paste.',
  box: "Claude's own sign-in, on your server",
  other: 'Other ways to sign in',
}

const RU = {
  head: 'Войдите один раз',
  s1: 'Открыть страницу входа', s1sub: 'Claude откроется в новой вкладке. Войдите там, как обычно.',
  s1wait: 'готовлю страницу входа…', s1box: 'Нажмите синюю ссылку в тёмном окне ниже.',
  s2: 'Вставить код', s2sub: 'Claude покажет код. Скопируйте его, вернитесь в эту вкладку, нажмите кнопку, вставьте (Ctrl+V, на Mac Cmd+V) и нажмите Enter.',
  s2btn: 'Вставить код сюда',
  s3: 'Готово', s3sub: 'Страница сама увидит вход и откроет ваш мозг.',
  s3wait: 'жду входа…', s3ok: 'Вход выполнен.',
  again: 'Начать вход заново',
  pending: (t) => `Ваша кнопка подождёт и сама запустится после входа: «${t}»`,
  phone: 'Проще всего на ноутбуке: там копирование кода — один шаг. На телефоне тоже можно: скопируйте код, вернитесь, задержите палец в тёмном окне и выберите «Вставить».',
  box: 'Вход в Claude, на вашем сервере',
  other: 'Другие способы входа',
}

const SK = {
  head: 'Prihlás sa raz',
  s1: 'Otvoriť stránku prihlásenia', s1sub: 'Claude sa otvorí v novej karte. Prihlás sa tam ako vždy.',
  s1wait: 'pripravujem stránku prihlásenia…', s1box: 'Stlač modrý odkaz v tmavom okne nižšie.',
  s2: 'Vložiť kód', s2sub: 'Claude ukáže kód. Skopíruj ho, vráť sa do tejto karty, stlač tlačidlo, vlož (Ctrl+V, na Macu Cmd+V) a stlač Enter.',
  s2btn: 'Vložiť kód sem',
  s3: 'Hotovo', s3sub: 'Stránka sama uvidí prihlásenie a otvorí tvoj mozog.',
  s3wait: 'čakám na prihlásenie…', s3ok: 'Prihlásené.',
  again: 'Začať prihlásenie znova',
  pending: (t) => `Tvoj štart počká a spustí sa sám po prihlásení: „${t}“`,
  phone: 'Najľahšie je to na notebooku: kopírovanie kódu je tam jeden krok. Na telefóne to ide tiež: skopíruj kód, vráť sa, podrž prst v tmavom okne a vyber Vložiť.',
  box: 'Prihlásenie do Claude, na tvojom serveri',
  other: 'Iné spôsoby prihlásenia',
}

const DE = {
  head: 'Einmal anmelden',
  s1: 'Anmeldeseite öffnen', s1sub: 'Claude öffnet sich in einem neuen Tab. Melde dich dort an wie immer.',
  s1wait: 'die Anmeldeseite wird vorbereitet…', s1box: 'Drück den blauen Link im dunklen Feld unten.',
  s2: 'Code einfügen', s2sub: 'Claude zeigt einen Code. Kopier ihn, komm zu diesem Tab zurück, drück den Knopf, füg ein (Strg+V, am Mac Cmd+V) und drück Enter.',
  s2btn: 'Code hier einfügen',
  s3: 'Fertig', s3sub: 'Die Seite merkt die Anmeldung von selbst und öffnet dein Brain.',
  s3wait: 'warte auf die Anmeldung…', s3ok: 'Angemeldet.',
  again: 'Anmeldung neu starten',
  pending: (t) => `Dein Start wartet und läuft nach der Anmeldung von selbst: „${t}“`,
  phone: 'Am Laptop ist es am leichtesten: dort ist das Kopieren des Codes ein Schritt. Am Handy geht es auch: Code kopieren, zurückkommen, den Finger im dunklen Feld halten und Einfügen wählen.',
  box: 'Die Anmeldung bei Claude, auf deinem Server',
  other: 'Andere Wege zur Anmeldung',
}

const EL = {
  head: 'Συνδέσου μία φορά',
  s1: 'Άνοιξε τη σελίδα σύνδεσης', s1sub: 'Το Claude ανοίγει σε νέα καρτέλα. Συνδέσου εκεί όπως πάντα.',
  s1wait: 'ετοιμάζω τη σελίδα σύνδεσης…', s1box: 'Πάτα τον μπλε σύνδεσμο στο σκούρο πλαίσιο από κάτω.',
  s2: 'Επικόλλησε τον κωδικό', s2sub: 'Το Claude δείχνει έναν κωδικό. Αντίγραψέ τον, γύρνα σε αυτή την καρτέλα, πάτα το κουμπί, επικόλλησε (Ctrl+V, σε Mac Cmd+V) και πάτα Enter.',
  s2btn: 'Επικόλληση κωδικού εδώ',
  s3: 'Έτοιμο', s3sub: 'Η σελίδα βλέπει μόνη της τη σύνδεση και ανοίγει το μυαλό σου.',
  s3wait: 'περιμένω τη σύνδεση…', s3ok: 'Συνδέθηκες.',
  again: 'Ξεκίνα ξανά τη σύνδεση',
  pending: (t) => `Αυτό που πάτησες περιμένει και ξεκινά μόνο του μετά τη σύνδεση: «${t}»`,
  phone: 'Πιο εύκολα σε laptop: εκεί η αντιγραφή του κωδικού είναι ένα βήμα. Και στο κινητό γίνεται: αντίγραψε τον κωδικό, γύρνα, κράτα το δάχτυλο στο σκούρο πλαίσιο και διάλεξε Επικόλληση.',
  box: 'Η σύνδεση στο Claude, στον server σου',
  other: 'Άλλοι τρόποι σύνδεσης',
}

// Rusyn (Prešov Rusyn, Cyrillic): needs a native read before Julesa sees it.
const RUE = {
  head: 'Приголось ся раз',
  s1: 'Отворити сторінку приголошіня', s1sub: 'Claude ся отворить в новій карті. Приголось ся там як все.',
  s1wait: 'рыхтую сторінку приголошіня…', s1box: 'Стисни голубый одказ в тмавім окнї долу.',
  s2: 'Вкласти код', s2sub: 'Claude укаже код. Скопіруй го, вернь ся до тій карты, стисни гомбік, вклади (Ctrl+V, на Mac Cmd+V) і стисни Enter.',
  s2btn: 'Вкласти код сюды',
  s3: 'Готово', s3sub: 'Сторінка сама увидить приголошіня і отворить твій мозок.',
  s3wait: 'чекам на приголошіня…', s3ok: 'Приголошена.',
  again: 'Зачати приголошіня знову',
  pending: (t) => `Твій старт почекать і пустить ся сам по приголошіню: «${t}»`,
  phone: 'Найлегше на ноутбуку: там є копірованя коду єден крок. На телефонї то іде тыж: скопіруй код, вернь ся, придрж палець в тмавім окнї і выбер Вкласти.',
  box: 'Приголошіня до Claude, на твоїм сервері',
  other: 'Іншы способы приголошіня',
}

const SIGNIN_TEXT = { en: EN, ru: RU, sk: SK, de: DE, el: EL, rue: RUE }
const signinWords = (lang) => SIGNIN_TEXT[lang] || EN

// A start's text, cut for the waiting line.
function shortStart(t) {
  const s = String(t || '').replace(/\s+/g, ' ').trim()
  return s.length > 90 ? s.slice(0, 88).trimEnd() + '…' : s
}

module.exports = { SIGNIN_TEXT, signinWords, shortStart }
