import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// The systems board (BOARD-3, 2026-11-12). hbar: "I SHOULD BE ABLE TO WRITE AND SEND RIGHT THERE AND THEN
// (SAY OR SPEAK IT)". One tile per system of the owner's world (GET /cc/systems, scripts/cc/cc_systems.py).
// At rest a tile is its name and one rust number: the things moving there now (running jobs, open court
// items, thoughts of the last 24 h). A press opens it in place (260 ms): up to seven plain lines of at most
// eight words, each with one link; "+N" opens the rest in place, grouped by kind with counts.
// One control per tile: a line to write in ("say it here") with a mic mark inside it.
//   Enter: POST /cc/systems/thread gives the system's one standing thread (made once, then kept), then the
//   page makes the chat page's own call, POST /cc/chat {message, new: false, thread}, with the console's
//   session; the answer shows under the tile as a card, "continue" opens /talk?thread=<id>.
//   Mic: tap to record (MediaRecorder), tap to stop, tap to send: POST /cc/systems/voice?system=<id> keeps
//   the clip as in/<date>/memo_<id>_<stamp>.<ext>, where the memo tape takes it.
// Updates: one light request every three seconds, none while the tab is hidden (the /board pattern).
// Look: the chat's sand skin, no borders, no black, nothing moves on its own.

const CSS = `
.sy{--bg:#efe3cf;--surface:#e6d6bd;--ink:#2b2116;--dim:#54473a;--muted:#7a6a55;--rust:#a8452b;--ease:cubic-bezier(.2,.7,.2,1);
  background:var(--bg);color:var(--ink);min-height:calc(100vh - var(--nav-h, 52px));font:400 16px/1.5 system-ui,-apple-system,sans-serif;box-sizing:border-box}
.sy *{box-sizing:border-box}
.sy :where(a){color:inherit}
.sy :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.sy :focus-visible{outline:2px solid var(--rust);outline-offset:3px;border-radius:6px}
.sy-main{max-width:1240px;margin:0 auto;padding:48px 40px 72px}
.sy-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:6px 28px;align-items:start}
.sy-t{border-radius:14px;transition:background-color 260ms var(--ease);min-width:0}
.sy-t.open,.sy-t.carded{background:var(--surface)}
.sy-th{display:flex;align-items:baseline;gap:12px;width:100%;padding:12px 16px}
.sy-nm{font:400 26px/1.2 Lora,Georgia,serif;overflow-wrap:anywhere}
.sy-n{font-size:16px;color:var(--rust);font-variant-numeric:tabular-nums}
.sy-q .sy-nm{color:var(--muted);opacity:.62}.sy-q.open .sy-nm,.sy-th:hover .sy-nm{opacity:1;color:var(--ink)}
.sy-fold{display:grid;grid-template-rows:0fr;visibility:hidden;transition:grid-template-rows 260ms var(--ease),visibility 0s linear 260ms}
.sy-fold.on{grid-template-rows:1fr;visibility:visible;transition:grid-template-rows 260ms var(--ease),visibility 0s}
.sy-fi{overflow:hidden;min-height:0}
.sy-lines{list-style:none;margin:0;padding:0 16px;max-width:58ch}
.sy-ln{display:flex;align-items:baseline;gap:8px;padding:5px 0;color:var(--dim)}
.sy-ln span{flex:1}
.sy-ln.run span::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--rust);margin:0 9px 2px 0;vertical-align:middle}
.sy-m{display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;color:var(--muted);opacity:.6;border-radius:50%;flex:none;transition:opacity 200ms var(--ease),color 200ms var(--ease)}
.sy-m:hover,.sy-m:focus-visible{opacity:1;color:var(--rust)}
.sy-m svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
.sy-more{font-size:13px;color:var(--muted);padding:4px 16px}.sy-more:hover,.sy-more.on{color:var(--rust)}
.sy-gh{margin:6px 0 0;padding:0 16px;font-size:13px;color:var(--muted);letter-spacing:.04em}.sy-gh b{font-weight:400;color:var(--rust);margin-left:4px}
.sy-say{position:relative;margin:8px 16px 14px}
.sy-say input{width:100%;font:inherit;font-size:15px;color:var(--ink);background:var(--bg);border:0;border-radius:999px;padding:9px 42px 9px 16px;outline:none;-webkit-appearance:none;appearance:none}
.sy-say input::placeholder{color:var(--muted);opacity:.85}.sy-say input:focus{box-shadow:0 0 0 1.5px var(--rust)}
.sy-say .sy-m{position:absolute;right:8px;top:50%;transform:translateY(-50%)}
.sy-say .sy-m.rec{opacity:1;color:var(--rust);animation:sy-pulse 1.2s ease-in-out infinite}
.sy-say .sy-m.ready{opacity:1;color:var(--rust)}
@keyframes sy-pulse{50%{opacity:.45}}
.sy-card{margin:0 16px 14px;padding:10px 14px;border-radius:12px;background:var(--bg);font-size:15px;color:var(--dim);max-width:58ch}
.sy-card p{margin:0 0 6px;white-space:pre-wrap;overflow-wrap:anywhere}
.sy-card .me{color:var(--muted);font-size:13px}
.sy-card .err{color:var(--rust)}
.sy-card a{color:var(--rust);font-size:13px;text-decoration-thickness:1px;text-underline-offset:3px}
.sy-note{color:var(--muted);font-size:14px;margin:24px 16px}
@media(max-width:700px){.sy-main{padding:22px 14px 48px}.sy-grid{grid-template-columns:1fr;gap:2px}.sy-th{padding:9px 12px}.sy-nm{font-size:23px}
  .sy-lines{padding:0 12px}.sy-say{margin:8px 12px 12px}.sy-gh,.sy-more{padding-left:12px;padding-right:12px}.sy-card{margin:0 12px 12px}}
@media(prefers-reduced-motion:reduce){.sy-fold,.sy-t{transition:none!important}.sy-say .sy-m.rec{animation:none}}
`

const ICON = {
  link: <path d="M6 3h7v7M13 3 4 12" />,
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
  send: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>

const postJson = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const plain = (s) => String(s || '').replace(/<!--[\s\S]*?-->/g, '').replace(/<choices>[\s\S]*?<\/choices>/g, '').replace(/[*_`#>]+/g, '').trim()
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '...' : s)

function Line({ ln }) {
  return (
    <li className={'sy-ln' + (ln.run ? ' run' : '')}>
      <span>{ln.text}</span>
      {ln.href ? <a className="sy-m" href={ln.href} aria-label="open" title={ln.href}><Svg k="link" /></a> : null}
    </li>
  )
}

function Composer({ sid, onSay, onVoice, busy }) {
  const [text, setText] = useState('')
  const [mic, setMic] = useState('idle')       // idle | rec | ready | sending
  const [secs, setSecs] = useState(0)
  const rec = useRef(null)                      // { recorder, stream, chunks, blob, timer, since }
  const drop = () => {
    const r = rec.current; rec.current = null
    if (r) { try { if (r.timer) clearInterval(r.timer) } catch {} try { r.stream.getTracks().forEach(t => t.stop()) } catch {} }
    setMic('idle'); setSecs(0)
  }
  useEffect(() => () => drop(), [])   // eslint-disable-line react-hooks/exhaustive-deps
  const start = async () => {
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)) { onVoice(sid, null, 'this browser cannot record'); return }
    let stream
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) } catch { onVoice(sid, null, 'the microphone is not allowed for this page'); return }
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => { try { return MediaRecorder.isTypeSupported(t) } catch { return false } })
    let recorder
    try { recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream) } catch { stream.getTracks().forEach(t => t.stop()); onVoice(sid, null, 'could not start recording'); return }
    const r = { recorder, stream, chunks: [], blob: null, since: Date.now(), timer: null }
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) r.chunks.push(e.data) }
    recorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop())
      if (r.timer) clearInterval(r.timer)
      if (rec.current !== r) return
      if (!r.chunks.length) { drop(); return }
      r.blob = new Blob(r.chunks, { type: recorder.mimeType || mime || 'audio/webm' })
      setMic('ready')
    }
    r.timer = setInterval(() => { const s = Math.round((Date.now() - r.since) / 1000); setSecs(s); if (s >= 600) { try { recorder.stop() } catch {} } }, 500)
    rec.current = r
    try { recorder.start(250); setMic('rec'); setSecs(0) } catch { drop(); onVoice(sid, null, 'could not start recording') }
  }
  const tap = async () => {
    if (mic === 'idle') { start(); return }
    if (mic === 'rec') { try { rec.current.recorder.stop() } catch { drop() } return }
    if (mic === 'ready' && rec.current && rec.current.blob) {
      const blob = rec.current.blob
      setMic('sending')
      await onVoice(sid, blob)
      drop()
    }
  }
  const submit = (e) => {
    e.preventDefault()
    const t = text.trim()
    if (!t || busy) return
    setText('')
    onSay(sid, t)
  }
  const hint = mic === 'rec' ? `listening ${secs} s, tap to stop` : mic === 'ready' ? 'tap to send, Esc to drop' : mic === 'sending' ? 'keeping it' : 'say it here'
  const markLabel = mic === 'rec' ? 'stop' : mic === 'ready' ? 'send the recording' : 'speak'
  return (
    <form className="sy-say" onSubmit={submit}>
      <input value={text} onChange={e => setText(e.target.value)} placeholder={hint} aria-label={`say it to ${sid}`} autoComplete="off" enterKeyHint="send"
        onKeyDown={e => { if (e.key === 'Escape' && (mic === 'ready' || mic === 'rec')) { e.stopPropagation(); drop() } }} />
      <button type="button" className={'sy-m' + (mic === 'rec' ? ' rec' : mic === 'ready' ? ' ready' : '')} onClick={tap} aria-label={markLabel} title={markLabel} disabled={mic === 'sending'}>
        <Svg k={mic === 'rec' ? 'stop' : mic === 'ready' || mic === 'sending' ? 'send' : 'mic'} />
      </button>
    </form>
  )
}

function Card({ c }) {
  if (!c) return null
  const words = {
    sending: 'sending', answering: 'answering', queued: 'waits behind the answer in progress',
  }[c.state]
  return (
    <div className="sy-card" role="status">
      {c.me ? <p className="me">{clip(c.me, 140)}</p> : null}
      {c.reply ? <p>{clip(plain(c.reply), 700)}</p> : null}
      {words ? <p className="me">{words}</p> : null}
      {c.error ? <p className="err">{c.error}</p> : null}
      {c.thread ? <a href={`/talk?thread=${encodeURIComponent(c.thread)}`}>continue</a> : null}
      {c.path ? <a href={`/files?path=${encodeURIComponent(c.path)}`}>the recording</a> : null}
    </div>
  )
}

function Tile({ t, open, more, card, onToggle, onMore, onSay, onVoice }) {
  const busy = card && (card.state === 'sending' || card.state === 'answering')
  return (
    <section className={'sy-t' + (t.moving ? '' : ' sy-q') + (open ? ' open' : '') + (card && !open ? ' carded' : '')} id={t.id}>
      <button className="sy-th" aria-expanded={open ? 'true' : 'false'} onClick={() => onToggle(t.id)} title={t.description || t.id}>
        <span className="sy-nm">{t.id}</span>{t.moving ? <span className="sy-n">{t.moving}</span> : null}
      </button>
      <div className={'sy-fold' + (open ? ' on' : '')}><div className="sy-fi">
        {t.lines.length ? <ul className="sy-lines">{t.lines.map((ln, i) => <Line key={i} ln={ln} />)}</ul> : null}
        {t.extra ? (
          <div>
            <button className={'sy-more' + (more ? ' on' : '')} aria-expanded={more ? 'true' : 'false'} onClick={() => onMore(t.id)}>+{t.extra}</button>
            <div className={'sy-fold' + (more ? ' on' : '')}><div className="sy-fi">
              {t.more.map(g => (
                <div key={g.kind}>
                  <p className="sy-gh">{g.kind}<b>{g.count}</b></p>
                  <ul className="sy-lines">{g.lines.map((ln, i) => <Line key={i} ln={ln} />)}</ul>
                </div>
              ))}
            </div></div>
          </div>
        ) : null}
        <Composer sid={t.id} onSay={onSay} onVoice={onVoice} busy={busy} />
      </div></div>
      <Card c={card} />
    </section>
  )
}

export default function Systems() {
  const [data, setData] = useState(null)        // null: not read yet; false: the bridge did not answer
  const [open, setOpen] = useState({})
  const [more, setMore] = useState({})
  const [cards, setCards] = useState({})
  const timer = useRef(null)
  const watch = useRef({})                      // sid -> poll timer for an answer in progress

  const load = () => fetch('/cc/systems', { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(d => setData(d && Array.isArray(d.tiles) ? d : false))
    .catch(() => setData(d => (d ? d : false)))

  useEffect(() => {
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    const onKey = (e) => { if (e.key === 'Escape') setOpen({}) }
    document.addEventListener('keydown', onKey)
    return () => {
      stop(); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey)
      Object.values(watch.current).forEach(clearInterval)
    }
  }, [])

  const setCard = (sid, patch) => setCards(c => ({ ...c, [sid]: { ...(c[sid] || {}), ...patch } }))

  // The answer, when the reply did not come back on the send itself (a queued message, a dropped
  // connection): the thread's real state from GET /cc/state, then its last answer from the brain's record.
  const follow = (sid, thread, sentAt) => {
    if (watch.current[sid]) clearInterval(watch.current[sid])
    const tick = async () => {
      if (Date.now() - sentAt > 30 * 60 * 1000) { clearInterval(watch.current[sid]); delete watch.current[sid]; return }
      try {
        const s = await fetch(`/cc/state?thread=${encodeURIComponent(thread)}`, { cache: 'no-store' }).then(r => r.json())
        if (s.running || (s.queue && s.queue.length)) return
        const m = await fetch(`/api/bf/sessions/${encodeURIComponent(thread)}/messages`, { cache: 'no-store' }).then(r => r.json())
        const last = [...((m && m.messages) || [])].reverse().find(x => x.role === 'assistant' && x.content)
        clearInterval(watch.current[sid]); delete watch.current[sid]
        setCard(sid, { state: 'done', reply: last ? last.content : '', error: last ? '' : 'no answer in the thread yet; continue opens it' })
      } catch {}
    }
    watch.current[sid] = setInterval(tick, 3000)
  }

  const say = async (sid, text) => {
    const sentAt = Date.now()
    setCard(sid, { state: 'sending', me: text, reply: '', error: '', path: '' })
    let thread = null
    try {
      const r = await postJson('/cc/systems/thread', { system: sid })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.thread) { setCard(sid, { state: 'done', error: d.error || `the bridge answered ${r.status}` }); return }
      thread = d.thread
    } catch { setCard(sid, { state: 'done', error: 'the bridge did not answer' }); return }
    setCard(sid, { state: 'answering', thread })
    // the chat page's own call, into this system's thread
    try {
      const r = await postJson('/cc/chat', { message: `${sid}: ${text}`, new: false, thread, stream: false, queue: true })
      const d = await r.json().catch(() => ({}))
      if (r.status === 202) { setCard(sid, { state: d.duplicate ? 'done' : 'queued', reply: d.duplicate ? d.reply : '' }); if (!d.duplicate) follow(sid, thread, sentAt); return }
      if (!r.ok) { setCard(sid, { state: 'done', error: d.reply || d.error || `the bridge answered ${r.status}` }); return }
      setCard(sid, { state: 'done', reply: d.reply || '', error: d.error && !d.reply ? 'the turn failed' : '' })
    } catch {
      // a dropped connection is not a dead turn: it runs on the box; watch it there
      follow(sid, thread, sentAt)
    }
    load()
  }

  const voice = async (sid, blob, problem) => {
    if (!blob) { setCard(sid, { state: 'done', me: '', reply: '', error: problem || 'nothing recorded', path: '' }); return }
    const ext = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm'
    const fd = new FormData(); fd.append('file', blob, 'clip.' + ext)
    setCard(sid, { state: 'sending', me: 'a recording', reply: '', error: '', path: '' })
    try {
      const r = await fetch(`/cc/systems/voice?system=${encodeURIComponent(sid)}`, { method: 'POST', body: fd })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) { setCard(sid, { state: 'done', error: d.error || `the bridge answered ${r.status}` }); return }
      setCard(sid, { state: 'done', reply: `kept as a memo for ${sid}; the tape takes it within minutes`, path: d.path })
    } catch { setCard(sid, { state: 'done', error: 'the bridge did not answer' }) }
  }

  const tiles = (data && data.tiles) || []
  return (
    <>
      <Head><title>Systems</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="sy">
        <main className="sy-main" aria-label={data && data.built ? `Systems, read ${data.built}` : 'Systems'}>
          {data === false ? <p className="sy-note">The bridge is not answering at /cc/systems. The tiles fill by themselves once it does.</p> : null}
          <div className="sy-grid">
            {tiles.map(t => (
              <Tile key={t.id} t={t} open={!!open[t.id]} more={!!more[t.id]} card={cards[t.id]}
                onToggle={id => setOpen(o => ({ ...o, [id]: !o[id] }))} onMore={id => setMore(o => ({ ...o, [id]: !o[id] }))}
                onSay={say} onVoice={voice} />
            ))}
          </div>
        </main>
      </div>
    </>
  )
}
