import { useEffect, useState } from 'react'

// Economy — the harmonics surface for THIS brain. Plain-language prose is
// sourced from the hbar.harmonics EXPLAINER (Part 1). Honesty constraints are
// load-bearing: harmonics is earned recognition, never money — no coin, token,
// wallet, balance, currency, or payment language anywhere on this page.

function Block({ children }) {
  // One sentence per visual block — never run-together paragraphs.
  return <div style={{ margin: '0 0 7px 0', lineHeight: 1.65 }}>{children}</div>
}

function Card({ children, style }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: '12px', padding: '22px 24px', ...style,
    }}>{children}</div>
  )
}

function fmtTime(ts) {
  if (!ts) return '—'
  try { return new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ') }
  catch { return String(ts) }
}

export default function Economy() {
  const [standing, setStanding] = useState(null) // { standing, half_life_days }
  const [ledger, setLedger] = useState(null)     // { events, count }
  const [err, setErr] = useState(null)

  useEffect(() => {
    fetch('/api/bf/harmonics/standing')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) setStanding(d) })
      .catch(() => {})
    fetch('/api/bf/harmonics/ledger')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (d) setLedger(d) })
      .catch(e => setErr(String(e)))
  }, [])

  const muted = 'var(--muted)'
  const events = ledger?.events || []

  return (
    <div style={{
      padding: '40px 32px', maxWidth: '860px', margin: '0 auto',
      color: 'var(--text)', fontFamily: 'var(--font-body)',
    }}>
      <h1 style={{ fontSize: '26px', fontWeight: 700, margin: '0 0 6px 0' }}>Economy</h1>
      <div style={{ fontSize: '14px', color: muted, marginBottom: '20px' }}>
        Harmonics — earned recognition for contributing knowledge. Not money.
      </div>

      {/* One-test-brain honesty frame — load-bearing. */}
      <Card style={{ marginBottom: '24px', borderColor: 'var(--accent)', background: 'rgba(201,169,110,0.06)' }}>
        <div style={{ fontSize: '13px', color: 'var(--text)' }}>
          <Block><strong>This is one test brain.</strong></Block>
          <Block>What you see here is how harmonics is designed to work — not a live network.</Block>
          <Block>Cross-brain exchange is still being built; this brain shows its own ledger and standing only.</Block>
        </div>
      </Card>

      {/* What harmonics is — plain language, from the EXPLAINER. */}
      <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 10px 0' }}>What harmonics is</h2>
      <div style={{ fontSize: '14px', color: 'var(--text)', marginBottom: '22px' }}>
        <Block>Harmonics is an honest, unfakeable record of who has genuinely contributed to a shared community of knowledge.</Block>
        <Block>A contribution is the moment one brain's knowledge genuinely reaches another brain — and is relevant and new to it.</Block>
        <Block>When that happens, the exchange is scored, signed by both brains, and locked into an append-only ledger.</Block>
        <Block>Each exchange is measured as an angle between two pieces of meaning: enough common ground to be understood, enough novelty to matter.</Block>
        <Block>The score is a symbol attached to a calculated equation, attached to a measurement — nothing more.</Block>
      </div>

      {/* The honest limit — hard constraint. */}
      <Card style={{ marginBottom: '24px' }}>
        <div style={{ fontSize: '13px', color: muted }}>
          <Block><strong style={{ color: 'var(--text)' }}>What it can and cannot claim.</strong></Block>
          <Block>The system estimates whether a contribution was relevant and new.</Block>
          <Block>It does not know whether it helped — "help" is a human reading of a high score, not something the system itself measures.</Block>
        </div>
      </Card>

      {/* Standing. */}
      <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 10px 0' }}>This brain's standing</h2>
      <Card style={{ marginBottom: '10px' }}>
        <div style={{
          fontSize: '40px', fontWeight: 700, fontFamily: 'var(--font-mono)',
          color: 'var(--accent)', lineHeight: 1.1,
        }}>
          {standing ? Number(standing.standing).toFixed(6) : '—'}
        </div>
        <div style={{ fontSize: '12px', color: muted, marginTop: '6px' }}>
          {standing
            ? `decayed contribution score · half-life ${standing.half_life_days} days`
            : 'loading…'}
        </div>
      </Card>
      <div style={{ fontSize: '13px', color: muted, marginBottom: '24px' }}>
        <Block>Standing is the decayed sum of this brain's contributions, computed fresh every time it is read — never stored as a balance.</Block>
        <Block>It fades: if the brain stops contributing, its standing slowly decays — a record of what it is doing, not a medal it keeps.</Block>
        <Block>It is non-transferable and non-spendable. There is no operation to send it, and holding money earns none of it.</Block>
        <Block>Only contributing earns standing — receiving an exchange earns none.</Block>
      </div>

      {/* Ledger. */}
      <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 10px 0' }}>
        Coherence-event ledger {ledger ? <span style={{ color: muted, fontWeight: 400 }}>· {ledger.count}</span> : null}
      </h2>
      <div style={{ fontSize: '13px', color: muted, marginBottom: '12px' }}>
        <Block>Every exchange this brain took part in, signed and append-only — rows are never edited or deleted.</Block>
      </div>

      {err && (
        <Card><div style={{ fontSize: '13px', color: '#c98080' }}>Could not load the ledger: {err}</div></Card>
      )}

      {!err && events.length === 0 && (
        <Card>
          <div style={{ fontSize: '13px', color: muted }}>
            <Block>No coherence events recorded on this brain yet.</Block>
            <Block>An event is written only when a contribution genuinely reaches another brain and is relevant and new — never for a file sitting in storage.</Block>
          </div>
        </Card>
      )}

      {!err && events.length > 0 && (
        <Card style={{ padding: '0', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{
              width: '100%', borderCollapse: 'collapse',
              fontSize: '12px', fontFamily: 'var(--font-mono)',
            }}>
              <thead>
                <tr style={{ color: muted, textAlign: 'left' }}>
                  {['when (UTC)', 'role', 'score', 'cos', 'sin', 'peer', 'content hash'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {events.map(ev => (
                  <tr key={ev.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '9px 12px' }}>{fmtTime(ev.event_timestamp)}</td>
                    <td style={{ padding: '9px 12px', color: ev.role === 'contributor' ? 'var(--accent)' : muted }}>{ev.role}</td>
                    <td style={{ padding: '9px 12px' }}>{Number(ev.score).toFixed(6)}</td>
                    <td style={{ padding: '9px 12px', color: muted }}>{Number(ev.cos).toFixed(4)}</td>
                    <td style={{ padding: '9px 12px', color: muted }}>{Number(ev.sin).toFixed(4)}</td>
                    <td style={{ padding: '9px 12px', color: muted }}>{(ev.peer_pubkey || '—').slice(0, 10)}…</td>
                    <td style={{ padding: '9px 12px', color: muted }}>{(ev.content_hash || '').slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <h2 style={{ fontSize: '16px', fontWeight: 700, margin: '28px 0 10px 0' }}>What this is not</h2>
      <div style={{ fontSize: '13px', color: muted, marginBottom: '8px' }}>
        <Block>Harmonics is not a coin, a token, a wallet, or a currency.</Block>
        <Block>The closest honest comparison is a reputation, or an academic citation record.</Block>
        <Block>It is accumulated recognition tied to specific, verifiable exchanges that actually happened.</Block>
      </div>
    </div>
  )
}
