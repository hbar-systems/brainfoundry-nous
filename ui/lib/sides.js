// Talk in place (INLINE-1, 2026-11-23): the console's side of /cc/sides. Pure functions, no DOM:
// ui/components/SideNote.js and SidesFooter.js use them, tests/test_cc_sides.py runs them under node.
// The same doors as scripts/cc/static/inline.js (the script brain-built pages include).

// The key of a tree node's note: bound to the thread and the node, so the same node in a later tree
// of the same thread opens the same note. A page on a brand new conversation has none.
function treeKey(cur, node) {
  if (!cur || String(cur).startsWith('new:') || !node || !node.id) return null
  const k = 'tree:' + String(cur).slice(0, 80) + ':' + String(node.id).replace(/[^A-Za-z0-9._:/#@-]/g, '-').slice(0, 60)
  return /^[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,159}$/.test(k) ? k : null
}

// The body of one turn.
function sayBody(item, message, mode) {
  return {
    key: item.key, message: String(message || '').trim(), mode: mode === 'agent' ? 'agent' : 'ask',
    title: String(item.title || '').slice(0, 160), text: String(item.text || '').slice(0, 2000),
    link: item.link || '', page: item.page || 'console', home: item.home || undefined,
  }
}

function busy(side) {
  return !!side && (side.state === 'running' || side.state === 'waiting')
}

// One word for the box's state line.
function stateWord(side) {
  if (!side) return ''
  if (side.state === 'running') return 'working…'
  if (side.state === 'waiting') return 'waits for a free seat'
  if (side.state === 'failed') return 'did not finish' + (side.error ? ': ' + side.error : '')
  if (side.ready) return 'answer ready'
  return ''
}

// The footer's line: "1 answer ready" / "3 answers ready", or nothing.
function footerLine(n) {
  n = Number(n) || 0
  if (n <= 0) return ''
  return n === 1 ? '1 answer ready' : n + ' answers ready'
}

// Where a press on the footer goes: the item's page, opened on its note.
function jumpHref(item) {
  if (!item) return null
  const link = String(item.link || '')
  const safe = (link.startsWith('/') && !link.startsWith('//')) || link.startsWith('https://')
  if (!safe) return null
  const base = link.split('#')[0]
  return /^\/cc\/page\//.test(base) ? base + '#talk=' + encodeURIComponent(item.key) : link
}

module.exports = { treeKey, sayBody, busy, stateWord, footerLine, jumpHref }
