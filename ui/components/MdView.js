import React, { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { parseMd, sortRows, extractRefs, countSections } from '../lib/mdview'
import { remarkPathLinks, hrefToPath, looksLikeFile } from '../lib/pathlinks'

// The md is the input, a visual is the output (hbar rule 2026-10-09). The clean view the Files pane
// draws for a markdown note that has no hand-made `<name>.view.html` beside it: headings as a
// collapsible tree, tables as sortable grids, checklists as toggles, links and file references as
// clickable nodes. Never raw monospace as the default; the source is one click away in the pane.
// Black, thin type, mono labels. No emoji, no native selects.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim, #9a8f82)', faint: 'var(--text-faint, #6b5f52)', line: 'var(--line, #2a2621)', card: 'var(--card, #16140f)', gold: 'var(--accent, #c9a96e)' }
const label = { ...mono, fontSize: '10px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.faint }
const linkBtn = { ...mono, fontSize: '11px', color: T.dim, cursor: 'pointer', textDecoration: 'underline' }

function dirOf(p) { const i = (p || '').lastIndexOf('/'); return i > 0 ? p.slice(0, i) : '' }

// Markdown inside a block. `open(target)` opens a file in the Files pane.
function Inline({ text, base, open, block }) {
  const components = useMemo(() => ({
    a: ({ node, href, children, ...props }) => {
      const cc = props['data-ccpath']
      const fp = cc || hrefToPath(href)
      if (fp) {
        const target = fp.startsWith('/') ? fp : (base ? `${base}/${fp}` : fp)
        return <a onClick={() => open(target)} title={`Open ${target}`} style={{ color: T.gold, cursor: 'pointer', textDecoration: 'underline dotted' }}>{children}</a>
      }
      return <a href={href} target="_blank" rel="noreferrer" style={{ color: T.gold }}>{children}</a>
    },
    code: ({ node, children, ...props }) => {
      const s = typeof children === 'string' ? children : (Array.isArray(children) && typeof children[0] === 'string' ? children[0] : null)
      if (s && looksLikeFile(s)) {
        const t = s.trim(); const target = t.startsWith('/') ? t : (base && !t.includes('/') ? `${base}/${t}` : t)
        return <a onClick={() => open(target)} title={`Open ${target}`} style={{ ...mono, fontSize: '12px', color: T.gold, cursor: 'pointer', textDecoration: 'underline dotted' }}>{s}</a>
      }
      return <code {...props} style={{ ...mono, fontSize: '12px', color: T.dim }}>{children}</code>
    },
    pre: ({ node, ...props }) => <pre {...props} style={{ ...mono, fontSize: '12px', lineHeight: 1.5, color: T.dim, backgroundColor: T.card, border: `1px solid ${T.line}`, borderRadius: '6px', padding: '8px 10px', margin: '6px 0 10px', overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }} />,
    p: ({ node, children }) => (block ? <p style={{ margin: '0 0 10px', fontWeight: 300, lineHeight: 1.7, fontSize: '15px' }}>{children}</p> : <>{children}</>),
    ul: ({ node, ...props }) => <ul {...props} style={{ margin: '0 0 10px', paddingLeft: '20px', fontWeight: 300, lineHeight: 1.7 }} />,
    ol: ({ node, ...props }) => <ol {...props} style={{ margin: '0 0 10px', paddingLeft: '22px', fontWeight: 300, lineHeight: 1.7 }} />,
    blockquote: ({ node, ...props }) => <blockquote {...props} style={{ margin: '0 0 10px', padding: '2px 0 2px 12px', borderLeft: `2px solid ${T.line}`, color: T.dim }} />,
    h1: ({ children }) => <p style={{ ...label, margin: '10px 0 4px' }}>{children}</p>,
    h2: ({ children }) => <p style={{ ...label, margin: '10px 0 4px' }}>{children}</p>,
    h3: ({ children }) => <p style={{ ...label, margin: '10px 0 4px' }}>{children}</p>,
    hr: () => <div style={{ borderTop: `1px solid ${T.line}`, margin: '10px 0' }} />,
    table: ({ node, ...props }) => <table {...props} style={{ borderCollapse: 'collapse', fontSize: '13px', margin: '4px 0 10px' }} />,
    th: ({ node, ...props }) => <th {...props} style={{ textAlign: 'left', padding: '4px 8px', borderBottom: `1px solid ${T.line}`, color: T.dim, fontWeight: 400 }} />,
    td: ({ node, ...props }) => <td {...props} style={{ padding: '4px 8px', borderBottom: `1px solid ${T.line}`, fontWeight: 300 }} />,
  }), [base, open, block])
  return <ReactMarkdown remarkPlugins={[remarkGfm, remarkPathLinks]} skipHtml components={components}>{text || ''}</ReactMarkdown>
}

// A table as a grid: click a heading to sort, click again to reverse; a small box filters the rows.
function Grid({ block, base, open }) {
  const [col, setCol] = useState(null)
  const [dir, setDir] = useState('asc')
  const [q, setQ] = useState('')
  let rows = block.rows
  if (q.trim()) { const k = q.trim().toLowerCase(); rows = rows.filter(r => r.some(c => String(c).toLowerCase().includes(k))) }
  if (col !== null) rows = sortRows(rows, col, dir)
  const pick = (i) => { if (col === i) setDir(d => (d === 'asc' ? 'desc' : 'asc')); else { setCol(i); setDir('asc') } }
  return (
    <div style={{ margin: '4px 0 14px' }}>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'baseline', marginBottom: '4px' }}>
        <span style={label}>{block.rows.length} row{block.rows.length === 1 ? '' : 's'}{q.trim() ? ` · ${rows.length} shown` : ''}</span>
        {block.rows.length > 6 && <input value={q} onChange={e => setQ(e.target.value)} placeholder="filter" spellCheck={false}
          style={{ ...mono, fontSize: '11px', color: T.ink, backgroundColor: 'transparent', border: 0, borderBottom: `1px solid ${T.line}`, outline: 'none', width: '110px', padding: '2px 0' }} />}
        {(col !== null || q) && <a onClick={() => { setCol(null); setQ('') }} style={linkBtn}>reset</a>}
      </div>
      <div style={{ overflowX: 'auto', border: `1px solid ${T.line}`, borderRadius: '6px' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: '13px' }}>
          <thead>
            <tr>{block.head.map((h, i) => (
              <th key={i} onClick={() => pick(i)} title="sort" style={{ textAlign: block.align[i] || 'left', padding: '6px 10px', borderBottom: `1px solid ${T.line}`, cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none', ...mono, fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 400, color: col === i ? T.gold : T.dim }}>
                {h.replace(/[`*_]/g, '')}{col === i ? (dir === 'asc' ? ' +' : ' -') : ''}
              </th>))}</tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>{block.head.map((_, ci) => (
                <td key={ci} style={{ textAlign: block.align[ci] || 'left', padding: '6px 10px', borderBottom: `1px solid ${T.line}`, verticalAlign: 'top', fontWeight: 300, minWidth: ci === 0 ? 0 : '80px' }}>
                  <Inline text={r[ci] == null ? '' : r[ci]} base={base} open={open} />
                </td>))}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// A checklist as toggles. The state is the viewer's own, kept in this browser per note; the note on
// disk is not rewritten by a click (edit the source to change it for good).
function Tasks({ block, base, open, store }) {
  const [state, setState] = useState(() => {
    let saved = null
    try { saved = JSON.parse(localStorage.getItem(store) || 'null') } catch (e) {}
    return block.items.map((it, i) => (saved && typeof saved[i] === 'boolean' ? saved[i] : it.done))
  })
  const flip = (i) => setState(s => { const n = s.map((v, j) => (j === i ? !v : v)); try { localStorage.setItem(store, JSON.stringify(n)) } catch (e) {} return n })
  const done = state.filter(Boolean).length
  return (
    <div style={{ margin: '4px 0 14px' }}>
      <div style={{ ...label, marginBottom: '4px' }}>{done} of {block.items.length} done</div>
      {block.items.map((it, i) => (
        <div key={i} onClick={() => flip(i)} style={{ display: 'flex', gap: '10px', alignItems: 'baseline', padding: '4px 0', paddingLeft: `${it.depth * 18}px`, cursor: 'pointer' }}>
          <span style={{ ...mono, fontSize: '11px', width: '28px', flexShrink: 0, color: state[i] ? T.gold : T.faint, border: `1px solid ${state[i] ? T.gold : T.line}`, borderRadius: '10px', textAlign: 'center', userSelect: 'none' }}>{state[i] ? 'on' : 'off'}</span>
          <span onClick={e => { if (e.target.closest && e.target.closest('a')) e.stopPropagation() }} style={{ flex: 1, minWidth: 0, fontWeight: 300, lineHeight: 1.6, color: state[i] ? T.faint : T.ink, textDecoration: state[i] ? 'line-through' : 'none' }}>
            <Inline text={it.text} base={base} open={open} />
          </span>
        </div>
      ))}
    </div>
  )
}

function Section({ sec, base, open, store, closed, setClosed, depth }) {
  const kids = sec.children
  const isClosed = closed.has(sec.id)
  const n = countSections(sec)
  const toggle = () => setClosed(c => { const x = new Set(c); if (x.has(sec.id)) x.delete(sec.id); else x.add(sec.id); return x })
  const size = [20, 18, 16, 15, 14, 14][Math.min(sec.level, 6) - 1] || 14
  return (
    <div style={{ marginTop: depth === 0 ? '14px' : '8px', borderTop: depth === 0 ? `1px solid ${T.line}` : 0, paddingTop: depth === 0 ? '8px' : 0 }}>
      <div onClick={toggle} style={{ display: 'flex', gap: '10px', alignItems: 'baseline', cursor: 'pointer' }}>
        <span style={{ ...mono, fontSize: '12px', width: '12px', color: T.gold, flexShrink: 0 }}>{isClosed ? '+' : '-'}</span>
        <span style={{ fontSize: `${size}px`, fontWeight: 300, color: T.ink, lineHeight: 1.4, flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}><Inline text={sec.title} base={base} open={open} /></span>
        {isClosed && n > 0 && <span style={{ ...mono, fontSize: '10px', color: T.faint }}>{n} below</span>}
      </div>
      {!isClosed && (
        <div style={{ marginLeft: '6px', paddingLeft: '16px', borderLeft: `1px solid ${T.line}`, marginTop: '6px' }}>
          {sec.blocks.map((b, i) => (
            b.type === 'table' ? <Grid key={i} block={b} base={base} open={open} />
              : b.type === 'tasks' ? <Tasks key={i} block={b} base={base} open={open} store={`${store}:${sec.id}:${i}`} />
                : <Inline key={i} text={b.text} base={base} open={open} block />
          ))}
          {kids.map(k => <Section key={k.id} sec={k} base={base} open={open} store={store} closed={closed} setClosed={setClosed} depth={depth + 1} />)}
        </div>
      )}
    </div>
  )
}

export default function MdView({ text, path, open }) {
  const base = dirOf(path)
  const parsed = useMemo(() => parseMd(text), [text])
  const refs = useMemo(() => extractRefs(text), [text])
  const all = []
  const collect = (s) => { s.children.forEach(c => { all.push(c); collect(c) }) }
  collect(parsed.root)
  // open the first two levels; deeper sections start folded so a long note reads as an outline
  const [closed, setClosed] = useState(() => new Set(all.filter(s => s.level >= 3 && s.children.length + s.blocks.length > 0).map(s => s.id)))
  const [showRefs, setShowRefs] = useState(false)
  const store = `mdview:${path}`
  return (
    <div style={{ color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
      <div style={{ display: 'flex', gap: '14px', alignItems: 'baseline', flexWrap: 'wrap', marginBottom: '6px' }}>
        <span style={label}>view · {all.length} section{all.length === 1 ? '' : 's'} · {refs.length} reference{refs.length === 1 ? '' : 's'}</span>
        <a onClick={() => setClosed(new Set())} style={linkBtn}>open all</a>
        <a onClick={() => setClosed(new Set(all.map(s => s.id)))} style={linkBtn}>fold all</a>
        {refs.length > 0 && <a onClick={() => setShowRefs(v => !v)} style={linkBtn}>{showRefs ? 'hide references' : 'references'}</a>}
      </div>
      {showRefs && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', margin: '4px 0 10px' }}>
          {refs.map((r, i) => (r.kind === 'url'
            ? <a key={i} href={r.target} target="_blank" rel="noreferrer" title={r.target} style={{ ...mono, fontSize: '11px', color: T.dim, border: `1px solid ${T.line}`, borderRadius: '12px', padding: '2px 9px', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</a>
            : <a key={i} onClick={() => open(r.target.startsWith('/') ? r.target : (base ? `${base}/${r.target}` : r.target))} title={r.target} style={{ ...mono, fontSize: '11px', color: T.gold, border: `1px solid ${T.line}`, borderRadius: '12px', padding: '2px 9px', cursor: 'pointer', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.target.split('/').pop()}</a>))}
        </div>
      )}
      {parsed.meta && <pre style={{ ...mono, fontSize: '11px', color: T.faint, margin: '6px 0', whiteSpace: 'pre-wrap' }}>{parsed.meta}</pre>}
      {parsed.root.blocks.map((b, i) => (
        b.type === 'table' ? <Grid key={i} block={b} base={base} open={open} />
          : b.type === 'tasks' ? <Tasks key={i} block={b} base={base} open={open} store={`${store}:root:${i}`} />
            : <Inline key={i} text={b.text} base={base} open={open} block />
      ))}
      {parsed.root.children.map(s => <Section key={s.id} sec={s} base={base} open={open} store={store} closed={closed} setClosed={setClosed} depth={0} />)}
    </div>
  )
}
