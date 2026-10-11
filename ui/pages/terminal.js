import Head from 'next/head'
import { useEffect, useState } from 'react'

// Terminal: the box's own shell, in the console. It frames the terminal door (/claude/,
// a web terminal served on this origin behind the same console password), so the owner
// never needs a laptop terminal for their server. Present only where the door is
// installed (CC enabled); the drawer entry comes from /apps/list. Added 2026-09-22.
export default function Terminal() {
  const [ok, setOk] = useState(null)   // null unknown, true door answers, false not installed
  useEffect(() => {
    fetch('/claude/', { method: 'HEAD', cache: 'no-store' }).then(r => setOk(r.ok)).catch(() => setOk(false))
  }, [])
  return (
    <>
      <Head><title>Terminal · BrainFoundry</title></Head>
      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - var(--nav-h, 52px))', minHeight: '480px', color: 'var(--text)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', padding: '10px 18px', borderBottom: '1px solid var(--border)' }}>
          <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--accent)' }}>Terminal · your server</span>
          <span style={{ fontSize: '13px', color: 'var(--text-dim)' }}>A shell on your box as its owner. Everything here is yours to break; the reasoner does not see this window.</span>
          <a href="/claude/" target="_blank" rel="noreferrer" style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--text-dim)', textDecoration: 'underline' }}>open in its own tab</a>
        </div>
        {ok === false ? (
          <p style={{ padding: '24px', fontSize: '14px', color: 'var(--text-dim)' }}>The terminal door is not installed on this brain. It comes with CC: `bash scripts/cc/install.sh` on the box, see docs/CC.md.</p>
        ) : (
          <iframe src="/claude/" title="Terminal" style={{ flex: 1, border: 0, width: '100%', backgroundColor: 'var(--bg)' }} />
        )}
      </div>
    </>
  )
}
