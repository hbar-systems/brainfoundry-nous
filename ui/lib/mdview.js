// The md is the input, a visual is the output (hbar rule 2026-10-09). Pure functions that turn a
// markdown note into a structure the Files pane draws as a view: a tree of headings (collapsible),
// tables as data (sortable grids), checklists as items (toggles), and the files and links it names
// (clickable nodes). No React here; tests/test_cc_bridge.py runs this under node.
const { looksLikeFile } = require('./pathlinks')

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/
const FENCE = /^\s*(```|~~~)/
const TASK = /^(\s*)[-*+]\s+\[( |x|X)\]\s+(.*)$/
const SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/

function splitRow(line) {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  const cells = []
  let cur = '', tick = false
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (c === '`') tick = !tick
    if (c === '\\' && s[i + 1] === '|') { cur += '|'; i++; continue }
    if (c === '|' && !tick) { cells.push(cur.trim()); cur = ''; continue }
    cur += c
  }
  cells.push(cur.trim())
  return cells
}

// Lines of one section's body -> blocks: { type: 'md', text } | { type: 'table', head, rows, align } | { type: 'tasks', items }
function toBlocks(lines) {
  const blocks = []
  let buf = []
  const flush = () => { const t = buf.join('\n'); if (t.trim()) blocks.push({ type: 'md', text: t }); buf = [] }
  let i = 0, fence = false
  while (i < lines.length) {
    const ln = lines[i]
    if (FENCE.test(ln)) { fence = !fence; buf.push(ln); i++; continue }
    if (fence) { buf.push(ln); i++; continue }
    if (ln.includes('|') && i + 1 < lines.length && SEP.test(lines[i + 1]) && lines[i + 1].includes('-') && lines[i + 1].includes('|')) {
      flush()
      const head = splitRow(ln)
      const align = splitRow(lines[i + 1]).map(c => (c.startsWith(':') && c.endsWith(':') ? 'center' : c.endsWith(':') ? 'right' : 'left'))
      i += 2
      const rows = []
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) { rows.push(splitRow(lines[i])); i++ }
      blocks.push({ type: 'table', head, rows, align })
      continue
    }
    if (TASK.test(ln)) {
      flush()
      const items = []
      while (i < lines.length) {
        const m = TASK.exec(lines[i])
        if (!m) break
        items.push({ text: m[3], done: m[2] !== ' ', depth: Math.floor(m[1].replace(/\t/g, '  ').length / 2) })
        i++
      }
      blocks.push({ type: 'tasks', items })
      continue
    }
    buf.push(ln); i++
  }
  flush()
  return blocks
}

// -> { meta: string|null, root: { level: 0, title: null, blocks, children: [section] } }
// section = { id, level, title, blocks, children }
function parseMd(md) {
  let text = String(md == null ? '' : md).replace(/\r\n?/g, '\n')
  let meta = null
  const fm = /^---\n([\s\S]*?)\n---\n?/.exec(text)
  if (fm) { meta = fm[1]; text = text.slice(fm[0].length) }
  const root = { id: 's0', level: 0, title: null, lines: [], children: [] }
  const stack = [root]
  let n = 0, fence = false
  for (const ln of text.split('\n')) {
    if (FENCE.test(ln)) fence = !fence
    const m = !fence && !FENCE.test(ln) ? HEADING.exec(ln) : null
    if (m) {
      const sec = { id: 's' + (++n), level: m[1].length, title: m[2], lines: [], children: [] }
      while (stack.length > 1 && stack[stack.length - 1].level >= sec.level) stack.pop()
      stack[stack.length - 1].children.push(sec)
      stack.push(sec)
    } else stack[stack.length - 1].lines.push(ln)
  }
  const fin = (s) => { s.blocks = toBlocks(s.lines); delete s.lines; s.children.forEach(fin) }
  fin(root)
  return { meta, root }
}

function countSections(sec) { return sec.children.reduce((a, c) => a + 1 + countSections(c), 0) }

// Sort rows of a table by a column: numbers as numbers (a leading number, "12%", "$3,400"), else text, case-folded.
function cellNum(c) {
  const m = /^[^\d-]*(-?\d[\d,]*\.?\d*)/.exec(String(c).replace(/[`*_]/g, ''))
  return m ? parseFloat(m[1].replace(/,/g, '')) : NaN
}
function sortRows(rows, col, dir) {
  const k = dir === 'desc' ? -1 : 1
  const nums = rows.length > 0 && rows.every(r => !isNaN(cellNum(r[col] == null ? '' : r[col])))
  return rows.map((r, i) => [r, i]).sort((a, b) => {
    const x = a[0][col] == null ? '' : a[0][col], y = b[0][col] == null ? '' : b[0][col]
    const d = nums ? cellNum(x) - cellNum(y) : String(x).toLowerCase().localeCompare(String(y).toLowerCase(), undefined, { numeric: true })
    return d ? d * k : a[1] - b[1]
  }).map(p => p[0])
}

// Files and web links a note names (outside code fences): markdown links, inline code that is a file, bare absolute paths.
function extractRefs(md) {
  const out = [], seen = new Set()
  const add = (kind, target, label) => { const key = kind + '|' + target; if (!seen.has(key)) { seen.add(key); out.push({ kind, target, label: label || target }) } }
  let fence = false
  for (const ln of String(md || '').split('\n')) {
    if (FENCE.test(ln)) { fence = !fence; continue }
    if (fence) continue
    let m
    const link = /\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g
    while ((m = link.exec(ln))) {
      const t = m[2]
      if (/^https?:\/\//i.test(t)) add('url', t, m[1] || t)
      else if (t[0] !== '#' && !/^[a-z][a-z0-9+.-]*:/i.test(t)) add('file', t.replace(/#.*$/, ''), m[1] || t)
    }
    const code = /`([^`]+)`/g
    while ((m = code.exec(ln))) if (looksLikeFile(m[1])) add('file', m[1].trim())
    const abs = /(?:^|[\s(])(\/(?:home|opt|srv|var|tmp)\/[^\s`'"<>)\],;]+\.[A-Za-z][A-Za-z0-9]{0,5})/g
    while ((m = abs.exec(ln))) add('file', m[1])
  }
  return out
}

module.exports = { parseMd, toBlocks, splitRow, sortRows, extractRefs, countSections }
