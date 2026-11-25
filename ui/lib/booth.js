// The booth's pure helpers (SING-FREE-1, 2026-11-24): the WAV a take is kept as, the level meter's numbers, the
// timer, and the marker that lets the box find bar 1 when a take was sung over a track or a loop.
// No browser objects here, so node runs them in tests/test_sing_booth.py.

// ---- the take as a WAV: PCM 24-bit, little endian, interleaved; samples clipped to [-1, 1]
export function encodeWav(channels, rate, bits = 24) {
  const ch = channels.length
  const n = ch ? channels[0].length : 0
  const bps = bits / 8
  const dataLen = n * ch * bps
  const buf = new ArrayBuffer(44 + dataLen)
  const v = new DataView(buf)
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); v.setUint32(4, 36 + dataLen, true); str(8, 'WAVE')
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, ch, true)
  v.setUint32(24, rate, true); v.setUint32(28, rate * ch * bps, true); v.setUint16(32, ch * bps, true); v.setUint16(34, bits, true)
  str(36, 'data'); v.setUint32(40, dataLen, true)
  let o = 44
  const max = bits === 24 ? 8388607 : 32767
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      let s = channels[c][i]
      s = s > 1 ? 1 : s < -1 ? -1 : (s || 0)
      const q = Math.round(s * max)
      if (bits === 24) { v.setUint8(o, q & 255); v.setUint8(o + 1, (q >> 8) & 255); v.setUint8(o + 2, (q >> 16) & 255); o += 3 } else { v.setInt16(o, q, true); o += 2 }
    }
  }
  return new Uint8Array(buf)
}

// chunks of Float32Array per channel -> one Float32Array per channel
export function joinChunks(chunks, ch) {
  const out = []
  for (let c = 0; c < ch; c++) {
    const len = chunks.reduce((a, k) => a + k[c].length, 0)
    const x = new Float32Array(len)
    let o = 0
    for (const k of chunks) { x.set(k[c], o); o += k[c].length }
    out.push(x)
  }
  return out
}

// ---- the meter: peak and RMS of a block in dBFS, and where that sits on a -60..0 dB scale
export function levels(x) {
  let pk = 0, sq = 0
  for (let i = 0; i < x.length; i++) { const a = Math.abs(x[i]); if (a > pk) pk = a; sq += x[i] * x[i] }
  const rms = x.length ? Math.sqrt(sq / x.length) : 0
  const db = (a) => (a > 1e-6 ? 20 * Math.log10(a) : -120)
  return { peakDb: db(pk), rmsDb: db(rms) }
}
export const meterPos = (db, floor = -60) => (db <= floor ? 0 : db >= 0 ? 1 : 1 - db / floor)
// what the meter says under itself: nothing, quiet, good, hot (over -3 dBFS peaks), clipped (at 0)
export function levelWord(peakDb, heldPeakDb) {
  if (heldPeakDb >= -0.1) return 'clip'
  if (peakDb > -3) return 'hot'
  if (peakDb < -45) return 'quiet'
  return 'good'
}

// ---- the timer: m:ss, and h:mm:ss past an hour
export function clock(sec) {
  const s = Math.max(0, Math.floor(sec || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`
}

// ---- names: what the box will call it (cc_booth.slug keeps the last word); shown under the field
export const nameHint = (s) => String(s || '').trim().replace(/\s+/g, ' ').slice(0, 120)

// ---- the marker (the same chirp the loop page has used since SING-1): a 30 ms sweep 1.5 to 6 kHz under a Hann
// window, mixed into the recording only, never the headphones. Found again by cross-correlation.
export const CHIRP = { f0: 1500, f1: 6000, dur_s: 0.03, amp: 0.5 }
export function chirpSamples(rate, amp) {
  const n = Math.round(CHIRP.dur_s * rate)
  const out = new Float32Array(n)
  const k = (CHIRP.f1 - CHIRP.f0) / CHIRP.dur_s
  for (let i = 0; i < n; i++) {
    const t = i / rate
    const w = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1))
    out[i] = amp * Math.sin(2 * Math.PI * (CHIRP.f0 * t + 0.5 * k * t * t)) * w
  }
  return out
}
function fft(re, im, inv) {     // in place, radix 2, length a power of two
  const n = re.length
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const a = ((inv ? 2 : -2) * Math.PI) / len, wr = Math.cos(a), wi = Math.sin(a)
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0
      for (let j = 0; j < len / 2; j++) {
        const ur = re[i + j], ui = im[i + j]
        const vr = re[i + j + len / 2] * cr - im[i + j + len / 2] * ci
        const vi = re[i + j + len / 2] * ci + im[i + j + len / 2] * cr
        re[i + j] = ur + vr; im[i + j] = ui + vi; re[i + j + len / 2] = ur - vr; im[i + j + len / 2] = ui - vi
        const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr
      }
    }
  }
}
// the marker's place in x[from..to) (seconds) and how clearly: peak over the 99th percentile of |xcorr|
export function findChirp(x, rate, from, to) {
  const tpl = chirpSamples(rate, 1)
  const a = Math.max(0, Math.floor(from * rate)), b = Math.min(x.length, Math.floor(to * rate))
  const m = b - a
  if (m < tpl.length * 2) return null
  let n = 1; while (n < m + tpl.length) n <<= 1
  const xr = new Float64Array(n), xi = new Float64Array(n), tr = new Float64Array(n), ti = new Float64Array(n)
  for (let i = 0; i < m; i++) xr[i] = x[a + i]
  for (let i = 0; i < tpl.length; i++) tr[i] = tpl[i]
  fft(xr, xi, false); fft(tr, ti, false)
  for (let i = 0; i < n; i++) { const r = xr[i] * tr[i] + xi[i] * ti[i]; const im = xi[i] * tr[i] - xr[i] * ti[i]; xr[i] = r; xi[i] = im }
  fft(xr, xi, true)
  const L = m - tpl.length, mag = new Float64Array(L)
  let best = 0, at = 0
  for (let i = 0; i < L; i++) { const v = Math.abs(xr[i]); mag[i] = v; if (v > best) { best = v; at = i } }
  const sorted = Array.from(mag).sort((p, q) => p - q)
  const ref = sorted[Math.floor(0.99 * (L - 1))] || 1e-12
  const clarity = best / ref
  return clarity >= 3 ? { t: (a + at) / rate, clarity } : { t: null, clarity }
}
