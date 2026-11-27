// Tide (AUTO-UPDATE-1, 2026-11-27, docs/TIDE.md): the /update page's line "updates itself at quiet
// moments: on/off", the next check's answer in words, and the last three automatic updates.
// Pure functions, no DOM: ui/pages/update.js uses them, tests/test_cc_tide.py runs them under node.

function hm(t) {
  if (!t) return ''
  const d = new Date(Number(t) * 1000)
  if (isNaN(d.getTime())) return ''
  return d.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
}

function ago(t, now) {
  const s = Math.max(0, Math.round(Number(now) - Number(t)))
  if (s < 90) return 'just now'
  if (s < 5400) return `${Math.round(s / 60)} min ago`
  if (s < 172800) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} days ago`
}

// One automatic update in words: "2026-11-27 15:05 UTC: 4 commits, healthy at 1a2b3c4".
function recentLine(r) {
  if (!r || typeof r !== 'object') return ''
  const n = Number(r.n) || 0
  const when = hm(r.started || r.at)
  const what = n ? `${n} commit${n === 1 ? '' : 's'}` : 'update'
  const sha = String(r.head || r.to || '').slice(0, 7)
  const res = r.result === 'healthy' ? `healthy at ${sha}`
    : r.result === 'busy' ? 'skipped (another update ran)'
    : r.result === 'unknown' ? 'never reported back'
    : `failed (rc=${r.rc == null ? '?' : r.rc}), no retry until a new commit`
  return `${when}: ${what}, ${res}`
}

// The whole line from GET /cc/autoupdate. null = nothing to show (no bridge, or a member's brain).
function tideView(v, now) {
  if (!v || typeof v !== 'object' || v.member) return null
  const t = now == null ? Date.now() / 1000 : Number(now)
  const on = v.on === true
  const asked = v.asked && v.asked.at ? Number(v.asked.at) : 0
  // the root timer asks every five minutes; silent for 15 = not installed, or stopped
  const timer = !asked ? 'the box timer has not asked yet (install steps: docs/TIDE.md)'
    : (t - asked > 900 ? `the box timer last asked ${ago(asked, t)}; it may be stopped`
      : `the box timer asked ${ago(asked, t)}`)
  return {
    on,
    label: `updates itself at quiet moments: ${on ? 'on' : 'off'}`,
    press: on ? 'Turn off' : 'Turn on',
    next: v.begun ? `updating now: ${Number(v.begun.n) || 0} commits` : String(v.next || ''),
    timer,
    recent: (Array.isArray(v.recent) ? v.recent : []).slice(0, 3).map(recentLine).filter(Boolean),
  }
}

module.exports = { tideView, recentLine, hm, ago }
