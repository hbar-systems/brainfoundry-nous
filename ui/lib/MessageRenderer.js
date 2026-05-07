import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'

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
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', margin: '0.5em 0' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: '0.95em' }}>{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th style={{ borderBottom: '1px solid var(--border)', padding: '4px 10px', textAlign: 'left', fontWeight: 600 }}>{children}</th>
  ),
  td: ({ children }) => (
    <td style={{ borderBottom: '1px solid var(--border)', padding: '4px 10px', opacity: 0.92 }}>{children}</td>
  ),
  code: ({ className, children, ...props }) => {
    // react-markdown v10 removed the `inline` prop. Convention: fenced code
    // gets a `language-*` className from rehype-highlight; inline code does
    // not. Use that to branch.
    const isBlock = typeof className === 'string' && className.startsWith('language-')
    if (isBlock) {
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
  pre: ({ children }) => (
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
  ),
}

export default function MessageRenderer({ content }) {
  return (
    <div className="bf-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={components}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  )
}
