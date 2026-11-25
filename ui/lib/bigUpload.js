// bigUpload: attachments of any size to the box (VIDEO-DOOR-1, 2026-11-24).
// hbar: "GIVE ME A NORMAL PLACE I CAN DRAG AND DROP THE VIDEO INTO!" (a six-minute phone video).
// Files up to SMALL_MAX go in one multipart POST to /cc/upload as before. Bigger ones go in pieces
// through /cc/upload/big/* (scripts/cc/cc_extras.py BigUploads): start says how much the box already
// holds, each piece is sent at that offset, finish returns the path and sha256. A dropped connection
// is retried with a growing wait (and at once when the browser says it is online again); the same
// file dropped again later resumes where it stopped (the key is name, size and a hash of its first and last MB).
// Plain fetch with Blob slices: works in Safari on iPhone and in Firefox.

export const SMALL_MAX = 50 * 1024 * 1024
const GIVE_UP_MS = 15 * 60 * 1000          // no progress for this long: stop, say so; dropping it again resumes

export function fmtMB(n) {
  if (n >= 1024 * 1024 * 1024) return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
  return Math.round(n / (1024 * 1024)) + ' MB'
}

// "412 of 640 MB": the unit of the whole, so the two numbers read together
export function progressLine(done, total) {
  if (total >= 1024 * 1024 * 1024) return `${(done / (1024 * 1024 * 1024)).toFixed(2)} of ${(total / (1024 * 1024 * 1024)).toFixed(2)} GB`
  return `${Math.floor(done / (1024 * 1024))} of ${Math.max(1, Math.round(total / (1024 * 1024)))} MB`
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

function waitOnline(ms) {
  return new Promise(resolve => {
    let done = false
    const go = () => { if (done) return; done = true; window.removeEventListener('online', go); resolve() }
    window.addEventListener('online', go)
    setTimeout(go, ms)
  })
}

async function postJSON(url, body) {
  const r = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const d = await r.json().catch(() => ({ ok: false, error: 'http ' + r.status }))
  return { status: r.status, d }
}

// The resume key: a hash of the file's first and last MB (with name and size on the box's side). Not
// lastModified alone: a video picked from Photos on an iPhone gets a new one on every pick, so "drop it
// again" would start over. Without crypto.subtle (not https) it falls back to lastModified.
async function resumeKey(file) {
  try {
    if (!(window.crypto && crypto.subtle)) throw new Error('no subtle')
    const M = 1024 * 1024
    const head = await file.slice(0, Math.min(M, file.size)).arrayBuffer()
    const tail = await file.slice(Math.max(0, file.size - M)).arrayBuffer()
    const both = new Uint8Array(head.byteLength + tail.byteLength); both.set(new Uint8Array(head), 0); both.set(new Uint8Array(tail), head.byteLength)
    const h = new Uint8Array(await crypto.subtle.digest('SHA-256', both))
    return 'h:' + Array.from(h.slice(0, 16)).map(b => b.toString(16).padStart(2, '0')).join('')
  } catch { return 'm:' + String(file.lastModified || '') }
}

// One file over SMALL_MAX. onProgress(doneBytes, totalBytes). Resolves {ok, file} or {ok:false, error}.
export async function uploadBig(file, onProgress) {
  const key = await resumeKey(file)
  let start
  try { start = await postJSON('/cc/upload/big/start', { name: file.name, size: file.size, key }) }
  catch { return { ok: false, error: 'the bridge did not answer' } }
  if (!start.d.ok) return { ok: false, error: start.d.error || 'http ' + start.status }
  const id = start.d.id, chunk = start.d.chunk || 8 * 1024 * 1024
  let at = start.d.received || 0, wait = 1000, lastGain = Date.now()
  if (onProgress) onProgress(at, file.size)
  while (at < file.size) {
    let r = null, d = null
    try {
      r = await fetch(`/cc/upload/big/chunk?id=${encodeURIComponent(id)}&offset=${at}`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' },
        body: file.slice(at, Math.min(file.size, at + chunk)),
      })
      d = await r.json().catch(() => null)
    } catch { r = null }
    if (r && d && d.ok) { at = d.received; wait = 1000; lastGain = Date.now(); if (onProgress) onProgress(at, file.size); continue }
    if (r && d && r.status === 409 && typeof d.received === 'number') { at = d.received; if (onProgress) onProgress(at, file.size); continue }
    if (r && d && r.status >= 400 && r.status < 500 && r.status !== 408) return { ok: false, error: d.error || 'http ' + r.status }
    if (r && r.status === 507) return { ok: false, error: (d && d.error) || 'the box is full' }
    // the connection dropped or the proxy hiccupped: wait, ask the box where it stands, go on
    if (Date.now() - lastGain > GIVE_UP_MS) return { ok: false, error: `stopped at ${progressLine(at, file.size)}: no connection for 15 minutes. Drop the same file again and it carries on from there` }
    if (onProgress) onProgress(at, file.size, 'connection lost, retrying')
    await waitOnline(wait); wait = Math.min(wait * 2, 15000)
    try { const s = await postJSON('/cc/upload/big/status', { id }); if (s.d.ok) at = s.d.received } catch {}
  }
  let fin
  for (let i = 0; i < 6; i++) {
    try { fin = await postJSON('/cc/upload/big/finish', { id }); break } catch { await waitOnline(2000 * (i + 1)) }
  }
  if (!fin) return { ok: false, error: 'the bridge did not answer at the end; drop the file again to finish' }
  if (!fin.d.ok) return { ok: false, error: fin.d.error || 'http ' + fin.status }
  return { ok: true, file: fin.d.files[0] }
}

// Any mix of files: small ones together through /cc/upload, big ones one by one in pieces.
// onProgress(line) gets "412 of 640 MB" (with the file's name when there are several).
// Resolves {ok:true, files:[{name, path, size, sha256?}]} or {ok:false, error}.
export async function uploadFiles(files, onProgress) {
  const list = Array.from(files || [])
  const small = list.filter(f => f.size <= SMALL_MAX), big = list.filter(f => f.size > SMALL_MAX)
  const saved = []
  if (small.length) {
    const fd = new FormData(); small.forEach(f => fd.append('file', f, f.name))
    try {
      const r = await fetch('/cc/upload', { method: 'POST', credentials: 'same-origin', body: fd })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) return { ok: false, error: d.error || String(r.status) }
      saved.push(...(d.files || []))
    } catch { return { ok: false, error: 'the bridge did not answer' } }
  }
  for (const f of big) {
    const res = await uploadBig(f, (done, total, note) => {
      if (onProgress) onProgress((list.length > 1 ? f.name + ' ' : '') + progressLine(done, total) + (note ? ', ' + note : ''))
    })
    if (!res.ok) return { ok: false, error: res.error, files: saved }
    saved.push(res.file)
  }
  return { ok: true, files: saved }
}
