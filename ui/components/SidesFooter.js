// The quiet line at the foot of every console page (INLINE-1, 2026-11-23): "2 answers ready", press to
// jump to the first one. It also tells the box the owner is looking (POST /cc/sides/seen while the page is
// in front), so a Telegram line goes out only after five minutes away. Mounted once in pages/_app.js.
import { useEffect, useState } from 'react'
import { footerLine, jumpHref } from '../lib/sides'

export default function SidesFooter() {
  const [d, setD] = useState({ ready: 0, items: [] })
  useEffect(() => {
    let stop = false
    const load = () => fetch('/cc/sides/count', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
      .then(x => { if (!stop && x) setD({ ready: x.ready || 0, items: x.items || [] }) }).catch(() => {})
    const seen = () => { if (document.visibilityState === 'visible') fetch('/cc/sides/seen', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {}) }
    load(); seen()
    const a = setInterval(load, 20000), b = setInterval(seen, 60000)
    document.addEventListener('visibilitychange', seen)
    return () => { stop = true; clearInterval(a); clearInterval(b); document.removeEventListener('visibilitychange', seen) }
  }, [])
  const line = footerLine(d.ready)
  if (!line) return null
  const first = d.items[0]
  const href = jumpHref(first)
  return (
    <a data-sides-footer="1" href={href || undefined} title={first ? 'opens: ' + (first.title || first.key) : ''}
      style={{ position: 'fixed', left: '12px', bottom: '10px', zIndex: 60, fontFamily: 'var(--font-mono, monospace)', fontSize: '12px',
        color: 'var(--accent)', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '14px', padding: '4px 12px',
        textDecoration: 'none', cursor: href ? 'pointer' : 'default' }}>
      ● {line}
    </a>
  )
}
