// The brain-app bridge (moved out of ui/pages/apps/[id].js on 2026-10-16 so tests can run it under
// node; tests/test_app_lane.py). The host page calls makeBridge() once per app and answers every
// postMessage from the app's frame with handleIntent(). The bridge is the only way an app acts:
// since 2026-10-16 the app runs in an opaque origin (ui/lib/appLane.js) and cannot call /api/bf.
//
// Bridge contract (v0):
//
//   Iframe -> host:
//     postMessage({ type: <intent>, payload: <object?>, request_id: <string> }, '*')
//
//   Host -> iframe:
//     postMessage({ type: 'reply', request_id: <string>,
//                   ok: <bool>, result?: <object>, error?: { code, message } }, '*')
//     ('*' because the frame's origin is opaque; the host posts only to the frame's own window.)
//
// Implemented intents (v0):
//   ping              -> result = 'pong'  (sanity)
//   meta.app_info     -> { id, name, version }
//   meta.brain_info   -> { name }         (reads NEXT_PUBLIC_BRAIN_NAME)
//   memory.write      -> { layer, content, source?, metadata?, privacy? }
//                        gated by manifest permissions + requires_layers;
//                        proxies to brain POST /memory/append. `privacy` is
//                        "open" (default) or "local-only" (2026-10-15): no
//                        extra permission to declare, since a stricter level
//                        only narrows who reads the write; the brain keeps the
//                        stricter of this, any level already stored for the
//                        same content, and a vault source. Reply carries it.
//                        The reply never carries memory content.
//   llm.complete      -> { messages: [{role, content}, ...], max_tokens? }
//                        gated by manifest permission 'llm.invoke'. Generates
//                        a completion over the brain's own corpus using the
//                        brain's selected (BYOK) model. RAG retrieval is
//                        scoped to the read-mode layers in requires_layers.
//                        The host mints + holds the loop permit (agent
//                        "app:<id>"); the iframe never sees it. The brain gives
//                        an app:<id> permit the open view only: no local-only
//                        memory reaches the reply or its sources, whatever the
//                        model (api/main.py /chat/rag). The body is built here
//                        from fixed fields; an app cannot pass session_id,
//                        include_local_only or anything else through.
//                        result -> { text, model, sources: [...] }
//   storage.set / storage.remove / storage.clear
//                     -> the app's own localStorage, kept by the host page per
//                        app id (2026-10-16). Sent by the shim (ui/lib/appLane.js);
//                        no permission, the app reaches only its own store.
//
// Reserved-but-unimplemented intents (will land when first app needs them):
//   memory.read       -> { layer, query, limit? }   (must use the open view)
//   federation.query  -> { peer, path, body? }
//   federation.send   -> { peer, message }

const STORAGE_PREFIX = 'bf.app-storage.'
const STORAGE_MAX_CHARS = 2000000

// Keys the default-shelf apps wrote into the console's own localStorage while they shared its origin
// (before 2026-10-16). Copied once into the app's own store on first load; the originals stay.
const LEGACY_KEYS = {
  daybook: (k) => k.startsWith('daybook:'),
  'hbar-ink': (k) => k.startsWith('hbar-ink-'),
  'quantum-room': (k) => k === 'qr-progress',
}

function legacyStore(appId, ls) {
  const match = LEGACY_KEYS[appId]
  const out = {}
  if (!match || !ls) return out
  for (let i = 0; i < ls.length; i++) {
    const k = ls.key(i)
    if (k && match(k)) out[k] = ls.getItem(k)
  }
  return out
}

// The app's store, read from the console's localStorage (or the legacy keys on first load).
function loadStore(appId, ls) {
  if (!ls) return {}
  const raw = ls.getItem(STORAGE_PREFIX + appId)
  if (raw == null) {
    const seeded = legacyStore(appId, ls)
    try { ls.setItem(STORAGE_PREFIX + appId, JSON.stringify(seeded)) } catch (_) { /* quota */ }
    return seeded
  }
  try {
    const v = JSON.parse(raw)
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  } catch (_) { return {} }
}

// What the host writes into the iframe's name attribute; the shim reads it before app code runs.
function seedName(store) {
  return 'bf-app-storage:' + JSON.stringify(store || {})
}

// Accept a message only from the app's own frame window, shaped as a request.
function acceptMessage(event, frameWindow) {
  if (!event || !frameWindow || event.source !== frameWindow) return false
  const msg = event.data
  if (!msg || typeof msg !== 'object' || !msg.request_id || !msg.type) return false
  if (msg.type === 'reply') return false
  return true
}

function makeBridge({ appInfo, fetch, ls, brainName }) {
  const store = loadStore(appInfo.id, ls)
  function saveStore() {
    const s = JSON.stringify(store)
    if (s.length > STORAGE_MAX_CHARS) return false
    try { if (ls) ls.setItem(STORAGE_PREFIX + appInfo.id, s) } catch (_) { return false }
    return true
  }

  function handleIntent(msg) {
    const { type } = msg
    const payload = (msg.payload && typeof msg.payload === 'object') ? msg.payload : {}
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
      return Promise.resolve({ ok: true, result: { name: brainName || 'brain' } })
    }
    // The app's own storage (the shim's localStorage). Only this app's store is reachable.
    if (type === 'storage.set' || type === 'storage.remove' || type === 'storage.clear') {
      const prev = JSON.stringify(store)
      if (type === 'storage.set') {
        if (typeof payload.key !== 'string') return Promise.resolve({ ok: false, error: { code: 'missing_key' } })
        store[payload.key] = String(payload.value)
      } else if (type === 'storage.remove') {
        delete store[String(payload.key)]
      } else {
        for (const k of Object.keys(store)) delete store[k]
      }
      if (!saveStore()) {
        const back = JSON.parse(prev)
        for (const k of Object.keys(store)) delete store[k]
        Object.assign(store, back)
        return Promise.resolve({ ok: false, error: { code: 'storage_full', detail: `an app keeps at most ${STORAGE_MAX_CHARS} characters` } })
      }
      return Promise.resolve({ ok: true, result: { saved: true } })
    }
    // memory.write — append a chunk into the brain's memory layer. Requires
    // permissions: ['memory.write'] AND a matching layer in requires_layers
    // with mode 'write' or 'append'.
    if (type === 'memory.write') {
      const perms = appInfo.permissions || []
      if (!perms.includes('memory.write')) {
        return Promise.resolve({ ok: false, error: { code: 'permission_denied', detail: 'app did not declare memory.write' } })
      }
      const layer = payload.layer
      if (!layer) {
        return Promise.resolve({ ok: false, error: { code: 'missing_layer' } })
      }
      const layerOk = (appInfo.requires_layers || []).some(l =>
        l.layer === layer && (l.mode === 'write' || l.mode === 'append')
      )
      if (!layerOk) {
        return Promise.resolve({ ok: false, error: { code: 'layer_not_declared', detail: `app did not declare ${layer}:write/append` } })
      }
      return fetch('/api/bf/memory/append', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          layer,
          content: payload.content,
          source: payload.source || appInfo.id,
          metadata: payload.metadata || {},
          ...(payload.privacy ? { privacy: String(payload.privacy) } : {}),
        }),
      })
        .then(r => r.json().then(body => ({ status: r.status, ok: r.ok, body })))
        .then(({ status, ok, body }) => {
          if (!ok) {
            return { ok: false, error: { code: 'memory_append_failed', status, body } }
          }
          return { ok: true, result: { id: body.id, doc_name: body.doc_name, privacy: body.privacy } }
        })
        .catch(e => ({ ok: false, error: { code: 'memory_append_network_error', detail: String(e) } }))
    }

    // llm.complete — a completion over the brain's own corpus, the brain's
    // selected (BYOK) model. Requires permission 'llm.invoke'. The host mints
    // a loop permit attributed to this app and proxies it to /chat/rag; the
    // iframe only ever holds the generated text. Retrieval is scoped to the
    // read-mode layers the operator approved at install (requires_layers).
    if (type === 'llm.complete') {
      const perms = appInfo.permissions || []
      if (!perms.includes('llm.invoke')) {
        return Promise.resolve({ ok: false, error: { code: 'permission_denied', detail: 'app did not declare llm.invoke' } })
      }
      const messages = payload.messages
      if (!Array.isArray(messages) || messages.length === 0) {
        return Promise.resolve({ ok: false, error: { code: 'missing_messages', detail: 'payload.messages must be a non-empty array of {role, content}' } })
      }
      const layers = (appInfo.requires_layers || [])
        .filter(l => l.mode === 'read')
        .map(l => l.layer)
      return Promise.all([
        fetch('/api/bf/settings/model')
          .then(r => r.ok ? r.json() : Promise.reject(`settings/model ${r.status}`)),
        fetch('/api/permit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent_id: `app:${appInfo.id}`,
            reason: `brain-app ${appInfo.id} llm.complete`,
          }),
        }).then(r => r.json()),
      ])
        .then(([modelInfo, permit]) => {
          if (!permit || !permit.permit_id || !permit.permit_token) {
            return { ok: false, error: { code: 'permit_failed', detail: (permit && (permit.detail || permit.error)) || 'NodeOS did not issue a permit' } }
          }
          const body = {
            model: modelInfo && modelInfo.active,
            messages,
            permit_id: permit.permit_id,
            permit_token: permit.permit_token,
          }
          // Let an app raise its output ceiling (server clamps to [256, 65536]).
          const mt = payload.max_tokens
          if (Number.isInteger(mt) && mt > 0) body.max_tokens = mt
          if (layers.length) body.layers = layers
          return fetch('/api/bf/chat/rag', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
            .then(r => r.json().then(b => ({ status: r.status, ok: r.ok, body: b })))
            .then(({ status, ok, body }) => {
              if (!ok) {
                return { ok: false, error: { code: 'llm_complete_failed', status, body } }
              }
              const text = body.choices && body.choices[0] && body.choices[0].message && body.choices[0].message.content
              return {
                ok: true,
                result: {
                  text: text || '',
                  model: body.model,
                  sources: (body.rag_metadata && body.rag_metadata.sources) || [],
                },
              }
            })
        })
        .catch(e => ({ ok: false, error: { code: 'llm_complete_network_error', detail: String(e) } }))
    }

    return Promise.resolve({ ok: false, error: { code: 'unknown_intent', type } })
  }

  return { handleIntent, store }
}

module.exports = { makeBridge, acceptMessage, seedName, loadStore, legacyStore, LEGACY_KEYS, STORAGE_PREFIX, STORAGE_MAX_CHARS }
