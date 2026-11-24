import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'
import { CHIRP, chirpSamples, clock, encodeWav, findChirp, joinChunks, levelWord, levels, meterPos } from '../lib/booth'

// The booth (SING-FREE-1, 2026-11-24). hbar, on the loop page: "I don't want a loop. I just wanted to sing." and
// "WHATS WITH THIS SAME STANDARDIZED DESIGN YOU KEEP GIVING ME FOR EACH OF THESE TOOLS".
// One control: press, sing, press again. The microphone is recorded as plain PCM (no echo cancelling, no noise
// suppression, no auto gain) and kept as a 24-bit WAV through /cc/booth/take (scripts/cc/cc_booth.py): one
// folder per day under the studio folder, the bytes as recorded, never rewritten. Name it afterwards (typed or
// said); play it back; send it to the phone (the bridge's /cc/send-file, Telegram).
// Optional, never required: sing over one of his tracks (drop any audio file on the page, or pick one: it plays in
// the headphones, only the microphone is recorded) or over a loop (the loop list, folded away). Over a track or a
// loop a 30 ms marker is mixed into the recording only (never the headphones), 0.35 s in, so the box finds where
// the track or bar 1 sits in the take to the sample; a loop take also goes to /cc/upload with the hbar.sing.take/v1
// sidecar, so the rooms (rooms.py watch) place it on the grid as before.
// The old loop page is kept as it was at /sing/v1 (ui/pages/sing/v1.js): count-in, nudge, latency measure.
// Look: its own room, not the house card: a dark booth, one lit ring that breathes with the voice, a big clock,
// a live meter, an ON AIR light. The console's font and accent are used; the room itself is the booth's.

const LEAD = 0.35                 // capture start -> marker, marker -> track or count-in
const MAX_S = 30 * 60             // a take stops by itself after 30 minutes
const LS_LAT = 'cc.sing.latency'  // the latency the loop page measured, when it did
const HEADPHONES = 'Wired headphones on: only your voice is recorded'

const CSS = `
.bo{--room:#0d0907;--wall:#16100c;--ink:#f1e6d8;--dim:#b3a291;--faint:#7d6d5e;--glow:var(--accent,#e0a35a);--air:#ff3b2f;
  --ease:cubic-bezier(.2,.7,.2,1);--top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));--lv:0;--pk:0;--hold:0;
  position:relative;min-height:calc(100vh - var(--top));color:var(--ink);font:400 16px/1.5 var(--font-body,system-ui,sans-serif);
  background:
    radial-gradient(ellipse 70% 55% at 50% 0%, rgba(255,190,120,.13), transparent 70%),
    repeating-conic-gradient(from 45deg at 50% 50%, rgba(255,255,255,.018) 0 25%, rgba(0,0,0,.05) 0 50%) 0 0/28px 28px,
    linear-gradient(var(--wall), var(--room) 60%);
  box-sizing:border-box;overflow-x:hidden}
.bo *{box-sizing:border-box}
.bo :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;-webkit-tap-highlight-color:transparent}
.bo :focus-visible{outline:2px solid var(--glow);outline-offset:4px;border-radius:10px}
.bo-in{max-width:760px;margin:0 auto;padding:22px 20px 90px;display:flex;flex-direction:column;align-items:center}
.bo-top{width:100%;display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.bo-name{font:400 22px/1 var(--font-display,Lora,Georgia,serif);letter-spacing:.02em;color:var(--dim)}
.bo-air{font:600 12px/1 var(--font-mono,ui-monospace,monospace);letter-spacing:.24em;padding:8px 12px 7px;border-radius:6px;
  border:1px solid rgba(255,59,47,.25);color:rgba(255,120,100,.35);transition:all 240ms var(--ease)}
.bo.rec .bo-air{background:var(--air);color:#fff;border-color:var(--air);box-shadow:0 0 18px rgba(255,59,47,.7),0 0 60px rgba(255,59,47,.35)}
.bo-stage{position:relative;width:clamp(210px,46vmin,320px);aspect-ratio:1;margin:clamp(18px,5vh,46px) 0 8px;display:grid;place-items:center}
.bo-halo{position:absolute;inset:-18%;border-radius:50%;pointer-events:none;
  background:radial-gradient(circle, color-mix(in srgb,var(--glow) 55%,transparent) 0%, transparent 62%);
  opacity:calc(.28 + var(--lv) * .72);transform:scale(calc(.86 + var(--lv) * .34))}
.bo.rec .bo-halo{background:radial-gradient(circle, rgba(255,70,50,.75) 0%, rgba(255,59,47,.18) 42%, transparent 64%)}
.bo-ring{position:relative;width:100%;height:100%;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;
  background:radial-gradient(circle at 50% 38%, #2a1d15, #140d09 70%);
  box-shadow:inset 0 0 0 2px color-mix(in srgb,var(--glow) 70%,transparent), inset 0 -18px 40px rgba(0,0,0,.6), 0 24px 60px rgba(0,0,0,.55);
  transition:transform 160ms var(--ease),box-shadow 240ms var(--ease),background 240ms var(--ease)}
.bo-ring:active{transform:scale(.97)}
.bo-ring svg{width:28%;height:28%;color:var(--glow)}
.bo-ring span{font:500 15px/1.2 var(--font-body,system-ui);letter-spacing:.06em;color:var(--dim)}
.bo.rec .bo-ring{background:radial-gradient(circle at 50% 38%, #ff5a44, #c41e12 72%);box-shadow:inset 0 0 0 2px rgba(255,255,255,.25), 0 24px 60px rgba(0,0,0,.5)}
.bo.rec .bo-ring svg{color:#fff}.bo.rec .bo-ring span{color:#ffe9e4}
.bo-ring[disabled]{cursor:default;opacity:.6}
.bo-clock{font:300 clamp(56px,12vw,104px)/1 var(--font-mono,ui-monospace,monospace);font-variant-numeric:tabular-nums;letter-spacing:-.02em;margin-top:18px;color:var(--ink);opacity:.35;transition:opacity 240ms var(--ease)}
.bo.rec .bo-clock{opacity:1}
.bo-meter{position:relative;width:min(520px,100%);height:14px;margin-top:18px;border-radius:7px;overflow:hidden;
  background:linear-gradient(90deg,#3fae6a 0%,#7ccf5f 62%,#e9c443 80%,#ff8a3c 92%,#ff3b2f 100%);opacity:.95}
.bo-meter::after{content:"";position:absolute;top:0;bottom:0;right:0;width:calc((1 - var(--pk)) * 100%);background:#1a120d}
.bo-meter i{position:absolute;top:0;bottom:0;width:3px;left:calc(var(--hold) * 100% - 3px);background:#fff;opacity:calc(var(--hold) * 1.4);z-index:1}
.bo-meter b{position:absolute;top:0;bottom:0;width:1px;background:rgba(0,0,0,.55);z-index:1}
.bo-scale{position:relative;width:min(520px,100%);height:12px;font:400 11px/1 var(--font-mono,monospace);color:var(--faint);margin-top:6px}
.bo-scale span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}
.bo-scale span:first-child{transform:none}.bo-scale span:last-child{transform:translateX(-100%)}
.bo-word{min-height:22px;margin-top:8px;font-size:15px;color:var(--dim);text-align:center}
.bo-word.hot{color:#ffb35c}.bo-word.clip,.bo-word.err{color:#ff6b5c}
.bo-hp{font:500 clamp(18px,2.4vw,24px)/1.3 var(--font-display,Lora,Georgia,serif);color:var(--ink);text-align:center;margin:12px 0 0}
.bo-opts{display:flex;flex-wrap:wrap;justify-content:center;gap:10px;margin-top:22px}
.bo-opt{padding:9px 16px;border-radius:999px;border:1px solid rgba(241,230,216,.16);color:var(--dim);font-size:14px;transition:background-color 200ms var(--ease),color 200ms var(--ease)}
.bo-opt:hover{background:rgba(241,230,216,.06);color:var(--ink)}
.bo-opt.on{border-color:color-mix(in srgb,var(--glow) 70%,transparent);color:var(--ink);background:color-mix(in srgb,var(--glow) 14%,transparent)}
.bo-opt[disabled]{opacity:.4;cursor:default}
.bo-over{margin-top:14px;display:flex;align-items:center;gap:10px;font-size:15px;color:var(--ink);background:rgba(255,255,255,.04);border-radius:12px;padding:8px 8px 8px 14px;max-width:100%}
.bo-over span{overflow-wrap:anywhere}
.bo-over button{padding:4px 10px;border-radius:8px;color:var(--dim);font-size:13px}
.bo-over button:hover{background:rgba(255,255,255,.06)}
.bo-loops{width:100%;margin-top:14px;background:rgba(0,0,0,.25);border-radius:16px;padding:8px}
.bo-tr{border-radius:12px}
.bo-tn{display:flex;align-items:baseline;gap:10px;width:100%;padding:9px 12px;text-align:left}
.bo-tn b{font:400 18px/1.25 var(--font-display,Lora,serif);flex:1;min-width:0;overflow-wrap:anywhere;font-weight:400}
.bo-tn span{font-size:13px;color:var(--faint);white-space:nowrap}
.bo-parts{display:flex;flex-wrap:wrap;gap:6px;padding:0 10px 10px}
.bo-p{padding:6px 12px;border-radius:999px;background:rgba(255,255,255,.05);font-size:14px;color:var(--dim)}
.bo-p.on{background:var(--glow);color:#1a110b}
.bo-note{color:var(--faint);font-size:14px;margin:8px 12px}
.bo-words{width:100%;margin-top:16px;border-radius:16px;padding:16px 18px;background:rgba(0,0,0,.3);max-height:46vh;overflow:auto}
.bo-words pre{white-space:pre-wrap;margin:0;font:400 clamp(20px,2.2vw,26px)/1.5 var(--font-display,Lora,serif);color:var(--ink)}
.bo-takes{width:100%;margin-top:44px}
.bo-th{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:0 4px 10px;color:var(--faint);font-size:13px;letter-spacing:.14em;text-transform:uppercase}
.bo-th small{letter-spacing:0;text-transform:none;font-size:12px;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;direction:rtl;text-align:left}
.bo-t{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:12px;padding:10px 12px;border-radius:14px;margin-bottom:6px;
  background:linear-gradient(90deg,rgba(255,255,255,.045),rgba(255,255,255,.02))}
.bo-t.fresh{box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--glow) 55%,transparent)}
.bo-play{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;background:rgba(255,255,255,.07);color:var(--ink)}
.bo-play:hover{background:rgba(255,255,255,.12)}
.bo-play svg{width:16px;height:16px}
.bo-tm{min-width:0}
.bo-tname{font:400 18px/1.25 var(--font-display,Lora,serif);overflow-wrap:anywhere;text-align:left}
.bo-tname:hover{color:#fff}
.bo-tmeta{font-size:13px;color:var(--faint);overflow-wrap:anywhere}
.bo-bar{height:2px;background:rgba(255,255,255,.08);border-radius:2px;margin-top:6px;overflow:hidden}
.bo-bar i{display:block;height:100%;background:var(--glow);width:0}
.bo-send{padding:8px 12px;border-radius:999px;border:1px solid rgba(241,230,216,.16);font-size:13px;color:var(--dim);white-space:nowrap}
.bo-send:hover{color:var(--ink);background:rgba(255,255,255,.05)}
.bo-send[disabled]{opacity:.5;cursor:default}
.bo-said{grid-column:1/-1;font-size:13px;color:var(--dim)}
.bo-said.err{color:#ff8a7c}
.bo-nm{display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%}
.bo-nm input{flex:1 1 220px;min-width:0;font:400 18px/1.25 var(--font-display,Lora,serif);color:var(--ink);background:rgba(0,0,0,.35);
  border:1px solid color-mix(in srgb,var(--glow) 45%,transparent);border-radius:10px;padding:8px 12px;outline:none}
.bo-nm input::placeholder{color:var(--faint)}
.bo-nm button{padding:8px 12px;border-radius:10px;background:rgba(255,255,255,.07);font-size:13px;white-space:nowrap}
.bo-nm button.on{background:var(--air);color:#fff}
.bo-empty{color:var(--faint);font-size:15px;margin:4px}
.bo-drop{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(10,6,4,.82);pointer-events:none}
.bo-drop div{border:2px dashed var(--glow);border-radius:24px;padding:40px 48px;text-align:center;font:400 24px/1.35 var(--font-display,Lora,serif);max-width:80vw}
.bo-drop small{display:block;font:400 15px/1.4 var(--font-body,system-ui);color:var(--dim);margin-top:8px}
.bo-v{position:absolute;right:16px;bottom:14px;font-size:12px;color:var(--faint);text-decoration:none}
.bo-v:hover{color:var(--dim)}
@media(max-width:599px){
  .bo-in{padding:14px 14px 80px}
  .bo-t{grid-template-columns:auto 1fr;}
  .bo-send{grid-column:1/-1;justify-self:start}
}
@media(prefers-reduced-motion:reduce){.bo-ring,.bo-air,.bo-clock{transition:none!important}.bo-halo{transform:none}}
`

const raw = (p) => `/cc/files/raw?path=${encodeURIComponent(p)}`
const takeUrl = (p) => `/cc/booth/file?path=${encodeURIComponent(p)}`
const stampNow = () => new Date().toISOString().replace(/[-:]/g, '').replace(/\..*$/, '').replace('T', '-')
const words = (t) => String(t || '').replace(/^---[\s\S]*?\n---\n/, '').split('\n').filter(l => !/^\s*(#|<!--)/.test(l)).join('\n').trim()
const hhmm = (iso) => { const m = /T(\d{2}):?(\d{2})/.exec(String(iso || '')); return m ? `${m[1]}:${m[2]}` : '' }
const dayWord = (day) => {
  const today = new Date(); const t = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  return day === t ? 'today' : day
}
const overWord = (o) => (!o ? '' : o.kind === 'track' ? `over ${o.name || 'a track'}` : o.kind === 'loop' ? `over the loop ${o.label || o.id || ''}` : '')

function Glyph({ k }) {
  if (k === 'stop') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" /></svg>
  if (k === 'play') return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" fill="currentColor" /></svg>
  if (k === 'pause') return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" /><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" /></svg>
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2.5" width="6" height="12.5" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5M9 21.5h6" />
    </svg>
  )
}

export default function Sing() {
  const [phase, setPhase] = useState('idle')      // idle | arming | rec | saving
  const [msg, setMsg] = useState({ text: '', err: false })
  const [takes, setTakes] = useState(null)        // the booth's list, false when it did not load
  const [dir, setDir] = useState('')
  const [fresh, setFresh] = useState(null)        // the file of the take just kept: its name field is open
  const [naming, setNaming] = useState(null)      // a file whose name is being typed
  const [nameText, setNameText] = useState('')
  const [hearing, setHearing] = useState(false)   // speech recognition on for the name
  const [row, setRow] = useState({})              // file -> { text, err } under a take (sent, failed)
  const [playing, setPlaying] = useState(null)    // the file playing
  const [backing, setBacking] = useState(null)    // null | {kind:'track', name, seconds} | {kind:'loop', loop}
  const [loopsOpen, setLoopsOpen] = useState(false)
  const [cat, setCat] = useState(null)            // the loop catalogue, false when it did not load
  const [openTrack, setOpenTrack] = useState(null)
  const [lyrics, setLyrics] = useState('')
  const [dragging, setDragging] = useState(false)
  const [unsaved, setUnsaved] = useState(null)    // { url, blob, meta, grid } when the box did not take it
  const A = useRef({})                            // audio: ctx, stream, nodes, chunks, the track buffer
  const rootRef = useRef(null), clockRef = useRef(null), wordRef = useRef(null)
  const audioRef = useRef(null), barRef = useRef({})
  const fileRef = useRef(null)
  const phaseRef = useRef(phase)
  useEffect(() => { phaseRef.current = phase }, [phase])

  const say = (text, err = false) => setMsg({ text, err })

  // ---- the list of takes
  async function loadTakes() {
    try {
      const r = await fetch('/cc/booth')
      const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.error || String(r.status))
      setTakes(d.takes || []); setDir(d.dir || '')
    } catch { setTakes(false) }
  }

  useEffect(() => {
    loadTakes()
    let q = null
    try { q = new URLSearchParams(window.location.search) } catch {}
    if (q && (q.get('loops') || q.get('loop'))) { setLoopsOpen(true); loadCat(q.get('loops'), q.get('loop')) }
    const over = (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) { e.preventDefault(); setDragging(true) } }
    const leave = (e) => { if (!e.relatedTarget) setDragging(false) }
    const drop = (e) => {
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return
      e.preventDefault(); setDragging(false)
      const f = Array.from(e.dataTransfer.files).find(x => /^audio\//.test(x.type) || /\.(mp3|wav|m4a|aac|flac|ogg|opus|aif|aiff|webm)$/i.test(x.name))
      if (f) pickTrack(f); else say('that is not an audio file', true)
    }
    window.addEventListener('dragover', over); window.addEventListener('dragleave', leave); window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragover', over); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop)
      teardown(true)
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // ---- optional: a loop under the voice (the catalogue the loop page reads)
  function loadCat(path, want) {
    const p = path || 'ops/sing/loops.json'
    setCat(null)
    fetch(raw(p)).then(r => (r.ok ? r.json() : Promise.reject(r.status))).then(d => {
      setCat({ ...d, path: p })
      const ls = d.loops || []
      const l = ls.find(x => x.id === want) || (ls.length === 1 ? ls[0] : null)
      if (l) { setBacking({ kind: 'loop', loop: l }); setOpenTrack(l.track) }
    }).catch(() => setCat(false))
  }
  useEffect(() => {
    setLyrics('')
    const l = backing && backing.kind === 'loop' ? backing.loop : null
    if (!l || !l.lyrics) return
    let live = true
    fetch(raw(l.lyrics)).then(r => (r.ok ? r.text() : '')).then(t => { if (live) setLyrics(words(t)) }).catch(() => {})
    return () => { live = false }
  }, [backing])

  // ---- audio plumbing
  async function ctxReady() {
    const a = A.current
    if (!a.ctx) { const C = window.AudioContext || window.webkitAudioContext; a.ctx = new C({ latencyHint: 'interactive' }) }
    if (a.ctx.state !== 'running') { try { await a.ctx.resume() } catch {} }
    return a.ctx
  }
  function teardown(all) {
    const a = A.current
    a.capturing = false
    try { if (a.raf) cancelAnimationFrame(a.raf) } catch {}
    try { (a.sources || []).forEach(s => s.stop()) } catch {}
    a.sources = []
    for (const k of ['src', 'recIn', 'proc', 'mute', 'analyser']) { try { if (a[k]) a[k].disconnect() } catch {} a[k] = null }
    try { if (a.stream) a.stream.getTracks().forEach(t => t.stop()) } catch {}
    a.stream = null
    if (all) { try { if (audioRef.current) audioRef.current.pause() } catch {} }
  }

  async function pickTrack(file) {
    if (phaseRef.current === 'rec' || phaseRef.current === 'arming') return
    say(`reading ${file.name}`)
    try {
      const ctx = A.current.ctx || new (window.AudioContext || window.webkitAudioContext)({ latencyHint: 'interactive' })
      A.current.ctx = ctx
      const buf = await ctx.decodeAudioData(await file.arrayBuffer())
      A.current.trackBuf = buf
      setBacking({ kind: 'track', name: file.name, seconds: buf.duration, size: file.size })
      setLoopsOpen(false)
      say('')
    } catch { say(`this browser could not play ${file.name}`, true) }
  }
  async function loopBuffer(l) {
    const a = A.current
    if (a.loopId === l.id && a.loopBuf) return a.loopBuf
    const ctx = await ctxReady()
    const r = await fetch(raw(l.audio))
    if (!r.ok) throw new Error(`the loop's audio did not load (${r.status})`)
    const buf = await ctx.decodeAudioData(await r.arrayBuffer())
    const extra = buf.duration - l.samples / l.rate
    a.loopOff = extra > 0.0005 && extra >= 1105 / l.rate ? 1105 / l.rate : 0     // an MP3 decoder that kept LAME's delay
    a.loopBuf = buf; a.loopId = l.id; a.loopLen = (l.bars * 240) / l.bpm
    return buf
  }
  function play(ctx, buf, at, dest) { const s = ctx.createBufferSource(); s.buffer = buf; s.connect(dest || ctx.destination); s.start(at); return s }
  function clickBuffer(ctx, accent) {
    const n = Math.round(0.03 * ctx.sampleRate), d = new Float32Array(n), f = accent ? 1760 : 1320
    for (let i = 0; i < n; i++) d[i] = 0.5 * Math.sin((2 * Math.PI * f * i) / ctx.sampleRate) * Math.exp(-i / (0.006 * ctx.sampleRate))
    const b = ctx.createBuffer(1, n, ctx.sampleRate); b.getChannelData(0).set(d); return b
  }
  function latencyNow(ctx) {
    try { const v = JSON.parse(localStorage.getItem(LS_LAT) || 'null'); if (v && typeof v.ms === 'number') return { ms: v.ms, source: v.source } } catch {}
    return { ms: Math.round(1000 * ((ctx.outputLatency || 0) + (ctx.baseLatency || 0))), source: 'browser-reported output' }
  }

  // ---- record: press, sing, press again
  async function record() {
    if (phaseRef.current !== 'idle') return
    setFresh(null); setNaming(null); setUnsaved(null); say('')
    setPhase('arming')
    try { if (audioRef.current) audioRef.current.pause() } catch {}
    setPlaying(null)
    const a = A.current
    let ctx, stream, loopBuf = null
    try {
      if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) throw new Error('this browser cannot record')
      ctx = await ctxReady()
      if (backing && backing.kind === 'loop') loopBuf = await loopBuffer(backing.loop)
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } })
      } catch { throw new Error('the microphone is not allowed for this page: allow it in the address bar, then press again') }
    } catch (e) { setPhase('idle'); say(e.message || String(e), true); return }
    a.stream = stream
    const tr = stream.getAudioTracks()[0]
    const st = (tr && tr.getSettings && tr.getSettings()) || {}
    const ch = Math.min(2, Math.max(1, st.channelCount || 1))
    a.ch = ch; a.chunks = []; a.mic = (tr && tr.label) || ''
    a.src = ctx.createMediaStreamSource(stream)
    a.recIn = ctx.createGain()
    a.src.connect(a.recIn)
    a.proc = ctx.createScriptProcessor(4096, ch, ch)
    a.proc.channelCount = ch; a.proc.channelCountMode = 'explicit'
    a.mute = ctx.createGain(); a.mute.gain.value = 0
    a.recIn.connect(a.proc); a.proc.connect(a.mute); a.mute.connect(ctx.destination)
    a.analyser = ctx.createAnalyser(); a.analyser.fftSize = 2048
    a.src.connect(a.analyser)
    a.capturing = true
    const started = new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('the microphone sent nothing')), 4000)
      a.proc.onaudioprocess = (e) => {
        if (!a.capturing) return
        const k = []
        for (let c = 0; c < ch; c++) k.push(new Float32Array(e.inputBuffer.getChannelData(c)))
        a.chunks.push(k)
        if (a.chunks.length === 1) { clearTimeout(t); resolve(ctx.currentTime) }
      }
    })
    let t0
    try { t0 = await started } catch (e) { teardown(); setPhase('idle'); say(e.message, true); return }
    a.t0 = t0; a.sources = []; a.peakHold = -120; a.holdAt = 0
    a.take = { rate: ctx.sampleRate, ch, latency: latencyNow(ctx), out: ctx.outputLatency || 0 }
    if (backing) {
      const M = t0 + LEAD
      const mk = chirpSamples(ctx.sampleRate, CHIRP.amp)
      const mb = ctx.createBuffer(1, mk.length, ctx.sampleRate); mb.getChannelData(0).set(mk)
      a.sources.push(play(ctx, mb, M, a.recIn))   // the marker: into the take only, never the headphones
      a.take.M = M
      if (backing.kind === 'track' && a.trackBuf) {
        const T = M + LEAD
        a.sources.push(play(ctx, a.trackBuf, T))
        a.take.T = T; a.endAt = T + a.trackBuf.duration
      } else if (backing.kind === 'loop' && loopBuf) {
        const l = backing.loop, bar = 240 / l.bpm, beat = bar / 4, C0 = M + LEAD, L = C0 + bar
        for (let k = 0; k < 4; k++) a.sources.push(play(ctx, clickBuffer(ctx, k === 0), C0 + k * beat))
        const s = ctx.createBufferSource()
        s.buffer = loopBuf; s.loop = true; s.loopStart = a.loopOff; s.loopEnd = a.loopOff + a.loopLen
        s.connect(ctx.destination); s.start(L, a.loopOff)
        a.sources.push(s)
        Object.assign(a.take, { C0, L, bar, beat, grid: (cat && cat.grid_bars) || 32 })
        a.endAt = null
      }
    } else { a.endAt = null }
    setPhase('rec')
    const buf = new Float32Array(a.analyser.fftSize)
    const root = rootRef.current
    const tick = () => {
      if (!a.capturing) return
      const now = ctx.currentTime
      a.analyser.getFloatTimeDomainData(buf)
      const { peakDb, rmsDb } = levels(buf)
      if (peakDb > a.peakHold || now - a.holdAt > 1.5) { a.peakHold = peakDb; a.holdAt = now }
      if (peakDb >= -0.1) a.clipped = now
      if (root) {
        root.style.setProperty('--lv', meterPos(rmsDb + 6, -48).toFixed(3))
        root.style.setProperty('--pk', meterPos(peakDb).toFixed(3))
        root.style.setProperty('--hold', meterPos(a.peakHold).toFixed(3))
      }
      if (clockRef.current) clockRef.current.textContent = clock(now - t0)
      if (wordRef.current) {
        let w = levelWord(peakDb, a.clipped && now - a.clipped < 2 ? 0 : -120)
        let text = w === 'clip' ? 'too loud: it clipped. Step back a little or turn the input down' : w === 'hot' ? 'hot: a touch further from the mic' : w === 'quiet' ? 'listening' : 'good level'
        if (a.take.L && now < a.take.L) { text = `count-in ${Math.min(4, Math.max(1, 4 - Math.floor((a.take.L - now) / a.take.beat)))}`; w = 'good' }
        if (wordRef.current.textContent !== text) { wordRef.current.textContent = text; wordRef.current.className = 'bo-word ' + w }
      }
      if (now - t0 > MAX_S) { stop('thirty minutes: the take stopped by itself'); return }
      if (a.endAt && now > a.endAt + 1.5) { stop('the track ended'); return }
      a.raf = requestAnimationFrame(tick)
    }
    a.raf = requestAnimationFrame(tick)
  }

  async function stop(why) {
    const a = A.current
    if (phaseRef.current !== 'rec' || a.stopping) return
    a.stopping = true
    const ctx = a.ctx, tk = a.take
    tk.stopCtx = ctx.currentTime
    const chunks = a.chunks, ch = a.ch, mic = a.mic
    teardown()
    a.chunks = []
    a.stopping = false
    const root = rootRef.current
    if (root) { root.style.setProperty('--lv', '0'); root.style.setProperty('--pk', '0'); root.style.setProperty('--hold', '0') }
    if (wordRef.current) { wordRef.current.textContent = ''; wordRef.current.className = 'bo-word' }
    const chans = joinChunks(chunks, ch)
    const seconds = chans[0].length / tk.rate
    if (seconds < 0.3) { setPhase('idle'); say('nothing was recorded', true); return }
    setPhase('saving')
    say(typeof why === 'string' ? `${why}; keeping it` : 'keeping it')
    let over = null, grid = null
    if (backing) {
      const f = findChirp(chans[0], tk.rate, 0, Math.min(seconds, 3))
      const marker = f && f.t != null ? f.t : null
      const lat = tk.latency.ms / 1000
      if (backing.kind === 'track') {
        over = { kind: 'track', name: backing.name, seconds: Math.round(backing.seconds * 1000) / 1000, marker_in_take_s: marker,
                 marker_clarity: f ? Math.round(f.clarity * 10) / 10 : 0, marker_s: LEAD, latency_ms: tk.latency.ms, latency_source: tk.latency.source,
                 track_start_in_take_s: marker != null ? Math.round((marker + (tk.T - tk.M) + lat) * 10000) / 10000 : null }
      } else {
        const l = backing.loop
        const bar1 = marker != null ? marker + (tk.L - tk.M) + lat : null
        over = { kind: 'loop', id: l.id, label: `${String(l.track || '').replace(/_/g, ' ')} ${l.label || ''}`.trim(), bpm: l.bpm, bars: l.bars,
                 marker_in_take_s: marker, latency_ms: tk.latency.ms, bar1_in_take_s: bar1 != null ? Math.round(bar1 * 10000) / 10000 : null }
        // the loop page's sidecar (hbar.sing.take/v1), so the rooms place it on the loop's grid as before
        grid = {
          dialect: 'hbar.sing.take/v1', made: new Date().toISOString(),
          loop: { id: l.id, track: l.track, part: l.part, key: l.key, bars: l.bars, bpm: l.bpm, audio: l.audio, layer: l.layer },
          grid_bars: tk.grid,
          recorded: { mime: 'audio/wav', ctx_rate: tk.rate, rec_start_ctx: a.t0, marker: { at_ctx: tk.M, ...CHIRP },
                      count_in: { at_ctx: tk.C0, bars: 1 }, loop_start_ctx: tk.L, stop_ctx: tk.stopCtx, loop_offset_s: a.loopOff || 0 },
          latency: { used_ms: tk.latency.ms, source: tk.latency.source, reported_output_ms: Math.round(1000 * (tk.out || 0)) },
          nudge_ms: 0,
          page: { marker_in_take_s: marker, marker_clarity: f ? f.clarity : 0, bar1_in_take_s: bar1, booth: true },
        }
      }
    }
    const wav = encodeWav(chans, tk.rate, 24)
    const blob = new Blob([wav], { type: 'audio/wav' })
    const meta = { over, page: { mic: String(mic).slice(0, 120), channels: ch, rate: tk.rate, browser_seconds: Math.round(seconds * 1000) / 1000 } }
    await keep(blob, meta, grid)
  }

  async function keep(blob, meta, grid) {
    setPhase('saving')
    try {
      const r = await fetch('/cc/booth/take', { method: 'POST', headers: { 'Content-Type': 'audio/wav', 'X-Booth-Meta': encodeURIComponent(JSON.stringify(meta)) }, body: blob })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || `the console answered ${r.status}`)
      setUnsaved(u => { if (u && u.url) { try { URL.revokeObjectURL(u.url) } catch {} } return null })
      setTakes(t => [d.take, ...((t || []).filter(x => x.file !== d.take.file))])
      setFresh(d.take.file); setNaming(d.take.file); setNameText('')
      setPhase('idle')
      say('')
      if (grid) toGrid(blob, grid, d.take)
    } catch (e) {
      setUnsaved(u => (u && u.blob === blob ? u : { url: URL.createObjectURL(blob), blob, meta, grid }))
      setPhase('idle')
      say(`not kept on the box yet (${e.message || 'no answer'}). The take is safe in this tab: try again, or download it.`, true)
    }
  }

  async function toGrid(blob, side, take) {
    const name = `sing_${stampNow()}_${side.loop.id ? String(backing && backing.loop && backing.loop.slug || side.loop.id).replace(/[^A-Za-z0-9_-]+/g, '_') : 'loop'}`
    side.file = `${name}.wav`
    const fd = new FormData()
    fd.append('file', blob, side.file)
    fd.append('sidecar', new Blob([JSON.stringify({ ...side, booth_take: take.path }, null, 1)], { type: 'application/json' }), `${name}.json`)
    try {
      const r = await fetch('/cc/upload', { method: 'POST', body: fd })
      const d = await r.json().catch(() => ({}))
      setRow(x => ({ ...x, [take.file]: r.ok && d.ok ? { text: 'also sent to the loop\'s grid; the room places it within two minutes' } : { text: `the grid copy did not go (${d.error || r.status}); the take itself is kept`, err: true } }))
    } catch { setRow(x => ({ ...x, [take.file]: { text: 'the grid copy did not go; the take itself is kept', err: true } })) }
  }

  // ---- name it afterwards
  async function saveName(t, text) {
    const name = String(text || '').trim()
    setNaming(null); setHearing(false)
    try { if (A.current.rec) A.current.rec.stop() } catch {}
    if (!name) return
    try {
      const r = await fetch('/cc/booth/name', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file: t.file, name }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || String(r.status))
      setTakes(list => (list || []).map(x => (x.file === t.file ? d.take : x)))
      if (fresh === t.file) setFresh(d.take.file)
      if (playing === t.file) setPlaying(d.take.file)
    } catch (e) { setRow(x => ({ ...x, [t.file]: { text: `could not name it: ${e.message}`, err: true } })) }
  }
  function sayName() {
    const R = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
    if (!R) return
    const a = A.current
    if (hearing) { try { a.rec && a.rec.stop() } catch {} setHearing(false); return }
    const rec = new R()
    rec.lang = navigator.language || 'en-US'; rec.interimResults = true; rec.maxAlternatives = 1
    rec.onresult = (e) => { let s = ''; for (let i = 0; i < e.results.length; i++) s += e.results[i][0].transcript; setNameText(s.trim()) }
    rec.onend = () => setHearing(false)
    rec.onerror = () => setHearing(false)
    a.rec = rec
    try { rec.start(); setHearing(true) } catch { setHearing(false) }
  }
  const canSay = typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition)

  // ---- play back, send to the phone
  function toggle(t) {
    const el = audioRef.current
    if (!el) return
    if (playing === t.file && !el.paused) { el.pause(); setPlaying(null); return }
    if (el.dataset.file !== t.file) { el.src = takeUrl(t.path); el.dataset.file = t.file }
    el.play().then(() => setPlaying(t.file)).catch(() => setRow(x => ({ ...x, [t.file]: { text: 'this browser could not play it', err: true } })))
  }
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const tu = () => { const b = barRef.current[el.dataset.file]; if (b && el.duration) b.style.width = `${(100 * el.currentTime) / el.duration}%` }
    const end = () => { setPlaying(null); const b = barRef.current[el.dataset.file]; if (b) b.style.width = '0' }
    el.addEventListener('timeupdate', tu); el.addEventListener('ended', end)
    return () => { el.removeEventListener('timeupdate', tu); el.removeEventListener('ended', end) }
  }, [])
  async function toPhone(t) {
    setRow(x => ({ ...x, [t.file]: { text: 'sending to your phone', busy: true } }))
    try {
      const r = await fetch('/cc/send-file', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: t.path, caption: `${t.title || t.name} (${clock(t.seconds)})` }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || `the console answered ${r.status}`)
      setRow(x => ({ ...x, [t.file]: { text: 'on your phone (Telegram)' } }))
    } catch (e) { setRow(x => ({ ...x, [t.file]: { text: `not sent: ${e.message}`, err: true } })) }
  }

  // ---- the loop list, grouped by track
  const tracks = []
  if (cat && cat.loops) {
    const by = {}
    cat.loops.forEach(l => { if (!by[l.track]) { by[l.track] = []; tracks.push(l.track) } by[l.track].push(l) })
    tracks.splice(0, tracks.length, ...tracks.map(t => ({ name: t, parts: by[t] })))
  }
  const rec = phase === 'rec'
  const busy = phase === 'rec' || phase === 'arming' || phase === 'saving'
  const ringWord = phase === 'arming' ? 'opening the mic' : phase === 'saving' ? 'keeping it' : rec ? 'stop' : backing ? 'sing over it' : 'press and sing'

  return (
    <>
      <Head><title>Booth</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className={'bo' + (rec ? ' rec' : '')} ref={rootRef}>
        <div className="bo-in">
          <div className="bo-top">
            <h1 className="bo-name" style={{ margin: 0 }}>Booth</h1>
            <div className="bo-air" aria-hidden="true">ON AIR</div>
          </div>

          <div className="bo-stage">
            <div className="bo-halo" />
            <button type="button" className="bo-ring" onClick={rec ? () => stop() : record} disabled={phase === 'arming' || phase === 'saving'}
              aria-label={rec ? 'stop recording' : 'record'} aria-pressed={rec}>
              <Glyph k={rec ? 'stop' : 'mic'} />
              <span>{ringWord}</span>
            </button>
          </div>

          <div className="bo-clock" ref={clockRef} aria-live="off">0:00</div>
          <div className="bo-meter" aria-hidden="true"><i />{[0.25, 0.5, 0.75, 0.95].map(p => <b key={p} style={{ left: `${p * 100}%` }} />)}</div>
          <div className="bo-scale" aria-hidden="true">{[[-60, 0], [-45, 0.25], [-30, 0.5], [-15, 0.75], [0, 1]].map(([db, p]) => <span key={db} style={{ left: `${p * 100}%` }}>{db === 0 ? '0 dB' : db}</span>)}</div>
          <div className="bo-word" ref={wordRef} />
          <div className={'bo-word' + (msg.err ? ' err' : '')} role="status">{msg.text}</div>
          {unsaved ? (
            <div className="bo-opts">
              <button type="button" className="bo-opt on" onClick={() => keep(unsaved.blob, unsaved.meta, unsaved.grid)} disabled={busy}>try again</button>
              <a className="bo-opt" href={unsaved.url} download={`take_${stampNow()}.wav`}>download the take</a>
            </div>
          ) : null}

          {backing ? <p className="bo-hp">{HEADPHONES}</p> : null}
          {backing ? (
            <div className="bo-over">
              <span>Over {backing.kind === 'track' ? `${backing.name} · ${clock(backing.seconds)}` : `${String(backing.loop.track).replace(/_/g, ' ')} · ${backing.loop.label} · ${backing.loop.bpm} BPM`}</span>
              <button type="button" onClick={() => { setBacking(null); A.current.trackBuf = null }} disabled={busy}>just my voice</button>
            </div>
          ) : null}

          <div className="bo-opts">
            <button type="button" className={'bo-opt' + (backing && backing.kind === 'track' ? ' on' : '')} onClick={() => fileRef.current && fileRef.current.click()} disabled={busy}>sing over a track</button>
            <button type="button" className={'bo-opt' + (loopsOpen ? ' on' : '')} disabled={busy}
              onClick={() => { const o = !loopsOpen; setLoopsOpen(o); if (o && cat === null) loadCat() }}>over a loop</button>
            <input ref={fileRef} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) pickTrack(f); e.target.value = '' }} />
          </div>

          {loopsOpen ? (
            <div className="bo-loops" aria-label="loops">
              {cat === null ? <p className="bo-note">loading the loops</p> : null}
              {cat === false ? <p className="bo-note">The loop list did not load (ops/sing/loops.json in the world).</p> : null}
              {tracks.map(t => (
                <div key={t.name} className="bo-tr">
                  <button type="button" className="bo-tn" onClick={() => setOpenTrack(o => (o === t.name ? null : t.name))} aria-expanded={openTrack === t.name}>
                    <b>{t.name.replace(/_/g, ' ')}</b><span>{t.parts.length} {t.parts.length === 1 ? 'part' : 'parts'} · {t.parts[0].key}</span>
                  </button>
                  {openTrack === t.name ? (
                    <div className="bo-parts">
                      {t.parts.map(l => (
                        <button type="button" key={l.id} className={'bo-p' + (backing && backing.kind === 'loop' && backing.loop.id === l.id ? ' on' : '')}
                          onClick={() => { if (!busy) { setBacking({ kind: 'loop', loop: l }); A.current.trackBuf = null } }}>
                          {l.label} · {l.bars}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {lyrics ? <div className="bo-words" aria-label="lyrics"><pre>{lyrics}</pre></div> : null}

          <section className="bo-takes" aria-label="takes">
            <div className="bo-th"><span>Takes</span>{dir ? <small title={dir}>{'\u200e' + dir}</small> : null}</div>
            {takes === null ? <p className="bo-empty">loading your takes</p> : null}
            {takes === false ? <p className="bo-empty">The takes did not load. Recording still works; each take is kept when you stop.</p> : null}
            {takes && !takes.length ? <p className="bo-empty">Nothing yet. Press the ring and sing: every take is kept as a WAV, and you name it after.</p> : null}
            {(takes || []).map(t => {
              const r = row[t.file]
              return (
                <div key={t.file} className={'bo-t' + (fresh === t.file ? ' fresh' : '')}>
                  <button type="button" className="bo-play" onClick={() => toggle(t)} aria-label={playing === t.file ? 'pause' : 'play'}>
                    <Glyph k={playing === t.file ? 'pause' : 'play'} />
                  </button>
                  <div className="bo-tm">
                    {naming === t.file ? (
                      <form className="bo-nm" onSubmit={(e) => { e.preventDefault(); saveName(t, nameText) }}>
                        <input autoFocus value={nameText} onChange={(e) => setNameText(e.target.value)} placeholder={canSay ? 'say or type a name' : 'type a name'}
                          onKeyDown={(e) => { if (e.key === 'Escape') { setNaming(null); setHearing(false) } }} aria-label="name this take" />
                        {canSay ? <button type="button" className={hearing ? 'on' : ''} onClick={sayName}>{hearing ? 'listening' : 'say it'}</button> : null}
                        <button type="submit">save</button>
                      </form>
                    ) : (
                      <button type="button" className="bo-tname" onClick={() => { setNaming(t.file); setNameText(t.title || (t.name === 'take' ? '' : t.name)) }} title="rename">
                        {t.title || t.name}
                      </button>
                    )}
                    <div className="bo-tmeta">{[dayWord(t.day), hhmm(t.made), clock(t.seconds), overWord(t.over)].filter(Boolean).join(' · ')}</div>
                    <div className="bo-bar"><i ref={el => { barRef.current[t.file] = el }} /></div>
                  </div>
                  <button type="button" className="bo-send" onClick={() => toPhone(t)} disabled={!!(r && r.busy)}>send to my phone</button>
                  {r ? <div className={'bo-said' + (r.err ? ' err' : '')}>{r.text}</div> : null}
                </div>
              )
            })}
          </section>
        </div>
        <a className="bo-v" href="/sing/v1">the loop page (v1)</a>
        <audio ref={audioRef} preload="none" hidden />
        {dragging ? <div className="bo-drop"><div>Drop a track<small>{HEADPHONES}. It plays in your headphones while you sing.</small></div></div> : null}
      </div>
    </>
  )
}
