// Press, do not drag (2026-10-09). Pure functions, no DOM: ui/lib/spanpick.js is also run under node
// by tests/test_cc_bridge.py.
//
// A message's rendered text is flattened to one string (a "\n" where one block ends and the next
// begins). A click lands on an offset in that string; pickSpan answers which stretch of it to
// underline: level 0 the clause or short phrase around the word (4 to 12 words, bounded by
// punctuation), level 1 the sentence, level 2 the paragraph or list item (the "\n" block).
// ladder() lists the distinct spans from narrowest to widest so "wider" and "narrower" always move.

const MIN_WORDS = 4
const MAX_WORDS = 12
const ABBREV = /^(e\.g|i\.e|etc|vs|cf|dr|mr|mrs|ms|prof|st|no|fig|approx|al)$/i

// tokens (runs of non-space) inside [s, e)
function tokens(text, s, e) {
  const out = []
  const re = /\S+/g
  re.lastIndex = s
  let m
  while ((m = re.exec(text)) && m.index < e) out.push([m.index, Math.min(m.index + m[0].length, e)])
  return out
}

function paragraphBounds(text, off) {
  let s = off; while (s > 0 && text[s - 1] !== '\n') s--
  let e = off; while (e < text.length && text[e] !== '\n') e++
  return [s, e]
}

// the cut points inside a paragraph where a sentence ends (offset just after the terminator)
function sentenceCuts(text, ps, pe) {
  const cuts = []
  const re = /[.!?]+["'”’)\]]*(?=\s|$)/g
  const seg = text.slice(ps, pe)
  let m
  while ((m = re.exec(seg))) {
    const before = seg.slice(0, m.index).match(/(\S+)$/)
    const w = before ? before[1].replace(/^[("'“\[]+/, '') : ''
    if (m[0][0] === '.' && m[0].length === 1 && (ABBREV.test(w) || /^[A-Za-z]$/.test(w))) continue
    cuts.push(ps + m.index + m[0].length)
  }
  return cuts
}

// the cut points inside a sentence where a clause ends (offset just after the punctuation)
function clauseCuts(text, ss, se) {
  const cuts = []
  const seg = text.slice(ss, se)
  const re = /[,;:](?=\s|$)|\)|\s[—–-]+\s|(?=\()/g
  let m
  while ((m = re.exec(seg))) {
    if (m[0] === '') { if (m.index > 0) cuts.push(ss + m.index); re.lastIndex = m.index + 1; continue }
    cuts.push(ss + m.index + (/^\s/.test(m[0]) ? 0 : m[0].length))
  }
  return cuts
}

function trimSpan(text, s, e, strip) {
  const junk = strip ? /[\s,;:]/ : /\s/
  while (s < e && junk.test(text[s])) s++
  while (e > s && junk.test(text[e - 1])) e--
  return [s, e]
}

// the token at or nearest to off inside [ps, pe)
function nearestToken(text, off, ps, pe) {
  const ts = tokens(text, ps, pe)
  if (!ts.length) return null
  let best = ts[0], bd = Infinity
  for (const t of ts) {
    const d = off < t[0] ? t[0] - off : off > t[1] ? off - t[1] : 0
    if (d < bd) { bd = d; best = t }
  }
  return best
}

// level 0, 1, 2 -> [start, end) in text, or null when the paragraph holds no words
function pickSpan(text, off, level) {
  text = String(text == null ? '' : text)
  if (!text.trim()) return null
  off = Math.max(0, Math.min(text.length, off | 0))
  const lv = Math.max(0, Math.min(2, level | 0))
  // a click on a block break belongs to the block before it unless that is empty
  let [ps, pe] = paragraphBounds(text, off === text.length || text[off] === '\n' ? Math.max(0, off - 1) : off)
  if (!text.slice(ps, pe).trim()) { [ps, pe] = paragraphBounds(text, off); if (!text.slice(ps, pe).trim()) return null }
  if (lv === 2) return trimSpan(text, ps, pe, false)

  const tok = nearestToken(text, Math.max(ps, Math.min(off, pe)), ps, pe)
  if (!tok) return null
  const at = tok[0]

  // the sentence holding the token
  const sc = sentenceCuts(text, ps, pe)
  let ss = ps, se = pe
  for (const c of sc) { if (c <= at) ss = c; else { se = c; break } }
  if (lv === 1) return trimSpan(text, ss, se, false)

  // clauses of that sentence
  const cc = [ss, ...clauseCuts(text, ss, se).filter(c => c > ss && c < se), se]
  const clauses = []
  for (let i = 0; i + 1 < cc.length; i++) if (cc[i + 1] > cc[i]) clauses.push([cc[i], cc[i + 1]])
  let ci = clauses.findIndex(c => at >= c[0] && at < c[1])
  if (ci < 0) ci = clauses.length - 1
  let [a, b] = clauses[ci]
  let lo = ci, hi = ci
  const count = () => tokens(text, a, b).length
  // too short: take in the neighbouring clause (the following one first), inside the sentence
  while (count() < MIN_WORDS && (lo > 0 || hi < clauses.length - 1)) {
    const next = hi < clauses.length - 1 ? 1 : 0
    if (next) { hi++; b = clauses[hi][1] } else { lo--; a = clauses[lo][0] }
  }
  // too long: a window of MAX_WORDS around the clicked word
  const ts = tokens(text, a, b)
  if (ts.length > MAX_WORDS) {
    const k = Math.max(0, ts.findIndex(t => at >= t[0] && at < t[1] + 1))
    let from = Math.max(0, Math.min(k - Math.floor(MAX_WORDS / 2), ts.length - MAX_WORDS))
    a = ts[from][0]; b = ts[from + MAX_WORDS - 1][1]
  }
  return trimSpan(text, a, b, true)
}

// distinct spans, narrowest first, each containing the one before (a wider level that adds nothing is dropped)
function ladder(text, off) {
  const out = []
  for (let l = 0; l <= 2; l++) {
    const s = pickSpan(text, off, l)
    if (!s) continue
    const last = out[out.length - 1]
    if (last && s[0] === last[0] && s[1] === last[1]) continue
    if (last && !(s[0] <= last[0] && s[1] >= last[1])) continue
    out.push(s)
  }
  return out
}

// segs: [{ start, len }] in order, the rendered text nodes' places in the flattened string.
// pos -> { i, off } the node index and the offset inside it. isEnd: a span's end sits at the end of
// the node it closes in, not at the start of the next one.
function locate(segs, pos, isEnd) {
  for (let i = 0; i < segs.length; i++) {
    const s = segs[i]
    if (isEnd ? (pos > s.start && pos <= s.start + s.len) : (pos >= s.start && pos < s.start + s.len)) return { i, off: pos - s.start }
  }
  // inside a block break or past the end: snap to the nearest node edge
  if (!segs.length) return null
  if (isEnd) { for (let i = segs.length - 1; i >= 0; i--) if (segs[i].start < pos) return { i, off: Math.min(segs[i].len, pos - segs[i].start) } ; return { i: 0, off: 0 } }
  for (let i = 0; i < segs.length; i++) if (segs[i].start >= pos) return { i, off: 0 }
  const l = segs.length - 1
  return { i: l, off: segs[l].len }
}

// the inverse of locate for a click: node index + offset in it -> position in the flattened string
function positionOf(segs, i, off) {
  return segs[i] ? segs[i].start + Math.max(0, Math.min(segs[i].len, off)) : -1
}

module.exports = { pickSpan, ladder, locate, positionOf, MIN_WORDS, MAX_WORDS }
