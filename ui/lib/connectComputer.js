// Connect this computer (SWITCH-1, hbar 2026-11-16: "don't they have to give you ssh? this is too technical for
// people like my mother"). The spoke of docs/spoke.md, as one card on the member's home: press, one file
// downloads, open it, press Allow where the Mac asks. The brain then looks (counts only) and, on a yes in
// place, runs MOVE-IN-2's whole-computer plan over the spoke instead of a pasted line. Since SPOKE-3 this is the
// advanced path, below the one-line Bring in this computer card. Pure logic and words here; the card is ui/components/ConnectComputer.js.

// The card's step from GET /cc/spoke/state and what this page did:
//   off (the spoke is not switched on for this brain) | get (no computer yet) | made (the file was made) |
//   asleep | look (here, nothing looked at yet) | looked (counts in) | moving (the list is being made)
function spokeStep(st, local) {
  const l = local || {}
  if (!st || st.ready === false) return 'off'
  const lap = st.status && st.status.laptop
  if (!lap) return l.made ? 'made' : 'get'
  if (lap.state !== 'online') return 'asleep'
  if (l.moving) return 'moving'
  if (l.looked || st.inventory) return 'looked'
  return 'look'
}

// Which computer this browser is on (the card picks it first; the person can switch).
function osOf(ua) {
  const u = String(ua || '')
  if (/Windows/i.test(u)) return 'windows'
  if (/iPhone|iPad|Android/i.test(u)) return 'phone'
  if (/Mac OS X|Macintosh/i.test(u)) return 'mac'
  return 'other'
}

const fmtBytes = (n) => {
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, x = Number(n) || 0
  while (x >= 1024 && i < u.length - 1) { x /= 1024; i += 1 }
  return i === 0 ? `${x} ${u[i]}` : `${x.toFixed(x < 10 ? 1 : 0)} ${u[i]}`
}

const EN = {
  title: 'Connect this computer',
  sub: 'Your brain gets its own private line to this computer, so it can look at what is on it and bring in what you choose. No typing, no passwords given to anyone.',
  off: 'not switched on yet',
  offSub: 'The private line is not switched on for your brain yet. Until it is, the card above does the same with one line you paste.',
  stGet: 'not connected', stMade: 'the file is ready', stAsleep: 'asleep', stHere: 'connected, looking only', stMoving: 'listing your computer',
  mac: 'Mac', windows: 'Windows',
  get: 'Get the file for this Mac', getting: 'Making your file...',
  again: 'Make a new file',
  once: (fp) => `The file works once, for one hour. Your brain's key: ${fp}. The window on the Mac shows the same key.`,
  steps: [
    'Open Downloads and double-click "Join my brain".',
    'Your Mac says it cannot check the app. Press Done, open System Settings, Privacy & Security, scroll down and press "Open Anyway", then your password.',
    'In the "Join my brain" window press Join.',
    'Your Mac asks for your password once (to install Tailscale, the private line).',
    'Your Mac asks about a VPN configuration and a system extension: press Allow.',
    'Sharing opens: turn on Remote Login, press the (i) beside it and turn on "Allow full disk access for remote users".',
    'The window says Done. Come back here; this card wakes up by itself.',
  ],
  stepsHead: 'What your Mac will show, in order:',
  why: 'The second step (Apple\'s warning) goes away once the app is signed with an Apple Developer ID. The other questions are your Mac\'s own and stay: they are how macOS asks you before a new program may connect or read your folders.',
  win: 'Not for Windows yet. It would need: OpenSSH Server switched on (Settings, Optional features), Tailscale for Windows, and a door like the Mac\'s written for PowerShell, then a test on a real Windows laptop. Until then, use the line in the card above.',
  phone: 'Open this page on the computer you want to connect.',
  asleep: (t) => `Your computer is asleep or away${t ? ` since ${t}` : ''}. Open it and this card wakes up.`,
  here: 'Your brain can see your computer. It looks only: counts and sizes, no names.',
  look: 'Look at it', looking: 'Looking...',
  looked: (f, b) => (f != null ? `On it: ${f} files, ${b}.` : 'Your brain has looked at it.'),
  page: 'Open the page',
  bring: 'Bring what is on it',
  ask: 'To propose what to bring, your brain lists your files: names, sizes and dates, not what is in them. Passwords, keys, mail and browsers are never listed. Nothing is brought in or moved before you say yes to the plan.',
  yes: 'Yes, list it', no: 'Not now',
  moving: 'Your brain is listing your computer. The plan appears in the card above; keep the computer open and awake.',
  disconnect: 'Disconnect this computer',
  discAsk: 'Your brain\'s key is removed from the computer and it leaves the private line. Disconnect?',
  discYes: 'Disconnect',
  failed: 'That did not work. Try again in a minute.',
  fallback: 'Or with a line in Terminal',
}

const RU = {
  title: 'Подключите этот компьютер',
  sub: 'Мозг получает свою закрытую линию к этому компьютеру: он может посмотреть, что на нём, и перенести то, что вы выберете. Ничего не нужно набирать, никому не нужно давать пароли.',
  off: 'ещё не включено',
  offSub: 'Закрытая линия для вашего мозга ещё не включена. Пока её нет, карточка выше делает то же самое одной строкой, которую вы вставляете.',
  stGet: 'не подключён', stMade: 'файл готов', stAsleep: 'спит', stHere: 'подключён, только смотрит', stMoving: 'составляет список',
  mac: 'Mac', windows: 'Windows',
  get: 'Получить файл для этого Mac', getting: 'Готовлю файл...',
  again: 'Сделать новый файл',
  once: (fp) => `Файл работает один раз, один час. Ключ вашего мозга: ${fp}. Окно на Mac покажет тот же ключ.`,
  steps: [
    'Откройте Загрузки и дважды нажмите «Join my brain».',
    'Mac скажет, что не может проверить программу. Нажмите «Готово», откройте Системные настройки, «Конфиденциальность и безопасность», прокрутите вниз и нажмите «Всё равно открыть», затем пароль.',
    'В окне «Подключить мозг» нажмите «Подключить».',
    'Mac один раз спросит пароль (чтобы установить Tailscale, закрытую линию).',
    'Mac спросит про конфигурацию VPN и системное расширение: нажмите «Разрешить».',
    'Откроется «Общий доступ»: включите «Удалённый вход», нажмите (i) рядом и включите «Разрешить полный доступ к диску для удалённых пользователей».',
    'Окно скажет «Готово». Вернитесь сюда; карточка оживёт сама.',
  ],
  stepsHead: 'Что покажет Mac, по порядку:',
  why: 'Второй шаг (предупреждение Apple) исчезнет, когда программа будет подписана Apple Developer ID. Остальные вопросы задаёт сам Mac, и они останутся: так macOS спрашивает вас, прежде чем новая программа подключится или прочитает ваши папки.',
  win: 'Для Windows пока нет. Понадобится: включить OpenSSH Server (Параметры, Дополнительные компоненты), Tailscale для Windows и дверь, как на Mac, написанная для PowerShell, затем проверка на настоящем ноутбуке с Windows. А пока используйте строку в карточке выше.',
  phone: 'Откройте эту страницу на компьютере, который хотите подключить.',
  asleep: (t) => `Компьютер спит или далеко${t ? ` с ${t}` : ''}. Откройте его, и карточка оживёт.`,
  here: 'Мозг видит ваш компьютер. Он только смотрит: количество и размеры, без названий.',
  look: 'Посмотреть', looking: 'Смотрю...',
  looked: (f, b) => (f != null ? `На нём: ${f} файлов, ${b}.` : 'Мозг посмотрел на него.'),
  page: 'Открыть страницу',
  bring: 'Перенести то, что на нём',
  ask: 'Чтобы предложить, что перенести, мозг составит список файлов: названия, размеры и даты, без содержимого. Пароли, ключи, почта и браузеры в список не попадают никогда. Ничего не переносится и не двигается, пока вы не скажете «да» плану.',
  yes: 'Да, составить список', no: 'Не сейчас',
  moving: 'Мозг составляет список файлов. План появится в карточке выше; не закрывайте компьютер и не давайте ему уснуть.',
  disconnect: 'Отключить этот компьютер',
  discAsk: 'Ключ мозга удаляется с компьютера, и компьютер выходит из закрытой линии. Отключить?',
  discYes: 'Отключить',
  failed: 'Не получилось. Попробуйте ещё раз через минуту.',
  fallback: 'Или одной строкой в Терминале',
}

const CONNECT_TEXT = { en: EN, ru: RU }
const connectWords = (lang) => CONNECT_TEXT[lang === 'ru' ? 'ru' : 'en']

module.exports = { spokeStep, osOf, fmtBytes, CONNECT_TEXT, connectWords }
