// The console's own words in the brain's console language (2026-11-12, HANDOFF-2: Elena and Alexander
// opened their consoles on the English page). The language is the bridge's layout.json key `lang`
// (scripts/cc/cc_layout.py LANGS; GET /cc/layout returns it, POST /cc/layout/lang sets it). Unset is
// English. Only the words a person meets in the first minutes are here; everything else stays English.
// tests/test_cc_layout.py checks every language has every key and that LANGS matches the box's list.

// MEMBERS-14 2026-11-23: sk (Martin), de (Johanna), el (Christos), rue (Rusyn, Julesa). The words in sk, de, el
// and rue are the assistant's, not a native speaker's: each needs one native read before a handover (rue most).
const LANGS = ['en', 'ru', 'sk', 'de', 'el', 'rue']
// each language in its own name, for the switch at the top of every screen
const NATIVE = { en: 'English', ru: 'Русский', sk: 'Slovenčina', de: 'Deutsch', el: 'Ελληνικά', rue: 'Русиньскый' }

const EN = {
  title: 'Talk to your brain',
  files: (n, of) => `Drop ten files (${n} of ${of})`,
  filesSub: 'Anything in your own words works best: notes, a CV, emails you wrote, a project readme, a decision you made and why, a list of what you are working on. The brain answers from what you give it.',
  openApp: (name) => `Open ${name}`,
  guide: ['New here? ', 'The guide', ' explains what this brain can do, with a seven-step tutorial that checks itself. Or type /help.'],
  empty: 'This surface reasons over what the brain remembers and over its own files on its own server. Ask what the brain knows about you, what changed recently, or what a document says. It reads; it does not change anything from here.',
  ask: 'Ask your brain. Enter sends, Shift+Enter for a new line. / for commands.',
  send: 'send',
  attach: 'attach',
  talk: 'talk',
  stop: 'stop',
  // the quiet home (PARENTS-HOME-1, 2026-11-15): the five menu entries and the press that shows the rest
  menu: { _chat: 'Chat', start: 'Start', _knowledge: 'Knowledge', _files: 'Files', _settings: 'Settings' },
  menuButton: 'menu',
  menuRest: 'everything',
  paneFull: 'Full screen', paneBack: 'Back', paneClose: 'Close',
}

const RU = {
  title: 'Разговор с вашим мозгом',
  files: (n, of) => `Положите десять файлов (${n} из ${of})`,
  filesSub: 'Лучше всего то, что написано вашими словами: заметки, резюме, ваши письма, описание проекта, решение и его причины, список того, над чем вы работаете. Мозг отвечает из того, что вы ему дали.',
  openApp: (name) => `Откройте ${name}`,
  guide: ['Вы здесь впервые? ', 'Путеводитель', ' рассказывает, что умеет этот мозг, и проводит по семи шагам. Или наберите /help.'],
  empty: 'Здесь мозг думает над тем, что он помнит, и над своими файлами на своём сервере. Спросите, что он знает о вас, что изменилось недавно или что сказано в документе. Он читает; отсюда он ничего не меняет.',
  ask: 'Спросите ваш мозг. Enter отправляет, Shift+Enter переносит строку.',
  send: 'отправить',
  attach: 'файл',
  talk: 'голос',
  stop: 'стоп',
  menu: { _chat: 'Разговор', start: 'Начало', _knowledge: 'Знания', _files: 'Файлы', _settings: 'Настройки' },
  menuButton: 'меню',
  menuRest: 'всё остальное',
  paneFull: 'Во весь экран', paneBack: 'Назад', paneClose: 'Закрыть',
}


const SK = {
  title: 'Hovor so svojím mozgom',
  files: (n, of) => `Vlož desať súborov (${n} z ${of})`,
  filesSub: 'Najlepšie funguje to, čo je napísané tvojimi slovami: poznámky, životopis, tvoje maily, popis projektu, rozhodnutie a jeho dôvody, zoznam toho, na čom pracuješ. Mozog odpovedá z toho, čo mu dáš.',
  openApp: (name) => `Otvor ${name}`,
  guide: ['Si tu prvýkrát? ', 'Sprievodca', ' ukáže, čo tento mozog vie, v siedmich krokoch. Alebo napíš /help.'],
  empty: 'Tu mozog premýšľa nad tým, čo si pamätá, a nad svojimi súbormi na svojom serveri. Spýtaj sa, čo o tebe vie, čo sa nedávno zmenilo alebo čo stojí v dokumente. Číta; odtiaľto nič nemení.',
  ask: 'Spýtaj sa svojho mozgu. Enter odošle, Shift+Enter nový riadok.',
  send: 'odoslať',
  attach: 'súbor',
  talk: 'hlas',
  stop: 'stop',
  menu: { _chat: 'Rozhovor', start: 'Začiatok', _knowledge: 'Vedomosti', _files: 'Súbory', _settings: 'Nastavenia' },
  menuButton: 'menu',
  menuRest: 'všetko ostatné',
  paneFull: 'Na celú obrazovku', paneBack: 'Späť', paneClose: 'Zavrieť',
}

const DE = {
  title: 'Sprich mit deinem Brain',
  files: (n, of) => `Leg zehn Dateien ab (${n} von ${of})`,
  filesSub: 'Am besten funktioniert, was in deinen eigenen Worten geschrieben ist: Notizen, ein Lebenslauf, deine Mails, eine Projektbeschreibung, eine Entscheidung und warum, eine Liste deiner Arbeit. Das Brain antwortet aus dem, was du ihm gibst.',
  openApp: (name) => `${name} öffnen`,
  guide: ['Neu hier? ', 'Die Anleitung', ' zeigt in sieben Schritten, was dieses Brain kann. Oder tippe /help.'],
  empty: 'Hier denkt das Brain über das nach, was es sich gemerkt hat, und über seine eigenen Dateien auf seinem eigenen Server. Frag, was es über dich weiß, was sich zuletzt geändert hat oder was in einem Dokument steht. Es liest; von hier aus ändert es nichts.',
  ask: 'Frag dein Brain. Enter sendet, Shift+Enter für eine neue Zeile.',
  send: 'senden',
  attach: 'Datei',
  talk: 'sprechen',
  stop: 'stopp',
  menu: { _chat: 'Gespräch', start: 'Start', _knowledge: 'Wissen', _files: 'Dateien', _settings: 'Einstellungen' },
  menuButton: 'Menü',
  menuRest: 'alles andere',
  paneFull: 'Vollbild', paneBack: 'Zurück', paneClose: 'Schließen',
}

const EL = {
  title: 'Μίλα με το μυαλό σου',
  files: (n, of) => `Βάλε δέκα αρχεία (${n} από ${of})`,
  filesSub: 'Δουλεύει καλύτερα ό,τι είναι γραμμένο με δικά σου λόγια: σημειώσεις, βιογραφικό, τα μέιλ σου, μια περιγραφή έργου, μια απόφαση και το γιατί, μια λίστα με ό,τι κάνεις. Το μυαλό απαντά από ό,τι του δίνεις.',
  openApp: (name) => `Άνοιξε ${name}`,
  guide: ['Πρώτη φορά εδώ; ', 'Ο οδηγός', ' δείχνει σε επτά βήματα τι μπορεί αυτό το μυαλό. Ή γράψε /help.'],
  empty: 'Εδώ το μυαλό σκέφτεται πάνω σε ό,τι θυμάται και στα δικά του αρχεία, στον δικό του server. Ρώτα τι ξέρει για σένα, τι άλλαξε πρόσφατα ή τι λέει ένα έγγραφο. Διαβάζει· από εδώ δεν αλλάζει τίποτα.',
  ask: 'Ρώτα το μυαλό σου. Το Enter στέλνει, Shift+Enter για νέα γραμμή.',
  send: 'αποστολή',
  attach: 'αρχείο',
  talk: 'φωνή',
  stop: 'στοπ',
  menu: { _chat: 'Συζήτηση', start: 'Αρχή', _knowledge: 'Γνώση', _files: 'Αρχεία', _settings: 'Ρυθμίσεις' },
  menuButton: 'μενού',
  menuRest: 'όλα τα άλλα',
  paneFull: 'Πλήρης οθόνη', paneBack: 'Πίσω', paneClose: 'Κλείσιμο',
}

// Rusyn (Prešov Rusyn, Cyrillic): the assistant's best attempt, needs a native read before Julesa sees it.
const RUE = {
  title: 'Бисїдуй зо своїм мозком',
  files: (n, of) => `Положты десять файлів (${n} з ${of})`,
  filesSub: 'Найлїпше робить тото, што єсь написала своїма словами: запискы, жывотопис, твої листы, опис проєкту, рїшіня і чом, зознам того, на чім робиш. Мозок одповідать з того, што му даш.',
  openApp: (name) => `Отворь ${name}`,
  guide: ['Ту єсь першый раз? ', 'Провідник', ' у семох кроках укаже, што тот мозок знать. Або напиш /help.'],
  empty: 'Ту мозок думать над тым, што собі памятать, і над своїма файлами на своїм сервері. Спытай ся, што о тобі знать, што ся недавно змінило, або што стоїть в документї. Він чітать; одты нич не мінять.',
  ask: 'Спытай ся свого мозку. Enter посылать, Shift+Enter новый рядок.',
  send: 'послати',
  attach: 'файл',
  talk: 'голос',
  stop: 'стоп',
  menu: { _chat: 'Бисїда', start: 'Початок', _knowledge: 'Знаня', _files: 'Файлы', _settings: 'Наставлїня' },
  menuButton: 'меню',
  menuRest: 'вшытко остатнє',
  paneFull: 'На цїлу образовку', paneBack: 'Назад', paneClose: 'Заперти',
}

const TEXT = { en: EN, ru: RU, sk: SK, de: DE, el: EL, rue: RUE }

function langOf(v) { return LANGS.includes(v) ? v : 'en' }

// words(lang) -> the table for that language, English for anything unknown.
function words(lang) { return TEXT[langOf(lang)] }

// The first-use steps come from the api in English; their words are redrawn here by step key.
function stepLabel(lang, s) {
  const w = words(lang)
  if (langOf(lang) === 'en' || !s) return s && s.label
  if (s.key === 'files' && s.progress) return w.files(Math.min(s.progress.done, s.progress.target), s.progress.target)
  if (s.key === 'app' && /^Open /.test(s.label || '')) return w.openApp(s.label.slice(5))
  return s.label
}
function stepSub(lang, s) {
  if (langOf(lang) !== 'en' && s && s.key === 'files') return words(lang).filesSub
  return s && s.sub
}

module.exports = { LANGS, NATIVE, TEXT, words, langOf, stepLabel, stepSub }
