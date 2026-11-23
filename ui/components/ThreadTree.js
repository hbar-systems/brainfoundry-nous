// The thread tree (TREE-1, 2026-11-22). hbar: "with each message an updated tree-branch-system of the
// subpoints ... each one should have an explanation card that i can click on any part on the growing
// tree at the end of message and get quick clarity".
// The block is parsed by ui/lib/tree.js; this draws it. A row opens its card: the why, one full
// link, then Talk, which fills the chat box (it never sends by itself).
// INLINE-1 (2026-11-23): Talk opens a small note box on the card itself (hbar: "I don't want to leave this
// page"); the turn goes to a side conversation bound to this node, the answer comes back in the box. A page on
// a conversation with no id yet keeps the old Talk (it fills the chat box).
import { useState } from 'react'
import { treeAsk, treeCounts } from '../lib/tree'
import { treeKey } from '../lib/sides'
import SideNote from './SideNote'

const mono = { fontFamily: 'var(--font-mono, monospace)' }
const ORDER = ['blocked', 'yours', 'running', 'scheduled', 'later', 'done', 'killed', 'unknown']
// One colour and one word per state. The words are the ones the person reads on the row.
const STATE = {
  done: { word: 'done', color: '#7f9a6b' },
  yours: { word: 'yours', color: 'var(--accent)' },
  running: { word: 'running', color: '#6f9bb3' },
  scheduled: { word: 'scheduled', color: '#a58bc2' },
  later: { word: 'later', color: 'var(--muted)' },
  blocked: { word: 'blocked', color: '#c06a54' },
  killed: { word: 'killed', color: 'var(--muted)' },
  unknown: { word: '', color: 'var(--muted)' },
}

function emit(name, detail) {
  if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(name, { detail }))
}

function Dot({ state }) {
  const s = STATE[state] || STATE.unknown
  const hollow = state === 'later' || state === 'killed' || state === 'unknown'
  return <span aria-hidden="true" style={{ flex: '0 0 auto', width: '9px', height: '9px', marginTop: '5px', borderRadius: '50%',
    border: '1.5px solid ' + s.color, backgroundColor: hollow ? 'transparent' : s.color }} />
}

function Door({ onClick, children, accent, title }) {
  return <a onClick={(e) => { e.stopPropagation(); onClick() }} title={title} role="button" tabIndex={0}
    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
    style={{ ...mono, fontSize: '11px', padding: '3px 10px', borderRadius: '12px', cursor: 'pointer', whiteSpace: 'nowrap',
      border: '1px solid ' + (accent ? 'var(--accent)' : 'var(--border)'), color: accent ? 'var(--accent)' : 'var(--muted)' }}>{children}</a>
}

function openLink(link) {
  if (!link) return
  if (link.kind === 'route') emit('cc-open-route', { route: link.href, title: link.href.replace(/^\//, '').split('?')[0] || 'pane' })
  else if (typeof window !== 'undefined') window.open(link.href, '_blank', 'noopener')
}

function Card({ node, cur, title }) {
  const s = STATE[node.state] || STATE.unknown
  const key = treeKey(cur, node)
  const [talk, setTalk] = useState(false)
  const word = node.state === 'unknown' ? (node.raw || '') : s.word
  return (
    <div data-tree-card={node.id} style={{ margin: '4px 0 8px 19px', padding: '10px 12px', borderRadius: '8px',
      border: '1px solid var(--border)', backgroundColor: 'var(--surface2)' }}>
      {word ? <div style={{ ...mono, fontSize: '10px', letterSpacing: '0.08em', textTransform: 'uppercase', color: s.color, marginBottom: '4px' }}>{word}</div> : null}
      <div style={{ fontSize: '14px', lineHeight: 1.5, color: 'var(--text)', overflowWrap: 'anywhere' }}>
        {node.why || node.note || 'No explanation was written for this branch. Press Talk to ask.'}
      </div>
      {node.link ? (
        <div style={{ marginTop: '6px' }}>
          <a onClick={(e) => { e.stopPropagation(); openLink(node.link) }} role="link" tabIndex={0}
            style={{ ...mono, fontSize: '12px', color: 'var(--accent)', cursor: 'pointer', textDecoration: 'underline', overflowWrap: 'anywhere' }}>{node.link.href}</a>
        </div>
      ) : null}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
        {key
          ? <Door accent onClick={() => setTalk(t => !t)} title="A small box right here: ask, clarify or send an agent; the answer comes back in it">{talk ? 'fold' : 'talk'}</Door>
          : <Door accent onClick={() => emit('cc-fill-text', treeAsk(node))} title="Puts this in the chat box; you finish and send it">talk</Door>}
        {node.link ? <Door onClick={() => openLink(node.link)} title={node.link.href}>open</Door> : null}
      </div>
      {key && talk ? <SideNote item={{ key, title: node.label, text: [title ? 'Tree: ' + title + '.' : '', node.why || node.note || '', node.state ? 'State: ' + node.state + '.' : '', node.link ? 'Link: ' + node.link.href : ''].filter(Boolean).join(' '),
        link: '/talk?thread=' + encodeURIComponent(cur), page: 'console tree', home: cur }} /> : null}
    </div>
  )
}

function Row({ node, depth, open, toggle, shut, fold, cur, title }) {
  const kids = node.children || []
  const isOpen = open === node.id
  const folded = shut.has(node.id)
  const gone = node.state === 'killed'
  const quiet = gone || node.state === 'done'
  const s = STATE[node.state] || STATE.unknown
  const word = node.state === 'unknown' ? (node.raw || '') : s.word
  return (
    <div style={{ marginLeft: depth ? '14px' : 0, paddingLeft: depth ? '10px' : 0, borderLeft: depth ? '1px solid var(--border)' : 'none' }}>
      <div data-tree-row={node.id} onClick={() => toggle(node.id)} role="button" tabIndex={0} aria-expanded={isOpen}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(node.id) } }}
        style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '4px 6px', borderRadius: '6px', cursor: 'pointer',
          backgroundColor: isOpen ? 'var(--surface2)' : 'transparent' }}>
        <Dot state={node.state} />
        <span style={{ flex: '1 1 auto', minWidth: 0, overflowWrap: 'anywhere', lineHeight: 1.45 }}>
          <span style={{ fontSize: '14px', color: quiet ? 'var(--muted)' : 'var(--text)', textDecoration: gone ? 'line-through' : 'none' }}>{node.label}</span>
          {word ? <span style={{ ...mono, fontSize: '10px', letterSpacing: '0.06em', textTransform: 'uppercase', color: s.color, marginLeft: '8px', whiteSpace: 'nowrap' }}>{word}</span> : null}
          {node.note ? <span style={{ display: 'block', fontSize: '12px', color: 'var(--muted)' }}>{node.note}</span> : null}
        </span>
        {kids.length ? (
          <a onClick={(e) => { e.stopPropagation(); fold(node.id) }} role="button" tabIndex={0} title={folded ? 'show its branches' : 'hide its branches'}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); fold(node.id) } }}
            style={{ ...mono, flex: '0 0 auto', fontSize: '11px', color: 'var(--muted)', padding: '1px 6px', cursor: 'pointer' }}>{folded ? '+' + kids.length : '−'}</a>
        ) : null}
      </div>
      {isOpen ? <Card node={node} cur={cur} title={title} /> : null}
      {!folded ? kids.map((k) => <Row key={k.id} node={k} depth={depth + 1} open={open} toggle={toggle} shut={shut} fold={fold} cur={cur} title={title} />) : null}
    </div>
  )
}

export default function ThreadTree({ tree, cur }) {
  const [open, setOpen] = useState(null)
  const [shut, setShut] = useState(() => new Set())
  if (!tree || !tree.nodes || tree.nodes.length === 0) return null
  const toggle = (id) => setOpen((o) => (o === id ? null : id))
  const fold = (id) => setShut((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const counts = treeCounts(tree)
  const line = ORDER.filter((k) => counts[k] && k !== 'unknown').map((k) => counts[k] + ' ' + STATE[k].word).join(' · ')
  return (
    <div data-nopick="1" data-thread-tree="1" style={{ marginTop: '10px', padding: '10px 8px 8px', borderRadius: '10px', border: '1px solid var(--border)', maxWidth: '100%', overflow: 'hidden' }}>
      <div style={{ ...mono, fontSize: '10px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', padding: '0 6px 6px', overflowWrap: 'anywhere' }}>
        {tree.title || 'This thread'}{line ? <span style={{ textTransform: 'none', letterSpacing: 0 }}>{'  ·  ' + line}</span> : null}
      </div>
      {tree.nodes.map((n) => <Row key={n.id} node={n} depth={0} open={open} toggle={toggle} shut={shut} fold={fold} cur={cur} title={tree.title} />)}
    </div>
  )
}
