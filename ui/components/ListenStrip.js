// The radio strip (LISTEN-1, 2026-11-24): the console's one audio owner, drawn in the top-level document only
// (pages/_app.js), so it outlives every page change and every pane. At rest it shows the play / pause press, next,
// the station's name, the title and the artist; nothing else. While a YouTube item plays, the official embed
// player sits in the strip's square at 200x200 (the controller owns that iframe and never re-parents it; the strip
// only says where the square is). An own track shows a turning disc instead. Drag the strip by its words to any
// corner; it stays there. Paused, a small x puts the radio away.
import { useEffect, useRef, useState } from 'react'
import Router from 'next/router'
import { listener, installLinks } from '../lib/listen'

const CORNER = 'cc.listen.corner'
const CSS = `
.ls{--ls-ease:cubic-bezier(.2,.7,.2,1);position:fixed;z-index:9979;display:flex;align-items:stretch;gap:0;
  background:color-mix(in srgb,var(--bg) 82%,#000);color:var(--text);border-radius:18px;
  box-shadow:0 0 0 1px color-mix(in srgb,var(--accent) 35%,transparent),0 18px 48px rgba(0,0,0,.5);
  font-family:var(--font-body);user-select:none;-webkit-user-select:none;max-width:calc(100vw - 20px);
  transition:left 220ms var(--ls-ease),top 220ms var(--ls-ease),right 220ms var(--ls-ease),bottom 220ms var(--ls-ease)}
.ls.drag{transition:none}
.ls-sq{position:relative;width:200px;height:200px;flex:none;border-radius:18px 0 0 18px;overflow:hidden;
  background:radial-gradient(circle at 50% 50%,color-mix(in srgb,var(--accent) 22%,#000) 0 18%,#0b0a09 19% 100%)}
.ls-sq.tiny{width:64px;height:64px;border-radius:18px 0 0 18px}
.ls-disc{position:absolute;inset:18px;border-radius:50%;
  background:repeating-radial-gradient(circle at 50% 50%,#111 0 2px,#1b1917 2px 4px);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}
.ls-disc::after{content:"";position:absolute;inset:38%;border-radius:50%;background:var(--accent);box-shadow:0 0 22px color-mix(in srgb,var(--accent) 60%,transparent)}
.ls.on .ls-disc{animation:ls-turn 1.8s linear infinite}
.ls-sq.tiny .ls-disc{inset:8px}
@keyframes ls-turn{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.ls.on .ls-disc{animation:none}}
.ls-body{display:flex;flex-direction:column;justify-content:space-between;padding:14px 14px 12px 16px;min-width:0;width:240px;cursor:grab}
.ls.drag .ls-body{cursor:grabbing}
.ls-st{font:500 11px/1.2 var(--font-mono);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-decoration:none}
.ls-ti{font:500 16px/1.25 var(--font-body);margin-top:8px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.ls-ar{font-size:13px;color:var(--text-dim);margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ls-err{font-size:12px;color:var(--text-dim);margin-top:6px}
.ls-row{display:flex;align-items:center;gap:10px;margin-top:10px}
.ls-b{font:inherit;color:var(--text);background:transparent;border:1px solid color-mix(in srgb,var(--text) 18%,transparent);
  width:44px;height:44px;border-radius:50%;display:grid;place-items:center;cursor:pointer;flex:none;
  transition:transform 120ms var(--ls-ease),background-color 150ms ease-out,border-color 150ms ease-out}
.ls-b:hover{border-color:var(--accent)}
.ls-b:active{transform:scale(.94)}
.ls-b:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.ls-b.big{width:52px;height:52px;background:var(--accent);color:var(--bg);border-color:transparent}
.ls-b svg{width:18px;height:18px}
.ls-b.big svg{width:20px;height:20px}
.ls-x{margin-left:auto;font:inherit;font-size:18px;line-height:1;color:var(--text-dim);background:none;border:0;cursor:pointer;padding:6px}
.ls-x:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:520px){.ls-body{width:auto;flex:1;padding:12px 10px 10px 12px}.ls-ti{font-size:15px}}
`

const PLAY = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l13-7.5z" /></svg>
const PAUSE = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z" /></svg>
const NEXT = <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 5v14l10-7zM15 5h3v14h-3z" /></svg>

function cornerStyle (c) {
  const v = { left: 'auto', right: 'auto', top: 'auto', bottom: 'auto' }
  const top = 'calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px) + 10px)'
  if (c === 'tl') { v.left = '10px'; v.top = top }
  else if (c === 'tr') { v.right = '10px'; v.top = top }
  else if (c === 'br') { v.right = '10px'; v.bottom = 'calc(64px + env(safe-area-inset-bottom, 0px))' }  // above the help button
  else { v.left = '10px'; v.bottom = 'calc(38px + env(safe-area-inset-bottom, 0px))' }                 // above the sides footer
  return v
}

export default function ListenStrip () {
  const [s, setS] = useState(null)
  const [corner, setCorner] = useState('bl')
  const [drag, setDrag] = useState(null)
  const box = useRef(null); const sq = useRef(null)
  const ctl = useRef(null)

  useEffect(() => {
    try { if (window.self !== window.top) return } catch (e) { return }   // a pane: the top document's strip plays
    const c = listener()
    ctl.current = c
    try { const v = localStorage.getItem(CORNER); if (['bl', 'br', 'tl', 'tr'].includes(v)) setCorner(v) } catch (e) {}
    const off = c.subscribe(setS)
    c.resume()
    const offLinks = installLinks(window, Router, () => !!(c.get().playing || c.get().loading))
    return () => { off(); offLinks() }
  }, [])

  const yt = !!(s && s.now && s.now.k === 'yt')
  const visible = !!(s && s.station)

  // tell the controller where the square is, after every layout change
  useEffect(() => {
    const c = ctl.current
    if (!c) return
    const put = () => {
      const r = sq.current && visible && yt ? sq.current.getBoundingClientRect() : null
      c.place(r)
    }
    put()
    const t = setTimeout(put, 240)       // after the corner move settles
    window.addEventListener('resize', put)
    window.addEventListener('scroll', put, true)
    return () => { clearTimeout(t); window.removeEventListener('resize', put); window.removeEventListener('scroll', put, true) }
  }, [visible, yt, corner, drag, s && s.i, s && s.now])

  if (!visible) return null

  const down = (e) => {
    if (e.button !== 0 || (e.target.closest && e.target.closest('button,a'))) return
    const r = box.current.getBoundingClientRect()
    setDrag({ dx: e.clientX - r.left, dy: e.clientY - r.top, x: r.left, y: r.top, moved: false })
    e.currentTarget.setPointerCapture && e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e) => {
    if (!drag) return
    setDrag(d => ({ ...d, x: e.clientX - d.dx, y: e.clientY - d.dy, moved: true }))
  }
  const up = (e) => {
    if (!drag) return
    if (drag.moved) {
      const r = box.current.getBoundingClientRect()
      const cx = r.left + r.width / 2; const cy = r.top + r.height / 2
      const c = (cy < window.innerHeight / 2 ? 't' : 'b') + (cx < window.innerWidth / 2 ? 'l' : 'r')
      setCorner(c)
      try { localStorage.setItem(CORNER, c) } catch (err) {}
    }
    setDrag(null)
  }

  const pos = drag && drag.moved ? { left: drag.x + 'px', top: drag.y + 'px', right: 'auto', bottom: 'auto' } : cornerStyle(corner)
  const playing = !!s.playing
  const now = s.now || {}
  const cls = 'ls' + (playing ? ' on' : '') + (drag && drag.moved ? ' drag' : '')

  return (
    <div ref={box} className={cls} style={pos} data-listen-strip="" role="region" aria-label="music">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div ref={sq} className={'ls-sq' + (yt ? '' : ' tiny')} data-sq={yt ? 'yt' : 'disc'}>
        {!yt && <div className="ls-disc" />}
      </div>
      <div className="ls-body" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <div>
          <a className="ls-st" href="/listen" title="all stations">{s.name || '...'}</a>
          <div className="ls-ti" data-listen-title="">{now.title || (s.loading ? '...' : '')}</div>
          {now.artist ? <div className="ls-ar" data-listen-artist="">{now.artist}</div> : null}
          {s.error ? <div className="ls-err">{s.error}</div> : null}
        </div>
        <div className="ls-row">
          <button type="button" className="ls-b big" onClick={() => ctl.current.toggle()} aria-label={playing ? 'pause' : 'play'} data-listen-toggle="">
            {playing ? PAUSE : PLAY}
          </button>
          <button type="button" className="ls-b" onClick={() => ctl.current.next()} aria-label="next" data-listen-next="">{NEXT}</button>
          {!playing && !s.loading ? <button type="button" className="ls-x" onClick={() => ctl.current.stop()} aria-label="put the radio away">×</button> : null}
        </div>
      </div>
    </div>
  )
}
