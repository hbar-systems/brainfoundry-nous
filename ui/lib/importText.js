// The Knowledge page's two import cards in the console's language (PARENTS-HOME-1 addendum 2,
// 2026-11-15: "translate the import cards on /upload too, so nothing a member sees is English").
// The language is the bridge's layout.json key lang (GET /cc/layout), English when unset; the same key
// ui/lib/consoleText.js reads. tests/test_move_in.py checks both languages carry every key.
const { ruPlural } = require('./moveIn')
const VENDOR = { chatgpt: 'ChatGPT', claude: 'Claude', gemini: 'Gemini', deepseek: 'DeepSeek', grok: 'Grok', copilot: 'Copilot', perplexity: 'Perplexity', lechat: 'Le Chat', codex: 'Codex', 'claude-code': 'Claude Code', pasted: 'a pasted conversation' }

const EN = {
  pageTitle: 'Knowledge — Upload & Search',
  chatTitle: 'Import your chats from ChatGPT, Claude and other AIs',
  unverified: 'format not yet checked on a real export',
  chatGpt: 'ChatGPT: chatgpt.com, Settings > Data controls > Export data. The zip comes by email.',
  claude: 'Claude: claude.ai, Settings > Privacy > Export data. The zip comes by email.',
  chatPick: 'Choose the export zip',
  chatReading: (n) => `Reading ${n}...`,
  chatFailed: (s) => `The import failed (${s}).`,
  chatLine: (j) => {
    const from = (j.sources || []).map((x) => VENDOR[x] || x).join(' and ')
    let l = `Found ${j.conversations} conversations from ${from}. `
    l += j.selected < j.conversations ? `Took the newest ${j.selected}. ` : `Took all ${j.selected}. `
    l += `${j.proposed} wait below under Pending memory proposals; nothing is remembered until you approve.`
    if (j.flagged) l += ` ${j.flagged} look like they carry instructions to a model; read those before approving.`
    if (j.stopped) l += ` Stopped early: ${j.stopped}`
    return l
  },
  lapTitle: 'Bring files from your computer',
  lapSub1: 'A small program runs on your computer and asks you, folder by folder, what to bring.',
  lapSub2: 'It never sends passwords, keys or hidden files. Documents wait below for your yes; music is kept as files for your music tools.',
  lapStart: 'Start', lapStarting: 'Starting...', lapCouldNot: (s) => `Could not start (${s}).`,
  lapMacHow: 'Open Terminal (Applications, Utilities, Terminal), paste this line, press Return:',
  lapWinHow: 'Open PowerShell (Start menu, type PowerShell), paste this line, press Enter:',
  lapCopy: 'Copy', lapCopied: 'Copied', lapNew: 'New line',
  lapMacTip: 'If your Mac offers to install developer tools, say yes, then paste the line again.',
  lapWinTip: 'If Windows opens the Microsoft Store for Python, install it, then paste the line again.',
  lapOnce: (t) => `This line works once, until ${t}. Keep it to yourself.`,
  lapNow: 'Arriving now', lapLast: 'Last time',
  lapDocs: (n) => `${n} document${n === 1 ? '' : 's'}`,
  lapMusic: (n) => `, ${n} music file${n === 1 ? '' : 's'}`,
  lapWaiting: 'Waiting for your yes under Pending memory proposals below:',
  lapMore: (n) => `and ${n} more`,
  lapKeptIn: 'Kept for your music tools (in your in folder, listed in audio.tsv):',
  lapKept: 'Kept on your brain for your music tools:',
  cont: 'Continue here',
  contTitle: 'Open a new thread that picks up this conversation',
}

const docs = (n) => `${n} ${ruPlural(n, ['документ', 'документа', 'документов'])}`
const RU = {
  pageTitle: 'Знания: перенести и найти',
  chatTitle: 'Перенести разговоры с ChatGPT, Claude и другими ИИ',
  unverified: 'формат ещё не проверен на настоящем экспорте',
  chatGpt: 'ChatGPT: chatgpt.com, Настройки > Управление данными > Экспорт данных. Архив .zip придёт по почте.',
  claude: 'Claude: claude.ai, Settings > Privacy > Export data. Архив .zip придёт по почте.',
  chatPick: 'Выбрать архив',
  chatReading: (n) => `Читаю ${n}...`,
  chatFailed: (s) => `Перенести не получилось (${s}).`,
  chatLine: (j) => {
    const c = j.conversations
    let l = `Найдено ${c} ${ruPlural(c, ['разговор', 'разговора', 'разговоров'])}. `
    l += j.selected < c ? `Взяты ${j.selected} последних. ` : `Взяты все ${j.selected}. `
    l += `${j.proposed} ${ruPlural(j.proposed, ['ждёт', 'ждут', 'ждут'])} ниже вашего «да»; без него ничего не запоминается.`
    if (j.flagged) l += ` ${j.flagged} похожи на указания для модели; прочитайте их перед «да».`
    if (j.stopped) l += ` Остановлено раньше: ${j.stopped}`
    return l
  },
  lapTitle: 'Перенести файлы с компьютера',
  lapSub1: 'На вашем компьютере запускается маленькая программа и спрашивает, папку за папкой, что перенести.',
  lapSub2: 'Она никогда не отправляет пароли, ключи и скрытые файлы. Документы ждут ниже вашего «да»; музыка хранится файлами.',
  lapStart: 'Начать', lapStarting: 'Начинаю...', lapCouldNot: (s) => `Не получилось начать (${s}).`,
  lapMacHow: 'Откройте Терминал (Программы, Утилиты, Терминал), вставьте эту строку и нажмите Return:',
  lapWinHow: 'Откройте PowerShell (меню Пуск, наберите PowerShell), вставьте эту строку и нажмите Enter:',
  lapCopy: 'Скопировать', lapCopied: 'Скопировано', lapNew: 'Новая строка',
  lapMacTip: 'Если Mac предложит установить инструменты разработчика, согласитесь и вставьте строку ещё раз.',
  lapWinTip: 'Если Windows откроет Microsoft Store для Python, установите его и вставьте строку ещё раз.',
  lapOnce: (t) => `Строка работает один раз, до ${t}. Никому её не показывайте.`,
  lapNow: 'Приходит сейчас', lapLast: 'В прошлый раз',
  lapDocs: docs,
  lapMusic: (n) => `, ${n} ${ruPlural(n, ['музыкальный файл', 'музыкальных файла', 'музыкальных файлов'])}`,
  lapWaiting: 'Ждут вашего «да» ниже:',
  lapMore: (n) => `и ещё ${n}`,
  lapKeptIn: 'Сохранено для музыки (в папке in, список в audio.tsv):',
  lapKept: 'Сохранено в мозге для музыки:',
  cont: 'Продолжить здесь',
  contTitle: 'Открыть новый разговор, который продолжает этот',
}

const IMPORT_TEXT = { en: EN, ru: RU }
const importWords = (lang) => IMPORT_TEXT[lang === 'ru' ? 'ru' : 'en']
module.exports = { IMPORT_TEXT, importWords }
