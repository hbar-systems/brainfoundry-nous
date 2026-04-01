# hbar-brain

Canonical brain node for the hbar systems network. A containerized private LLM assistant with document processing, vector search, RAG capabilities, and **NodeOS authority-governed memory**.

Built with FastAPI, Next.js, PostgreSQL + pgvector, Ollama, and the NodeOS Authority Service.

> **Governed by**: [`NODEOS_V0_CANON`](../../docs/NODEOS_V0_CANON.md)
> **Organization**: [hbar-systems](https://github.com/hbar-systems)

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Next.js UI    │    │   FastAPI API    │    │     Ollama      │
│   Port: 3010    │◄──►│   Port: 8010    │◄──►│   Port: 11435   │
└─────────────────┘    └────────┬────────┘    └─────────────────┘
        │                       │
        │              ┌────────▼────────┐
        │              │   PostgreSQL    │
        │              │   + pgvector    │
        │              │   Port: 54332   │
        │              └─────────────────┘
        │
        └─────►┌─────────────────┐
               │  NodeOS Authority│
               │  Port: 8011      │
               │  (SQLite)        │
               └─────────────────┘
```

### Services

- **API** (`api/`) -- FastAPI backend: chat, RAG, document upload, embeddings
- **NodeOS** (`nodeos/`) -- Authority service: loop permits, memory proposals, audit trail
- **UI** (`ui/`) -- Next.js frontend with NodeOS proxy routes
- **PostgreSQL** -- pgvector for document embeddings and chat sessions
- **Ollama** -- Local LLM inference

## Memory Governance

Document embeddings are classified as **long-term memory** under NodeOS canon. The `/documents/upload` endpoint enforces **deny-by-default** memory governance:

1. **No `proposal_id`** -- API proposes memory to NodeOS, returns `202 PENDING`. No embeddings written.
2. **`proposal_id` provided, not APPROVED** -- Returns `403 Forbidden`. No embeddings written.
3. **`proposal_id` APPROVED** -- Embeddings are written to PostgreSQL.
4. **NodeOS unreachable** -- Returns `503`. Fail closed. No embeddings written.

### Upload Flow

```bash
# Step 1: Get a loop permit
curl -X POST http://localhost:8011/v1/loops/request \
  -H "Content-Type: application/json" \
  -d '{"node_id":"brain-01","agent_id":"user","loop_type":"admin","ttl_seconds":300,"scopes":["write:documents"],"reason":"Upload document"}'

# Step 2: Upload file (returns 202 + proposal_id)
curl -X POST "http://localhost:8010/documents/upload?permit_id=<PERMIT_ID>" \
  -F "file=@document.pdf"

# Step 3: Approve the proposal
curl -X POST "http://localhost:8011/v1/memory/<PROPOSAL_ID>/decide" \
  -H "Content-Type: application/json" \
  -d '{"decision":"APPROVE","decided_by":"admin","note":"Approved"}'

# Step 4: Re-upload with approved proposal_id (returns 200, embeddings written)
curl -X POST "http://localhost:8010/documents/upload?proposal_id=<PROPOSAL_ID>" \
  -F "file=@document.pdf"
```

## Quick Start

```bash
# Clone
git clone https://github.com/hbar-systems/hbar-brain.git
cd hbar-brain

# Configure
cp .env.example .env

# Start (development mode -- lighter models)
docker compose -f docker-compose.dev.yml up -d

# Pull a model
docker compose exec ollama ollama pull llama3.2:1b

# Verify
curl http://localhost:8010/health
curl http://localhost:8011/health
```

## Compose Modes

| Mode | File | Default Model | Best For |
|------|------|---------------|----------|
| **Production** | `docker-compose.yml` | llama3.2:1b | Standard deployment |
| **Development** | `docker-compose.dev.yml` | llama3.2:1b | Dev/testing (exposed ports) |
| **Minimal** | `docker-compose.minimal.yml` | Disabled | API testing only (no LLM) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API info and status |
| `/health` | GET | Service health check |
| `/identity` | GET | Brain identity (YAML as JSON) |
| `/capabilities` | GET | Brain capabilities |
| `/persona` | GET | Loaded persona text |
| `/models` | GET | Available LLM models |
| `/chat/completions` | POST | OpenAI-compatible chat (streaming supported) |
| `/chat/rag` | POST | Document-based Q&A |
| `/documents/upload` | POST | Upload documents (NodeOS-gated) |
| `/documents/search` | POST | Vector similarity search |
| `/documents/stats` | GET | Document storage statistics |
| `/sessions` | GET | List chat sessions |
| `/sessions` | POST | Create chat session |
| `/sessions/{id}` | DELETE | Delete chat session |
| `/sessions/{id}/messages` | GET | Get session messages |
| `/sessions/{id}/title` | PUT | Update session title |
| `/brain/tags` | GET | List semantic tags |
| `/brain/docs` | GET | Filter docs by tags |

## NodeOS Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | NodeOS health |
| `/v1/identity` | GET | NodeOS identity |
| `/v1/loops/request` | POST | Request loop permit |
| `/v1/loops/status/{permit_id}` | GET | Check permit status |
| `/v1/loops/revoke` | POST | Revoke permit (permit_id in body) |
| `/v1/memory/propose` | POST | Propose memory write |
| `/v1/memory/proposals` | GET | List proposals |
| `/v1/memory/proposals/{proposal_id}` | GET | Get single proposal |
| `/v1/memory/{proposal_id}/decide` | POST | Approve/deny proposal |
| `/v1/audit/events` | GET | Query audit trail |

## Project Structure

```
hbar-brain/
├── api/                        # FastAPI backend
│   ├── main.py                 # API server + memory governance gate
│   ├── brain_identity.yaml     # Brain identity definition
│   ├── brain_persona.md        # Persona prompt
│   ├── requirements.txt
│   └── Dockerfile
├── nodeos/                     # NodeOS Authority Service
│   ├── main.py                 # Authority server (permits, proposals, audit)
│   ├── brain_identity.yaml     # NodeOS identity
│   ├── test_nodeos.sh          # Endpoint tests
│   ├── test_contract.sh        # Contract verification
│   ├── requirements.txt
│   └── Dockerfile
├── ui/                         # Next.js frontend
│   ├── pages/
│   │   ├── api/bf/             # API proxy routes
│   │   ├── api/nodeos/         # NodeOS proxy (with denylist)
│   │   ├── chat.js
│   │   ├── upload.js
│   │   └── upload-search.js
│   └── Dockerfile
├── vector-db/
│   └── init.sql                # PostgreSQL + pgvector schema
├── extensions/brain/           # Semantic layer (SQLite)
├── scripts/                    # Utilities and tools
│   ├── test_memory_gate.sh     # Memory governance smoke test
│   ├── ingest_folder.py
│   ├── planner.py
│   └── ...
├── hbar-brain-template/        # Template scaffold for new brain nodes
├── docker-compose.yml          # Production
├── docker-compose.dev.yml      # Development
├── docker-compose.minimal.yml  # Minimal / API-only
├── NODEOS_INTEGRATION.md
├── NODEOS_SUMMARY.md
└── README.md
```

## Testing

### Memory Governance Smoke Test

```bash
# Requires services running (docker compose -f docker-compose.dev.yml up -d)
bash scripts/test_memory_gate.sh
```

Tests:
1. Upload without `permit_id` -- 400
2. Get loop permit from NodeOS
3. Upload with `permit_id` (no `proposal_id`) -- 202 PENDING
4. Upload with PENDING `proposal_id` -- 403
5. Approve proposal via NodeOS
6. Upload with APPROVED `proposal_id` -- 200 (embeddings written)
7. Verify audit trail

### NodeOS Contract Tests

```bash
bash nodeos/test_nodeos.sh
bash nodeos/test_contract.sh
```

## Development

```bash
# Rebuild a specific service
docker compose -f docker-compose.dev.yml build api

# View logs
docker compose -f docker-compose.dev.yml logs -f api nodeos

# Reset database
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d
```

## Canon Reference

This brain node operates under the governance rules defined in [`NODEOS_V0_CANON`](../../docs/NODEOS_V0_CANON.md). Key invariants enforced:

- **Memory**: No long-term persistence without NodeOS approval (deny-by-default)
- **Loop permits**: Agents must hold valid permits for elevated operations
- **Audit**: All authority decisions are logged
- **Fail closed**: If NodeOS is unreachable, all gated operations are denied

---

**hbar-systems** | [github.com/hbar-systems/hbar-brain](https://github.com/hbar-systems/hbar-brain)
