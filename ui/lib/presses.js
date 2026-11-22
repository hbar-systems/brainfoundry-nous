// The console's private usage log, page side (USAGE-1, 2026-11-22). The box keeps the log
// (scripts/cc/cc_presses.py, ~/.cc-bridge/surface-events.jsonl); this file only names a press and
// posts it to the bridge on the same origin. Names are routes and command words from a closed
// alphabet: a query string, a file path, a choice's label or a slash command's argument never
// leaves the page. The bridge checks every name again and writes nothing while the log is off.
// The naming functions are pure and run under node in tests/test_cc_presses.py.

const NAME_RE = /^[a-z0-9/#][a-z0-9/#:._-]{0,79}$/

// '/files?path=/home/x' -> '/files'; '#threads' stays; anything outside the alphabet -> null
function routeName(route) {
  let s = String(route == null ? '' : route).trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(s)) { try { s = new URL(s).pathname } catch (e) { return null } }
  if (s.startsWith('#')) s = '#' + s.slice(1).split(/[?#]/)[0]
  else s = s.split(/[?#]/)[0]
  s = s.toLowerCase()
  if (s.length > 1 && s.endsWith('/')) s = s.slice(0, -1)
  return NAME_RE.test(s) ? s : null
}

// '/model opus' -> 'model' when the page knows /model; any other slash command -> 'other'
function slashName(text, known) {
  const m = String(text == null ? '' : text).match(/^\/([A-Za-z0-9_-]+)/)
  if (!m) return null
  const cmd = m[1].toLowerCase()
  const list = (known || []).map(k => String(k && k.c ? k.c : k).replace(/^\//, '').toLowerCase())
  return list.includes(cmd) ? cmd : 'other'
}

// A choice button: how it was sent and where it stood, never its words. -> 'reply-1', 'agent-2'
function choiceName(choice, index) {
  const mode = choice && choice.mode === 'agent' ? 'agent' : 'reply'
  const i = Number.isInteger(index) && index >= 0 && index < 9 ? index + 1 : 0
  return mode + '-' + i
}

function threadName(t) {
  const s = String(t == null ? '' : t)
  return /^[A-Za-z0-9][A-Za-z0-9:._-]{0,79}$/.test(s) ? s : ''
}

// After the bridge says the log is off (or is not there), the page stays quiet for a minute.
let quietUntil = 0
function press(kind, name, thread) {
  if (typeof window === 'undefined' || typeof fetch !== 'function' || !name) return
  if (Date.now() < quietUntil) return
  try {
    fetch('/cc/presses', { method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, name, thread: threadName(thread) }) })
      .then(r => (r.ok ? r.json() : { logged: false }))
      .then(d => { if (!d || d.logged !== true) quietUntil = Date.now() + 60000 })
      .catch(() => { quietUntil = Date.now() + 60000 })
  } catch (e) {}
}
function wake() { quietUntil = 0 }

module.exports = { routeName, slashName, choiceName, threadName, press, wake, NAME_RE }
