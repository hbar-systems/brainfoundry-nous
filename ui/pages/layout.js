import Head from 'next/head'
import React, { useEffect, useState } from 'react'

// Layout (2026-10-09): the owner's layout file on the box, as a page. The interview's answers as
// chips (change one, press apply), layouts waiting for a yes (from the interview or an installed
// pack), the accent from a short list, undo and reset, and the layout as a pack another brain can
// install. Everything is read from and written to the bridge (/cc/layout...); the bridge validates.
// No native selects or inputs of the browser's default look: chips and one plain text line.

const C = { ink: 'var(--text)', dim: 'var(--muted)', gold: 'var(--accent)', line: 'var(--border)', bg: 'var(--bg)', onAccent: 'var(--bg)', bad: '#c0605a' }
const mono = { fontFamily: 'var(--font-mono, monospace)' }
const label = { ...mono, fontSize: '10px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.dim, margin: '28px 0 10px 0' }
// Ways of working on the home (SURFACES-PICK-1, 2026-11-13): the bridge sends the list as the "surfaces"
// question (options and one sentence each in "about"). The defaults by person: a newcomer starts with the
// conversation and talk-through, the owner with every one. ?step=surfaces shows this step alone: the
// interview opens it beside the conversation for the pick by press.
const NEWCOMER = ['chat', 'talkthrough']
const NEEDS_PAGE = { decisions: 'decisions', talkthrough: 'tape', phone: 'tape' }
const ACCENTS = [['stock', null], ['white', '#e6e6e6'], ['gold', '#c9a96e'], ['green', '#88a868'], ['blue', '#6b8cce'], ['red', '#c87878']]

function Chip({ on, children, onClick, title }) {
  return (
    <span onClick={onClick} title={title} role="button"
      style={{ ...mono, fontSize: '12px', fontWeight: 300, padding: '5px 12px', marginRight: '8px', marginBottom: '8px', display: 'inline-block', cursor: 'pointer',
               border: `1px solid ${on ? C.gold : C.line}`, color: on ? C.gold : C.dim, backgroundColor: 'transparent' }}>{children}</span>
  )
}
function Btn({ children, onClick, primary, disabled, title }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      style={{ ...mono, fontSize: '12px', fontWeight: 300, padding: '6px 14px', marginRight: '8px', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.5 : 1,
               border: `1px solid ${primary ? C.gold : C.line}`, backgroundColor: 'transparent', color: primary ? C.gold : C.dim }}>{children}</button>
  )
}

export default function LayoutPage() {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [ans, setAns] = useState({})
  const [name, setName] = useState('')
  const [repo, setRepo] = useState('')
  const [packOut, setPackOut] = useState(null)
  const [surf, setSurf] = useState(null)        // the picked surface ids, while pressing; null = as saved
  const [stepOnly, setStepOnly] = useState(false)
  const [saved, setSaved] = useState('')
  useEffect(() => { try { setStepOnly(new URLSearchParams(window.location.search).get('step') === 'surfaces') } catch {} }, [])

  const take = (j, keepAns) => { setD(j); if (!keepAns) setAns(j.answers || {}) }
  const load = () => fetch('/cc/layout', { cache: 'no-store' }).then(r => (r.ok ? r.json() : Promise.reject(new Error('the bridge did not answer'))))
    .then(j => take(j)).catch(e => setErr(String(e.message || e)))
  useEffect(() => { load() }, [])
  const post = async (path, body) => {
    setErr('')
    try {
      const r = await fetch('/cc' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) { setErr(j.error || 'refused'); return null }
      if (j.questions) take(j)
      return j
    } catch { setErr('the bridge did not answer'); return null }
  }
  if (!d) return <div style={{ ...mono, color: C.dim, padding: '40px', fontSize: '13px' }}>{err || 'reading your layout'}</div>

  const pick = (q, v) => setAns(a => {
    if (q.multi) { const cur = a[q.id] || []; return { ...a, [q.id]: cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v] } }
    return { ...a, [q.id]: v }
  })
  const on = (q, v) => (q.multi ? (ans[q.id] || []).includes(v) : ans[q.id] === v)
  const lay = d.layout
  const sq = (d.questions || []).find(q => q.id === 'surfaces')
  const allSurf = sq ? sq.options.map(o => o[0]) : []
  const savedSurf = (lay && Array.isArray(lay.surfaces)) ? lay.surfaces : allSurf
  const curSurf = surf || savedSurf
  const pressSurf = (v) => { if (v === 'chat') return; setSaved(''); setSurf(curSurf.includes(v) ? curSurf.filter(x => x !== v) : allSurf.filter(x => x === v || curSurf.includes(x))) }
  const applySurf = async (list) => {
    const base = JSON.parse(JSON.stringify(lay || d.default))
    base.surfaces = list
    const answers = { ...(d.answers || {}) }
    if (list) answers.surfaces = list; else delete answers.surfaces
    const j = await post('/layout/save', { layout: base, answers: Object.keys(answers).length ? answers : undefined })
    if (j) { setSurf(null); setSaved(list ? 'saved: the home shows ' + list.length + ' of ' + allSurf.length : 'saved: the home shows every one') }
  }
  const pages = d.pages || {}
  const surfaces = sq && (
    <div data-step="surfaces">
      <div style={label}>ways of working on your home</div>
      <div style={{ fontSize: '15px', color: C.ink, margin: '0 0 4px 0' }}>{sq.ask}</div>
      <div style={{ fontSize: '13px', color: C.dim, margin: '0 0 14px 0', lineHeight: 1.6 }}>Press to pick. What you leave out only leaves the home; its address keeps working.</div>
      {sq.options.map(([v, w]) => {
        const picked = curSurf.includes(v)
        const missing = NEEDS_PAGE[v] && !pages[NEEDS_PAGE[v]]
        return (
          <div key={v} onClick={() => pressSurf(v)} role="button" aria-pressed={picked}
            style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: '14px', rowGap: '4px', padding: '10px 12px', marginBottom: '6px', cursor: v === 'chat' ? 'default' : 'pointer',
                     border: `1px solid ${picked ? C.gold : C.line}`, opacity: picked ? 1 : 0.72 }}>
            <span style={{ ...mono, fontSize: '12px', color: picked ? C.gold : C.dim, minWidth: '11em', flexShrink: 0 }}>{picked ? '● ' : '○ '}{w}</span>
            <span style={{ fontSize: '13px', lineHeight: 1.55, color: picked ? C.ink : C.dim, minWidth: 0, flex: '1 1 18em' }}>
              {sq.about && sq.about[v] ? sq.about[v] + '.' : ''}{v === 'chat' ? ' Always on.' : ''}{missing ? ' This brain has no page for it yet; picked, it shows once there is one.' : ''}
            </span>
          </div>
        )
      })}
      <div style={{ marginTop: '12px' }}>
        <Btn primary onClick={() => applySurf(curSurf)} disabled={!surf}>apply</Btn>
        <Chip on={surf ? surf.join() === NEWCOMER.join() : (lay && Array.isArray(lay.surfaces) && lay.surfaces.join() === NEWCOMER.join())} onClick={() => { setSaved(''); setSurf(NEWCOMER.slice()) }} title="the conversation and talk-through">newcomer</Chip>
        <Chip on={surf ? surf.length === allSurf.length : !(lay && Array.isArray(lay.surfaces))} onClick={() => { setSaved(''); setSurf(allSurf.slice()) }} title="every way of working">everything</Chip>
        {surf && <Btn onClick={() => setSurf(null)}>revert</Btn>}
      </div>
      {saved ? <div style={{ ...mono, fontSize: '11px', color: C.dim, marginTop: '4px' }}>{saved}. The home picks it up on its next load.</div> : null}
    </div>
  )
  if (stepOnly) return (
    <div style={{ maxWidth: '760px', margin: '0 auto', padding: '22px 22px 60px', color: C.ink, backgroundColor: C.bg, minHeight: '100vh', fontWeight: 300 }}>
      <Head><title>Ways of working</title></Head>
      {err ? <p style={{ ...mono, fontSize: '12px', color: C.bad }}>{err}</p> : null}
      {surfaces}
      <div style={{ ...mono, fontSize: '11px', color: C.dim, marginTop: '22px' }}><a href="/layout" style={{ color: C.dim }}>the whole layout</a></div>
    </div>
  )
  const accent = lay && lay.vars && lay.vars['--accent']
  const setAccent = (hex) => {
    const base = JSON.parse(JSON.stringify(lay || d.default))
    base.vars = { ...(base.vars || {}) }
    if (hex) base.vars['--accent'] = hex; else delete base.vars['--accent']
    post('/layout/save', { layout: base, answers: Object.keys(d.answers || {}).length ? d.answers : undefined })
  }

  return (
    <div style={{ maxWidth: '760px', margin: '0 auto', padding: '28px 22px 80px', color: C.ink, backgroundColor: C.bg, minHeight: '100vh', fontWeight: 300 }}>
      <Head><title>Layout</title></Head>
      <div style={{ ...mono, fontSize: '11px', letterSpacing: '0.18em', textTransform: 'uppercase', color: C.gold }}>layout</div>
      <p style={{ fontSize: '14px', lineHeight: 1.7, color: C.dim, margin: '10px 0 0 0' }}>
        Your arrangement of the console, kept as a file on this box. Updates never touch it. {lay ? (lay.name ? `Current: ${lay.name}.` : 'A layout is set.') : 'None is set; the console is stock.'}
      </p>
      {err ? <p style={{ ...mono, fontSize: '12px', color: C.bad }}>{err}</p> : null}

      {d.proposals.length > 0 && <>
        <div style={label}>waiting for your yes</div>
        {d.proposals.map(p => (
          <div key={p.id} style={{ border: `1px solid ${C.line}`, padding: '12px 14px', marginBottom: '10px' }}>
            <div style={{ ...mono, fontSize: '11px', color: C.dim }}>{p.source}{p.note && p.source.startsWith('pack') ? ` · ${p.note}` : ''}</div>
            <div style={{ fontSize: '14px', margin: '6px 0 10px 0' }}>{p.summary}</div>
            <Btn primary onClick={() => post('/layout/approve', { id: p.id })}>apply</Btn>
            <Btn onClick={() => post('/layout/dismiss', { id: p.id })}>dismiss</Btn>
          </div>
        ))}
        <div style={{ ...mono, fontSize: '11px', color: C.dim }}>Applying replaces your layout; undo steps back once.</div>
      </>}

      <div style={label}>your answers</div>
      {d.questions.filter(q => q.id !== 'surfaces').map(q => (
        <div key={q.id} style={{ marginBottom: '12px' }}>
          <div style={{ fontSize: '14px', color: C.ink, marginBottom: '6px' }}>{q.ask}</div>
          {q.options.map(([v, w]) => <Chip key={v} on={on(q, v)} onClick={() => pick(q, v)}>{w}</Chip>)}
        </div>
      ))}
      <Btn primary onClick={() => post('/layout/answers', { answers: ans })} disabled={Object.keys(ans).length === 0}>apply answers</Btn>
      <Btn onClick={() => setAns(d.answers || {})}>revert chips</Btn>

      {surfaces}

      <div style={label}>accent</div>
      {ACCENTS.map(([n, hex]) => <Chip key={n} on={(accent || null) === hex} onClick={() => setAccent(hex)}>{n}</Chip>)}

      <div style={label}>view</div>
      {[['talk', 'thread'], ['doors', 'doors']].map(([v, w]) => <Chip key={v} on={((lay && lay.view) || 'talk') === v}
        title={v === 'talk' ? 'The console opens on your thread, as it always has' : 'The console opens on a blank thread with a few large doors, one for each thing you do here'}
        onClick={() => { const base = JSON.parse(JSON.stringify(lay || d.default)); base.view = v; post('/layout/save', { layout: base, answers: Object.keys(d.answers || {}).length ? d.answers : undefined }) }}>{w}</Chip>)}

      <div style={label}>spacing</div>
      {[['compact', 'compact'], ['comfortable', 'comfortable']].map(([v, w]) => <Chip key={v} on={((lay && lay.density) || 'compact') === v} title="Spacing inside message bubbles"
        onClick={() => { const base = JSON.parse(JSON.stringify(lay || d.default)); base.density = v; post('/layout/save', { layout: base, answers: Object.keys(d.answers || {}).length ? d.answers : undefined }) }}>{w}</Chip>)}

      <div style={label}>history</div>
      <Btn onClick={() => post('/layout/undo')}>undo</Btn>
      <Btn onClick={() => post('/layout/reset')} disabled={!lay} title="Back to the stock console in every browser; undo brings your layout back">reset to stock</Btn>
      <div style={{ ...mono, fontSize: '11px', color: C.dim, marginTop: '6px' }}>Blocks you dragged or hid in a browser are saved to the file with "save layout" under details in the console.</div>

      <div style={label}>share as a pack</div>
      {!lay ? <p style={{ fontSize: '13px', color: C.dim }}>Set a layout first.</p> : <>
        <p style={{ fontSize: '13px', lineHeight: 1.7, color: C.dim, margin: '0 0 10px 0' }}>
          Writes three files (brain-app.yaml, layout.json, dist/index.html) into your out folder. Put them in a public repository on GitHub, GitLab or Codeberg; another brain installs that repository on its Apps page and receives the layout as a proposal it can refuse. The pack carries no code and no colours but the ones listed above.
        </p>
        <input value={name} onChange={e => setName(e.target.value.slice(0, 40))} placeholder="name of the pack"
          style={{ ...mono, fontSize: '12px', fontWeight: 300, width: '45%', padding: '6px 10px', marginRight: '8px', color: C.ink, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 0, outline: 'none' }} />
        <input value={repo} onChange={e => setRepo(e.target.value)} placeholder="https://github.com/you/layout-name"
          style={{ ...mono, fontSize: '12px', fontWeight: 300, width: '45%', padding: '6px 10px', marginBottom: '10px', color: C.ink, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 0, outline: 'none' }} />
        <div>
          <Btn primary onClick={async () => { const j = await post('/layout/export/write', { name: name || undefined, repo: repo || undefined }); if (j) setPackOut(j) }}>write the pack</Btn>
        </div>
        {packOut && <p style={{ ...mono, fontSize: '12px', color: C.dim, lineHeight: 1.7 }}>
          Written to <a href={`/files?path=${encodeURIComponent(packOut.dir)}`} style={{ color: C.gold }}>{packOut.dir}</a>.{packOut.repo_set ? '' : ' The repository line still reads OWNER/REPO: set your repository above, or edit brain-app.yaml, before you publish.'}
        </p>}
      </>}
    </div>
  )
}
