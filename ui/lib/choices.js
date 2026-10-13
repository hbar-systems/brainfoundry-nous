// The visual layer, first step (hbar 2026-10-13: "make it a button and you send out an agent").
// Pure functions, no React: run under node by tests/test_cc_bridge.py, like pathlinks.js.
//
// Choices: the reasoner may end an answer with
//   <choices>[{"label": "...", "send": "...", "mode": "reply|agent"}]</choices>
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
  return { label, send, mode: c.mode === 'agent' ? 'agent' : 'reply' }
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

module.exports = { splitChoices, splitMoney, remarkMoney, MAX_CHOICES }
