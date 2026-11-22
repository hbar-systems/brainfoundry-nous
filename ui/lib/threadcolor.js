// One colour scheme for threads, job tiles and /map (THREADS-1, hbar 2026-11-18: "human-friendly-visual (coloring,
// clear lighting up whats active in a systematic creative color-code scheme) + different color of production but
// also clear to understand").
//
// Two channels, never mixed:
//   STATE (the light): what the thread is doing. Answering now breathes softly in the accent; a job of its own
//     running is a steady lit amber edge; waiting on you is the one warm clay accent; done is calm sage; idle is
//     the border; archived is faded. A round dot and the row's left edge carry it.
//   LANE (the mark): which production it belongs to, a small square, quieter. Film, music, brains, sites, science,
//     ops, set by the bridge (scripts/cc/cc_lanes.py: the owner's lanes file, the registry, the title's words).
// The words for both are in LEGEND; a page shows them one press away (Legend below), never as a wall.
import React from 'react'

export const STATE = {
  answering: { color: 'var(--accent)', word: 'answering now', how: 'breathes' },
  job: { color: '#d4b86a', word: 'a job of its own runs', how: 'lit edge' },
  waiting: { color: '#e5875c', word: 'waits for you', how: 'warm accent' },
  failed: { color: '#c0605a', word: 'failed', how: 'red edge' },
  done: { color: '#8fb39a', word: 'done', how: 'calm' },
  idle: { color: 'var(--border)', word: 'quiet', how: 'unlit' },
  archived: { color: 'var(--border)', word: 'archived', how: 'faded' },
}
export const STATE_ORDER = ['answering', 'job', 'waiting', 'done', 'archived']

export const LANE = {
  film: { color: '#c98bb9', word: 'film and video' },
  music: { color: '#7ea7d8', word: 'music' },
  brains: { color: '#5fb3a5', word: 'brains and members' },
  sites: { color: '#a99be0', word: 'sites and pages' },
  science: { color: '#9cc46e', word: 'science' },
  ops: { color: '#a8a097', word: 'ops' },
}
export const LANE_ORDER = ['film', 'music', 'brains', 'sites', 'science', 'ops']

const FINISHED = { done: 1, 'let-go': 1, fold: 1, superseded: 1 }

// a thread row from /cc/threads, plus its /cc/activity entry (or null)
export function threadState(th, act) {
  if (!th) return 'idle'
  if (th.waiting) return 'waiting'
  if (th.running || (act && act.state === 'working' && (act.via || 'turn') === 'turn')) return 'answering'
  if ((Array.isArray(th.jobs_running) && th.jobs_running.length) || (act && act.state === 'working')) return 'job'
  if (th.archived) return 'archived'
  if (FINISHED[th.verdict] || (act && act.state === 'done')) return 'done'
  return 'idle'
}

// a tile from /cc/board (state answering | waiting | failed | done; kind run | job | thread)
export function tileState(t) {
  if (!t) return 'idle'
  if (t.state === 'answering') return t.kind === 'job' ? 'job' : 'answering'
  return STATE[t.state] ? t.state : 'idle'
}

export const THREADCOLOR_CSS =
  '@keyframes ccbreathe { 0%,100% { box-shadow: inset 3px 0 0 var(--accent), 0 0 0 0 transparent } ' +
  '50% { box-shadow: inset 3px 0 0 var(--accent), 0 0 16px -4px color-mix(in srgb, var(--accent) 70%, transparent) } } ' +
  '@keyframes ccbreathedot { 0%,100% { box-shadow: 0 0 0 0 transparent; opacity: 1 } 50% { box-shadow: 0 0 8px 2px color-mix(in srgb, var(--accent) 60%, transparent); opacity: 0.7 } } ' +
  '.cc-st-answering { animation: ccbreathe 2.6s ease-in-out infinite } .cc-dot-answering { animation: ccbreathedot 2.6s ease-in-out infinite } ' +
  '@media (prefers-reduced-motion: reduce) { .cc-st-answering, .cc-dot-answering { animation: none } .cc-st-answering { box-shadow: inset 3px 0 0 var(--accent) } }'

// the look of a row or tile in a state: a left edge, a tint for waiting, faded for archived
export function stateLook(state) {
  const s = STATE[state] || STATE.idle
  if (state === 'answering') return { className: 'cc-st-answering', style: {} }
  if (state === 'job' || state === 'failed') return { style: { boxShadow: `inset 3px 0 0 ${s.color}` } }
  if (state === 'waiting') return { style: { boxShadow: `inset 3px 0 0 ${s.color}`, backgroundColor: 'color-mix(in srgb, #e5875c 9%, transparent)' } }
  if (state === 'archived') return { style: { opacity: 0.55 } }
  if (state === 'done') return { style: { opacity: 0.8 } }
  return { style: {} }
}

export function StateDot({ state, size = 8, style }) {
  const s = STATE[state] || STATE.idle
  const ring = state === 'job'
  return <span title={s.word} className={state === 'answering' ? 'cc-dot-answering' : undefined}
               style={{ display: 'inline-block', width: size, height: size, borderRadius: '50%', boxSizing: 'border-box', flexShrink: 0, verticalAlign: 'middle',
                        backgroundColor: ring ? 'transparent' : s.color, border: ring ? `2px solid ${s.color}` : 'none', ...style }} />
}

export function LaneMark({ lane, size = 7, style }) {
  const l = LANE[lane]
  if (!l) return null
  return <span title={l.word} aria-label={l.word}
               style={{ display: 'inline-block', width: size, height: size, borderRadius: 2, backgroundColor: l.color, flexShrink: 0, verticalAlign: 'middle', ...style }} />
}

// The legend, one press away: the press is a small word; open, two short rows in words.
export function Legend({ open, onToggle, mono, faint, ink }) {
  const m = mono || {}
  const row = { display: 'flex', flexWrap: 'wrap', gap: '6px 14px', alignItems: 'center', margin: '4px 0' }
  const item = { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: ink || 'var(--text)', whiteSpace: 'nowrap' }
  return (
    <span style={{ display: 'contents' }}>
      <a data-legend-toggle="1" role="button" tabIndex={0} onClick={onToggle} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle() } }}
         title="what the colours mean" style={{ ...m, color: faint || 'var(--muted)', fontSize: 10, cursor: 'pointer', textDecoration: 'underline', whiteSpace: 'nowrap' }}>
        {open ? 'hide colours' : 'colours'}
      </a>
      {open && (
        <div style={{ flexBasis: '100%', padding: '8px 10px', borderRadius: 8, backgroundColor: 'var(--surface2)', border: '1px solid var(--border)' }}>
          <div style={{ ...m, fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: faint || 'var(--muted)' }}>light: what it is doing</div>
          <div style={row}>
            {STATE_ORDER.map(k => <span key={k} style={{ ...item, opacity: k === 'archived' ? 0.55 : 1 }}><StateDot state={k === 'archived' ? 'idle' : k} />{STATE[k].word}</span>)}
          </div>
          <div style={{ ...m, fontSize: 9, letterSpacing: '0.12em', textTransform: 'uppercase', color: faint || 'var(--muted)', marginTop: 6 }}>mark: which production</div>
          <div style={row}>
            {LANE_ORDER.map(k => <span key={k} style={item}><LaneMark lane={k} />{LANE[k].word}</span>)}
          </div>
        </div>
      )}
    </span>
  )
}
