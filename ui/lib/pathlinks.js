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
// A relative path ("ops/x.md") goes as ?path= so the bridge resolves it in the world; before 2026-10-18 it was glued
// on without a slash (/cc/files/rawops/x.md) and every relative link in an answer read "file not found".
function rawUrl(p) {
  const s = String(p)
  if (!s.startsWith('/')) return '/cc/files/raw?path=' + encodeURIComponent(s)
  return '/cc/files/raw' + s.split('/').map(encodeURIComponent).join('/')
}

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

// Markdown files open as a pop-up card with the text rendered (2026-10-14, hbar: "any .md named in an
// answer opens as a pop-up card, never through Files").
const MD_RE = /\.(md|markdown)$/i
function isMdPath(p) { return MD_RE.test(tidy(p)) }

// A console link to a markdown file's raw bytes (https://console.../cc/files/raw/home/...x.md) is that
// file's path, so it opens as the card instead of downloading. null for anything else.
function rawHrefToMdPath(href) {
  const m = String(href || '').trim().match(/^(?:https?:\/\/[^/]+)?\/cc\/files\/raw(\/[^?#]+)/i)
  if (!m) return null
  let p = m[1]
  try { p = decodeURIComponent(p) } catch (e) {}
  return isMdPath(p) && !p.includes('/../') ? p : null
}

// The page's own attachment line ("...\n\nAttached on the box: /a.png, /b.md", cc.js send and the
// Telegram lane) split off a person's message, so the files show as chips that open again on click.
// Upload names never carry a comma (Uploads._safe_name), so ", /" separates them.
function splitAttached(text) {
  const s = String(text == null ? '' : text)
  const m = s.match(/(?:^|\n)Attached on the box: ([^\n]+)\s*$/)
  if (!m) return { text: s, files: [] }
  const files = m[1].split(/,\s*(?=\/)/).map(x => x.trim()).filter(x => x.startsWith('/'))
  return files.length ? { text: s.slice(0, m.index).replace(/\s+$/, ''), files } : { text: s, files: [] }
}

// A web address that ends a sentence never takes the sentence's last mark (FILES-ARCHIVE-1 2026-11-28, hbar 2026-11-27:
// ".../done.html." opened nothing). Trailing full stops, commas, colons, quotes (straight and curly), * _ ~ and a
// closing bracket the address did not open come off; "(see a.org/x_(y))" keeps its own bracket.
const URL_TAIL = /[.,;:!?*_~'"\u2018\u2019\u201c\u201d\u00bb\u203a]$/
const PAIRS = { ')': '(', ']': '[', '}': '{', '>': '<' }
function tidyUrl(u) {
  let s = String(u == null ? '' : u)
  for (let i = 0; i < 40 && s; i++) {
    const c = s[s.length - 1]
    if (URL_TAIL.test(c)) { s = s.slice(0, -1); continue }
    if (PAIRS[c]) {
      const open = s.split(PAIRS[c]).length - 1, close = s.split(c).length - 1
      if (close > open) { s = s.slice(0, -1); continue }
    }
    break
  }
  return s
}

// remark plugin: a link whose text is its own address (GFM autolink literal, <...>) is trimmed with tidyUrl,
// and what came off goes back into the sentence as text. A written [label](url) is left as written.
function remarkTidyLinks() {
  const walk = (node) => {
    if (!node || !Array.isArray(node.children)) return
    const next = []
    for (const ch of node.children) {
      if (ch.type === 'link' && /^(?:https?:\/\/|mailto:|www\.)/i.test(ch.url || '') && ch.children && ch.children.length === 1 && ch.children[0].type === 'text') {
        const label = ch.children[0].value
        const bare = (ch.url || '').replace(/^mailto:/i, '')
        if (label === ch.url || label === bare || 'http://' + label === ch.url || 'https://' + label === ch.url) {
          const url = tidyUrl(ch.url), cut = ch.url.length - url.length
          if (cut > 0 && label.length > cut && label.endsWith(ch.url.slice(url.length))) {
            next.push({ ...ch, url, children: [{ type: 'text', value: label.slice(0, label.length - cut) }] })
            next.push({ type: 'text', value: ch.url.slice(url.length) })
            continue
          }
        }
        next.push(ch); continue
      }
      walk(ch); next.push(ch)
    }
    node.children = next
  }
  return (tree) => { walk(tree) }
}


// The folder a bare file name in an answer belongs to (LINK-FIX-1, 2026-11-28). Before, the LAST absolute
// folder anywhere in the message was the base for every bare name in it, so an answer that listed
// "Three files in `/home/hands/out/d/pkg/`: `a_b.pdf`, `c.tar.gz`" and later named
// `/home/hands/out/d/rehearse/index.html` linked a_b.pdf to .../rehearse/a_b.pdf, and every one of those
// links said "not a path the reasoner can reach". Now a name takes the nearest folder named BEFORE it
// (a folder, or the folder of a full file path); with none before it, the first one after it, a folder
// written as a folder ("/a/b/") first.
const FOLDER_RE = /\/(?:home|opt|srv|var|tmp|Users)\/[^\s`'"()<>|,;]*\//g
function folderMarks(text) {
  const s = String(text == null ? '' : text)
  const out = []
  const re = new RegExp(FOLDER_RE.source, 'g')
  let m
  while ((m = re.exec(s))) {
    const end = m.index + m[0].length
    // explicit: the path stops at this slash (`/a/b/`, "/a/b/ and"); otherwise it is a file's folder
    const explicit = end >= s.length || !/[^\s`'"()<>|,;]/.test(s[end])
    out.push({ start: m.index, end, dir: m[0].replace(/\/+$/, ''), explicit })
  }
  return out
}
function baseAt(marks, offset) {
  if (!marks || !marks.length) return null
  if (typeof offset !== 'number' || offset < 0) return marks[marks.length - 1].dir
  const before = marks.filter(m => m.end <= offset)
  if (before.length) return before[before.length - 1].dir
  const after = marks.filter(m => m.start >= offset)
  const exa = after.filter(m => m.explicit)
  return (exa.length ? exa[0] : after[0] || marks[marks.length - 1]).dir
}

// The file an inline-code span names, or null: an absolute path as written (trailing punctuation off), a
// bare name joined to its folder, a relative path (ops/x.md) as written for the bridge to resolve.
function codeTarget(s, base) {
  const t = String(s || '').trim()
  if (!t || t.length >= 300) return null
  if (/^\/(home|opt|srv|var|tmp)\/[^\n]+$/.test(t)) return t.replace(/[.,:;)]+$/, '')
  if (/^[\w][\w.\/ -]{0,200}\.[A-Za-z0-9]{1,5}$/.test(t) && !t.includes('..')) return base && !t.includes('/') ? `${base}/${t}` : t
  return null
}

module.exports = { folderMarks, baseAt, codeTarget, looksLikeFile, splitPaths, isImagePath, isMdPath, rawUrl, hrefToPath, rawHrefToMdPath, splitAttached, remarkPathLinks, remarkTidyLinks, tidy, tidyUrl }
