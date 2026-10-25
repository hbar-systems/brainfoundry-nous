// The activity lights (hbar 2026-10-25: "some of them were different colors and lighting on and off
// meaning it is working, operating"). One small dot before a thread's title, a pane tab or a board tile:
// pulsing slowly (2 s) in the colour of what works (a turn: the accent; a cc-job: amber; a standing
// agent: green), a short fade when it turns done, steady dim when idle. The state is GET /cc/activity
// (scripts/cc/cc-bridge.py `_activity`, also on /cc/health), read every 5 s only while the tab is
// visible. prefers-reduced-motion: colour only, no pulse. No dependencies.
import React, { useEffect, useState } from 'react'

export const LIGHT = { turn: 'var(--accent)', job: '#d4b86a', agent: '#7fc99c', done: '#7fc99c', idle: 'var(--border)' }
export const LIGHT_CSS = '@keyframes cclight { 0%,100% { opacity: 1 } 50% { opacity: 0.25 } } @keyframes cclightdone { from { opacity: 1 } to { opacity: 0.45 } } ' +
  '.cc-light-on { animation: cclight 2s ease-in-out infinite } .cc-light-done { animation: cclightdone 2.5s ease-out 1 forwards } ' +
  '@media (prefers-reduced-motion: reduce) { .cc-light-on, .cc-light-done { animation: none } .cc-light-done { opacity: 0.6 } }'

export function useActivity(every = 5000) {
  const [act, setAct] = useState(null)
  useEffect(() => {
    let timer = null
    const load = () => fetch('/cc/activity', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(d => { if (d && d.threads) setAct(d) }).catch(() => {})
    const start = () => { if (!timer) { load(); timer = setInterval(load, every) } }
    const stop = () => { if (timer) { clearInterval(timer); timer = null } }
    const onVis = () => (document.visibilityState === 'visible' ? start() : stop())
    onVis()
    document.addEventListener('visibilitychange', onVis)
    return () => { stop(); document.removeEventListener('visibilitychange', onVis) }
  }, [every])
  return act
}

// a: the thread's entry from /cc/activity ({state, via, since}) or null (idle); kind overrides the colour ('turn' | 'job' | 'agent')
export function Light({ a, kind, size = 7, style, title }) {
  const state = (a && a.state) || 'idle'
  const k = kind || (a && a.via) || 'turn'
  const color = state === 'working' ? LIGHT[k] || LIGHT.turn : state === 'done' ? LIGHT.done : LIGHT.idle
  const tip = title || (state === 'working' ? (k === 'agent' ? 'an agent works here' : k === 'job' ? 'a job runs from here' : 'answering') : state === 'done' ? 'a job just finished' : 'idle')
  return <span title={tip} className={state === 'working' ? 'cc-light-on' : state === 'done' ? 'cc-light-done' : undefined}
               style={{ display: 'inline-block', width: `${size}px`, height: `${size}px`, borderRadius: '50%', backgroundColor: color, flexShrink: 0, verticalAlign: 'middle', ...style }} />
}
