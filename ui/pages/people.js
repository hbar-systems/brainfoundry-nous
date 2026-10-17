import Head from 'next/head'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'

// People (2026-10-17, new-mind standard, Standard tier): who is on the network and a conversation
// with each of them, in plain words. It reads the brain's known peers and the brain-to-brain
// messages (inbox and outbox, merged per person). The Federation page stays the operator tool;
// a "details" link to it shows in operator mode only. Trust model unchanged; see docs/PEOPLE.md.

const API = '/api/bf'

const get = (path) => fetch(`${API}${path}`, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null)

// The name a message to this person is addressed by: the subdomain of a brainfoundry.ai address,
// otherwise the brain id. The same keys match their messages in and out.
function handleOf(peer) {
  try {
    const host = new URL(peer.endpoint).hostname
    if (host.endsWith('.brainfoundry.ai')) return host.split('.')[0]
  } catch { /* no usable address */ }
  return peer.brain_id
}

function when(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const today = new Date().toDateString() === d.toDateString()
  return today ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
               : d.toLocaleDateString([], { day: 'numeric', month: 'short' }) + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function People() {
  const [peers, setPeers] = useState(null) // null = loading
  const [inbox, setInbox] = useState([])
  const [outbox, setOutbox] = useState([])
  const [online, setOnline] = useState({}) // handle -> true | false
  const [open, setOpen] = useState(null)   // handle of the conversation shown
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [note, setNote] = useState(null)
  const [operator, setOperator] = useState(false)
  const bottom = useRef(null)

  const loadMessages = () => {
    get('/v1/federation/dm/inbox?limit=200').then(d => { if (d && Array.isArray(d.messages)) setInbox(d.messages) })
    get('/v1/federation/dm/outbox?limit=200').then(d => { if (d && Array.isArray(d.messages)) setOutbox(d.messages) })
  }

  useEffect(() => {
    get('/v1/federation/peers').then(d => {
      const list = (d && d.peers) || []
      setPeers(list)
      list.forEach(p => {
        fetch(`${API}/v1/federation/peers/ping`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: p.brain_id }),
        }).then(r => (r.ok ? r.json() : null)).then(x => setOnline(o => ({ ...o, [handleOf(p)]: !!(x && x.ok) })))
          .catch(() => setOnline(o => ({ ...o, [handleOf(p)]: false })))
      })
    })
    loadMessages()
    // A brain without the bridge, or in operator mode, is the operator's own: the details link shows.
    fetch('/cc/layout/mode', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null))
      .then(m => setOperator(!m || m.mode !== 'newcomer')).catch(() => setOperator(true))
    const t = setInterval(loadMessages, 20000)
    return () => clearInterval(t)
  }, [])

  // One entry per person: known peers first, then anyone who wrote without being on the list.
  const people = []
  const byKey = {}
  for (const p of peers || []) {
    const h = handleOf(p)
    const person = { handle: h, keys: new Set([h, p.brain_id]), name: p.name || '', known: true }
    people.push(person); byKey[h] = person; byKey[p.brain_id] = person
  }
  for (const m of inbox) {
    if (!byKey[m.from_brain]) {
      const person = { handle: m.from_brain, keys: new Set([m.from_brain]), name: '', known: false }
      people.push(person); byKey[m.from_brain] = person
    }
  }
  const threadOf = (person) => [
    ...inbox.filter(m => person.keys.has(m.from_brain)).map(m => ({ ...m, mine: false, ts: m.payload_ts })),
    ...outbox.filter(m => person.keys.has(m.to_brain)).map(m => ({ ...m, mine: true, ts: m.payload_ts })),
  ].sort((a, b) => a.ts - b.ts)
  const unreadOf = (person) => inbox.filter(m => person.keys.has(m.from_brain) && !m.read_at).length

  const current = open ? people.find(p => p.handle === open) : null
  const thread = current ? threadOf(current) : []

  // Opening a conversation reads it, and so does a new message arriving while it is open.
  const openUnread = current ? unreadOf(current) : 0
  useEffect(() => {
    if (!current || openUnread === 0) return
    const unread = inbox.filter(m => current.keys.has(m.from_brain) && !m.read_at)
    Promise.all(unread.map(m => fetch(`${API}/v1/federation/dm/inbox/${m.id}/read`, { method: 'POST' }).catch(() => {})))
      .then(loadMessages)
  }, [open, openUnread])

  useEffect(() => { if (bottom.current) bottom.current.scrollIntoView({ block: 'end' }) }, [open, thread.length])

  const send = async () => {
    const msg = text.trim()
    if (!current || !msg || sending) return
    setSending(true); setNote(null)
    try {
      const r = await fetch(`${API}/v1/federation/dm/send`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: current.handle, message: msg }),
      })
      const d = await r.json().catch(() => ({}))
      if (r.ok) {
        setText('')
        if (!d.delivered) setNote(`Saved, but ${current.name || current.handle}'s brain did not answer. Try again later.`)
      } else {
        setNote(`Not sent: ${current.name || current.handle}'s brain could not be reached.`)
      }
      loadMessages()
    } catch {
      setNote('Not sent: no connection.')
    } finally { setSending(false) }
  }

  const label = (p) => p.name ? `${p.name} (${p.handle})` : p.handle

  return (
    <div style={{ padding: '32px 24px', maxWidth: 980, margin: '0 auto' }}>
      <Head><title>People</title></Head>
      <h1 style={{ fontFamily: 'var(--font-display, Lora, Georgia, serif)', fontSize: 30, fontWeight: 600, margin: '0 0 6px 0', color: 'var(--text)' }}>People</h1>
      <p style={{ color: 'var(--muted)', margin: '0 0 20px 0', lineHeight: 1.6 }}>
        Friends whose brains know yours. Pick one to write to them.
        {operator && <> <Link href="/federation" style={{ color: 'var(--muted)', fontSize: 12, marginLeft: 6 }}>details</Link></>}
      </p>

      {peers === null && <p style={{ color: 'var(--muted)' }}>Loading…</p>}
      {peers !== null && people.length === 0 && (
        <p style={{ color: 'var(--muted)', fontStyle: 'italic' }}>No one yet. People appear here when a friend's brain joins yours.</p>
      )}

      {people.length > 0 && (
        <div style={{ display: 'flex', gap: 16, alignItems: 'stretch', minHeight: 420 }}>
          <div style={{ width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {people.map(p => {
              const n = unreadOf(p)
              const on = online[p.handle]
              return (
                <button key={p.handle} onClick={() => { setOpen(p.handle); setNote(null) }}
                  style={{ textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', fontFamily: 'var(--font-body)',
                           border: '1px solid var(--border)', color: 'var(--text)',
                           background: open === p.handle ? 'var(--surface2)' : 'var(--bg)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span title={on ? 'online' : on === false ? 'not online' : ''}
                      style={{ width: 8, height: 8, borderRadius: 4, flexShrink: 0,
                               background: on ? '#5fbf7f' : on === false ? 'var(--border)' : 'transparent' }} />
                    <span style={{ flex: 1, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name || p.handle}</span>
                    {n > 0 && <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 10, background: 'var(--accent)', color: 'var(--bg)' }}>{n}</span>}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2, marginLeft: 16 }}>
                    {p.name ? p.handle + ' · ' : ''}{p.known ? (on ? 'online' : on === false ? 'not online' : '') : 'wrote to you'}
                  </div>
                </button>
              )
            })}
          </div>

          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', border: '1px solid var(--border)', borderRadius: 10 }}>
            {!current && <p style={{ color: 'var(--muted)', margin: 'auto', fontStyle: 'italic' }}>Pick someone on the left.</p>}
            {current && (
              <>
                <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 14, color: 'var(--text)', fontWeight: 600 }}>
                  {label(current)}
                  {!current.known && <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--muted)' }}> · not among your friends yet</span>}
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: 14, display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '55vh' }}>
                  {thread.length === 0 && <p style={{ color: 'var(--muted)', fontStyle: 'italic', margin: 0 }}>No messages yet. Say hello.</p>}
                  {thread.map(m => (
                    <div key={(m.mine ? 'o' : 'i') + m.id} style={{ alignSelf: m.mine ? 'flex-end' : 'flex-start', maxWidth: '78%' }}>
                      <div style={{ padding: '8px 12px', borderRadius: 10, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 14, lineHeight: 1.5,
                                    background: m.mine ? 'var(--surface2)' : 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text)' }}>
                        {m.message}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2, textAlign: m.mine ? 'right' : 'left' }}>
                        {when(m.ts)}{m.mine && !m.delivered ? ' · not delivered' : ''}
                      </div>
                    </div>
                  ))}
                  <div ref={bottom} />
                </div>
                {note && <div style={{ padding: '6px 14px', fontSize: 12, color: '#c9a060' }}>{note}</div>}
                <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--border)' }}>
                  <textarea value={text} onChange={e => setText(e.target.value)} rows={2} maxLength={8000}
                    placeholder={`Write to ${current.name || current.handle}`}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                    style={{ flex: 1, resize: 'vertical', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border)',
                             background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--font-body)', fontSize: 14 }} />
                  <button onClick={send} disabled={sending || !text.trim()}
                    style={{ padding: '0 18px', borderRadius: 8, border: 'none', cursor: sending ? 'wait' : 'pointer',
                             background: 'var(--accent)', color: 'var(--bg)', fontWeight: 600, opacity: sending || !text.trim() ? 0.5 : 1 }}>
                    {sending ? 'Sending…' : 'Send'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
