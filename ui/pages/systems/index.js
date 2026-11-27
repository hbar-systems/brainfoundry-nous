import Head from 'next/head'
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { readOpen, toggleOpen, readFocus, framesLayout, paneMarks, OPEN_KEY, FOCUS_KEY } from '../../lib/steer'
import SurfaceCard, { SURFACE_CSS } from '../../components/SurfaceCard'
import { systemsFor } from '../../lib/surfaces'
import { switchView } from '../../lib/wall'
import ViewSwitch, { VIEW_CSS } from '../../components/ViewSwitch'

// LINE-TALK-1 (2026-11-25, hbar: "maybe we should try that parallel-systems verticle production surface?"): the corner
// switch goes back to the wall (the same systems and threads); the choice is kept (cc.view) and told to the bridge.
const VIEW_SKIN = { '--vw-bg': '#e6d6bd', '--vw-dim': '#7a6a55', '--vw-ink': '#2b2116', '--vw-on': '#efe3cf' }
const toWall = async () => {
  const store = (() => { try { return window.localStorage } catch { return null } })()
  await switchView(fetch, store, 'wall', 'columns')
  window.location.href = '/wall?view=wall'
}

// SURFACES-1 (2026-11-24): a tile whose system has a card in the register (GET /cc/surfaces) carries the card's pads
// under its name, in the card's hue; a card with no tile (a project, the court) is a tile of its own at the start.
// A pad with an address goes to that page; an ask opens the system's thread beside the tiles with the ask in its box.

// Several system threads at once, steered by a central chat (BOARD-5, 2026-11-23, hbar 2026-11-22: "We are getting
// way too disorganised we have so many threads open"). A press on a tile's name opens its standing thread beside the
// others, up to four (the /panes rule: three side by side, four as two by two); a second press closes it; a fifth
// closes the oldest. The choice survives a reload (localStorage cc.systems.open); /systems?open=a,b opens exactly those. The central chat is the world's
// standing thread, first on the left: when its answer ends with a <steer> line (ui/lib/steer.js) the press sends
// that turn into the named system's thread through POST /cc/threads/<id>/say, and the steered thread reports back
// into the central chat (REPORT-1). The page before this one is kept at /systems/v1; the look before the SURFACES-1 pads at /systems/v2.
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
// Focus (PANES-FOCUS-1 "Lens", 2026-11-27, hbar: "should be possibility to click any one of these and it expands to most
// of the screen so I can read it much better ... and then an easy exit back so we see all four also we are wasting space
// next to the titles of the system"): one press on a pane's title bar (or its corner mark) grows it to the wide column
// at full height in about 220 ms; the other open panes stay as a strip of title bars beside, each one press from the
// focus. Esc (here or from inside the focused pane, outside a text box), a press on its title bar again, or "all"
// goes back to the grid. Nothing remounts: the frames only move, so scroll, drafts and running answers stay; a pane
// in the strip keeps its frame at the size it had, hidden. The focus survives a reload (localStorage cc.systems.focus).
// Right of each name: jobs running, open rows and the ones that wait on him, the time of the thread's last turn
// (ui/lib/steer.js paneMarks; only what GET /cc/systems carries). The frames are told grid or focus ('cc-pane-focus')
// so a small pane folds its tools strip to its one mark.
// The look before this one: commit 186eace of brainfoundry-nous (ui/pages/systems/index.js there).

const KINDS = [
  ['running', 'running now'], ['done_today', 'done today'], ['tasks', 'open tasks'], ['next', 'next'],
]
const SEL = 'cc.systems.sel'          // the one thread of v1; read once so an open thread stays open
const CENTRAL = 'world'               // the central chat: the world's standing thread
const CKEY = 'cc.systems.central'

const CSS = `
.sy-vw{margin:0 12px 10px}
.sy{--bg:#efe3cf;--surface:#e6d6bd;--ink:#2b2116;--dim:#54473a;--muted:#7a6a55;--rust:#a8452b;--ease:cubic-bezier(.2,.7,.2,1);
  --top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));
  background:var(--bg);color:var(--ink);min-height:calc(100vh - var(--top));font:400 16px/1.5 system-ui,-apple-system,sans-serif;box-sizing:border-box}
.sy *{box-sizing:border-box}
.sy :where(a){color:inherit}
.sy :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.sy :focus-visible{outline:2px solid var(--rust);outline-offset:3px;border-radius:6px}
.sy-split{display:grid;grid-template-columns:minmax(0,1fr) minmax(380px,40%);align-items:start}
.sy-split.many{grid-template-columns:minmax(250px,22%) minmax(0,1fr)}
.sy-split.many .sy-left{padding:22px 12px 72px 18px}.sy-split.many .sy-grid{grid-template-columns:1fr;gap:0}
.sy-split.many .sy-nm{font-size:20px}
.sy-frames{position:sticky;top:var(--top);height:calc(100vh - var(--top));display:grid;gap:6px;min-width:0;background:var(--bg)}
.sy-frames .sy-right{position:relative;top:auto;height:auto;min-height:0;border-radius:14px 14px 0 0}
.sy-x{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;color:var(--muted);opacity:.65;border-radius:50%;flex:none}
.sy-x:hover,.sy-x:focus-visible{opacity:1;color:var(--rust)}
.sy-x svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round}
.sy-cen{font-size:12px;color:var(--muted);letter-spacing:.04em;white-space:nowrap}
.sy-tabs{display:none}
.sy-ctl{display:flex;flex-wrap:wrap;gap:6px;margin:0 12px 14px}
.sy-chip{font-size:13px;padding:4px 12px;border-radius:999px;background:var(--surface);color:var(--dim)}
.sy-chip.on{background:var(--ink);color:var(--bg)}
.sy-chip:hover{color:var(--ink)}.sy-chip.on:hover{color:var(--bg)}
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
.sy-res{display:block;margin-top:3px;font-size:13px;line-height:1.45;color:var(--dim)}
.sy-res a{color:inherit;text-decoration:underline;text-decoration-color:var(--muted);text-underline-offset:3px}
.sy-res b{font-weight:500;color:var(--rust)}
.sy-res .sy-f{display:inline-block;margin:2px 10px 0 0;font-size:12px;font-family:var(--font-mono,monospace)}
.sy-res .sy-f.img::before{content:'▣ ';opacity:.6}
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
.sy-ph .sy-nm{font-size:22px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sy-ph .st{font-size:13px;color:var(--muted);white-space:nowrap}
.sy-ph .st.busy{color:var(--rust)}
.sy-back{display:none;font-size:14px;color:var(--muted);padding:4px 8px 4px 0}
.sy-frame{flex:1;width:100%;border:0;background:var(--bg);border-radius:14px 14px 0 0;min-height:0}
.sy-hold{flex:1;display:flex;align-items:center;justify-content:center;padding:24px;color:var(--muted);font-size:15px;text-align:center}
.sy-msg{margin:0 18px 10px;font-size:13px;color:var(--dim)}.sy-msg.err{color:var(--rust)}.sy-msg a{color:var(--rust)}
.sy-note{color:var(--muted);font-size:14px;margin:8px 12px 18px}
.sy-pads{padding:0 10px 10px}
.sy .sf{--text:var(--ink);--surface:var(--bg)}
.sy-t.has-sf{box-shadow:inset 3px 0 0 var(--sfh)}
.sy-alone{margin:0 0 6px}
.sy-ph{cursor:zoom-in;user-select:none}
.sy-right.focus .sy-ph{cursor:zoom-out}
.sy-nmb{flex:1;min-width:0;display:flex;align-items:baseline;gap:12px;overflow:hidden}
.sy-nmb .sy-nm{flex:0 0 auto;max-width:100%}
/* a mark that does not fit wraps onto a hidden second line, whole, never cut; the bar's title says them all */
.sy-marks{flex:1 1 0;min-width:0;display:flex;flex-wrap:wrap;align-items:baseline;column-gap:10px;height:1.6em;overflow:hidden;font-size:13px;line-height:1.6;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.sy-mk.run{color:var(--rust);display:inline-flex;align-items:center;gap:5px}
.sy-mk.run::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor;animation:sy-pulse 2.4s ease-in-out infinite}
.sy-mk.his{color:var(--rust);font-weight:500}
.sy-all{font-size:13px;color:var(--muted);padding:3px 9px;border-radius:999px;background:var(--bg)}
.sy-all:hover,.sy-all:focus-visible{color:var(--rust)}
@media(min-width:900px){
  .sy-split.focus{grid-template-columns:minmax(0,1fr)}.sy-split.focus .sy-left{display:none}
  .sy-right.mini{border-radius:12px;overflow:hidden;cursor:zoom-in;min-height:0}
  .sy-right.mini .sy-ph{min-height:0;padding:10px 14px;flex-wrap:wrap;row-gap:2px}
  .sy-right.mini .sy-nmb{flex-wrap:wrap;row-gap:2px}.sy-right.mini .sy-marks{flex-basis:100%;height:auto}
  .sy-right.mini .sy-ph .sy-nm{font-size:17px}
  .sy-right.mini .sy-m,.sy-right.mini .sy-x,.sy-right.mini .sy-msg,.sy-right.mini .sy-hold{display:none}
  .sy-right.mini .sy-frame{position:absolute;left:0;top:0;visibility:hidden;pointer-events:none;flex:none}
  .sy-right.mini:hover{background:color-mix(in srgb,var(--surface) 80%,var(--rust))}
}
@media(max-width:899px){
  .sy-split{display:block}.sy-left{padding:18px 12px 48px}.sy-grid{grid-template-columns:1fr;gap:2px}
  .sy-right{display:none;position:fixed;left:0;right:0;bottom:0;top:var(--top);height:auto;z-index:40}
  .sy-right.show{display:flex}.sy-back{display:inline-block}.sy-talk{display:block}.sy-frame{border-radius:0}
  .sy-frames{display:contents}.sy-frames .sy-right{position:fixed;top:var(--top);border-radius:0}
  .sy-right .sy-tabs{display:flex;gap:6px;overflow-x:auto;padding:0 18px 8px}
  .sy-all{display:none}.sy-ph{cursor:default}.sy-nmb{flex-wrap:wrap;row-gap:0}.sy-marks{flex-basis:100%;height:auto}
}
@media(prefers-reduced-motion:reduce){.sy-fold,.sy-t{transition:none!important}.sy-m.rec,.sy-mk.run::before{animation:none}}
`

const ICON = {
  link: <path d="M6 3h7v7M13 3 4 12" />,
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
  send: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  grow: <path d="M9.5 2.5h4v4M13.5 2.5 9 7M6.5 13.5h-4v-4M2.5 13.5 7 9" />,
  shrink: <path d="M13.5 6.5h-4v-4M9.5 6.5l4-4M2.5 9.5h4v4M6.5 9.5l-4 4" />,
  done_today: <path d="M3 8.5 6.5 12 13 4.5" />,
  tasks: <rect x="3.5" y="3.5" width="9" height="9" rx="2" />,
  next: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>
const Glyph = ({ k }) => (k === 'running' ? <span className="sy-dot" aria-hidden="true" /> : <span className="sy-g"><Svg k={k} /></span>)

const postJson = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const fmt = (s) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)

// A done job's line carries its result (JOBCARD-1, 2026-11-13): the first sentence it ended with and the files
// it made, each a link, so the tile answers without asking anyone.
function Line({ ln }) {
  const r = ln.result
  return (
    <li className={'sy-ln' + (ln.run ? ' run' : '')}>
      <span>{ln.text}
        {r && (r.first || (r.files && r.files.length)) ? (
          <span className="sy-res">
            {r.rc !== 0 && r.rc != null ? <b>exit {r.rc} </b> : null}
            {r.first ? (r.href ? <a href={r.href} title={r.href}>{r.first}</a> : r.first) : null}
            {(r.files || []).map(f => <a key={f.href} className={'sy-f' + (f.image ? ' img' : '')} href={f.href} title={f.href}>{f.name}</a>)}
          </span>
        ) : null}
      </span>
      {ln.href ? <a className="sy-m" href={ln.href} aria-label="open" title={ln.href}><Svg k="link" /></a> : null}
    </li>
  )
}

function Tile({ t, open, kind, sel, onKind, onName, onTalk, surfs, onPad }) {
  const c = t.counts || {}
  const d = (t.detail || {})[kind] || { count: 0, lines: [] }
  const [all, setAll] = useState(false)
  useEffect(() => { setAll(false) }, [kind, open])
  const busy = KINDS.some(([k]) => c[k])
  const shown = all ? d.lines : d.lines.slice(0, 7)
  return (
    <section className={'sy-t' + (busy ? '' : ' sy-q') + (open ? ' open' : '') + (sel ? ' sel' : '') + (surfs && surfs.length ? ' has-sf' : '')} id={t.id}
      style={surfs && surfs.length ? { '--sfh': surfs[0].hue } : undefined}>
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
      {(surfs || []).map(sf => (
        <div key={sf.name} className="sy-pads">
          <SurfaceCard s={sf} small bare onOpen={(a) => onPad(t.id, sf, a)} onAsk={(a) => onPad(t.id, sf, a)} />
        </div>
      ))}
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

// One open thread: its head (name, what it does now, the mic, open in full, close) over the live chat in a frame.
// `tabs` is the phone's row of the other open threads, so one press moves between them.
function Thread({ sid, tile, thread, err, show, onBack, onClose, central, place, tabs, ask, zoom, keep, onZoom, onAll, asideRef }) {
  const [state, setState] = useState(null)      // the frame's own report ('cc-pane-state')
  const [msg, setMsg] = useState(null)
  const frame = useRef(null)
  useEffect(() => { setState(null); setMsg(null) }, [sid, thread])
  useEffect(() => {
    const on = (e) => {
      if (e.origin !== window.location.origin || !frame.current || e.source !== frame.current.contentWindow) return
      if (e.data && e.data.type === 'cc-pane-state') { setState(e.data); tell() }
    }
    window.addEventListener('message', on)
    return () => window.removeEventListener('message', on)
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  // the frame learns whether it is small (grid) or large (focus): small, it folds its tools strip to one mark
  const zoomRef = useRef(zoom)
  zoomRef.current = zoom
  const tell = () => {
    try { if (frame.current && frame.current.contentWindow) frame.current.contentWindow.postMessage({ type: 'cc-pane-focus', focus: zoomRef.current === 'focus' }, window.location.origin) } catch {}
  }
  useEffect(() => { tell() }, [zoom])   // eslint-disable-line react-hooks/exhaustive-deps
  const c = (tile && tile.counts) || {}
  const st = state && state.busy ? (state.waiting ? 'waits for you' : state.writing ? 'writing' : 'thinking') : ''
  const name = central ? 'central' : sid
  const marks = sid ? paneMarks({ ...(tile || {}), id: name }) : []
  const big = zoom === 'focus'
  const grow = big ? `back to all (Esc)` : `read ${name || 'it'} large; Esc comes back`
  // a press anywhere on the bar that is not one of its marks grows or shrinks the pane
  const onBar = (e) => { if (!onZoom || (e.target.closest && e.target.closest('button, a'))) return; onZoom() }
  const flat = keep && zoom === 'mini' ? { width: keep.w + 'px', height: keep.h + 'px' } : undefined
  return (
    <aside ref={asideRef} className={'sy-right' + (show ? ' show' : '') + (zoom === 'focus' ? ' focus' : zoom === 'mini' ? ' mini' : '')} style={place}
      aria-label={sid ? `${name} thread` : 'thread'}>
      <div className="sy-ph" onClick={onBar} title={onZoom ? grow : undefined}>
        <button className="sy-back" onClick={onBack} aria-label="back to the systems">back</button>
        {onZoom ? (
          <button className="sy-nmb" onClick={onZoom} aria-pressed={big ? 'true' : 'false'} aria-label={grow}
            title={[central ? 'the world thread; its send lines steer the others' : '', ...marks.map(m => m.title), grow].filter(Boolean).join('. ')}>
            <span className="sy-nm">{name || ''}</span>
            {marks.length ? <span className="sy-marks">{marks.map(m => <span key={m.k} className={'sy-mk ' + m.k} title={m.title}>{m.text}</span>)}</span> : null}
          </button>
        ) : <span className="sy-nm">{name || ''}</span>}
        {st ? <span className={'st' + (state && state.busy ? ' busy' : '')}>{st}</span> : null}
        {sid ? <Mic sid={sid} onDone={setMsg} /> : null}
        {thread ? <a className="sy-m" href={`/talk?thread=${encodeURIComponent(thread)}`} aria-label="open the thread in full" title="open the thread in full"><Svg k="link" /></a> : null}
        {onZoom && !big ? <button className="sy-m" onClick={onZoom} aria-label={grow} title={grow}><Svg k="grow" /></button> : null}
        {big && onAll ? <button className="sy-all" onClick={onAll} title="back to all the panes (Esc)">all</button> : null}
        {onClose ? <button className="sy-x" onClick={onClose} aria-label={`close ${name}`} title={`close ${name}; it keeps running`}><Svg k="close" /></button> : null}
      </div>
      {tabs}
      {msg ? (
        <p className={'sy-msg' + (msg.error ? ' err' : '')} role="status">
          {msg.error || msg.text}{msg.path ? <> <a href={`/files?path=${encodeURIComponent(msg.path)}`}>the recording</a></> : null}
        </p>
      ) : null}
      {thread ? (
        <iframe key={thread + (ask ? ':' + ask.n : '')} ref={frame} className="sy-frame" style={flat} onLoad={tell} title={`${name} thread`} src={`/talk?pane=sys-${encodeURIComponent(sid)}&thread=${encodeURIComponent(thread)}${ask ? `&ask=${encodeURIComponent(ask.text)}&n=${ask.n}` : ''}`}
          allow="microphone; clipboard-write" />
      ) : (
        <div className="sy-hold">{err ? err : sid ? `opening the ${name} thread` : 'press a system to talk in it'}</div>
      )}
    </aside>
  )
}

export default function Systems() {
  const [data, setData] = useState(null)        // null: not read yet; false: the bridge did not answer
  const [open, setOpen] = useState({})          // sid -> the kind shown in place
  const [list, setList] = useState([])          // the open system threads, oldest first (at most four)
  const [central, setCentral] = useState(true)  // the central chat beside them
  const [front, setFront] = useState(null)      // phone: the thread shown over the tiles
  const [threads, setThreads] = useState({})    // sid -> thread id, as the bridge gave it
  const [errs, setErrs] = useState({})          // sid -> why its thread did not open
  const [show, setShow] = useState(false)       // phone: a thread over the tiles
  const [ready, setReady] = useState(false)     // the saved choice was read (no save before that)
  const [surfs, setSurfs] = useState([])        // the surfaces register (SURFACES-1)
  const [asks, setAsks] = useState({})          // sid -> {text, n}: a pad's ask, put in that thread's box
  const [focus, setFocusRaw] = useState(null)   // the pane read large (PANES-FOCUS-1); null: the grid
  const [keep, setKeep] = useState({})          // sid -> {w, h}: the size its frame had, kept while it sits in the strip
  const timer = useRef(null)
  const asked = useRef({})
  const els = useRef({})                        // sid -> its <aside>, for the move
  const before = useRef(null)                   // sid -> rect, just before the layout changed

  const load = () => fetch('/cc/systems', { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(d => setData(d && Array.isArray(d.tiles) ? d : false))
    .catch(() => setData(d => (d ? d : false)))

  // a system's one standing thread: the bridge makes it on the first ask, then always gives the same one
  const want = async (sid) => {
    if (!sid || threads[sid] || asked.current[sid]) return
    asked.current[sid] = true
    setErrs(m => ({ ...m, [sid]: '' }))
    try {
      const r = await postJson('/cc/systems/thread', { system: sid })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || !d.thread) { setErrs(m => ({ ...m, [sid]: d.error || `the bridge answered ${r.status}` })); asked.current[sid] = false; return }
      setThreads(m => ({ ...m, [sid]: d.thread }))
    } catch { setErrs(m => ({ ...m, [sid]: 'the bridge did not answer' })); asked.current[sid] = false }
  }

  useEffect(() => {
    const start = () => { if (!timer.current) { load(); timer.current = setInterval(load, 3000) } }
    const stop = () => { if (timer.current) { clearInterval(timer.current); timer.current = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    fetch('/cc/surfaces', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
      .then(d => { if (d && Array.isArray(d.surfaces)) setSurfs(d.surfaces) }).catch(() => {})
    const onKey = (e) => { if (e.key === 'Escape') { setShow(false); setOpen({}); zoomTo(null) } }
    document.addEventListener('keydown', onKey)
    // Esc pressed inside a pane (outside its text box) comes up as cc-pane-key
    const onPaneKey = (e) => {
      if (e.origin !== window.location.origin || !e.data || e.data.type !== 'cc-pane-key' || e.data.key !== 'Escape') return
      zoomTo(null)
    }
    window.addEventListener('message', onPaneKey)
    let l = [], c = true, q = null, f = null
    try {
      const u = new URLSearchParams(window.location.search)
      // ?open=hbar.film,hbar.music opens exactly those (a link from the central chat); ?system=<id> adds one
      l = u.get('open') ? readOpen(JSON.stringify(u.get('open').split(','))) : readOpen(localStorage.getItem(OPEN_KEY), localStorage.getItem(SEL))
      c = localStorage.getItem(CKEY) !== '0'
      q = u.get('system')
      f = u.get('focus') || localStorage.getItem(FOCUS_KEY)   // ?focus=<id> opens that open pane large
    } catch {}
    if (q && q !== CENTRAL) l = toggleOpen(l.filter(x => x !== q), q)
    l = l.filter(x => x !== CENTRAL)
    f = readFocus(f, [...(c ? [CENTRAL] : []), ...l])
    setList(l); setCentral(c); setFocusRaw(f); setReady(true)
    if (f && phone()) { setFront(f); setShow(true) }
    return () => { stop(); document.removeEventListener('visibilitychange', onVis); document.removeEventListener('keydown', onKey); window.removeEventListener('message', onPaneKey) }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ready) return
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(list)); localStorage.setItem(CKEY, central ? '1' : '0') } catch {}
  }, [list, central, ready])
  useEffect(() => {
    if (!ready) return
    try { if (focus) localStorage.setItem(FOCUS_KEY, focus); else localStorage.removeItem(FOCUS_KEY) } catch {}
  }, [focus, ready])

  // The move (about 220 ms): each pane slides from where it was to where it is now (FLIP on transform only, so the
  // frames are never reloaded or resized twice). A pane going into the strip keeps its frame's size, hidden.
  const zoomTo = (next) => {
    const rects = {}, sizes = {}
    Object.entries(els.current).forEach(([sid, el]) => {
      if (!el) return
      rects[sid] = el.getBoundingClientRect()
      const fr = el.querySelector('iframe')
      if (fr) { const r = fr.getBoundingClientRect(); if (r.width > 40 && r.height > 40) sizes[sid] = { w: Math.round(r.width), h: Math.round(r.height) } }
    })
    before.current = rects
    setKeep(k => ({ ...k, ...sizes }))
    setFocusRaw(next)
  }
  useLayoutEffect(() => {
    const was = before.current
    before.current = null
    if (!was) return
    let still = false
    try { still = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch {}
    if (still) return
    Object.entries(els.current).forEach(([sid, el]) => {
      const a = was[sid]
      if (!el || !a || !el.animate) return
      const b = el.getBoundingClientRect()
      if (!b.width || !b.height) return
      const dx = a.left - b.left, dy = a.top - b.top, sx = a.width / b.width, sy = a.height / b.height
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01) return
      el.animate([{ transformOrigin: '0 0', transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` }, { transformOrigin: '0 0', transform: 'none' }],
        { duration: 220, easing: 'cubic-bezier(.2,.7,.2,1)' })
    })
  }, [focus])

  // every open thread (and the central one) gets its thread id; one the board already knows needs no call
  useEffect(() => {
    const known = {}
    ;((data && data.tiles) || []).forEach(t => { if (t.thread) known[t.id] = t.thread })
    setThreads(m => {
      const n = { ...m }
      let moved = false
      Object.entries(known).forEach(([k, v]) => { if (!n[k]) { n[k] = v; moved = true } })
      return moved ? n : m
    })
  }, [data])
  useEffect(() => {
    if (!ready || !data) return
    ;[...(central ? [CENTRAL] : []), ...list].forEach(sid => { if (!threads[sid]) want(sid) })
  }, [ready, data, list, central, threads])   // eslint-disable-line react-hooks/exhaustive-deps

  const phone = () => typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(max-width: 899px)').matches
  const toggle = (sid) => {
    if (sid === CENTRAL) { setCentral(c => !c); return }
    setList(l => toggleOpen(l, sid))
  }
  const onKind = (sid, k) => setOpen(o => (o[sid] === k ? { ...o, [sid]: null } : { ...o, [sid]: k }))
  const onName = (sid) => {
    const t = ((data && data.tiles) || []).find(x => x.id === sid)
    const first = (KINDS.find(([k]) => t && t.counts && t.counts[k]) || KINDS[0])[0]
    if (phone()) { setOpen(o => ({ ...o, [sid]: o[sid] ? null : first })); return }
    toggle(sid)
  }
  // phone: "say it here" opens that thread over the tiles (and keeps it in the open list)
  const onTalk = (sid) => {
    if (sid === CENTRAL) setCentral(true)
    else setList(l => (l.includes(sid) ? l : toggleOpen(l, sid)))
    setFront(sid); setShow(true); setFocusRaw(sid)
  }

  const tiles = (data && data.tiles) || []
  const { bySystem, alone } = systemsFor(tiles, surfs)
  // a pad: an address goes there; an ask opens the system's thread with the ask in its box (a card with no tile: the chat)
  const onPad = (sid, sf, a) => {
    if (a.kind !== 'ask') { window.location.assign(a.open); return }
    if (!sid) { window.location.assign('/talk?ask=' + encodeURIComponent(a.ask)); return }
    setAsks(m => ({ ...m, [sid]: { text: a.ask, n: ((m[sid] && m[sid].n) || 0) + 1 } }))
    setList(l => (l.includes(sid) ? l : toggleOpen(l, sid)))
    setFront(sid); if (phone()) setShow(true)
    if (focus) zoomTo(sid)
  }
  const tileOf = (sid) => tiles.find(t => t.id === sid)
  const running = data && data.running
  const isOpen = (sid) => (sid === CENTRAL ? central : list.includes(sid))
  const shown = [...(central ? [CENTRAL] : []), ...list]
  const many = shown.length > 0
  const fz = readFocus(focus, shown)            // a closed pane is never the focus
  const lay = framesLayout(shown, fz, central ? CENTRAL : null)
  const frontSid = front && shown.includes(front) ? front : shown[shown.length - 1]
  const frameStyle = { gridTemplateColumns: lay.cols, gridTemplateRows: lay.rows }
  const placeOf = (sid) => lay.place[sid]
  const zoomOf = (sid) => (fz ? (sid === fz ? 'focus' : 'mini') : 'grid')
  // the bar's press: on a phone the pane is already the whole screen; on a desk it grows, or goes back to all
  const onZoom = (sid) => { if (phone()) return; zoomTo(fz === sid ? null : sid) }
  const tabs = shown.length > 1 ? (
    <div className="sy-tabs" role="tablist">
      {shown.map(sid => (
        <button key={sid} role="tab" aria-selected={sid === frontSid ? 'true' : 'false'} className={'sy-chip' + (sid === frontSid ? ' on' : '')}
          onClick={() => { setFront(sid); setFocusRaw(sid) }}>{sid === CENTRAL ? 'central' : sid}</button>
      ))}
    </div>
  ) : null
  return (
    <>
      <Head><title>Systems</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS + SURFACE_CSS + VIEW_CSS }} />
      <div className="sy">
        <div className={'sy-split' + (many ? ' many' : '') + (many && fz ? ' focus' : '')}>
          <main className="sy-left" aria-label={data && data.built ? `Systems, read ${data.built}` : 'Systems'}>
            {data === false ? <p className="sy-note">The bridge is not answering at /cc/systems. The tiles fill by themselves once it does.</p> : null}
            <div className="sy-vw"><ViewSwitch view="columns" style={VIEW_SKIN} onPick={(v) => { if (v === 'wall') toWall() }} /></div>
            {tiles.length ? (
              <div className="sy-key" aria-hidden="true">
                <span><Glyph k="running" />{running ? `${running} running now` : 'running now'}</span>
                <span><Glyph k="done_today" />done today</span>
                <span><Glyph k="tasks" />open tasks</span>
                <span><Glyph k="next" />next</span>
              </div>
            ) : null}
            {tiles.length ? (
              <div className="sy-ctl">
                {/* desktop: a chip opens or closes its thread; phone: it shows that thread over the tiles */}
                <button className={'sy-chip' + (central ? ' on' : '')} onClick={() => (phone() && central ? onTalk(CENTRAL) : toggle(CENTRAL))} aria-pressed={central ? 'true' : 'false'}
                  title="the world's thread, which steers the others">central</button>
                {list.map(sid => (
                  <button key={sid} className="sy-chip on" onClick={() => (phone() ? onTalk(sid) : toggle(sid))} aria-pressed="true" title={`close ${sid}`}>{sid}</button>
                ))}
                {list.length < 4 ? <span className="sy-cen" style={{ alignSelf: 'center' }}>{list.length ? 'press a name to add one' : 'press a name to open its thread'}</span> : null}
              </div>
            ) : null}
            <div className="sy-grid">
              {alone.map(sf => (
                <div key={'sf-' + sf.name} className="sy-alone">
                  <SurfaceCard s={sf} small onOpen={(a) => onPad(null, sf, a)} onAsk={(a) => onPad(null, sf, a)} />
                </div>
              ))}
              {tiles.map(t => (
                <Tile key={t.id} t={t} open={!!open[t.id]} kind={open[t.id] || 'running'} sel={isOpen(t.id)}
                  onKind={onKind} onName={onName} onTalk={onTalk} surfs={bySystem[t.id]} onPad={onPad} />
              ))}
            </div>
          </main>
          {many ? (
            <div className="sy-frames" style={frameStyle}>
              {shown.map(sid => (
                <Thread key={sid} sid={sid} tile={tileOf(sid)} thread={threads[sid] || null} err={errs[sid] || ''}
                  central={sid === CENTRAL} place={placeOf(sid)} show={show && sid === frontSid} tabs={tabs}
                  onBack={() => { setShow(false); setFocusRaw(null) }} onClose={() => toggle(sid)} ask={asks[sid] || null}
                  zoom={zoomOf(sid)} keep={keep[sid] || null} onZoom={() => onZoom(sid)} onAll={() => zoomTo(null)}
                  asideRef={(el) => { if (el) els.current[sid] = el; else delete els.current[sid] }} />
              ))}
            </div>
          ) : (
            <Thread sid={null} tile={null} thread={null} err="" show={false} onBack={() => setShow(false)} />
          )}
        </div>
      </div>
    </>
  )
}
