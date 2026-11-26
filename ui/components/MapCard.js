// Your map (ORGANISE-1, 2026-11-26), one card on the quiet home, first after the move-in. The brain read what
// arrived and proposes the person's own areas (api/organise.py): chips with counts; press one to see what is
// in it, rename it, merge it into another, or move an item; one "Looks right" for the named map. Nothing is
// labelled before that yes; afterwards the card folds to one line with Undo. Words and rules: ui/lib/mapCard.js.
import { useEffect, useState } from 'react'
import css from 'styled-jsx/css'
import { mapWords, mapStep, chips, renameOp, mergeOp, moveOp, arrivedSince } from '../lib/mapCard'

const API = '/api/bf'
const SHOW = 12

const j = (u, body) => fetch(u, body === undefined ? { cache: 'no-store' } : {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
}).then(r => (r.ok ? r.json() : Promise.reject(r.status)))

export default function MapCard({ lang = 'en', initial = null }) {
  const W = mapWords(lang)
  const [st, setSt] = useState(initial)
  const [making, setMaking] = useState(false)
  const [openId, setOpenId] = useState(null)
  const [items, setItems] = useState({})        // area id -> [{name, title, kind}]
  const [shown, setShown] = useState(SHOW)
  const [mode, setMode] = useState(null)        // null | 'rename' | 'merge' | {move: item name}
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [expanded, setExpanded] = useState(false)

  const load = () => j(`${API}/organise`).then(setSt).catch(() => setSt(null))
  useEffect(() => { if (!initial) load() }, [])

  const step = mapStep(st)
  useEffect(() => {   // ready and no map yet: make it now, once
    if (step !== 'propose' || making) return
    setMaking(true)
    j(`${API}/organise/propose`, { lang }).then(p => { setSt(p); setMaking(false) }).catch(() => setMaking(false))
  }, [step])

  const area = (st && st.areas || []).find(a => a.id === openId) || null
  useEffect(() => {
    if (!openId || items[openId]) return
    j(`${API}/organise/area?id=${encodeURIComponent(openId)}`).then(d => setItems(m => ({ ...m, [openId]: d.items || [] }))).catch(() => {})
  }, [openId])

  const send = async (op) => {
    if (!op) return
    setBusy(true); setErr('')
    try {
      const p = await j(`${API}/organise/edit`, op)
      setSt(s => ({ ...s, ...p })); setItems({}); setMode(null)
      if (op.op === 'merge') setOpenId(op.into)
    } catch { setErr(W.failed) }
    setBusy(false)
  }
  const accept = async () => {
    setBusy(true); setErr('')
    try { const p = await j(`${API}/organise/accept`, { id: st.id }); setSt({ ...p, undo: true }); setOpenId(null); setNote('') } catch { setErr(W.failed) }
    setBusy(false)
  }
  const undo = async () => {
    setBusy(true); setErr('')
    try { await j(`${API}/organise/undo`, {}); setNote(W.undone); await load() } catch { setErr(W.failed) }
    setBusy(false)
  }

  if (step === 'hidden') return null
  if (step === 'propose') {
    return (<div className="mp"><section className="mp-card"><h2 className="mp-title">{W.title}</h2><p className="mp-sub">{W.making}</p></section><style jsx>{styles}</style></div>)
  }

  const cs = chips(st)
  if (step === 'accepted' && !expanded) {
    const k = arrivedSince(st)
    return (
      <div className="mp">
        <section className="mp-card mp-folded">
          <p className="mp-sub mp-first">{W.set(cs.length)}{k ? ` ${W.arrived(k)}` : ''}</p>
          {st.world && <p className="mp-dim">{W.world(st.world)}</p>}
          <div className="mp-actions">
            <button className="mp-btn" onClick={() => setExpanded(true)}>{W.open}</button>
            {st.undo && <button className="mp-link" onClick={undo} disabled={busy}>{W.undo}</button>}
          </div>
          {err && <p className="mp-bad">{err}</p>}
        </section>
        <style jsx>{styles}</style>
      </div>
    )
  }

  const editable = step === 'proposed'
  const list = (openId && items[openId]) || []
  return (
    <div className="mp">
      <section className="mp-card" aria-label={W.title}>
        <h2 className="mp-title">{W.title}</h2>
        <p className="mp-sub">{W.found(st.docs || 0, st.chats || 0, cs.length)}</p>
        {note && <p className="mp-dim">{note}</p>}
        <div className="mp-chips" role="list">
          {cs.map(c => (
            <button key={c.id} role="listitem" className={`mp-chip${openId === c.id ? ' mp-chip-on' : ''}${c.archive ? ' mp-chip-arch' : ''}`}
              onClick={() => { setOpenId(openId === c.id ? null : c.id); setMode(null); setShown(SHOW) }} aria-expanded={openId === c.id}>
              <span className="mp-cname">{c.name}</span><span className="mp-count">{c.count.toLocaleString('en-US')}</span>
            </button>
          ))}
        </div>

        {area && (
          <div className="mp-area">
            {mode === 'rename' ? (
              <form className="mp-rename" onSubmit={e => { e.preventDefault(); send(renameOp(area.id, draft)) }}>
                <input className="mp-input" value={draft} onChange={e => setDraft(e.target.value)} maxLength={40} autoFocus aria-label={W.rename} />
                <button className="mp-btn mp-primary" type="submit" disabled={busy || !draft.trim()}>{W.save}</button>
                <button className="mp-link" type="button" onClick={() => setMode(null)}>{W.close}</button>
              </form>
            ) : (
              <h3 className="mp-aname">{area.name}</h3>
            )}
            {area.line && <p className="mp-line">{area.line}</p>}
            <p className="mp-dim">{W.items(area.count, area.docs || 0, area.chats || 0)}</p>
            <ul className="mp-items">
              {(list.length ? list : (area.examples || [])).slice(0, shown).map(it => (
                <li key={it.name}>
                  <button className={`mp-item${mode && mode.move === it.name ? ' mp-item-on' : ''}`} disabled={!editable}
                    onClick={() => editable && setMode(mode && mode.move === it.name ? null : { move: it.name })}>
                    <span className="mp-ititle">{it.title || it.name}</span>
                    {it.kind === 'chat' && <span className="mp-tag">{W.chat}</span>}
                  </button>
                  {mode && mode.move === it.name && (
                    <div className="mp-chips mp-to">
                      <span className="mp-dim">{W.move}</span>
                      {cs.filter(c => c.id !== area.id).map(c => (
                        <button key={c.id} className="mp-chip mp-chip-sm" disabled={busy} onClick={() => send(moveOp(it.name, c.id))}>{c.name}</button>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {list.length > shown && <button className="mp-link" onClick={() => setShown(s => s + 50)}>{W.more(Math.min(50, list.length - shown))}</button>}
            {editable && mode !== 'rename' && (
              <div className="mp-actions mp-tools">
                <button className="mp-btn" onClick={() => { setDraft(area.name); setMode('rename') }}>{W.rename}</button>
                <button className={`mp-btn${mode === 'merge' ? ' mp-btn-on' : ''}`} onClick={() => setMode(mode === 'merge' ? null : 'merge')}>{W.merge}</button>
              </div>
            )}
            {mode === 'merge' && (
              <div className="mp-chips mp-to">
                {cs.filter(c => c.id !== area.id).map(c => (
                  <button key={c.id} className="mp-chip mp-chip-sm" disabled={busy} onClick={() => send(mergeOp(area.id, c.id))}>{W.mergeInto(c.name)}</button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mp-actions">
          {editable ? (
            <>
              <button className="mp-btn mp-primary" onClick={accept} disabled={busy}>{busy ? W.saving : W.looks}</button>
              <span className="mp-dim">{W.nothing}</span>
            </>
          ) : (
            <>
              <button className="mp-btn" onClick={() => { setExpanded(false); setOpenId(null) }}>{W.close}</button>
              {st.undo && <button className="mp-link" onClick={undo} disabled={busy}>{W.undo}</button>}
            </>
          )}
        </div>
        {err && <p className="mp-bad">{err}</p>}
      </section>
      <style jsx>{styles}</style>
    </div>
  )
}

const styles = css`
  .mp { margin: 4px 0 22px; }
  .mp-card { position: relative; padding: 26px 28px 24px; border-radius: 18px; background: var(--surface); border: 1px solid var(--border); color: var(--text); }
  .mp-folded { padding: 18px 24px; }
  .mp-title { margin: 0; font-family: var(--font-display); font-weight: 300; font-size: 24px; letter-spacing: 0.01em; }
  .mp-sub { margin: 10px 0 0; font-size: 18px; line-height: 1.5; }
  .mp-first { margin-top: 0; }
  .mp-dim { margin: 8px 0 0; font-size: 15px; line-height: 1.45; color: var(--text-dim, var(--muted)); }
  .mp-bad { margin: 10px 0 0; color: #d99a8a; font-size: 15px; }
  .mp-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 0; }
  .mp-to { margin: 10px 0 4px; align-items: center; }
  .mp-chip { display: inline-flex; align-items: center; gap: 10px; max-width: 100%; font: inherit; font-size: 17px; min-height: 44px; padding: 0 8px 0 16px; border-radius: 999px; cursor: pointer;
    color: var(--text); background: transparent; border: 1px solid color-mix(in srgb, var(--border) 50%, var(--text) 25%); transition: background-color 150ms ease-out, border-color 150ms ease-out, transform 120ms ease-out; }
  .mp-chip:hover:not(:disabled) { background: color-mix(in srgb, var(--text) 7%, transparent); }
  .mp-chip:active:not(:disabled) { transform: scale(0.97); }
  .mp-chip:focus-visible, .mp-btn:focus-visible, .mp-item:focus-visible, .mp-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .mp-chip-on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
  .mp-chip-arch { border-style: dashed; }
  .mp-chip-sm { font-size: 15px; min-height: 38px; padding: 0 14px; }
  .mp-cname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mp-count { font-family: var(--font-mono, ui-monospace, monospace); font-size: 13px; letter-spacing: 0.06em; padding: 3px 9px; border-radius: 999px; color: var(--text-dim, var(--muted)); background: color-mix(in srgb, var(--bg) 60%, transparent); }
  .mp-area { margin: 16px 0 0; padding: 18px 18px 14px; border-radius: 14px; border: 1px solid var(--border); background: color-mix(in srgb, var(--bg) 45%, transparent); }
  .mp-aname { margin: 0; font-family: var(--font-display); font-weight: 400; font-size: 20px; overflow-wrap: anywhere; }
  .mp-line { margin: 6px 0 0; font-size: 17px; line-height: 1.5; }
  .mp-items { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 4px; }
  .mp-item { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; text-align: left; font: inherit; font-size: 16px; padding: 9px 12px; border-radius: 10px; cursor: pointer; color: var(--text); background: transparent; border: 1px solid transparent; }
  .mp-item:hover:not(:disabled) { border-color: var(--border); }
  .mp-item:disabled { cursor: default; }
  .mp-item-on { border-color: var(--accent); }
  .mp-ititle { min-width: 0; overflow-wrap: anywhere; }
  .mp-tag { flex-shrink: 0; font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim, var(--muted)); }
  .mp-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 18px; margin: 22px 0 0; }
  .mp-tools { margin-top: 14px; }
  .mp-btn { font: inherit; font-size: 17px; line-height: 1.2; min-height: 48px; padding: 0 22px; border-radius: 12px; cursor: pointer; color: var(--text); background: transparent;
    border: 1px solid color-mix(in srgb, var(--border) 50%, var(--text) 30%); transition: background-color 150ms ease-out, transform 120ms ease-out; }
  .mp-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--text) 7%, transparent); }
  .mp-btn:active:not(:disabled) { transform: scale(0.98); }
  .mp-btn:disabled { opacity: 0.6; cursor: default; }
  .mp-btn-on { border-color: var(--accent); }
  .mp-primary { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }
  .mp-primary:hover:not(:disabled) { background: color-mix(in srgb, var(--accent) 88%, var(--text) 12%); }
  .mp-link { font: inherit; font-size: 16px; background: none; border: 0; padding: 0; cursor: pointer; color: var(--accent); text-decoration: underline; text-underline-offset: 3px; }
  .mp-rename { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .mp-input { flex: 1 1 200px; min-width: 0; font: inherit; font-size: 18px; min-height: 46px; padding: 0 14px; border-radius: 10px; color: var(--text); background: var(--bg); border: 1px solid var(--accent); outline: none; }
  @media (max-width: 560px) {
    .mp-card { padding: 20px 18px; border-radius: 16px; }
    .mp-title { font-size: 21px; }
    .mp-sub { font-size: 17px; }
    .mp-chip { font-size: 16px; }
    .mp-actions .mp-btn { width: 100%; }
    .mp-area { padding: 14px 12px 12px; }
  }
`
