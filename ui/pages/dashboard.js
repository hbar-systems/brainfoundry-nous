import Head from 'next/head'
import React, { useEffect, useState } from 'react'
import { Dashboard as StockDashboard } from './index'

// The dashboard as the owner's own page (DASH-1, 2026-11-22; before: the stock dashboard on its own route, D54).
// hbar: the knowledge from his study, "structured and ordered, each topic linking to the repos and notes we have on
// it, plus one row of live state (threads running, jobs, pushes waiting). Warm palette, few words at rest, detail on
// press."
// Data: GET /cc/dashboard (scripts/cc/cc_dashboard.py). The map is the owner's file in their world
// (ops/dashboard/knowledge.json), never this template's; a brain without one, or without the bridge, keeps the stock
// dashboard. At rest: the title, three numbers, and each group's name with its topics as plain names. A press on a
// number opens its lines; a press on a topic opens it in place (one line, a few points, its links) and writes
// #<group>.<topic> in the address, so a link to a topic works and a way back from a file lands on it again.
// A link to a file or folder of the world opens it in Files; one that is not on this box is shown as such, not hidden.
// Updates: one light request every five seconds, none while the tab is hidden. Look: the chat's sand skin.

const CSS = `
.db{--bg:#efe3cf;--surface:#e6d6bd;--ink:#2b2116;--dim:#54473a;--muted:#7a6a55;--rust:#a8452b;--ease:cubic-bezier(.2,.7,.2,1);
  --top:calc(var(--nav-h, 52px) + env(safe-area-inset-top, 0px));
  background:var(--bg);color:var(--ink);min-height:calc(100vh - var(--top));font:400 16px/1.5 system-ui,-apple-system,sans-serif;box-sizing:border-box}
.db *{box-sizing:border-box}
.db :where(a){color:inherit}
.db :where(button){font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;text-align:left}
.db :focus-visible{outline:2px solid var(--rust);outline-offset:3px;border-radius:6px}
.db-in{max-width:980px;margin:0 auto;padding:36px 32px 96px}
.db-h1{font:400 34px/1.15 Lora,Georgia,serif;margin:0}
.db-sub{margin:6px 0 0;color:var(--muted);font-size:15px;max-width:60ch}
.db-live{display:flex;flex-wrap:wrap;gap:6px 10px;margin:26px -12px 0}
.db-n{display:inline-flex;align-items:baseline;gap:8px;padding:6px 12px;border-radius:12px;color:var(--dim);font-size:15px;transition:background-color 200ms var(--ease)}
.db-n b{font:400 24px/1 Lora,Georgia,serif;font-variant-numeric:tabular-nums;color:var(--ink)}
.db-n.zero,.db-n.zero b{color:var(--muted)}
.db-n.hot b{color:var(--rust)}
.db-n:hover,.db-n.on{background:var(--surface)}
.db-fold{display:grid;grid-template-rows:0fr;visibility:hidden;transition:grid-template-rows 260ms var(--ease),visibility 0s linear 260ms}
.db-fold.on{grid-template-rows:1fr;visibility:visible;transition:grid-template-rows 260ms var(--ease),visibility 0s}
.db-fi{overflow:hidden;min-height:0}
.db-card{background:var(--surface);border-radius:14px;padding:14px 18px 16px;margin:8px 0 4px}
.db-rows{list-style:none;margin:0;padding:0}
.db-rows li{display:flex;align-items:baseline;gap:10px;padding:4px 0;font-size:15px;color:var(--dim)}
.db-rows li span.g{flex:1;min-width:0;overflow-wrap:anywhere}
.db-rows li .m{font-size:13px;color:var(--muted);white-space:nowrap}
.db-rows li .m.bad{color:var(--rust)}
.db-rows a{text-decoration:underline;text-decoration-color:var(--muted);text-underline-offset:3px}
.db-rows a:hover{color:var(--rust)}
.db-none{margin:0;font-size:14px;color:var(--muted)}
.db-map{margin-top:34px}
.db-g{display:grid;grid-template-columns:34px minmax(0,1fr);padding:16px 0 6px}
.db-no{font:400 15px/30px Lora,Georgia,serif;color:var(--muted);font-variant-numeric:tabular-nums}
.db-gn{font:400 23px/1.3 Lora,Georgia,serif;margin:0}
.db-gl{margin:0 0 6px;font-size:14px;color:var(--muted)}
.db-ts{display:flex;flex-wrap:wrap;gap:2px 4px;margin:0 -10px}
.db-t{padding:5px 10px;border-radius:10px;color:var(--dim);font-size:16px;transition:background-color 200ms var(--ease),color 200ms var(--ease)}
.db-t:hover{color:var(--ink);background:var(--surface)}
.db-t.on{color:var(--ink);background:var(--surface)}
.db-t i{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--rust);margin:0 0 3px 7px;vertical-align:middle}
.db-tl{margin:0;font:400 19px/1.35 Lora,Georgia,serif}
.db-weak{margin:8px 0 0;font-size:14px;color:var(--rust)}
.db-pts{margin:10px 0 0;padding:0 0 0 18px;color:var(--dim);font-size:15px;max-width:66ch}
.db-pts li{padding:2px 0}
.db-lk{display:flex;flex-wrap:wrap;gap:6px 8px;margin:14px 0 0}
.db-lk a,.db-lk span{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;background:var(--bg);font-size:14px;color:var(--ink);text-decoration:none}
.db-lk a:hover{color:var(--rust)}
.db-lk span{color:var(--muted);background:none;padding-left:0}
.db-lk svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;opacity:.7}
@media(max-width:640px){.db-in{padding:24px 18px 80px}.db-h1{font-size:28px}.db-g{grid-template-columns:26px minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){.db-fold,.db-n,.db-t{transition:none}}
`

const ICON = {
  file: <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 1.5h5l3 3v10H4z" /><path d="M9 1.5v3h3" /></svg>,
  dir: <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 4h4.5l1.5 1.5h7v8h-13z" /></svg>,
  out: <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3h7v7" /><path d="M13 3 4 12" /></svg>,
}

const plural = (n, one, many) => (n === 1 ? one : many)

function Fold({ on, children }) {
  return <div className={'db-fold' + (on ? ' on' : '')}><div className="db-fi">{children}</div></div>
}

function LiveRows({ kind, live }) {
  if (kind === 'threads') {
    return live.threads.length ? (
      <ul className="db-rows">{live.threads.map(t => (
        <li key={t.id}><span className="g"><a href={`/talk?thread=${encodeURIComponent(t.id)}`}>{t.title}</a></span><span className="m">answering</span></li>
      ))}</ul>
    ) : <p className="db-none">No thread is answering right now.</p>
  }
  if (kind === 'jobs') {
    return live.jobs.length ? (
      <ul className="db-rows">{live.jobs.map(j => (
        <li key={j.id}><span className="g">{j.thread ? <a href={`/talk?thread=${encodeURIComponent(j.thread)}`}>{j.title}</a> : j.title}</span><span className="m">{j.id}</span></li>
      ))}</ul>
    ) : <p className="db-none">No job is running.</p>
  }
  return live.pushes.length ? (
    <ul className="db-rows">{live.pushes.map(p => (
      <li key={p.repo}><span className="g">{p.repo}</span><span className="m">{p.ahead} {plural(p.ahead, 'commit', 'commits')}</span>
        <span className={'m' + (p.clean ? '' : ' bad')}>{p.clean ? 'clean' : 'held: ' + p.leak}</span></li>
    ))}</ul>
  ) : <p className="db-none">Nothing is waiting for a push.</p>
}

function TopicLink({ k }) {
  if (k.url) return <a href={k.url} target="_blank" rel="noopener noreferrer">{ICON.out}{k.label}</a>
  if (!k.exists) return <span title={k.path}>{k.label}: not on this box</span>
  return <a href={k.href} title={k.path}>{k.dir ? ICON.dir : ICON.file}{k.label}</a>
}

function Topic({ t }) {
  return (
    <div className="db-card">
      {t.line ? <p className="db-tl">{t.line}</p> : null}
      {t.weak ? <p className="db-weak">Weak spot: {t.weak}</p> : null}
      {t.points.length ? <ul className="db-pts">{t.points.map((p, i) => <li key={i}>{p}</li>)}</ul> : null}
      {t.links.length ? <div className="db-lk">{t.links.map((k, i) => <TopicLink key={i} k={k} />)}</div> : null}
    </div>
  )
}

export default function OwnDashboard() {
  const [data, setData] = useState(null)      // null: not asked yet; false: no bridge; else the answer
  const [open, setOpen] = useState('')        // '<group>.<topic>'
  const [kind, setKind] = useState('')        // which live number is open

  useEffect(() => {
    let dead = false
    const load = () => fetch('/cc/dashboard', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(d => { if (!dead) setData(d && typeof d === 'object' ? d : false) })
      .catch(() => { if (!dead) setData(prev => prev || false) })
    load()
    const id = setInterval(() => { if (!document.hidden) load() }, 5000)
    const onShow = () => { if (!document.hidden) load() }
    document.addEventListener('visibilitychange', onShow)
    const fromHash = () => setOpen(decodeURIComponent((window.location.hash || '').slice(1)))
    fromHash()
    window.addEventListener('hashchange', fromHash)
    return () => { dead = true; clearInterval(id); document.removeEventListener('visibilitychange', onShow); window.removeEventListener('hashchange', fromHash) }
  }, [])

  if (data === null) return <div className="db"><style>{CSS}</style></div>
  if (!data || !data.map) return <StockDashboard />

  const map = data.map
  const live = { threads: [], jobs: [], pushes: [], ...(data.live || {}) }
  const press = (key) => {
    const next = open === key ? '' : key
    setOpen(next)
    window.history.replaceState(null, '', next ? '#' + encodeURIComponent(next) : window.location.pathname + window.location.search)
  }
  const numbers = [
    ['threads', live.threads.length, plural(live.threads.length, 'thread answering', 'threads answering'), true],
    ['jobs', live.jobs.length, plural(live.jobs.length, 'job running', 'jobs running'), true],
    ['pushes', live.pushes.length, plural(live.pushes.length, 'push waiting', 'pushes waiting'), false],
  ]

  return (
    <div className="db">
      <Head><title>{map.title || 'Dashboard'}</title></Head>
      <style>{CSS}</style>
      <div className="db-in">
        <h1 className="db-h1">{map.title || 'Dashboard'}</h1>
        {map.line ? <p className="db-sub">{map.line}</p> : null}

        <div className="db-live">
          {numbers.map(([k, n, label, hot]) => (
            <button key={k} type="button" className={'db-n' + (n ? (hot ? ' hot' : '') : ' zero') + (kind === k ? ' on' : '')}
              aria-expanded={kind === k} onClick={() => setKind(kind === k ? '' : k)}>
              <b>{n}</b>{label}
            </button>
          ))}
        </div>
        <Fold on={!!kind}><div className="db-card">{kind ? <LiveRows kind={kind} live={live} /> : null}</div></Fold>

        <div className="db-map">
          {map.groups.map((g, gi) => {
            const cur = g.topics.find(t => open === g.id + '.' + t.id)
            return (
              <section key={g.id} className="db-g">
                <div className="db-no">{gi + 1}</div>
                <div>
                  <h2 className="db-gn">{g.name}</h2>
                  {g.line ? <p className="db-gl">{g.line}</p> : null}
                  <div className="db-ts">
                    {g.topics.map(t => {
                      const key = g.id + '.' + t.id
                      return (
                        <button key={t.id} type="button" className={'db-t' + (open === key ? ' on' : '')} aria-expanded={open === key}
                          onClick={() => press(key)}>
                          {t.name}{t.weak ? <i title="weak spot" /> : null}
                        </button>
                      )
                    })}
                  </div>
                  <Fold on={!!cur}>{cur ? <Topic t={cur} /> : null}</Fold>
                </div>
              </section>
            )
          })}
        </div>
      </div>
    </div>
  )
}
