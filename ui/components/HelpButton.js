// "Something wrong? Ask hbar" (MEMBERS-14, 2026-11-23): one small button in the bottom-right
// corner of every console screen, and a panel that sends a help request to the helper brain.
// hbar 2026-11-23: "if people have problems with their brains they can ask for help through the
// Federation protocol". What is sent: the member's words, the screen's route, the last few press
// names (ui/lib/presses.js recent()), the console language. The panel shows that list before Send.
// No memory, no chat text, no file names: the brain refuses anything beyond the shape
// (api/federation_help.py). The answer comes back the same way and shows here, with a dot.
import { useCallback, useEffect, useRef, useState } from 'react'
import Router from 'next/router'
import useConsoleLang from '../lib/useConsoleLang'
import { helpWords, fill } from '../lib/helpText'
import { recent, routeName } from '../lib/presses'

const SEEN_KEY = 'bf-help-seen'
const EDGE = 12
const INTERACTIVE = 'button, textarea, input, select, a[href], a[onclick], [role="button"], [contenteditable="true"]'

function seenSet() {
  try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]')) } catch (e) { return new Set() }
}
function markSeen(rids) {
  try {
    const s = seenSet()
    rids.forEach(r => s.add(r))
    localStorage.setItem(SEEN_KEY, JSON.stringify(Array.from(s).slice(-200)))
  } catch (e) {}
}

// How far above the bottom edge the button sits so it covers no control of the page under it
// (the chat's send button above all): raise it over whatever control is in its spot, a few times.
function clearBottom(el) {
  if (!el || typeof document.elementsFromPoint !== 'function') return EDGE
  const w = el.offsetWidth || 120
  const h = el.offsetHeight || 32
  const vw = window.innerWidth
  const vh = window.innerHeight
  let bottom = EDGE
  for (let i = 0; i < 6; i++) {
    const top = vh - bottom - h
    const left = vw - EDGE - w
    const pts = [[left + 2, top + 2], [left + w - 2, top + 2], [left + 2, top + h - 2], [left + w - 2, top + h - 2], [left + w / 2, top + h / 2]]
    let hit = null
    for (const [x, y] of pts) {
      for (const e of document.elementsFromPoint(x, y)) {
        if (el.contains(e) || (e.closest && e.closest('[data-help-panel]'))) continue
        const c = e.closest ? e.closest(INTERACTIVE) : null
        if (c) { hit = c; break }
      }
      if (hit) break
    }
    if (!hit) break
    const next = vh - hit.getBoundingClientRect().top + 8
    if (next <= bottom || next > vh * 0.6) break
    bottom = next
  }
  return Math.round(bottom)
}

export default function HelpButton() {
  const lang = useConsoleLang()
  const W = helpWords(lang)
  const [st, setSt] = useState(undefined) // undefined: not loaded; null: the brain did not answer
  const [open, setOpen] = useState(false)
  const [words, setWords] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState(null) // {ok, text}
  const [screen, setScreen] = useState('/')
  const [pressed, setPressed] = useState([])
  const [bottom, setBottom] = useState(EDGE)
  const [narrow, setNarrow] = useState(false)
  const [seen, setSeen] = useState(() => new Set())
  const btnRef = useRef(null)

  const load = useCallback(() => {
    fetch('/api/bf/v1/help/status', { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null))
      .then(d => setSt(d && typeof d === 'object' ? d : null))
      .catch(() => setSt(null))
  }, [])

  useEffect(() => {
    setSeen(seenSet())
    load()
    const t = setInterval(load, 60000)
    window.addEventListener('focus', load)
    return () => { clearInterval(t); window.removeEventListener('focus', load) }
  }, [load])

  useEffect(() => {
    const place = () => {
      setNarrow(window.innerWidth < 520)
      const b = clearBottom(btnRef.current)
      setBottom(prev => (prev === b ? prev : b))
    }
    place()
    const t = setInterval(place, 2000)
    window.addEventListener('resize', place)
    Router.events.on('routeChangeComplete', place)
    return () => { clearInterval(t); window.removeEventListener('resize', place); Router.events.off('routeChangeComplete', place) }
  }, [])

  const asked = (st && Array.isArray(st.asked)) ? st.asked : []
  const unseen = asked.filter(a => a.answer && !seen.has(a.rid))

  const openPanel = () => {
    setScreen(routeName(window.location.pathname) || '/')
    setPressed(recent(5))
    setNote(null)
    setOpen(true)
    load()
  }
  const closePanel = () => {
    const done = asked.filter(a => a.answer).map(a => a.rid)
    if (done.length) { markSeen(done); setSeen(seenSet()) }
    setOpen(false)
  }

  const blocked = st === null ? W.down : st && !st.ready ? (st.helper ? W.notPinned : W.noHelper) : null

  const send = async () => {
    if (!words.trim() || busy || blocked) return
    setBusy(true); setNote(null)
    try {
      const r = await fetch('/api/bf/v1/help/ask', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ screen, pressed, words: words.trim(), lang }),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) setNote({ ok: false, text: `${W.failed} ${d.detail || r.status}` })
      else { setNote({ ok: true, text: W.sent }); setWords('') }
    } catch (e) {
      setNote({ ok: false, text: `${W.failed} ${e.message}` })
    } finally { setBusy(false); load() }
  }

  const retry = async (rid) => {
    await fetch('/api/bf/v1/federation/records/redeliver', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rid }),
    }).catch(() => {})
    load()
  }

  if (st === undefined || (st && st.button === false)) return null

  const pill = {
    position: 'fixed', right: EDGE, bottom: `calc(${bottom}px + env(safe-area-inset-bottom, 0px))`, zIndex: 9990,
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 11px', borderRadius: 999,
    background: 'var(--surface)', color: unseen.length ? 'var(--text)' : 'var(--muted)',
    border: `1px solid ${unseen.length ? 'var(--accent)' : 'var(--border)'}`, fontSize: 12, lineHeight: 1.4,
    fontFamily: 'var(--font-body)', cursor: 'pointer', boxShadow: '0 2px 10px rgba(0,0,0,0.25)',
  }
  const small = { fontSize: 12, color: 'var(--muted)', margin: 0, lineHeight: 1.5 }

  return (
    <>
      <button ref={btnRef} type="button" data-help-button="1" onClick={open ? closePanel : openPanel}
        aria-expanded={open} title={W.title} style={pill}>
        {unseen.length > 0 && <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: 999, background: 'var(--accent)' }} />}
        {unseen.length > 0 ? W.answered : narrow ? W.short : W.button}
      </button>
      {open && (
        <div data-help-panel="1" role="dialog" aria-label={W.title} style={{
          position: 'fixed', right: EDGE, bottom: `calc(${bottom + 42}px + env(safe-area-inset-bottom, 0px))`, zIndex: 9991,
          width: `min(360px, calc(100vw - ${EDGE * 2}px))`, maxHeight: `calc(100vh - ${bottom + 120}px)`, overflowY: 'auto',
          background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 12,
          padding: '14px 16px', boxShadow: '0 8px 30px rgba(0,0,0,0.4)', fontFamily: 'var(--font-body)', boxSizing: 'border-box',
        }}>
          <p style={{ margin: '0 0 4px 0', fontSize: 15, fontWeight: 600 }}>{W.title}</p>

          {asked.filter(a => a.answer).slice(0, 3).map(a => (
            <div key={a.rid} style={{ margin: '8px 0', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--accent)',
              background: 'color-mix(in srgb, var(--accent) 8%, transparent)' }}>
              <p style={{ ...small, marginBottom: 4 }}>{a.words.length > 90 ? a.words.slice(0, 90) + '...' : a.words}</p>
              <p style={{ margin: 0, fontSize: 14, whiteSpace: 'pre-wrap' }}><b>{W.answerFrom}</b> {a.answer.words}</p>
            </div>
          ))}

          {blocked ? (
            <p style={{ fontSize: 14, margin: '10px 0' }}>{blocked}</p>
          ) : (
            <>
              <p style={{ ...small, margin: '0 0 8px 0' }}>{W.intro}</p>
              <textarea value={words} onChange={e => setWords(e.target.value)} rows={4} maxLength={2000}
                placeholder={W.placeholder} disabled={busy} aria-label={W.placeholder}
                style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', borderRadius: 8, resize: 'vertical',
                  background: 'var(--bg)', color: 'var(--text)', border: '1px solid var(--border)', fontFamily: 'inherit',
                  fontSize: 14, lineHeight: 1.5, outline: 'none' }} />
              <p style={{ ...small, margin: '10px 0 4px 0', color: 'var(--text)' }}>{W.willSend}</p>
              <ul style={{ ...small, paddingLeft: 18, margin: '0 0 6px 0' }}>
                <li>{W.yourWords}</li>
                <li>{fill(W.screen, { screen })}</li>
                <li>{pressed.length ? fill(W.pressed, { list: pressed.join(', ') }) : W.pressedNone}</li>
                <li>{W.langVersion}</li>
              </ul>
              <p style={{ ...small, margin: '0 0 10px 0' }}>{W.nothingElse}</p>
            </>
          )}

          {note && <p style={{ fontSize: 13, margin: '0 0 8px 0', color: note.ok ? 'var(--text)' : '#c98080' }}>{note.text}</p>}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button type="button" onClick={closePanel}
              style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--muted)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit' }}>{W.close}</button>
            {!blocked && (
              <button type="button" onClick={send} disabled={!words.trim() || busy}
                style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--border)', fontSize: 13, fontFamily: 'inherit',
                  background: words.trim() && !busy ? 'var(--accent)' : 'var(--surface)',
                  color: words.trim() && !busy ? 'var(--bg)' : 'var(--muted)',
                  cursor: words.trim() && !busy ? 'pointer' : 'not-allowed' }}>{busy ? W.sending : W.send}</button>
            )}
          </div>

          {asked.filter(a => !a.answer).length > 0 && (
            <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
              <p style={{ ...small, marginBottom: 4 }}>{W.earlier}</p>
              {asked.filter(a => !a.answer).slice(0, 3).map(a => (
                <p key={a.rid} style={{ ...small, margin: '2px 0' }}>
                  {a.words.length > 60 ? a.words.slice(0, 60) + '...' : a.words}{' '}
                  <span style={{ color: 'var(--text)' }}>({a.delivered ? W.waiting : W.notDelivered})</span>
                  {!a.delivered && <> <a onClick={() => retry(a.rid)} style={{ textDecoration: 'underline', cursor: 'pointer' }}>{W.retry}</a></>}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  )
}
