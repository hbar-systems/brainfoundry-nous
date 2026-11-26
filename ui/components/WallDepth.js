import React, { useEffect, useMemo, useRef, useState } from 'react'
import { CENTRE, depthOf, jobLines, jobsBySystem, minsText, promptsOf, waitsForMore } from '../lib/wall'
import { parseTree, treeCounts } from '../lib/tree'
import ThreadTree from './ThreadTree'

// The depth layer of the wall (WALL-3, 2026-11-24). hbar, verbatim: "will i be satisfied with the number of
// information i can get about the system (and talkign to it: ex: how many jobs are going, maybe agentic
// substructure of each job or info, clear summary, this thing too (see image 3) and so i can also maybe red the
// thread if i wanted too etc. but like everything is hidden, and i can gain access some easy way WITHOUT interfering
// with production and the main focus."
//
// At rest nothing of this shows. One press on a system's light or count opens it in place, over the sky, never a
// navigation; Esc or a press outside closes it. It only reads: opening and closing it sends nothing and stops
// nothing (the page keeps its one three-second poll, which asks for this system's tree while the layer is open).
// Four rows, each one line until pressed:
//   now      one sentence of where the system stands (its state card, else its thread's last answer)
//   jobs     the jobs running now, each with its minutes and, pressed, its inside: the brief, the last steps of its
//            log, the files it made so far, the job that will push it
//   tree     the thread's last <tree>, drawn as the chat draws it, read-only; its Talk puts the ask in the box
//   thread   the whole thread, opened beside as before
// The centre's layer is the same for the brain as a whole: every running job grouped by system, and what waits for
// him (tasks due today, court items) as two counts that open their pages beside.

const short = (id) => String(id || '').replace(/^hbar\./, '')

const CSS = `
.wd{position:absolute;z-index:8;width:min(380px,92vw);max-height:min(62vh,560px);overflow:auto;padding:8px 6px 6px;border-radius:16px;
  background:rgba(10,10,11,.97);border:1px solid rgba(255,255,255,.08);box-shadow:0 18px 60px rgba(0,0,0,.7);text-align:left;
  font:300 13px/1.45 var(--font-body,system-ui,sans-serif);color:var(--oink,#ecebe6);animation:wd-in 180ms cubic-bezier(.2,.7,.2,1);
  --text:var(--oink,#ecebe6);--muted:var(--odim,#8f8c85);--border:rgba(255,255,255,.08);--surface2:rgba(255,255,255,.04)}
.wd *{box-sizing:border-box}
.wd :where(button){font:inherit;color:inherit;background:none;border:0;margin:0;cursor:pointer;text-align:left}
.wd-hd{display:flex;align-items:baseline;gap:8px;padding:4px 10px 8px;font-size:11px;letter-spacing:.14em;text-transform:lowercase;color:var(--omute,#4f4d49)}
.wd-hd b{font-weight:400;color:var(--odim,#8f8c85);letter-spacing:.06em}
.wd-x{margin-left:auto!important;font-size:11px;color:var(--omute,#4f4d49)!important;letter-spacing:.06em}.wd-x:hover{color:var(--oink,#ecebe6)!important}
.wd-r{display:flex;align-items:baseline;gap:10px;width:100%;padding:7px 10px;border-radius:10px;transition:background-color 200ms}
.wd-r:hover,.wd-r[aria-expanded=true]{background:rgba(255,255,255,.035)}
.wd-k{flex:none;width:44px;font-size:10px;letter-spacing:.14em;text-transform:lowercase;color:var(--omute,#4f4d49)}
.wd-t{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--odim,#8f8c85)}
.wd-r[aria-expanded=true] .wd-t.wrap{white-space:normal;overflow:visible;color:var(--oink,#ecebe6)}
.wd-t .n{color:var(--olit,#c9a96e);font-variant-numeric:tabular-nums}
.wd-r.go .wd-t{color:var(--oink,#ecebe6)}.wd-r.go:hover .wd-t{color:var(--olit,#c9a96e)}
.wd-in{padding:2px 8px 8px 64px}
.wd-j{padding:6px 0;border-top:1px solid rgba(255,255,255,.04)}.wd-j:first-child{border-top:0}
.wd-jh{display:flex;gap:8px;align-items:baseline;width:100%}
.wd-jt{flex:1;min-width:0;color:var(--oink,#ecebe6);overflow-wrap:anywhere}
.wd-jm{flex:none;font-size:11px;color:var(--olit,#c9a96e);font-variant-numeric:tabular-nums}
.wd-jl{font-size:12px;color:var(--odim,#8f8c85);overflow-wrap:anywhere;margin-top:2px}
.wd-jl .k{color:var(--omute,#4f4d49);margin-right:6px}
.wd-sys{font-size:10px;letter-spacing:.14em;text-transform:lowercase;color:var(--omute,#4f4d49);margin:8px 0 2px}
.wd-w{display:flex;align-items:center;gap:8px;padding:4px 10px 8px}
.wd-w button{font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.1)!important;color:var(--odim,#8f8c85)}
.wd-w button:hover{color:var(--oink,#ecebe6);border-color:rgba(255,255,255,.22)!important}
.wd-w b{font-weight:400;color:var(--olit,#c9a96e);margin-right:5px;font-variant-numeric:tabular-nums}
.wd-tree{padding:0 4px 6px 10px}
.wd-tree [data-thread-tree]{border-color:rgba(255,255,255,.06)!important}
.wd-none{font-size:12px;color:var(--omute,#4f4d49);padding:2px 0 6px}
.wd-pr{display:flex;gap:10px;padding:5px 10px 7px;align-items:flex-start}
.wd-pr .wd-k{padding-top:5px}
.wd-pl{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}
.wd-p{font-size:12.5px;line-height:1.35;color:var(--odim,#8f8c85)!important;padding:4px 8px!important;margin-left:-8px!important;border-radius:8px;overflow-wrap:anywhere}
.wd-p:hover,.wd-p:focus-visible{color:var(--oink,#ecebe6)!important;background:rgba(255,255,255,.035)}
.wd-p .k{color:var(--omute,#4f4d49)}
@keyframes wd-in{from{opacity:0;transform:translateY(4px)}}
@media(max-width:759px){.wd{position:static;width:auto;max-height:none;margin:8px 0 4px;animation:none;transform:none!important}.wd-in{padding-left:10px}}
@media(prefers-reduced-motion:reduce){.wd{animation:none}}
`

function Row({ k, open, onPress, wrap, go, children, title }) {
  return (
    <button type="button" className={'wd-r' + (go ? ' go' : '')} aria-expanded={go ? undefined : !!open} onClick={onPress} title={title}>
      <span className="wd-k">{k}</span>
      <span className={'wd-t' + (wrap ? ' wrap' : '')}>{children}</span>
    </button>
  )
}

function Job({ j, sys }) {
  const [open, setOpen] = useState(false)
  const lines = jobLines(j)
  return (
    <div className="wd-j">
      <button type="button" className="wd-jh" onClick={() => setOpen(o => !o)} aria-expanded={open}
        title={lines.length ? (open ? 'fold' : 'what it is doing inside') : j.title}>
        <span className="wd-jt">{sys ? <span className="k" style={{ color: 'var(--omute,#4f4d49)', marginRight: 6 }}>{short(sys)}</span> : null}{j.title}</span>
        <span className="wd-jm">{minsText(j.mins)}</span>
      </button>
      {open ? (lines.length ? lines.map((l, i) => <div key={i} className="wd-jl"><span className="k">{l.k}</span>{l.text}</div>)
        : <div className="wd-jl">nothing written yet; its report lands when it ends</div>) : null}
    </div>
  )
}

export default function WallDepth({ t, tiles, waits, style, onClose, onRead, onTalk, onRoute }) {
  const ref = useRef(null)
  const [row, setRow] = useState(null)
  const sid = t ? t.id : null
  const centre = sid === CENTRE
  const d = depthOf(t)
  const prompts = promptsOf(t)
  const tree = useMemo(() => (t && t.tree ? parseTree(JSON.stringify(t.tree)) : null), [t && t.tree])   // eslint-disable-line react-hooks/exhaustive-deps
  const counts = tree ? treeCounts(tree) : {}
  const groups = centre ? jobsBySystem(tiles) : null
  const total = centre ? groups.reduce((n, g) => n + g.jobs.length, 0) : d.jobs.n

  // a press outside closes it (the light that opened it toggles it itself)
  useEffect(() => {
    const down = (e) => {
      const el = ref.current
      if (!el || el.contains(e.target)) return
      if (e.target && e.target.closest && e.target.closest('[data-depth-for]')) return
      onClose()
    }
    document.addEventListener('pointerdown', down)
    return () => document.removeEventListener('pointerdown', down)
  }, [onClose])
  if (!t) return null
  const flip = (k) => setRow(r => (r === k ? null : k))
  const treeLine = tree ? [d.tree.line, ...['running', 'yours', 'blocked', 'done'].filter(k => counts[k]).map(k => counts[k] + ' ' + k)].join(' · ') : d.tree.line
  const tasks = waits && typeof waits.tasks_today === 'number' ? waits.tasks_today : null
  const court = waits && typeof waits.court === 'number' ? waits.court : null
  return (
    <div className="wd" ref={ref} style={style} role="dialog" aria-label={`${centre ? 'the brain' : sid}, in depth`} data-depth={sid}>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="wd-hd">
        <b>{centre ? 'the brain' : short(sid)}</b>
        <button type="button" className="wd-x" onClick={onClose} title="close (Esc); nothing stops">close</button>
      </div>
      <Row k="now" open={row === 'now'} onPress={() => flip('now')} wrap title={d.summary.from === 'card' ? 'from its state card' : d.summary.from === 'thread' ? "from its thread's last answer" : 'from the registry'}>
        {d.summary.text}
      </Row>
      {prompts.length ? (
        <div className="wd-pr" role="group" aria-label="prompts to continue">
          <span className="wd-k">continue</span>
          <div className="wd-pl">
            {prompts.map(p => (
              <button key={p} type="button" className="wd-p" onClick={() => onTalk(sid, p)}
                title={waitsForMore(p) ? 'puts it in the box; you finish it' : 'puts it in the box; press it again there, or Enter, to send'}>
                {p.trim()}{waitsForMore(p) ? <span className="k">…</span> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <Row k="jobs" open={row === 'jobs'} onPress={() => flip('jobs')}>
        {centre ? (total ? <><span className="n">{total}</span> running in {groups.length} {groups.length === 1 ? 'system' : 'systems'}</> : 'nothing running') : d.jobs.n ? <><span className="n">{d.jobs.n}</span>{d.jobs.line.slice(String(d.jobs.n).length)}</> : d.jobs.line}
      </Row>
      {row === 'jobs' ? (
        <div className="wd-in">
          {centre
            ? (groups.length ? groups.map(g => (
              <div key={g.id}>
                <div className="wd-sys">{short(g.id)} · {g.jobs.length}</div>
                {g.jobs.map(j => <Job key={j.id} j={j} />)}
              </div>
            )) : <div className="wd-none">nothing running now</div>)
            : (d.jobs.list.length ? d.jobs.list.map(j => <Job key={j.id} j={j} />) : <div className="wd-none">nothing running now</div>)}
        </div>
      ) : null}
      {centre ? (
        <>
          <div className="wd-w">
            <span className="wd-k">waits</span>
            <button type="button" onClick={() => onRoute({ route: '/tasks', title: 'tasks' })} title="the tasks page, beside">{tasks == null ? 'tasks' : <><b>{tasks}</b>{tasks === 1 ? 'task' : 'tasks'} today</>}</button>
            <button type="button" onClick={() => onRoute({ route: '/cc/page/court/', title: 'court' })} title="the court, beside">{court == null ? null : <b>{court}</b>}court</button>
          </div>
        </>
      ) : null}
      <Row k="tree" open={row === 'tree'} onPress={() => flip('tree')}>{treeLine}</Row>
      {row === 'tree' ? (
        <div className="wd-tree">
          {tree ? <ThreadTree tree={tree} cur={null} onTalk={(text) => onTalk(sid, text)} />
            : <div className="wd-none" style={{ paddingLeft: 54 }}>{d.tree.n ? 'reading the tree' : 'its thread has not drawn a tree yet'}</div>}
        </div>
      ) : null}
      <Row k="thread" go onPress={() => onRead(sid)} title="the whole thread, beside">{d.thread ? 'read the whole thread' : 'open its thread'}</Row>
    </div>
  )
}
