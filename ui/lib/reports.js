// Thread reports (REPORT-1, 2026-11-22): a thread started from another thread's choice button
// (mode "agent") reports back. Each time it finishes a turn the bridge leaves a short card for the
// PARENT thread: title, state, the first three lines of the answer, and a link to open it.
// Pure functions, no DOM: ui/pages/cc.js uses them, tests/test_cc_reports.py runs them under node.
//
// The rule of 2026-10-11 holds (ui/lib/jobs.js): a card renders only in the conversation it
// belongs to. The bridge hands a parent's cards to the page that names that parent; `mine` is the
// second guard, so a stale bridge or a page that switched threads never shows one in the wrong chat.

const { known } = require('./jobs')

// What the choice button sends so the bridge knows whom the new thread reports to. A page on a
// conversation that has no id yet (its first turn is still unrecorded) names no parent.
function startBody(choice, cur) {
  const body = { message: choice.send, new: true, thread: null, stream: false }
  if (known(cur)) { body.parent = cur; body.label = String(choice.label || '').slice(0, 120) }
  return body
}

// The cards that belong in the conversation shown.
function mine(cards, cur) {
  return (cards || []).filter(c => c && c.id && known(cur) && c.parent === cur)
}

// Where the card's link goes: the thread itself, in a tab of its own. A thread that failed before
// it was saved has no address.
function href(card) {
  return card && known(card.child) ? '/talk?thread=' + encodeURIComponent(card.child) : null
}

// good | ask | bad: the colour of the state word.
function tone(state) {
  if (state === 'failed') return 'bad'
  if (state === 'asks you' || state === 'waits for your yes' || state === 'stopped') return 'ask'
  return 'good'
}

// At most three lines, each a string.
function lines(card) {
  return ((card && card.lines) || []).filter(l => typeof l === 'string' && l.trim()).slice(0, 3)
}

module.exports = { startBody, mine, href, tone, lines }
