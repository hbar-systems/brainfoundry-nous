import Head from 'next/head'

const SHIPPED = [
  { title: 'Chat ↔ RAG retrieval (layer-filtered)', detail: 'Chat now queries identity / thinking / projects / writing layers and injects retrieved chunks into context.' },
  { title: 'BYOK as default — Anthropic / OpenAI / Groq', detail: 'Buyer pastes API key, brain calls provider directly, you pay at-cost. Sovereignty mode (local Ollama) still available.' },
  { title: 'Personalized brain persona at provision', detail: 'Each brain ships with [BRAIN_NAME] and [OWNER_NAME] pre-substituted in the system prompt — no day-one [PLACEHOLDERS].' },
  { title: 'Self-service updates — `nous update` / `update_brain.sh`', detail: 'One command pulls latest from public template, rebuilds, health-checks, restores config on failure. Volumes persist.' },
  { title: 'Hardening at first boot — automatic', detail: 'SSH cipher pinning, fail2ban, ufw, sysctl hardening, login banner, 127.0.0.1 port binding, all applied via cloud-init.' },
  { title: 'SOVEREIGN_SECURITY_GUIDE.md', detail: 'Operator security reference shipped with every brain. Honest disclosure of access layers + how to close each.' },
  { title: 'Federation handshake (ED25519 signed)', detail: 'Each brain has an ED25519 keypair. Inbound federation requests are signature-verified and logged in BrainKernel audit.' },
]

const IN_PROGRESS = [
  { title: 'Wall of Brains — public federation display', detail: 'Opt-in social surface listing brains by handle + bio + last-seen. Federation works without it; the Wall is discovery, not requirement.' },
]

const PLANNED = [
  { title: 'Image persistence (currently ephemeral)', detail: 'Images you attach in chat are sent to the model and shown in the current session, but not stored. Reload removes them. Consolidation never sees image content. v0.8 will persist images locally on your brain (your data, your server) so reload preserves visual context and episodic memory can reference past images.' },
  { title: 'Plain-language admin / code-edit panel', detail: 'Adjust brain behavior in plain English — no Docker, no SSH. "Your brain, your rules" UI for non-technical operators.' },
  { title: 'Identity-first onboarding wizard', detail: 'New buyers get walked through: drop an identity doc first, then chat. No more landing on Knowledge upload cold.' },
  { title: 'Approval queue UI', detail: 'Governance kernel proposes memory writes; explicit approve/reject UI in the Knowledge tab.' },
  { title: 'Rename / delete chat sessions', detail: 'Basic affordances missing today.' },
  { title: 'Memory-layer "select structure" feature', detail: 'After your brain reads enough, it proposes an organization scheme. You pick it, an alternative, or "no structure". Self-organizing minds, not forced taxonomies.' },
  { title: 'Build-your-brain extensions', detail: 'Write a Python/JS module in extensions/brain/, register it as a tool, brain exposes it in chat. Code-as-capability.' },
  { title: '2FA on SSH for buyer brains', detail: 'Optional second factor on SSH for buyers who want it. Default stays key-only.' },
  { title: 'Hetzner Cloud project transfer (Premium tier)', detail: 'White-glove handoff: server moves to your Hetzner account, you hold the infrastructure API token, full Layer-3 sovereignty.' },
  { title: 'Brain-to-brain messaging board', detail: 'Once federation is live across multiple brains, a public log of inter-brain exchanges (opt-in per brain).' },
]

function StatusBadge({ status }) {
  const colors = {
    SHIPPED: { bg: '#1e3a26', text: '#7fc99c', label: 'shipped' },
    IN_PROGRESS: { bg: '#3a3520', text: '#d4b86a', label: 'in progress' },
    PLANNED: { bg: '#2a2420', text: '#8b7d6e', label: 'planned' },
  }
  const c = colors[status]
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      backgroundColor: c.bg,
      color: c.text,
      fontSize: '11px',
      fontFamily: 'DM Mono, ui-monospace, monospace',
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      borderRadius: '4px',
      marginRight: '12px',
      verticalAlign: 'middle',
    }}>{c.label}</span>
  )
}

function FeatureRow({ status, title, detail }) {
  return (
    <li style={{
      padding: '14px 0',
      borderBottom: '1px solid #2a2420',
      listStyle: 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '6px', marginBottom: '4px' }}>
        <StatusBadge status={status} />
        <span style={{ fontSize: '15px', color: '#e8e0d5', fontWeight: 500 }}>{title}</span>
      </div>
      <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#8b7d6e', lineHeight: '1.55' }}>{detail}</p>
    </li>
  )
}

export default function Future() {
  return (
    <>
      <Head><title>Future · BrainFoundry</title></Head>
      <div style={{ padding: '40px 32px', maxWidth: '900px', margin: '0 auto', fontFamily: 'Lora, ui-serif, serif' }}>

        <div style={{ marginBottom: '12px' }}>
          <p style={{ color: '#c9a96e', fontSize: '11px', letterSpacing: '0.15em', textTransform: 'uppercase', fontFamily: 'DM Mono, monospace', margin: '0 0 6px 0' }}>
            brainfoundry-nous · roadmap
          </p>
          <h1 style={{ fontSize: '32px', color: '#e8e0d5', margin: '0 0 6px 0', fontWeight: 600 }}>
            What&apos;s coming next
          </h1>
          <p style={{ color: '#8b7d6e', fontSize: '14px', margin: '0 0 32px 0' }}>
            Your brain runs on a public, open-source codebase. This is the live roadmap — what shipped, what&apos;s being built, and what&apos;s waiting in line.
          </p>
        </div>

        {/* Community contribution callout */}
        <div style={{
          padding: '18px 22px',
          backgroundColor: '#1c1814',
          border: '1px solid #c9a96e40',
          borderRadius: '10px',
          marginBottom: '40px',
        }}>
          <p style={{ color: '#e8e0d5', fontSize: '14px', margin: '0 0 8px 0', fontWeight: 500 }}>
            BrainFoundry is a public AI project.
          </p>
          <p style={{ color: '#8b7d6e', fontSize: '13px', lineHeight: '1.6', margin: 0 }}>
            Want to contribute, suggest a feature, or build something custom on top? The brain template is open source at{' '}
            <a href="https://github.com/hbar-systems/brainfoundry-nous" target="_blank" rel="noreferrer" style={{ color: '#c9a96e', textDecoration: 'underline' }}>
              github.com/hbar-systems/brainfoundry-nous
            </a>{' '}
            — fork it, file issues, or email{' '}
            <a href="mailto:hello@hbar.systems?subject=contribute" style={{ color: '#c9a96e', textDecoration: 'underline' }}>
              hello@hbar.systems
            </a>
            . Your friction is our roadmap.
          </p>
        </div>

        {/* Shipped */}
        <section style={{ marginBottom: '40px' }}>
          <h2 style={{ fontSize: '18px', color: '#e8e0d5', margin: '0 0 12px 0', fontWeight: 600 }}>Shipped</h2>
          <ul style={{ padding: 0, margin: 0 }}>
            {SHIPPED.map((f, i) => <FeatureRow key={`s${i}`} status="SHIPPED" title={f.title} detail={f.detail} />)}
          </ul>
        </section>

        {/* In progress */}
        <section style={{ marginBottom: '40px' }}>
          <h2 style={{ fontSize: '18px', color: '#e8e0d5', margin: '0 0 12px 0', fontWeight: 600 }}>In progress</h2>
          <ul style={{ padding: 0, margin: 0 }}>
            {IN_PROGRESS.map((f, i) => <FeatureRow key={`i${i}`} status="IN_PROGRESS" title={f.title} detail={f.detail} />)}
          </ul>
        </section>

        {/* Planned */}
        <section style={{ marginBottom: '40px' }}>
          <h2 style={{ fontSize: '18px', color: '#e8e0d5', margin: '0 0 12px 0', fontWeight: 600 }}>Planned</h2>
          <ul style={{ padding: 0, margin: 0 }}>
            {PLANNED.map((f, i) => <FeatureRow key={`p${i}`} status="PLANNED" title={f.title} detail={f.detail} />)}
          </ul>
        </section>

        {/* Footer */}
        <p style={{ color: '#6b5f52', fontSize: '12px', textAlign: 'center', marginTop: '60px', fontStyle: 'italic' }}>
          This roadmap lives in the open. Last updated 2026-04-29.
        </p>

      </div>
    </>
  )
}
