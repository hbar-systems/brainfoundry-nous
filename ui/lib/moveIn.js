// Moving in (PARENTS-HOME-1 addendum 2, hbar 2026-11-15 on a member's console: "WHERE IS THERE ANY
// INDICATION OF IMPORT"). On the quiet home, until it is done, the first thing on screen is moving the
// person's past in: their ChatGPT (or Claude) history, then their documents. Both cards drop files on
// the home itself and use the Knowledge page's own doors (/documents/import-chats, /documents/upload
// under a permit, /documents/approve-all); no new api. This file holds the words (by the console's lang
// key) and the pure state rules; ui/components/MoveInCards.js draws them. Mechanism only: no person here.

// The names an imported conversation gets in memory (scripts/import_chats.py prep): chatgpt_<date>_...,
// claude_<date>_..., claude-project_<date>_...
const CHAT_DOC = /^(chatgpt|claude|claude-project)_/

// How many conversations the home asks the import to take: the import's own ceiling (api/chat_import.py
// NEWEST_MAX), so a person's whole history comes, not the Knowledge page's default newest 50.
const HOME_NEWEST = 500

// chatState(docs, pending, waiting) -> { step, n, at }
//   docs: GET /documents rows ({ name, last_updated }); pending: proposals still waiting ({ filename });
//   waiting: the day the person said the export was asked for (this browser), or null.
//   step: 'done' (conversations are in memory) | 'pending' (imported, waiting for their yes) |
//         'waiting' (export asked for, the email not here yet) | 'new'.
function chatState(docs, pending, waiting) {
  const inMem = (Array.isArray(docs) ? docs : []).filter(d => d && CHAT_DOC.test(String(d.name || '')))
  const wait = (Array.isArray(pending) ? pending : []).filter(p => p && CHAT_DOC.test(String(p.filename || '')))
  if (inMem.length) {
    const at = inMem.map(d => String(d.last_updated || '')).filter(Boolean).sort().pop() || null
    return { step: 'done', n: inMem.length, at, waitingYes: wait.length }
  }
  if (wait.length) return { step: 'pending', n: wait.length, at: null, waitingYes: wait.length }
  if (waiting) return { step: 'waiting', n: 0, at: waiting, waitingYes: 0 }
  return { step: 'new', n: 0, at: null, waitingYes: 0 }
}

// docState(mark, pending) -> { step, n, at }: mark is what this home recorded after the person's last
// documents went in ({ n, at }, this browser); pending: document proposals that are not conversations.
function docState(mark, pending) {
  const wait = (Array.isArray(pending) ? pending : []).filter(p => p && !CHAT_DOC.test(String(p.filename || '')))
  if (mark && Number(mark.n) > 0) return { step: 'done', n: Number(mark.n), at: mark.at || null, waitingYes: wait.length }
  if (wait.length) return { step: 'pending', n: wait.length, at: null, waitingYes: wait.length }
  return { step: 'new', n: 0, at: null, waitingYes: 0 }
}

// Both in: the cards fold into one quiet line.
const folded = (chat, doc) => !!(chat && doc && chat.step === 'done' && doc.step === 'done')

const MOVE_WAIT_KEY = 'cc.movein.export-asked'
const MOVE_DOCS_KEY = 'cc.movein.docs'

const MONTHS = {
  ru: ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
}
// day(lang, iso) -> "15 ноября" / "15 November"; null for anything unreadable
function day(lang, iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''))
  if (!m) return null
  const names = MONTHS[lang === 'ru' ? 'ru' : 'en']
  return `${Number(m[3])} ${names[Number(m[2]) - 1]}`
}

// Russian plural: plural(n, ['разговор', 'разговора', 'разговоров'])
function ruPlural(n, f) {
  const a = Math.abs(n) % 100, b = a % 10
  if (a > 10 && a < 20) return f[2]
  if (b > 1 && b < 5) return f[1]
  if (b === 1) return f[0]
  return f[2]
}

const EN = {
  chatTitle: 'Bring your ChatGPT conversations here',
  chatSteps: [
    ['Open ', 'chatgpt.com', ', then Settings, Data controls, Export data.'],
    ['An email comes with a download link. Download the .zip.'],
    ['Drop the .zip on this card, or press the button.'],
  ],
  chatPick: 'Choose the .zip',
  chatAsked: 'I asked for the export',
  chatReading: (name) => `Reading ${name}...`,
  chatFound: (n, took) => `Found ${n} conversations${took < n ? `, the newest ${took} taken` : ''}.`,
  docTitle: 'Bring your documents here',
  docSub: 'Lectures, texts, slides, letters. Drop them on this card.',
  docPick: 'Choose files',
  docWhole: 'A whole folder from the computer',
  docSending: (i, n) => `Sending ${i} of ${n}...`,
  remember: (n) => `Remember ${n === 1 ? 'it' : `all ${n}`}`,
  remembering: (d, n) => `Remembering ${d} of ${n}...`,
  state: {
    new: 'not started',
    waiting: (d) => `waiting for the email${d ? ` since ${d}` : ''}`,
    pending: (n) => `${n} waiting for your yes`,
    chatDone: (n, d) => `${n} conversation${n === 1 ? '' : 's'} moved in${d ? ` on ${d}` : ''}`,
    docDone: (n, d) => `${n} document${n === 1 ? '' : 's'} moved in${d ? ` on ${d}` : ''}`,
  },
  dropHere: 'Drop it here',
  folded: (c, d) => `Moved in: ${c} conversations and ${d} documents.`,
  foldedMore: 'bring more',
  failed: 'That did not work.',
  notZip: 'This card takes the .zip from the export email.',
}

const RU = {
  chatTitle: 'Перенесите сюда свои разговоры с ChatGPT',
  chatSteps: [
    ['Откройте ', 'chatgpt.com', ', затем Настройки, Управление данными, Экспорт данных.'],
    ['Придёт письмо со ссылкой. Скачайте архив .zip.'],
    ['Перетащите архив на эту карточку или нажмите кнопку.'],
  ],
  chatPick: 'Выбрать архив',
  chatAsked: 'Экспорт уже запрошен',
  chatReading: (name) => `Читаю ${name}...`,
  chatFound: (n, took) => `Найдено ${n} ${ruPlural(n, ['разговор', 'разговора', 'разговоров'])}${took < n ? `, взяты ${took} последних` : ''}.`,
  docTitle: 'Перенесите сюда свои документы',
  docSub: 'Лекции, тексты, слайды, письма. Перетащите их на эту карточку.',
  docPick: 'Выбрать файлы',
  docWhole: 'Целую папку с компьютера',
  docSending: (i, n) => `Отправляю ${i} из ${n}...`,
  remember: (n) => (n === 1 ? 'Запомнить' : `Запомнить все ${n}`),
  remembering: (d, n) => `Запоминаю ${d} из ${n}...`,
  state: {
    new: 'ещё не начато',
    waiting: (d) => `ждём письмо${d ? ` с ${d}` : ''}`,
    pending: (n) => `${n} ${ruPlural(n, ['ждёт', 'ждут', 'ждут'])} вашего «да»`,
    chatDone: (n, d) => `${ruPlural(n, ['перенесён', 'перенесено', 'перенесено'])} ${n} ${ruPlural(n, ['разговор', 'разговора', 'разговоров'])}${d ? `, ${d}` : ''}`,
    docDone: (n, d) => `${ruPlural(n, ['перенесён', 'перенесено', 'перенесено'])} ${n} ${ruPlural(n, ['документ', 'документа', 'документов'])}${d ? `, ${d}` : ''}`,
  },
  dropHere: 'Отпустите здесь',
  folded: (c, d) => `Перенесено: ${c} ${ruPlural(c, ['разговор', 'разговора', 'разговоров'])} и ${d} ${ruPlural(d, ['документ', 'документа', 'документов'])}.`,
  foldedMore: 'добавить ещё',
  failed: 'Не получилось.',
  notZip: 'Сюда нужен архив .zip из письма с экспортом.',
}

const MOVE_TEXT = { en: EN, ru: RU }
const moveWords = (lang) => MOVE_TEXT[lang === 'ru' ? 'ru' : 'en']

module.exports = { CHAT_DOC, HOME_NEWEST, chatState, docState, folded, MOVE_WAIT_KEY, MOVE_DOCS_KEY, day, ruPlural, MOVE_TEXT, moveWords }
