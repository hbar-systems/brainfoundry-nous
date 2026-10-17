import React from 'react'

// A face for each agent (2026-10-17): drawn from its tag, the same every time, no image service.
// Unit colour ring, a field with its institution letters, and rank marks: a star for the General,
// two bars for a captain. The pattern behind is a 5x5 mirrored grid seeded by the serial.
function hashOf(str) { let h = 2166136261; for (const ch of String(str)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) } return h >>> 0 }
function Face({ a, size = 46 }) {
  const h = hashOf(a.post || 'none'), g = hashOf(`${a.serial}-${a.callsign}`)
  const hue = h % 360, hue2 = (hue + 40 + (g % 80)) % 360
  const cells = []
  for (let y = 0; y < 5; y++) for (let x = 0; x < 3; x++) if ((g >> (y * 3 + x)) & 1) { cells.push([x, y]); if (x < 2) cells.push([4 - x, y]) }
  const general = ['CMD', 'COMMAND'].includes(a.code || '') || /general/i.test(a.name || '')
  const letters = (a.code || a.callsign || a.name || '?').slice(0, 3).toUpperCase()
  return (
    <svg width={size} height={size} viewBox="0 0 50 50" style={{ flex: 'none', alignSelf: 'center' }} aria-label={`face of ${a.tag}`}>
      <circle cx="25" cy="25" r="23.5" fill={`hsl(${hue2} 35% 16%)`} stroke={`hsl(${hue} 55% 55%)`} strokeWidth="3" />
      <g opacity="0.55">{cells.map(([x, y], i) => <rect key={i} x={12.5 + x * 5} y={9 + y * 5} width="5" height="5" fill={`hsl(${hue2} 50% 45%)`} />)}</g>
      <text x="25" y="41.5" textAnchor="middle" fontSize="8.5" fontFamily="monospace" fill={`hsl(${hue} 70% 80%)`}>{letters}</text>
      {general
        ? <polygon points="25,3 27,8 32,8 28,11 30,16 25,13 20,16 22,11 18,8 23,8" fill="#d4b86a" />
        : <g fill="#d4b86a"><rect x="19" y="4" width="12" height="2" /><rect x="19" y="7.5" width="12" height="2" /></g>}
    </svg>
  )
}

export { Face, hashOf }
