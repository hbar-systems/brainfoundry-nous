import { useEffect, useState } from 'react'
import MessageRenderer from '../lib/MessageRenderer'

// Documentation of the brain's RAG + chat architecture. Written as markdown
// + embedded mermaid diagrams so it flows through the same renderer as
// chat messages — themes, fonts, code-highlight, math, diagrams all work
// here automatically. Updates to this doc are markdown edits, not JSX.

const ARCHITECTURE_DOC = `
# How this brain thinks

This is a sovereign personal brain running on BrainFoundryOS. It does three things: stores knowledge, retrieves what's relevant for a question, and uses an LLM to write the answer grounded in that knowledge.

## End-to-end flow

\`\`\`mermaid
graph TD
    Operator -->|message| API
    API -->|loads| Persona[Persona system-prompt]
    API -->|semantic search| RAG[Vector store]
    Persona --> Prompt[Assembled prompt]
    RAG --> Prompt
    History[Session history] --> Prompt
    Prompt --> Model[LLM provider]
    Model -->|streamed tokens| Operator
    Model -->|saved| DB[Postgres]
    DB -->|rehydrate| History
\`\`\`

Every operator message goes through this loop. The persona file is the system prompt, the vector store contributes retrieved context, the prior session messages are replayed for continuity, and the model writes the next message.

## Ingestion pipeline

When you upload a document, the brain does this:

\`\`\`mermaid
graph LR
    Upload[File / paste] -->|extract text| Text
    Text -->|chunk| Chunks
    Chunks -->|embed| Vectors
    Vectors -->|tag layer| Store[(document_embeddings)]
\`\`\`

| Stage | What happens |
| --- | --- |
| **Extract** | PDF → text via PyPDF; .docx → python-docx; .md / .txt go straight in |
| **Chunk** | Long text split into overlapping segments (configurable; default ~500 tokens) |
| **Embed** | Each chunk → vector via the embedding model configured in the api container |
| **Layer-tag** | Each chunk gets a layer label so retrieval can scope which parts of the brain answer |
| **Store** | pgvector column in Postgres \`document_embeddings\` table |

## Layers

Layers are how the brain partitions its memory. Different chats see different layers.

| Layer | What it holds | Who can read it |
| --- | --- | --- |
| **public** | Knowledge intentionally exposed to anyone visiting the public node | Public chat (rate-limited, no API key) |
| **private** | Operator's documents — research, writing, projects, anything tagged private at upload | Operator chat (API-key gated) |
| **episodic** | Consolidated past conversations — created by clicking "Save to memory" on a session | Operator chat (when episodic recall is enabled) |

Public-chat retrieval is hard-coded to \`layers=["public"]\` — it cannot accidentally surface private documents even if the API tries.

## Retrieval

\`\`\`mermaid
graph LR
    Query[User message] -->|embed| QV[Query vector]
    QV -->|cosine top-k| Hits[Top-k chunks]
    Hits -->|filter by layer| Filtered
    Filtered -->|inject as context| Prompt
\`\`\`

The query is embedded in the same vector space as the documents. Cosine similarity ranks the top-k matches. Operator chat can pass an explicit layer list; public chat is locked to public.

## Generation

The final prompt the model sees is assembled in order:

1. **System prompt** — the persona file (\`api/brain_persona.md\` for operator chat, \`brain_persona_nous.md\` for the public node)
2. **Vendor-disavowal turn-prefix** — if the user message names a centralized AI vendor, a forced "I am not X" instruction is prepended (defends sovereign identity from confused queries on small models)
3. **Retrieved documents** — the top-k chunks from RAG, prefixed by layer context
4. **Conversation history** — prior turns of this session
5. **The current user message**

The model's reply streams back as Server-Sent Events. Each token is appended to the assistant message in the UI, persisted to Postgres on stream close.

## Storage

| Component | Where | What |
| --- | --- | --- |
| Sessions | Postgres \`chat_sessions\` | session_id, title, created_at, model_name |
| Messages | Postgres \`chat_messages\` | session_id, role, content, created_at |
| Documents | Postgres \`document_embeddings\` | chunks, vectors, layer, document_name |
| Federation peers | \`api/identity/known_peers.toml\` | trusted brain endpoints + their pubkeys |
| Persona | \`api/brain_persona.md\` (operator-edited) | the brain's system prompt — governance artifact |
| Identity | \`api/brain_identity.yaml\` + on-disk ED25519 keypair | brain handle + signing key for federation |

## Endpoint surface

All chat / data routes are on the API host (\`yury.brainfoundry.ai\`, no \`console.\` prefix):

| Route | Method | What it does |
| --- | --- | --- |
| \`/health\` | GET | Service health (db, ollama, embeddings) — always public |
| \`/identity\` | GET | Brain handle + version + pubkey — always public |
| \`/chat/completions\` | POST | Operator chat (OpenAI-compatible, streaming) — API key gated |
| \`/v1/public/chat\` | POST | Public chat — no key, per-IP rate limited, locked to public layer |
| \`/sessions\` | GET / POST | List + create chat sessions |
| \`/sessions/{id}\` | DELETE | Delete a session |
| \`/sessions/{id}/title\` | PUT | Rename a session |
| \`/sessions/{id}/messages\` | GET | Replay a saved session |
| \`/chat/sessions/{id}/consolidate\` | POST | Compact a chat into an episodic memory |
| \`/documents/upload\` | POST | Add a document to the vector store |
| \`/v1/federation/assertion\` | GET | Federation handshake — always public |

The full API uses OpenAI-compatible request shape so any client that talks to OpenAI can talk to this brain by changing only the endpoint and API key.
`

export default function Architecture() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetch('/api/bf/health')
      .then(r => r.ok ? r.json() : null)
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <div style={{
      maxWidth: '880px',
      margin: '0 auto',
      padding: '40px 32px 80px',
      color: 'var(--text)',
      fontFamily: 'var(--font-body)',
      lineHeight: 1.6,
    }}>
      <MessageRenderer content={ARCHITECTURE_DOC} />

      {health && (
        <div style={{
          marginTop: '32px',
          padding: '20px 24px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '12px',
        }}>
          <h3 style={{
            margin: '0 0 12px 0',
            fontFamily: 'var(--font-display)',
            fontSize: '1.08em',
            fontWeight: 600,
          }}>
            Live status (this brain, right now)
          </h3>
          <pre style={{
            margin: 0,
            padding: '12px 14px',
            background: 'var(--code-bg)',
            color: 'var(--code-fg)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.85em',
            overflowX: 'auto',
          }}>{JSON.stringify(health, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
