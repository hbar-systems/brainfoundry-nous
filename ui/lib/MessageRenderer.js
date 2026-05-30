import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import DiagramBlock from './DiagramBlock'

// Walk a React children tree to collect plain text. Used to pull the
// raw source out of a fenced code block after rehype-highlight has wrapped
// each token in span elements.
const extractText = (node) => {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (typeof node === 'object' && node.props) return extractText(node.props.children)
  return ''
}

const components = {
  p: ({ children }) => (
    <p style={{ margin: '0 0 0.7em 0', lineHeight: 1.6 }}>{children}</p>
  ),
  h1: ({ children }) => (
    <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '1.35em', fontWeight: 600, margin: '0.6em 0 0.4em 0' }}>{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.2em', fontWeight: 600, margin: '0.6em 0 0.35em 0' }}>{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '1.08em', fontWeight: 600, margin: '0.5em 0 0.3em 0' }}>{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 style={{ fontSize: '1em', fontWeight: 600, margin: '0.5em 0 0.25em 0' }}>{children}</h4>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '0.3em 0 0.7em 0', paddingLeft: '1.3em' }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '0.3em 0 0.7em 0', paddingLeft: '1.3em' }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ margin: '0.15em 0', lineHeight: 1.55 }}>{children}</li>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', textDecoration: 'underline', textUnderlineOffset: '2px' }}>{children}</a>
  ),
  strong: ({ children }) => (
    <strong style={{ fontWeight: 600 }}>{children}</strong>
  ),
  em: ({ children }) => (
    <em style={{ fontStyle: 'italic' }}>{children}</em>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{ borderLeft: '3px solid var(--accent)', margin: '0.5em 0', padding: '0.1em 0 0.1em 0.9em', opacity: 0.85 }}>{children}</blockquote>
  ),
  hr: () => (
    <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '0.9em 0' }} />
  ),
  // The message bubble sets word-break: break-word; without table-layout +
  // column widths that lets the browser squeeze a column to ~1 char and wrap
  // a header letter-per-line. tableLayout:auto + th nowrap + a td minWidth
  // keep columns intact; the wrapper scrolls horizontally on overflow.
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', maxWidth: '100%', margin: '0.5em 0' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: '0.95em', tableLayout: 'auto', width: 'auto' }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ borderBottom: '1px solid var(--border)', padding: '5px 12px', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ borderBottom: '1px solid var(--border)', padding: '5px 12px', opacity: 0.92, minWidth: '72px', wordBreak: 'normal' }}>{children}</td>
  ),
  code: ({ node, className, children, ...props }) => {
    // react-markdown v10 removed the `inline` prop. We branch by className:
    // fenced code carries `language-*`; inline code has no className.
    // rehype-highlight may add `hljs` and other tokens, so we match against
    // any whitespace-separated class, not just the prefix of the string.
    const cls = typeof className === 'string' ? className : ''
    const langMatch = cls.match(/(?:^|\s)language-([\w+-]+)/)
    if (langMatch) {
      const lang = langMatch[1]
      if (lang === 'mermaid' || lang === 'svg') {
        // DiagramBlock wants raw source. After rehype-highlight runs, the
        // hast children become highlighted <span>s; walk children to collect
        // text. Falls back to node.children[0].value when un-highlighted
        // (rehype-highlight skips unknown languages like mermaid/svg).
        const raw = extractText(children) || node?.children?.[0]?.value || ''
        return <DiagramBlock kind={lang} source={raw.replace(/\n$/, '')} />
      }
      return <code className={className} {...props}>{children}</code>
    }
    return (
      <code style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '0.9em',
        padding: '1px 5px',
        borderRadius: '4px',
        background: 'rgba(0,0,0,0.18)',
      }} {...props}>{children}</code>
    )
  },
  pre: ({ children }) => {
    // react-markdown v10 may pass children as a single element or an array
    // (text whitespace + element). Find the meaningful child and inspect
    // its props. Our code component returns <DiagramBlock kind={lang} ...>
    // for mermaid/svg fences — skip the <pre> wrapper for those because
    // DiagramBlock has its own outer styling. For everything else, wrap.
    const arr = Array.isArray(children) ? children : [children]
    const elt = arr.find(c => c && typeof c === 'object' && c.type !== undefined)
    const kind = elt?.props?.kind
    if (kind === 'mermaid' || kind === 'svg') return elt
    return (
      <pre style={{
        background: 'var(--code-bg)',
        color: 'var(--code-fg)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '12px 14px',
        margin: '0.5em 0',
        overflowX: 'auto',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.88em',
        lineHeight: 1.5,
      }}>{children}</pre>
    )
  },
}

export default function MessageRenderer({ content }) {
  return (
    <div className="bf-md">
      <ReactMarkdown
        // singleDollarTextMath: false — a lone `$` is NOT math. Without this,
        // prose dollar amounts ("$50 billion … $225 billion", common in web
        // results, pricing, finance) get parsed as inline LaTeX and rendered
        // as a stack of single characters. Display math `$$…$$` still works.
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: false }]]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={components}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  )
}
