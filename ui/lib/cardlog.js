// The card log (INLINE-1, 2026-11-23): a thread's job tiles and report cards are kept on the box
// (GET /cc/cards?thread=<id>) and drawn again after any reload, in time order between the messages,
// each with its state: open, or answered. Pure functions, no DOM: ui/pages/cc.js uses them,
// tests/test_cc_cardlog.py runs them under node.
//
// hbar 2026-11-23, after a crashed browser: "CARDS SHOULD BE KEPT. CARDS ARE LIKE LOGS NO?"

// The brain records created_at without a zone (the database runs in UTC): read a bare stamp as UTC,
// never as the browser's local time, or a card would land hours away from its messages.
function whenOf(stamp) {
  if (stamp == null || stamp === '') return null
  if (typeof stamp === 'number') return stamp > 1e12 ? stamp / 1000 : stamp
  const s = String(stamp)
  const zoned = /(Z|[+-]\d\d:?\d\d)$/.test(s)
  const ms = Date.parse(zoned ? s : s + 'Z')
  return Number.isFinite(ms) ? ms / 1000 : null
}

// A log entry as a turn of the conversation.
function cardTurn(e) {
  if (!e || !e.data) return null
  const t = { who: 'brain', text: '', at: Number(e.at) || 0, logId: e.id, answered: !!e.answered }
  if (e.kind === 'job') t.job = e.data
  else if (e.kind === 'report') t.report = e.data
  else return null
  return t
}

// Messages (turns with `at`, or none) and log entries, merged in time order. A message without a
// time keeps its place after the message before it; a card goes after every message older than it.
function merge(turns, entries) {
  const cards = (entries || []).map(cardTurn).filter(Boolean).sort((a, b) => a.at - b.at)
  if (!cards.length) return (turns || []).slice()
  const out = []
  let i = 0, last = -Infinity
  for (const t of (turns || [])) {
    const at = typeof t.at === 'number' ? t.at : last
    while (i < cards.length && cards[i].at < at) out.push(cards[i++])
    out.push(t)
    if (typeof t.at === 'number') last = t.at
  }
  while (i < cards.length) out.push(cards[i++])
  return out
}

// The log id a live card will have, so a card that arrives by the poll is not drawn twice.
function idOf(turn) {
  if (!turn) return null
  if (turn.logId) return turn.logId
  if (turn.job && turn.job.id) return 'job:' + turn.job.id
  if (turn.report && turn.report.id) return 'report:' + turn.report.id
  return null
}

function has(turns, id) {
  return !!id && (turns || []).some(t => idOf(t) === id)
}

// Add a card that came by the poll, unless it is already drawn.
function addLive(turns, kind, data) {
  const id = kind + ':' + (data && data.id)
  if (!data || !data.id || has(turns, id)) return turns
  return [...turns, { who: 'brain', text: '', [kind]: data, logId: id, answered: false, at: Date.now() / 1000 }]
}

// After the owner sends a turn: every card drawn before it is answered.
function answerAll(turns) {
  return (turns || []).map(t => (idOf(t) && (t.job || t.report) && !t.answered ? { ...t, answered: true } : t))
}

function openCount(turns) {
  return (turns || []).filter(t => (t.job || t.report) && idOf(t) && !t.answered).length
}

module.exports = { whenOf, cardTurn, merge, idOf, has, addLive, answerAll, openCount }
