// The console's own words in the brain's console language (2026-11-12, HANDOFF-2: Elena and Alexander
// opened their consoles on the English page). The language is the bridge's layout.json key `lang`
// (scripts/cc/cc_layout.py LANGS; GET /cc/layout returns it, POST /cc/layout/lang sets it). Unset is
// English. Only the words a person meets in the first minutes are here; everything else stays English.
// tests/test_cc_layout.py checks every language has every key and that LANGS matches the box's list.

const LANGS = ['en', 'ru']

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
}

const TEXT = { en: EN, ru: RU }

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

module.exports = { LANGS, TEXT, words, langOf, stepLabel, stepSub }
