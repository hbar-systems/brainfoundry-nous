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
// Added 2026-10-22 for the base shelf (toolbox, clip, today, people, weekly-review). Each is gated
// by one manifest permission; the host calls the brain with the owner key, the iframe sees only the
// result. External content (pages, mail, calendar) comes back marked trust: 'untrusted'.
//   meta.theme        -> { tokens: { '--bg': ..., ... }, theme, font }  (no permission). The host
//                        also posts { type: 'bf.theme', tokens, ... } to the frame when the skin changes.
//   ui.open           -> { route }  opens a console screen (/files, /tasks, /chat, /cc, /graph,
//                        /upload, /apps/<id>, with an optional ?query). No permission; no other URL.
//   memory.search     -> { query, limit? (<=20) }  permission 'memory.read'; searches only the
//                        read-mode layers in requires_layers, open view only (never local-only).
//                        result -> { results: [{ content, document_name, similarity, metadata }] }
//   tasks.list        -> { include_done? }  permission 'tasks.read'. result -> { tasks: [...] }
//   tasks.add         -> { text, due? }     permission 'tasks.write'. result -> { task }
//   tasks.complete    -> { id, done? }      permission 'tasks.write'. result -> { ok }
//   calendar.upcoming -> { max_results? }   permission 'calendar.read'. result -> { source, events, trust }
//   email.recent      -> { query?, max_results?, unread_only? }  permission 'email.read'.
//                        result -> { source, messages, trust }
//   web.fetch         -> { url }  permission 'network.outbound'; the brain's guarded fetch_url
//                        (http/https, no private addresses). result -> { url, title, text, trust }
//   files.save        -> { name, text } or { name, base64, mime? }  permission 'files.write'; lands
//                        in the owner's Files desk (out/<date>/), through the CC bridge.
//                        result -> { path, route }; error 'no_files_door' on a brain without CC.
//   audio.transcribe  -> { base64, mime?, name? }  permission 'audio.transcribe'; the CC bridge's
//                        speech door. result -> { text }; error 'no_speech_door' when it is not set up.
//
// Reserved-but-unimplemented intents (will land when first app needs them):
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

// Console screens an app may open (ui.open). Anything else is refused.
const OPEN_ROUTE_RE = /^\/(files|tasks|chat|cc|graph|upload|apps\/[a-z0-9][a-z0-9-]{1,62}[a-z0-9])(\?[^#\s]{0,1000})?$/

function b64ToBlob(b64, mime) {
  const bin = atob(String(b64))
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type: mime || 'application/octet-stream' })
}

function makeBridge({ appInfo, fetch, ls, brainName, theme, navigate }) {
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

    // ---- the base-shelf intents (2026-10-22) ----
    const perms = appInfo.permissions || []
    const denied = (p) => Promise.resolve({ ok: false, error: { code: 'permission_denied', detail: `app did not declare ${p}` } })
    // One call to the brain (or the CC bridge) with the owner's authority; the reply carries only `pick(body)`.
    const call = (url, init, code, pick) => fetch(url, init)
      .then(r => r.json().catch(() => ({})).then(body => ({ status: r.status, ok: r.ok, body })))
      .then(({ status, ok, body }) => ok
        ? { ok: true, result: pick(body) }
        : { ok: false, error: { code, status, detail: (body && (body.detail || body.error)) || `HTTP ${status}` } })
      .catch(e => ({ ok: false, error: { code: code + '_network_error', detail: String(e) } }))
    const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const clampInt = (v, lo, hi, d) => (Number.isInteger(v) ? Math.max(lo, Math.min(hi, v)) : d)

    if (type === 'meta.theme') {
      const t = typeof theme === 'function' ? theme() : null
      return Promise.resolve({ ok: true, result: t || { tokens: {} } })
    }
    if (type === 'ui.open') {
      const route = String(payload.route || '')
      if (!OPEN_ROUTE_RE.test(route)) return Promise.resolve({ ok: false, error: { code: 'route_not_allowed', detail: route } })
      if (typeof navigate !== 'function') return Promise.resolve({ ok: false, error: { code: 'no_navigation' } })
      navigate(route)
      return Promise.resolve({ ok: true, result: { route } })
    }
    if (type === 'memory.search') {
      if (!perms.includes('memory.read')) return denied('memory.read')
      const query = String(payload.query || '').trim()
      if (!query) return Promise.resolve({ ok: false, error: { code: 'missing_query' } })
      const layers = [...new Set((appInfo.requires_layers || []).filter(l => l.mode === 'read').map(l => l.layer))]
      if (!layers.length) return Promise.resolve({ ok: false, error: { code: 'layer_not_declared', detail: 'app declared no read layer' } })
      // Fixed fields only: an app cannot ask for include_local_only.
      return call('/api/bf/documents/search', json('POST', { query, limit: clampInt(payload.limit, 1, 20, 8), layers }),
        'memory_search_failed', b => ({
          results: (b.results || []).map(x => ({
            content: x.content, document_name: x.document_name, similarity: x.similarity, metadata: x.metadata || {},
          })),
        }))
    }
    if (type === 'tasks.list') {
      if (!perms.includes('tasks.read')) return denied('tasks.read')
      return call(`/api/bf/tasks${payload.include_done ? '?include_done=true' : ''}`, { method: 'GET' },
        'tasks_failed', b => ({ tasks: b.tasks || [] }))
    }
    if (type === 'tasks.add') {
      if (!perms.includes('tasks.write')) return denied('tasks.write')
      const text = String(payload.text || '').trim()
      if (!text) return Promise.resolve({ ok: false, error: { code: 'missing_text' } })
      return call('/api/bf/tasks', json('POST', { text, due: payload.due || null, source: `app:${appInfo.id}` }),
        'tasks_failed', b => ({ task: b.task }))
    }
    if (type === 'tasks.complete') {
      if (!perms.includes('tasks.write')) return denied('tasks.write')
      const id = String(payload.id || '')
      if (!/^[A-Za-z0-9_-]{1,80}$/.test(id)) return Promise.resolve({ ok: false, error: { code: 'bad_id' } })
      return call(`/api/bf/tasks/${id}/complete?done=${payload.done === false ? 'false' : 'true'}`, { method: 'POST' },
        'tasks_failed', b => ({ ok: !!b.ok }))
    }
    if (type === 'calendar.upcoming') {
      if (!perms.includes('calendar.read')) return denied('calendar.read')
      return call(`/api/bf/integrations/calendar/events?max_results=${clampInt(payload.max_results, 1, 50, 15)}`, { method: 'GET' },
        'calendar_failed', b => ({ source: b.source || null, events: b.events || [], trust: 'untrusted' }))
    }
    if (type === 'email.recent') {
      if (!perms.includes('email.read')) return denied('email.read')
      const q = new URLSearchParams({ max_results: String(clampInt(payload.max_results, 1, 50, 15)) })
      if (payload.query) q.set('query', String(payload.query).slice(0, 200))
      if (payload.unread_only) q.set('unread_only', 'true')
      return call(`/api/bf/integrations/email/messages?${q}`, { method: 'GET' },
        'email_failed', b => ({ source: b.source || null, messages: b.messages || [], trust: 'untrusted' }))
    }
    if (type === 'web.fetch') {
      if (!perms.includes('network.outbound')) return denied('network.outbound')
      const url = String(payload.url || '').trim()
      if (!/^https?:\/\//i.test(url)) return Promise.resolve({ ok: false, error: { code: 'bad_url' } })
      return call('/api/bf/tools/fetch-url', json('POST', { url }),
        'fetch_failed', b => ({ url: b.url, title: b.title || '', text: b.text || '', trust: 'untrusted' }))
    }
    if (type === 'files.save') {
      if (!perms.includes('files.write')) return denied('files.write')
      const name = String(payload.name || '').trim()
      if (!name) return Promise.resolve({ ok: false, error: { code: 'missing_name' } })
      const body = { name, app: appInfo.id }
      if (typeof payload.base64 === 'string') { body.base64 = payload.base64; body.mime = String(payload.mime || '') }
      else body.text = String(payload.text == null ? '' : payload.text)
      return fetch('/cc/files/save', json('POST', body))
        .then(r => r.json().catch(() => ({})).then(b => ({ status: r.status, ok: r.ok, b })))
        .then(({ status, ok, b }) => {
          if (status === 404 || status === 502) return { ok: false, error: { code: 'no_files_door', detail: 'this brain has no Files desk (CC is not installed)' } }
          if (!ok || !b.ok) return { ok: false, error: { code: 'files_save_failed', status, detail: b.error || `HTTP ${status}` } }
          return { ok: true, result: { path: b.path, route: `/files?path=${encodeURIComponent(b.path)}` } }
        })
        .catch(e => ({ ok: false, error: { code: 'no_files_door', detail: String(e) } }))
    }
    if (type === 'audio.transcribe') {
      if (!perms.includes('audio.transcribe')) return denied('audio.transcribe')
      if (typeof payload.base64 !== 'string' || !payload.base64) return Promise.resolve({ ok: false, error: { code: 'missing_audio' } })
      let fd
      try {
        fd = new FormData()
        fd.append('file', b64ToBlob(payload.base64, payload.mime), String(payload.name || 'audio.webm'))
      } catch (e) { return Promise.resolve({ ok: false, error: { code: 'bad_audio', detail: String(e) } }) }
      return fetch('/cc/transcribe', { method: 'POST', body: fd })
        .then(r => r.json().catch(() => ({})).then(b => ({ status: r.status, ok: r.ok, b })))
        .then(({ status, ok, b }) => {
          if (status === 404 || status === 409) return { ok: false, error: { code: 'no_speech_door', detail: b.error || 'transcription is not set up on this brain' } }
          if (!ok || !b.ok) return { ok: false, error: { code: 'transcribe_failed', status, detail: b.error || `HTTP ${status}` } }
          return { ok: true, result: { text: b.text || '' } }
        })
        .catch(e => ({ ok: false, error: { code: 'transcribe_network_error', detail: String(e) } }))
    }

    return Promise.resolve({ ok: false, error: { code: 'unknown_intent', type } })
  }

  return { handleIntent, store }
}

module.exports = { makeBridge, OPEN_ROUTE_RE, acceptMessage, seedName, loadStore, legacyStore, LEGACY_KEYS, STORAGE_PREFIX, STORAGE_MAX_CHARS }
