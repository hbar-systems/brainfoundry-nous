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
  seatTitle: 'Sign in with ChatGPT or Claude',
  seatSub: 'Your brain thinks with the subscription you already have. Sign in once below; your password stays with OpenAI or Anthropic.',
  seatLocal: 'Without a sign-in, your brain runs on a small free model on the shared server (llama3.2, 3B). It keeps your notes and finds your documents, but it cannot replace ChatGPT: for that, sign in.',
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
  seatTitle: 'Войдите через ChatGPT или Claude',
  seatSub: 'Мозг думает по подписке, которая у вас уже есть. Войдите один раз ниже; пароль остаётся у OpenAI или Anthropic.',
  seatLocal: 'Без входа мозг работает на маленькой бесплатной модели на общем сервере (llama3.2, 3B). Он хранит заметки и находит документы, но заменить ChatGPT не может: для этого войдите.',
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

const FIRST_TEXT = { en: EN, ru: RU }
const firstWords = (lang) => FIRST_TEXT[lang === 'ru' ? 'ru' : 'en']

module.exports = { ORDER, currentStep, showFirstRun, NEWCOMER, startPicks, togglePick, FIRST_TEXT, firstWords }
