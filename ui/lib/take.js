// /take's pure helpers (DEMO-1, 2026-11-25): the embed clock against the take's, the sync step the demo player runs,
// the step strip's counts. No browser objects, so node runs them in tests/test_take_lib.py.

// least-squares line through [x, y] pairs -> { rate, at0, maxResMs } (y = rate * x + at0)
export function fitLine(pairs) {
  const p = (pairs || []).filter(q => Array.isArray(q) && q.length === 2 && isFinite(q[0]) && isFinite(q[1]))
  if (p.length < 2) return null
  const n = p.length
  let sx = 0, sy = 0, sxx = 0, sxy = 0
  for (const [x, y] of p) { sx += x; sy += y; sxx += x * x; sxy += x * y }
  const den = n * sxx - sx * sx
  if (Math.abs(den) < 1e-12) return null
  const rate = (n * sxy - sx * sy) / den
  const at0 = (sy - rate * sx) / n
  let mx = 0
  for (const [x, y] of p) mx = Math.max(mx, Math.abs(y - (rate * x + at0)))
  return { rate, at0, maxResMs: Math.round(mx * 10000) / 10 }
}

// The pairs the page sampled while recording over an embed: [ctx time, video time]. The take's own clock: a ctx
// time c sits in the take at marker + (c - M) + latency (the booth's rule for a track, SING-FREE-1).
export function pairsInTake(raw, marker, M, latencyS) {
  if (marker == null) return []
  return (raw || []).map(([c, v]) => [Math.round((marker + (c - M) + latencyS) * 10000) / 10000, Math.round(v * 10000) / 10000])
}

// One step of the demo player's sync: where the voice should be for this video time, how far off it is, and what to
// do about it. Small drift is pulled in with the playback rate (inaudible within 3 %), a big one is a seek.
export function syncStep(videoT, audioT, map) {
  const rate = map && map.rate ? map.rate : 1
  const v0 = map && map.video_at_voice_0 != null ? map.video_at_voice_0 : 0
  const target = (videoT - v0) / rate
  const drift = audioT - target
  const a = Math.abs(drift)
  if (target < 0) return { target, drift, action: 'wait', rate: 1 }
  if (a > 0.12) return { target, drift, action: 'seek', rate: 1 }
  if (a > 0.02) return { target, drift, action: 'nudge', rate: Math.max(0.97, Math.min(1.03, 1 - drift * 0.5)) }
  return { target, drift, action: 'hold', rate: 1 }
}

// drift samples [ms] -> { n, meanAbs, p95, max } in ms
export function driftStats(ms) {
  const a = (ms || []).filter(x => isFinite(x)).map(x => Math.abs(x)).sort((x, y) => x - y)
  if (!a.length) return { n: 0, meanAbs: 0, p95: 0, max: 0 }
  const r = (x) => Math.round(x * 10) / 10
  return { n: a.length, meanAbs: r(a.reduce((s, x) => s + x, 0) / a.length), p95: r(a[Math.min(a.length - 1, Math.floor(0.95 * a.length))]), max: r(a[a.length - 1]) }
}

// the strip: how many takes stand at each step
export function stripCounts(takes) {
  const c = { record: 0, demo: 0, ask: 0, done: 0, making: 0, ready: 0, toAsk: 0 }
  for (const t of takes || []) {
    const s = (t && t.step) || {}
    if (s.at && c[s.at] != null) c[s.at] += 1
    if (s.state === 'making') c.making += 1
    if (s.state === 'ready') c.ready += 1
    if (s.state === 'to-ask' || s.state === 'drafted') c.toAsk += 1
  }
  return c
}

export const hasOffer = (body) => !String(body || '').includes('[your offer')
