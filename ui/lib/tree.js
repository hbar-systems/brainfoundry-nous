// The thread tree (TREE-1, 2026-11-22, hbar: "an explanation card that i can click on any part on the
// growing tree ... and get quick clarity"). Pure functions, no React: run under node by
// tests/test_cc_bridge.py, like choices.js.
//
// The reasoner may put one block near the end of an answer, before <choices> and <pane>:
//   <tree>{"title": "This thread, 2026-11-22", "nodes": [
//     {"id": "1", "label": "Push", "state": "blocked", "note": "one short line", "why": "2-4 sentences",
//      "link": "https://... | /talk?thread=<id> | /update", "ask": "text for the chat box", "children": [...]}
//   ]}</tree>
// The page cuts the block out of the text and draws it as a tree of rows; a row opens its card.
// The block is not anchored to the end of the text: a <choices> block or the pane marker may follow it.

const TREE_STATES = ['done', 'yours', 'running', 'scheduled', 'later', 'blocked', 'killed']
const MAX_NODES = 120
const MAX_DEPTH = 6

// A block is "<tree>" followed by a JSON object or list. A bare mention of the tag in prose or in
// inline code (`<tree>`) is not a block and stays in the text.
const TREE_RE = /<tree>\s*([{[][\s\S]*?)\s*<\/tree>/g
// Still streaming in (opened, not closed): hidden up to the next block that may follow it, or the end.
const OPEN_RE = /<tree>\s*(?:[{[][\s\S]*?)?(?=<choices>|<pane>|\n*<!--pane:|$)/

function str(v, max) {
  return (typeof v === 'string' || typeof v === 'number' ? String(v) : '').replace(/\s+/g, ' ').trim().slice(0, max)
}

// A link is one of: a web address, a talk thread on this console, a console route. Anything else
// (javascript:, data:, //host, a bare word) is dropped.
//   -> { href, kind: 'web' | 'talk' | 'route' } | null
function treeLink(v) {
  const s = (typeof v === 'string' ? v : '').trim()
  if (!s || s.length > 600 || /[\s<>"'`\\]/.test(s)) return null
  if (/^https?:\/\/[^/]+/i.test(s)) return { href: s, kind: 'web' }
  if (/^\/(?!\/)/.test(s)) return { href: s, kind: /^\/talk(?:[/?#]|$)/.test(s) ? 'talk' : 'route' }
  return null
}

function cleanNode(n, path, depth, budget) {
  if (!n || typeof n !== 'object' || Array.isArray(n) || budget.left <= 0) return null
  const label = str(n.label, 120)
  if (!label) return null
  budget.left -= 1
  const raw = str(n.state, 24).toLowerCase()
  const out = { id: str(n.id, 40) || path, label, state: TREE_STATES.includes(raw) ? raw : 'unknown' }
  if (out.state === 'unknown' && raw) out.raw = raw
  const note = str(n.note, 200); if (note) out.note = note
  const why = str(n.why, 1200); if (why) out.why = why
  const link = treeLink(n.link); if (link) out.link = link
  const ask = str(n.ask, 2000); if (ask) out.ask = ask
  out.children = depth < MAX_DEPTH ? cleanNodes(n.children, path, depth + 1, budget) : []
  return out
}

function cleanNodes(list, path, depth, budget) {
  if (!Array.isArray(list)) return []
  const out = []
  const seen = new Set()
  list.forEach((n, i) => {
    const c = cleanNode(n, (path ? path + '.' : '') + (i + 1), depth, budget)
    if (!c) return
    if (seen.has(c.id)) c.id = (path ? path + '.' : '') + (i + 1) + '#' + i
    seen.add(c.id)
    out.push(c)
  })
  return out
}

// JSON text -> { title, nodes } | null   (null: not JSON, not a tree, or no usable node)
function parseTree(json) {
  let v
  try { v = JSON.parse(json) } catch (e) { return null }
  if (Array.isArray(v)) v = { nodes: v }
  if (!v || typeof v !== 'object') return null
  const nodes = cleanNodes(v.nodes, '', 1, { left: MAX_NODES })
  if (nodes.length === 0) return null
  return { title: str(v.title, 120), nodes }
}

// text -> { body, tree }   (tree: null when there is no block or it does not parse)
// Every closed block is cut out of the body; the last one that parses is the tree. A block still
// streaming in is hidden, so raw JSON never flashes. What follows the block (choices, the pane
// marker) stays in the body, so splitChoices and splitPane read it as before, in either order.
function splitTree(text) {
  const s = String(text == null ? '' : text)
  if (s.indexOf('<tree>') < 0) return { body: s, tree: null }
  let tree = null
  let body = ''
  let last = 0
  let m
  const re = new RegExp(TREE_RE.source, 'g')
  const join = (a, b) => { const x = a.trimEnd(); const y = b.replace(/^\s+/, ''); return x && y ? x + '\n\n' + y : x + y }
  while ((m = re.exec(s))) {
    const t = parseTree(m[1])
    if (t) tree = t
    body = join(body, s.slice(last, m.index))
    last = m.index + m[0].length
  }
  let rest = s.slice(last)
  const open = rest.match(OPEN_RE)
  if (open) rest = join(rest.slice(0, open.index), rest.slice(open.index + open[0].length))
  body = last === 0 ? rest : join(body, rest)
  return { body: last === 0 && !open ? s : body.trimEnd(), tree }
}

// What Talk puts in the chat box: the node's own ask, or a start the person finishes.
function treeAsk(node) {
  if (!node) return ''
  if (node.ask) return node.ask
  const st = node.state === 'unknown' ? (node.raw || '') : node.state
  return 'About "' + node.label + '"' + (st ? ' (' + st + ')' : '') + ': '
}

// { done: 2, yours: 1, ... } over every node, for the one line above the tree.
function treeCounts(tree) {
  const out = {}
  const walk = (list) => { for (const n of list || []) { out[n.state] = (out[n.state] || 0) + 1; walk(n.children) } }
  walk(tree && tree.nodes)
  return out
}

module.exports = { splitTree, parseTree, treeLink, treeAsk, treeCounts, TREE_STATES, MAX_NODES, MAX_DEPTH }
