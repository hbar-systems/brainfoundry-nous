// The visual layer, first step (hbar 2026-10-13: "make it a button and you send out an agent").
// Pure functions, no React: run under node by tests/test_cc_bridge.py, like pathlinks.js.
//
// Choices: the reasoner may end an answer with
//   <choices>[{"label": "...", "send": "...", "mode": "reply|agent", "p": 65}]</choices>
// "p" (optional, hbar 2026-10-29): the reasoner's probability that this is the right pick, 1 to 99
// (a 0..1 fraction is read as a share); shown on the button as "65%".
// The page cuts the block out of the text and draws it as buttons. "reply" sends `send` as the next
// message in the thread; "agent" starts it as a new thread that runs beside this one.
// Money: amounts with a currency become highlighted chips in rendered answers.

const MAX_CHOICES = 4
const CHOICES_RE = /<choices>\s*([\s\S]*?)\s*<\/choices>\s*$/
const OPEN_RE = /<choices>[\s\S]*$/

function clean(c) {
  if (!c || typeof c !== 'object') return null
  const label = String(c.label || '').trim().slice(0, 80)
  const send = String(c.send || c.label || '').trim().slice(0, 2000)
  if (!label || !send) return null
  const out = { label, send, mode: c.mode === 'agent' ? 'agent' : 'reply' }
  let p = Number(c.p)
  if (Number.isFinite(p) && p > 0) {
    if (p <= 1) p = p * 100
    out.p = Math.min(99, Math.max(1, Math.round(p)))
  }
  return out
}

// text -> { body, choices }  (choices: [] when there is no block or it does not parse)
// A block still streaming in (opened, not closed) is hidden from the body, so raw JSON never flashes.
function splitChoices(text) {
  const s = String(text == null ? '' : text)
  const m = s.match(CHOICES_RE)
  if (!m) {
    const open = s.search(OPEN_RE)
    return { body: open >= 0 ? s.slice(0, open).trimEnd() : s, choices: [] }
  }
  let list = []
  try { const v = JSON.parse(m[1]); if (Array.isArray(v)) list = v.map(clean).filter(Boolean).slice(0, MAX_CHOICES) } catch (e) {}
  return { body: s.slice(0, m.index).trimEnd(), choices: list }
}

// An amount with a currency: "EUR 34", "34 EUR", "€5", "$0.39", "1,200 USD", "€27-31", "$1.2k".
const NUM = '\\d+(?:[.,]\\d+)*(?:\\s?(?:k|K|M|bn)\\b)?'
const RANGE = NUM + '(?:\\s?[-\u2013]\\s?' + NUM + ')?'
const CODE = '(?:EUR|USD|GBP|CHF)'
const MONEY_RE_SRC = '(?:[\u20ac$\u00a3]\\s?' + RANGE + ')|(?:\\b' + CODE + '\\s?' + RANGE + ')|(?:\\b' + RANGE + '\\s?(?:\u20ac|' + CODE + '\\b))'

// text -> [{ t: 'text', v } | { t: 'money', v }]
function splitMoney(text) {
  const s = String(text == null ? '' : text)
  const re = new RegExp(MONEY_RE_SRC, 'g')
  const out = []
  let last = 0, m
  while ((m = re.exec(s))) {
    if (m[0].length === 0) { re.lastIndex++; continue }
    if (m.index > last) out.push({ t: 'text', v: s.slice(last, m.index) })
    out.push({ t: 'money', v: m[0] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ t: 'text', v: s.slice(last) })
  return out
}

// remark plugin: amounts in plain text (not in links or code) become <span data-ccmoney>, which the
// renderer's `span` component draws as a chip.
function remarkMoney() {
  const walk = (node) => {
    if (!node || !Array.isArray(node.children)) return
    if (node.type === 'link' || node.type === 'linkReference' || node.type === 'inlineCode' || node.type === 'code') return
    const next = []
    for (const ch of node.children) {
      if (ch.type === 'text') {
        const parts = splitMoney(ch.value)
        if (parts.length === 1 && parts[0].t === 'text') { next.push(ch); continue }
        for (const p of parts) {
          if (p.t === 'text') next.push({ type: 'text', value: p.v })
          else next.push({ type: 'ccmoney', data: { hName: 'span', hProperties: { 'data-ccmoney': '1' }, hChildren: [{ type: 'text', value: p.v }] } })
        }
      } else { walk(ch); next.push(ch) }
    }
    node.children = next
  }
  return (tree) => { walk(tree) }
}

// Actionable phrases (2026-10-15, hbar: "you often say nothing was pushed or deployed: the word should be
// pressable so an agent can go and do it"). A status phrase in plain text becomes <span data-ccact>, which
// the renderer draws with a quiet shade; clicking it offers "do it (send agent)" with the sentence prefilled.
const ACT_PHRASES = [
  'nothing was pushed', 'nothing is pushed', 'not pushed', 'unpushed', 'waiting for your push', 'waiting only for your "push"',
  'nothing was deployed', 'not deployed', 'not yet deployed', 'not installed', 'nothing installed',
  'not committed', 'uncommitted', 'owed by hbar', 'owed by you', 'still to do', 'not built', 'not started',
]
const ACT_RE_SRC = '\\b(?:' + ACT_PHRASES.slice().sort((a, b) => b.length - a.length)
  .map(s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b'

// text -> [{ t: 'text', v } | { t: 'act', v }]
function splitAct(text) {
  const s = String(text == null ? '' : text)
  const re = new RegExp(ACT_RE_SRC, 'gi')
  const out = []
  let last = 0, m
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ t: 'text', v: s.slice(last, m.index) })
    out.push({ t: 'act', v: m[0] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ t: 'text', v: s.slice(last) })
  return out
}

// The sentence of `block` that holds `phrase` (for the agent's prefilled task).
function sentenceAround(block, phrase) {
  const s = String(block || '').replace(/\s+/g, ' ').trim()
  const i = s.toLowerCase().indexOf(String(phrase || '').toLowerCase())
  if (i < 0) return s.slice(0, 300)
  const before = s.slice(0, i), after = s.slice(i)
  const a = Math.max(before.lastIndexOf('. '), before.lastIndexOf('? '), before.lastIndexOf('! '), before.lastIndexOf(': '))
  const bm = after.search(/[.?!](\s|$)/)
  return s.slice(a < 0 ? 0 : a + 2, bm < 0 ? s.length : i + bm + 1).trim().slice(0, 400)
}

function remarkActions() {
  const walk = (node) => {
    if (!node || !Array.isArray(node.children)) return
    if (node.type === 'link' || node.type === 'linkReference' || node.type === 'inlineCode' || node.type === 'code' || node.type === 'strong') return
    const next = []
    for (const ch of node.children) {
      if (ch.type === 'text') {
        const parts = splitAct(ch.value)
        if (parts.length === 1 && parts[0].t === 'text') { next.push(ch); continue }
        for (const p of parts) {
          if (p.t === 'text') next.push({ type: 'text', value: p.v })
          else next.push({ type: 'ccact', data: { hName: 'span', hProperties: { 'data-ccact': '1' }, hChildren: [{ type: 'text', value: p.v }] } })
        }
      } else { walk(ch); next.push(ch) }
    }
    node.children = next
  }
  return (tree) => { walk(tree) }
}

// Agent tags (2026-10-17, hbar: "whenever you name an agent in a conversation, make it clickable and a card
// appears"). A tag like LAW-1 or LOGISTICS-1, optionally followed by its "Callsign", becomes
// <span data-ccagent="LAW-1">; the renderer shows it as a link only when the tag is on the roster, so
// look-alikes (UTF-8, SHA-256) stay plain text.
const AGENT_RE_SRC = '\\b[A-Z]{2,12}-\\d{1,3}\\b(?:\\s\u201c[^\u201d]{1,30}\u201d|\\s"[^"\\n]{1,30}")?'

// text -> [{ t: 'text', v } | { t: 'agent', v, tag }]
function splitAgents(text) {
  const s = String(text == null ? '' : text)
  const re = new RegExp(AGENT_RE_SRC, 'g')
  const out = []
  let last = 0, m
  while ((m = re.exec(s))) {
    if (m.index > last) out.push({ t: 'text', v: s.slice(last, m.index) })
    out.push({ t: 'agent', v: m[0], tag: m[0].match(/^[A-Z]{2,12}-\d{1,3}/)[0] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ t: 'text', v: s.slice(last) })
  return out
}

function remarkAgents() {
  const walk = (node) => {
    if (!node || !Array.isArray(node.children)) return
    if (node.type === 'link' || node.type === 'linkReference' || node.type === 'code') return
    const next = []
    for (const ch of node.children) {
      if (ch.type === 'text' || ch.type === 'inlineCode') {
        const parts = splitAgents(ch.value)
        if (parts.length === 1 && parts[0].t === 'text') { next.push(ch); continue }
        for (const p of parts) {
          if (p.t === 'text') next.push(ch.type === 'inlineCode' ? { type: 'inlineCode', value: p.v } : { type: 'text', value: p.v })
          else next.push({ type: 'ccagent', data: { hName: 'span', hProperties: { 'data-ccagent': p.tag }, hChildren: [{ type: 'text', value: p.v }] } })
        }
      } else { walk(ch); next.push(ch) }
    }
    node.children = next
  }
  return (tree) => { walk(tree) }
}

module.exports = { splitChoices, splitMoney, remarkMoney, splitAct, sentenceAround, remarkActions, splitAgents, remarkAgents, ACT_PHRASES, MAX_CHOICES }
