// Moving in, two doors (MOVE-IN-2, hbar 2026-11-16: "the user switches over to the brain ... their entire
// computer ... sign in with their Claude or ChatGPT ... have their data exported and imported here and
// continue working from there"). The words (by the console's lang key) and the pure rules for:
// 1. the whole-computer card: the survey run's plan (api/laptop_survey.py), one yes per group or all proposed;
// 2. the chats card: every AI's export, the paste fallback, and "Continue here" on each conversation.
// ui/components/MoveInCards.js draws them. tests/test_move_in_plan.py runs this file under node.
const { ruPlural } = require('./moveIn')

// What the home first picks: every group the brain did not propose to leave.
function defaultPicks(groups) {
  const out = {}
  for (const g of Array.isArray(groups) ? groups : []) out[g.id] = g.proposal !== 'leave'
  return out
}

// The chosen groups' numbers, and whether they are exactly the proposed ones.
function pickTotals(groups, picks) {
  let n = 0, files = 0, bytes = 0, same = true
  for (const g of Array.isArray(groups) ? groups : []) {
    const on = !!(picks && picks[g.id])
    if (on !== (g.proposal !== 'leave')) same = false
    if (!on) continue
    n += 1; files += g.files || 0; bytes += g.bytes || 0
  }
  return { groups: n, files, bytes, proposed: same }
}

// Over the run's caps (the status's run.max_files / run.max_bytes): the words say the numbers.
function overCaps(t, run) {
  if (!run) return false
  return t.files > (run.max_files || Infinity) || t.bytes > (run.max_bytes || Infinity)
}

// How far the pull is: arrived rows of this run against the chosen total.
function pullState(run, survey) {
  const arrived = (run && Array.isArray(run.arrived)) ? run.arrived : []
  const docs = arrived.filter(a => a.kind === 'knowledge').length
  const kept = arrived.filter(a => a.kind === 'audio' || a.kind === 'media').length
  const total = survey && survey.chosen && Array.isArray(survey.groups)
    ? survey.groups.filter(g => survey.chosen.includes(g.id)).reduce((s, g) => s + (g.files || 0), 0) : 0
  return { docs, kept, done: docs + kept, total, open: !!(run && run.open) }
}

// The step of the whole-computer card: start | line (token shown, waiting for the computer) |
// plan (the list is in, choose) | pulling | pulled (the run closed after a choice).
function surveyStep(run, survey, minted) {
  if (!run || !run.survey) return minted ? 'line' : 'start'
  if (!survey || survey.state === 'waiting') return run.open ? 'line' : 'start'
  if (survey.state === 'plan') return run.open ? 'plan' : 'start'
  return run.open ? 'pulling' : 'pulled'
}

function fmtBytes(n) {
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, x = Number(n) || 0
  while (x >= 1024 && i < u.length - 1) { x /= 1024; i += 1 }
  return i === 0 ? `${x} ${u[i]}` : `${x.toFixed(x < 10 ? 1 : 0)} ${u[i]}`
}

// The one line for the person's computer (SPOKE-3, 2026-11-16): the dial-out agent from the person's own
// brain, plain bash on a Mac (no Python, no app, so no "unidentified developer" warning) and Windows
// PowerShell as it ships. The key travels in the line, never in the address. api/laptop_agent.py renders it.
function agentUrls(base, lang) {
  const q = lang === 'ru' ? '?lang=ru' : ''
  return { mac: `${base}/laptop/agent.sh${q}`, windows: `${base}/laptop/agent.ps1${q}` }
}
// The fallback under it (MOVE-IN-2): the Python helper, for a computer where the line above does not run.
function helperCommands(base, token) {
  const helper = `${base}/documents/import-laptop/helper.py`
  return {
    mac: `curl -fsSLo brain_import.py "${helper}" && python3 brain_import.py --survey --brain "${base}" --token ${token}`,
    windows: `curl.exe -fsSLo brain_import.py "${helper}"; python brain_import.py --survey --brain "${base}" --token ${token}`,
  }
}
function surveyCommands(base, token, lang) {
  const u = agentUrls(base, lang)
  return {
    mac: `curl -fsSL ${u.mac} | bash -s -- ${token}`,
    windows: `$env:BRAIN_TOKEN="${token}"; irm ${u.windows} | iex`,
  }
}

// The chats list on the home: "Your chats from ChatGPT and Claude".
function vendorsOf(rows) {
  const seen = []
  for (const r of Array.isArray(rows) ? rows : []) {
    const v = r && (r.vendor || r.source)
    if (v && !seen.includes(v)) seen.push(v)
  }
  return seen
}
const continueHref = (name, lang) => `/?continue=${encodeURIComponent(String(name || ''))}${lang === 'ru' ? '&lang=ru' : ''}`

const EN = {
  compTitle: 'Bring in this computer',
  compSub: 'You copy one line into your computer. It looks through your files and your cloud folders, names, sizes and dates only, and shows the list here. You say yes to what comes; only that is sent.',
  compAgents: 'Your Codex and Claude Code history on this computer comes along too, each session as one conversation.',
  compNever: 'Passwords, keys, mail and browser data are never sent. Nothing is installed and nothing stays running: when it is done, it is gone. Your brain cannot reach into the computer; the line only calls out to your brain.',
  compNoApp: 'There is no app to download, so the computer shows no warning about an unknown developer.',
  compRead: 'Read what this line runs',
  compHelper: 'If this line does not run',
  compHelperSub: 'The same with the Python helper (the computer needs Python 3). Same key, same list, same yes here.',
  compMacAllow: 'Your Mac may ask whether Terminal may open Desktop, Documents or Downloads: press Allow. Folders you do not allow stay private and are only named here.',
  compPhone: 'From the phone: put photos and files in iCloud Drive or Google Drive; the run on the computer finds them there.',
  compStart: 'Start', compStarting: 'Starting...',
  compMacHow: 'On the Mac: open Terminal (Applications, Utilities, Terminal), paste this line, press Return.',
  compWinHow: 'On Windows: open PowerShell (Start menu, type PowerShell), paste this line, press Enter. No administrator needed.',
  compCopy: 'Copy', compCopied: 'Copied', compNew: 'New line',
  compOnce: (t) => `The line works once, until ${t}. Keep it to yourself. Keep the window open until it says Done.`,
  compWaiting: 'Waiting for your computer...',
  compPlan: (n, f, b) => `Your computer, in ${n} groups: ${f} files, ${b}. Proposed:`,
  kind: { knowledge: 'into Knowledge', files: 'kept as files', leave: 'stays on the computer' },
  why: { documents: 'documents', music: 'music', pictures: 'pictures', code: 'code, has its own git', old_downloads: 'downloads older than two years', many_pictures: 'many pictures, say yes to keep them', screenshots: 'screenshots', codex_history: 'your Codex history, one conversation per session', claude_code_history: 'your Claude Code history, one conversation per session' },
  files: (n) => `${n} file${n === 1 ? '' : 's'}`,
  showAll: (n) => `show all ${n}`,
  bringProposed: (f, b) => `Bring all proposed (${f} files, ${b})`,
  bringChosen: (f, b) => `Bring the chosen (${f} files, ${b})`,
  overCaps: (f, b) => `Too much for one run: at most ${f} files, ${b}. Leave out a group.`,
  pulling: (d, n) => `Arriving: ${d} of ${n}. Keep the window on the computer open.`,
  pullingSpoke: (d, n) => `Arriving: ${d} of ${n}. Keep the computer open and awake.`,
  pulled: (d, k) => `Arrived: ${d} document${d === 1 ? '' : 's'} wait for your yes${k ? `, ${k} file${k === 1 ? '' : 's'} kept` : ''}.`,
  dropOr: 'Or drop single files on this card.',
  chatsTitle: 'Bring your chats with ChatGPT, Claude and other AIs',
  chatsWhich: 'Where is your export?',
  otherAI: 'Any other AI',
  chatsDrop: 'Drop the file from the export on this card (a .zip, .json, .html or .csv as it came, or a Codex or Claude Code session .jsonl), or press the button.',
  chatsPick: 'Choose the file',
  chatsUnverified: 'This format is read from the vendor\'s description; if it does not come in, paste the conversation below.',
  chatsPaste: 'Paste a conversation instead',
  chatsPasteHint: 'Paste a conversation from any AI here (copy the page, or a PDF\'s text).',
  chatsPasteGo: 'Bring it',
  chatsSeat: 'Signing in with Claude or ChatGPT lets your brain think with your subscription. It does not bring your old chats; the export does.',
  listTitle: (vs) => `Your chats from ${vs.length ? vs.join(vs.length === 2 ? ' and ' : ', ') : 'other AIs'}`,
  cont: 'Continue here',
  waitingYes: 'waiting for your yes',
  turns: (n) => `${n} turns`,
}

const RU = {
  compTitle: 'Перенести этот компьютер',
  compSub: 'Вы копируете одну строку в свой компьютер. Она просматривает ваши файлы и облачные папки, только названия, размеры и даты, и показывает список здесь. Вы говорите «да» тому, что перенести; отправляется только это.',
  compAgents: 'История Codex и Claude Code на этом компьютере тоже переносится, каждая сессия одним разговором.',
  compNever: 'Пароли, ключи, почта и данные браузера не отправляются никогда. Ничего не устанавливается и ничего не остаётся работать: когда всё готово, её нет. Мозг не может зайти в компьютер; строка только сама обращается к мозгу.',
  compNoApp: 'Скачивать приложение не нужно, поэтому компьютер не предупреждает о неизвестном разработчике.',
  compRead: 'Прочитать, что делает эта строка',
  compHelper: 'Если эта строка не работает',
  compHelperSub: 'То же самое через помощник на Python (на компьютере нужен Python 3). Тот же ключ, тот же список, то же «да» здесь.',
  compMacAllow: 'Mac может спросить, можно ли Терминалу открыть Рабочий стол, Документы или Загрузки: нажмите «Разрешить». Папки, которые вы не разрешили, остаются закрытыми, здесь только их названия.',
  compPhone: 'С телефона: положите фото и файлы в iCloud Drive или Google Drive; программа на компьютере найдёт их там.',
  compStart: 'Начать', compStarting: 'Начинаю...',
  compMacHow: 'На Mac: откройте Терминал (Программы, Утилиты, Терминал), вставьте эту строку и нажмите Return.',
  compWinHow: 'В Windows: откройте PowerShell (меню Пуск, наберите PowerShell), вставьте эту строку и нажмите Enter. Права администратора не нужны.',
  compCopy: 'Скопировать', compCopied: 'Скопировано', compNew: 'Новая строка',
  compOnce: (t) => `Строка работает один раз, до ${t}. Никому её не показывайте. Не закрывайте окно, пока не появится «Готово».`,
  compWaiting: 'Ждём ваш компьютер...',
  compPlan: (n, f, b) => `Ваш компьютер: ${n} ${ruPlural(n, ['группа', 'группы', 'групп'])}, ${f} ${ruPlural(f, ['файл', 'файла', 'файлов'])}, ${b}. Предложение:`,
  kind: { knowledge: 'в Знания', files: 'хранить файлами', leave: 'остаётся на компьютере' },
  why: { documents: 'документы', music: 'музыка', pictures: 'фотографии', code: 'код, у него свой git', old_downloads: 'загрузки старше двух лет', many_pictures: 'много фотографий, скажите «да», чтобы сохранить', screenshots: 'снимки экрана', codex_history: 'ваша история Codex, каждая сессия одним разговором', claude_code_history: 'ваша история Claude Code, каждая сессия одним разговором' },
  files: (n) => `${n} ${ruPlural(n, ['файл', 'файла', 'файлов'])}`,
  showAll: (n) => `показать все ${n}`,
  bringProposed: (f, b) => `Перенести всё предложенное (${f} ${ruPlural(f, ['файл', 'файла', 'файлов'])}, ${b})`,
  bringChosen: (f, b) => `Перенести выбранное (${f} ${ruPlural(f, ['файл', 'файла', 'файлов'])}, ${b})`,
  overCaps: (f, b) => `Слишком много за один раз: не больше ${f} файлов, ${b}. Уберите одну группу.`,
  pulling: (d, n) => `Приходит: ${d} из ${n}. Не закрывайте окно на компьютере.`,
  pullingSpoke: (d, n) => `Приходит: ${d} из ${n}. Не закрывайте компьютер и не давайте ему уснуть.`,
  pulled: (d, k) => `Пришло: ${d} ${ruPlural(d, ['документ ждёт', 'документа ждут', 'документов ждут'])} вашего «да»${k ? `, ${k} ${ruPlural(k, ['файл сохранён', 'файла сохранены', 'файлов сохранено'])}` : ''}.`,
  dropOr: 'Или перетащите сюда отдельные файлы.',
  chatsTitle: 'Перенесите сюда разговоры с ChatGPT, Claude и другими ИИ',
  chatsWhich: 'Где ваш экспорт?',
  otherAI: 'Другой ИИ',
  chatsDrop: 'Перетащите файл из экспорта на эту карточку (.zip, .json, .html или .csv, как пришёл, или сессию Codex или Claude Code .jsonl) или нажмите кнопку.',
  chatsPick: 'Выбрать файл',
  chatsUnverified: 'Этот формат прочитан по описанию компании; если не получится, вставьте разговор ниже.',
  chatsPaste: 'Или вставьте разговор',
  chatsPasteHint: 'Вставьте сюда разговор с любым ИИ (скопируйте страницу или текст из PDF).',
  chatsPasteGo: 'Перенести',
  chatsSeat: 'Вход через Claude или ChatGPT даёт мозгу думать по вашей подписке. Старые разговоры он не переносит; это делает экспорт.',
  listTitle: (vs) => `Ваши разговоры с ${vs.length ? vs.join(vs.length === 2 ? ' и ' : ', ') : 'другими ИИ'}`,
  cont: 'Продолжить здесь',
  waitingYes: 'ждёт вашего «да»',
  turns: (n) => `${n} ${ruPlural(n, ['реплика', 'реплики', 'реплик'])}`,
}

const PLAN_TEXT = { en: EN, ru: RU }
const planWords = (lang) => PLAN_TEXT[lang === 'ru' ? 'ru' : 'en']

module.exports = { defaultPicks, pickTotals, overCaps, pullState, surveyStep, fmtBytes, surveyCommands, helperCommands, agentUrls, vendorsOf, continueHref, PLAN_TEXT, planWords }
