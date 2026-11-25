import Head from 'next/head'
import React, { useEffect, useRef, useState } from 'react'
import { cellLine, cellState, sentOver, sendText, sendClip, Recorder, CENTRE, pickLook, keptSet, addTo, removeFrom, loadWall, saveWall, systemsUrl } from '../lib/wall'
import WallOrbit from '../components/WallOrbit'

// The wall (WALL-1, 2026-11-24). hbar, verbatim: "I still want to apply this view board where I see in parallel on
// a dark screen every single system operating and then I can write into the small little box, whatever it is, I
// want to speak into it and we can continue the changing from there so all threats [threads] are actually live in
// real time and all I need is that text box to speak into it I don't even have to see the entire text ... Of
// course it would be able to see which systems are activated and how many jobs are running".
// One more way to work the brain beside /systems, /board and /panes, not a replacement of them.
//
// A dark screen, one cell per system of GET /cc/systems, all at once (the grid fits a 1440 screen; a phone
// scrolls). A cell at rest: the name, a light that is on while something runs there, the number of jobs running
// now, and ONE line: what its standing thread is saying now, else the running job's title, else the last thing the
// thread said (the tile's `said`, WALL-1 in cc-bridge.py). Quiet systems sit dim. Cells keep their places (the
// registry's order, world first), so the box under the hand never moves while things change.
// Each cell has one small box: type and Enter, or tap the mic, speak, tap again. It sends in place into that
// system's standing thread (made once if missing, ui/lib/wall.js); the page never navigates; the cell shows
// "sent" and then the thread's own live line as it answers. A press on the name opens the full thread beside
// (the /systems pane: /talk?pane=...&thread=... in a frame), for when the whole text is wanted.
// Updates: one light request every three seconds, none while the tab is hidden (the /board pattern).
// Look: dark on his word for this page; the console's own accent and font; few words at rest.
//
// Two looks (WALL-2, 2026-11-24, hbar: "concept good and design is nice, but in this case lets do more slick (so
// maybe what you have is the generic one, and the personalized one is what I'm asking to be built for me"): the
// grid above is the generic look, kept at /wall?look=grid; the orbit (ui/components/WallOrbit.js) is the personal
// one: true black, the kept systems around the brain's own symbol. Which one a brain opens on, and which systems
// its orbit keeps, is that brain's setting (GET/POST /cc/wall, localStorage when the bridge is away); ?look= wins
// for one visit. The look switch sits quietly in a corner.
//
// Depth (WALL-3, 2026-11-24, hbar: "everything is hidden, and i can gain access some easy way WITHOUT interfering
// with production and the main focus"): in the orbit, a press on a system's light or count opens its quiet layer in
// place (ui/components/WallDepth.js); the centre's count opens the brain's. While a layer is open the same
// three-second poll asks for that system's tree too (GET /cc/systems?depth=<id>); nothing is sent, nothing
// navigates, nothing that streams is touched. Pages the layer opens (tasks, court, an instrument) open beside.
//
// Continue (WALL-4, 2026-11-24, hbar: "fill it with what we are currently doing-- the systems that is + prompts to
// continue from what has been in this thread, and maybe some faint ones that i HAVE BEEN working on in other
// threads"): a focused box (or a system's layer) shows up to five prompts from its card's "## Continue"; a press puts
// one in the box, a second press sends it. The world's faint systems sit dim on the outer ring; a press brings one
// in. When the brain's seed is newer than his own set, one quiet line asks: "take it" or "keep mine".

const LAST = ['self', 'unfiled']
const short = (id) => String(id || '').replace(/^hbar\./, '')
const order = (tiles) => {
  const rank = (id) => (id === 'world' ? 0 : LAST.includes(id) ? 2 : 1)
  return [...tiles].sort((a, b) => rank(a.id) - rank(b.id) || short(a.id).localeCompare(short(b.id)))
}
const fmt = (s) => (s < 60 ? `0:${String(s).padStart(2, '0')}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)

const CSS = `
.wl{--wbg:#0b0c0e;--wcell:#131418;--wcell2:#1a1c21;--wink:#e9e7e2;--wdim:#9a978f;--wmute:#5d5b56;--wlit:var(--accent,#c9a96e);
  --ease:cubic-bezier(.2,.7,.2,1);--top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));
  background:var(--wbg);color:var(--wink);min-height:calc(100vh - var(--top));font:400 14px/1.4 var(--font-body,system-ui,sans-serif);box-sizing:border-box;
  display:grid;grid-template-columns:minmax(0,1fr)}
.wl.with{grid-template-columns:minmax(0,1fr) minmax(420px,42%)}
.wl *{box-sizing:border-box}
.wl :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.wl :focus-visible{outline:2px solid var(--wlit);outline-offset:2px;border-radius:6px}
.wl-main{padding:14px 14px 20px;min-width:0}
.wl-top{display:flex;align-items:baseline;gap:14px;padding:0 4px 10px;color:var(--wmute);font-size:12px;letter-spacing:.06em}
.wl-top b{font-weight:500;color:var(--wdim)}.wl-top .on{color:var(--wlit)}
.wl-top .wl-lk{margin-left:auto}
.wl-lk{display:flex;gap:12px;font-size:11px;letter-spacing:.14em;color:var(--wmute,#4f4d49);text-transform:lowercase}
.wl-lk button{color:inherit;opacity:.8}.wl-lk button:hover{color:var(--wink,#ecebe6)}.wl-lk button[aria-pressed=true]{color:var(--wdim,#8f8c85);cursor:default}
.wl-lkf{position:absolute;left:22px;bottom:18px;z-index:6}
.wl-orb{position:relative;min-width:0}
.wl.orbit{background:#000}
.wl-toast{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);z-index:7;display:flex;gap:14px;align-items:center;font-size:12px;color:var(--wdim,#8f8c85);
  background:rgba(14,14,15,.92);border:1px solid rgba(255,255,255,.07);border-radius:999px;padding:7px 16px}
.wl-toast button{color:var(--wlit);font-size:12px}
.wl-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(166px,1fr));gap:8px}
.wl.with .wl-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.wl-c{background:var(--wcell);border-radius:12px;padding:9px 10px 8px;display:flex;flex-direction:column;gap:5px;min-width:0;
  transition:background-color 300ms var(--ease),opacity 300ms var(--ease)}
.wl-c.q{opacity:.48}.wl-c.q:hover,.wl-c.q:focus-within,.wl-c.open{opacity:1}
.wl-c.lit{background:var(--wcell2)}.wl-c.open{box-shadow:inset 0 0 0 1px var(--wlit)}
.wl-h{display:flex;align-items:center;gap:7px;min-width:0}
.wl-lt{width:7px;height:7px;border-radius:50%;flex:none;background:var(--wmute);opacity:.5}
.wl-c.lit .wl-lt{background:var(--wlit);opacity:1;box-shadow:0 0 8px var(--wlit)}
.wl-nm{flex:1;min-width:0;font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wl-nm:hover{color:var(--wlit)}
.wl-n{font-size:12px;color:var(--wlit);font-variant-numeric:tabular-nums}
.wl-ln{font-size:12px;line-height:1.35;color:var(--wdim);min-height:2.7em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.wl-ln.live,.wl-ln.waits{color:var(--wink)}.wl-ln.sent{color:var(--wlit)}.wl-ln.error{color:#e07a5f}
.wl-ln .k{color:var(--wmute);margin-right:5px}
.wl-box{display:flex;align-items:center;gap:4px;background:var(--wbg);border-radius:999px;padding:0 3px 0 10px;height:28px}
.wl-in{flex:1;min-width:0;background:none;border:0;outline:none;color:var(--wink);font:inherit;font-size:13px;padding:0}
.wl-in::placeholder{color:var(--wmute)}
.wl-m{display:inline-flex;width:22px;height:22px;align-items:center;justify-content:center;border-radius:50%;color:var(--wmute);flex:none}
.wl-m:hover{color:var(--wlit)}
.wl-m svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}
.wl-m.rec{color:#e07a5f;animation:wl-p 1.2s ease-in-out infinite}.wl-m.busy{opacity:.5;cursor:default}
.wl-t{font-size:11px;color:#e07a5f;font-variant-numeric:tabular-nums}
@keyframes wl-p{50%{opacity:.45}}
.wl-note{color:var(--wdim);padding:20px 4px}
.wl-side{position:sticky;top:var(--top);height:calc(100vh - var(--top));display:flex;flex-direction:column;background:var(--wcell);min-width:0}
.wl-sh{display:flex;align-items:center;gap:10px;padding:10px 14px;min-height:46px}
.wl-sh .wl-nm{font-size:16px}
.wl-sh a,.wl-x{color:var(--wdim);font-size:13px;text-decoration:none}.wl-sh a:hover,.wl-x:hover{color:var(--wlit)}
.wl-fr{flex:1;width:100%;border:0;background:var(--wbg);min-height:0}
.wl-hold{flex:1;display:flex;align-items:center;justify-content:center;color:var(--wdim);padding:20px;text-align:center}
@media(max-width:899px){
  .wl,.wl.with{grid-template-columns:minmax(0,1fr)}
  .wl-grid,.wl.with .wl-grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
  .wl-side{position:fixed;inset:var(--top) 0 0 0;height:auto;z-index:40}
}
@media(max-width:420px){.wl-grid,.wl.with .wl-grid{grid-template-columns:1fr 1fr;gap:6px}.wl-main{padding:10px 8px 16px}.wl-ln.quiet{min-height:0;display:none}}
@media(prefers-reduced-motion:reduce){.wl-c{transition:none}.wl-m.rec{animation:none}}
`

const ICON = {
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>

function Cell({ t, sent, rec, secs, open, onSend, onMic, onName }) {
  const [text, setText] = useState('')
  const st = cellState(t)
  const ln = cellLine(t, sent)
  const quiet = !st.on && ln.kind !== 'sent' && ln.kind !== 'error' && !open
  const recording = rec === 'rec'
  const busy = rec === 'busy'
  const key = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && text.trim()) { e.preventDefault(); onSend(t.id, text); setText('') }
  }
  const lead = ln.kind === 'sent' ? 'sent' : ln.kind === 'job' ? 'job' : ln.kind === 'waits' ? 'waits' : ''
  return (
    <section className={'wl-c' + (st.on ? ' lit' : '') + (quiet ? ' q' : '') + (open ? ' open' : '')} aria-label={t.id}>
      <div className="wl-h">
        <span className="wl-lt" aria-hidden="true" />
        <button className="wl-nm" onClick={() => onName(t.id)} title={`${t.id}: open the whole thread beside`}>{short(t.id)}</button>
        {st.running ? <span className="wl-n" title={`${st.running} running now`}>{st.running}</span> : null}
      </div>
      <p className={'wl-ln ' + ln.kind} title={ln.text || undefined}>
        {lead ? <span className="k">{lead}</span> : null}{ln.text || ' '}
      </p>
      <div className="wl-box">
        <input className="wl-in" value={text} onChange={e => setText(e.target.value)} onKeyDown={key}
          placeholder={recording ? 'listening' : busy ? 'hearing it' : 'say'} aria-label={`say to ${t.id}`} disabled={busy} maxLength={8000} />
        {recording ? <span className="wl-t">{fmt(secs)}</span> : null}
        <button type="button" className={'wl-m' + (recording ? ' rec' : busy ? ' busy' : '')} onClick={() => onMic(t.id)} disabled={busy}
          aria-label={recording ? 'stop and send' : busy ? 'sending the recording' : `speak to ${t.id}`}
          title={recording ? 'tap to stop and send, Esc drops it' : `speak to ${t.id}`}>
          <Svg k={recording ? 'stop' : 'mic'} />
        </button>
      </div>
    </section>
  )
}

function LookSwitch({ look, onLook, className }) {
  return (
    <div className={'wl-lk ' + (className || '')} role="group" aria-label="the wall's look">
      {['orbit', 'grid'].map(k => (
        <button key={k} type="button" aria-pressed={look === k} onClick={() => look !== k && onLook(k)}
          title={k === 'orbit' ? 'the kept systems around the brain' : 'every system at once'}>{k}</button>
      ))}
    </div>
  )
}

function Side({ sid, thread, err, onClose }) {
  return (
    <aside className="wl-side" aria-label={`${sid} thread`}>
      <div className="wl-sh">
        <span className="wl-nm">{sid === CENTRE ? 'the brain (central thread)' : sid}</span>
        {thread ? <a href={`/talk?thread=${encodeURIComponent(thread)}`} title="open the thread in full">full</a> : null}
        <button className="wl-x" onClick={onClose} aria-label={`close ${sid}`} title="close; it keeps running">close</button>
      </div>
      {thread ? (
        <iframe key={thread} className="wl-fr" title={`${sid} thread`} allow="microphone; clipboard-write"
          src={`/talk?pane=wall-${encodeURIComponent(sid)}&thread=${encodeURIComponent(thread)}`} />
      ) : <div className="wl-hold">{err || `opening the ${sid} thread`}</div>}
    </aside>
  )
}

// A page beside (WALL-3): the tasks, the court, an instrument; on the console origin only (openOf / the layer).
function Beside({ route, onClose }) {
  const safe = /^\/(?!\/)/.test(route.route) ? route.route : null
  return (
    <aside className="wl-side" aria-label={`${route.title || 'page'} beside`}>
      <div className="wl-sh">
        <span className="wl-nm">{route.title || route.route}</span>
        {safe ? <a href={safe} title="open it in full">full</a> : null}
        <button className="wl-x" onClick={onClose} aria-label={`close ${route.title || 'the page'}`} title="close">close</button>
      </div>
      {safe ? <iframe key={safe} className="wl-fr" title={route.title || 'page'} src={safe} allow="microphone; clipboard-write" />
        : <div className="wl-hold">only a page of this console opens here</div>}
    </aside>
  )
}

export default function Wall() {
  const [data, setData] = useState(null)       // null: not read yet; false: the bridge did not answer
  const [sent, setSent] = useState({})         // sid -> {text, state, at, before}
  const [threads, setThreads] = useState({})   // sid -> thread id made here (the board catches up within 3 s)
  const [side, setSide] = useState(null)       // the system whose whole thread is open beside
  const [sideErr, setSideErr] = useState('')
  const [mic, setMic] = useState({ sid: null, state: null, secs: 0 })
  const [look, setLookState] = useState(null)  // 'grid' | 'orbit'
  const [set, setSet] = useState(null)         // the orbit's kept systems (null: not chosen yet, start from use)
  const [note, setNote] = useState(null)       // {text, undo}
  const [depth, setDepthState] = useState(null) // the system whose depth layer is open (WALL-3), CENTRE for the brain
  const [route, setRoute] = useState(null)      // {route, title}: a page open beside (tasks, court, an instrument)
  const [faint, setFaint] = useState([])        // WALL-4: systems worked on in other threads, dim on the outer ring
  const [fresh, setFresh] = useState(null)      // WALL-4: {set, stamp} when the brain's seed is newer than his own set
  const depthRef = useRef(null)
  const timer = useRef(null)
  const noteTimer = useRef(null)
  const recorder = useRef(null)

  const load = () => fetch(systemsUrl(depthRef.current), { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(d => setData(d && Array.isArray(d.tiles) ? d : false))
    .catch(() => setData(d => (d ? d : false)))

  useEffect(() => {
    recorder.current = new Recorder({ mediaDevices: navigator.mediaDevices, MediaRecorder: window.MediaRecorder })
    const store = (() => { try { return window.localStorage } catch { return null } })()
    loadWall(fetch, store).then(w => {
      setLookState(pickLook(new URLSearchParams(window.location.search).get('look'), w))
      if (Array.isArray(w.set)) setSet(w.set)
      setFaint(w.faint || []); setFresh(w.fresh || null)
    })
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      if (recorder.current && recorder.current.busy) { recorder.current.drop(); setMic({ sid: null, state: null, secs: 0 }); return }
      if (depthRef.current) { depthRef.current = null; setDepthState(null); return }   // the layer first, the thread beside stays
      setSide(null); setRoute(null)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      stop(); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey)
      clearTimeout(noteTimer.current)
      if (recorder.current) recorder.current.drop()
    }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const tiles = order((data && data.tiles) || [])
  const tileOf = (sid) => tiles.find(t => t.id === sid)
  const threadOf = (sid) => threads[sid] || (tileOf(sid) || {}).thread || null

  const mark = (sid, v) => setSent(m => ({ ...m, [sid]: v }))
  const done = (sid, text, res) => {
    if (res.thread) setThreads(m => (m[sid] ? m : { ...m, [sid]: res.thread }))
    if (!res.ok) { mark(sid, { text: res.error || 'not sent', state: 'error', at: Date.now() }); return }
    const before = ((tileOf(sid) || {}).said || {}).at
    const what = res.memo ? 'kept as a memo; the tape takes it within minutes' : (res.queued ? 'queued: ' : '') + (res.heard || text)
    mark(sid, { text: what, state: 'sent', at: Date.now(), before })
    load()
  }
  const onSend = async (sid, text) => {
    mark(sid, { text, state: 'sent', at: Date.now(), before: ((tileOf(sid) || {}).said || {}).at })
    done(sid, text, await sendText(fetch, sid, text, threadOf(sid)))
  }
  const onMic = async (sid) => {
    const r = recorder.current
    if (!r) return
    if (r.busy && mic.sid !== sid) { r.drop(); setMic({ sid: null, state: null, secs: 0 }) }
    if (!r.busy) {
      const got = await r.start(s => setMic(m => (m.sid === sid ? { ...m, secs: s } : m)))
      if (got.error) { mark(sid, { text: got.error, state: 'error', at: Date.now() }); return }
      setMic({ sid, state: 'rec', secs: 0 })
      return
    }
    setMic({ sid, state: 'busy', secs: 0 })
    const blob = await r.stop()
    if (!blob) { setMic({ sid: null, state: null, secs: 0 }); return }
    const res = await sendClip(fetch, sid, blob, threadOf(sid))
    setMic({ sid: null, state: null, secs: 0 })
    done(sid, '', res)
  }
  const onDepth = (sid) => {
    depthRef.current = sid || null
    setDepthState(sid || null)
    if (sid) load()          // its tree at once, then with every poll; a read, never a send
  }
  const onRoute = (r) => { setSide(null); setRoute(r && r.route ? r : null) }
  const onName = async (sid) => {
    setRoute(null)
    if (side === sid) { setSide(null); return }
    setSide(sid); setSideErr('')
    if (threadOf(sid)) return
    try {
      const r = await fetch('/cc/systems/thread', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ system: sid }) })
      const d = await r.json().catch(() => ({}))
      if (r.ok && d.thread) setThreads(m => ({ ...m, [sid]: d.thread }))
      else setSideErr(d.error || `the bridge answered ${r.status}`)
    } catch { setSideErr('the bridge did not answer') }
  }

  const store = () => { try { return window.localStorage } catch { return null } }
  const kept = keptSet(set === null ? null : { set }, tiles, null)
  const tell = (text, undo) => {
    clearTimeout(noteTimer.current)
    setNote({ text, undo })
    noteTimer.current = setTimeout(() => setNote(null), 6000)
  }
  const keep = (next) => {
    setSet(next)
    saveWall(fetch, store(), { set: next }).then(r => { if (r.kept !== 'bridge') tell('kept in this browser only: ' + (r.error || 'the bridge is away')) })
  }
  const onAdd = (sid) => keep(addTo(kept, sid))
  const onLeave = (sid) => {
    const before = kept
    keep(removeFrom(kept, sid))
    if (side === sid) setSide(null)
    if (depthRef.current === sid) onDepth(null)
    tell(`${sid.replace(/^hbar\./, '')} left the orbit`, () => { keep(before); setNote(null) })
  }
  // the brain's new set (WALL-4): taken or declined by his press, never applied silently
  const onFresh = (take) => {
    const f = fresh
    if (!f) return
    setFresh(null)
    if (take) {
      const before = kept
      setSet(f.set)
      saveWall(fetch, store(), { set: f.set, seen: f.stamp }).then(r => { if (r.kept !== 'bridge') tell('kept in this browser only: ' + (r.error || 'the bridge is away')) })
      tell('the brain\'s set is in the orbit', () => { keep(before); setNote(null) })
    } else {
      saveWall(fetch, store(), { seen: f.stamp })
    }
  }
  const onLook = (k) => {
    setLookState(k)
    saveWall(fetch, store(), { look: k })
  }

  // "sent" gives way to the thread's own line once it answers (or after a minute)
  const now = Date.now()
  const shownSent = (sid) => { const s = sent[sid]; return s && !sentOver(s, tileOf(sid), now) ? s : null }
  const lit = tiles.filter(t => cellState(t).on).length
  const running = (data && data.running) || 0
  return (
    <>
      <Head><title>Wall</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className={'wl' + (side || route ? ' with' : '') + (look === 'orbit' ? ' orbit' : '')}>
        {look === 'orbit' ? (
          <main className="wl-orb" aria-label="the orbit">
            <WallOrbit tiles={tiles} set={kept} running={running} symbol={process.env.NEXT_PUBLIC_BRAIN_SYMBOL || '\u210f'}
              sentOf={shownSent} mic={mic} side={side} ready={!!data} onSend={onSend} onMic={onMic} onName={onName}
              onAdd={onAdd} onLeave={onLeave} depth={depth} onDepth={onDepth} waits={(data && data.waits) || null} onRoute={onRoute}
              faint={faint} fresh={fresh} onFresh={onFresh} />
            {data === false ? <p className="wl-note" style={{ position: 'absolute', top: 14, left: 22 }}>The bridge is not answering at /cc/systems.</p> : null}
            <LookSwitch look={look} onLook={onLook} className="wl-lkf" />
            {note ? (
              <div className="wl-toast" role="status">{note.text}{note.undo ? <button onClick={note.undo}>undo</button> : null}</div>
            ) : null}
          </main>
        ) : look === 'grid' ? (
        <main className="wl-main" aria-label="every system, live">
          {tiles.length ? (
            <div className="wl-top" aria-live="polite">
              <span className={lit ? 'on' : ''}><b>{lit}</b> active</span>
              <span><b>{running}</b> jobs running</span>
              <span><b>{tiles.length}</b> systems</span>
              <LookSwitch look={look} onLook={onLook} />
            </div>
          ) : null}
          {data === false ? <p className="wl-note">The bridge is not answering at /cc/systems. The wall fills by itself once it does.</p> : null}
          {data === null ? <p className="wl-note">reading the systems</p> : null}
          <div className="wl-grid">
            {tiles.map(t => (
              <Cell key={t.id} t={t} sent={shownSent(t.id)} open={side === t.id}
                rec={mic.sid === t.id ? mic.state : null} secs={mic.sid === t.id ? mic.secs : 0}
                onSend={onSend} onMic={onMic} onName={onName} />
            ))}
          </div>
        </main>
        ) : <main className="wl-main" aria-label="the wall" />}
        {side ? <Side sid={side} thread={threadOf(side)} err={sideErr} onClose={() => setSide(null)} /> : null}
        {!side && route ? <Beside route={route} onClose={() => setRoute(null)} /> : null}
      </div>
    </>
  )
}
