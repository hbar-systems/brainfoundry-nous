// The console's one audio owner (LISTEN-1, 2026-11-24). hbar: "cant we just get my tracks and all in youtube music
// ... so i can listen while doing tasks?"
//
// One controller per console tab, living in the top-level document (pages/_app.js mounts the strip there). A page
// inside a pane (an iframe of the same origin) never plays on its own: it reaches the top's controller through
// window.top, so opening, closing or changing a pane never stops the music, and two panes never play at once.
// Moving between console pages is client-side routing inside the same document, so the controller lives on; the
// strip also routes plain same-origin links to console pages through the router while music plays (installLinks).
//
// Stations come from the bridge (GET /cc/listen, scripts/cc/cc_listen.py). A YouTube item plays through the
// official IFrame embed player (youtube-nocookie host), shown at 200x200, the smallest the embed's terms allow;
// nothing is downloaded or rehosted. An item whose embedding is off (errors 101/150, or 100 gone, 2 bad id, 5
// html5) is skipped and counted. An own track (k: "file") plays as a plain <audio> from /cc/listen/file?n=<id>.
// Advancing is event-driven (ended / onStateChange), never a timer, so a background tab advances too.
// Every start, finish, skip, blocked and pause is posted to /cc/listen/event (the play log stays on the box).

const LS = 'cc.listen.v1'
const YT_HOST = 'https://www.youtube-nocookie.com'
const MAX_BLOCKED_RUN = 25

function emptyState () {
  return { station: null, name: '', kind: '', items: [], i: 0, playing: false, loading: false, blocked: 0,
    blockedRun: 0, error: '', now: null, started: 0 }
}

function makeController (win) {
  const doc = win.document
  let st = emptyState()
  const subs = new Set()
  let yt = null; let ytReady = null; let host = null; let audio = null
  let current = null          // the item now loaded: {k, id|n, title, artist}
  let startedLogged = false   // a "start" row is written once per item, on its first real play

  const emit = () => { const snap = { ...st }; subs.forEach(f => { try { f(snap) } catch (e) {} }) }
  const set = (patch) => { st = { ...st, ...patch }; emit(); save() }
  const save = () => {
    try { win.localStorage.setItem(LS, JSON.stringify({ station: st.station, name: st.name, i: st.i })) } catch (e) {}
  }

  const tz = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || '' } catch (e) { return '' } })()
  function log (event, extra) {
    const it = current
    if (!it || !st.station) return
    let tab = ''
    try { tab = doc.visibilityState === 'hidden' ? 'hidden' : 'visible' } catch (e) {}
    const body = { event, station: st.station, kind: it.k, item: it.id || it.n, title: it.title, artist: it.artist, tz, tab, ...extra }
    try {
      win.fetch('/cc/listen/event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive: true }).catch(() => {})
    } catch (e) {}
  }

  function position () {
    try {
      if (current && current.k === 'yt' && yt && yt.getCurrentTime) return { position_s: yt.getCurrentTime() || 0, duration_s: yt.getDuration() || current.dur || 0 }
      if (current && current.k === 'file' && audio) return { position_s: audio.currentTime || 0, duration_s: audio.duration || current.dur || 0 }
    } catch (e) {}
    return {}
  }

  // ---- the two players -----------------------------------------------------------------------------------------
  function hostEl () {
    if (host && doc.body.contains(host)) return host
    host = doc.createElement('div')
    host.id = 'bf-listen-yt'
    host.setAttribute('aria-hidden', 'false')
    host.style.cssText = 'position:fixed;width:200px;height:200px;left:-10000px;top:0;z-index:9980;border-radius:14px;overflow:hidden;background:#000'
    const inner = doc.createElement('div')
    inner.id = 'bf-listen-yt-frame'
    host.appendChild(inner)
    doc.body.appendChild(host)
    return host
  }

  function loadYT () {
    if (ytReady) return ytReady
    ytReady = new Promise((resolve, reject) => {
      const make = () => {
        hostEl()
        yt = new win.YT.Player('bf-listen-yt-frame', {
          host: YT_HOST, width: 200, height: 200,
          playerVars: { playsinline: 1, rel: 0, modestbranding: 1, origin: win.location.origin },
          events: {
            onReady: () => {
              try { const f = yt.getIframe(); f.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin'); f.setAttribute('title', 'YouTube player') } catch (e) {}
              resolve(yt)
            },
            onStateChange: (e) => onYTState(e.data),
            onError: (e) => blocked('yt-' + e.data),
          },
        })
      }
      if (win.YT && win.YT.Player) { make(); return }
      const prev = win.onYouTubeIframeAPIReady
      win.onYouTubeIframeAPIReady = () => { if (typeof prev === 'function') { try { prev() } catch (e) {} } make() }
      const s = doc.createElement('script')
      s.src = 'https://www.youtube.com/iframe_api'
      s.async = true
      s.onerror = () => { ytReady = null; reject(new Error('the YouTube player did not load')) }
      doc.head.appendChild(s)
    })
    return ytReady
  }

  function onYTState (s) {
    if (!current || current.k !== 'yt') return
    if (s === 1) { // playing
      if (!startedLogged) { startedLogged = true; log('start', position()) }
      set({ playing: true, loading: false, blockedRun: 0, error: '' })
    } else if (s === 2) { // paused (by us or inside the player)
      if (st.playing) set({ playing: false })
    } else if (s === 0) { // ended
      log('finish', position())
      advance(1)
    }
  }

  function fileEl () {
    if (audio) return audio
    audio = doc.createElement('audio')
    audio.preload = 'auto'
    audio.addEventListener('playing', () => {
      if (!current || current.k !== 'file') return
      if (!startedLogged) { startedLogged = true; log('start', position()) }
      set({ playing: true, loading: false, blockedRun: 0, error: '' })
    })
    audio.addEventListener('pause', () => { if (current && current.k === 'file' && st.playing && !audio.ended) set({ playing: false }) })
    audio.addEventListener('ended', () => { if (current && current.k === 'file') { log('finish', position()); advance(1) } })
    audio.addEventListener('error', () => { if (current && current.k === 'file' && audio.getAttribute('src')) blocked('file') })
    return audio
  }

  function blocked (reason) {
    if (!current) return
    log('blocked', { reason })
    const run = st.blockedRun + 1
    if (run >= MAX_BLOCKED_RUN) {
      set({ blocked: st.blocked + 1, blockedRun: run, playing: false, loading: false, error: `${run} in a row would not play here; stopped` })
      return
    }
    set({ blocked: st.blocked + 1, blockedRun: run })
    advance(1)
  }

  function quiet () {
    try { if (yt && yt.pauseVideo) yt.pauseVideo() } catch (e) {}
    try { if (audio) audio.pause() } catch (e) {}
  }

  async function playAt (i, autoplay = true) {
    const n = st.items.length
    if (!n) return
    i = ((i % n) + n) % n
    const it = st.items[i]
    quiet()
    current = it
    startedLogged = false
    set({ i, now: it, loading: autoplay, error: st.blockedRun >= MAX_BLOCKED_RUN ? st.error : '' })
    mediaSession(it)
    if (it.k === 'yt') {
      hostEl().dataset.on = '1'
      try {
        const p = await loadYT()
        if (current !== it) return
        if (autoplay) p.loadVideoById(it.id); else p.cueVideoById(it.id)
      } catch (e) { set({ loading: false, playing: false, error: e.message || 'the YouTube player did not load' }) }
    } else {
      if (host) host.dataset.on = ''
      const a = fileEl()
      a.src = '/cc/listen/file?n=' + encodeURIComponent(it.n)
      if (autoplay) a.play().catch(() => set({ loading: false, playing: false }))
    }
  }

  function advance (d) {
    if (st.blockedRun >= MAX_BLOCKED_RUN && d > 0 && st.error) return
    playAt(st.i + d, true)
  }

  function mediaSession (it) {
    try {
      const ms = win.navigator.mediaSession
      if (!ms || !win.MediaMetadata) return
      ms.metadata = new win.MediaMetadata({ title: it.title || '', artist: it.artist || '', album: st.name || '' })
      ms.setActionHandler('play', () => api.toggle(true))
      ms.setActionHandler('pause', () => api.toggle(false))
      ms.setActionHandler('nexttrack', () => api.next())
    } catch (e) {}
  }

  // ---- the controller ------------------------------------------------------------------------------------------
  const api = {
    get: () => ({ ...st }),
    subscribe (f) { subs.add(f); f({ ...st }); return () => subs.delete(f) },
    async start (station, at = 0, autoplay = true) {
      if (st.station && current) { const pos = position(); if (st.playing) log('skip', { ...pos, reason: 'station' }) }
      quiet()
      set({ ...emptyState(), station, loading: true })
      try {
        const r = await win.fetch('/cc/listen/station?id=' + encodeURIComponent(station), { cache: 'no-store' })
        const d = await r.json().catch(() => ({}))
        if (!r.ok || !d.ok) throw new Error(d.error || 'the station did not open')
        if (st.station !== station) return
        set({ name: d.name, kind: d.kind, items: d.items || [], loading: false })
        if (!d.items || !d.items.length) { set({ error: 'nothing on this station' }); return }
        await playAt(at, autoplay)
      } catch (e) { set({ loading: false, error: e.message || 'the station did not open' }) }
    },
    toggle (want) {
      if (!current) { if (st.station) playAt(st.i, true); return }
      const go = typeof want === 'boolean' ? want : !st.playing
      if (go) {
        if (st.blockedRun >= MAX_BLOCKED_RUN) set({ blockedRun: 0, error: '' })
        if (current.k === 'yt' && yt) { try { yt.playVideo() } catch (e) {} } else if (audio) audio.play().catch(() => {})
        set({ loading: !st.playing })
      } else {
        log('pause', position())
        quiet()
        set({ playing: false, loading: false })
      }
    },
    next () {
      if (!st.items.length) return
      if (current && startedLogged) log('skip', position())
      if (st.blockedRun >= MAX_BLOCKED_RUN) set({ blockedRun: 0, error: '' })
      playAt(st.i + 1, true)
    },
    stop () { if (st.playing) log('pause', position()); quiet(); current = null; if (host) host.dataset.on = ''; set(emptyState()); try { win.localStorage.removeItem(LS) } catch (e) {} },
    // where the strip wants the video square (the strip owns the layout; the iframe is never re-parented)
    place (rect) {
      const h = hostEl()
      if (!rect || !(current && current.k === 'yt')) { h.style.left = '-10000px'; return }
      h.style.left = rect.left + 'px'; h.style.top = rect.top + 'px'
    },
    resume () { // after a full reload: the last station and item, paused, one press plays
      try {
        const v = JSON.parse(win.localStorage.getItem(LS) || 'null')
        if (v && v.station && !st.station) api.start(v.station, v.i || 0, false)
      } catch (e) {}
    },
  }
  return api
}

// The controller of this console tab: the top document's, created there once. A pane reaches the top's.
export function listener () {
  if (typeof window === 'undefined') return null
  let w = window
  try { if (window.top && window.top !== window && window.top.document) w = window.top } catch (e) { w = window }
  if (!w.__bfListen) w.__bfListen = makeController(w)
  return w.__bfListen
}

// Plain same-origin links to console pages go through the router while music plays, so a press on "full" on the
// wall or a thread link keeps the music. Bridge pages (/cc/...), the api, files and new tabs are left alone.
export function installLinks (win, router, isPlaying) {
  const onClick = (e) => {
    if (!isPlaying() || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    const a = e.target && e.target.closest ? e.target.closest('a[href]') : null
    if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return
    let u
    try { u = new URL(a.getAttribute('href'), win.location.href) } catch (err) { return }
    if (u.origin !== win.location.origin || !isConsolePage(u.pathname, win)) return
    e.preventDefault()
    router.push(u.pathname + u.search + u.hash)
  }
  win.document.addEventListener('click', onClick)
  return () => win.document.removeEventListener('click', onClick)
}

export function isConsolePage (path, win) {
  if (!path || /^\/(cc|api|v1|_next)(\/|$)/.test(path) || /\.[a-z0-9]{1,5}$/i.test(path)) return false
  const pages = (win && win.__BUILD_MANIFEST && win.__BUILD_MANIFEST.sortedPages) || []
  return pages.some(p => {
    if (p.startsWith('/_')) return false
    const rx = new RegExp('^' + p.replace(/\[\.\.\.[^\]]+\]/g, '.+').replace(/\[[^\]]+\]/g, '[^/]+') + '/?$')
    return rx.test(path)
  })
}

export function clock (s) {
  if (!Number.isFinite(s) || s < 0) return ''
  s = Math.round(s)
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0')
}
