import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'

// The systems page (BOARD-3 2026-11-12, BOARD-4 2026-11-13). hbar: "ON SINGLE PAGE I SEE EACH SYSTEM AND I CAN
// DISCUSS IN THE CHAT IN A SYSTEM WHILE SEEING ALL THE SYSTEMS WHATS GOING ON AND FUNCTIONING", with "HOW MANY
// AGENTS/TEAMS OF AGENTS ... CAN BE SEEN ACTIVE" per system.
// Split: the tiles on the left (GET /cc/systems, scripts/cc/cc_systems.py), the pressed system's ONE standing
// thread on the right as the live chat itself (/talk?pane=systems&thread=<id> in a frame, the /panes pattern: the
// stream, the composer, cards and stop all work there). POST /cc/systems/thread gives the thread, made once.
// A tile at rest: its name and four numbers, each shown only when not zero: agents running now (a rust dot),
// agents done today (a tick), open tasks (court items and his tasks), next rows (an arrow). A press on a number
// opens the tile in place on that kind's lines (at most eight words, one link each); a press on the name opens
// the system's thread on the right. On a phone the thread opens over the tiles, with a way back.
// The mic in the thread's head: tap to record (MediaRecorder), tap to stop, tap to send, Esc drops it;
// POST /cc/systems/voice?system=<id> keeps the clip as in/<date>/memo_<id>_<stamp>.<ext> for the memo tape.
// Updates: one light request every three seconds, none while the tab is hidden (the /board pattern).
// Look: the chat's sand skin, no borders, no black, nothing moves on its own.

const KINDS = [
  ['running', 'running now'], ['done_today', 'done today'], ['tasks', 'open tasks'], ['next', 'next'],
]
const SEL = 'cc.systems.sel'

const CSS = `
.sy{--bg:#efe3cf;--surface:#e6d6bd;--ink:#2b2116;--dim:#54473a;--muted:#7a6a55;--rust:#a8452b;--ease:cubic-bezier(.2,.7,.2,1);
  --top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));
  background:var(--bg);color:var(--ink);min-height:calc(100vh - var(--top));font:400 16px/1.5 system-ui,-apple-system,sans-serif;box-sizing:border-box}
.sy *{box-sizing:border-box}
.sy :where(a){color:inherit}
.sy :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.sy :focus-visible{outline:2px solid var(--rust);outline-offset:3px;border-radius:6px}
.sy-split{display:grid;grid-template-columns:minmax(0,1fr) minmax(380px,40%);align-items:start}
.sy-left{padding:28px 24px 72px 32px;min-width:0}
.sy-key{display:flex;flex-wrap:wrap;gap:4px 18px;margin:0 12px 18px;font-size:13px;color:var(--muted)}
.sy-key span{display:inline-flex;align-items:center;gap:6px}
.sy-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:4px 18px;align-items:start}
.sy-t{border-radius:14px;transition:background-color 260ms var(--ease);min-width:0}
.sy-t.open,.sy-t.sel{background:var(--surface)}
.sy-th{display:block;width:100%;padding:10px 12px 2px}
.sy-nm{font:400 23px/1.2 Lora,Georgia,serif;overflow-wrap:anywhere}
.sy-q .sy-nm{color:var(--muted);opacity:.62}.sy-q.open .sy-nm,.sy-q.sel .sy-nm,.sy-th:hover .sy-nm{opacity:1;color:var(--ink)}
.sy-ns{display:flex;flex-wrap:wrap;gap:2px 4px;padding:0 6px 8px;min-height:10px}
.sy-c{display:inline-flex;align-items:center;gap:5px;padding:2px 6px;border-radius:8px;font-size:14px;color:var(--dim);font-variant-numeric:tabular-nums}
.sy-c:hover,.sy-c.on{color:var(--ink);background:var(--bg)}
.sy-c.running{color:var(--rust)}
.sy-g{display:inline-block;width:12px;height:12px;flex:none}
.sy-g svg{width:12px;height:12px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.sy-dot{width:7px;height:7px;border-radius:50%;background:var(--rust);display:inline-block;margin:0 2px}
.sy-fold{display:grid;grid-template-rows:0fr;visibility:hidden;transition:grid-template-rows 260ms var(--ease),visibility 0s linear 260ms}
.sy-fold.on{grid-template-rows:1fr;visibility:visible;transition:grid-template-rows 260ms var(--ease),visibility 0s}
.sy-fi{overflow:hidden;min-height:0}
.sy-gh{margin:2px 0 0;padding:0 12px;font-size:13px;color:var(--muted);letter-spacing:.04em}
.sy-lines{list-style:none;margin:0;padding:0 12px 6px;max-width:58ch}
.sy-ln{display:flex;align-items:baseline;gap:8px;padding:4px 0;color:var(--dim);font-size:15px}
.sy-ln span{flex:1}
.sy-ln.run span::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--rust);margin:0 9px 2px 0;vertical-align:middle}
.sy-m{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;color:var(--muted);opacity:.65;border-radius:50%;flex:none;transition:opacity 200ms var(--ease),color 200ms var(--ease)}
.sy-m:hover,.sy-m:focus-visible{opacity:1;color:var(--rust)}
.sy-m svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
.sy-m.rec{opacity:1;color:var(--rust);animation:sy-pulse 1.2s ease-in-out infinite}.sy-m.ready{opacity:1;color:var(--rust)}
@keyframes sy-pulse{50%{opacity:.45}}
.sy-more{font-size:13px;color:var(--muted);padding:0 12px 10px}.sy-more:hover{color:var(--rust)}
.sy-empty{font-size:14px;color:var(--muted);padding:2px 12px 10px;margin:0}
.sy-talk{display:none;margin:2px 12px 12px;width:calc(100% - 24px);padding:9px 16px;border-radius:999px;background:var(--bg);color:var(--muted);font-size:15px}
.sy-right{position:sticky;top:var(--top);height:calc(100vh - var(--top));display:flex;flex-direction:column;background:var(--surface);min-width:0}
.sy-ph{display:flex;align-items:center;gap:10px;padding:14px 18px 10px;min-height:56px}
.sy-ph .sy-nm{font-size:22px;flex:1;min-width:0}
.sy-ph .st{font-size:13px;color:var(--muted);white-space:nowrap}
.sy-ph .st.busy{color:var(--rust)}
.sy-back{display:none;font-size:14px;color:var(--muted);padding:4px 8px 4px 0}
.sy-frame{flex:1;width:100%;border:0;background:var(--bg);border-radius:14px 14px 0 0;min-height:0}
.sy-hold{flex:1;display:flex;align-items:center;justify-content:center;padding:24px;color:var(--muted);font-size:15px;text-align:center}
.sy-msg{margin:0 18px 10px;font-size:13px;color:var(--dim)}.sy-msg.err{color:var(--rust)}.sy-msg a{color:var(--rust)}
.sy-note{color:var(--muted);font-size:14px;margin:8px 12px 18px}
@media(max-width:899px){
  .sy-split{display:block}.sy-left{padding:18px 12px 48px}.sy-grid{grid-template-columns:1fr;gap:2px}
  .sy-right{display:none;position:fixed;left:0;right:0;bottom:0;top:var(--top);height:auto;z-index:40}
  .sy-right.show{display:flex}.sy-back{display:inline-block}.sy-talk{display:block}.sy-frame{border-radius:0}
}
@media(prefers-reduced-motion:reduce){.sy-fold,.sy-t{transition:none!important}.sy-m.rec{animation:none}}
`

const ICON = {
  link: <path d="M6 3h7v7M13 3 4 12" />,
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
  send: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
  done_today: <path d="M3 8.5 6.5 12 13 4.5" />,
  tasks: <rect x="3.5" y="3.5" width="9" height="9" rx="2" />,
  next: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>
const Glyph = ({ k }) => (k === 'running' ? <span className="sy-dot" aria-hidden="true" /> : <span className="sy-g"><Svg k={k} /></span>)

const postJson = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const fmt = (s) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)

function Line({ ln }) {
  return (
    <li className={'sy-ln' + (ln.run ? ' run' : '')}>
      <span>{ln.text}</span>
      {ln.href ? <a className="sy-m" href={ln.href} aria-label="open" title={ln.href}><Svg k="link" /></a> : null}
    </li>
  )
}

function Tile({ t, open, kind, sel, onKind, onName, onTalk }) {
  const c = t.counts || {}
  const d = (t.detail || {})[kind] || { count: 0, lines: [] }
  const [all, setAll] = useState(false)
  useEffect(() => { setAll(false) }, [kind, open])
  const busy = KINDS.some(([k]) => c[k])
  const shown = all ? d.lines : d.lines.slice(0, 7)
  return (
    <section className={'sy-t' + (busy ? '' : ' sy-q') + (open ? ' open' : '') + (sel ? ' sel' : '')} id={t.id}>
      <button className="sy-th" onClick={() => onName(t.id)} title={t.description || t.id} aria-pressed={sel ? 'true' : 'false'}>
        <span className="sy-nm">{t.id}</span>
      </button>
      <div className="sy-ns">
        {KINDS.map(([k, label]) => (c[k] ? (
          <button key={k} className={'sy-c ' + k + (open && kind === k ? ' on' : '')} onClick={() => onKind(t.id, k)}
            aria-expanded={open && kind === k ? 'true' : 'false'} aria-label={`${c[k]} ${label}`} title={label}>
            <Glyph k={k} />{c[k]}
          </button>
        ) : null))}
      </div>
      <div className={'sy-fold' + (open ? ' on' : '')}><div className="sy-fi">
        <p className="sy-gh">{(KINDS.find(x => x[0] === kind) || KINDS[0])[1]}</p>
        {shown.length ? <ul className="sy-lines">{shown.map((ln, i) => <Line key={i} ln={ln} />)}</ul> : <p className="sy-empty">nothing</p>}
        {!all && d.lines.length > 7 ? <button className="sy-more" onClick={() => setAll(true)}>+{d.count - 7}</button> : null}
        {all && d.count > d.lines.length ? <p className="sy-empty">{d.count - d.lines.length} more in its thread</p> : null}
        <button className="sy-talk" onClick={() => onTalk(t.id)}>say it here</button>
      </div></div>
    </section>
  )
}

function Mic({ sid, onDone }) {
  const [mic, setMic] = useState('idle')       // idle | rec | ready | sending
  const [secs, setSecs] = useState(0)
  const rec = useRef(null)                      // { recorder, stream, chunks, blob, timer, since }
  const drop = () => {
    const r = rec.current; rec.current = null
    if (r) { try { if (r.timer) clearInterval(r.timer) } catch {} try { r.stream.getTracks().forEach(x => x.stop()) } catch {} }
    setMic('idle'); setSecs(0)
  }
  useEffect(() => () => drop(), [sid])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (mic !== 'rec' && mic !== 'ready') return undefined
    const k = (e) => { if (e.key === 'Escape') { e.stopPropagation(); drop() } }
    document.addEventListener('keydown', k, true)
    return () => document.removeEventListener('keydown', k, true)
  }, [mic])   // eslint-disable-line react-hooks/exhaustive-deps
  const start = async () => {
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)) { onDone({ error: 'this browser cannot record' }); return }
    let stream
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) } catch { onDone({ error: 'the microphone is not allowed for this page' }); return }
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find(x => { try { return MediaRecorder.isTypeSupported(x) } catch { return false } })
    let recorder
    try { recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream) } catch { stream.getTracks().forEach(x => x.stop()); onDone({ error: 'could not start recording' }); return }
    const r = { recorder, stream, chunks: [], blob: null, since: Date.now(), timer: null }
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) r.chunks.push(e.data) }
    recorder.onstop = () => {
      stream.getTracks().forEach(x => x.stop())
      if (r.timer) clearInterval(r.timer)
      if (rec.current !== r) return
      if (!r.chunks.length) { drop(); return }
      r.blob = new Blob(r.chunks, { type: recorder.mimeType || mime || 'audio/webm' })
      setMic('ready')
    }
    r.timer = setInterval(() => { const s = Math.round((Date.now() - r.since) / 1000); setSecs(s); if (s >= 600) { try { recorder.stop() } catch {} } }, 500)
    rec.current = r
    try { recorder.start(250); setMic('rec'); setSecs(0); onDone(null) } catch { drop(); onDone({ error: 'could not start recording' }) }
  }
  const send = async (blob) => {
    const ext = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm'
    const fd = new FormData(); fd.append('file', blob, 'clip.' + ext)
    try {
      const r = await fetch(`/cc/systems/voice?system=${encodeURIComponent(sid)}`, { method: 'POST', body: fd })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.ok) { onDone({ error: d.error || `the bridge answered ${r.status}` }); return }
      onDone({ text: `kept as a memo for ${sid}; the tape takes it within minutes`, path: d.path })
    } catch { onDone({ error: 'the bridge did not answer' }) }
  }
  const tap = async () => {
    if (mic === 'idle') { start(); return }
    if (mic === 'rec') { try { rec.current.recorder.stop() } catch { drop() } return }
    if (mic === 'ready' && rec.current && rec.current.blob) {
      const blob = rec.current.blob
      setMic('sending')
      await send(blob)
      drop()
    }
  }
  const label = mic === 'rec' ? `recording ${fmt(secs)}, tap to stop` : mic === 'ready' ? 'tap to send, Esc to drop' : mic === 'sending' ? 'keeping it' : 'speak a memo'
  return (
    <>
      {mic !== 'idle' ? <span className="st busy">{label}</span> : null}
      <button type="button" className={'sy-m' + (mic === 'rec' ? ' rec' : mic === 'ready' ? ' ready' : '')} onClick={tap}
        aria-label={label} title={label} disabled={mic === 'sending'}>
        <Svg k={mic === 'rec' ? 'stop' : mic === 'ready' || mic === 'sending' ? 'send' : 'mic'} />
      </button>
    </>
  )
}

function Thread({ sid, tile, thread, err, show, onBack }) {
  const [state, setState] = useState(null)      // the frame's own report ('cc-pane-state')
  const [msg, setMsg] = useState(null)
  const frame = useRef(null)
  useEffect(() => { setState(null); setMsg(null) }, [sid, thread])
  useEffect(() => {
    const on = (e) => {
      if (e.origin !== window.location.origin || !frame.current || e.source !== frame.current.contentWindow) return
      if (e.data && e.data.type === 'cc-pane-state') setState(e.data)
    }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [])
  const c = (tile && tile.counts) || {}
  const st = state && state.busy ? (state.waiting ? 'waits for you' : state.writing ? 'writing' : 'thinking')
    : c.running ? `${c.running} running` : ''
  return (
    <aside className={'sy-right' + (show ? ' show' : '')} aria-label={sid ? `${sid} thread` : 'thread'}>
      <div className="sy-ph">
        <button className="sy-back" onClick={onBack} aria-label="back to the systems">back</button>
        <span className="sy-nm">{sid || ''}</span>
        {st ? <span className={'st' + (state && state.busy ? ' busy' : '')}>{st}</span> : null}
        {sid ? <Mic sid={sid} onDone={setMsg} /> : null}
        {thread ? <a className="sy-m" href={`/talk?thread=${encodeURIComponent(thread)}`} aria-label="open the thread in full" title="open the thread in full"><Svg k="link" /></a> : null}
      </div>
      {msg ? (
        <p className={'sy-msg' + (msg.error ? ' err' : '')} role="status">
          {msg.error || msg.text}{msg.path ? <> <a href={`/files?path=${encodeURIComponent(msg.path)}`}>the recording</a></> : null}
        </p>
      ) : null}
      {thread ? (
        <iframe key={thread} ref={frame} className="sy-frame" title={`${sid} thread`} src={`/talk?pane=systems&thread=${encodeURIComponent(thread)}`}
          allow="microphone; clipboard-write" />
      ) : (
        <div className="sy-hold">{err ? err : sid ? `opening the ${sid} thread` : 'press a system to talk in it'}</div>
      )}
    </aside>
  )
}

export default function Systems() {
  const [data, setData] = useState(null)        // null: not read yet; false: the bridge did not answer
  const [open, setOpen] = useState({})          // sid -> the kind shown in place
  const [sel, setSel] = useState(null)
  const [threads, setThreads] = useState({})    // sid -> thread id, as the bridge gave it
  const [err, setErr] = useState('')
  const [show, setShow] = useState(false)       // phone: the thread over the tiles
  const timer = useRef(null)

  const load = () => fetch('/cc/systems', { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(d => setData(d && Array.isArray(d.tiles) ? d : false))
    .catch(() => setData(d => (d ? d : false)))

  // the system's one standing thread: the bridge makes it on the first press, then always gives the same one
  const pick = async (sid, phone) => {
    setSel(sid); setErr('')
    if (phone) setShow(true)
    try { localStorage.setItem(SEL, sid) } catch {}
    if (threads[sid]) return
    try {
      const r = await postJson('/cc/systems/thread', { system: sid })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.thread) { setErr(d.error || `the bridge answered ${r.status}`); return }
      setThreads(m => ({ ...m, [sid]: d.thread }))
    } catch { setErr('the bridge did not answer') }
  }

  useEffect(() => {
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    const onKey = (e) => { if (e.key === 'Escape') { setShow(false); setOpen({}) } }
    document.addEventListener('keydown', onKey)
    let first = null
    try { first = new URLSearchParams(window.location.search).get('system') || localStorage.getItem(SEL) } catch {}
    if (first) pick(first, false)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey) }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  // a thread the board already knows needs no call
  useEffect(() => {
    if (!data || !data.tiles) return
    const known = {}
    data.tiles.forEach(t => { if (t.thread) known[t.id] = t.thread })
    setThreads(m => {
      const n = { ...m }
      let moved = false
      Object.entries(known).forEach(([k, v]) => { if (!n[k]) { n[k] = v; moved = true } })
      return moved ? n : m
    })
  }, [data])

  const phone = () => typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(max-width: 899px)').matches
  const onKind = (sid, k) => setOpen(o => (o[sid] === k ? { ...o, [sid]: null } : { ...o, [sid]: k }))
  const onName = (sid) => {
    const t = ((data && data.tiles) || []).find(x => x.id === sid)
    const first = (KINDS.find(([k]) => t && t.counts && t.counts[k]) || KINDS[0])[0]
    if (phone()) { setOpen(o => ({ ...o, [sid]: o[sid] ? null : first })); return }
    setOpen(o => ({ ...o, [sid]: o[sid] && sel === sid ? null : (o[sid] || first) }))
    pick(sid, false)
  }

  const tiles = (data && data.tiles) || []
  const tile = tiles.find(t => t.id === sel)
  const running = data && data.running
  return (
    <>
      <Head><title>Systems</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="sy">
        <div className="sy-split">
          <main className="sy-left" aria-label={data && data.built ? `Systems, read ${data.built}` : 'Systems'}>
            {data === false ? <p className="sy-note">The bridge is not answering at /cc/systems. The tiles fill by themselves once it does.</p> : null}
            {tiles.length ? (
              <div className="sy-key" aria-hidden="true">
                <span><Glyph k="running" />{running ? `${running} running now` : 'running now'}</span>
                <span><Glyph k="done_today" />done today</span>
                <span><Glyph k="tasks" />open tasks</span>
                <span><Glyph k="next" />next</span>
              </div>
            ) : null}
            <div className="sy-grid">
              {tiles.map(t => (
                <Tile key={t.id} t={t} open={!!open[t.id]} kind={open[t.id] || 'running'} sel={sel === t.id}
                  onKind={onKind} onName={onName} onTalk={sid => pick(sid, true)} />
              ))}
            </div>
          </main>
          <Thread sid={sel} tile={tile} thread={sel ? threads[sel] : null} err={err} show={show} onBack={() => setShow(false)} />
        </div>
      </div>
    </>
  )
}
