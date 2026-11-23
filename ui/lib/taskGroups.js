// The tasks page's grouping (SKIN-2, 2026-11-23, hbar: "in the tasks it could be a little better in terms of
// UI"). Pure functions, no DOM; ui/pages/tasks.js draws them, tests/test_ui_skin_tasks.py runs them under node.
//
// Three sources become one list of items: the owner's own tasks (GET /api/bf/tasks), the finished jobs whose
// report waits on him (GET /cc/actions `jobs`) and the agents' next rows (GET /cc/actions `next`).
// Each item: { key, kind: task|job|next, text, sub, system, due, hands, raw }.
//   system  from the repo path (systems/<name>/repos/...), "world" for the world repo, "you" for his own tasks
//   hands   only he can move it: his own tasks, a job that asks him, a next row that waits on his word
// Two views: by time (past due, today, this week, later, no date) and by system. In every group the
// his-hands items come first, then the soonest.

const WHEN = [['past', 'past due'], ['today', 'today'], ['week', 'this week'], ['later', 'later'], ['none', 'no date']]
const HANDS_RE = /\b(on (his|hbar'?s?|my|your|the owner'?s?) word|his hands|hbar (word|decides|rules)|only (he|hbar) can|needs you)\b/i

function systemOf(repo) {
  const r = String(repo || '').trim()
  const m = /^systems\/([^/]+)/.exec(r)
  if (m) return m[1]
  if (r === 'world' || r === '.' || !r) return 'world'
  return r.split('/')[0]
}

function fromSources(tasks, acts) {
  const out = []
  for (const t of tasks || []) {
    if (!t || t.done) continue
    out.push({ key: 't' + t.id, kind: 'task', text: t.text, sub: t.source ? 'from ' + t.source : '', system: t.system || 'you', due: t.due || null, hands: true, raw: t })
  }
  const a = acts || {}
  for (const j of a.jobs || []) {
    out.push({ key: 'j' + j.id, kind: 'job', text: j.title || j.id, sub: (j.status || '') + (j.line ? ': ' + j.line : ''), system: j.system || 'jobs', due: j.ended || null, hands: true, asks: true, raw: j })
  }
  for (const n of a.next || []) {
    out.push({ key: 'n' + n.id, kind: 'next', text: n.what, sub: n.why || '', system: systemOf(n.repo), due: null, hands: HANDS_RE.test((n.what || '') + ' ' + (n.why || '')), raw: n })
  }
  return out
}

// past | today | week | later | none, in the browser's own day. A job that asks him is "today": it waits now.
function whenOf(item, now) {
  if (item.asks) return 'today'
  if (!item.due) return 'none'
  const d = new Date(item.due)
  if (isNaN(d)) return 'none'
  const n = new Date(now)
  const day0 = new Date(n.getFullYear(), n.getMonth(), n.getDate())
  const day1 = new Date(day0); day1.setDate(day0.getDate() + 1)
  const week = new Date(day0); week.setDate(day0.getDate() + 7)
  if (d < n) return 'past'
  if (d < day1) return 'today'
  if (d < week) return 'week'
  return 'later'
}

function order(a, b) {
  if (a.hands !== b.hands) return a.hands ? -1 : 1
  const da = a.due ? Date.parse(a.due) : Infinity, db = b.due ? Date.parse(b.due) : Infinity
  if (da !== db) return da - db
  return String(a.text || '').localeCompare(String(b.text || ''))
}

// [{ id, label, items }], empty groups left out.
function groupBy(items, view, now) {
  const at = {}, groups = []
  const put = (id, label, it) => { if (!(id in at)) { at[id] = groups.length; groups.push({ id, label, items: [] }) } groups[at[id]].items.push(it) }
  if (view === 'system') {
    for (const it of items) put(it.system, it.system, it)
    for (const g of groups) g.items.sort(order)
    // his own first, then the systems with the most for his hands, then by name
    const hands = g => g.items.filter(i => i.hands).length
    groups.sort((x, y) => (x.id === 'you' ? -1 : y.id === 'you' ? 1 : 0) || hands(y) - hands(x) || x.id.localeCompare(y.id))
    return groups
  }
  for (const [id, label] of WHEN) { at[id] = groups.length; groups.push({ id, label, items: [] }) }
  for (const it of items) groups[at[whenOf(it, now)]].items.push(it)
  for (const g of groups) g.items.sort(order)
  return groups.filter(g => g.items.length)
}

function counts(items, now) {
  const c = { all: items.length, hands: 0, past: 0, today: 0 }
  for (const it of items) {
    if (it.hands) c.hands++
    const w = whenOf(it, now)
    if (w === 'past') c.past++
    if (w === 'today') c.today++
  }
  return c
}

module.exports = { WHEN, systemOf, fromSources, whenOf, groupBy, counts }
