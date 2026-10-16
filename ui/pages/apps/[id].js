import { useRouter } from 'next/router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { makeBridge, acceptMessage, seedName } from '../../lib/appBridge'
import { APP_SANDBOX } from '../../lib/appLane'

// Iframe host shell for installed brain apps.
//
// Routing:
//   /apps/<id>          (this page)            — Next.js dynamic route, host shell.
//   /api/bf/apps/<id>/  (brain api StaticFiles) — the iframe content. Proxied
//                                                 through ui/pages/api/bf/[...path].js.
//
// The host fetches /api/bf/apps/list to look up the app by id, then renders an
// iframe pointing at the brain api's mounted bundle. Apps publish manifest +
// pre-built dist/; brain api serves static files; this page wraps with the
// postMessage bridge.
//
// The bridge (contract, intents, permission gates) lives in ui/lib/appBridge.js.
//
// Trust posture (2026-10-16): the app is NOT trusted with the console's authority. The iframe is
// sandboxed WITHOUT allow-same-origin, and every app file is served with a sandbox CSP
// (ui/lib/appLane.js), so the app runs in an opaque origin: it cannot read this page, its storage
// or cookies, and the /api/bf proxy refuses its requests (it holds the owner key). The postMessage
// bridge below is the only way an app acts. The app's localStorage is a shim kept by this page per
// app id, seeded through the iframe's name attribute and saved through storage.* intents.
//
// Created: 2026-05-08

export default function AppHost() {
  const router = useRouter()
  const { id } = router.query

  const [appInfo, setAppInfo] = useState(null)
  const [error, setError] = useState(null)
  const iframeRef = useRef(null)

  // Look up the app by id once we have it from the router.
  useEffect(() => {
    if (!id || typeof id !== 'string') return
    let cancelled = false
    fetch('/api/bf/apps/list')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        if (cancelled) return
        const app = (data.apps || []).find(a => a.id === id)
        if (!app) { setError({ code: 'not_installed', id }); return }
        if (app.enabled === false) { setError({ code: 'disabled', id }); return }
        setAppInfo(app)
      })
      .catch(e => { if (!cancelled) setError({ code: 'fetch_failed', detail: String(e) }) })
    return () => { cancelled = true }
  }, [id])

  // The bridge and the app's saved storage, built once per app. The seed goes into the iframe's
  // name attribute before the frame loads; the shim inside reads it and clears it.
  const lane = useMemo(() => {
    if (!appInfo || typeof window === 'undefined') return null
    let ls = null
    try { ls = window.localStorage } catch (_) { ls = null }
    const bridge = makeBridge({
      appInfo,
      fetch: (...a) => window.fetch(...a),
      ls,
      brainName: process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain',
    })
    return { bridge, seed: seedName(bridge.store) }
  }, [appInfo])

  // postMessage bridge. Mounts once we have app info; tears down on unmount or app change.
  useEffect(() => {
    if (!lane) return

    function onMessage(event) {
      // The frame's origin is opaque ("null"), so the check is on the sender's window: only the
      // app's own frame is answered. Replies go to that window with '*' (an opaque origin cannot
      // be named as a target); nothing else receives them.
      const frame = iframeRef.current && iframeRef.current.contentWindow
      if (!acceptMessage(event, frame)) return
      const msg = event.data
      lane.bridge.handleIntent(msg).then(result => {
        try {
          event.source.postMessage({ type: 'reply', request_id: msg.request_id, ...result }, '*')
        } catch (_) { /* iframe gone */ }
      })
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [lane])

  if (error) {
    return (
      <div style={{ padding: '32px', color: 'var(--text)', fontFamily: 'var(--font-body)' }}>
        <div style={{ fontSize: '15px', marginBottom: '8px' }}>App not loadable.</div>
        <div style={{ fontSize: '13px', color: 'var(--muted)' }}>
          {error.code === 'not_installed' && <>No app with id <code>{error.id}</code> is installed.</>}
          {error.code === 'disabled' && <>App <code>{error.id}</code> is installed but disabled.</>}
          {error.code === 'fetch_failed' && <>Could not reach the brain api: {error.detail}</>}
        </div>
      </div>
    )
  }

  if (!appInfo || !lane) {
    return (
      <div style={{ padding: '32px', color: 'var(--muted)', fontFamily: 'var(--font-body)', fontSize: '13px' }}>
        Loading…
      </div>
    )
  }

  return (
    // The wrapper is fixed to the viewport below the nav and clips any
    // overflow. Without this, the brain UI's outer page (with its own
    // theme bg) shows through below the iframe whenever the brain is in
    // a different theme than the app inside — visible as a colored stripe
    // when scrolled. Fixed-position wrapper guarantees the iframe owns
    // the entire below-nav area edge-to-edge.
    <div
      style={{
        position: 'fixed',
        top: 'calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px))',
        left: 0,
        right: 0,
        bottom: 0,
        overflow: 'hidden',
        backgroundColor: 'var(--bg)',
      }}
    >
      <iframe
        ref={iframeRef}
        title={appInfo.name}
        // Point at index.html explicitly. The directory-form URL
        // (/api/bf/apps/<id>/) gets 308'd by Next.js to the no-slash form,
        // which breaks relative URLs like ./styles.css inside the iframe
        // (they'd resolve to /api/bf/apps/styles.css — wrong directory).
        // Pointing at /index.html keeps the iframe document.location
        // anchored in the app's directory so relative URLs resolve right.
        src={`/api/bf/apps/${appInfo.id}/index.html`}
        // No allow-same-origin (2026-10-16): the app gets an opaque origin and only the bridge.
        // The same list is sent as the files' CSP sandbox (ui/lib/appLane.js APP_SANDBOX).
        sandbox={APP_SANDBOX}
        name={lane.seed}
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          backgroundColor: 'var(--bg)',
          display: 'block',
        }}
      />
    </div>
  )
}
