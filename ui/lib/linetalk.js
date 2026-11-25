// Line talk (LINE-TALK-1, 2026-11-25). hbar, verbatim: "u know what would be nice, if i can click the line say the line
// say, 'The court: ' -- and this automatically either does what the ask button does or what note does.. but point is by
// clicking i can continue to talk without needing to press too much and then press twice my button on keys to do audio
// for me to speak in etc."
//
// One press on a line that starts a point in an answer (a list item, a heading, a table row, a paragraph that opens
// with a bold lead-in) opens a small reply slot right under that line, bound to it ("About this: <the line>"), the
// cursor in it. Enter sends. Holding the line for half a second, or the slot's mic, dictates into the slot. Used by
// the chat (ui/pages/cc.js, the slots are margin remarks of kind "line") and the wall's reading card
// (ui/components/WallRead.js). The pure parts run under node in tests/test_cc_linetalk.py.
//
//   POINT_TAGS, HOLD_MS          what counts as a point; how long a hold is
//   pointOf(target, root)        the point element a press landed in, or null (needs a DOM)
//   pointsIn(root)               every point element of an answer, in order (a slot is re-anchored by its index)
//   lineText(el)                 the point's own words, one line, without nested lists, slots or buttons
//   anchorSlot(el, doc)          a host element right under the line (inside a list item, a row after a table row)
//   findPoint(root, idx, quote)  the point a kept slot belongs to: the one at idx when its words still match, else
//                                the first whose words are the quote
//   squash(s, n)                 one line, at most n characters
//   aboutBlock(slots)            the wall's message: About this: "<line>" - <words>, one per filled slot
//   plainStep(name, input)       a tool call as plain words ("reading the handoff"), never the raw command; the
//                                bridge does the same in cc_extras.tool_plain

const POINT_TAGS = ['LI', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'TR']
const HOLD_MS = 500
const LINE_MAX = 300

const squash = (s, n) => {
  const v = String(s == null ? '' : s).replace(/\s+/g, ' ').trim()
  const m = n || LINE_MAX
  return v.length > m ? v.slice(0, m - 1).trimEnd() + '…' : v
}

const tagOf = (el) => String((el && el.tagName) || '').toUpperCase()

// a paragraph is a point when its first words are bold (a "**Lead:**" line), and it is not inside a list item
function leadPara(el) {
  if (tagOf(el) !== 'P') return false
  if (el.parentElement && el.parentElement.closest && el.parentElement.closest('li')) return false
  for (let n = el.firstChild; n; n = n.nextSibling) {
    if (n.nodeType === 3) { if (String(n.nodeValue || '').trim()) return false; continue }
    if (n.nodeType !== 1) continue
    const t = tagOf(n)
    return t === 'STRONG' || t === 'B'
  }
  return false
}

function isPoint(el, root) {
  if (!el || el.nodeType !== 1) return false
  if (el.closest && el.closest('[data-nopick],[data-lineslot]')) return false
  if (root && root.contains && !root.contains(el)) return false
  const t = tagOf(el)
  if (t === 'TR') return !(el.parentElement && tagOf(el.parentElement) === 'THEAD')
  return POINT_TAGS.includes(t) || leadPara(el)
}

function pointOf(target, root) {
  let el = target && target.nodeType === 3 ? target.parentElement : target
  while (el && el !== root && el.nodeType === 1) {
    if (el.closest && el.closest('[data-lineslot],a,button,input,textarea,select,summary,[data-nopick]')) return null
    if (isPoint(el, root)) return el
    el = el.parentElement
  }
  return null
}

function pointsIn(root) {
  if (!root || !root.querySelectorAll) return []
  return Array.from(root.querySelectorAll('li,h1,h2,h3,h4,h5,h6,tr,p')).filter(el => isPoint(el, root))
}

function lineText(el) {
  if (!el) return ''
  if (tagOf(el) === 'TR') return squash(Array.from(el.children).map(c => squash(c.textContent)).filter(Boolean).join(' · '))
  const parts = []
  const walk = (n) => {
    for (let c = n.firstChild; c; c = c.nextSibling) {
      if (c.nodeType === 3) { parts.push(c.nodeValue); continue }
      if (c.nodeType !== 1) continue
      const t = tagOf(c)
      if (t === 'UL' || t === 'OL' || t === 'BUTTON' || t === 'TEXTAREA' || t === 'STYLE' || t === 'SCRIPT') continue
      if (c.hasAttribute && (c.hasAttribute('data-lineslot') || c.hasAttribute('data-nopick'))) continue
      if (/^(P|DIV|BLOCKQUOTE|PRE)$/.test(t)) parts.push(' ')
      walk(c)
    }
  }
  walk(el)
  return squash(parts.join(''))
}

// The host goes right under the line: inside a list item before its nested list; a row of its own after a table row
// (one cell across the table); after a heading or a lead paragraph.
function anchorSlot(el, doc) {
  const d = doc || (el && el.ownerDocument)
  if (!el || !d) return null
  const t = tagOf(el)
  if (t === 'TR') {
    const tr = d.createElement('tr'); tr.setAttribute('data-lineslot-host', '1'); tr.setAttribute('data-nopick', '1')
    const td = d.createElement('td'); td.colSpan = Math.max(1, el.children.length); tr.appendChild(td)
    el.parentNode.insertBefore(tr, el.nextSibling)
    return { host: td, remove: () => tr.remove() }
  }
  const host = d.createElement('div'); host.setAttribute('data-lineslot-host', '1'); host.setAttribute('data-nopick', '1')
  if (t === 'LI') {
    const nested = Array.from(el.children).find(c => /^(UL|OL)$/.test(tagOf(c)))
    el.insertBefore(host, nested || null)
  } else {
    el.parentNode.insertBefore(host, el.nextSibling)
  }
  return { host, remove: () => host.remove() }
}

function findPoint(root, idx, quote) {
  const pts = pointsIn(root)
  const q = squash(quote)
  if (pts[idx] && lineText(pts[idx]) === q) return { el: pts[idx], idx }
  const k = pts.findIndex(p => lineText(p) === q)
  return k >= 0 ? { el: pts[k], idx: k } : null
}

function aboutBlock(slots) {
  return (slots || []).filter(s => s && String(s.text || '').trim())
    .map(s => `About this: "${squash(s.quote)}" - ${String(s.text).trim()}`).join('\n\n')
}

// ---- plain words for a tool call (the wall's live line) ----
const IRREGULAR = { run: 'running', get: 'getting', set: 'setting', put: 'putting', stop: 'stopping', cut: 'cutting', see: 'seeing',
  be: 'being', go: 'going', do: 'doing', map: 'mapping', tag: 'tagging', pin: 'pinning', plan: 'planning', ship: 'shipping', drop: 'dropping',
  grep: 'searching', cat: 'reading', ls: 'listing', rm: 'removing', cd: 'going', mv: 'moving', cp: 'copying', curl: 'fetching',
  wait: 'waiting', open: 'opening', visit: 'visiting', edit: 'editing', audit: 'auditing', admit: 'admitting', commit: 'committing',
  submit: 'submitting', permit: 'permitting', begin: 'beginning', omit: 'omitting', emit: 'emitting', rerun: 'rerunning' }
function gerund(w) {
  const v = String(w || '').toLowerCase()
  if (!/^[a-z]+$/.test(v)) return null
  if (IRREGULAR[v]) return IRREGULAR[v]
  if (/ing$/.test(v)) return v
  if (/ie$/.test(v)) return v.slice(0, -2) + 'ying'
  if (/[^aeiou]e$/.test(v) || /[^e]ue$/.test(v)) return v.slice(0, -1) + 'ing'
  return v + 'ing'
}

// "Read the handoff" -> "reading the handoff"; a description that does not start with a verb stays as it is, lower-cased
function plainWords(desc) {
  const s = squash(desc, 120).replace(/[.:]+$/, '')
  if (!s) return ''
  const m = s.match(/^([A-Za-z]+)(\b.*)$/)
  if (!m) return s
  const g = gerund(m[1])
  const verbish = /^[A-Z][a-z]+$/.test(m[1]) || /^[a-z]+$/.test(m[1])
  return (g && verbish ? g : m[1].toLowerCase()) + m[2]
}

const base = (p) => String(p || '').replace(/\/+$/, '').split('/').pop()

function plainStep(name, inp) {
  const i = inp && typeof inp === 'object' ? inp : {}
  const n = String(name || '')
  if (n === 'Bash') return i.description ? plainWords(i.description) : 'running a command'
  if (n === 'Read') return 'reading ' + (base(i.file_path) || 'a file')
  if (n === 'Edit' || n === 'MultiEdit') return 'editing ' + (base(i.file_path) || 'a file')
  if (n === 'Write') return 'writing ' + (base(i.file_path) || 'a file')
  if (n === 'Grep' || n === 'Glob') return 'searching the files'
  if (n === 'Agent' || n === 'Task') return 'a helper: ' + (i.description ? plainWords(i.description) : 'started')
  if (n === 'WebFetch') return 'reading a web page'
  if (n === 'WebSearch') return 'searching the web'
  if (n === 'TodoWrite') return 'updating the plan'
  if (/^mcp__/.test(n)) return 'using ' + n.split('__')[1].replace(/[_-]+/g, ' ')
  return i.description ? plainWords(i.description) : (n ? 'using ' + n : 'working')
}

module.exports = { POINT_TAGS, HOLD_MS, LINE_MAX, squash, isPoint, pointOf, pointsIn, lineText, anchorSlot, findPoint, aboutBlock, gerund, plainWords, plainStep }
