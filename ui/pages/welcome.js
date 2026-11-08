import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/router'
import { WELCOME_VERSION, landing } from '../lib/welcome'

// Welcome: the six-scene film a new owner sees the first time the console opens
// (ui/public/onboarding/index.html, one self-contained file). Shown once per
// person: "/" sends a fresh brain here while the server's welcome_seen_version is
// below WELCOME_VERSION; "Talk to it" stores the version and goes to the thread (the console's
// talk view, /talk; Chat only on a brain without CC), or to Knowledge when a folder was dropped on scene 3 (the film only counts it, so the
// real upload, propose then approve, happens there). /welcome?replay=1 (Guide)
// plays it again without touching the flag. Added 2026-10-23.
// 2026-11-08 (NOUS-M): members landed on /chat, the old page of many chats, after the film; the thread
// is where a person starts (and its doors, when the layout's view is "doors").

export default function Welcome() {
  const router = useRouter()
  const frame = useRef(null)
  const dropped = useRef(0)
  const home = useRef('/talk')
  const [src, setSrc] = useState(null)

  useEffect(() => {
    if (!router.isReady) return
    const replay = router.query.replay === '1'
    const json = u => fetch(u).then(r => (r.ok ? r.json() : null)).catch(() => null)
    Promise.all([json('/api/bf/onboarding/welcome'), json('/api/bf/apps/list')])
      .then(([d, apps]) => {
        home.current = landing(apps)
        const q = new URLSearchParams({ start: home.current })
        if (d && d.name) q.set('name', d.name)
        setSrc('/onboarding/index.html?' + q.toString())
      })

    const onMessage = e => {
      if (e.origin !== window.location.origin) return
      if (!frame.current || e.source !== frame.current.contentWindow) return
      const m = e.data || {}
      if (m.type === 'onboarding:drop') dropped.current = Number(m.count) || 1
      if (m.type === 'onboarding:done') {
        const go = () => router.replace(dropped.current ? '/upload' : home.current)
        if (replay) { setTimeout(go, 1500); return }
        fetch('/api/bf/onboarding/welcome/seen', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version: Number(m.version) || WELCOME_VERSION }),
        }).catch(() => {}).finally(() => setTimeout(go, 1500))
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [router.isReady])

  return (
    <>
      <Head><title>Welcome</title></Head>
      <div style={{ position: 'fixed', inset: 0, zIndex: 10000, background: '#050505' }}>
        {src && (
          <iframe
            ref={frame}
            src={src}
            title="Welcome"
            allow="fullscreen"
            style={{ width: '100%', height: '100%', border: 0, display: 'block' }}
            onLoad={() => { try { frame.current.contentWindow.focus() } catch {} }}
          />
        )}
      </div>
    </>
  )
}
