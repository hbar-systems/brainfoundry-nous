// The first sign-in order on a member brain (SWITCH-1, hbar 2026-11-16: "what about the initial onboarding where
// the user selects the method of production (as we have)?"). Once, then never again, on the quiet home:
//   1 seat    sign in with ChatGPT or Claude (the reasoner; without one the brain runs on the shared small model)
//   2 ways    pick the ways of working (the surfaces pick-list, scripts/cc/cc_layout.py SURFACE_LIST)
//   3 movein  move in: connect this computer, bring the chats from other AIs
//   4 home    the quiet home, from then on
// Each step can be skipped; the state is the bridge's (GET/POST /cc/first-run), so another browser does not
// start over. Pure logic and words here; the steps are ui/components/FirstRun.js.

const ORDER = ['seat', 'ways', 'movein', 'home']

// The step to show, or null when the order is over. A signed-in seat counts as done.
function currentStep(st, loggedIn) {
  if (!st || st.finished) return null
  const s = st.steps || {}
  for (const k of ORDER) {
    if (k === 'seat' && loggedIn) continue
    if (!s[k]) return k
  }
  return null
}

// Whether the order shows at all: a member brain's quiet home that has not finished it.
const showFirstRun = (st, quiet) => !!(quiet && st && st.member && !st.finished)

// The newcomer's ways of working when nothing was picked yet (cc_layout: member and org presets).
const NEWCOMER = ['chat', 'talkthrough']
function startPicks(layout, all) {
  if (layout && Array.isArray(layout.surfaces)) return layout.surfaces.slice()
  return NEWCOMER.filter(x => (all || []).includes(x))
}
function togglePick(picks, v, all) {
  if (v === 'chat') return picks
  const on = picks.includes(v)
  return (all || []).filter(x => x === 'chat' || (x === v ? !on : picks.includes(x)))
}

const EN = {
  names: { seat: 'Sign in', ways: 'Ways of working', movein: 'Move in', home: 'Your home' },
  stepOf: (n) => `Step ${n} of 4`,
  skip: 'Skip for now', next: 'Next',
  seatTitle: 'Sign in with Claude',
  seatSub: 'Your brain thinks with the Claude subscription you already have. Sign in once: three steps below, about two minutes. Your password stays with Claude.',
  // MEMBERS-13 walk 2026-11-23: a member brain has no local model, so the old line ("runs on a small free model") was false there.
  // MEMBERS-14: a start pressed before the sign-in now waits and runs by itself after it.
  seatLocal: 'Sign in first. A start you press before that waits here and runs by itself once you are signed in. Moving in (step 3) works already.',
  seatDone: 'Signed in.',
  waysTitle: 'How do you want to work here?',
  waysSub: 'Press to pick. What you leave out only leaves the home; you can change it any time in Settings.',
  waysKeep: 'Keep these',
  waysAlways: 'always on',
  about: {},
  moveTitle: 'Move in',
  moveSub: 'Bring your computer and your chats with other AIs. Both can wait; this page keeps them.',
  moveDone: 'Done for now',
  homeTitle: 'This is your home',
  homeSub: 'From now on this page opens empty and quiet: write or speak, and your brain answers. The cards for moving in stay here until both are in.',
  homeGo: 'Open my home',
}

const RU = {
  names: { seat: 'Вход', ways: 'Как работать', movein: 'Переезд', home: 'Ваш дом' },
  stepOf: (n) => `Шаг ${n} из 4`,
  skip: 'Пропустить', next: 'Дальше',
  seatTitle: 'Войдите через Claude',
  seatSub: 'Мозг думает по подписке Claude, которая у вас уже есть. Войдите один раз: три шага ниже, около двух минут. Пароль остаётся у Claude.',
  seatLocal: 'Сначала войдите. Кнопка, нажатая до входа, подождёт здесь и сама запустится после входа. Переезд (шаг 3) работает уже сейчас.',
  seatDone: 'Вход выполнен.',
  waysTitle: 'Как вы хотите здесь работать?',
  waysSub: 'Нажмите, чтобы выбрать. То, что не выбрано, просто не показывается на главной; изменить можно в любой момент в Настройках.',
  waysKeep: 'Оставить так',
  waysAlways: 'всегда',
  about: {
    chat: ['разговор', 'говорите с мозгом один на один; всё остальное начинается отсюда'],
    decisions: ['решения', 'одно решение за другим, на каждое «да» или «нет»; «да» запускает работу'],
    systems: ['страница проектов', 'каждый проект плиткой со своим разговором рядом, чтобы видеть все сразу'],
    talkthrough: ['наговорить', 'нажмите запись и говорите свободно несколько минут; мозг разрежет это на мысли и разложит'],
    thoughts: ['просто мысли', 'напишите или скажите мысль, она сохраняется на потом, без ответа'],
    phone: ['голосовые с телефона', 'отправьте голосовое боту мозга; оно ложится на ленту и разбирается так же'],
    sidepane: ['боковая панель', 'разговоры, доска, агенты и экспорт открываются рядом с разговором'],
    terminal: ['терминал', 'простая командная строка на вашем сервере, для шагов, которые делают только ваши руки'],
  },
  moveTitle: 'Переезд',
  moveSub: 'Перенесите сюда компьютер и разговоры с другими ИИ. Оба могут подождать; эта страница их помнит.',
  moveDone: 'Пока хватит',
  homeTitle: 'Это ваш дом',
  homeSub: 'Теперь эта страница открывается пустой и тихой: напишите или скажите, и мозг ответит. Карточки переезда остаются здесь, пока всё не перенесено.',
  homeGo: 'Открыть мой дом',
}


// MEMBERS-14 2026-11-23: Slovak, German, Greek, Rusyn. The assistant's words, not a native speaker's; one native read each
// before a handover (Rusyn most of all).
const SK = {
  names: { seat: 'Prihlásenie', ways: 'Spôsob práce', movein: 'Sťahovanie', home: 'Tvoj domov' },
  stepOf: (n) => `Krok ${n} zo 4`,
  skip: 'Teraz preskočiť', next: 'Ďalej',
  seatTitle: 'Prihlás sa cez Claude',
  seatSub: 'Tvoj mozog myslí s predplatným Claude, ktoré už máš. Prihlás sa raz: tri kroky nižšie, asi dve minúty. Heslo zostáva u Claude.',
  seatLocal: 'Najprv sa prihlás. Štart, ktorý stlačíš skôr, tu počká a spustí sa sám po prihlásení. Sťahovanie (krok 3) funguje už teraz.',
  seatDone: 'Prihlásené.',
  waysTitle: 'Ako tu chceš pracovať?',
  waysSub: 'Stlač a vyber. Čo vynecháš, len zmizne z domova; zmeniť to môžeš kedykoľvek v Nastaveniach.',
  waysKeep: 'Nechať takto',
  waysAlways: 'vždy',
  about: {
    chat: ['rozhovor', 'hovor s mozgom medzi štyrmi očami; všetko ostatné začína tu'],
    decisions: ['rozhodnutia', 'jedno rozhodnutie za druhým, na každé áno alebo nie; áno spustí prácu'],
    systems: ['stránka projektov', 'každý projekt ako dlaždica s vlastným rozhovorom, aby si videl všetky naraz'],
    talkthrough: ['nahovoriť', 'stlač nahrávanie a hovor voľne pár minút; mozog to rozdelí na myšlienky a zoradí'],
    thoughts: ['len myšlienky', 'napíš alebo povedz myšlienku, uloží sa na neskôr, bez odpovede'],
    phone: ['hlasovky z telefónu', 'pošli hlasovú správu botovi mozgu; pristane na páske a spracuje sa rovnako'],
    sidepane: ['bočný panel', 'rozhovory, nástenka, agenti a export sa otvárajú vedľa rozhovoru'],
    terminal: ['terminál', 'jednoduchý príkazový riadok na tvojom serveri, pre kroky, ktoré robia len tvoje ruky'],
  },
  moveTitle: 'Sťahovanie',
  moveSub: 'Prenes sem svoj počítač a rozhovory s inými AI. Oboje môže počkať; táto stránka si to pamätá.',
  moveDone: 'Zatiaľ stačí',
  homeTitle: 'Toto je tvoj domov',
  homeSub: 'Odteraz sa táto stránka otvára prázdna a tichá: napíš alebo povedz, a mozog odpovie. Karty sťahovania tu zostanú, kým nie je všetko prenesené.',
  homeGo: 'Otvoriť môj domov',
}

const DE = {
  names: { seat: 'Anmelden', ways: 'Arbeitsweise', movein: 'Einziehen', home: 'Dein Zuhause' },
  stepOf: (n) => `Schritt ${n} von 4`,
  skip: 'Jetzt überspringen', next: 'Weiter',
  seatTitle: 'Mit Claude anmelden',
  seatSub: 'Dein Brain denkt mit dem Claude-Abo, das du schon hast. Melde dich einmal an: drei Schritte unten, etwa zwei Minuten. Dein Passwort bleibt bei Claude.',
  seatLocal: 'Zuerst anmelden. Ein Start, den du vorher drückst, wartet hier und läuft nach der Anmeldung von selbst. Einziehen (Schritt 3) geht schon jetzt.',
  seatDone: 'Angemeldet.',
  waysTitle: 'Wie willst du hier arbeiten?',
  waysSub: 'Drück, um zu wählen. Was du weglässt, verschwindet nur vom Zuhause; ändern kannst du es jederzeit in den Einstellungen.',
  waysKeep: 'So lassen',
  waysAlways: 'immer an',
  about: {
    chat: ['Gespräch', 'sprich mit dem Brain unter vier Augen; alles andere fängt hier an'],
    decisions: ['Entscheidungen', 'eine Entscheidung nach der anderen, jede mit Ja oder Nein; Ja startet die Arbeit'],
    systems: ['Projektseite', 'jedes Projekt als Kachel mit eigenem Gespräch daneben, alle auf einen Blick'],
    talkthrough: ['einsprechen', 'Aufnahme drücken und ein paar Minuten frei reden; das Brain zerlegt es in Gedanken und ordnet sie'],
    thoughts: ['nur Gedanken', 'schreib oder sag einen Gedanken, er wird für später aufgehoben, ohne Antwort'],
    phone: ['Sprachnachrichten vom Handy', 'schick dem Bot des Brains eine Sprachnachricht; sie landet auf dem Band und wird genauso verarbeitet'],
    sidepane: ['Seitenleiste', 'Gespräche, Board, Agenten und Export öffnen sich neben dem Gespräch'],
    terminal: ['Terminal', 'eine einfache Kommandozeile auf deinem Server, für Schritte, die nur deine Hände machen'],
  },
  moveTitle: 'Einziehen',
  moveSub: 'Bring deinen Computer und deine Chats mit anderen KIs mit. Beides kann warten; diese Seite merkt es sich.',
  moveDone: 'Fürs Erste fertig',
  homeTitle: 'Das ist dein Zuhause',
  homeSub: 'Ab jetzt öffnet sich diese Seite leer und ruhig: schreib oder sprich, und dein Brain antwortet. Die Karten zum Einziehen bleiben hier, bis alles drin ist.',
  homeGo: 'Mein Zuhause öffnen',
}

const EL = {
  names: { seat: 'Σύνδεση', ways: 'Τρόποι δουλειάς', movein: 'Μετακόμιση', home: 'Το σπίτι σου' },
  stepOf: (n) => `Βήμα ${n} από 4`,
  skip: 'Παράλειψη για τώρα', next: 'Επόμενο',
  seatTitle: 'Σύνδεση με το Claude',
  seatSub: 'Το μυαλό σου σκέφτεται με τη συνδρομή Claude που ήδη έχεις. Συνδέσου μία φορά: τρία βήματα παρακάτω, περίπου δύο λεπτά. Ο κωδικός σου μένει στο Claude.',
  seatLocal: 'Πρώτα σύνδεση. Ό,τι πατήσεις πριν περιμένει εδώ και ξεκινά μόνο του μόλις συνδεθείς. Η μετακόμιση (βήμα 3) δουλεύει ήδη.',
  seatDone: 'Συνδέθηκες.',
  waysTitle: 'Πώς θέλεις να δουλεύεις εδώ;',
  waysSub: 'Πάτα για να διαλέξεις. Ό,τι αφήσεις έξω απλώς φεύγει από το σπίτι· το αλλάζεις όποτε θες στις Ρυθμίσεις.',
  waysKeep: 'Κράτα αυτά',
  waysAlways: 'πάντα',
  about: {
    chat: ['συζήτηση', 'μίλα με το μυαλό ένας προς έναν· όλα τα άλλα ξεκινούν από εδώ'],
    decisions: ['αποφάσεις', 'μία απόφαση τη φορά, ναι ή όχι στην καθεμία· το ναι ξεκινά τη δουλειά'],
    systems: ['σελίδα έργων', 'κάθε έργο ως πλακίδιο με τη δική του συζήτηση δίπλα, όλα με μια ματιά'],
    talkthrough: ['μίλα ελεύθερα', 'πάτα εγγραφή και μίλα λίγα λεπτά· το μυαλό το κόβει σε σκέψεις και τις τακτοποιεί'],
    thoughts: ['μόνο σκέψεις', 'γράψε ή πες μια σκέψη, φυλάγεται για αργότερα, χωρίς απάντηση'],
    phone: ['φωνητικά από το κινητό', 'στείλε φωνητικό στο bot του μυαλού· μπαίνει στην ταινία και επεξεργάζεται το ίδιο'],
    sidepane: ['πλαϊνό πάνελ', 'συζητήσεις, πίνακας, πράκτορες και εξαγωγή ανοίγουν δίπλα στη συζήτηση'],
    terminal: ['τερματικό', 'μια απλή γραμμή εντολών στον server σου, για βήματα που κάνουν μόνο τα χέρια σου'],
  },
  moveTitle: 'Μετακόμιση',
  moveSub: 'Φέρε εδώ τον υπολογιστή σου και τις συζητήσεις σου με άλλα AI. Και τα δύο μπορούν να περιμένουν· η σελίδα τα θυμάται.',
  moveDone: 'Αρκετά για τώρα',
  homeTitle: 'Αυτό είναι το σπίτι σου',
  homeSub: 'Από τώρα η σελίδα ανοίγει άδεια και ήσυχη: γράψε ή μίλα, και το μυαλό απαντά. Οι κάρτες μετακόμισης μένουν εδώ μέχρι να έρθουν όλα.',
  homeGo: 'Άνοιξε το σπίτι μου',
}

// Rusyn (Prešov Rusyn, Cyrillic): needs a native read before Julesa sees it.
const RUE = {
  names: { seat: 'Приголошіня', ways: 'Як робити', movein: 'Переселїня', home: 'Твій дом' },
  stepOf: (n) => `Крок ${n} з 4`,
  skip: 'Теперь перескочіти', next: 'Далше',
  seatTitle: 'Приголось ся через Claude',
  seatSub: 'Твій мозок думать з предплатным Claude, котре уж маєш. Приголось ся раз: три кроки долу, коло двох мінут. Гесло остане у Claude.',
  seatLocal: 'Найперше ся приголось. Старт, котрый стиснеш скорше, ту почекать і пустить ся сам по приголошіню. Переселїня (крок 3) уж робить.',
  seatDone: 'Приголошена.',
  waysTitle: 'Як хочеш ту робити?',
  waysSub: 'Стисни і выбер. Што лишыш, лем щезне з дому; змінити можеш коли хочеш в Наставлїнях.',
  waysKeep: 'Лишыти так',
  waysAlways: 'все',
  about: {
    chat: ['бисїда', 'бисїдуй з мозком сам на сам; вшытко інше ту зачінать'],
    decisions: ['рїшіня', 'єдно рїшіня за другым, на кажде гей або нїт; гей пустить роботу'],
    systems: ['сторінка проєктів', 'кажный проєкт як плитка з власнов бисїдов, вшыткы нараз'],
    talkthrough: ['наговорити', 'стисни награваня і говор вольно пару мінут; мозок то розділить на думкы і поскладать'],
    thoughts: ['лем думкы', 'напиш або повіч думку, схопить ся на пізнїше, без одповіди'],
    phone: ['голосовы з телефону', 'пошли голосову справу ботови мозку; ляже на пасок і спрацує ся так само'],
    sidepane: ['бочный панел', 'бисїды, табля, аґенты і експорт ся отворяють побіч бисїды'],
    terminal: ['термінал', 'простый командный рядок на твоїм сервері, про кроки, котры робиш лем ты сама'],
  },
  moveTitle: 'Переселїня',
  moveSub: 'Принеси сюды свій компютер і бисїды з іншыма AI. Обоє може почекати; тота сторінка собі то памятать.',
  moveDone: 'Покы досить',
  homeTitle: 'То є твій дом',
  homeSub: 'Од теперь ся тота сторінка отворять порожня і тиха: напиш або повіч, і мозок одповість. Карты переселїня ту остануть, покы вшытко не буде ту.',
  homeGo: 'Отворити мій дом',
}

const FIRST_TEXT = { en: EN, ru: RU, sk: SK, de: DE, el: EL, rue: RUE }
const firstWords = (lang) => FIRST_TEXT[lang] || FIRST_TEXT.en

module.exports = { ORDER, currentStep, showFirstRun, NEWCOMER, startPicks, togglePick, FIRST_TEXT, firstWords }
