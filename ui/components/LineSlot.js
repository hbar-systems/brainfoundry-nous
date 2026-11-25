import React, { useEffect, useRef } from 'react'

// The reply slot under a pressed line (LINE-TALK-1, 2026-11-25; ui/lib/linetalk.js). "About this: <the line>", a box
// with the cursor in it, a mic. Enter sends (every filled slot of the answer goes as one message), Shift+Enter is a
// new line, Esc stops the dictation, else closes an empty slot (a filled one stays and goes with the next message).
// Dictation (the mic here, or holding the line for half a second) writes into this box, never sends by itself. The
// Mac's own dictation (fn twice) also types here, since the cursor is in it. Colours come from the page: --lt-ink,
// --lt-dim, --lt-line, --lt-accent, --lt-bg, so the chat and the dark wall each keep their own skin.

const CSS = `
.lt-slot{margin:6px 0 8px;padding:7px 9px 7px 10px;border-radius:10px;background:var(--lt-bg,rgba(0,0,0,.04));border-left:2px solid var(--lt-accent,#c9a96e);
  font-size:14px;line-height:1.45;color:var(--lt-ink,inherit);white-space:normal;list-style:none;cursor:auto;user-select:text}
.lt-about{font-size:12px;color:var(--lt-dim,#8a857c);margin:0 0 4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lt-about b{font-weight:500;color:var(--lt-accent,#c9a96e);margin-right:4px}
.lt-row{display:flex;align-items:flex-end;gap:6px}
.lt-in{flex:1;min-width:0;resize:none;border:0;outline:none;background:transparent;color:inherit;font:inherit;font-size:14px;line-height:1.45;padding:2px 0;min-height:22px;max-height:160px}
.lt-in::placeholder{color:var(--lt-dim,#8a857c);opacity:.8}
.lt-b{display:inline-flex;align-items:center;justify-content:center;height:24px;min-width:24px;padding:0 6px;border-radius:999px;border:0;background:none;color:var(--lt-dim,#8a857c);cursor:pointer;font:inherit;font-size:11px;letter-spacing:.08em;text-transform:lowercase}
.lt-b:hover{color:var(--lt-accent,#c9a96e)}
.lt-b svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.lt-b.rec{color:#e07a5f;animation:lt-p 1.2s ease-in-out infinite}
.lt-b.go{color:var(--lt-accent,#c9a96e)}
.lt-b[disabled]{opacity:.45;cursor:default}
.lt-n{font-size:11px;color:var(--lt-dim,#8a857c);margin-top:3px}
@keyframes lt-p{50%{opacity:.45}}
@media(prefers-reduced-motion:reduce){.lt-b.rec{animation:none}}
`

const Mic = () => <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="6" y="2" width="4" height="8" rx="2" /><path d="M3.5 8a4.5 4.5 0 0 0 9 0M8 12.5V14.5" /></svg>
const Stop = () => <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="4.5" y="4.5" width="7" height="7" rx="1.5" /></svg>

export const LINE_SLOT_CSS = CSS

export default function LineSlot({ slot, listening, hearing, canMic, onText, onSend, onClose, onMic, others, focus }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!focus) return
    const el = ref.current
    if (!el) return
    try { el.focus({ preventScroll: true }); const n = el.value.length; el.setSelectionRange(n, n) } catch {}
  }, [focus])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'; el.style.height = Math.min(160, el.scrollHeight) + 'px'
  }, [slot.text])
  const filled = !!String(slot.text || '').trim()
  const key = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (filled || others) onSend(slot.id); return }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (listening) onMic(slot.id); else onClose(slot.id, filled) }
  }
  return (
    <div className="lt-slot" data-lineslot="1" data-pickui="1" data-nopick="1" data-slot-id={slot.id}
      onMouseDown={e => e.stopPropagation()} onMouseUp={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
      <p className="lt-about"><b>About this:</b>{slot.quote}</p>
      <div className="lt-row">
        <textarea ref={ref} className="lt-in" rows={1} value={slot.text || ''} onChange={e => onText(slot.id, e.target.value)} onKeyDown={key}
          placeholder={listening ? (hearing ? 'hearing you' : 'listening') : 'say it; Enter sends'} aria-label={`about this: ${slot.quote}`} maxLength={8000} />
        {canMic ? (
          <button type="button" className={'lt-b' + (listening ? ' rec' : '')} onClick={() => onMic(slot.id)} data-lt-mic="1"
            aria-label={listening ? 'stop dictating' : 'dictate into this'} title={listening ? 'stop; the words stay to send' : 'speak into this (or hold the line)'}>
            {listening ? <Stop /> : <Mic />}
          </button>
        ) : null}
        <button type="button" className={'lt-b' + (filled ? ' go' : '')} onClick={() => onSend(slot.id)} disabled={!filled && !others} data-lt-send="1"
          title={others ? 'send every filled line as one message (Enter)' : 'send (Enter)'}>send</button>
        <button type="button" className="lt-b" onClick={() => onClose(slot.id, false)} aria-label="close" title="close">×</button>
      </div>
      {others ? <p className="lt-n">goes with {others} more as one message</p> : null}
    </div>
  )
}
