import { useRouter } from 'next/router'
import { useEffect, useRef, useState } from 'react'

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
// Bridge contract (v0):
//
//   Iframe -> host:
//     postMessage({ type: <intent>, payload: <object?>, request_id: <string> }, '*')
//
//   Host -> iframe:
//     postMessage({ type: 'reply', request_id: <string>,
//                   ok: <bool>, result?: <object>, error?: { code, message } },
//                 event.origin)
//
// Implemented intents (v0):
//   ping              -> result = 'pong'  (sanity)
//   meta.app_info     -> { id, name, version }
//   meta.brain_info   -> { name }         (reads NEXT_PUBLIC_BRAIN_NAME)
//
// Reserved-but-unimplemented intents (will land when first app needs them):
//   memory.read       -> { layer, query, limit? }
//   memory.write      -> { layer, content, metadata? }
//   federation.query  -> { peer, path, body? }
//   federation.send   -> { peer, message }
//
// Permission gating: the manifest's `permissions` list and `requires_layers`
// will be checked in handleIntent() against installed.json before any
// permission-gated intent executes. v0 ships with only the two `meta.*`
// intents which require no permission; the gate is wired but exercises
// nothing yet.
//
// Trust posture: same-origin sandbox in v0 ("trust your installed apps"),
// per registry/schema/brain/app.schema.json (in hbar.world) and ops/brain-
// apps-ownership.md. v1 hardening will move apps to a cross-origin subdomain
// where the sandbox is real.
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

  // postMessage bridge. Mounts once we have app info; tears down on unmount or app change.
  useEffect(() => {
    if (!appInfo) return

    function handleIntent(msg) {
      const { type } = msg
      // No-permission intents
      if (type === 'ping') {
        return Promise.resolve({ ok: true, result: 'pong' })
      }
      if (type === 'meta.app_info') {
        return Promise.resolve({
          ok: true,
          result: { id: appInfo.id, name: appInfo.name, version: appInfo.version },
        })
      }
      if (type === 'meta.brain_info') {
        return Promise.resolve({
          ok: true,
          result: { name: process.env.NEXT_PUBLIC_BRAIN_NAME || 'brain' },
        })
      }
      // Permission-gated intents land here in follow-on commits. The pattern:
      //   1. Look up appInfo.permissions + appInfo.requires_layers.
      //   2. Check the intent against them (e.g. memory.write requires
      //      'memory.write' permission AND a matching layer in
      //      requires_layers with mode 'write' or 'append').
      //   3. If allowed: call /api/bf/<brain-endpoint> with payload.
      //   4. Return { ok: true, result } or { ok: false, error }.
      return Promise.resolve({ ok: false, error: { code: 'unknown_intent', type } })
    }

    function onMessage(event) {
      // v0: same-origin only. The iframe at /api/bf/apps/<id>/ shares origin
      // with this page after the proxy hop.
      if (event.origin !== window.location.origin) return
      // Don't echo our own replies.
      if (event.source === window) return
      const msg = event.data
      if (!msg || typeof msg !== 'object' || !msg.request_id || !msg.type) return
      // Don't reply to replies.
      if (msg.type === 'reply') return

      handleIntent(msg).then(result => {
        if (!event.source) return
        try {
          event.source.postMessage(
            { type: 'reply', request_id: msg.request_id, ...result },
            event.origin,
          )
        } catch (_) { /* iframe gone */ }
      })
    }

    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [appInfo])

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

  if (!appInfo) {
    return (
      <div style={{ padding: '32px', color: 'var(--muted)', fontFamily: 'var(--font-body)', fontSize: '13px' }}>
        Loading…
      </div>
    )
  }

  return (
    <iframe
      ref={iframeRef}
      title={appInfo.name}
      src={`/api/bf/apps/${appInfo.id}/`}
      sandbox="allow-scripts allow-same-origin"
      style={{
        // Fill the viewport below the fixed nav (52px + safe-area inset).
        width: '100%',
        height: 'calc(100vh - 52px - env(safe-area-inset-top, 0px))',
        border: 'none',
        backgroundColor: 'var(--bg)',
        display: 'block',
      }}
    />
  )
}
