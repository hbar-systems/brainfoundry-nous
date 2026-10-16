import Head from 'next/head'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Guide: how CC works, in the console, in plain words, and a tutorial that checks itself
// against the brain: each step turns done when the box has seen it happen. Served by the
// bridge (/cc/guide is docs/CC.md from the brain's checkout; /cc/health carries the counts).
// Added 2026-09-23.
const mono = { fontFamily: "'JetBrains Mono', ui-monospace, monospace" }
const T = { ink: 'var(--text)', dim: 'var(--text-dim)', faint: 'var(--muted)', line: 'var(--border)', card: 'var(--surface)', gold: 'var(--accent)', codeBg: 'var(--code-bg)' }

function steps(h) {
  const t = (h && h.tutorial) || {}
  const auth = (h && h.auth) || {}
  return [
    { key: 'connect', label: 'Give your brain a reasoner', done: !!auth.loggedIn,
      how: 'On the home screen, paste your own API key in the card, or press "Sign in with a Claude subscription" and follow the door. Your credentials stay on your server.' },
    { key: 'first', label: 'Ask it something it should remember', done: !!(h && h.session),
      how: 'Type a question about yourself or your work. The answer is grounded in what the brain remembers; the rings on the graph show what it read.' },
    { key: 'files', label: 'See what it makes', done: (t.out_files || 0) > 0,
      how: 'Ask for something concrete: "make a 5 second tone as a wav" or "write a short note about today under your out folder". The Files pane opens beside the chat; play it, read it, download it.' },
    { key: 'attach', label: 'Give it a file', done: (t.in_files || 0) > 0,
      how: 'Press attach, or drop a file on the box where you type, then ask about it. It lands on your server and the reasoner reads it there.' },
    { key: 'card', label: 'Allow one action with a card', done: (t.permits || 0) > 0,
      how: 'Ask it to create or change a file on the box. A card shows the exact file or command. Press Allow. Everything it does with hands goes through a card like this, or a rule you set.' },
    { key: 'job', label: 'Start something that outlives a turn', done: (t.jobs || 0) > 0,
      how: 'Ask for a task that takes minutes: "start a job that sleeps 90 seconds then writes done.txt". It runs on after the answer; a small card tells you when it is finished.' },
    { key: 'posture', label: 'Choose how much it asks', done: !!(h && h.posture && h.posture !== 'cards'),
      how: 'Type /posture and read the three choices: cards asks for everything, auto lets the vendor classifier decide, judged scores each action and asks only when the score is low. sudo always asks.' },
  ]
}

// Privacy: short entries pointing to the full chapters in docs/public (2026-10-16).
const PRIVACY = [
  { label: 'Two kinds of memory',
    how: 'Every piece of memory is open (the default: any model may read it) or local-only (only a model on your own hardware, answering you here). Choose with the Privacy chips on the Knowledge tab, before an upload or per document in Browse.' },
  { label: 'Local or hosted, judged by address',
    how: 'A model counts as local only when it runs in Ollama at an address on your own network (the box, a private or Tailscale address) and is not a :cloud model. Anything in doubt counts as hosted. Narrow it further with your list of local readers in Knowledge -> Vault.' },
  { label: 'The session mark',
    how: 'Once a local model has read local-only memory in a session, the session is marked. A hosted model may not continue it: nothing is sent, and you are offered a fresh session. In that turn only GREEN tools (own memory, own task list) run.' },
  { label: 'The vault',
    how: 'A folder on the box only you can read; the Claude and Codex seats cannot. Set it up on the box, as yourself, with scripts/vault-setup.sh. Its text files become local-only memory; every read is listed under Recent reads in Knowledge -> Vault and in the Trace tab.' },
  { label: 'What is not protected',
    how: 'Files outside the vault (the seats can read them), memory is not encrypted, backups hold everything, the API key reads local-only memory, embeddings see all text at ingest, and the allowlist matches model names.' },
  { label: 'Who reads what',
    how: 'One table: every reader (you, local and hosted models, the seats, brain-apps, Telegram, visitors, other brains, root) against every kind of thing the brain holds.' },
]

export default function Guide() {
  const [health, setHealth] = useState(null)
  const [md, setMd] = useState(null)
  const [tab, setTab] = useState('tutorial')
  const embedded = typeof window !== 'undefined' && window.self !== window.top
  useEffect(() => {
    fetch('/cc/health', { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).then(setHealth).catch(() => setHealth(false))
    fetch('/cc/guide', { cache: 'no-store' }).then(r => (r.ok ? r.json() : { markdown: null })).then(d => setMd(d.markdown || null)).catch(() => setMd(null))
    try { const q = new URLSearchParams(window.location.search).get('tab'); if (q) setTab(q) } catch {}
  }, [])
  const rows = steps(health)
  const done = rows.filter(r => r.done).length
  return (
    <>
      <Head><title>Guide · BrainFoundry</title></Head>
      <div style={{ maxWidth: '860px', margin: '0 auto', padding: '18px 20px 60px', color: T.ink, fontFamily: 'var(--font-display, serif)' }}>
        <p style={{ ...mono, fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', color: T.gold, margin: '0 0 6px 0' }}>Guide · how this brain works</p>
        <div style={{ display: 'flex', gap: '14px', margin: '0 0 18px 0', borderBottom: `1px solid ${T.line}` }}>
          {[['tutorial', `Tutorial (${done} of ${rows.length})`], ['guide', 'The guide'], ['privacy', 'Privacy']].map(([k, label]) => (
            <a key={k} onClick={() => setTab(k)} style={{ ...mono, fontSize: '12px', padding: '8px 2px', cursor: 'pointer', color: tab === k ? T.ink : T.dim, borderBottom: tab === k ? `2px solid ${T.gold}` : '2px solid transparent' }}>{label}</a>
          ))}
        </div>
        {tab === 'tutorial' && (
          <div>
            <p style={{ fontSize: '14px', color: T.dim, lineHeight: 1.6, margin: '0 0 16px 0' }}>
              Seven things to do once. Each turns done by itself when your brain has seen it happen. Nothing here is required; it is the shortest way to know what you have.
            </p>
            {health === false && <p style={{ fontSize: '13px', color: '#d08a7a' }}>The bridge on the box is not answering, so the checks cannot run. The guide tab still reads.</p>}
            {rows.map((s, i) => (
              <div key={s.key} style={{ display: 'flex', gap: '14px', padding: '12px 0', borderBottom: `1px solid ${T.line}`, opacity: s.done ? 0.6 : 1 }}>
                <span style={{ ...mono, fontSize: '12px', color: s.done ? T.gold : T.faint, width: '22px', flexShrink: 0 }}>{s.done ? '✓' : i + 1}</span>
                <div>
                  <p style={{ margin: '0 0 4px 0', fontSize: '15px', color: T.ink }}>{s.label}</p>
                  <p style={{ margin: 0, fontSize: '13px', color: T.dim, lineHeight: 1.6 }}>{s.how}</p>
                </div>
              </div>
            ))}
            <p style={{ ...mono, fontSize: '11px', color: T.faint, margin: '16px 0 0 0' }}>
              {embedded ? 'Close this pane to go back to the conversation.' : 'The conversation is the home screen; "everything" at the top right lists every tab.'}
            </p>
          </div>
        )}
        {tab === 'privacy' && (
          <div>
            <p style={{ fontSize: '14px', color: T.dim, lineHeight: 1.6, margin: '0 0 16px 0' }}>
              Who can read what your brain remembers, in six lines. The full text is in your brain's checkout: docs/public/06-privacy-and-memory.md and docs/public/07-who-reads-what.md. Ask the brain to open either one.
            </p>
            {PRIVACY.map(s => (
              <div key={s.label} style={{ padding: '12px 0', borderBottom: `1px solid ${T.line}` }}>
                <p style={{ margin: '0 0 4px 0', fontSize: '15px', color: T.ink }}>{s.label}</p>
                <p style={{ margin: 0, fontSize: '13px', color: T.dim, lineHeight: 1.6 }}>{s.how}</p>
              </div>
            ))}
          </div>
        )}
        {tab === 'guide' && (
          <div className="cc-md" style={{ fontSize: '14.5px', lineHeight: 1.65 }}>
            {md === null && <p style={{ color: T.dim, fontSize: '13px' }}>The guide is docs/CC.md in your brain's checkout; the bridge could not read it.</p>}
            {md && (
              <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
                components={{
                  h1: ({ node, ...p }) => <h1 {...p} style={{ fontSize: '22px', margin: '0 0 12px 0' }} />,
                  h2: ({ node, ...p }) => <h2 {...p} style={{ fontSize: '17px', margin: '26px 0 8px 0', color: T.gold }} />,
                  p: ({ node, ...p }) => <p {...p} style={{ margin: '0 0 10px 0' }} />,
                  a: ({ node, ...p }) => <a {...p} target="_blank" rel="noreferrer" style={{ color: T.gold }} />,
                  ul: ({ node, ...p }) => <ul {...p} style={{ margin: '0 0 10px 0', paddingLeft: '20px' }} />,
                  pre: ({ node, ...p }) => <pre {...p} style={{ ...mono, fontSize: '12.5px', backgroundColor: T.codeBg, padding: '8px 10px', borderRadius: '6px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }} />,
                  code: ({ node, ...p }) => <code {...p} style={{ ...mono, fontSize: '12.5px', backgroundColor: T.codeBg, padding: '1px 5px', borderRadius: '4px' }} />,
                }}>{md}</ReactMarkdown>
            )}
          </div>
        )}
      </div>
    </>
  )
}
