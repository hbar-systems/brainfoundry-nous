/* Talk in place (INLINE-1, 2026-11-23): the one script a brain-built page includes.

   <script src="/cc/inline.js" data-page="court-tasks"></script>
   <li data-talk-key="T123" data-talk-title="Fix the door" data-talk-text="..." data-talk-link="/cc/...">...</li>

   A press inside the item marked data-talk-open is the note press (else a small "note" chip is added); a press
   marked data-talk-send="text" sends that text at once as a turn of the item's note (a ruling, a done), and the
   answer shows in the box; with no console behind the page, both fall back to their own href.
   Every element with data-talk-key gets a note press. It opens a box under the item: type a question,
   a clarification, or "send an agent". The turn goes to a side conversation bound to that item (never a new
   thread in the list); the answer comes back into the same box, folded, with a dot until you open it. A job
   the agent starts lands in the box as a card when it ends. A quiet line at the bottom says "2 answers ready".

   Same login, same posture and cards as a typed turn: the script only calls the console's own doors
   (/cc/sides*), which need the console login and refuse an app frame. All text is drawn with textContent,
   never as HTML, so an answer cannot put markup or script into this page. Opened at /cc/files/raw (an
   opaque origin) the doors refuse it; the press then says where the page talks. */
(function () {
  'use strict'
  if (window.ccInline) return
  var me = document.currentScript
  var base = '/cc'
  try { base = new URL(me.src, location.href).pathname.replace(/\/inline\.js$/, '') } catch (e) {}
  var page = (me && me.getAttribute('data-page')) || location.pathname
  var home = (me && me.getAttribute('data-home')) || ''
  var refused = location.origin === 'null'
  var sides = {}, open = {}, drafts = {}
  var C = { ink: '#e8e2d6', dim: '#a89e90', faint: '#7a7166', line: 'rgba(232,226,214,0.16)', bg: '#22201d', gold: '#d9b36c', bad: '#d08a7a', onGold: '#1c1a17' }
  // the box takes the page's own tone: a light page (the tasks court is cream) gets a light, warm box
  function tone() {
    try {
      var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(getComputedStyle(document.body).backgroundColor || '')
      if (m && (0.299 * m[1] + 0.587 * m[2] + 0.114 * m[3]) > 150) {
        C = { ink: '#2b2620', dim: '#6f6556', faint: '#9a8f80', line: '#e2d8c6', bg: '#fffaf1', gold: '#8a6a2e', bad: '#9a4f3f', onGold: '#fffaf1' }
      }
    } catch (e) {}
  }

  function el(tag, css, text) {
    var n = document.createElement(tag)
    if (css) n.style.cssText = css
    if (text != null) n.textContent = text
    return n
  }
  // a line of an answer: plain text, with https:// and console paths as links (built as nodes, never HTML)
  function linkify(line) {
    var p = el('p', 'margin:0 0 6px 0;white-space:pre-wrap;word-break:break-word')
    var re = /(https:\/\/[^\s<>"')]+|\/cc\/[^\s<>"')]+)/g, last = 0, m
    while ((m = re.exec(line))) {
      if (m.index > last) p.appendChild(document.createTextNode(line.slice(last, m.index)))
      var a = el('a', 'color:' + C.gold, m[0]); a.href = m[0]; a.target = '_blank'; a.rel = 'noreferrer'
      p.appendChild(a); last = m.index + m[0].length
    }
    if (last < line.length) p.appendChild(document.createTextNode(line.slice(last)))
    return p
  }
  function api(method, path, body) {
    return fetch(base + path, { method: method, credentials: 'same-origin', cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {} }).then(function (d) { d._status = r.status; return d }) })
  }
  function itemOf(key) { return document.querySelector('[data-talk-key="' + (window.CSS && CSS.escape ? CSS.escape(key) : key) + '"]') }
  function stateWord(s) {
    if (!s) return ''
    if (s.state === 'running') return 'working…'
    if (s.state === 'waiting') return 'waits for a free seat'
    if (s.state === 'failed') return 'did not finish'
    if (s.ready) return 'answer ready'
    return ''
  }

  // the presses that belong to this item, not to an item nested inside it (a group holds its tasks)
  function own(node, sel) {
    return Array.prototype.filter.call(node.querySelectorAll(sel), function (x) { return x.closest('[data-talk-key]') === node })
  }
  function chip(node) {
    var key = node.getAttribute('data-talk-key')
    var c = own(node, '[data-talk-chip]')[0]
    if (!node.getAttribute('data-talk-wired')) {
      node.setAttribute('data-talk-wired', '1')
      own(node, '[data-talk-send]').forEach(function (b) {
        b.addEventListener('click', function (e) {
          if (refused) return                      // the plain file: the press keeps its own href (the chat)
          e.preventDefault(); e.stopPropagation()
          send(key, b.getAttribute('data-talk-send'), b.getAttribute('data-talk-mode') || 'ask')
        })
      })
      var o = own(node, '[data-talk-open]')[0]
      if (o) {
        o.setAttribute('data-talk-chip', '1'); c = o
        c.addEventListener('click', function (e) { if (refused) return; e.preventDefault(); e.stopPropagation(); toggle(key) })
        c.setAttribute('data-talk-label', c.textContent)
      }
    }
    if (!c) {
      c = el('button', 'font:11px ui-monospace,monospace;letter-spacing:.08em;background:none;border:1px solid ' + C.line +
        ';color:' + C.dim + ';border-radius:12px;padding:2px 9px;cursor:pointer;margin-left:6px;vertical-align:middle')
      c.type = 'button'; c.setAttribute('data-talk-chip', '1')
      ;(own(node, '[data-talk-slot]')[0] || node).appendChild(c)
      c.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); toggle(key) })
    }
    var s = sides[key]
    c.textContent = ''
    if (s && (s.ready || s.state === 'running' || s.state === 'waiting')) {
      c.appendChild(el('span', 'display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;vertical-align:1px;background:' +
        (s.state === 'running' || s.state === 'waiting' ? C.dim : s.state === 'failed' ? C.bad : C.gold)))
    }
    var label = c.getAttribute('data-talk-label') || 'note'
    c.appendChild(document.createTextNode(s && s.turns && s.turns.length ? label + ' · ' + Math.ceil(s.turns.length / 2) : label))
    c.title = refused ? 'talk in place works when this page is opened at ' + base + '/page/…' : (stateWord(s) || 'ask, clarify or send an agent, right here')
  }

  function box(key) {
    var node = itemOf(key)
    if (!node) return null
    var b = own(node, '[data-talk-box]')[0]
    if (!b) {
      b = el('div', 'grid-column:1/-1;margin:8px 0 4px 0;padding:10px 12px;border:1px solid ' + C.line + ';border-radius:10px;background:' + C.bg +
        ';color:' + C.ink + ';font:14px/1.45 system-ui,sans-serif;text-align:left;cursor:auto')
      b.setAttribute('data-talk-box', '1')
      b.addEventListener('click', function (e) { e.stopPropagation() })
      node.appendChild(b)
    }
    return b
  }

  function draw(key) {
    var b = box(key)
    if (!b) return
    b.style.display = open[key] ? 'block' : 'none'
    if (!open[key]) return
    var s = sides[key] || { turns: [] }
    var keep = b.querySelector('textarea'); if (keep) drafts[key] = keep.value
    b.textContent = ''
    if (refused) {
      b.appendChild(el('p', 'margin:0;color:' + C.dim, 'This copy of the page cannot talk (opened as a plain file). Open it at ' + base + '/page/… to talk here.'))
      return
    }
    var turns = s.turns || []
    var answered = s.ready ? turns.length - 1 : -1
    turns.forEach(function (t, i) {
      var row = el('div', 'margin:0 0 8px 0')
      if (t.who === 'me') {
        row.appendChild(el('p', 'margin:0;color:' + C.dim + ';font-size:13px', (t.mode === 'agent' ? 'agent: ' : 'you: ') + t.text))
      } else if (i === answered) {
        var fold = el('button', 'font:12px ui-monospace,monospace;background:none;border:none;color:' + C.gold + ';cursor:pointer;padding:0', '● answer ready, press to read')
        fold.type = 'button'
        fold.addEventListener('click', function () { s.ready = false; api('POST', '/sides/read', { key: key }).then(footer); draw(key); chip(itemOf(key)); footer() })
        row.appendChild(fold)
      } else {
        String(t.text || '').split('\n').filter(function (l) { return l.trim() }).forEach(function (l) { row.appendChild(linkify(l)) })
      }
      b.appendChild(row)
    })
    ;(s.cards || []).forEach(function (c) {
      var d = c.data || {}, r = d.result || {}
      var card = el('div', 'margin:0 0 8px 0;padding:6px 9px;border-left:2px solid ' + (d.rc === 0 || r.rc === 0 ? C.gold : C.bad))
      card.appendChild(el('p', 'margin:0 0 4px 0;font:10px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:' + C.dim,
        (c.kind === 'job' ? 'job finished' : 'report') + ' · ' + (d.title || d.id || '')))
      String(r.text || (d.lines || []).join('\n')).split('\n').filter(function (l) { return l.trim() }).slice(0, 6).forEach(function (l) { card.appendChild(linkify(l)) })
      b.appendChild(card)
    })
    var w = stateWord(s)
    if (w && w !== 'answer ready') b.appendChild(el('p', 'margin:0 0 8px 0;font:12px ui-monospace,monospace;color:' + (s.state === 'failed' ? C.bad : C.dim), w + (s.error ? ': ' + s.error : '')))
    var ta = el('textarea', 'width:100%;box-sizing:border-box;min-height:54px;resize:vertical;background:transparent;color:' + C.ink +
      ';border:1px solid ' + C.line + ';border-radius:8px;padding:7px 9px;font:14px/1.4 system-ui,sans-serif')
    ta.placeholder = turns.length ? 'continue, or send an agent' : 'a question, a clarification, or what an agent should do'
    ta.value = drafts[key] || ''
    ta.addEventListener('input', function () { drafts[key] = ta.value; try { localStorage.setItem('cc.inline.draft.' + key, ta.value) } catch (e) {} })
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); say(key, 'ask') } })
    b.appendChild(ta)
    var row = el('div', 'display:flex;gap:8px;margin-top:6px;flex-wrap:wrap')
    var busy = s.state === 'running' || s.state === 'waiting'
    ;[['ask', 'ask'], ['agent', 'send an agent']].forEach(function (m) {
      var btn = el('button', 'font:12px ui-monospace,monospace;border-radius:14px;padding:4px 12px;cursor:pointer;border:1px solid ' +
        (m[0] === 'ask' ? C.gold : C.line) + ';background:' + (m[0] === 'ask' ? C.gold : 'transparent') + ';color:' + (m[0] === 'ask' ? C.onGold : C.ink), m[1])
      btn.type = 'button'; btn.disabled = busy; if (busy) btn.style.opacity = '0.5'
      btn.addEventListener('click', function () { say(key, m[0]) })
      row.appendChild(btn)
    })
    var close = el('button', 'margin-left:auto;font:12px ui-monospace,monospace;background:none;border:none;color:' + C.faint + ';cursor:pointer', 'fold')
    close.type = 'button'; close.addEventListener('click', function () { toggle(key) })
    row.appendChild(close)
    b.appendChild(row)
  }

  function toggle(key) {
    open[key] = !open[key]
    if (open[key]) { var n = itemOf(key), d = n && n.closest('details'); while (d) { d.open = true; d = d.parentElement && d.parentElement.closest('details') } }
    if (open[key] && drafts[key] == null) { try { drafts[key] = localStorage.getItem('cc.inline.draft.' + key) || '' } catch (e) { drafts[key] = '' } }
    draw(key)
    if (open[key]) { var t = box(key) && box(key).querySelector('textarea'); if (t) t.focus() }
  }

  function say(key, mode) {
    var text = (drafts[key] || '').trim()
    if (!text) return
    drafts[key] = ''; try { localStorage.removeItem('cc.inline.draft.' + key) } catch (e) {}
    send(key, text, mode, true)
  }

  // one turn of the item's note: typed in its box, or a press that carries its own text
  function send(key, text, mode, typed) {
    var node = itemOf(key)
    text = String(text || '').trim()
    if (!node || !text) return
    if (!open[key]) { open[key] = true; if (drafts[key] == null) drafts[key] = '' }
    var body = { key: key, message: text, mode: mode, page: page, home: home || undefined,
      title: node.getAttribute('data-talk-title') || (node.textContent || '').trim().slice(0, 120),
      text: node.getAttribute('data-talk-text') || '', link: node.getAttribute('data-talk-link') || location.pathname }
    var s = sides[key] || (sides[key] = { key: key, turns: [] })
    if (s.state === 'running' || s.state === 'waiting') { s.error = 'still answering the last one'; draw(key); return }
    s.turns = (s.turns || []).concat([{ who: 'me', text: text, mode: mode }]); s.state = 'running'; s.ready = false; s.error = null
    draw(key); chip(node)
    api('POST', '/sides/say', body).then(function (d) {
      if (d._status >= 300) { s.state = 'failed'; s.error = d.error || ('the door answered ' + d._status); s.turns.pop(); if (typed) drafts[key] = text }
      else if (d.side) sides[key] = Object.assign(d.side, { cards: s.cards })
      draw(key); chip(node); poll(true)
    }).catch(function () { s.state = 'failed'; s.error = 'the console did not answer'; if (typed) drafts[key] = text; draw(key) })
  }

  // the footer's quiet line: "2 answers ready", press to jump to the first one on this page
  var foot = null
  function footer() {
    var ready = Object.keys(sides).filter(function (k) { return sides[k].ready && itemOf(k) })
    if (!foot) {
      foot = el('button', 'position:fixed;left:50%;transform:translateX(-50%);bottom:10px;z-index:9999;font:12px ui-monospace,monospace;' +
        'background:' + C.bg + ';color:' + C.gold + ';border:1px solid ' + C.line + ';border-radius:14px;padding:5px 14px;cursor:pointer;display:none')
      foot.type = 'button'; foot.setAttribute('data-talk-footer', '1')
      foot.addEventListener('click', function () {
        var k = Object.keys(sides).filter(function (x) { return sides[x].ready && itemOf(x) })[0]
        if (!k) return
        itemOf(k).scrollIntoView({ block: 'center', behavior: 'smooth' })
        if (!open[k]) toggle(k)
      })
      document.body.appendChild(foot)
    }
    foot.style.display = ready.length ? 'block' : 'none'
    foot.textContent = ready.length === 1 ? '1 answer ready' : ready.length + ' answers ready'
  }

  var timer = null
  function poll(soon) {
    if (refused) return
    clearTimeout(timer)
    timer = setTimeout(tick, soon ? 2500 : 0)
  }
  function tick() {
    api('GET', '/sides?page=' + encodeURIComponent(page)).then(function (d) {
      var before = JSON.stringify(sides)
      ;(d.sides || []).forEach(function (s) { sides[s.key] = s })
      if (JSON.stringify(sides) !== before) Object.keys(open).forEach(function (k) { if (open[k]) draw(k) })
      scan(); footer()
      var running = Object.keys(sides).some(function (k) { return sides[k].state === 'running' || sides[k].state === 'waiting' })
      timer = setTimeout(tick, running ? 4000 : 15000)
    }).catch(function () { timer = setTimeout(tick, 30000) })
  }
  // presence: while this page is in front, the box knows the owner is looking (no Telegram line then)
  function seen() { if (!refused && document.visibilityState === 'visible') api('POST', '/sides/seen', {}).catch(function () {}) }

  function scan() { Array.prototype.forEach.call(document.querySelectorAll('[data-talk-key]'), chip) }

  window.ccInline = { scan: scan, open: function (k) { if (!open[k]) toggle(k) }, send: send, sides: sides }
  function start() {
    tone()
    scan()
    if (refused) return
    tick(); seen()
    // /cc/page/<name>/#talk=<key>: open that item's note (the footer of another page jumps here this way)
    var h = /^#talk=(.+)$/.exec(location.hash || '')
    if (h) { var k = decodeURIComponent(h[1]); if (itemOf(k)) { toggle(k); itemOf(k).scrollIntoView({ block: 'center' }) } }
    setInterval(seen, 60000)
    document.addEventListener('visibilitychange', seen)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start()
})()
