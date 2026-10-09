// Paths in messages become links (2026-10-09). Pure functions, no React: ui/lib/pathlinks.js is also
// run under node by tests/test_cc_bridge.py.
//
// What a person sees: "Attached on the box: /home/hands/in/2026-10-09/Screenshot 2026-10-09 at 10.12.34 AM.png"
// as text. Now every absolute path under an in/ or out/ folder (spaces allowed in the file name, the
// way the upload keeps them) and any other absolute path with a file suffix is a link that opens in
// the Files pane; images also preview on hover.

// A file name ends at a suffix that starts with a letter (so "10.12.34 AM.png" is one name, not "10.12")
// and is followed by the end, space, comma, a closing bracket or sentence punctuation.
const AFTER = '(?=$|[\\s,;:)\\]}\'"!?<>*`]|\\.(?:\\s|$))'
const DESK = '\\/home\\/[\\w.-]+\\/(?:in|out)\\/(?:[^\\/\\s,`"<>|]+\\/)*[^\\/\\n,`"<>|]+?\\.[A-Za-z][A-Za-z0-9]{0,5}' + AFTER
const ANY = '\\/(?:home|opt|srv|var|tmp|Users)\\/[^\\s`\'"<>|,;()\\[\\]]+?\\.[A-Za-z][A-Za-z0-9]{0,5}' + AFTER
const PATH_RE_SRC = '(?:' + DESK + ')|(?:' + ANY + ')'

function tidy(p) { return String(p || '').replace(/[.,;:)\]}>'"!?*`]+$/, '') }

// text -> [{ t: 'text', v } | { t: 'path', v }]
function splitPaths(text) {
  const s = String(text == null ? '' : text)
  const re = new RegExp(PATH_RE_SRC, 'g')
  const out = []
  let last = 0, m
  while ((m = re.exec(s))) {
    if (m[0].length === 0) { re.lastIndex++; continue }
    if (m.index > last) out.push({ t: 'text', v: s.slice(last, m.index) })
    out.push({ t: 'path', v: m[0] })
    last = m.index + m[0].length
  }
  if (last < s.length) out.push({ t: 'text', v: s.slice(last) })
  return out
}

const IMAGE_RE = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i
function isImagePath(p) { return IMAGE_RE.test(tidy(p)) }
function rawUrl(p) { return '/cc/files/raw' + String(p).split('/').map(encodeURIComponent).join('/') }

// A markdown link target that is a file on the box or in the world, not a web address or an in-page
// anchor: "ops/x.md", "./x.md#part", "/home/hands/in/...png", "file:///home/...". null otherwise.
function hrefToPath(href) {
  let h = String(href || '').trim()
  if (!h || h[0] === '#') return null
  if (/^file:\/\//i.test(h)) h = h.replace(/^file:\/\//i, '')
  else if (/^[a-z][a-z0-9+.-]*:/i.test(h)) return null          // http:, mailto:, tel: ...
  if (h.startsWith('//')) return null
  try { h = decodeURIComponent(h) } catch (e) {}
  h = h.replace(/#[^/]*$/, '').replace(/\?[^/]*$/, '')
  if (h.startsWith('/') && !/^\/(home|opt|srv|var|tmp|Users)\//.test(h)) return null   // a console route, not a file
  if (!/\.[A-Za-z][A-Za-z0-9]{0,5}$/.test(h) && !h.endsWith('/')) return null
  return h
}

// remark plugin: plain text nodes (not inside links or code) get their paths turned into links
// whose hast property data-ccpath the renderer's `a` component reads.
function remarkPathLinks() {
  const walk = (node) => {
    if (!node || !Array.isArray(node.children)) return
    if (node.type === 'link' || node.type === 'linkReference' || node.type === 'inlineCode' || node.type === 'code') return
    const next = []
    for (const ch of node.children) {
      if (ch.type === 'text') {
        const parts = splitPaths(ch.value)
        if (parts.length === 1 && parts[0].t === 'text') { next.push(ch); continue }
        for (const p of parts) {
          if (p.t === 'text') next.push({ type: 'text', value: p.v })
          else next.push({ type: 'link', url: '#', title: null, data: { hProperties: { 'data-ccpath': p.v } }, children: [{ type: 'text', value: p.v }] })
        }
      } else { walk(ch); next.push(ch) }
    }
    node.children = next
  }
  return (tree) => { walk(tree) }
}

// An inline-code span that names a file: an absolute path on the box, or a bare name / relative path with a suffix.
function looksLikeFile(s) {
  const t = String(s || '').trim()
  if (!t || t.length > 300 || t.includes('..')) return false
  if (/^\/(home|opt|srv|var|tmp|Users)\/[^\n]+$/.test(t)) return true
  return /^[\w][\w.\/ -]{0,200}\.[A-Za-z][A-Za-z0-9]{0,4}$/.test(t)
}

module.exports = { looksLikeFile, splitPaths, isImagePath, rawUrl, hrefToPath, remarkPathLinks, tidy }
