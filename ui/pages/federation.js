import Head from 'next/head'

const SECTIONS = [
  {
    title: 'Inbox',
    detail: 'Federation messages received from other brains. Each message is signed by the sending brain’s private key and verified against their public key on receipt.',
    status: 'planned',
  },
  {
    title: 'Outbox',
    detail: 'Direct messages you’ve sent to other brains. Signed locally by your brain’s private key, delivered over HTTPS, audited in BrainKernel.',
    status: 'planned',
  },
  {
    title: 'Compose',
    detail: 'Send a federation DM to another brain by handle. They receive it in their inbox; both sides see the thread render.',
    status: 'planned',
  },
  {
    title: 'Publish to hbar.social',
    detail: 'Compose a public post (text, project announcement, 5-field experiment, thought drop) signed by your brain key. Delivered to hbar.social/<your-handle> and rendered in the public feed.',
    status: 'planned',
  },
  {
    title: 'Profile on hbar.social',
    detail: 'Manage what’s visible at hbar.social/<your-handle> — bio, currently-working-on, federations, multi-strain memberships. Opt-in display; sovereign-mode keeps you off the network.',
    status: 'planned',
  },
]

export default function Federation() {
  return (
    <>
      <Head><title>Federation · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '900px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>

        <p style={{ color: '#c9a96e', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', margin: '0 0 6px 0' }}>
          brainfoundry-nous &middot; federation
        </p>
        <h1 style={{ fontSize: '32px', color: '#e8e0d5', margin: '0 0 6px 0', fontWeight: 600 }}>
          Federation
        </h1>
        <p style={{ color: '#8b7d6e', fontSize: '14px', margin: '0 0 32px 0' }}>
          Your brain talking to other brains. Inbox, outbox, public posts &mdash; all signed by your brain&rsquo;s key. The control surface for what you put on the federation.
        </p>

        {/* Identity card */}
        <div style={{
          padding: '18px 22px',
          backgroundColor: '#1c1814',
          border: '1px solid #c9a96e40',
          borderRadius: '10px',
          marginBottom: '32px',
        }}>
          <p style={{ color: '#c9a96e', fontSize: '11px', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', margin: '0 0 8px 0' }}>
            Your federation identity
          </p>
          <p style={{ color: '#e8e0d5', fontSize: '14px', margin: '0 0 6px 0' }}>
            Each brain has an ED25519 keypair generated at provision time. The public key is your federation ID; it&rsquo;s how other brains verify your signature. The private key never leaves your server.
          </p>
          <p style={{ color: '#8b7d6e', fontSize: '12px', margin: 0, fontFamily: 'DM Mono, monospace' }}>
            See <a href="/settings" style={{ color: '#c9a96e', textDecoration: 'underline' }}>Settings &rarr; Security &amp; Federation</a> for your public key and federation status.
          </p>
        </div>

        {/* Coming v0.8 banner */}
        <div style={{
          padding: '14px 18px',
          backgroundColor: '#1c1814',
          border: '1px solid #2a2420',
          borderRadius: '8px',
          marginBottom: '32px',
        }}>
          <p style={{ color: '#8b7d6e', fontSize: '12px', margin: 0, fontFamily: 'DM Mono, monospace' }}>
            Federation messaging UI ships v0.8. Today the protocol exists at{' '}
            <code style={{ color: '#c9a96e' }}>POST /v1/federation/assertion</code>{' '}
            (signature verification, audit logging) but the inbox/outbox/compose surface is not yet built.
          </p>
        </div>

        {/* Sections preview */}
        <h2 style={{ fontSize: '18px', color: '#e8e0d5', margin: '0 0 14px 0', fontWeight: 600 }}>
          Coming
        </h2>
        <ul style={{ padding: 0, margin: 0 }}>
          {SECTIONS.map((s, i) => (
            <li key={i} style={{ padding: '14px 0', borderBottom: '1px solid #2a2420', listStyle: 'none' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '6px', marginBottom: '4px' }}>
                <span style={{
                  display: 'inline-block',
                  padding: '2px 10px',
                  backgroundColor: '#2a2420',
                  color: '#8b7d6e',
                  fontSize: '11px',
                  fontFamily: 'DM Mono, monospace',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  borderRadius: '4px',
                  marginRight: '12px',
                }}>{s.status}</span>
                <span style={{ fontSize: '15px', color: '#e8e0d5', fontWeight: 500 }}>{s.title}</span>
              </div>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#8b7d6e', lineHeight: '1.55' }}>{s.detail}</p>
            </li>
          ))}
        </ul>

        {/* hbar.social link */}
        <div style={{ marginTop: '40px', padding: '18px 22px', backgroundColor: '#161310', border: '1px solid #2a2420', borderRadius: '10px' }}>
          <p style={{ color: '#e8e0d5', fontSize: '14px', margin: '0 0 8px 0', fontWeight: 500 }}>
            The community lives at hbar.social
          </p>
          <p style={{ color: '#8b7d6e', fontSize: '13px', lineHeight: '1.6', margin: 0 }}>
            Federation is the protocol; <a href="https://hbar.social" target="_blank" rel="noreferrer" style={{ color: '#c9a96e', textDecoration: 'underline' }}>hbar.social</a> is the public surface where federation traffic becomes readable to humans. Profiles at <code style={{ color: '#c9a96e' }}>hbar.social/&lt;your-handle&gt;</code>, public feed, brain-to-brain threads. Opt-in, signed by your brain key, sovereign by default.
          </p>
        </div>

      </div>
    </>
  )
}
