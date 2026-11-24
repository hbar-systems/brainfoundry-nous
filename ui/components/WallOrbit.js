import React, { useEffect, useRef, useState } from 'react'
import { CENTRE, SET_MAX, cellLine, cellState, orbitPlace, rimPlace, ringOf, kindOf, openOf, addGroups, promptsOf, promptPress, waitsForMore } from '../lib/wall'
import WallDepth from './WallDepth'

// The orbit (WALL-2, 2026-11-24): the wall's personal look. hbar, verbatim: "it should be a full black screen as
// space, feeling and only say 10 systems visible and spaced out and around , in center is hbar symbol which should
// do what... not sure. decide. because 44 at once is too much, most wont be used. rather if i need to add a system
// to the page i just have ability to add. but dont START WITH ALL 44."
//
// True black, a few fixed stars. The kept systems sit as bodies on one wide ring around the brain's own symbol.
// A body at rest is its name, a light when something runs, the job count, and its one live line only when it has
// something to say. Nothing moves on its own except the light. Each body keeps its one small box (type and Enter,
// or the mic), sent in place exactly as the grid sends; a press on the name opens the whole thread beside.
// The centre is the central thread (the world's standing thread): it glows with the total of jobs running; a press
// opens its one box to speak or type to the brain as a whole.
// Adding: the quiet "+" at the bottom of the ring opens the remaining systems as plain names, in place. Leaving:
// press and hold a name, or the "leave" mark while its thread is open. A system outside the ring that runs
// something shows as a faint dot on the outer ring with its count, so nothing running is hidden.
// Phone: the same set as a calm vertical list on black, the symbol on top.
//
// Depth (WALL-3, 2026-11-24): a press on a body's light or count opens its quiet layer in place (WallDepth); the
// centre's count opens the brain's. Nothing else changes at rest. Systems and surfaces are told apart: a body whose
// registry kind is "instrument" or "site" is opened, never talked into, so it has no box; its press opens its page
// beside (or its own address outside). Work on an instrument is said to its parent system or to the centre.

const HOLD_MS = 650
const short = (id) => String(id || '').replace(/^hbar\./, '')
const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

const CSS = `
.wo{--obg:#000;--oink:#ecebe6;--odim:#8f8c85;--omute:#4f4d49;--olit:var(--accent,#c9a96e);--ease:cubic-bezier(.2,.7,.2,1);
  position:relative;background:var(--obg);color:var(--oink);height:calc(100vh - var(--top, 52px));min-height:560px;overflow:hidden;
  font:300 14px/1.4 var(--font-body,system-ui,sans-serif);
  background-image:
    radial-gradient(1px 1px at 8% 12%,rgba(255,255,255,.28),transparent 60%),radial-gradient(1px 1px at 23% 64%,rgba(255,255,255,.16),transparent 60%),
    radial-gradient(1px 1px at 37% 9%,rgba(255,255,255,.2),transparent 60%),radial-gradient(1px 1px at 61% 88%,rgba(255,255,255,.18),transparent 60%),
    radial-gradient(1px 1px at 72% 18%,rgba(255,255,255,.24),transparent 60%),radial-gradient(1px 1px at 91% 41%,rgba(255,255,255,.15),transparent 60%),
    radial-gradient(1.5px 1.5px at 84% 76%,rgba(255,255,255,.22),transparent 60%),radial-gradient(1px 1px at 4% 83%,rgba(255,255,255,.14),transparent 60%),
    radial-gradient(1px 1px at 49% 31%,rgba(255,255,255,.1),transparent 60%),radial-gradient(1px 1px at 15% 38%,rgba(255,255,255,.12),transparent 60%),
    radial-gradient(1px 1px at 96% 7%,rgba(255,255,255,.2),transparent 60%),radial-gradient(1px 1px at 57% 55%,rgba(255,255,255,.08),transparent 60%)}
.wo *{box-sizing:border-box}
.wo :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer}
.wo :focus-visible{outline:1px solid var(--olit);outline-offset:4px;border-radius:8px}
.wo-ring{position:absolute;left:13%;top:15%;width:74%;height:70%;border-radius:50%;border:1px solid rgba(255,255,255,.03);pointer-events:none}
.wo-c{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);display:flex;flex-direction:column;align-items:center;gap:10px;z-index:3}
.wo-sym{position:relative;width:112px;height:112px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.wo-sym .g{font:400 68px/1 var(--font-display,Georgia,serif);color:var(--odim);transition:color 900ms var(--ease),text-shadow 900ms var(--ease)}
.wo-sym::before{content:'';position:absolute;inset:-14px;border-radius:50%;background:radial-gradient(circle,var(--olit) 0%,transparent 66%);opacity:0;transition:opacity 900ms var(--ease);pointer-events:none}
.wo-c.lit .wo-sym .g{color:var(--olit)}
.wo-c.lit .wo-sym::before{opacity:var(--glow,.12);animation:wo-breath 5.5s ease-in-out infinite}
.wo-sym:hover .g{color:var(--oink)}
.wo-cn{font-size:12px;letter-spacing:.14em;color:var(--omute);text-transform:lowercase;font-variant-numeric:tabular-nums;min-height:17px}
.wo-c.lit .wo-cn{color:var(--odim)}
.wo-cbox{display:flex;flex-direction:column;align-items:center;gap:8px;width:340px}
.wo-cbox .wo-ln{max-width:340px;text-align:center}
.wo-th{font-size:12px;color:var(--omute);letter-spacing:.06em}.wo-th:hover{color:var(--olit)}
.wo-b{position:absolute;left:var(--x);top:var(--y);transform:translate(-50%,-26px);width:214px;padding:12px 12px 14px;display:flex;flex-direction:column;align-items:center;gap:6px;z-index:2;
  background:radial-gradient(closest-side,#000 72%,rgba(0,0,0,0))}
.wo-h{display:flex;align-items:center;gap:8px;max-width:100%}
.wo-lt{width:6px;height:6px;border-radius:50%;flex:none;background:var(--omute);opacity:.6;transition:background-color 600ms var(--ease),box-shadow 600ms var(--ease)}
.wo-b.lit .wo-lt,.wo-d .wo-lt{background:var(--olit);opacity:1;box-shadow:0 0 10px var(--olit);animation:wo-breath 3.2s ease-in-out infinite}
.wo-nm{font-size:17px;letter-spacing:.02em;color:var(--odim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;
  user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;transition:color 300ms var(--ease)}
.wo-b.lit .wo-nm,.wo-b:hover .wo-nm,.wo-b:focus-within .wo-nm,.wo-b.open .wo-nm{color:var(--oink)}
.wo-b.open .wo-nm{color:var(--olit)}
.wo-b.hold .wo-nm{color:#e07a5f}
.wo-n{font-size:12px;color:var(--olit);font-variant-numeric:tabular-nums}
.wo-dp{display:inline-flex;align-items:center;padding:7px;margin:-7px -7px -7px -7px;border-radius:999px}
.wo-dpn{padding:4px 6px!important;margin:-4px -6px!important;border-radius:999px}.wo-dpn:hover{color:var(--oink)!important}
.wo-dp:hover .wo-lt{opacity:1;background:var(--odim)}.wo-b.lit .wo-dp:hover .wo-lt{background:var(--olit)}
.wo-dp[aria-expanded=true] .wo-lt{box-shadow:0 0 0 3px rgba(255,255,255,.08)}
.wo-cn{padding:4px 10px;border-radius:999px}button.wo-cn:hover{color:var(--oink)}
.wo-b.inst .wo-nm{font-style:italic}
.wo-op{font-size:11px;color:var(--omute);letter-spacing:.06em}
.wo-add .g{width:100%;display:flex;flex-wrap:wrap;justify-content:center;gap:4px 18px;margin-top:6px}
.wo-add .g p{margin:6px 0 2px}
.wo-lv{font-size:11px;color:var(--omute);letter-spacing:.06em}.wo-lv:hover{color:#e07a5f}
.wo-ln{font-size:12px;line-height:1.4;color:var(--odim);max-width:190px;text-align:center;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.wo-ln.live,.wo-ln.waits{color:var(--oink)}.wo-ln.sent{color:var(--olit)}.wo-ln.error{color:#e07a5f}
.wo-ln .k{color:var(--omute);margin-right:5px}
.wo-box{display:flex;align-items:center;gap:2px;width:160px;height:28px;padding:0 2px 0 12px;border-radius:999px;border:1px solid rgba(255,255,255,.07);
  opacity:.32;transition:opacity 300ms var(--ease),border-color 300ms var(--ease)}
.wo-b:hover .wo-box,.wo-b:focus-within .wo-box,.wo-b.open .wo-box,.wo-box.on,.wo-cbox .wo-box{opacity:1;border-color:rgba(255,255,255,.14)}
.wo-cbox .wo-box{width:340px;height:36px}
.wo-in{flex:1;min-width:0;background:none;border:0;outline:none;color:var(--oink);font:inherit;font-size:13px;padding:0}
.wo-in::placeholder{color:var(--omute)}
.wo-m{display:inline-flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:50%;color:var(--omute);flex:none}
.wo-m:hover{color:var(--olit)}
.wo-m svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.3;stroke-linecap:round;stroke-linejoin:round}
.wo-m.rec{color:#e07a5f;animation:wo-breath 1.2s ease-in-out infinite}.wo-m.busy{opacity:.5;cursor:default}
.wo-t{font-size:11px;color:#e07a5f;font-variant-numeric:tabular-nums}
.wo-d{position:absolute;left:var(--x);top:var(--y);transform:translate(-50%,-50%);display:flex;align-items:center;gap:6px;opacity:.5;z-index:1;
  font-size:11px;color:var(--odim);transition:opacity 300ms var(--ease)}
.wo-d .wo-lt{width:4px;height:4px}
.wo-d:hover,.wo-d:focus-visible{opacity:1}
.wo-d .wo-n{font-size:11px}
.wo-plus{position:absolute;left:var(--x);top:var(--y);transform:translate(-50%,-50%);width:30px;height:30px;border-radius:50%;
  border:1px solid rgba(255,255,255,.1);color:var(--omute);display:flex;align-items:center;justify-content:center;font-size:16px;line-height:1;z-index:2;
  transition:color 300ms var(--ease),border-color 300ms var(--ease)}
.wo-plus:hover,.wo-plus.on{color:var(--oink);border-color:rgba(255,255,255,.24)}
.wo-add{position:absolute;left:50%;bottom:calc(15% + 34px);transform:translateX(-50%);width:min(620px,84%);max-height:46%;overflow:auto;z-index:5;
  display:flex;flex-wrap:wrap;justify-content:center;gap:4px 18px;padding:18px 22px;border-radius:18px;background:#0b0b0c;box-shadow:0 0 0 40px rgba(0,0,0,.55);
  border:1px solid rgba(255,255,255,.07);animation:wo-in 220ms var(--ease)}
.wo-add button{font-size:14px;color:var(--odim);padding:4px 2px;transition:color 200ms var(--ease)}
.wo-add button:hover,.wo-add button:focus-visible{color:var(--oink)}
.wo-add button.lit{color:var(--oink)}.wo-add button.lit::after{content:'';display:inline-block;width:4px;height:4px;border-radius:50%;background:var(--olit);margin-left:6px;vertical-align:middle}
.wo-add p{width:100%;text-align:center;margin:0 0 6px;font-size:11px;letter-spacing:.14em;color:var(--omute);text-transform:lowercase}
.wo-empty{position:absolute;left:50%;top:calc(50% + 120px);transform:translateX(-50%);color:var(--omute);font-size:13px;text-align:center}
.wo-bw{display:flex;flex-direction:column;align-items:center;gap:6px;position:relative}
.wo-b:focus-within{z-index:4}
.wo-pr{display:flex;flex-direction:column;align-items:stretch;gap:1px;width:250px;padding:5px;border-radius:14px;background:rgba(8,8,9,.96);
  border:1px solid rgba(255,255,255,.06);animation:wo-up 160ms var(--ease)}
.wo-cbox .wo-pr{width:340px}
.wo-p{font-size:12.5px!important;line-height:1.35;color:var(--odim)!important;text-align:left!important;padding:6px 9px!important;border-radius:9px;
  display:flex;gap:8px;align-items:baseline;overflow-wrap:anywhere;transition:color 160ms var(--ease),background-color 160ms var(--ease)}
.wo-p:hover,.wo-p:focus-visible{color:var(--oink)!important;background:rgba(255,255,255,.04)}
.wo-p.more::after{content:'…';color:var(--omute)}
.wo-p.armed{color:var(--oink)!important;background:rgba(255,255,255,.05)}
.wo-p .go{margin-left:auto;flex:none;font-size:10px;letter-spacing:.14em;color:var(--olit)}
.wo-f{opacity:.34;font-size:12px;letter-spacing:.03em;padding:6px 8px;border-radius:999px}
.wo-f.run{opacity:.55}
.wo-f:hover,.wo-f:focus-visible{opacity:.95;color:var(--oink)}
.wo-f:disabled{cursor:default}
.wo-fresh{position:absolute;left:50%;top:16px;transform:translateX(-50%);z-index:7;display:flex;gap:14px;align-items:center;font-size:12px;color:var(--odim);
  padding:6px 14px;border-radius:999px;border:1px solid rgba(255,255,255,.07);background:rgba(10,10,11,.9);white-space:nowrap}
.wo-fresh button{font-size:12px;color:var(--omute)}.wo-fresh button:hover{color:var(--oink)}.wo-fresh button.take{color:var(--olit)}
@keyframes wo-up{from{opacity:0;transform:translateY(-3px)}}
@keyframes wo-breath{50%{opacity:.45}}
@keyframes wo-in{from{opacity:0;transform:translate(-50%,6px)}}
@media(max-width:699px){
  .wo{height:auto;min-height:calc(100vh - var(--top, 52px));overflow:visible;display:flex;flex-direction:column;align-items:stretch;padding:28px 18px 40px;gap:0}
  .wo-ring{display:none}
  .wo-c{position:static;transform:none;margin:0 auto 26px}
  .wo-sym{width:84px;height:84px}.wo-sym .g{font-size:52px}
  .wo-cbox,.wo-cbox .wo-box,.wo-cbox .wo-ln{width:100%;max-width:none}
  .wo-b{position:static;transform:none;width:auto;background:none;display:grid;grid-template-columns:minmax(0,1fr);gap:7px;align-items:stretch;padding:15px 2px;border-top:1px solid rgba(255,255,255,.05)}
  .wo-h{justify-content:flex-start}
  .wo-nm{max-width:none;font-size:17px}
  .wo-ln{text-align:left;max-width:none}
  .wo-box{width:100%;opacity:.6;height:34px}
  .wo-d{position:static;transform:none;padding:9px 2px;border-top:1px solid rgba(255,255,255,.04)}
  .wo-plus{position:static;transform:none;margin:22px auto 0}
  .wo-add{position:static;transform:none;width:100%;max-height:none;margin-top:14px;animation:none}
  .wo-empty{position:static;transform:none;margin:8px 0 0}
  .wo-bw{align-items:stretch}.wo-pr,.wo-cbox .wo-pr{width:100%}
  .wo-f{padding:9px 2px;border-radius:0}
  .wo-fresh{position:static;transform:none;margin:0 auto 18px;white-space:normal;flex-wrap:wrap;justify-content:center}
}
@media(hover:none){.wo-box{opacity:.6}}
@media(prefers-reduced-motion:reduce){.wo *{animation:none!important;transition:none!important}}
`

const ICON = {
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>

// The prompts to continue (WALL-4): quiet lines under a focused box, nothing at rest. A press puts the line in the
// box; a second press on the same line sends it, unless it ends in ":" (it waits for him to finish it). Enter sends
// whatever the box holds, as always.
function Prompts({ list, armed, onPress }) {
  if (!list.length) return null
  return (
    <div className="wo-pr" role="group" aria-label="prompts to continue">
      {list.map(p => (
        <button key={p} type="button" className={'wo-p' + (armed === p ? ' armed' : '') + (waitsForMore(p) ? ' more' : '')}
          onMouseDown={e => e.preventDefault()} onClick={() => onPress(p)}
          title={waitsForMore(p) ? 'puts it in the box; you finish it' : armed === p ? 'press again to send it' : 'puts it in the box; a second press sends it'}>
          {p.trim()}{armed === p && !waitsForMore(p) ? <span className="go">send</span> : null}
        </button>
      ))}
    </div>
  )
}

function Box({ sid, rec, secs, onSend, onMic, wide, autoFocus, fill, prompts }) {
  const [text, setText] = useState('')
  const [armed, setArmed] = useState(null)
  const [inside, setInside] = useState(false)
  const inp = useRef(null)
  const wrap = useRef(null)
  // the tree's Talk and the layer's prompts put their ask here (WALL-3, WALL-4); he finishes and sends it
  useEffect(() => { if (fill && fill.text) { setText(fill.text); setArmed(fill.text); if (inp.current) inp.current.focus() } }, [fill && fill.n])   // eslint-disable-line react-hooks/exhaustive-deps
  const recording = rec === 'rec'
  const busy = rec === 'busy'
  const send = (v) => { onSend(sid, v); setText(''); setArmed(null) }
  const key = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && text.trim()) { e.preventDefault(); send(text) }
  }
  const press = (p) => {
    const r = promptPress(armed && text === armed ? armed : null, p)
    if (r.send) { send(r.text); return }
    setText(r.text); setArmed(p)
    const el = inp.current
    if (el) { el.focus(); try { el.setSelectionRange(r.text.length, r.text.length) } catch {} }
  }
  const list = promptsOf({ prompts })
  const who = sid === CENTRE ? 'the brain' : sid
  return (
    <div className={'wo-bw' + (inside ? ' in' : '')} ref={wrap}
      onFocus={() => setInside(true)}
      onBlur={e => { if (!wrap.current || !wrap.current.contains(e.relatedTarget)) setInside(false) }}>
    <div className={'wo-box' + (recording || text ? ' on' : '')}>
      <input ref={inp} className="wo-in" value={text} onChange={e => setText(e.target.value)} onKeyDown={key} autoFocus={autoFocus}
        placeholder={recording ? 'listening' : busy ? 'hearing it' : wide ? 'say it to the brain' : 'say'}
        aria-label={`say to ${who}`} disabled={busy} maxLength={8000} />
      {recording ? <span className="wo-t">{fmt(secs)}</span> : null}
      <button type="button" className={'wo-m' + (recording ? ' rec' : busy ? ' busy' : '')} onClick={() => onMic(sid)} disabled={busy}
        aria-label={recording ? 'stop and send' : busy ? 'sending the recording' : `speak to ${who}`}
        title={recording ? 'tap to stop and send, Esc drops it' : `speak to ${who}`}>
        <Svg k={recording ? 'stop' : 'mic'} />
      </button>
    </div>
    {inside && !recording && !busy ? <Prompts list={list} armed={armed && text === armed ? armed : null} onPress={press} /> : null}
    </div>
  )
}

function Line({ ln }) {
  const lead = ln.kind === 'sent' ? 'sent' : ln.kind === 'job' ? 'job' : ln.kind === 'waits' ? 'waits' : ''
  return (
    <p className={'wo-ln ' + ln.kind} title={ln.text || undefined}>
      {lead ? <span className="k">{lead}</span> : null}{ln.text}
    </p>
  )
}

// A line only when it has something to say: live, just sent, an error, or a running job. A finished answer is
// not repeated at rest.
const speaks = (ln) => ['live', 'waits', 'sent', 'error', 'job'].includes(ln.kind) && !!ln.text

function Body({ t, at, sent, rec, secs, open, onSend, onMic, onName, onLeave, deep, onDepth, fill, onOpen }) {
  const st = cellState(t)
  const inst = kindOf(t) !== 'work'
  const ln = cellLine(t, sent)
  const hold = useRef(null)
  const hold2 = useRef(null)
  const held = useRef(false)
  const [holding, setHolding] = useState(false)
  const down = (e) => {
    if (e.button && e.button !== 0) return
    held.current = false
    setHolding(false)
    clearTimeout(hold.current)
    hold.current = setTimeout(() => setHolding(true), 220)
    clearTimeout(hold2.current)
    hold2.current = setTimeout(() => { held.current = true; setHolding(false); onLeave(t.id) }, HOLD_MS)
  }
  const up = () => { clearTimeout(hold.current); clearTimeout(hold2.current); setHolding(false) }
  const click = () => { if (held.current) { held.current = false; return } if (inst) onOpen(t); else onName(t.id) }
  useEffect(() => () => { clearTimeout(hold.current); clearTimeout(hold2.current) }, [])
  return (
    <section className={'wo-b' + (st.on ? ' lit' : '') + (open ? ' open' : '') + (holding ? ' hold' : '') + (inst ? ' inst' : '')} style={{ '--x': at.x + '%', '--y': at.y + '%' }}
      aria-label={t.id}>
      <div className="wo-h">
        {inst ? <span className="wo-lt" aria-hidden="true" /> : (
          <button type="button" className="wo-dp" data-depth-for={t.id} onClick={() => onDepth(t.id)} aria-expanded={!!deep}
            aria-label={`${t.id} in depth: where it stands, its jobs, its tree`} title="where it stands, its jobs, its tree (nothing is sent)">
            <span className="wo-lt" aria-hidden="true" />
          </button>
        )}
        <button className="wo-nm" onClick={click} onPointerDown={down} onPointerUp={up} onPointerLeave={up} onPointerCancel={up}
          onContextMenu={e => e.preventDefault()} title={inst ? `${t.id}: an instrument; press to open it, hold to let it leave the orbit` : `${t.id}: press to open the whole thread beside; hold to let it leave the orbit`}>
          {short(t.id)}
        </button>
        {st.running ? (inst ? <span className="wo-n" title={`${st.running} running now`}>{st.running}</span> : (
          <button type="button" className="wo-n wo-dpn" data-depth-for={t.id} onClick={() => onDepth(t.id)} aria-expanded={!!deep}
            aria-label={`${st.running} running in ${t.id}: open its depth`} title={`${st.running} running now; press for what each is doing`}>{st.running}</button>
        )) : null}
        {open ? <button className="wo-lv" onClick={() => onLeave(t.id)} title={`take ${t.id} out of the orbit; + brings it back`}>leave</button> : null}
      </div>
      {inst ? <span className="wo-op">{kindOf(t) === 'site' ? 'a site · press to open' : 'an instrument · press to open'}</span> : (
        <>
          {speaks(ln) ? <Line ln={ln} /> : null}
          <Box sid={t.id} rec={rec} secs={secs} onSend={onSend} onMic={onMic} fill={fill} prompts={t.prompts} />
        </>
      )}
    </section>
  )
}

export default function WallOrbit({ tiles, set, running, symbol, sentOf, mic, side, onSend, onMic, onName, onAdd, onLeave, ready,
  depth, onDepth, waits, onRoute, faint, fresh, onFresh }) {
  const [adding, setAdding] = useState(false)
  const [centre, setCentre] = useState(false)
  const [fills, setFills] = useState({})       // sid -> {text, n}: the tree's Talk, put in that system's box
  const deepRef = useRef(depth)
  deepRef.current = depth
  const byId = Object.fromEntries((tiles || []).map(t => [t.id, t]))
  const kept = (set || []).filter(id => byId[id])
  const dots = ringOf(tiles, kept, faint)
  const rest = (tiles || []).filter(t => t.id !== CENTRE && !kept.includes(t.id))
  const world = byId[CENTRE] || { id: CENTRE }
  const wln = cellLine(world, sentOf(CENTRE))
  const lit = running > 0 || cellState(world).on
  const glow = Math.min(0.12 + running * 0.035, 0.42)
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape' && !deepRef.current) { setAdding(false); setCentre(false) } }   // Esc closes the layer first
    document.addEventListener('keydown', k)
    return () => document.removeEventListener('keydown', k)
  }, [])
  const micOf = (sid) => (mic.sid === sid ? mic.state : null)
  const secsOf = (sid) => (mic.sid === sid ? mic.secs : 0)
  const plus = orbitPlace(0, kept.length)
  const onTalk = (sid, text) => {
    setFills(f => ({ ...f, [sid]: { text, n: ((f[sid] || {}).n || 0) + 1 } }))
    if (sid === CENTRE) setCentre(true)
    onDepth(null)
  }
  const onOpen = (t) => {
    const o = openOf(t)
    if (o && o.route) onRoute({ route: o.route, title: short(t.id) })
    else if (o && o.href && typeof window !== 'undefined') window.open(o.href, '_blank', 'noopener')
  }
  // where the layer sits: under its body, or above it in the lower half; kept inside the sky
  const placeOf = (sid) => {
    if (sid === CENTRE) return { left: '50%', top: 'calc(50% + 96px)', transform: 'translateX(-50%)' }
    const i = kept.indexOf(sid)
    if (i < 0) return { left: '50%', top: '18%', transform: 'translateX(-50%)' }
    const at = orbitPlace(i + 1, kept.length)
    const x = Math.min(Math.max(at.x, 16), 84)
    return at.y > 52 ? { left: x + '%', bottom: (100 - at.y + 4) + '%', transform: 'translateX(-50%)' }
      : { left: x + '%', top: 'calc(' + at.y + '% + 34px)', transform: 'translateX(-50%)' }
  }
  const layer = depth && (depth === CENTRE || kept.includes(depth)) ? (
    <WallDepth t={depth === CENTRE ? world : byId[depth]} tiles={tiles} waits={waits} style={placeOf(depth)}
      onClose={() => onDepth(null)} onRead={(sid) => { onDepth(null); onName(sid) }} onTalk={onTalk}
      onRoute={(r) => { onDepth(null); onRoute(r) }} />
  ) : null
  return (
    <div className="wo" aria-label="the orbit: the systems you keep, around the brain">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      {fresh ? (
        <div className="wo-fresh" role="status" data-fresh="1">
          <span>new set from the brain</span>
          <button type="button" className="take" onClick={() => onFresh(true)} title={(fresh.set || []).map(short).join(', ')}>take it</button>
          <button type="button" onClick={() => onFresh(false)} title="keep your own arrangement">keep mine</button>
        </div>
      ) : null}
      <div className="wo-ring" aria-hidden="true" />
      <div className={'wo-c' + (lit ? ' lit' : '')} style={{ '--glow': glow }}>
        <button className="wo-sym" onClick={() => setCentre(c => !c)} aria-expanded={centre}
          title={centre ? 'close the box; the brain keeps going' : 'speak or type to the brain as a whole (the central thread)'}>
          <span className="g">{symbol}</span>
        </button>
        {ready ? (
          <button type="button" className="wo-cn" data-depth-for={CENTRE} onClick={() => onDepth(CENTRE)} aria-expanded={depth === CENTRE}
            aria-live="polite" title="every job running, and what waits for you (nothing is sent)">{running ? `${running} running` : 'quiet'}</button>
        ) : <span className="wo-cn" />}
        {centre ? (
          <div className="wo-cbox">
            {speaks(wln) ? <Line ln={wln} /> : null}
            <Box sid={CENTRE} rec={micOf(CENTRE)} secs={secsOf(CENTRE)} onSend={onSend} onMic={onMic} wide autoFocus fill={fills[CENTRE]} prompts={world.prompts} />
            <button className="wo-th" onClick={() => onName(CENTRE)}>{side === CENTRE ? 'close the thread' : 'the whole thread'}</button>
          </div>
        ) : (speaks(wln) ? <div className="wo-cbox"><Line ln={wln} /></div> : null)}
      </div>
      {depth === CENTRE ? <div className="wo-phl">{layer}</div> : null}
      {kept.map((id, i) => (
        <React.Fragment key={id}>
          <Body t={byId[id]} at={orbitPlace(i + 1, kept.length)} sent={sentOf(id)} open={side === id}
            rec={micOf(id)} secs={secsOf(id)} onSend={onSend} onMic={onMic} onName={onName} onLeave={onLeave}
            deep={depth === id} onDepth={(sid) => onDepth(depth === sid ? null : sid)} fill={fills[id]} onOpen={onOpen} />
          {depth === id ? <div className="wo-phl">{layer}</div> : null}
        </React.Fragment>
      ))}
      {dots.map((d, i) => {
        const at = rimPlace(i, dots.length, kept.length)
        return (
          d.faint ? (
            <button key={d.id} className={'wo-d wo-f' + (d.running || d.live ? ' run' : '')} style={{ '--x': at.x + '%', '--y': at.y + '%' }} data-faint={d.id}
              onClick={() => onAdd(d.id)} disabled={kept.length >= SET_MAX}
              title={`${d.id}: worked on in other threads${d.running ? `, ${d.running} running now` : ''}; press to bring it into the orbit`}>
              {d.running || d.live ? <span className="wo-lt" aria-hidden="true" /> : null}{short(d.id)}{d.running ? <span className="wo-n">{d.running}</span> : null}
            </button>
          ) : (
          <button key={d.id} className="wo-d" style={{ '--x': at.x + '%', '--y': at.y + '%' }} onClick={() => onName(d.id)}
            title={`${d.id} runs ${d.running || 'a turn'} outside the orbit: press to open its thread; + keeps it`}>
            <span className="wo-lt" aria-hidden="true" />{short(d.id)}{d.running ? <span className="wo-n">{d.running}</span> : null}
          </button>
          )
        )
      })}
      {ready && !kept.length ? <p className="wo-empty">nothing kept in the orbit yet; + brings a system in</p> : null}
      {kept.length < SET_MAX && rest.length ? (
        <button className={'wo-plus' + (adding ? ' on' : '')} style={{ '--x': plus.x + '%', '--y': plus.y + '%' }} onClick={() => setAdding(a => !a)}
          aria-expanded={adding} aria-label="add a system to the orbit" title={adding ? 'close' : 'add a system'}>{adding ? '×' : '+'}</button>
      ) : null}
      {adding ? (
        <div className="wo-add" role="group" aria-label="systems outside the orbit">
          {addGroups(rest).map(g => (
            <div key={g.kind} className="g" role="group" aria-label={g.label}>
              <p>{g.kind === 'work' ? 'bring one in' : g.kind === 'instrument' ? 'instruments · they open, you do not talk into them' : 'sites · they open'}</p>
              {g.items.map(t => (
                <button key={t.id} className={cellState(t).on ? 'lit' : ''} onClick={() => { onAdd(t.id); if (kept.length + 1 >= SET_MAX) setAdding(false) }}>{short(t.id)}</button>
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
