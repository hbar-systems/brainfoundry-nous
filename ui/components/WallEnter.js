import React, { useEffect, useRef, useState } from 'react'
import { CENTRE, cellLine, cellState, nowOf, latestOf, shortcutsOf, waitsForMore, depthOf } from '../lib/wall'
import { MARK } from './SurfaceCard'

// Entering a system (WALL-6, 2026-11-26). hbar, 00:51 Bratislava: "the wall is now main one i want to begin with but
// the thing is it just lets me see the current system but not so much easy", and on the centre box: "can i only send
// this? i cant type a message and it will go through?". One press on a system's name opens this card over the orbit:
//   its now-line (the card's "Now:"), and what its thread is saying while it works;
//   its box, EMPTY and focused, "type your own message": Enter or the arrow sends what he typed, in place;
//   its shortcuts, separate chips under the box ("or start from"): a press puts the words in the box for him to
//     change and send; nothing is sent by a chip alone;
//   its latest thing to look at or hear (the card's "Latest:"), opening beside the wall on the console;
//   its instruments (the register), each opening beside, with a small ring that keeps one out on the wall (pinned,
//     saved with the set; WALL-5's fan held that mark); the whole thread beside.
// Back: the "back" press, a press outside the card, or Esc. Nothing navigates; the orbit stays under it.

export const ENTER_CSS = `
.we-veil{position:absolute;inset:0;z-index:20;background:rgba(0,0,0,.62);display:flex;align-items:center;justify-content:center;padding:18px;
  animation:we-fade 140ms ease-out}
.we{width:min(560px,100%);max-height:calc(100% - 12px);overflow:auto;background:#0d0d0e;border:1px solid rgba(255,255,255,.12);border-radius:18px;
  padding:18px 20px 16px;display:flex;flex-direction:column;gap:14px;color:#ecebe6;box-shadow:0 24px 80px rgba(0,0,0,.7);animation:we-up 160ms cubic-bezier(.2,.7,.2,1)}
.we *{box-sizing:border-box}
.we :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.we :focus-visible{outline:2px solid var(--accent,#c9a96e);outline-offset:2px;border-radius:8px}
.we .we-in:focus-visible{outline:none}
.we-h{display:flex;align-items:center;gap:10px}
.we-lt{width:8px;height:8px;border-radius:50%;background:#77746d;flex:none}
.we-h.lit .we-lt{background:var(--accent,#c9a96e);box-shadow:0 0 10px var(--accent,#c9a96e)}
.we-nm{font-size:22px;letter-spacing:.01em;font-weight:400;margin:0;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.we-n{font-size:13px;color:var(--accent,#c9a96e)}
.we-back{font-size:13px;color:#b9b6ae;padding:6px 12px!important;border-radius:999px;border:1px solid rgba(255,255,255,.16)!important}
.we-back:hover{color:#fff;border-color:rgba(255,255,255,.32)!important}
.we-now{font-size:15px;line-height:1.45;color:#d6d3cb;margin:0}
.we-live{font-size:13px;line-height:1.4;color:#ecebe6;margin:-6px 0 0}.we-live .k{color:#a29f97;margin-right:6px}
.we-live.sent{color:var(--accent,#c9a96e)}.we-live.error{color:#f08b70}
.we-box{display:flex;align-items:center;gap:4px;height:46px;padding:0 5px 0 16px;border-radius:999px;background:#151517;border:1px solid rgba(255,255,255,.22)}
.we-box:focus-within{border-color:var(--accent,#c9a96e)}
.we-in{flex:1;min-width:0;background:none;border:0;outline:none;color:#f4f3ef;font:inherit;font-size:15px;padding:0}
.we-in::placeholder{color:#9c998f}
.we-ic{display:inline-flex;width:36px;height:36px;align-items:center;justify-content:center;border-radius:50%;color:#b9b6ae;flex:none}
.we-ic:hover{color:#fff}.we-ic:disabled{opacity:.35;cursor:default}
.we-ic.go{background:var(--accent,#c9a96e);color:#111}.we-ic.go:disabled{background:#2a2a2c;color:#8a877f;opacity:1}
.we-ic.rec{color:#f08b70}
.we-ic svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.we-t{font-size:12px;color:#f08b70;font-variant-numeric:tabular-nums}
.we-k{font-size:11px;letter-spacing:.14em;text-transform:lowercase;color:#a29f97;margin:0 0 -6px}
.we-chips{display:flex;flex-wrap:wrap;gap:8px}
.we-chip{font-size:13px!important;line-height:1.3;color:#d6d3cb!important;padding:7px 12px!important;border-radius:12px;background:#1a1a1c!important;
  border:1px solid rgba(255,255,255,.1)!important;max-width:100%;overflow-wrap:anywhere}
.we-chip:hover,.we-chip:focus-visible{color:#fff!important;border-color:rgba(255,255,255,.28)!important}
.we-chip.more::after{content:' …';color:#a29f97}
.we-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.we-lk{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:#ecebe6;text-decoration:none;padding:7px 12px;border-radius:12px;
  border:1px solid rgba(255,255,255,.14);background:#151517;max-width:100%}
.we-lk:hover{border-color:rgba(255,255,255,.32)}
.we-lk .m{font-size:11px;letter-spacing:.12em;color:#a29f97;text-transform:lowercase}
.we-ins{display:inline-flex;align-items:center;gap:6px;font-size:13px!important;padding:6px 11px 6px 8px!important;border-radius:999px;
  color:color-mix(in oklab, var(--h,#888) 45%, #fff)!important;background:color-mix(in oklab, var(--h,#888) 16%, #070707)!important;
  border:1px solid color-mix(in oklab, var(--h,#888) 45%, transparent)!important}
.we-ins svg{width:14px;height:14px;fill:currentColor;stroke:currentColor}
.we-iw{display:inline-flex;align-items:center;gap:2px}
.we-pin{width:24px;height:24px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:color-mix(in oklab, var(--h,#888) 45%, #fff)!important}
.we-pin i{width:8px;height:8px;border-radius:50%;border:1.4px solid currentColor;display:block}
.we-pin[aria-pressed=true] i{background:currentColor}
.we-foot{display:flex;gap:16px;align-items:center;font-size:13px;color:#b9b6ae;border-top:1px solid rgba(255,255,255,.08);padding-top:12px}
.we-foot button:hover{color:#fff}
.we-foot .esc{margin-left:auto;font-size:11px;color:#8a877f;letter-spacing:.06em}
@keyframes we-fade{from{opacity:0}}
@keyframes we-up{from{opacity:0;transform:translateY(6px)}}
@media(max-width:759px){.we-veil{position:fixed;padding:10px;align-items:flex-start;padding-top:calc(var(--top,52px) + 10px)}.we{max-height:calc(100vh - var(--top,52px) - 20px)}}
@media(prefers-reduced-motion:reduce){.we-veil,.we{animation:none}}
`

const ICON = {
  mic: <><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></>,
  stop: <rect x="4.5" y="4.5" width="7" height="7" rx="1.5" />,
  go: <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" />,
}
const Svg = ({ k }) => <svg viewBox="0 0 16 16" aria-hidden="true">{ICON[k]}</svg>
const short = (id) => String(id || '').replace(/^hbar\./, '')
const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function WallEnter({ t, sent, rec, secs, tools, onSend, onMic, onClose, onWhole, onRoute, onTool, side, pinned, onPin }) {
  const [text, setText] = useState('')
  const inp = useRef(null)
  const sid = t.id
  const centre = sid === CENTRE
  const st = cellState(t)
  const ln = cellLine(t, sent)
  const now = nowOf(t) || depthOf(t).summary.text
  const latest = latestOf(t)
  const cuts = shortcutsOf(t, 4)
  const recording = rec === 'rec'
  const busy = rec === 'busy'
  useEffect(() => { if (inp.current) inp.current.focus() }, [])
  const send = () => { const v = text.trim(); if (!v) return; onSend(sid, v); setText('') }
  const key = (e) => { if (e.key === 'Enter' && !e.shiftKey && text.trim()) { e.preventDefault(); send() } }
  const cut = (p) => {
    const v = waitsForMore(p) ? p : p.trim()
    setText(v)
    const el = inp.current
    if (el) { el.focus(); setTimeout(() => { try { el.setSelectionRange(v.length, v.length) } catch {} }, 0) }
  }
  const showLive = ['live', 'waits', 'sent', 'error'].includes(ln.kind) && ln.text
  const lead = ln.kind === 'sent' ? 'sent' : ln.kind === 'waits' ? 'waits' : ln.kind === 'live' ? 'now' : ''
  const name = centre ? 'the brain' : short(sid)
  const open = (l) => {
    if (l.route) onRoute({ route: l.href, title: l.label })
    else if (typeof window !== 'undefined') window.open(l.href, '_blank', 'noopener')
  }
  return (
    <div className="we-veil" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }} data-enter-for={sid}>
      <section className="we" role="dialog" aria-modal="true" aria-label={`${name}: entered`}>
        <div className={'we-h' + (st.on ? ' lit' : '')}>
          <span className="we-lt" aria-hidden="true" />
          <h2 className="we-nm">{name}</h2>
          {st.running ? <span className="we-n">{st.running} running</span> : null}
          <button type="button" className="we-back" onClick={onClose} aria-label="back to the wall">back</button>
        </div>
        <p className="we-now" data-now-for={sid}>{now}</p>
        {showLive ? <p className={'we-live ' + ln.kind}>{lead ? <span className="k">{lead}</span> : null}{ln.text}</p> : null}
        <div className="we-box">
          <input ref={inp} className="we-in" value={text} onChange={e => setText(e.target.value)} onKeyDown={key} maxLength={8000} disabled={busy}
            placeholder={recording ? 'listening' : busy ? 'hearing it' : 'type your own message'} aria-label={`your message to ${name}`} />
          {recording ? <span className="we-t">{fmt(secs)}</span> : null}
          <button type="button" className={'we-ic' + (recording ? ' rec' : '')} onClick={() => onMic(sid)} disabled={busy}
            aria-label={recording ? 'stop and send' : `speak to ${name}`}><Svg k={recording ? 'stop' : 'mic'} /></button>
          <button type="button" className="we-ic go" onClick={send} disabled={!text.trim() || busy} aria-label="send">
            <Svg k="go" />
          </button>
        </div>
        {cuts.length ? (
          <>
            <p className="we-k">or start from a shortcut (it goes in the box; you send it)</p>
            <div className="we-chips" role="group" aria-label="shortcuts">
              {cuts.map(p => (
                <button key={p} type="button" className={'we-chip' + (waitsForMore(p) ? ' more' : '')} onClick={() => cut(p)}>{p.trim()}</button>
              ))}
            </div>
          </>
        ) : null}
        {latest || (tools && tools.length) ? (
          <>
            <p className="we-k">look and hear</p>
            <div className="we-row">
              {latest ? (
                <a className="we-lk" href={latest.href} target={latest.route ? undefined : '_blank'} rel="noopener noreferrer" data-latest-for={sid}
                  onClick={(e) => { if (latest.route) { e.preventDefault(); open(latest) } }}>
                  <span className="m">{latest.hear ? 'hear' : 'latest'}</span>{latest.label}
                </a>
              ) : null}
              {(tools || []).map(i => {
                const draw = MARK[i.mark] || MARK.dot
                const on = (pinned || []).includes(i.name)
                return (
                  <span key={i.name} className="we-iw" style={{ '--h': i.hue }} data-instrument={i.name}>
                    <button type="button" className="we-ins" onClick={() => onTool(sid, i)}>
                      <svg viewBox="0 0 64 64" aria-hidden="true">{draw()}</svg>{i.label}
                    </button>
                    {onPin ? (
                      <button type="button" className="we-pin" aria-pressed={on} onClick={() => onPin(i.name)}
                        aria-label={on ? `let ${i.label} fold back in` : `keep ${i.label} out on the wall`}><i /></button>
                    ) : null}
                  </span>
                )
              })}
            </div>
          </>
        ) : null}
        <div className="we-foot">
          <button type="button" onClick={() => onWhole(sid)}>{side === sid ? 'close the whole thread' : 'the whole thread beside'}</button>
          <span className="esc">Esc goes back</span>
        </div>
      </section>
    </div>
  )
}
