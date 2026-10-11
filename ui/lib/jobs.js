// Jobs and conversations (2026-10-11): a finished job's tile lands only in the conversation whose
// hands started it. Pure functions, no DOM: ui/pages/cc.js uses them, tests/test_cc_bridge.py runs
// them under node.
//
// Before this, every mounted CC page polled `/cc/jobs?take=1` and the bridge handed each finished
// job to whichever page asked first, so the music thread's jobs showed up as "JOB FINISHED" tiles
// in another thread's chat (the operator, 2026-10-11: "cards from this thread appear in another
// thread, this confuses me"). Now a job record carries `thread` (the brain thread id, or
// "unknown"), the page asks for its own thread's jobs, and the others are shown once in a small
// strip under the conversation, never inline.

const UNKNOWN = 'unknown'

// A thread id the page can own: a real brain id, not 'unknown', not a 'new:' placeholder.
function known(thread) {
  return !!thread && thread !== UNKNOWN && !String(thread).startsWith('new:')
}

// The poll address for the page showing `cur`: it names its thread so the bridge hands over only
// that thread's finished jobs. A page on a new conversation names none and takes nothing.
function jobsUrl(cur) {
  return '/cc/jobs?take=1' + (known(cur) ? '&thread=' + encodeURIComponent(cur) : '')
}

// Does this finished job belong in the conversation shown? Only when both sides are known and equal.
function isMine(job, cur) {
  return !!job && known(cur) && job.thread === cur
}

// Split what the bridge returned: mine become tiles in the conversation, the rest go to the strip
// (a second guard after the bridge's own filter, so a stale bridge can never put a tile in the wrong chat).
function splitFinished(finished, cur) {
  const mine = [], others = []
  for (const j of (finished || [])) (isMine(j, cur) ? mine : others).push(j)
  return { mine, others }
}

// The strip's items: the bridge's `others` plus anything the split set aside, without duplicates,
// without the ids the person dismissed in this browser, newest first. Each carries a label and
// where to go: the owning conversation when it is known, else the job's log.
function stripItems(others, extra, dismissed) {
  const seen = new Set(), out = []
  const hidden = new Set(dismissed || [])
  for (const j of [...(others || []), ...(extra || [])]) {
    if (!j || !j.id || seen.has(j.id) || hidden.has(j.id)) continue
    seen.add(j.id)
    const where = known(j.thread) ? (j.thread_title || 'another conversation') : 'no conversation'
    out.push({
      id: j.id, title: j.title || j.id, thread: known(j.thread) ? j.thread : null, where,
      ok: j.rc === 0, ended: j.ended || 0,
      href: known(j.thread) ? '/talk?thread=' + encodeURIComponent(j.thread) : (j.log ? '/files?path=' + encodeURIComponent(j.log) : null),
    })
  }
  out.sort((a, b) => b.ended - a.ended)
  return out
}

// One line for the strip: "finished elsewhere: <title> (<where>)" or the count when there are many.
function stripLabel(items) {
  if (!items || !items.length) return ''
  if (items.length === 1) return `finished in ${items[0].where}: ${items[0].title}`
  return `${items.length} jobs finished in other conversations`
}

// What dismiss should do: a job of a known conversation is only hidden here (its own page still
// takes the tile); a job of no conversation is marked seen on the bridge, or it would stay for a day.
function dismissAction(item) {
  return item && item.thread ? 'hide' : 'seen'
}

module.exports = { UNKNOWN, known, jobsUrl, isMine, splitFinished, stripItems, stripLabel, dismissAction }
