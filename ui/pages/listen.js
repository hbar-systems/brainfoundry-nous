import Head from 'next/head'
import { useEffect, useRef, useState } from 'react'
import { listener } from '../lib/listen'

// /listen (LISTEN-1, 2026-11-24): the tuner. Every station this brain's world holds (GET /cc/listen): the pinned
// playlist series first (newest first), the likes, the owner's own tracks, "mixed by the brain", then every other
// playlist. A press tunes in; the music plays in the console's strip (components/ListenStrip.js), which keeps
// playing on every other page and pane. Opened inside a pane, this page drives the top document's player.
// Its own look: a dark tuner glass with a lit needle over the station marks, in the console's own accent and font.

const CSS = `
.tu{--glass:color-mix(in srgb,var(--bg) 70%,#000);--line:color-mix(in srgb,var(--text) 14%,transparent);
  --top:calc(var(--nav-h,52px) + env(safe-area-inset-top,0px));min-height:calc(100vh - var(--top));
  color:var(--text);font:400 16px/1.5 var(--font-body);
  background:radial-gradient(ellipse 80% 40% at 50% 0%,color-mix(in srgb,var(--accent) 14%,transparent),transparent 70%),var(--bg)}
.tu-in{max-width:1080px;margin:0 auto;padding:22px 20px 260px}
.tu-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.tu-h h1{font:400 28px/1.1 var(--font-display);margin:0;letter-spacing:.01em}
.tu-h span{font:500 12px/1 var(--font-mono);letter-spacing:.14em;color:var(--text-dim);text-transform:uppercase}
.tu-dial{position:relative;margin:22px 0 30px;height:136px;border-radius:18px;background:var(--glass);
  box-shadow:inset 0 0 0 1px var(--line),inset 0 -30px 60px rgba(0,0,0,.35);overflow:hidden}
.tu-scale{position:absolute;inset:0;overflow-x:auto;overflow-y:hidden;scrollbar-width:none;display:flex;align-items:flex-end;
  padding:0 50%;scroll-behavior:smooth}
.tu-scale::-webkit-scrollbar{display:none}
.tu-mk{flex:none;width:58px;height:100%;position:relative;cursor:pointer;background:none;border:0;padding:0;color:inherit;font:inherit}
.tu-mk::before{content:"";position:absolute;left:50%;bottom:0;width:1px;height:26px;background:var(--line)}
.tu-mk.major::before{height:44px;background:color-mix(in srgb,var(--text) 34%,transparent)}
.tu-mk b{position:absolute;left:50%;bottom:52px;transform:translateX(-4px) rotate(-38deg);transform-origin:left bottom;
  font:500 11px/1 var(--font-mono);letter-spacing:.06em;white-space:nowrap;color:var(--text-dim);max-width:110px;overflow:hidden;text-overflow:ellipsis}
.tu-mk.cur b{color:var(--accent)}
.tu-mk:focus-visible{outline:2px solid var(--accent);outline-offset:-4px;border-radius:8px}
.tu-needle{position:absolute;left:50%;top:10px;bottom:0;width:2px;margin-left:-1px;background:var(--accent);pointer-events:none;
  box-shadow:0 0 14px var(--accent),0 0 40px color-mix(in srgb,var(--accent) 50%,transparent)}
.tu-shelf{margin-top:26px}
.tu-shelf h2{font:500 12px/1 var(--font-mono);letter-spacing:.16em;text-transform:uppercase;color:var(--text-dim);margin:0 0 12px}
.tu-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:10px}
.tu-st{position:relative;text-align:left;font:inherit;color:var(--text);cursor:pointer;min-height:84px;padding:14px 14px 12px;
  border-radius:14px;border:1px solid var(--line);background:color-mix(in srgb,var(--surface) 55%,transparent);
  display:flex;flex-direction:column;justify-content:space-between;gap:8px;
  transition:transform 120ms cubic-bezier(.2,.7,.2,1),border-color 150ms ease-out,background-color 150ms ease-out}
.tu-st:hover{border-color:color-mix(in srgb,var(--accent) 60%,transparent)}
.tu-st:active{transform:scale(.98)}
.tu-st:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.tu-st .n{font:500 17px/1.2 var(--font-body);overflow-wrap:anywhere}
.tu-st .c{font:400 12px/1 var(--font-mono);color:var(--text-dim);letter-spacing:.06em}
.tu-st.cur{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent)}
.tu-st.cur::after{content:"";position:absolute;top:14px;right:14px;width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 10px var(--accent)}
.tu-st.big{min-height:110px}
.tu-st.big .n{font-size:20px}
.tu-why{color:var(--text-dim);margin-top:30px}
.tu-more{margin-top:12px;font:500 13px/1 var(--font-mono);letter-spacing:.1em;color:var(--text-dim);background:none;border:1px solid var(--line);border-radius:999px;padding:10px 16px;cursor:pointer}
.tu-more:hover{color:var(--text);border-color:var(--accent)}
.tu-more:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media (max-width:520px){.tu-in{padding:16px 12px 280px}.tu-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.tu-dial{height:104px}}
`

export default function Listen () {
  const [d, setD] = useState(null)
  const [s, setS] = useState(null)
  const [all, setAll] = useState(false)
  const scale = useRef(null)

  useEffect(() => {
    fetch('/cc/listen', { cache: 'no-store' }).then(r => r.json()).then(setD).catch(() => setD({ ok: false, stations: [], why: 'the bridge did not answer' }))
    const c = listener()
    return c ? c.subscribe(setS) : undefined
  }, [])

  const stations = (d && d.stations) || []
  const cur = s && s.station
  // keep the needle on the station that plays
  useEffect(() => {
    const el = scale.current && cur ? scale.current.querySelector(`[data-mk="${CSS_ESC(cur)}"]`) : null
    if (el) el.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [cur, stations.length])

  const tune = (id) => { const c = listener(); if (c) { if (cur === id && s && s.now) c.toggle(); else c.start(id) } }
  const first = stations.filter(x => x.first)
  const mine = stations.filter(x => ['likes', 'own', 'mix'].includes(x.kind))
  const rest = stations.filter(x => !x.first && x.kind === 'playlist')

  const tile = (x, big) => (
    <button key={x.id} type="button" className={'tu-st' + (big ? ' big' : '') + (cur === x.id ? ' cur' : '')} onClick={() => tune(x.id)}
      data-station={x.id} title={x.note || ''}>
      <span className="n">{x.name}</span>
      <span className="c">{x.count}</span>
    </button>
  )

  return (
    <div className="tu">
      <Head><title>listen</title></Head>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="tu-in">
        <div className="tu-h"><h1>listen</h1><span>{stations.length ? `${stations.length} stations` : ''}</span></div>
        {stations.length ? (
          <div className="tu-dial">
            <div className="tu-scale" ref={scale}>
              {stations.map((x, i) => (
                <button key={x.id} type="button" className={'tu-mk' + (x.first || x.kind !== 'playlist' ? ' major' : '') + (cur === x.id ? ' cur' : '')}
                  data-mk={x.id} onClick={() => tune(x.id)} aria-label={x.name}><b>{x.name}</b></button>
              ))}
            </div>
            <div className="tu-needle" />
          </div>
        ) : null}
        {first.length ? <section className="tu-shelf"><h2>{first.length > 1 ? 'series' : ''}</h2><div className="tu-grid">{first.map(x => tile(x, true))}</div></section> : null}
        {mine.length ? <section className="tu-shelf"><h2>yours</h2><div className="tu-grid">{mine.map(x => tile(x, true))}</div></section> : null}
        {rest.length ? <section className="tu-shelf"><h2>playlists</h2><div className="tu-grid">{(all ? rest : rest.slice(0, 10)).map(x => tile(x, false))}</div>
          {rest.length > 10 && !all ? <button type="button" className="tu-more" onClick={() => setAll(true)} data-more="">all {rest.length}</button> : null}</section> : null}
        {d && !stations.length ? <p className="tu-why">{d.why || d.error || 'no stations'}</p> : null}
      </div>
    </div>
  )
}

function CSS_ESC (v) { return String(v).replace(/["\\]/g, '\\$&') }
