import React, { useEffect, useRef, useState } from 'react'

// Spiders (AGENTS-VIS-1, hbar 2026-11-15: "a spider walks the page while an agent works, small spiders
// for subagents"). A fixed canvas over the page that never takes a click. `count` large spiders (a turn,
// a running job) and `small` small ones (subagents, jobs a turn started) walk with planted feet: each leg
// steps only when its foot falls too far behind, alternating sets, so the gait reads as walking, not
// sliding. When a count drops the extra spider walks off the nearest edge; at zero the loop stops.
// Paused while the tab is hidden; prefers-reduced-motion draws nothing. Off with spidersSet(false)
// (localStorage "bf-spiders" = "0"); every mounted overlay hears the change at once.

const KEY = 'bf-spiders'
const EVT = 'bf-spiders-change'
export function spidersOn() { try { return window.localStorage.getItem(KEY) !== '0' } catch { return true } }
export function spidersSet(on) {
  try { window.localStorage.setItem(KEY, on ? '1' : '0') } catch {}
  try { window.dispatchEvent(new CustomEvent(EVT)) } catch {}
}
export function useSpidersOn() {
  const [on, setOn] = useState(true)
  useEffect(() => {
    const read = () => setOn(spidersOn())
    read()
    window.addEventListener(EVT, read)
    window.addEventListener('storage', read)
    return () => { window.removeEventListener(EVT, read); window.removeEventListener('storage', read) }
  }, [])
  return on
}

// leg rest positions in the body frame (forward = +x), per side: front to back
const LEGS = [[0.9, 1.25], [0.35, 1.45], [-0.2, 1.4], [-0.7, 1.15]]

function makeSpider(w, h, small, id) {
  const s = small ? 4.2 : 7          // body unit in px
  // enter from a random edge, already facing in
  const edge = Math.floor(Math.random() * 4)
  const x = edge === 0 ? -20 : edge === 1 ? w + 20 : Math.random() * w
  const y = edge === 2 ? -20 : edge === 3 ? h + 20 : Math.random() * h
  const sp = { id, small, s, x, y, a: Math.atan2(h / 2 - y, w / 2 - x), v: 0, max: small ? 46 : 32, legs: [], goal: null, rest: 0, leaving: false, gone: false, t: Math.random() * 10 }
  for (let side = -1; side <= 1; side += 2) {
    LEGS.forEach(([fx, fy], k) => {
      const set = (k + (side > 0 ? 1 : 0)) % 2
      const p = local(sp, fx * s * 1.6, side * fy * s * 1.6)
      sp.legs.push({ fx, fy: side * fy, set, foot: p, from: p, to: p, t: 1 })
    })
  }
  return sp
}

function local(sp, lx, ly) {
  const c = Math.cos(sp.a), n = Math.sin(sp.a)
  return { x: sp.x + lx * c - ly * n, y: sp.y + lx * n + ly * c }
}

function pickGoal(sp, w, h) {
  const m = 40
  // mostly a short walk ahead, now and then across the page
  const far = Math.random() < 0.25
  const d = far ? 200 + Math.random() * 400 : 60 + Math.random() * 160
  const a = sp.a + (Math.random() - 0.5) * (far ? 2.4 : 1.6)
  sp.goal = { x: Math.min(w - m, Math.max(m, sp.x + Math.cos(a) * d)), y: Math.min(h - m, Math.max(m, sp.y + Math.sin(a) * d)) }
}

function step(sp, dt, w, h) {
  sp.t += dt
  if (!sp.goal) pickGoal(sp, w, h)
  if (sp.leaving && !sp.exit) {
    const opts = [[-60, sp.y, sp.x], [w + 60, sp.y, w - sp.x], [sp.x, -60, sp.y], [sp.x, h + 60, h - sp.y]]
    opts.sort((p, q) => p[2] - q[2])
    sp.exit = true; sp.goal = { x: opts[0][0], y: opts[0][1] }; sp.rest = 0
  }
  const dx = sp.goal.x - sp.x, dy = sp.goal.y - sp.y, dist = Math.hypot(dx, dy)
  if (sp.rest > 0) { sp.rest -= dt; sp.v = Math.max(0, sp.v - sp.max * 3 * dt) }
  else if (dist < 6) {
    if (sp.leaving) { sp.gone = true; return }
    sp.goal = null; sp.rest = Math.random() < 0.45 ? 0.4 + Math.random() * 1.6 : 0
  } else {
    // turn toward the goal with a little wobble, ease the speed in and out
    let da = Math.atan2(dy, dx) - sp.a
    while (da > Math.PI) da -= Math.PI * 2
    while (da < -Math.PI) da += Math.PI * 2
    sp.a += Math.max(-1, Math.min(1, da)) * dt * 3.2 + Math.sin(sp.t * 2.3) * 0.004
    const want = Math.abs(da) > 1.2 ? sp.max * 0.25 : Math.min(sp.max, dist * 1.4) * (sp.leaving ? 1.4 : 1)
    sp.v += (want - sp.v) * Math.min(1, dt * 4)
  }
  sp.x += Math.cos(sp.a) * sp.v * dt
  sp.y += Math.sin(sp.a) * sp.v * dt
  // legs: a foot steps when it falls a stride behind; one set at a time
  const stride = sp.s * 1.5
  const busy = [0, 0]
  for (const l of sp.legs) if (l.t < 1) busy[l.set] += 1
  for (const l of sp.legs) {
    if (l.t < 1) {
      l.t = Math.min(1, l.t + dt / (sp.small ? 0.09 : 0.12))
      const e = 1 - Math.pow(1 - l.t, 3)
      l.foot = { x: l.from.x + (l.to.x - l.from.x) * e, y: l.from.y + (l.to.y - l.from.y) * e, lift: Math.sin(l.t * Math.PI) }
      continue
    }
    const home = local(sp, l.fx * sp.s * 1.6, l.fy * sp.s * 1.6)
    if (Math.hypot(home.x - l.foot.x, home.y - l.foot.y) > stride && busy[1 - l.set] === 0) {
      const lead = local(sp, l.fx * sp.s * 1.6 + Math.min(stride * 0.8, sp.v * 0.12), l.fy * sp.s * 1.6)
      l.from = l.foot; l.to = lead; l.t = 0; busy[l.set] += 1
    }
  }
}

function draw(ctx, sp, ink, rim) {
  const s = sp.s
  ctx.lineCap = 'round'; ctx.lineJoin = 'round'
  ctx.strokeStyle = ink
  for (const l of sp.legs) {
    const hip = local(sp, l.fx * s * 0.45, Math.sign(l.fy) * s * 0.35)
    const f = l.foot
    // the knee: above the line from hip to foot, pushed outward and up while the foot is lifted
    const mx = (hip.x + f.x) / 2, my = (hip.y + f.y) / 2
    const out = local(sp, l.fx * s * 0.2, Math.sign(l.fy) * s * 1.1)
    const kx = mx + (out.x - sp.x) * 0.55, ky = my + (out.y - sp.y) * 0.55 - (f.lift || 0) * s * 0.5
    ctx.lineWidth = sp.small ? 0.9 : 1.25
    ctx.beginPath(); ctx.moveTo(hip.x, hip.y); ctx.quadraticCurveTo(kx, ky - s * 0.4, kx, ky); ctx.lineTo(f.x, f.y); ctx.stroke()
  }
  // abdomen behind, cephalothorax ahead, a faint rim of the accent
  const ab = local(sp, -s * 0.95, 0), ce = local(sp, s * 0.35, 0)
  ctx.fillStyle = ink
  ctx.beginPath(); ctx.ellipse(ab.x, ab.y, s * 0.95, s * 0.72, sp.a, 0, Math.PI * 2); ctx.fill()
  ctx.beginPath(); ctx.ellipse(ce.x, ce.y, s * 0.55, s * 0.48, sp.a, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = rim; ctx.lineWidth = 1
  ctx.beginPath(); ctx.ellipse(ab.x, ab.y, s * 0.95, s * 0.72, sp.a, 0, Math.PI * 2); ctx.stroke()
}

export default function Spiders({ count = 0, small = 0, z = 60 }) {
  const on = useSpidersOn()
  const ref = useRef(null)
  const state = useRef({ list: [], raf: 0, last: 0, want: [0, 0], id: 0, colors: null })
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    const mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null
    const read = () => setReduced(!!(mq && mq.matches))
    read()
    if (mq && mq.addEventListener) mq.addEventListener('change', read)
    return () => { if (mq && mq.removeEventListener) mq.removeEventListener('change', read) }
  }, [])

  const big = on && !reduced ? Math.max(0, Math.min(8, Number(count) || 0)) : 0
  const little = on && !reduced ? Math.max(0, Math.min(16, Number(small) || 0)) : 0

  useEffect(() => {
    const S = state.current
    S.want = [big, little]
    const cv = ref.current
    if (!cv) return undefined
    const ctx = cv.getContext('2d')
    if (!S.colors) {
      const css = getComputedStyle(document.documentElement)
      S.colors = { ink: (css.getPropertyValue('--text') || '#e8e0d5').trim(), rim: (css.getPropertyValue('--accent') || '#c9a96e').trim() }
    }
    const fit = () => {
      const d = Math.min(2, window.devicePixelRatio || 1)
      cv.width = Math.round(window.innerWidth * d); cv.height = Math.round(window.innerHeight * d)
      cv.style.width = window.innerWidth + 'px'; cv.style.height = window.innerHeight + 'px'
      ctx.setTransform(d, 0, 0, d, 0, 0)
    }
    fit()
    // match the population to the counts: new ones walk in, extras walk out
    const census = () => {
      const w = window.innerWidth, h = window.innerHeight
      for (const [i, isSmall] of [[0, false], [1, true]]) {
        const live = S.list.filter(sp => sp.small === isSmall && !sp.leaving)
        for (let k = live.length; k < S.want[i]; k++) S.list.push(makeSpider(w, h, isSmall, ++S.id))
        for (let k = S.want[i]; k < live.length; k++) live[k].leaving = true
      }
    }
    census()
    const frame = (ts) => {
      const dt = Math.min(0.05, S.last ? (ts - S.last) / 1000 : 0.016)
      S.last = ts
      const w = window.innerWidth, h = window.innerHeight
      ctx.clearRect(0, 0, w, h)
      for (const sp of S.list) { step(sp, dt, w, h); if (!sp.gone) draw(ctx, sp, S.colors.ink, S.colors.rim) }
      S.list = S.list.filter(sp => !sp.gone)
      if (S.list.length && document.visibilityState === 'visible') S.raf = requestAnimationFrame(frame)
      else { S.raf = 0; S.last = 0; if (!S.list.length) ctx.clearRect(0, 0, w, h) }
    }
    const go = () => { if (!S.raf && S.list.length && document.visibilityState === 'visible') { S.last = 0; S.raf = requestAnimationFrame(frame) } }
    const onVis = () => { if (document.visibilityState === 'visible') go(); else if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0 } }
    go()
    window.addEventListener('resize', fit)
    document.addEventListener('visibilitychange', onVis)
    return () => {
      window.removeEventListener('resize', fit)
      document.removeEventListener('visibilitychange', onVis)
      if (S.raf) { cancelAnimationFrame(S.raf); S.raf = 0 }
    }
  }, [big, little])

  // reduced motion or switched off: nothing on the page at all
  if (reduced || !on) return null
  return <canvas ref={ref} aria-hidden="true" data-spiders={big + little}
                 style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: z }} />
}
