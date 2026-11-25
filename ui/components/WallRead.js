import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import LineSlot, { LINE_SLOT_CSS } from './LineSlot'
import { pointOf, pointsIn, lineText, anchorSlot, aboutBlock, HOLD_MS } from '../lib/linetalk'
import { lastAnswer, transcribe } from '../lib/wall'

// Reading a thread from the wall (LINE-TALK-1, 2026-11-25, hbar: "how can we read thread thru wall? like something pop
// out?"). A press on a system's line (or the centre's) opens its thread's last answer as a card over the wall: not a
// navigation, nothing is sent by opening it, Esc or the × closes it. The line talk of the chat works inside it: a
// press on a point line opens a slot under it, Enter sends every filled slot as one message into that system's
// standing thread (the wall's own door, ui/lib/wall.js sendText), as About this: "<line>" - <words>. Holding a line
// for half a second records into the slot until the release (the wall's recorder, then /cc/transcribe); the slot's
// mic does the same with two presses. "the whole thread" stays for the full pane.

const CSS = `
.wr-veil{position:fixed;inset:0;z-index:60;background:rgba(0,0,0,.55);display:flex;align-items:flex-start;justify-content:center;
  padding:calc(var(--nav-h,52px) + 28px) 16px 24px;animation:wr-in 160ms cubic-bezier(.2,.7,.2,1)}
.wr{width:min(720px,100%);max-height:calc(100vh - var(--nav-h,52px) - 60px);display:flex;flex-direction:column;background:#141518;color:#e9e7e2;
  border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.6);font:400 15px/1.55 var(--font-body,system-ui,sans-serif);
  --lt-ink:#e9e7e2;--lt-dim:#9a978f;--lt-accent:var(--accent,#c9a96e);--lt-bg:rgba(255,255,255,.05)}
.wr-h{display:flex;align-items:baseline;gap:12px;padding:12px 16px 8px}
.wr-nm{font-size:15px;font-weight:500;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.wr-h button{font:inherit;font-size:13px;color:#9a978f;background:none;border:0;cursor:pointer;padding:0}
.wr-h button:hover{color:var(--accent,#c9a96e)}
.wr-now{margin:0 16px 6px;font-size:12px;color:var(--accent,#c9a96e)}
.wr-b{overflow:auto;padding:4px 18px 18px;min-height:0}
.wr-b :where(p,ul,ol,table,pre,blockquote,h1,h2,h3,h4){margin:0 0 10px}
.wr-b :where(h1,h2,h3,h4){font-size:16px;font-weight:600}
.wr-b li{margin:2px 0}.wr-b li > p{margin:0}
.wr-b a{color:var(--accent,#c9a96e)}
.wr-b code{font-size:13px;background:rgba(255,255,255,.06);padding:0 4px;border-radius:4px}
.wr-b pre{background:rgba(255,255,255,.04);padding:8px 10px;border-radius:8px;overflow:auto}
.wr-b table{border-collapse:collapse;font-size:14px}.wr-b td,.wr-b th{padding:3px 8px;border-bottom:1px solid rgba(255,255,255,.08);text-align:left}
.wr-b li,.wr-b h1,.wr-b h2,.wr-b h3,.wr-b h4,.wr-b tr{cursor:text}
.wr-q{color:#9a978f;padding:14px 18px 20px}
.wr-f{padding:6px 16px 12px;font-size:12px;color:#5d5b56}
@keyframes wr-in{from{opacity:0}}
@media(prefers-reduced-motion:reduce){.wr-veil{animation:none}}
`

export default function WallRead({ sid, thread, title, now, onClose, onSend, onWhole, recorder, f }) {
  const fetcher = f || ((...a) => fetch(...a))
  const [msg, setMsg] = useState(null)          // null: reading; {text} | {error}
  const [slots, setSlots] = useState([])        // { id, idx, quote, text }
  const [focus, setFocus] = useState(null)      // { id, n }
  const [rec, setRec] = useState(null)          // { id, state: 'rec' | 'busy' }
  const [note, setNote] = useState('')
  const body = useRef(null)
  const hosts = useRef({})
  const hold = useRef(null)
  const [, tick] = useState(0)
  const slotsRef = useRef(slots); slotsRef.current = slots
  const recRef = useRef(rec); recRef.current = rec

  useEffect(() => {
    let off = false
    if (!thread) { setMsg({ error: 'no thread here yet' }); return }
    lastAnswer(fetcher, thread).then(r => { if (!off) setMsg(r) })
    return () => { off = true }
  }, [thread])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (e) => {
      if (e.key !== 'Escape') return
      if (e.target && e.target.closest && e.target.closest('[data-lineslot]')) return   // the slot's own Esc first
      e.stopPropagation()
      if (recRef.current && recorder) { recorder.drop(); setRec(null); return }
      onClose()
    }
    document.addEventListener('keydown', k, true)
    return () => { document.removeEventListener('keydown', k, true); if (recRef.current && recorder) recorder.drop() }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const root = body.current
    const hs = hosts.current
    let changed = false
    const want = new Set(slots.map(s => s.id))
    for (const s of slots) {
      const h = hs[s.id]
      if (h && h.host.isConnected) continue
      const el = root ? pointsIn(root)[s.idx] : null
      const a = el ? anchorSlot(el) : null
      if (a) { hs[s.id] = a; changed = true }
    }
    for (const id of Object.keys(hs)) if (!want.has(id)) { try { hs[id].remove() } catch {} delete hs[id]; changed = true }
    if (changed) tick(x => x + 1)
  })

  const pointAt = (target) => {
    const root = body.current
    const el = root ? pointOf(target, root) : null
    const quote = el ? lineText(el) : ''
    return quote ? { idx: pointsIn(root).indexOf(el), quote } : null
  }
  const open = (pt) => {
    const have = slotsRef.current.find(s => s.idx === pt.idx)
    const id = have ? have.id : 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5)
    if (!have) setSlots(l => [...l, { id, idx: pt.idx, quote: pt.quote, text: '' }])
    setFocus(x => ({ id, n: ((x && x.n) || 0) + 1 }))
    return id
  }
  const setText = (id, text) => setSlots(l => l.map(s => (s.id === id ? { ...s, text } : s)))
  const close = (id, keep) => {
    if (keep) { try { document.activeElement && document.activeElement.blur() } catch {} return }
    if (rec && rec.id === id && recorder) { recorder.drop(); setRec(null) }
    setSlots(l => l.filter(s => s.id !== id))
  }
  const mic = async (id) => {
    if (!recorder) { setNote('this browser cannot record'); return }
    const cur = recRef.current
    if (cur && cur.state === 'busy') return
    if (cur) {
      setRec({ id: cur.id, state: 'busy' })
      const blob = await recorder.stop()
      const r = blob ? await transcribe(fetcher, blob) : { ok: false, error: 'nothing was recorded' }
      setRec(null)
      if (!r.ok) { setNote(r.error); return }
      setNote('')
      setSlots(l => l.map(s => (s.id === cur.id ? { ...s, text: [String(s.text || '').trim(), r.text].filter(Boolean).join(' ') } : s)))
      setFocus(x => ({ id: cur.id, n: ((x && x.n) || 0) + 1 }))
      return
    }
    const got = await recorder.start()
    if (got.error) { setNote(got.error); return }
    setRec({ id, state: 'rec' })
  }
  const send = () => {
    const text = aboutBlock(slotsRef.current)
    if (!text) return
    onSend(sid, text)
    setSlots([])
    onClose()
  }

  const down = (e) => {
    if (e.button !== 0 || !recorder) return
    const pt = pointAt(e.target)
    if (!pt) return
    const h = { x: e.clientX, y: e.clientY, fired: false }
    h.timer = setTimeout(() => { if (hold.current !== h) return; h.fired = true; mic(open(pt)) }, HOLD_MS)
    hold.current = h
  }
  const move = (e) => { const h = hold.current; if (h && !h.fired && (Math.abs(e.clientX - h.x) > 4 || Math.abs(e.clientY - h.y) > 4)) { clearTimeout(h.timer); hold.current = null } }
  const up = (e) => {
    const h = hold.current; hold.current = null
    if (h) clearTimeout(h.timer)
    if (h && h.fired) { if (recRef.current && recRef.current.state === 'rec') mic(recRef.current.id); return }
    let sel = ''; try { sel = window.getSelection().toString().trim() } catch {}
    if (sel || e.button !== 0) return
    const pt = pointAt(e.target)
    if (pt) open(pt)
  }

  const filled = slots.filter(s => String(s.text || '').trim()).length
  return (
    <div className="wr-veil" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }} data-wallread={sid}>
      <style dangerouslySetInnerHTML={{ __html: CSS + LINE_SLOT_CSS }} />
      <section className="wr" role="dialog" aria-modal="true" aria-label={`${title || sid}: the last answer`}>
        <div className="wr-h">
          <span className="wr-nm">{title || sid}</span>
          {onWhole ? <button type="button" onClick={onWhole}>the whole thread</button> : null}
          <button type="button" onClick={onClose} aria-label="close" title="close (Esc); nothing is sent">×</button>
        </div>
        {now ? <p className="wr-now">now: {now}</p> : null}
        {msg === null ? <p className="wr-q">reading the thread</p> : msg.error ? <p className="wr-q">{msg.error}</p> : (
          <div className="wr-b" ref={body} onMouseDown={down} onMouseMove={move} onMouseUp={up}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{msg.text}</ReactMarkdown>
          </div>
        )}
        <p className="wr-f">{note || (filled ? `${filled} to send · Enter` : 'press a line to answer it')}</p>
      </section>
      {slots.filter(s => hosts.current[s.id]).map(s => createPortal(
        <LineSlot slot={s} listening={!!rec && rec.id === s.id && rec.state === 'rec'} canMic={!!recorder}
          others={slots.filter(x => x.id !== s.id && String(x.text || '').trim()).length}
          focus={focus && focus.id === s.id ? focus.n : 0}
          onText={setText} onSend={send} onClose={close} onMic={mic} />,
        hosts.current[s.id].host, s.id))}
    </div>
  )
}
