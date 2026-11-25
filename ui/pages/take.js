import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'
import { CHIRP, chirpSamples, clock, encodeWav, findChirp, joinChunks, levels, meterPos } from '../lib/booth'
import { listener } from '../lib/listen'
import { driftStats, fitLine, hasOffer, pairsInTake, stripCounts, syncStep } from '../lib/take'

// Take (DEMO-1, 2026-11-25). The owner: "i want to record my rap tracks ... put the tracks i like under them and then
// contact the people and show them the demo and ask if i can use it" and "I WANT AN EASIER METHOD TO JUST DO IT".
// One surface, three steps and nothing else: record, demo, ask. The strip on top says where every take stands.
//   Record: what is under the voice (nothing, one of the owner's own tracks, a track from their playlists, a file
//     they drop) and one record control; spoken lines from the world's lines file shown large, one take per group.
//     A playlist track plays through the official YouTube embed in the headphones while only the microphone is
//     recorded; nothing is downloaded. The page samples the embed's clock against the take's while recording and
//     keeps the pairs with the take (the sync mark is the booth's 30 ms marker in the take).
//   Demo: the box renders each take by itself (the world's renderer, a few minutes): three treatments (dry, warm,
//     phone), alone and over the track; keep, again or drop in one press. An embed take plays the artist's own embed
//     with the voice in sync (rate nudges, a seek past 120 ms; the drift is shown).
//   Ask: on a kept demo over someone else's track, the brain drafts the message; the owner fills the offer line and
//     sends with one press (the world's renderer sends it through the owner's mail door). Nothing goes out unpressed.
// Recording is the booth's (POST /cc/booth/take, page.surface = "take"); state is GET /cc/take (scripts/cc/cc_take.py).

const LEAD = 0.35
const MAX_S = 20 * 60
const HEADPHONES = 'Wired headphones on: only your voice is recorded'
const YT_HOST = 'https://www.youtube-nocookie.com'
const LS_LAT = 'cc.sing.latency'

const CSS = `
.tk{--line:color-mix(in srgb,var(--text) 14%,transparent);--soft:color-mix(in srgb,var(--surface) 60%,transparent);--rec:#e5483b;
  --ease:cubic-bezier(.2,.7,.2,1);--top:calc(var(--nav-h,52px) + env(safe-area-inset-top,0px));--lv:0;--pk:0;
  min-height:calc(100vh - var(--top));color:var(--text);font:400 16px/1.5 var(--font-body);box-sizing:border-box;
  background:linear-gradient(180deg,color-mix(in srgb,var(--accent) 9%,var(--bg)) 0,var(--bg) 340px)}
.tk *{box-sizing:border-box}
.tk :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;-webkit-tap-highlight-color:transparent}
.tk :focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:10px}
.tk-in{max-width:860px;margin:0 auto;padding:20px 20px 120px}
.tk-h{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.tk-h h1{font:400 30px/1 var(--font-display);margin:0;letter-spacing:.01em}
.tk-strip{display:flex;gap:0;border-radius:999px;background:var(--soft);box-shadow:inset 0 0 0 1px var(--line);padding:4px}
.tk-st{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:999px;font:500 14px/1 var(--font-body);color:var(--text-dim);white-space:nowrap;
  transition:background-color 160ms var(--ease),color 160ms var(--ease)}
.tk-st b{font:600 11px/1 var(--font-mono);min-width:20px;height:20px;border-radius:10px;display:inline-grid;place-items:center;background:var(--line);color:var(--text);padding:0 6px}
.tk-st.on{background:var(--accent);color:var(--bg)}.tk-st.on b{background:color-mix(in srgb,var(--bg) 25%,transparent);color:var(--bg)}
.tk-st.hot b{background:var(--accent);color:var(--bg)}
.tk-sec{margin-top:26px}
.tk-lab{font:500 12px/1 var(--font-mono);letter-spacing:.16em;text-transform:uppercase;color:var(--text-dim);margin:0 0 10px}
.tk-chips{display:flex;flex-wrap:wrap;gap:8px}
.tk-chip{padding:9px 16px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--line);font-size:15px;color:var(--text-dim);
  transition:background-color 160ms var(--ease),color 160ms var(--ease),box-shadow 160ms var(--ease)}
.tk-chip:hover{color:var(--text);background:var(--soft)}
.tk-chip.on{color:var(--text);background:color-mix(in srgb,var(--accent) 16%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 70%,transparent)}
.tk-chip[disabled]{opacity:.45;cursor:default}
.tk-list{margin-top:10px;max-height:300px;overflow:auto;border-radius:14px;background:var(--soft);box-shadow:inset 0 0 0 1px var(--line);padding:6px}
.tk-it{display:flex;justify-content:space-between;align-items:baseline;gap:12px;width:100%;text-align:left;padding:9px 12px;border-radius:10px}
.tk-it:hover{background:color-mix(in srgb,var(--text) 6%,transparent)}
.tk-it.on{background:color-mix(in srgb,var(--accent) 18%,transparent)}
.tk-it span{overflow-wrap:anywhere}.tk-it small{color:var(--text-dim);white-space:nowrap;font-size:13px}
.tk-note{color:var(--text-dim);font-size:14px;margin:8px 4px}
.tk-under{display:flex;align-items:center;gap:14px;margin-top:14px;padding:12px 14px;border-radius:14px;background:var(--soft);box-shadow:inset 0 0 0 1px var(--line)}
.tk-under div{min-width:0;flex:1}.tk-under b{display:block;font:400 19px/1.25 var(--font-display);overflow-wrap:anywhere}
.tk-under small{color:var(--text-dim);font-size:13px}
.tk-yt{width:200px;height:200px;border-radius:12px;overflow:hidden;background:#000;flex:none}
.tk-mine{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--text-dim);margin-top:8px;cursor:pointer}
.tk-mine i{width:18px;height:18px;border-radius:5px;box-shadow:inset 0 0 0 1.5px var(--line);display:grid;place-items:center;font-style:normal;font-size:12px}
.tk-mine.on i{background:var(--accent);color:var(--bg);box-shadow:none}
.tk-hp{font:400 clamp(22px,3vw,30px)/1.25 var(--font-display);text-align:center;margin:30px 0 0}
.tk-rec{display:flex;flex-direction:column;align-items:center;margin-top:22px}
.tk-btn{width:132px;height:132px;border-radius:50%;display:grid;place-items:center;background:color-mix(in srgb,var(--rec) 14%,var(--bg));
  box-shadow:inset 0 0 0 2px var(--rec),0 12px 40px color-mix(in srgb,var(--rec) calc(20% + var(--lv) * 50%),transparent);transition:transform 140ms var(--ease)}
.tk-btn:active{transform:scale(.96)}
.tk-btn i{width:46px;height:46px;border-radius:50%;background:var(--rec);transition:border-radius 200ms var(--ease),width 200ms var(--ease),height 200ms var(--ease)}
.tk.rec .tk-btn i{width:40px;height:40px;border-radius:8px}
.tk-btn[disabled]{opacity:.55;cursor:default}
.tk-clock{font:300 54px/1 var(--font-mono);font-variant-numeric:tabular-nums;margin-top:16px;opacity:.4}.tk.rec .tk-clock{opacity:1}
.tk-meter{width:min(460px,100%);height:8px;border-radius:4px;margin-top:14px;background:var(--line);overflow:hidden}
.tk-meter i{display:block;height:100%;width:calc(var(--pk) * 100%);background:linear-gradient(90deg,#4caf6e,#cfc04a 78%,var(--rec))}
.tk-word{min-height:22px;margin-top:10px;color:var(--text-dim);text-align:center}.tk-word.err{color:var(--rec)}
.tk-read{margin-top:24px;padding:22px 24px;border-radius:18px;background:var(--soft);box-shadow:inset 0 0 0 1px var(--line)}
.tk-read p{margin:0;font:400 clamp(26px,3.6vw,40px)/1.35 var(--font-display)}
.tk-read nav{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px;color:var(--text-dim);font-size:14px}
.tk-read nav button{padding:6px 12px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--line)}
.tk-row{display:grid;grid-template-columns:1fr auto;gap:10px 14px;align-items:center;padding:14px 16px;border-radius:16px;background:var(--soft);
  box-shadow:inset 0 0 0 1px var(--line);margin-bottom:10px;text-align:left;width:100%}
.tk-row.sel{box-shadow:inset 0 0 0 1.5px color-mix(in srgb,var(--accent) 75%,transparent)}
.tk-row b{font:400 19px/1.25 var(--font-display);overflow-wrap:anywhere;display:block}
.tk-row small{color:var(--text-dim);font-size:13px;overflow-wrap:anywhere}
.tk-tag{font:600 11px/1 var(--font-mono);letter-spacing:.08em;text-transform:uppercase;padding:6px 9px;border-radius:6px;background:var(--line);color:var(--text);white-space:nowrap}
.tk-tag.ready,.tk-tag.drafted,.tk-tag.to-ask{background:var(--accent);color:var(--bg)}
.tk-tag.making,.tk-tag.drafting,.tk-tag.sending{background:transparent;box-shadow:inset 0 0 0 1px var(--line);color:var(--text-dim)}
.tk-panel{grid-column:1/-1;margin-top:6px}
.tk-tr{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 4px}
.tk-tr button{display:flex;align-items:center;gap:8px;padding:10px 16px;border-radius:12px;box-shadow:inset 0 0 0 1px var(--line);font-size:15px}
.tk-tr button.on{background:color-mix(in srgb,var(--accent) 18%,transparent);box-shadow:inset 0 0 0 1.5px var(--accent)}
.tk-tr button svg{width:13px;height:13px}
.tk-tr small{display:block;color:var(--text-dim);font-size:12px}
.tk-words{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.tk-w{padding:10px 20px;border-radius:999px;font-weight:500;box-shadow:inset 0 0 0 1px var(--line)}
.tk-w.keep{background:var(--accent);color:var(--bg);box-shadow:none}
.tk-w[disabled]{opacity:.5;cursor:default}
.tk-sync{font:400 13px/1.4 var(--font-mono);color:var(--text-dim);margin-top:8px}
.tk-film video{width:100%;border-radius:14px;background:#000;margin-top:10px}
.tk-film ol{margin:10px 0 0;padding-left:20px;color:var(--text-dim);font-size:14px}.tk-film li{margin:4px 0}
.tk-film li button{color:var(--text);text-decoration:underline;text-decoration-color:var(--line);text-underline-offset:3px;text-align:left}
.tk-form{display:grid;gap:10px;margin-top:10px}
.tk-form label{font-size:13px;color:var(--text-dim)}
.tk-form input,.tk-form textarea{width:100%;font:400 16px/1.45 var(--font-body);color:var(--text);background:color-mix(in srgb,var(--bg) 70%,transparent);
  border:0;box-shadow:inset 0 0 0 1px var(--line);border-radius:10px;padding:10px 12px;outline:none}
.tk-form input:focus,.tk-form textarea:focus{box-shadow:inset 0 0 0 1.5px var(--accent)}
.tk-form textarea{min-height:230px;resize:vertical}
.tk-found{font-size:13px;color:var(--text-dim);overflow-wrap:anywhere}
.tk-empty{color:var(--text-dim);margin:6px 2px}
.tk-eye{display:block;font:500 11px/1 var(--font-mono);letter-spacing:.2em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.tk-find{margin-top:10px;border-radius:16px;background:var(--soft);box-shadow:inset 0 0 0 1px var(--line);padding:12px}
.tk-find header{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:0 2px 10px;flex-wrap:wrap}
.tk-find header b{font:400 19px/1.2 var(--font-display)}.tk-find header small{color:var(--text-dim);font-size:13px}
.tk-q{display:flex;gap:8px;align-items:center}
.tk-q input{flex:1;min-width:0;font:400 17px/1.4 var(--font-body);color:var(--text);background:color-mix(in srgb,var(--bg) 70%,transparent);border:0;
  box-shadow:inset 0 0 0 1px var(--line);border-radius:12px;padding:11px 14px;outline:none;-webkit-appearance:none;appearance:none}
.tk-q input:focus{box-shadow:inset 0 0 0 1.5px var(--accent)}
.tk-q input::placeholder{color:var(--text-dim)}
.tk-q button{padding:11px 16px;border-radius:12px;background:var(--accent);color:var(--bg);font-weight:500;white-space:nowrap}
.tk-q button[disabled]{opacity:.5;cursor:default}
.tk-fl{margin:14px 2px 4px;font:500 11px/1 var(--font-mono);letter-spacing:.14em;text-transform:uppercase;color:var(--text-dim)}
.tk-sc{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.tk-sc button{padding:7px 12px;border-radius:999px;font-size:14px;box-shadow:inset 0 0 0 1px var(--line);color:var(--text-dim)}
.tk-sc button:hover{color:var(--text);background:color-mix(in srgb,var(--text) 6%,transparent)}
.tk-it.off{opacity:.42;cursor:not-allowed}.tk-it.off:hover{background:none}
.tk-it em{display:block;font-style:normal;font-size:12px;color:var(--text-dim)}
.tk-grey{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:12px 2px 2px;font-size:13px;color:var(--text-dim)}
.tk-grey button{padding:7px 12px;border-radius:999px;box-shadow:inset 0 0 0 1px var(--line);color:var(--text)}
.tk-drop{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:color-mix(in srgb,var(--bg) 85%,transparent);pointer-events:none}
.tk-drop div{border:2px dashed var(--accent);border-radius:24px;padding:40px 48px;text-align:center;font:400 26px/1.3 var(--font-display)}
@media(max-width:599px){.tk-in{padding:14px 14px 100px}.tk-st{padding:8px 11px;font-size:13px}.tk-yt{width:200px;height:200px}.tk-under{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){.tk *{transition:none!important}}
`

const fileUrl = (p) => `/cc/take/file?path=${encodeURIComponent(p)}`
const underWord = (o) => {
  if (!o || !o.kind || o.kind === 'none') return 'just the voice'
  return `over ${o.title || o.name || 'a track'}${o.artist ? ` (${o.artist})` : ''}`
}
const ago = (iso) => { const m = /T(\d{2}):?(\d{2})/.exec(String(iso || '')); return m ? `${String(iso).slice(0, 10)} ${m[1]}:${m[2]}` : '' }

let ytApi = null
function loadYT() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if (window.YT && window.YT.Player) return Promise.resolve(window.YT)
  if (ytApi) return ytApi
  ytApi = new Promise((resolve, reject) => {
    const prev = window.onYouTubeIframeAPIReady
    window.onYouTubeIframeAPIReady = () => { if (typeof prev === 'function') { try { prev() } catch (e) {} } resolve(window.YT) }
    const s = document.createElement('script')
    s.src = 'https://www.youtube.com/iframe_api'; s.async = true
    s.onerror = () => { ytApi = null; reject(new Error('the YouTube player did not load')) }
    document.head.appendChild(s)
  })
  return ytApi
}
function makePlayer(el, videoId, onState) {
  return loadYT().then(YT => new Promise((resolve, reject) => {
    const p = new YT.Player(el, {
      host: YT_HOST, width: 200, height: 200, videoId,
      playerVars: { playsinline: 1, rel: 0, modestbranding: 1, origin: window.location.origin },
      events: {
        onReady: () => resolve(p),
        onStateChange: (e) => onState && onState(e.data),
        onError: (e) => reject(new Error(e.data === 101 || e.data === 150 ? 'the artist does not allow this video to play outside YouTube' : `the video did not play (${e.data})`)),
      },
    })
  }))
}

function Play({ on }) {
  return on
    ? <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" /><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" /></svg>
    : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" fill="currentColor" /></svg>
}

export default function TakePage() {
  const [tab, setTab] = useState('record')
  const [data, setData] = useState(null)          // GET /cc/take, false when it did not load
  const [stations, setStations] = useState(null)  // GET /cc/listen stations
  const [pick, setPick] = useState(null)          // 'own' | 'playlists' | null: which list is open
  const [items, setItems] = useState(null)        // the open list's items
  const [plOpen, setPlOpen] = useState(null)      // the playlist whose items show
  const [q, setQ] = useState('')                  // the orfeo library search box
  const [found, setFound] = useState(null)        // GET /cc/take/find answer
  const [finding, setFinding] = useState(false)   // a live YouTube search on its way
  const [under, setUnder] = useState({ kind: 'none' })
  const [read, setRead] = useState(null)          // { set, group } lines shown to read
  const [phase, setPhase] = useState('idle')      // idle | loading | arming | rec | saving
  const [msg, setMsg] = useState({ text: '', err: false })
  const [sel, setSel] = useState(null)            // the take open on the demo or ask screen
  const [treat, setTreat] = useState({})          // take file -> treatment chosen by ear
  const [playing, setPlaying] = useState(null)    // `${file}:${treatment}`
  const [sync, setSync] = useState(null)          // the synced demo's drift line
  const [forms, setForms] = useState({})          // take file -> { to, subject, body }
  const [rowMsg, setRowMsg] = useState({})
  const [dragging, setDragging] = useState(false)
  const A = useRef({})
  const rootRef = useRef(null), clockRef = useRef(null), audioRef = useRef(null)
  const ytRecEl = useRef(null), ytDemoEl = useRef(null), fileRef = useRef(null)
  const phaseRef = useRef(phase)
  useEffect(() => { phaseRef.current = phase }, [phase])
  const say = (text, err = false) => setMsg({ text, err })

  // ---- state from the bridge, polled faster while the box works
  async function load() {
    try {
      const r = await fetch('/cc/take'); const d = await r.json()
      if (!r.ok || !d.ok) throw new Error(d.error || r.status)
      setData(d)
      return d
    } catch { setData(x => x || false) }
    return null
  }
  const busyBox = !!(data && data.takes && data.takes.some(t => ['making', 'drafting', 'sending'].includes(t.step && t.step.state)))
  useEffect(() => {
    load()
    const t = setInterval(() => { if (phaseRef.current !== 'rec') load() }, busyBox ? 5000 : 15000)
    return () => clearInterval(t)
  }, [busyBox])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let q = null
    try { q = new URLSearchParams(window.location.search) } catch {}
    const demo = q && q.get('demo')
    if (demo) { setTab('demo'); setSel(demo) }
    const over = (e) => { if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) { e.preventDefault(); setDragging(true) } }
    const leave = (e) => { if (!e.relatedTarget) setDragging(false) }
    const drop = (e) => {
      if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return
      e.preventDefault(); setDragging(false)
      const f = Array.from(e.dataTransfer.files).find(x => /^audio\//.test(x.type) || /\.(mp3|wav|m4a|aac|flac|ogg|opus|aif|aiff|webm)$/i.test(x.name))
      if (f) { setTab('record'); pickFile(f) } else say('that is not an audio file', true)
    }
    window.addEventListener('dragover', over); window.addEventListener('dragleave', leave); window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragover', over); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop)
      teardown(); stopSync()
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // ---- what goes under the voice
  async function openList(which) {
    if (pick === which) { setPick(null); return }
    setPick(which); setItems(null); setPlOpen(null)
    try {
      let st = stations
      if (!st) { const r = await fetch('/cc/listen'); const d = await r.json(); st = d.stations || []; setStations(st) }
      if (which === 'own') {
        const r = await fetch('/cc/listen/station?id=own'); const d = await r.json()
        setItems(r.ok ? (d.items || []) : [])
      } else {
        setItems(st.filter(s => s.kind !== 'own' && s.id !== 'own' && s.id !== 'mix'))
        if (which === 'orfeo') find(q, false)
      }
    } catch { setItems([]) }
  }
  // the orfeo library: his own music first (in the brain, free, as he types), YouTube through his account on the press
  const findSeq = useRef(0)
  async function find(words, live) {
    const n = ++findSeq.current
    if (live) setFinding(true)
    try {
      const r = await fetch(`/cc/take/find?q=${encodeURIComponent(words || '')}&live=${live ? 1 : 0}`)
      const d = await r.json()
      if (n === findSeq.current) setFound(r.ok && d.ok ? d : { library: [], recent: [], shortcuts: [], live: { ok: false, items: [], why: d.error || String(r.status) } })
    } catch { if (n === findSeq.current) setFound(f => f || { library: [], recent: [], shortcuts: [] }) }
    if (live) setFinding(false)
  }
  useEffect(() => {
    if (pick !== 'orfeo') return
    const t = setTimeout(() => find(q, false), 220)
    return () => clearTimeout(t)
  }, [q])   // eslint-disable-line react-hooks/exhaustive-deps
  async function choosePick(it) {
    if (it.k === 'file') { chooseOwn(it); return }
    if (it.embed === false) { say(`${it.title}: ${it.why}. Drop the file instead if you have it.`, true); return }
    if (it.embed == null) {
      say('checking that YouTube lets it play here')
      try {
        const r = await fetch(`/cc/take/find?check=${encodeURIComponent(it.id)}`); const d = await r.json()
        if (r.ok && d.ok && d.embed === false) { say(`${it.title}: ${d.why}. Drop the file instead if you have it.`, true); return }
        if (d && d.dur && !it.dur) it = { ...it, dur: d.dur }
      } catch {}
    }
    chooseYT(it)
  }
  async function openPlaylist(s) {
    setPlOpen({ ...s, items: null })
    try { const r = await fetch(`/cc/listen/station?id=${encodeURIComponent(s.id)}`); const d = await r.json(); setPlOpen({ ...s, items: d.items || [] }) } catch { setPlOpen({ ...s, items: [] }) }
  }
  function ctxNow() {
    const a = A.current
    if (!a.ctx) { const C = window.AudioContext || window.webkitAudioContext; a.ctx = new C({ latencyHint: 'interactive' }) }
    return a.ctx
  }
  function dropPlayer() { const a = A.current; try { if (a.yt) a.yt.destroy() } catch {} a.yt = null }
  async function chooseOwn(it) {
    dropPlayer(); setPhase('loading'); say(`loading ${it.title}`)
    try {
      const r = await fetch(`/cc/listen/file?n=${encodeURIComponent(it.n)}`)
      if (!r.ok) throw new Error(r.status)
      const buf = await ctxNow().decodeAudioData(await r.arrayBuffer())
      A.current.trackBuf = buf
      setUnder({ kind: 'own', n: it.n, title: it.title, artist: it.artist, seconds: buf.duration, mine: true }); setPick(null); say('')
    } catch { say(`could not load ${it.title}`, true) }
    setPhase('idle')
  }
  async function chooseYT(it) {
    dropPlayer(); A.current.trackBuf = null
    setUnder({ kind: 'embed', video_id: it.id, title: it.title, artist: it.artist, dur: it.dur, ready: false }); setPick(null)
    say('loading the player')
  }
  useEffect(() => {
    if (under.kind !== 'embed' || under.ready || !ytRecEl.current) return
    let live = true
    const el = document.createElement('div'); ytRecEl.current.innerHTML = ''; ytRecEl.current.appendChild(el)
    makePlayer(el, under.video_id, (s) => { A.current.ytState = s; if (s === 0 && phaseRef.current === 'rec') A.current.endAt = A.current.ctx && A.current.ctx.currentTime }).then(p => {
      if (!live) { try { p.destroy() } catch {} return }
      A.current.yt = p; setUnder(u => ({ ...u, ready: true })); say('')
    }).catch(e => { if (live) say(e.message, true) })
    return () => { live = false }
  }, [under.kind, under.video_id])   // eslint-disable-line react-hooks/exhaustive-deps
  async function pickFile(f) {
    if (phaseRef.current !== 'idle') return
    dropPlayer(); setPhase('loading'); say(`reading ${f.name}`)
    try {
      const raw = await f.arrayBuffer()
      const buf = await ctxNow().decodeAudioData(raw.slice(0))
      A.current.trackBuf = buf
      say('keeping the track on the box so the demo can go over it')
      const r = await fetch('/cc/take/backing', { method: 'POST', headers: { 'Content-Type': f.type || 'application/octet-stream', 'X-Take-Name': encodeURIComponent(f.name) }, body: raw })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || r.status)
      setUnder({ kind: 'file', name: f.name, title: f.name.replace(/\.[^.]+$/, ''), backing: d.id, seconds: buf.duration, mine: false }); setPick(null); say('')
    } catch (e) { say(`could not use ${f.name}: ${e.message || e}`, true) }
    setPhase('idle')
  }
  function again(t) {
    const o = t.over || {}
    setTab('record'); setRead(t.page && t.page.lines ? { set: t.page.lines.set, group: t.page.lines.group } : null)
    if (o.kind === 'own') chooseOwn({ n: o.n, title: o.title, artist: o.artist })
    else if (o.kind === 'embed') chooseYT({ id: o.video_id, title: o.title, artist: o.artist })
    else if (o.kind === 'file' && t.demo && t.demo.versions) {
      const bed = t.demo.versions[t.demo.versions.length - 1].bed
      const rel = bed && bed.includes('/backing/') ? 'backing/' + bed.split('/backing/')[1] : null
      if (rel) fetch(fileUrl(rel)).then(r => r.arrayBuffer()).then(b => ctxNow().decodeAudioData(b)).then(buf => {
        A.current.trackBuf = buf; setUnder({ kind: 'file', name: o.name, title: o.title, backing: o.backing, seconds: buf.duration, mine: !!o.mine })
      }).catch(() => say('the track did not load; drop it again', true))
    } else setUnder({ kind: 'none' })
  }

  // ---- record
  function teardown() {
    const a = A.current
    a.capturing = false
    try { if (a.raf) cancelAnimationFrame(a.raf) } catch {}
    try { if (a.pairTimer) clearInterval(a.pairTimer) } catch {}
    try { (a.sources || []).forEach(s => s.stop()) } catch {}
    a.sources = []
    for (const k of ['src', 'recIn', 'proc', 'mute', 'analyser']) { try { if (a[k]) a[k].disconnect() } catch {} a[k] = null }
    try { if (a.stream) a.stream.getTracks().forEach(t => t.stop()) } catch {}
    a.stream = null
    try { if (a.yt && a.yt.pauseVideo && phaseRef.current === 'rec') a.yt.pauseVideo() } catch {}
  }
  function latency(ctx) {
    try { const v = JSON.parse(localStorage.getItem(LS_LAT) || 'null'); if (v && typeof v.ms === 'number') return { ms: v.ms, source: v.source } } catch {}
    return { ms: Math.round(1000 * ((ctx.outputLatency || 0) + (ctx.baseLatency || 0))), source: 'browser-reported output' }
  }
  async function record() {
    if (phaseRef.current !== 'idle') return
    if (under.kind === 'embed' && !A.current.yt) { say('the player is still loading', true); return }
    say(''); setPhase('arming')
    try { const L = listener(); if (L && L.toggle) L.toggle(false) } catch {}
    try { if (audioRef.current) audioRef.current.pause() } catch {}
    stopSync()
    const a = A.current
    let ctx, stream
    try {
      if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) throw new Error('this browser cannot record')
      ctx = ctxNow(); if (ctx.state !== 'running') await ctx.resume()
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } }) } catch { throw new Error('the microphone is not allowed for this page: allow it in the address bar, then press again') }
    } catch (e) { setPhase('idle'); say(e.message || String(e), true); return }
    a.stream = stream
    const tr = stream.getAudioTracks()[0]
    const st = (tr && tr.getSettings && tr.getSettings()) || {}
    const ch = Math.min(2, Math.max(1, st.channelCount || 1))
    a.ch = ch; a.chunks = []; a.mic = (tr && tr.label) || ''; a.pairs = []; a.endAt = null; a.warned = false
    a.src = ctx.createMediaStreamSource(stream); a.recIn = ctx.createGain(); a.src.connect(a.recIn)
    a.proc = ctx.createScriptProcessor(4096, ch, ch); a.proc.channelCount = ch; a.proc.channelCountMode = 'explicit'
    a.mute = ctx.createGain(); a.mute.gain.value = 0
    a.recIn.connect(a.proc); a.proc.connect(a.mute); a.mute.connect(ctx.destination)
    a.analyser = ctx.createAnalyser(); a.analyser.fftSize = 2048; a.src.connect(a.analyser)
    a.capturing = true
    const started = new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('the microphone sent nothing')), 4000)
      a.proc.onaudioprocess = (e) => {
        if (!a.capturing) return
        const k = []; for (let c = 0; c < ch; c++) k.push(new Float32Array(e.inputBuffer.getChannelData(c)))
        a.chunks.push(k)
        if (a.chunks.length === 1) { clearTimeout(t); resolve(ctx.currentTime) }
      }
    })
    let t0
    try { t0 = await started } catch (e) { teardown(); setPhase('idle'); say(e.message, true); return }
    a.t0 = t0; a.sources = []
    a.take = { rate: ctx.sampleRate, ch, latency: latency(ctx) }
    if (under.kind !== 'none') {
      const M = t0 + LEAD
      const mk = chirpSamples(ctx.sampleRate, CHIRP.amp)
      const mb = ctx.createBuffer(1, mk.length, ctx.sampleRate); mb.getChannelData(0).set(mk)
      const s = ctx.createBufferSource(); s.buffer = mb; s.connect(a.recIn); s.start(M)   // the sync mark: into the take only
      a.sources.push(s); a.take.M = M
      const T = M + LEAD
      if (a.trackBuf && (under.kind === 'own' || under.kind === 'file')) {
        const b = ctx.createBufferSource(); b.buffer = a.trackBuf; b.connect(ctx.destination); b.start(T)
        a.sources.push(b); a.take.T = T; a.endAt = T + a.trackBuf.duration
      } else if (under.kind === 'embed' && a.yt) {
        try { a.yt.seekTo(0, true); a.yt.pauseVideo() } catch {}
        setTimeout(() => { try { a.yt.playVideo() } catch {} }, Math.max(0, (T - ctx.currentTime) * 1000))
        a.pairTimer = setInterval(() => {
          try { if (a.ytState === 1) a.pairs.push([ctx.currentTime, a.yt.getCurrentTime()]) } catch {}
        }, 200)
      }
    }
    setPhase('rec')
    const buf = new Float32Array(a.analyser.fftSize)
    const tick = () => {
      if (!a.capturing) return
      const now = ctx.currentTime
      a.analyser.getFloatTimeDomainData(buf)
      const { peakDb, rmsDb } = levels(buf)
      const root = rootRef.current
      if (root) { root.style.setProperty('--lv', meterPos(rmsDb + 6, -48).toFixed(3)); root.style.setProperty('--pk', meterPos(peakDb).toFixed(3)) }
      if (clockRef.current) clockRef.current.textContent = clock(now - t0)
      if (now - t0 > MAX_S) { stop('twenty minutes: the take stopped by itself'); return }
      if (a.endAt && now > a.endAt + 1.5) { stop('the track ended'); return }
      if (a.take.M && a.yt && !a.pairs.length && !a.warned && now - t0 > 6) {
        a.warned = true
        say('the video has not started in your headphones (YouTube may want a sign-in, or the artist blocks embedding): stop, then pick another track or open it on YouTube once', true)
      }
      a.raf = requestAnimationFrame(tick)
    }
    a.raf = requestAnimationFrame(tick)
  }
  async function stop(why) {
    const a = A.current
    if (phaseRef.current !== 'rec' || a.stopping) return
    a.stopping = true
    const ctx = a.ctx, tk = a.take, chunks = a.chunks, ch = a.ch, mic = a.mic, rawPairs = a.pairs || []
    teardown(); a.chunks = []; a.stopping = false
    try { if (a.yt) a.yt.pauseVideo() } catch {}
    const root = rootRef.current
    if (root) { root.style.setProperty('--lv', '0'); root.style.setProperty('--pk', '0') }
    const chans = joinChunks(chunks, ch)
    const seconds = chans[0].length / tk.rate
    if (seconds < 0.3) { setPhase('idle'); say('nothing was recorded', true); return }
    setPhase('saving'); say(typeof why === 'string' ? `${why}; keeping it` : 'keeping it')
    let over = { kind: 'none' }
    const lat = tk.latency.ms / 1000
    if (under.kind !== 'none') {
      const f = findChirp(chans[0], tk.rate, 0, Math.min(seconds, 3))
      const marker = f && f.t != null ? f.t : null
      const base = { title: under.title || under.name, artist: under.artist || '', mine: !!under.mine, marker_in_take_s: marker,
        marker_clarity: f ? Math.round(f.clarity * 10) / 10 : 0, latency_ms: tk.latency.ms, latency_source: tk.latency.source }
      if (under.kind === 'embed') {
        const all = pairsInTake(rawPairs, marker, tk.M, lat)
        const fit = fitLine(all)
        const step = Math.max(1, Math.ceil(all.length / 24))
        const pairs = all.filter((_, i) => i % step === 0 || i === all.length - 1)
        over = { ...base, kind: 'embed', video_id: under.video_id, start_s: all.length ? all[0][1] : 0, pairs,
          embed_start_in_take_s: all.length ? all[0][0] : null, pairs_all: all.length, fit_rate: fit ? Math.round(fit.rate * 1e6) / 1e6 : null,
          fit_res_ms: fit ? fit.maxResMs : null }
      } else {
        over = { ...base, kind: under.kind, n: under.n || null, backing: under.backing || null, name: under.name || null,
          seconds: Math.round((under.seconds || 0) * 1000) / 1000,
          track_start_in_take_s: marker != null && tk.T ? Math.round((marker + (tk.T - tk.M) + lat) * 10000) / 10000 : null }
      }
    }
    let lines = null
    if (read) {
      const s = ((data && data.lines) || []).find(x => x.id === read.set)
      const g = s && s.groups.find(x => x.n === read.group)
      if (g) lines = { set: s.id, group: g.n, bar: g.bar, text: g.lines.join(' / ').slice(0, 280) }
    }
    const name = lines ? `${lines.set} line ${lines.group}` : (over.title || 'take')
    const wav = encodeWav(chans, tk.rate, 24)
    const meta = { name, over, page: { surface: 'take', lines, mic: String(mic).slice(0, 80), channels: ch, rate: tk.rate, browser_seconds: Math.round(seconds * 1000) / 1000 } }
    try {
      const r = await fetch('/cc/booth/take', { method: 'POST', headers: { 'Content-Type': 'audio/wav', 'X-Booth-Meta': encodeURIComponent(JSON.stringify(meta)) }, body: new Blob([wav], { type: 'audio/wav' }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || `the console answered ${r.status}`)
      say('kept. The demo comes back by itself in a few minutes, on Demo.')
      if (lines && read) {
        const s = ((data && data.lines) || []).find(x => x.id === read.set)
        if (s && s.groups.some(x => x.n === read.group + 1)) setRead({ ...read, group: read.group + 1 })
      }
      load()
    } catch (e) {
      const url = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }))
      A.current.unsaved = url
      say(`not kept on the box (${e.message}). Download it from this tab: `, true)
    }
    setPhase('idle')
  }

  // ---- the demo: hear it, choose by ear, keep / again / drop
  function playDemo(t, tr) {
    const el = audioRef.current
    const key = `${t.file}:${tr.id}`
    if (!el) return
    if (t.over && t.over.kind === 'embed') { syncPlay(t, tr); return }
    if (playing === key && !el.paused) { el.pause(); setPlaying(null); return }
    el.src = fileUrl(tr.mix || tr.voice); el.currentTime = 0
    el.play().then(() => setPlaying(key)).catch(() => setRowMsg(m => ({ ...m, [t.file]: 'this browser could not play it' })))
    setTreat(x => ({ ...x, [t.file]: tr.id }))
  }
  function stopSync() {
    const a = A.current
    try { if (a.syncTimer) clearInterval(a.syncTimer) } catch {}
    a.syncTimer = null
    try { if (a.demoYt) a.demoYt.destroy() } catch {}
    a.demoYt = null
  }
  async function syncPlay(t, tr) {
    const a = A.current, el = audioRef.current
    const key = `${t.file}:${tr.id}`
    if (playing === key) { stopSync(); el.pause(); setPlaying(null); return }
    stopSync(); el.pause()
    setTreat(x => ({ ...x, [t.file]: tr.id }))
    const ver = t.demo.versions[t.demo.versions.length - 1]
    const map = ver.sync || { rate: 1, video_at_voice_0: t.over.start_s || 0 }
    el.src = fileUrl(tr.voice); el.currentTime = 0
    if (!ytDemoEl.current) return
    const host = document.createElement('div'); ytDemoEl.current.innerHTML = ''; ytDemoEl.current.appendChild(host)
    setSync({ file: t.file, text: 'loading the artist\'s video' })
    let p
    try { p = await makePlayer(host, t.over.video_id, (s) => { if (s !== 1) { try { el.pause() } catch {} } }) } catch (e) { setSync({ file: t.file, text: e.message }); return }
    a.demoYt = p
    const v0 = map.video_at_voice_0 || 0
    try { p.seekTo(Math.max(0, v0), true); p.playVideo() } catch {}
    setPlaying(key)
    const drift = []
    const tally = { seeks: 0, nudges: 0, holds: 0, rateSum: 0 }
    window.__takeDrift = drift; window.__takeSync = tally    // read by the drift measurement (DEMO-1 report)
    a.syncTimer = setInterval(() => {
      let vt = 0, st = -1
      try { vt = p.getCurrentTime(); st = p.getPlayerState() } catch { return }
      if (st !== 1) return
      const s = syncStep(vt, el.currentTime, map)
      if (s.action === 'wait') { if (!el.paused) el.pause(); return }
      if (el.paused) { el.currentTime = Math.max(0, s.target); el.play().catch(() => {}); return }
      drift.push(s.drift * 1000)
      if (s.action === 'seek') { el.currentTime = s.target; el.playbackRate = 1; tally.seeks++ } else { el.playbackRate = s.rate; if (s.action === 'nudge') tally.nudges++; else tally.holds++; tally.rateSum += s.rate }
      if (drift.length % 8 === 0) {
        const d = driftStats(drift.slice(-120))
        setSync({ file: t.file, text: `in sync: off by ${d.meanAbs} ms on average, ${d.p95} ms at worst most of the time (last ${Math.round(d.n / 4)} s)` })
      }
    }, 250)
  }
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    const end = () => setPlaying(null)
    el.addEventListener('ended', end)
    return () => el.removeEventListener('ended', end)
  }, [])
  async function verdict(t, word) {
    const ver = t.demo && t.demo.versions[t.demo.versions.length - 1]
    const tr = treat[t.file] || (ver && ver.first) || 'dry'
    setRowMsg(m => ({ ...m, [t.file]: '' }))
    try {
      const r = await fetch('/cc/take/verdict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ take: t.file, word, treatment: word === 'keep' ? tr : null }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || r.status)
      try { audioRef.current.pause() } catch {}
      stopSync(); setPlaying(null)
      const fresh = await load()
      if (word === 'again') again(t)
      if (word === 'keep' && fresh) { const nt = fresh.takes.find(x => x.file === t.file); if (nt && nt.step.at === 'ask') { setTab('ask'); setSel(t.file) } }
    } catch (e) { setRowMsg(m => ({ ...m, [t.file]: `not saved: ${e.message}` })) }
  }

  // ---- ask
  async function ask(t, word, extra) {
    setRowMsg(m => ({ ...m, [t.file]: '' }))
    try {
      const r = await fetch('/cc/take/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ take: t.file, word, ...(extra || {}) }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) throw new Error(d.error || r.status)
      load()
    } catch (e) { setRowMsg(m => ({ ...m, [t.file]: e.message })) }
  }
  const formOf = (t) => forms[t.file] || { to: (t.ask && t.ask.to) || '', subject: (t.ask && t.ask.subject) || '', body: (t.ask && t.ask.body) || '' }
  const setForm = (t, k, v) => setForms(f => ({ ...f, [t.file]: { ...formOf(t), [k]: v } }))

  // ---- what shows
  const takes = (data && data.takes) || []
  const counts = stripCounts(takes)
  const sets = (data && data.lines) || []
  const readSet = read && sets.find(s => s.id === read.set)
  const readGroup = readSet && readSet.groups.find(g => g.n === read.group)
  const rec = phase === 'rec'
  const busy = phase !== 'idle'
  const demoTakes = takes.filter(t => ['demo', 'done', 'record'].includes(t.step.at) || t.step.state === 'kept')
  const askTakes = takes.filter(t => t.step.at === 'ask' || t.step.state === 'answered')
  const againTakes = takes.filter(t => t.step.state === 'again').slice(0, 4)
  const film = (data && data.films && data.films[0]) || null

  const strip = () => (
    <nav className="tk-strip" aria-label="steps">
      {[['record', 'record', againTakes.length], ['demo', 'demo', counts.ready + counts.making], ['ask', 'ask', counts.toAsk]].map(([id, label, n]) => (
        <button key={id} type="button" className={'tk-st' + (tab === id ? ' on' : '') + (n ? ' hot' : '')} onClick={() => setTab(id)} aria-pressed={tab === id}>
          {label}{n ? <b>{n}</b> : null}
        </button>
      ))}
    </nav>
  )

  function pickRow(it, i) {
    const off = it.embed === false
    const meta = [it.artist, it.dur ? clock(it.dur) : '', it.src].filter(Boolean).join(' · ')
    return (
      <button key={(it.id || it.n) + ':' + i} type="button" className={'tk-it' + (off ? ' off' : '')} aria-disabled={off}
        title={off ? it.why : undefined} onClick={() => choosePick(it)}>
        <span>{it.title}{off ? <em>{it.why}</em> : null}</span><small>{meta}</small>
      </button>
    )
  }
  function findPanel() {
    const f = found || {}
    const lib = f.library || [], rec = f.recent || [], sc = f.shortcuts || []
    const lv = f.live
    const shown = [...rec, ...lib, ...((lv && lv.items) || [])]
    const anyOff = shown.some(x => x.embed === false)
    const words = q.trim()
    return (
      <div className="tk-find" aria-label="orfeo library">
        <header><b>orfeo library</b><small>your account's music: your tracks, likes and playlists, then YouTube</small></header>
        <form className="tk-q" onSubmit={(e) => { e.preventDefault(); if (words) find(words, true) }}>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="a title or an artist" aria-label="search your music" autoFocus spellCheck={false} />
          <button type="submit" disabled={!words || finding}>{finding ? 'searching' : 'search YouTube'}</button>
        </form>
        {plOpen ? null : !words ? (
          <>
            {sc.length || (items && items.length) ? (
              <div className="tk-sc">
                {sc.map(s => <button key={s.id} type="button" onClick={() => openPlaylist({ id: s.id, name: s.name })}>from {s.name}</button>)}
                {items && items.length ? <button type="button" onClick={() => setPick('playlists')}>all {items.length} playlists</button> : null}
              </div>
            ) : null}
            {rec.length ? <><p className="tk-fl">recently used</p>{rec.map(pickRow)}</> : null}
          </>
        ) : (
          <>
            <p className="tk-fl">in your library{lib.length ? ` · ${lib.length}` : ''}</p>
            {lib.length ? lib.map(pickRow) : <p className="tk-note">Nothing in your tracks, likes or playlists has all of those words.</p>}
            {lv ? (
              <>
                <p className="tk-fl">on YouTube{lv.cached ? ' · from earlier today' : ''}</p>
                {lv.ok ? (lv.items.length ? lv.items.map(pickRow) : <p className="tk-note">YouTube found nothing for that.</p>) : <p className="tk-note">{lv.why}</p>}
              </>
            ) : <p className="tk-note">Not here? Press search YouTube{f.live_left == null ? '' : ` (${f.live_left} searches left today)`}.</p>}
          </>
        )}
        {plOpen ? (
          <div className="tk-list" aria-label={plOpen.name}>
            <button type="button" className="tk-it" onClick={() => setPlOpen(null)}><span>back to the search</span><small>{plOpen.name}</small></button>
            {plOpen.items === null ? <p className="tk-note">loading</p> : plOpen.items.filter(x => x.k === 'yt').map(it => pickRow({ ...it, src: '' }, it.id))}
          </div>
        ) : null}
        {anyOff ? (
          <div className="tk-grey">
            <span>Greyed out: embedding off (or blocked in most countries), so YouTube will not play it under your take.</span>
            <button type="button" onClick={() => fileRef.current && fileRef.current.click()}>drop the file instead</button>
          </div>
        ) : null}
      </div>
    )
  }
  function demoRow(t) {
    const open = sel === t.file || sel === t.demo_dir
    const ver = t.demo && t.demo.versions && t.demo.versions[t.demo.versions.length - 1]
    const chosen = treat[t.file] || (t.verdict && t.verdict.treatment) || (ver && ver.first)
    const isLine = t.page && t.page.lines
    return (
      <div key={t.file} className={'tk-row' + (open ? ' sel' : '')}>
        <button type="button" style={{ textAlign: 'left', minWidth: 0 }} onClick={() => setSel(open ? null : t.file)} aria-expanded={open}>
          <b>{t.title || t.name}</b>
          <small>{[ago(t.made), clock(t.seconds), underWord(t.over), isLine ? `bar ${t.page.lines.bar}` : ''].filter(Boolean).join(' · ')}</small>
        </button>
        <span className={'tk-tag ' + t.step.state}>{t.step.state}</span>
        {open ? (
          <div className="tk-panel">
            <small style={{ color: 'var(--text-dim)' }}>{t.step.say}</small>
            {ver ? (
              <>
                <div className="tk-tr" role="group" aria-label="treatments">
                  {ver.treatments.map(tr => (
                    <button key={tr.id} type="button" className={chosen === tr.id ? 'on' : ''} onClick={() => playDemo(t, tr)} aria-pressed={playing === `${t.file}:${tr.id}`}>
                      <Play on={playing === `${t.file}:${tr.id}`} />
                      <span>{tr.label}<small>{tr.mix ? 'over the track' : t.over && t.over.kind === 'embed' ? 'with the artist\'s video' : 'voice'}</small></span>
                    </button>
                  ))}
                </div>
                {t.over && t.over.kind === 'embed' ? <div className="tk-yt" ref={ytDemoEl} style={{ marginTop: 8 }} /> : null}
                {sync && sync.file === t.file ? <div className="tk-sync">{sync.text}</div> : null}
                <div className="tk-words">
                  <button type="button" className="tk-w keep" onClick={() => verdict(t, 'keep')}>keep {ver.treatments.find(x => x.id === chosen) ? ver.treatments.find(x => x.id === chosen).label : ''}</button>
                  <button type="button" className="tk-w" onClick={() => verdict(t, 'again')}>again</button>
                  <button type="button" className="tk-w" onClick={() => verdict(t, 'drop')}>drop</button>
                </div>
                <div className="tk-sync">{ver.v} · {ver.voice_s} s of voice · pitch untouched{ver.sync && ver.sync.pairs ? ` · embed clock from ${ver.sync.pairs} marks, ${ver.sync.residual_ms_max} ms scatter` : ''}</div>
              </>
            ) : null}
            {rowMsg[t.file] ? <div className="tk-word err">{rowMsg[t.file]}</div> : null}
          </div>
        ) : null}
      </div>
    )
  }

  function askRow(t) {
    const open = sel === t.file || sel === t.demo_dir || askTakes.length === 1
    const f = formOf(t)
    const st = t.step.state
    return (
      <div key={t.file} className={'tk-row' + (open ? ' sel' : '')}>
        <button type="button" style={{ textAlign: 'left', minWidth: 0 }} onClick={() => setSel(open ? null : t.file)}>
          <b>{t.over && (t.over.title || t.over.name)}</b>
          <small>{[t.over && t.over.artist, t.title || t.name, ago(t.made)].filter(Boolean).join(' · ')}</small>
        </button>
        <span className={'tk-tag ' + st}>{st}</span>
        {open ? (
          <div className="tk-panel">
            <small style={{ color: 'var(--text-dim)' }}>{t.step.say}</small>
            {st === 'to-ask' ? <div className="tk-words"><button type="button" className="tk-w keep" onClick={() => ask(t, 'draft')}>draft the message</button></div> : null}
            {st === 'drafted' || st === 'send-failed' ? (
              <form className="tk-form" onSubmit={(e) => { e.preventDefault(); ask(t, 'send', f) }}>
                <label>to {t.ask.contact && t.ask.contact.found_on ? <span className="tk-found">(found on {t.ask.contact.found_on}: "{t.ask.contact.line}")</span> : <span className="tk-found">({(t.ask.contact && t.ask.contact.why) || 'type their address'})</span>}</label>
                <input value={f.to} onChange={(e) => setForm(t, 'to', e.target.value)} placeholder="their address" aria-label="to" />
                <label>subject</label>
                <input value={f.subject} onChange={(e) => setForm(t, 'subject', e.target.value)} aria-label="subject" />
                <label>message {t.ask.attach ? <span className="tk-found">(the demo goes with it: {String(t.ask.attach).split('/').pop()})</span> : null}</label>
                <textarea value={f.body} onChange={(e) => setForm(t, 'body', e.target.value)} aria-label="message" />
                <div className="tk-words">
                  <button type="submit" className="tk-w keep" disabled={!hasOffer(f.body) || !f.to}>send from hello@hbar.systems</button>
                  {!hasOffer(f.body) ? <span className="tk-found" style={{ alignSelf: 'center' }}>write your offer where it says [your offer]</span> : null}
                </div>
              </form>
            ) : null}
            {st === 'sent' ? (
              <div className="tk-words">
                <span className="tk-found" style={{ alignSelf: 'center' }}>their answer:</span>
                {['yes', 'no', 'talking'].map(w => <button key={w} type="button" className="tk-w" onClick={() => ask(t, 'answer', { answer: w })}>{w}</button>)}
              </div>
            ) : null}
            {rowMsg[t.file] ? <div className="tk-word err">{rowMsg[t.file]}</div> : null}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <>
      <Head><title>Take · orfeo</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className={'tk' + (rec ? ' rec' : '')} ref={rootRef}>
        <div className="tk-in">
          <div className="tk-h"><h1><span className="tk-eye">orfeo</span>Take</h1>{strip()}</div>

          {tab === 'record' ? (
            <>
              <section className="tk-sec" aria-label="under your voice">
                <p className="tk-lab">under your voice</p>
                <div className="tk-chips">
                  <button type="button" className={'tk-chip' + (under.kind === 'none' && !pick ? ' on' : '')} disabled={busy} onClick={() => { dropPlayer(); A.current.trackBuf = null; setUnder({ kind: 'none' }); setPick(null) }}>nothing</button>
                  <button type="button" className={'tk-chip' + (under.kind === 'own' || pick === 'own' ? ' on' : '')} disabled={busy} onClick={() => openList('own')}>my tracks</button>
                  <button type="button" className={'tk-chip' + (under.kind === 'embed' || pick === 'orfeo' || pick === 'playlists' ? ' on' : '')} disabled={busy} onClick={() => openList('orfeo')}>orfeo library</button>
                  <button type="button" className={'tk-chip' + (under.kind === 'file' ? ' on' : '')} disabled={busy} onClick={() => fileRef.current && fileRef.current.click()}>a file</button>
                  <input ref={fileRef} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files && e.target.files[0]; if (f) pickFile(f); e.target.value = '' }} />
                </div>
                {pick === 'own' ? (
                  <div className="tk-list" aria-label="my tracks">
                    {items === null ? <p className="tk-note">loading</p> : !items.length ? <p className="tk-note">No own tracks on this brain yet.</p> : items.map(it => (
                      <button key={it.n} type="button" className="tk-it" onClick={() => chooseOwn(it)}><span>{it.title}</span><small>{it.dur ? clock(it.dur) : ''}</small></button>
                    ))}
                  </div>
                ) : null}
                {pick === 'orfeo' ? findPanel() : null}
                {pick === 'playlists' ? (
                  <div className="tk-list" aria-label="my playlists">
                    {items === null ? <p className="tk-note">loading</p> : !items.length ? <p className="tk-note">No playlists on this brain yet.</p> : plOpen ? (
                      <>
                        <button type="button" className="tk-it" onClick={() => setPlOpen(null)}><span>back to the playlists</span><small>{plOpen.name}</small></button>
                        {plOpen.items === null ? <p className="tk-note">loading</p> : plOpen.items.filter(x => x.k === 'yt').map(it => (
                          <button key={it.id} type="button" className="tk-it" onClick={() => chooseYT(it)}><span>{it.title}</span><small>{[it.artist, it.dur ? clock(it.dur) : ''].filter(Boolean).join(' · ')}</small></button>
                        ))}
                      </>
                    ) : items.map(s => (
                      <button key={s.id} type="button" className="tk-it" onClick={() => openPlaylist(s)}><span>{s.name}</span><small>{s.count}</small></button>
                    ))}
                  </div>
                ) : null}
                {under.kind !== 'none' ? (
                  <div className="tk-under">
                    {under.kind === 'embed' ? <div className="tk-yt" ref={ytRecEl} /> : null}
                    <div>
                      <b>{under.title || under.name}</b>
                      <small>{[under.artist, under.seconds ? clock(under.seconds) : under.dur ? clock(under.dur) : '', under.kind === 'embed' ? 'plays from YouTube in your headphones; nothing is downloaded' : under.kind === 'own' ? 'your track' : 'kept on the box for the demo'].filter(Boolean).join(' · ')}</small>
                      {under.kind === 'file' ? (
                        <button type="button" className={'tk-mine' + (under.mine ? ' on' : '')} onClick={() => setUnder(u => ({ ...u, mine: !u.mine }))} aria-pressed={!!under.mine}>
                          <i>{under.mine ? '✓' : ''}</i>this track is mine (no ask needed)
                        </button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </section>

              {sets.length ? (
                <section className="tk-sec" aria-label="lines">
                  <p className="tk-lab">lines to read</p>
                  <div className="tk-chips">
                    <button type="button" className={'tk-chip' + (!read ? ' on' : '')} disabled={busy} onClick={() => setRead(null)}>none</button>
                    {sets.map(s => <button key={s.id} type="button" className={'tk-chip' + (read && read.set === s.id ? ' on' : '')} disabled={busy} onClick={() => setRead({ set: s.id, group: s.groups[0].n })}>{s.title || s.id}</button>)}
                  </div>
                  {readGroup ? (
                    <div className="tk-read">
                      <nav>
                        <button type="button" disabled={busy || readGroup.n === readSet.groups[0].n} onClick={() => setRead({ ...read, group: read.group - 1 })}>back</button>
                        <span>group {readGroup.n} of {readSet.groups.length} · lands on bar {readGroup.bar}{readSet.treatment === 'phone' ? ' · telephone' : ''}</span>
                        <button type="button" disabled={busy || !readSet.groups.some(g => g.n === readGroup.n + 1)} onClick={() => setRead({ ...read, group: read.group + 1 })}>next</button>
                      </nav>
                      {readGroup.lines.map((l, i) => <p key={i}>{l}</p>)}
                    </div>
                  ) : null}
                </section>
              ) : null}

              {againTakes.length ? (
                <section className="tk-sec" aria-label="again">
                  <p className="tk-lab">again</p>
                  <div className="tk-chips">{againTakes.map(t => <button key={t.file} type="button" className="tk-chip" disabled={busy} onClick={() => again(t)}>{t.title || t.name}</button>)}</div>
                </section>
              ) : null}

              <p className="tk-hp">{HEADPHONES}</p>
              <div className="tk-rec">
                <button type="button" className="tk-btn" onClick={rec ? () => stop() : record} disabled={phase === 'arming' || phase === 'saving' || phase === 'loading' || (under.kind === 'embed' && !under.ready)}
                  aria-label={rec ? 'stop' : 'record'} aria-pressed={rec}><i /></button>
                <div className="tk-clock" ref={clockRef}>0:00</div>
                <div className="tk-meter" aria-hidden="true"><i /></div>
                <div className={'tk-word' + (msg.err ? ' err' : '')} role="status">{msg.text}{A.current.unsaved && msg.err ? <a href={A.current.unsaved} download="take.wav">take.wav</a> : null}</div>
                <div className="tk-word">laptop mic or phone; press, then press again to stop</div>
              </div>
            </>
          ) : null}

          {tab === 'demo' ? (
            <section className="tk-sec" aria-label="demos">
              {data === null ? <p className="tk-empty">loading</p> : null}
              {data === false ? <p className="tk-empty">The takes did not load.</p> : null}
              {data && !demoTakes.length ? <p className="tk-empty">No takes yet. Record one: the demo comes back here by itself.</p> : null}
              {demoTakes.map(t => demoRow(t))}
              {film && (film.cuts.length || film.choices.length) ? (
                <div className="tk-film">
                  <p className="tk-lab" style={{ marginTop: 26 }}>the film, with your spoken lines</p>
                  {film.cuts.length ? (
                    <>
                      <video controls preload="none" src={fileUrl(film.cuts[film.cuts.length - 1].file)} />
                      <div className="tk-sync">{film.cuts[film.cuts.length - 1].v}: {film.cuts[film.cuts.length - 1].placed.map(p => `group ${p.group} on bar ${p.bar}`).join(', ')}; the release file is untouched</div>
                    </>
                  ) : <p className="tk-empty">Read a group on Record: the cut with your voice on its bars appears here.</p>}
                  {film.choices.length ? (
                    <>
                      <p className="tk-lab" style={{ marginTop: 18 }}>more cuts, from the film's own shots</p>
                      <ol>{film.choices.map(c => <li key={c.id}>{c.say}</li>)}</ol>
                    </>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}

          {tab === 'ask' ? (
            <section className="tk-sec" aria-label="asks">
              {data && !askTakes.length ? <p className="tk-empty">Nothing to ask yet. Keep a demo made over someone else's track and its ask shows here.</p> : null}
              {askTakes.map(t => askRow(t))}
            </section>
          ) : null}
        </div>
        <audio ref={audioRef} preload="none" hidden />
        {dragging ? <div className="tk-drop"><div>Drop a track to record over</div></div> : null}
      </div>
    </>
  )
}
