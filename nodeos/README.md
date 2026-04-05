# NodeOS Authority Service - Phase 1

## Overview

NodeOS is the authority service for the BrainFoundryOS brain system. It enforces:

1. **Memory Authority**: Only NodeOS can commit long-term memory
2. **Loop Permits**: Agents must request explicit autonomy permits
3. **Audit Trail**: All permits, denials, and memory decisions are logged

## Architecture

- **FastAPI** service running on port 8001 (internal, bound to `127.0.0.1`)
- **SQLite** database for permits, memory proposals, and audit events
- **HMAC-signed tokens** for permit authentication
- **No browser proxy.** NodeOS is reachable only from inside the Docker network.
  The brain API (`api` container) is the sole legitimate caller. Browser clients
  do not talk to NodeOS directly.

## Identity

```yaml
brain_id: system.ops.nodeos.v1
display_name: "NodeOS (authority)"
lineage: system
domain: ops
role: authority
```

## Endpoints

### Core Endpoints

- `GET /v1/identity` - NodeOS identity
- `GET /health` - Health check

### Loop Permits

- `POST /v1/loops/request` - Request a loop permit
- `POST /v1/loops/revoke` - Revoke a permit
- `GET /v1/loops/status/{permit_id}` - Check permit status

### Memory Management

- `POST /v1/memory/propose` - Propose memory for storage (default: PENDING)
- `POST /v1/memory/{proposal_id}/decide` - Approve/reject memory proposal
- `GET /v1/memory/proposals` - List memory proposals

### Audit

- `GET /v1/audit/events` - Retrieve audit events (filterable)

## Database Schema

### loop_permits
- `permit_id` (PK)
- `node_id`
- `agent_id`
- `loop_type`
- `ttl_seconds`
- `reason`
- `expires_at_unix`
- `status` (ACTIVE, REVOKED)
- `created_at`, `revoked_at`, `revoke_reason`

### memory_proposals
- `proposal_id` (PK)
- `permit_id`
- `memory_type`
- `content`
- `source_refs` (JSON)
- `status` (PENDING, APPROVED, REJECTED)
- `created_at`, `decided_at`, `decision_reason`

### audit_events
- `event_id` (PK)
- `event_type` (LOOP_PERMIT, MEMORY_PROPOSAL)
- `agent_id`
- `resource_id`
- `action` (REQUEST, REVOKE, PROPOSE, DECIDE)
- `outcome` (GRANTED, DENIED, SUCCESS, PENDING, APPROVED, REJECTED)
- `metadata` (JSON)
- `timestamp`

## Usage Examples

### Request a Loop Permit

```bash
curl -X POST http://localhost:8001/v1/loops/request \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "my-brain-01",
    "agent_id": "my-agent.v1",
    "loop_type": "research",
    "ttl_seconds": 1800,
    "reason": "Research assistant loop"
  }'
```

Response:
```json
{
  "permit_id": "uuid-here",
  "permit_token": "uuid.hmac-signature",
  "node_id": "my-brain-01",
  "agent_id": "my-agent.v1",
  "loop_type": "research",
  "reason": "Research assistant loop",
  "expires_at_unix": 1700000000,
  "status": "ACTIVE"
}
```

### Propose Memory

```bash
curl -X POST http://localhost:8001/v1/memory/propose \
  -H "Content-Type: application/json" \
  -d '{
    "permit_id": "<permit_id from loop request>",
    "memory_type": "preference",
    "content": "User prefers concise, modern language",
    "source_refs": {"confidence": 0.95}
  }'
```

### Approve Memory Proposal

```bash
curl -X POST http://localhost:8001/v1/memory/{proposal_id}/decide \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVE",
    "decided_by": "operator",
    "note": "High confidence user preference"
  }'
```

### View Audit Events

```bash
# All events
curl http://localhost:8001/v1/audit/events

# Filter by event type
curl "http://localhost:8001/v1/audit/events?event_type=LOOP_PERMIT"

# Filter by agent
curl "http://localhost:8001/v1/audit/events?agent_id=my-agent.v1&limit=50"
```

## Access model

NodeOS is an **internal-only service**. It has no browser-facing proxy and
binds only to `127.0.0.1:8001` on the host. The only legitimate caller is the
brain `api` container on the Docker network.

All state-mutating endpoints (permit request/revoke, memory propose/decide,
action propose/decide) additionally require an `X-Internal-Key` header matching
`NODEOS_INTERNAL_KEY`. The brain API forwards this header automatically when it
calls NodeOS. Requests without the header are rejected `401`.

## Security Notes

- `NODEOS_SIGNING_SECRET` (HMAC) and `NODEOS_INTERNAL_KEY` (service-to-service
  auth) are required. In `BRAIN_ENV=prod`, NodeOS refuses to start if either is
  unset or left at a default value.
- Permit tokens are HMAC-signed (not encrypted) — do not log them.
- SQLite database is volume-mounted for persistence at `/data/nodeos.db`.

## Development

### Build and Run

```bash
# Development mode (nodeos exposed on port 8001)
docker compose -f docker-compose.dev.yml up -d nodeos

# Production mode (internal only)
docker compose up -d nodeos
```

### View Logs

```bash
docker compose logs -f nodeos
```

### Access Database

```bash
docker compose exec nodeos sqlite3 /data/nodeos.db
```

## Phase 2 Enhancements (Future)

- Admin authentication for memory decisions
- Token encryption (not just HMAC)
- PostgreSQL migration option
- Permit usage tracking (iteration count)
- Automatic permit expiration cleanup
- Memory proposal auto-approval rules
- Webhook notifications for audit events
