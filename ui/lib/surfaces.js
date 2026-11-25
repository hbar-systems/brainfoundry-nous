// A system's card (SURFACES-1, 2026-11-24). hbar: "every time I say I not liking this production service, you don't
// bring the proper one for me to evolve into". GET /cc/surfaces gives the owner's register (scripts/cc/cc_surfaces.py,
// <world>/registry/surfaces/*.json); nothing here knows a system's name. Pure functions, no DOM: ui/pages/cc.js and
// ui/pages/systems/index.js use them through ui/components/SurfaceCard.js, tests/test_cc_surfaces.py runs them under node.
//
// sayMatch(text, surfaces): the surface whose say-word is the whole message, else null. Case and spaces do not count,
//   one trailing "." or "!" does not count; anything else ("music?", "music please") is a message for the brain.
// keyIndex(key, n): "1".."5" -> 0..4 when there is such a button, else -1.
// daysLeft(iso, now): whole days from today (local) to the date; negative once passed; null when not a date.
// systemsFor(tiles, surfaces): {bySystem: {tileId: [surface]}, alone: [surface]}: the cards a /systems tile carries, and
//   the ones with no tile, which /systems shows as tiles of their own.

function norm(t) {
  return String(t == null ? '' : t).toLowerCase().replace(/\s+/g, ' ').trim().replace(/[.!]$/, '').trim()
}

function sayMatch(text, surfaces) {
  const w = norm(text)
  if (!w || w.length > 40 || !Array.isArray(surfaces)) return null
  for (const s of surfaces) {
    if (s && Array.isArray(s.say) && s.say.includes(w)) return s
  }
  return null
}

function keyIndex(key, n) {
  if (typeof key !== 'string' || !/^[1-5]$/.test(key)) return -1
  const i = Number(key) - 1
  return i < (n || 0) ? i : -1
}

function daysLeft(iso, now) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''))
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  const n = now ? new Date(now) : new Date()
  const t = new Date(n.getFullYear(), n.getMonth(), n.getDate())
  return Math.round((d - t) / 86400000)
}

function systemsFor(tiles, surfaces) {
  const ids = new Set((Array.isArray(tiles) ? tiles : []).map(t => t && t.id))
  const bySystem = {}, alone = []
  ;(Array.isArray(surfaces) ? surfaces : []).forEach(s => {
    if (!s || !s.system) return
    if (ids.has(s.system)) (bySystem[s.system] = bySystem[s.system] || []).push(s)
    else alone.push(s)
  })
  return { bySystem, alone }
}

module.exports = { sayMatch, keyIndex, daysLeft, systemsFor }
