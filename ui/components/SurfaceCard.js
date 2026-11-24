import React from 'react'
import { daysLeft } from '../lib/surfaces'

// A system's card (SURFACES-1, 2026-11-24): the register's hue and one strong mark, its name, one line, and three to five
// pads. In the chat (keys on) the pads carry their numbers, 1 to 5 press them; on /systems (small) they sit under a tile.
// A pad with an address calls onOpen(action), one with an ask calls onAsk(action); the page decides what that does.
// Colours follow the console's skin (var(--text), var(--surface), var(--muted)); the hue only tints and draws the mark,
// so every system has its own character and none of them fights the skin.

const MARK = {
  dot: () => <circle cx="32" cy="32" r="14" />,
  wave: () => <path d="M4 32c5-14 9-14 14 0s9 14 14 0 9-14 14 0 9 14 14 0" fill="none" strokeWidth="5" strokeLinecap="round" />,
  frames: () => (
    <g>
      <rect x="6" y="14" width="52" height="36" rx="4" fill="none" strokeWidth="4" />
      {[12, 22, 32, 42, 52].map(x => <rect key={'t' + x} x={x - 2.5} y="18" width="5" height="5" rx="1" />)}
      {[12, 22, 32, 42, 52].map(x => <rect key={'b' + x} x={x - 2.5} y="41" width="5" height="5" rx="1" />)}
      <rect x="16" y="27" width="32" height="10" rx="2" opacity=".55" />
    </g>
  ),
  stroke: () => <path d="M8 46c10-2 14-26 26-28s8 22 22 16" fill="none" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />,
  ring: () => (
    <g fill="none" strokeLinecap="round">
      <circle cx="32" cy="32" r="22" strokeWidth="5" strokeDasharray="110 30" />
      <circle cx="32" cy="32" r="11" strokeWidth="4" opacity=".55" />
      <path d="M50 14l4 10-10 1" strokeWidth="4" strokeLinejoin="round" />
    </g>
  ),
  grain: () => (
    <g>
      {[0, 1, 2, 3].map(r => [0, 1, 2, 3].map(c => (
        <rect key={`${r}${c}`} x={8 + c * 13} y={8 + r * 13} width="10" height="10" rx="2" opacity={((r * 3 + c * 5) % 4 + 1) / 4} />
      )))}
    </g>
  ),
  scales: () => (
    <g fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d="M32 10v42M20 54h24M12 18h40" strokeWidth="4" />
      <path d="M12 18 5 36h14zM52 18l-7 18h14z" strokeWidth="3.5" />
    </g>
  ),
}

function Mark({ s, size }) {
  if (s.mark === 'count' && s.count_to) {
    const n = daysLeft(s.count_to)
    if (n != null) {
      return (
        <span className="sf-count" aria-label={n >= 0 ? `${n} days left` : 'passed'}>
          <b>{n >= 0 ? n : '·'}</b><i>{n === 1 ? 'day' : 'days'}</i>
        </span>
      )
    }
  }
  const draw = MARK[s.mark] || MARK.dot
  return (
    <svg className="sf-mark" viewBox="0 0 64 64" width={size} height={size} aria-hidden="true">
      {draw()}
    </svg>
  )
}

export const SURFACE_CSS = `
.sf{--hue:#888;--tint:color-mix(in srgb, var(--hue) 13%, var(--surface, #f4efe6));--ink2:color-mix(in oklab, var(--hue) 80%, var(--text, #222));
  position:relative;display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 16px;align-items:center;
  background:var(--tint);color:var(--text, #222);border-radius:18px;padding:16px 18px 16px 16px;max-width:660px;overflow:hidden;
  font-size:16px;line-height:1.4;box-sizing:border-box}
.sf *{box-sizing:border-box}
.sf::before{content:'';position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--hue)}
.sf-mark{fill:var(--ink2);stroke:var(--ink2);flex:none;display:block}
.sf-count{display:flex;flex-direction:column;align-items:center;justify-content:center;width:64px;color:var(--ink2);line-height:1}
.sf-count b{font:600 40px/1 Lora,Georgia,serif;font-variant-numeric:tabular-nums}
.sf-count i{font-style:normal;font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-top:3px;opacity:.8}
.sf-hd{min-width:0}
.sf-nm{font:400 26px/1.15 Lora,Georgia,serif;margin:0;color:var(--text, #222);overflow-wrap:anywhere}
.sf-ln{margin:2px 0 0;font-size:14px;color:var(--muted, #777)}
.sf-pads{grid-column:1 / -1;display:grid;grid-template-columns:repeat(var(--n, 4),minmax(0,1fr));gap:8px;margin-top:10px}
.sf-pad{all:unset;box-sizing:border-box;cursor:pointer;display:flex;flex-direction:column;gap:2px;min-height:58px;padding:9px 12px 10px;border-radius:12px;
  background:var(--surface, #fff);color:var(--text, #222);box-shadow:inset 0 0 0 1px color-mix(in srgb, var(--hue) 28%, transparent);
  transition:transform 140ms cubic-bezier(.2,.7,.2,1), box-shadow 140ms, background-color 140ms}
.sf-pad:hover{box-shadow:inset 0 0 0 1.5px var(--hue)}
.sf-pad:active,.sf-pad.hit{transform:scale(.97);background:color-mix(in srgb, var(--hue) 22%, var(--surface, #fff))}
.sf-pad:focus-visible{outline:2px solid var(--hue);outline-offset:2px}
.sf-pl{display:flex;align-items:baseline;gap:8px;font-size:16px;font-weight:500}
.sf-k{font:500 11px/1 var(--font-mono, monospace);color:var(--ink2);min-width:14px;padding:3px 0;border-radius:4px;text-align:center;opacity:.85}
.sf-ask{font:400 10px/1 var(--font-mono, monospace);letter-spacing:.1em;text-transform:uppercase;color:var(--muted, #777);margin-left:auto}
.sf-nt{font-size:12.5px;line-height:1.35;color:var(--muted, #777)}
.sf.small{grid-template-columns:auto minmax(0,1fr);padding:10px 12px 12px 12px;border-radius:14px;max-width:none}
.sf.small .sf-nm{font-size:18px}.sf.small .sf-pads{grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:6px;margin-top:6px}
.sf.small .sf-pad{min-height:0;padding:6px 10px;border-radius:10px}.sf.small .sf-nt{display:none}.sf.small .sf-pl{font-size:14px}
.sf.small .sf-count{width:40px}.sf.small .sf-count b{font-size:24px}.sf.small .sf-count i{font-size:9px}
.sf.bare{background:none;padding:0 0 4px 0}.sf.bare::before{display:none}.sf.bare .sf-pads{margin-top:0}
@media(max-width:520px){.sf{padding:14px 14px 14px 14px;gap:4px 12px}.sf-nm{font-size:22px}.sf-pads{grid-template-columns:repeat(var(--np, 2),minmax(0,1fr))}.sf-pad{padding:8px 10px 9px}}
@media(prefers-reduced-motion:reduce){.sf-pad{transition:none}}
`

export default function SurfaceCard({ s, keys = false, small = false, bare = false, hit = -1, onOpen, onAsk }) {
  if (!s || !Array.isArray(s.actions)) return null
  const n = s.actions.length
  const press = (a, i) => (a.kind === 'ask' ? onAsk && onAsk(a, i) : onOpen && onOpen(a, i))
  return (
    <section className={'sf' + (small ? ' small' : '') + (bare ? ' bare' : '')} style={{ '--hue': s.hue, '--n': n, '--np': n <= 3 ? n : n === 4 ? 2 : 3 }} data-surface={s.name}
      aria-label={`${s.name}: ${s.actions.length} actions`}>
      {bare ? null : <Mark s={s} size={small ? 36 : 60} />}
      {bare ? null : (
        <div className="sf-hd">
          <h3 className="sf-nm">{s.name}</h3>
          {s.line ? <p className="sf-ln">{s.line}</p> : null}
        </div>
      )}
      <div className="sf-pads">
        {s.actions.map((a, i) => (
          <button key={i} type="button" className={'sf-pad' + (hit === i ? ' hit' : '')} onClick={() => press(a, i)}
            title={a.kind === 'ask' ? `puts "${a.ask.trim()}" in the box` : a.open}
            aria-keyshortcuts={keys ? String(i + 1) : undefined}>
            <span className="sf-pl">{keys ? <span className="sf-k">{i + 1}</span> : null}{a.label}{a.kind === 'ask' ? <span className="sf-ask">ask</span> : null}</span>
            {a.note ? <span className="sf-nt">{a.note}</span> : null}
          </button>
        ))}
      </div>
    </section>
  )
}
