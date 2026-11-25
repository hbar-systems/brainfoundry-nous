import React from 'react'

// The corner switch between the wall and the columns (LINE-TALK-1, 2026-11-25, hbar: "maybe we should try that
// parallel-systems verticle production surface?"). Two quiet words beside each page's own controls (the wall's look
// switch; the top of /systems), never floating over them: the same systems and threads in the other view. The page
// does the keeping and the telling (ui/lib/wall.js switchView).

export const VIEW_CSS = `
.vw-sw{display:inline-flex;gap:2px;vertical-align:middle;
  padding:2px;border-radius:999px;background:var(--vw-bg,rgba(20,20,22,.72));font:400 11px/1 var(--font-body,system-ui,sans-serif);letter-spacing:.1em;text-transform:lowercase}
.vw-sw button{font:inherit;letter-spacing:inherit;border:0;background:none;color:var(--vw-dim,#8f8c85);padding:5px 10px;border-radius:999px;cursor:pointer}
.vw-sw button:hover{color:var(--vw-ink,#ecebe6)}
.vw-sw button[aria-pressed=true]{background:var(--vw-on,rgba(255,255,255,.08));color:var(--vw-ink,#ecebe6);cursor:default}
`

export default function ViewSwitch({ view, onPick, style }) {
  return (
    <div className="vw-sw" role="group" aria-label="wall or columns" style={style}>
      {[['wall', 'the wall: every system at a glance'], ['columns', 'the columns: the threads side by side']].map(([k, tip]) => (
        <button key={k} type="button" aria-pressed={view === k} data-view={k} title={tip} onClick={() => { if (view !== k) onPick(k) }}>{k}</button>
      ))}
    </div>
  )
}
