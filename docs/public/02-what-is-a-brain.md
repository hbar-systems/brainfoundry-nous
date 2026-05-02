# What is a brain

A brain is a personal AI node. It is a set of cooperating services running on a Linux server under docker compose, exposing an HTTP API and a web console. This document describes the architecture at the level you need to trust it.

## The six services

When you start a brain, `docker compose up -d` brings these up:

| Service | Role |
|---|---|
| `api` | FastAPI server — chat, retrieval, identity, federation, document management |
| `nodeos` | BrainKernel — governance kernel for permits, proposals, and audit log |
| `ui` | Next.js console — dashboard, chat, knowledge, settings, kernel inspector |
| `postgres` | PostgreSQL with pgvector — vector memory and document metadata |
| `ollama` | Local model runtime for inference without a cloud API |
| `redis` | Rate-limit store for the kernel |

Only the API and the console UI are exposed externally. The database, kernel, local inference, and rate limiter bind to localhost inside the Docker network.

## Memory

Memory is the reason the brain is worth having. The model is interchangeable; the accumulated context is not.

### Ingestion

A brain eats documents. The `scripts/ingest_folder.py` helper reads a directory tree, splits each file into token-bounded chunks with configurable overlap, embeds each chunk with a local sentence-transformer model, and writes the embeddings into PostgreSQL with metadata about the source file.

Re-running ingestion updates chunks in place. You can point a brain at a directory of notes, essays, PDFs, or exported vaults, and it will learn from them.

### Retrieval

Each chat turn runs a retrieval pass before prompting the model. The query is embedded, matched against the vector store with cosine similarity, and the top chunks are injected into the model's context alongside the brain's persona and the conversation history.

### Layers

The brain supports named memory layers. A layer is a tag on a chunk that gives it retrieval priority or lets you filter by it. Default layers:

| Layer | Priority | Intended use |
|---|---|---|
| `identity` | Highest — always retrieved | Who you are, principles, core context |
| `thinking` | High — one result always | Active notes and reasoning |
| `projects` | High — one result always | Current work |
| `writing` | High — one result always | Essays and published work |
| (everything else) | Similarity only | General corpus |

Layer names are configurable. If you do not use layers, the brain falls back to similarity search across the whole corpus.

## Persona

The persona file (`api/brain_persona.md`) is a plain-text description of the brain's owner — who you are, what you work on, how you think. It is injected as a system message on every chat turn.

The persona is what makes the brain yours before any document is ingested. A newly provisioned brain with a filled-in persona already knows enough to answer "who am I" and "what do I work on" before you upload a single file.

## Governance

Every mutation — remembering a new fact, forgetting a chunk, clearing audit state, pushing to a git repository, running an external tool — goes through a two-phase commit against BrainKernel.

**Phase one — PROPOSE.** The command is parsed, its intent is shown back with a plan and a risk assessment, and a single-use confirmation token is issued. Nothing has happened yet.

**Phase two — CONFIRM.** The same command is re-submitted with the token. The kernel verifies the token, checks the permit that authorizes the action, and only then mutates.

Read-only commands skip both phases and return immediately.

The next document in this series describes permits, execution classes, and the audit log in detail.

## Strains

A strain is a logical cognitive domain within a brain. It is a named scope that groups related memory, commands, and connectors.

Strains are declarative: each strain declares the commands it may request permits for, the connector namespaces it may read and write, and the data classes of its content (public, internal, sensitive, sealed). Strains do not grant themselves authority — every privileged action still goes through a permit issued by the kernel.

Strains are logical boundaries. Nodes are physical boundaries. A single brain can host many strains. Cross-strain sharing is deny-by-default and must be explicitly permitted.

## Model agnosticism

The brain routes requests by the `model` field of a chat request. Model names are prefix-matched to a provider: names starting with recognized prefixes route to the corresponding cloud API, and everything else routes to the local Ollama runtime.

You configure which providers your brain can use by adding API keys to `.env`. Providers without keys are hidden from the model selector. Local inference via Ollama is always available and requires no key.

The same conversation can switch models mid-session. Memory, persona, and governance are shared across all models — the brain you talk to is the same brain regardless of which model runs the forward pass.

## Identity

Every brain generates an ED25519 keypair at install. The private key stays on the server. The public key is published at `GET /identity` alongside the brain's ID, display name, owner, and supported capabilities.

This identity is how federation works — other brains verify your signatures by fetching your public key from your own endpoint.

## Runtime properties

- **Append-only audit log.** Every kernel command, every proposal, every confirmation, every model call is recorded. Existing log entries are never modified or deleted.
- **Fail-closed governance.** If the kernel is unreachable, mutations are refused. The chat path fails rather than silently bypassing governance.
- **Internal-only kernel.** BrainKernel binds to localhost inside the Docker network and requires a service-to-service key on all mutating routes. It is not exposed to browsers or the public internet.
- **Single-tenant.** The design is a single owner per node. Multi-tenancy is explicitly out of scope.
- **TLS at the edge.** The containers do not terminate TLS. You put a reverse proxy in front and issue certificates from a public certificate authority.

## What the brain is not

It is not a hosted SaaS product. There is no central API to call.

It is not a multi-tenant platform. You cannot carve up one brain among several users.

It is not a model. The brain uses models — swaps them freely — but the intelligence in the node is the organization of memory around the model, not the weights.

It is not a polished appliance. The reference implementation is fully usable but deliberately transparent: you can read every container, every script, every schema, and change any of them.
