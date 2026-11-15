// The quiet home (PARENTS-HOME-1, hbar 2026-11-15, on a member's console: "I DONT GET IT WHAT MAKES THIS
// SPECIAL"). A member brain whose layout is quiet (the title block, the button row and the tool line hidden:
// the hand-off screen step) opens as the owner's own place:
//   - the title is the owner's name in the console's language, from the name the brain already holds
//     (its persona's first line, else BRAIN_OWNER through /onboarding/welcome);
//   - the start page (layout key start) opens beside the chat by itself the first time each day;
//   - the menu shows at most five entries (Chat, the start page, Knowledge, Files, Settings), the rest
//     behind one more press;
//   - the empty chat shows three or four large buttons, each sending a real first message. Their words
//     live on the owner's own desk, <out>/week/asks.json, never in this code.
// Mechanism only: no person's name or interest is in this file.

// A layout is quiet when the hand-off screen step hid the title block, the row of buttons and the tool line.
const isQuiet = (lay) => !!(lay && lay.panels && lay.panels.hero === false && lay.panels.nav === false && lay.panels.tools === false)

// The persona's own words for whose brain it is: "Ты мозг Анны: ..." or "You are Anna's brain ...".
const RU_PERSONA = /(?:^|[\s#*>])Ты\s+мозг\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)/
const EN_PERSONA = /(?:^|[\s#*>])You\s+are\s+([A-Z][A-Za-z'-]+?)['’]s\s+brain/

// Russian genitive of a first name, for a name the brain holds only in the nominative (BRAIN_OWNER).
// The common endings only; anything else is left as it is ("Мозг: Ким" is better than a wrong case).
const HUSH = 'гкхжчшщ'
function ruGenitive(n) {
  if (!n || !/^[А-ЯЁ][а-яё-]+$/.test(n)) return null
  const last = n.slice(-1), prev = n.slice(-2, -1)
  if (last === 'а') return n.slice(0, -1) + (HUSH.includes(prev) ? 'и' : 'ы')
  if (last === 'я') return n.slice(0, -1) + 'и'
  if (last === 'й' || last === 'ь') return n.slice(0, -1) + 'я'
  if ('бвгдзклмнпрстфхцчшщж'.includes(last)) return n + 'а'
  return null
}

// ownerTitle(lang, persona, name) -> the title, or null when the brain holds no usable name.
function ownerTitle(lang, persona, name) {
  const p = String(persona || '').slice(0, 400)   // the persona's opening, where it says whose brain it is
  const ru = p.match(RU_PERSONA), en = p.match(EN_PERSONA)
  const nm = String(name || '').trim().split(/\s+/)[0] || ''
  if (lang === 'ru') {
    if (ru) return 'Мозг ' + ru[1]
    const g = ruGenitive(nm)
    if (g) return 'Мозг ' + g
    return null
  }
  if (en) return `${en[1]}’s brain`
  if (nm && /^[A-Za-z][A-Za-z'-]*$/.test(nm)) return `${nm}’s brain`
  return null
}

// The five entries of the quiet menu, in order. 'start' is the start page; it shows only when the layout has one.
const QUIET_ORDER = ['_chat', 'start', '_knowledge', '_files', '_settings']
const START_HREF = '/?start=1'

// quietMenu(tabs, start, label) -> { shown, rest }: tabs as the Nav holds them ({ id, href, label }), the
// layout's start route (or null), labels by id ({ _chat: 'Разговор', start: 'Неделя', ... }).
function quietMenu(tabs, start, label) {
  const list = Array.isArray(tabs) ? tabs : []
  const by = {}
  list.forEach(t => { if (t && t.id) by[t.id] = t })
  const L = label || {}
  const shown = []
  for (const id of QUIET_ORDER) {
    if (id === 'start') { if (start) shown.push({ id: '_start', href: START_HREF, label: L.start || 'Start' }); continue }
    // Files is a console page, not an api tab: it is always there
    if (id === '_files') { shown.push({ id: '_files', href: '/files', label: L._files || 'Files' }); continue }
    if (by[id]) shown.push({ ...by[id], label: L[id] || by[id].label })
  }
  const keep = new Set(QUIET_ORDER)
  const rest = list.filter(t => t && t.id !== '_cc' && !keep.has(t.id))
  return { shown: shown.slice(0, 5), rest }
}

// asks.json on the owner's desk: { "title"?: string, "start_label"?: string,
//   "asks": [{ "label": string, "sub"?: string, "send": string }] }. Anything malformed is dropped;
// at most four asks; label up to 60 characters, sub up to 90, send up to 1200.
const cut = (v, n) => (typeof v === 'string' ? v.trim().slice(0, n) : '')
function parseAsks(d) {
  if (!d || typeof d !== 'object' || Array.isArray(d)) return null
  const asks = (Array.isArray(d.asks) ? d.asks : [])
    .map(a => (a && typeof a === 'object' ? { label: cut(a.label, 60), sub: cut(a.sub, 90), send: cut(a.send, 1200) } : null))
    .filter(a => a && a.label && a.send)
    .slice(0, 4)
  return { title: cut(d.title, 60) || null, startLabel: cut(d.start_label, 30) || null, asks }
}

// Where the asks live: the bridge's desk ("out" in /cc/health), week/asks.json, through the Files door.
const asksUrl = (out) => (out ? '/cc/files/raw' + encodeURI(String(out).replace(/\/+$/, '') + '/week/asks.json') : null)

// The start page opens by itself once a day: due when the last day it opened is not today.
const dayOf = (d) => { const x = d || new Date(); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}` }
const START_DAY_KEY = 'cc.start.day'
const startDue = (lastDay, today) => !lastDay || lastDay !== today

module.exports = { isQuiet, ruGenitive, ownerTitle, QUIET_ORDER, START_HREF, quietMenu, parseAsks, asksUrl, dayOf, START_DAY_KEY, startDue }
