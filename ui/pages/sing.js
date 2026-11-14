import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// The sing page (SING-1 "Booth", 2026-11-14). hbar: "play a loop on the phone and sing over it, and the take lands
// as a clip on the grid."
// Pick a loop; press the ring: one bar of count-in clicks, then the loop plays round on the page's audio clock and
// the microphone records (MediaRecorder); press again to stop. Hear it back over the loop, nudge it by ear in ms,
// keep it or sing again.
// Timing: the recording runs through this page's AudioContext (mic -> MediaStreamDestination -> MediaRecorder), and
// 0.35 s after the recorder starts a 30 ms chirp (1.5 to 6 kHz) is mixed into the RECORDING ONLY (never the
// speakers) at a known clock time. Whoever reads the take finds the chirp and knows, to the sample, where bar 1 of
// the loop sits in it: bar1 = chirp_in_file + (loop_start - chirp_at) + latency - nudge. The page does that for the
// playback; the box does it again when it files the take.
// Latency: what the browser reports (outputLatency + baseLatency), or measured: "measure" plays three chirps out of
// the speaker and finds them in the microphone (speaker on, headphones off), round trip to the ms.
// Keep: the take and a sidecar JSON (hbar.sing.take/v1: loop, bpm, the clock times, latency, nudge) go up in one
// POST to the console's own /cc/upload (logged in, no new door) as in/<date>/sing_<stamp>_<loop>.<ext|json>; the
// box's sing_place.py moves the pair into in/<date>/sing/, trims it to whole bars and adds it as the next version
// on the loop's grid; this page then shows where it landed (the project's takes.tsv).
// The loops: a catalogue in the world (default ops/sing/loops.json, or ?loops=<path>), audio read through
// /cc/files/raw. Look: the chat's sand skin, one control per action, nothing moves on its own except the clock.

const CHIRP = { f0: 1500, f1: 6000, dur_s: 0.03, amp: 0.5 }
const LEAD = 0.35          // recorder start -> chirp, chirp -> first count-in click
const LS_LAT = 'cc.sing.latency'
const LS_NUDGE = 'cc.sing.nudge'
const LS_LOOP = 'cc.sing.loop'

const CSS = `
.sg{--bg:#efe3cf;--surface:#e6d6bd;--ink:#2b2116;--dim:#54473a;--muted:#7a6a55;--rust:#a8452b;--ease:cubic-bezier(.2,.7,.2,1);
  --top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));
  background:var(--bg);color:var(--ink);min-height:calc(100vh - var(--top));font:400 16px/1.5 system-ui,-apple-system,sans-serif;box-sizing:border-box}
.sg *{box-sizing:border-box}
.sg :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left;-webkit-tap-highlight-color:transparent}
.sg :where(a){color:inherit}
.sg :focus-visible{outline:2px solid var(--rust);outline-offset:3px;border-radius:8px}
.sg-wrap{max-width:1080px;margin:0 auto;padding:28px 32px 80px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;align-items:start}
.sg-h{font:400 30px/1.15 Lora,Georgia,serif;margin:0 0 4px}
.sg-sub{color:var(--muted);font-size:15px;margin:0 0 18px}
.sg-booth{position:sticky;top:calc(var(--top) + 16px);background:var(--surface);border-radius:18px;padding:22px 22px 20px;text-align:center}
.sg-loop{font:400 21px/1.25 Lora,Georgia,serif;overflow-wrap:anywhere}
.sg-meta{font-size:13px;color:var(--muted);letter-spacing:.04em;margin-top:2px}
.sg-ring{display:flex!important;align-items:center;justify-content:center;width:132px;height:132px;margin:22px auto 10px;border-radius:50%;background:var(--bg);color:var(--rust);text-align:center!important;transition:transform 160ms var(--ease),background-color 200ms var(--ease)}
.sg-ring:active{transform:scale(.97)}
.sg-ring svg{width:46px;height:46px}
.sg-ring.rec{background:var(--rust);color:var(--bg)}
.sg-ring[disabled]{opacity:.45;cursor:default}
.sg-clock{font:400 34px/1.1 Lora,Georgia,serif;font-variant-numeric:tabular-nums;min-height:40px}
.sg-clock small{font:400 14px/1 system-ui,sans-serif;color:var(--muted);margin-left:6px}
.sg-st{font-size:14px;color:var(--dim);min-height:21px;margin-top:4px}
.sg-st.err{color:var(--rust)}
.sg-row{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:14px}
.sg-b{padding:9px 18px;border-radius:999px;background:var(--bg);font-size:15px;color:var(--ink);transition:background-color 200ms var(--ease)}
.sg-b:hover{background:#f6ecdc}
.sg-b.main{background:var(--rust);color:var(--bg)}
.sg-b[disabled]{opacity:.45;cursor:default}
.sg-nudge{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:16px;font-size:14px;color:var(--dim)}
.sg-nudge .sg-b{padding:6px 12px;font-size:14px;font-variant-numeric:tabular-nums}
.sg-nudge span{min-width:104px;text-align:center;font-variant-numeric:tabular-nums}
.sg-lat{margin-top:10px;font-size:13px;color:var(--muted)}
.sg-lat button{color:var(--rust);text-decoration:underline;text-underline-offset:3px;font-size:13px}
.sg-done{margin-top:14px;font-size:14px;color:var(--dim);text-align:left;background:var(--bg);border-radius:12px;padding:10px 14px;overflow-wrap:anywhere}
.sg-done a{color:var(--rust)}
.sg-list{min-width:0}
.sg-t{border-radius:14px;transition:background-color 220ms var(--ease)}
.sg-t.open{background:var(--surface)}
.sg-tn{display:flex;align-items:baseline;gap:10px;width:100%;padding:9px 12px}
.sg-tn b{font:400 19px/1.25 Lora,Georgia,serif;flex:1;min-width:0;overflow-wrap:anywhere}
.sg-tn span{font-size:13px;color:var(--muted);white-space:nowrap}
.sg-parts{display:flex;flex-wrap:wrap;gap:6px;padding:0 10px 12px}
.sg-p{padding:6px 12px;border-radius:999px;background:var(--bg);font-size:14px;color:var(--dim)}
.sg-p.on{background:var(--rust);color:var(--bg)}
.sg-note{color:var(--muted);font-size:14px;margin:8px 12px}
@media(max-width:899px){
  .sg-wrap{display:block;padding:16px 12px 60px}
  .sg-booth{position:static;margin-bottom:18px;padding:18px 14px}
  .sg-ring{width:120px;height:120px;margin:16px auto 8px}
}
@media(prefers-reduced-motion:reduce){.sg-ring,.sg-t,.sg-b{transition:none!important}}
`

const raw = (p) => `/cc/files/raw?path=${encodeURIComponent(p)}`
const stampNow = () => new Date().toISOString().replace(/[-:]/g, '').replace(/\..*$/, '').replace('T', '-')
const fmtMs = (ms) => `${ms > 0 ? '+' : ''}${Math.round(ms)} ms`

// ---- signal helpers (pure)
function chirpSamples(rate, amp) {
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
// the chirp's place in x[from..to) (seconds) and how clearly: peak over the 99th percentile of |xcorr|
function findChirp(x, rate, from, to) {
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
function bufferOf(ctx, samples) { const b = ctx.createBuffer(1, samples.length, ctx.sampleRate); b.getChannelData(0).set(samples); return b }
function clickBuffer(ctx, accent) {
  const n = Math.round(0.03 * ctx.sampleRate), d = new Float32Array(n), f = accent ? 1760 : 1320
  for (let i = 0; i < n; i++) d[i] = 0.5 * Math.sin((2 * Math.PI * f * i) / ctx.sampleRate) * Math.exp(-i / (0.006 * ctx.sampleRate))
  return bufferOf(ctx, d)
}
function play(ctx, buf, at, dest) { const s = ctx.createBufferSource(); s.buffer = buf; s.connect(dest || ctx.destination); s.start(at); return s }
const pickMime = () => ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(x => { try { return MediaRecorder.isTypeSupported(x) } catch { return false } })

const Svg = ({ k }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    {k === 'stop' ? <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" /> : <><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" /></>}
  </svg>
)

export default function Sing() {
  const [cat, setCat] = useState(null)          // the catalogue, false when it did not load
  const [open, setOpen] = useState(null)        // track unfolded in the list
  const [loop, setLoop] = useState(null)        // the chosen loop entry
  const [phase, setPhase] = useState('idle')    // idle | loading | count | rec | review | sending | kept
  const [clock, setClock] = useState('')
  const [msg, setMsg] = useState({ text: '', err: false })
  const [nudge, setNudge] = useState(0)
  const [lat, setLat] = useState(null)          // { ms, source }
  const [kept, setKept] = useState(null)        // { files, placed }
  const A = useRef({})                          // the audio state: ctx, buffers, stream, recorder, times

  useEffect(() => {
    let path = 'ops/sing/loops.json'
    try { path = new URLSearchParams(window.location.search).get('loops') || path } catch {}
    fetch(raw(path)).then(r => (r.ok ? r.json() : Promise.reject(r.status))).then(d => {
      setCat({ ...d, path })
      let first = null
      try { first = new URLSearchParams(window.location.search).get('loop') || localStorage.getItem(LS_LOOP) } catch {}
      const l = (d.loops || []).find(x => x.id === first)
      if (l) { setLoop(l); setOpen(l.track) }
    }).catch(() => setCat(false))
    try { const v = JSON.parse(localStorage.getItem(LS_LAT) || 'null'); if (v && typeof v.ms === 'number') setLat(v) } catch {}
    try { const n = parseInt(localStorage.getItem(LS_NUDGE) || '0', 10); if (!Number.isNaN(n)) setNudge(n) } catch {}
    return () => teardown()
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const say = (text, err = false) => setMsg({ text, err })

  function teardown() {
    const a = A.current
    try { if (a.raf) cancelAnimationFrame(a.raf) } catch {}
    try { (a.sources || []).forEach(s => s.stop()) } catch {}
    try { if (a.recorder && a.recorder.state !== 'inactive') a.recorder.stop() } catch {}
    try { if (a.stream) a.stream.getTracks().forEach(t => t.stop()) } catch {}
    a.stream = null
  }

  async function ctxReady() {
    const a = A.current
    if (!a.ctx) {
      const C = window.AudioContext || window.webkitAudioContext
      a.ctx = new C({ latencyHint: 'interactive' })
    }
    if (a.ctx.state !== 'running') await a.ctx.resume()
    return a.ctx
  }
  async function loopBuffer(l) {
    const a = A.current
    if (a.loopId === l.id && a.loopBuf) return a.loopBuf
    const ctx = await ctxReady()
    const r = await fetch(raw(l.audio))
    if (!r.ok) throw new Error(`the loop's audio did not load (${r.status})`)
    const buf = await ctx.decodeAudioData(await r.arrayBuffer())
    const partS = l.samples / l.rate
    const extra = buf.duration - partS
    a.loopOff = extra > 0.0005 && extra >= 1105 / l.rate ? 1105 / l.rate : 0     // an MP3 decoder that kept LAME's delay
    a.loopBuf = buf; a.loopId = l.id; a.loopLen = (l.bars * 240) / l.bpm
    return buf
  }
  async function mic() {
    const a = A.current
    if (a.stream && a.stream.active) return a.stream
    a.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } })
    return a.stream
  }
  function reported(ctx) { return Math.round(1000 * ((ctx.outputLatency || 0) + (ctx.baseLatency || 0))) }
  function usedLatency(ctx) { return lat ? { ms: lat.ms, source: lat.source } : { ms: reported(ctx), source: 'browser-reported output (input unknown: nudge by ear)' } }

  // recorder through the context; resolves with { recorder, startCtx } once it has started
  function startRecorder(ctx, stream) {
    const a = A.current
    const src = ctx.createMediaStreamSource(stream)
    const dest = ctx.createMediaStreamDestination()
    src.connect(dest)
    const mime = pickMime()
    const recorder = mime ? new MediaRecorder(dest.stream, { mimeType: mime }) : new MediaRecorder(dest.stream)
    const chunks = []
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data) }
    return new Promise((resolve, reject) => {
      recorder.onstart = () => resolve({ recorder, dest, src, chunks, startCtx: ctx.currentTime, mime: recorder.mimeType || mime || 'audio/webm' })
      recorder.onerror = () => reject(new Error('the recorder stopped with an error'))
      try { recorder.start(250) } catch (e) { reject(e) }
      a.recorder = recorder
    })
  }
  const stopped = (r) => new Promise(res => { r.recorder.onstop = () => res(new Blob(r.chunks, { type: r.mime })); try { r.recorder.stop() } catch { res(new Blob(r.chunks, { type: r.mime })) } })

  async function record() {
    if (!loop) return
    setKept(null); say('')
    setPhase('loading')
    let ctx, buf, stream
    try {
      if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)) throw new Error('this browser cannot record')
      ctx = await ctxReady()
      buf = await loopBuffer(loop)
      try { stream = await mic() } catch { throw new Error('the microphone is not allowed for this page') }
    } catch (e) { setPhase('idle'); say(e.message || String(e), true); return }
    const a = A.current
    const r = await startRecorder(ctx, stream).catch(e => { say(e.message, true); return null })
    if (!r) { setPhase('idle'); return }
    const bar = (240 / loop.bpm), beat = bar / 4
    const M = r.startCtx + LEAD, C0 = M + LEAD, L = C0 + bar
    const grid = (cat && cat.grid_bars) || 32
    a.sources = [play(ctx, bufferOf(ctx, chirpSamples(ctx.sampleRate, CHIRP.amp)), M, r.dest)]   // into the take only
    for (let k = 0; k < 4; k++) a.sources.push(play(ctx, clickBuffer(ctx, k === 0), C0 + k * beat))
    const s = ctx.createBufferSource()
    s.buffer = buf; s.loop = true; s.loopStart = a.loopOff; s.loopEnd = a.loopOff + a.loopLen
    s.connect(ctx.destination); s.start(L, a.loopOff)
    a.sources.push(s)
    a.take = { rec: r, M, C0, L, bar, grid, latency: usedLatency(ctx), rate: ctx.sampleRate, out: ctx.outputLatency || 0 }
    setPhase('count')
    const tick = () => {
      const t = ctx.currentTime - L - (a.take.out || 0)
      if (t < 0) { setClock(`${Math.min(4, Math.max(1, 4 - Math.floor(-t / beat)))}`); } else {
        const b = Math.floor(t / bar), bt = Math.floor((t - b * bar) / beat)
        setClock(`${b + 1}.${bt + 1}`)
        if (phaseRef.current === 'count') setPhase('rec')
        if (b >= grid) { stop(); return }
      }
      a.raf = requestAnimationFrame(tick)
    }
    a.raf = requestAnimationFrame(tick)
  }
  const phaseRef = useRef(phase)
  useEffect(() => { phaseRef.current = phase }, [phase])

  async function stop() {
    const a = A.current, tk = a.take
    if (!tk || a.stopping) return
    a.stopping = true
    try { if (a.raf) cancelAnimationFrame(a.raf) } catch {}
    const ctx = a.ctx
    tk.stopCtx = ctx.currentTime
    try { (a.sources || []).forEach(x => x.stop()) } catch {}
    const blob = await stopped(tk.rec)
    try { tk.rec.src.disconnect() } catch {}
    a.stopping = false
    tk.blob = blob
    setClock('')
    if (!blob.size) { setPhase('idle'); say('nothing was recorded', true); return }
    // where bar 1 sits in the take, from the chirp (the box measures it again)
    try {
      const vb = await ctx.decodeAudioData(await blob.arrayBuffer())
      tk.voice = vb
      const f = findChirp(vb.getChannelData(0), vb.sampleRate, 0, Math.min(vb.duration, 3))
      tk.marker = f && f.t != null ? f.t : null
      tk.clarity = f ? f.clarity : 0
    } catch { tk.voice = null; tk.marker = null }
    tk.bar1Base = tk.marker != null ? tk.marker + (tk.L - tk.M) : tk.L - tk.rec.startCtx
    const bars = Math.floor((tk.stopCtx - tk.L) / tk.bar)
    setPhase('review')
    say(`${Math.max(0, bars)} bars${tk.marker != null ? '; bar 1 found by the marker' : '; marker not found, bar 1 from the recorder start'}. Hear it, nudge if it sits early or late, then keep.`)
  }

  function bar1(tk) { return tk.bar1Base + tk.latency.ms / 1000 - nudge / 1000 }

  async function hear() {
    const a = A.current, tk = a.take
    if (!tk || !tk.voice) { say('this browser could not decode the take to play it back; keep it and listen on the grid', true); return }
    const ctx = await ctxReady()
    try { (a.sources || []).forEach(x => x.stop()) } catch {}
    const from = Math.max(0, bar1(tk) - tk.bar)           // from the count-in bar
    const t = ctx.currentTime + 0.15
    const v = ctx.createBufferSource(); v.buffer = tk.voice; v.connect(ctx.destination); v.start(t, from)
    const s = ctx.createBufferSource()
    s.buffer = a.loopBuf; s.loop = true; s.loopStart = a.loopOff; s.loopEnd = a.loopOff + a.loopLen
    s.connect(ctx.destination); s.start(t + (bar1(tk) - from), a.loopOff); s.stop(t + (tk.voice.duration - from))
    a.sources = [v, s]
  }

  function setN(n) { setNudge(n); try { localStorage.setItem(LS_NUDGE, String(n)) } catch {} }

  async function keep() {
    const a = A.current, tk = a.take
    if (!tk || !tk.blob) return
    try { (a.sources || []).forEach(x => x.stop()) } catch {}
    setPhase('sending')
    const ext = /mp4/.test(tk.blob.type) ? 'm4a' : /ogg/.test(tk.blob.type) ? 'ogg' : 'webm'
    const name = `sing_${stampNow()}_${loop.slug}`
    const side = {
      dialect: 'hbar.sing.take/v1', file: `${name}.${ext}`, made: new Date().toISOString(),
      loop: { id: loop.id, track: loop.track, part: loop.part, key: loop.key, bars: loop.bars, bpm: loop.bpm, audio: loop.audio, layer: loop.layer },
      grid_bars: tk.grid,
      recorded: { mime: tk.blob.type, ctx_rate: tk.rate, rec_start_ctx: tk.rec.startCtx, marker: { at_ctx: tk.M, ...CHIRP },
                  count_in: { at_ctx: tk.C0, bars: 1 }, loop_start_ctx: tk.L, stop_ctx: tk.stopCtx, loop_offset_s: a.loopOff },
      latency: { used_ms: tk.latency.ms, source: tk.latency.source, reported_output_ms: Math.round(1000 * (tk.out || 0)) },
      nudge_ms: nudge,
      page: { marker_in_take_s: tk.marker, marker_clarity: tk.clarity, bar1_in_take_s: bar1(tk) },
    }
    const fd = new FormData()
    fd.append('file', tk.blob, side.file)
    fd.append('sidecar', new Blob([JSON.stringify(side, null, 1)], { type: 'application/json' }), `${name}.json`)
    try {
      const r = await fetch('/cc/upload', { method: 'POST', body: fd })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || `the console answered ${r.status}`)
      setKept({ files: d.files || [], name: side.file, placed: null })
      setPhase('kept')
      say('kept. The box puts it on the loop\'s grid as the next version, usually within two minutes.')
      watchPlaced(side.file)
    } catch (e) { setPhase('review'); say(e.message || 'the console did not answer', true) }
  }

  // the project's takes.tsv, read until this take's line shows (3 min at most)
  function watchPlaced(file) {
    if (!cat || !cat.projects) return
    const url = raw(`${cat.projects}/${loop.slug}/takes.tsv`)
    const until = Date.now() + 180000
    const look = async () => {
      try {
        const r = await fetch(url)
        if (r.ok) {
          const line = (await r.text()).split('\n').find(l => l.split('\t')[2] === file)
          if (line) { const c = line.split('\t'); setKept(k => (k ? { ...k, placed: { version: c[1], where: c[3], verdict: c[10] } } : k)); return }
        }
      } catch {}
      if (Date.now() < until && document.visibilityState !== 'hidden') setTimeout(look, 5000)
    }
    setTimeout(look, 4000)
  }

  async function measure() {
    say('measuring: speaker on, headphones off, stay quiet for three seconds')
    let ctx, stream
    try { ctx = await ctxReady(); stream = await mic() } catch { say('the microphone is not allowed for this page', true); return }
    const r = await startRecorder(ctx, stream).catch(() => null)
    if (!r) { say('could not start recording', true); return }
    const M = r.startCtx + LEAD
    const P = [M + 0.6, M + 1.2, M + 1.8]
    play(ctx, bufferOf(ctx, chirpSamples(ctx.sampleRate, CHIRP.amp)), M, r.dest)
    P.forEach(t => play(ctx, bufferOf(ctx, chirpSamples(ctx.sampleRate, 0.9)), t))
    await new Promise(res => setTimeout(res, 1000 * (P[2] - ctx.currentTime + 0.7)))
    const blob = await stopped(r)
    try { r.src.disconnect() } catch {}
    try {
      const vb = await ctx.decodeAudioData(await blob.arrayBuffer())
      const x = vb.getChannelData(0)
      const m = findChirp(x, vb.sampleRate, 0, 0.6 + LEAD)
      if (!m || m.t == null) throw new Error('marker')
      const rt = P.map(t => { const want = m.t + (t - M); const f = findChirp(x, vb.sampleRate, want - 0.01, want + 0.5); return f && f.t != null ? f.t - want : null }).filter(v => v != null)
      if (rt.length < 2) throw new Error('speaker')
      rt.sort((p, q) => p - q)
      const ms = Math.round(1000 * rt[Math.floor(rt.length / 2)])
      if (rt[rt.length - 1] - rt[0] > 0.006) throw new Error('spread')
      const v = { ms, source: `measured round trip (speaker to microphone), ${new Date().toISOString().slice(0, 10)}` }
      setLat(v); try { localStorage.setItem(LS_LAT, JSON.stringify(v)) } catch {}
      say(`latency measured: ${ms} ms round trip. With headphones it differs; nudge by ear.`)
    } catch (e) {
      say(e.message === 'marker' ? 'could not read the measurement back; the browser\'s figure stays' : 'the microphone did not hear the speaker clearly; the browser\'s figure stays, nudge by ear', true)
    }
  }

  function choose(l) {
    if (phase === 'count' || phase === 'rec' || phase === 'sending') return
    setLoop(l); setKept(null); setPhase('idle'); say('')
    A.current.take = null
    try { localStorage.setItem(LS_LOOP, l.id) } catch {}
  }

  const tracks = []
  if (cat && cat.loops) {
    const by = {}
    cat.loops.forEach(l => { if (!by[l.track]) { by[l.track] = []; tracks.push(l.track) } by[l.track].push(l) })
    tracks.splice(0, tracks.length, ...tracks.map(t => ({ name: t, parts: by[t] })))
  }
  const busy = phase === 'count' || phase === 'rec'
  const ctxNow = A.current.ctx
  const latLine = lat ? `latency ${lat.ms} ms, measured` : ctxNow ? `latency ${reported(ctxNow)} ms, as the browser reports it` : 'latency: the browser\'s figure, read on the first press'
  const projectPage = cat && cat.projects && loop ? `/files?path=${encodeURIComponent(`${cat.projects}/${loop.slug}/index.html`)}` : null

  return (
    <>
      <Head><title>Sing</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="sg">
        <div className="sg-wrap">
          <section className="sg-booth" aria-label="booth">
            <div className="sg-loop">{loop ? `${loop.track.replace(/_/g, ' ')}` : 'Pick a loop'}</div>
            <div className="sg-meta">{loop ? `${loop.label} · ${loop.bars} bars · ${loop.key} · ${loop.bpm} BPM` : 'then press the ring and sing'}</div>
            <button type="button" className={'sg-ring' + (busy ? ' rec' : '')} disabled={!loop || phase === 'loading' || phase === 'sending'}
              onClick={busy ? stop : record} aria-label={busy ? 'stop' : 'record'}>
              <Svg k={busy ? 'stop' : 'mic'} />
            </button>
            <div className="sg-clock" aria-live="off">{phase === 'count' ? <>{clock}<small>count-in</small></> : phase === 'rec' ? <>{clock}<small>bar.beat</small></> : ' '}</div>
            <div className={'sg-st' + (msg.err ? ' err' : '')} role="status">{phase === 'loading' ? 'loading the loop' : msg.text}</div>
            {phase === 'review' || phase === 'kept' || phase === 'sending' ? (
              <>
                <div className="sg-row">
                  <button type="button" className="sg-b" onClick={hear} disabled={phase === 'sending'}>hear it</button>
                  {phase === 'review' ? <button type="button" className="sg-b main" onClick={keep}>keep</button> : null}
                  <button type="button" className="sg-b" onClick={() => { A.current.take = null; setKept(null); setPhase('idle'); say('') }} disabled={phase === 'sending'}>again</button>
                </div>
                {phase === 'review' ? (
                  <div className="sg-nudge">
                    <button type="button" className="sg-b" onClick={() => setN(nudge - 10)} aria-label="earlier by 10 ms">-10</button>
                    <span>nudge {fmtMs(nudge)}</span>
                    <button type="button" className="sg-b" onClick={() => setN(nudge + 10)} aria-label="later by 10 ms">+10</button>
                  </div>
                ) : null}
              </>
            ) : null}
            {kept ? (
              <div className="sg-done">
                {kept.placed ? <>On the grid: {kept.placed.version}, {kept.placed.where}. {kept.placed.verdict}. </> : <>Saved as {kept.files.map(f => f.name).join(' and ')}. </>}
                {projectPage ? <a href={projectPage}>the grid page</a> : null}
              </div>
            ) : null}
            <div className="sg-lat">{latLine} · <button type="button" onClick={measure} disabled={busy}>measure</button></div>
          </section>
          <main className="sg-list" aria-label="loops">
            <h1 className="sg-h">Sing</h1>
            <p className="sg-sub">A loop, one bar of clicks, your voice. Stop when you are done.</p>
            {cat === false ? <p className="sg-note">The loop list did not load. It is a file in the world (ops/sing/loops.json); the box writes it with sing_place.py catalog.</p> : null}
            {cat === null ? <p className="sg-note">loading the loops</p> : null}
            {tracks.map(t => (
              <div key={t.name} className={'sg-t' + (open === t.name ? ' open' : '')}>
                <button type="button" className="sg-tn" onClick={() => setOpen(o => (o === t.name ? null : t.name))} aria-expanded={open === t.name}>
                  <b>{t.name.replace(/_/g, ' ')}</b><span>{t.parts.length} {t.parts.length === 1 ? 'part' : 'parts'} · {t.parts[0].key}</span>
                </button>
                {open === t.name ? (
                  <div className="sg-parts">
                    {t.parts.map(l => (
                      <button type="button" key={l.id} className={'sg-p' + (loop && loop.id === l.id ? ' on' : '')} onClick={() => choose(l)}>
                        {l.label} · {l.bars}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </main>
        </div>
      </div>
    </>
  )
}
