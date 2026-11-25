import React, { useEffect, useRef } from 'react'
import { fanPlace, pinFirst } from '../lib/wall'
import { MARK } from './SurfaceCard'

// A system's instruments on the orbit (WALL-5, 2026-11-24). hbar, on the live wall: "okay but where is my musical
// surfaces tho those i wanted actually -- i want to create more than the hbar.ink". The register names them
// (GET /cc/surfaces, a file's "instruments"), nothing here knows one. At rest only the pinned ones are out, small
// bodies beside their system; a press on the system's name (a hover on a laptop) fans the rest out beside it, each one
// word in its own hue with its own mark. A press opens the instrument beside the wall (an `ask` one puts its words in
// the system's box, nothing sent). Press and hold, or the small ring beside an open one, keeps it out (pinned, saved
// with the set). Esc folds the fan. Phone: the same items as a row of chips under the system's name.

const HOLD_MS = 650

export const FAN_CSS = `
.wf{position:absolute;left:50%;top:26px;width:0;height:0;z-index:4}
.wf-i{position:absolute;left:0;top:0;transform:translate(calc(var(--ax) + var(--dx)), calc(-50% + var(--dy)));display:flex;align-items:center;gap:2px;
  --hl:color-mix(in oklab, var(--h, #888) 62%, #fff)}
.wf-i.in{animation:wf-in 200ms cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--k) * 24ms)}
.wf-i.l{flex-direction:row-reverse}
.wf-o{display:flex;align-items:center;gap:6px;padding:5px 10px 5px 7px;border-radius:999px;white-space:nowrap;font-size:13px;letter-spacing:.02em;
  color:var(--hl);background:color-mix(in oklab, var(--h, #888) 16%, #050505);border:1px solid color-mix(in oklab, var(--h, #888) 38%, transparent);
  user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;transition:background-color 160ms ease,color 160ms ease,transform 120ms ease}
.wf-o:hover,.wf-o:focus-visible{color:#fff;background:color-mix(in oklab, var(--h, #888) 30%, #050505)}
.wf-o:active{transform:scale(.97)}
.wf-o.hold{color:#fff;box-shadow:0 0 0 3px color-mix(in oklab, var(--h, #888) 30%, transparent)}
.wf-o svg{width:14px;height:14px;fill:var(--hl);stroke:var(--hl);flex:none}
.wf-i.pin .wf-o{border-color:color-mix(in oklab, var(--h, #888) 60%, transparent)}
.wf-i:not(.pin) .wf-o{opacity:.92}
.wf-p{width:18px;height:18px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:var(--hl);opacity:.55}
.wf-p:hover,.wf-p:focus-visible{opacity:1}
.wf-p i{width:7px;height:7px;border-radius:50%;border:1.3px solid currentColor;display:block}
.wf-p[aria-pressed=true]{opacity:.9}.wf-p[aria-pressed=true] i{background:currentColor}
@keyframes wf-in{from{opacity:0;transform:translate(calc(var(--ax) + var(--dx) * .7), calc(-50% + var(--dy) * .4)) scale(.92)}}
@media(max-width:699px){
  .wf{position:static;width:auto;height:auto;display:flex;flex-wrap:wrap;gap:6px 6px}
  .wf-i{position:static;transform:none}
  .wf-i.in{animation:none}
}
@media(prefers-reduced-motion:reduce){.wf-i.in{animation:none}.wf-o{transition:none}}
`

function Item({ inst, k, at, n, pinned, open, fresh, onOpen, onPin }) {
  const hold = useRef(null)
  const held = useRef(false)
  const btn = useRef(null)
  const draw = MARK[inst.mark] || MARK.dot
  const p = fanPlace(k, n, at)
  const down = (e) => {
    if (e.button && e.button !== 0) return
    held.current = false
    clearTimeout(hold.current)
    hold.current = setTimeout(() => {
      held.current = true
      if (btn.current) btn.current.classList.add('hold')
      onPin(inst.name)
    }, HOLD_MS)
  }
  const up = () => { clearTimeout(hold.current); if (btn.current) btn.current.classList.remove('hold') }
  const click = () => { if (held.current) { held.current = false; return } onOpen(inst) }
  useEffect(() => () => clearTimeout(hold.current), [])
  const what = inst.open ? 'press to open it beside' : 'press to put it in the box'
  return (
    <div className={'wf-i' + (pinned ? ' pin' : '') + (fresh ? ' in' : '') + (p.side < 0 ? ' l' : '')} data-instrument={inst.name}
      style={{ '--h': inst.hue, '--dx': p.dx + 'px', '--dy': p.dy + 'px', '--k': k, '--ax': p.side < 0 ? '-100%' : '0%' }}>
      <button ref={btn} type="button" className="wf-o" onClick={click} onPointerDown={down} onPointerUp={up} onPointerLeave={up}
        onPointerCancel={up} onContextMenu={e => e.preventDefault()}
        title={`${inst.label}${inst.note ? ': ' + inst.note : ''} (${what}; hold to ${pinned ? 'fold it back in' : 'keep it out'})`}>
        <svg viewBox="0 0 64 64" aria-hidden="true">{draw()}</svg>{inst.label}
      </button>
      {open ? (
        <button type="button" className="wf-p" aria-pressed={pinned} onClick={() => onPin(inst.name)}
          aria-label={pinned ? `let ${inst.label} fold back in` : `keep ${inst.label} out on the orbit`}
          title={pinned ? 'kept out: press to fold it back in' : 'keep it out on the orbit'}><i /></button>
      ) : null}
    </div>
  )
}

export default function WallFan({ host, items, pinned, open, at, onOpen, onPin }) {
  const pins = Array.isArray(pinned) ? pinned : []
  const list = pinFirst(items, pins)
  const shown = list.map((inst, k) => ({ inst, k })).filter(x => open || pins.includes(x.inst.name))
  if (!shown.length) return null
  return (
    <div className="wf" role="group" aria-label={`${host}: instruments`} data-fan-for={host} data-fan-open={open ? 'true' : 'false'}>
      {shown.map(({ inst, k }) => (
        <Item key={inst.name} inst={inst} k={k} n={list.length} at={at} pinned={pins.includes(inst.name)} open={open}
          fresh={open && !pins.includes(inst.name)} onOpen={onOpen} onPin={onPin} />
      ))}
    </div>
  )
}
