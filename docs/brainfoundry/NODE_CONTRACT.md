# BrainFoundry Node Runtime Contract

**Version:** 0.1.0  
**Status:** Future Specification — describes the target protocol, NOT the current implementation

> **Note for brainfoundry-nous users:** This document is a protocol design spec for the BrainFoundry federation protocol (target: v1.0). The current brainfoundry-nous implementation (v0.6.x) is a subset. The table below maps contract terms to current env var names.
>
> | Contract term | Current env var / behaviour |
> |---|---|
> | `NODE_ID` | `BRAIN_ID` |
> | `POLICY_MODE` (sealed/standard/dev) | `BRAIN_ENV` (prod/dev) |
> | `API_KEY` | `BRAIN_API_KEY` |
> | `RUNTIME_VERSION` | Hardcoded as `BRAIN_VERSION` in `api/main.py` |
> | `/ready` body | `{ "ok": bool, "model": { "loaded": bool, "error": str } }` |
>
> Everything below is aspirational protocol design. Implementation will converge toward it over time.

---

This document defines the minimal interface that any BrainFoundry node runtime MUST expose. This contract prevents divergent implementations and ensures all nodes can participate in the federated network.

---

## Required Endpoints

All node runtimes must expose the following HTTP endpoints:

### `GET /health`

**Purpose:** Basic liveness check  
**Response:** `200 OK` if node process is running  
**Body:** `{ "status": "ok" }`

**Contract:**
- MUST respond within 1 second
- MUST return 200 if process is alive
- No authentication required

### `GET /ready`

**Purpose:** Readiness check (can accept traffic)  
**Response:** `200 OK` if node is ready to serve requests  
**Body:** `{ "status": "ready", "node_id": "<id>", "version": "<version>" }`

**Contract:**
- MUST respond within 2 seconds
- MUST return 200 only if all dependencies are available
- MUST include node_id and runtime version
- No authentication required

### `POST /chat/completions`

**Purpose:** OpenAI-compatible chat completions endpoint  
**Request:** OpenAI chat completions format  
**Response:** OpenAI chat completions response format

**Contract:**
- MUST accept OpenAI-compatible request format
- MUST return OpenAI-compatible response format
- MUST respect policy_mode restrictions
- MUST require authentication (except in dev mode)
- MUST log all requests (audit trail)

---

## Execution Modes

Every node runtime MUST support three execution modes, controlled by `policy_mode`:

### `sealed`

- **Authentication:** Required (API key or mTLS)
- **Logging:** Full audit trail, encrypted at rest
- **Model access:** Restricted to allowed_models list
- **Rate limiting:** Enforced per policy
- **Data retention:** Minimal, encrypted
- **External calls:** Blocked by default

### `standard`

- **Authentication:** Required (API key)
- **Logging:** Standard logging, 30-day retention
- **Model access:** Configurable allowed_models
- **Rate limiting:** Enforced per policy
- **Data retention:** Standard retention policy
- **External calls:** Allowed with logging

### `dev`

- **Authentication:** Optional (can be disabled)
- **Logging:** Verbose, local only
- **Model access:** No restrictions
- **Rate limiting:** Relaxed or disabled
- **Data retention:** Ephemeral
- **External calls:** Allowed without restrictions

**Invariant:** A node MUST NOT switch from `sealed` to `dev` without explicit operator intervention and registry update.

---

## Required Environment Variables

All node runtimes MUST accept these environment variables:

### Core Configuration

- `NODE_ID` — Unique node identifier (must match registry)
- `POLICY_MODE` — Execution mode: `sealed` | `standard` | `dev`
- `RUNTIME_VERSION` — Runtime version tag (e.g., `node-v0.1.0`)

### Network

- `PORT` — HTTP port to listen on (default: 3000)
- `HOST` — Host to bind to (default: 0.0.0.0)

### Authentication

- `API_KEY` — Primary API key (required in sealed/standard modes)
- `API_KEY_SECONDARY` — Optional secondary key for rotation

### Logging

- `LOG_LEVEL` — Logging verbosity: `debug` | `info` | `warn` | `error`
- `LOG_RETENTION_DAYS` — Log retention period (default: 30)

### Model Access

- `ALLOWED_MODELS` — Comma-separated list of allowed model IDs
- `DEFAULT_MODEL` — Default model if not specified in request

### Optional

- `DOMAIN` — Public domain for this node (if applicable)
- `DEPLOY_TARGET` — Deployment target: `local` | `hetzner` | `runpod` | `other`

---

## Logging Invariants

All node runtimes MUST:

1. **Log all requests** — Every `/chat/completions` request must be logged with:
   - Timestamp (ISO 8601)
   - Node ID
   - Request ID (unique)
   - Model used
   - Token counts (prompt + completion)
   - Response status

2. **Audit trail** — In `sealed` mode, logs must be:
   - Encrypted at rest
   - Tamper-evident (append-only or signed)
   - Retained per policy (minimum 30 days)

3. **No PII in logs** — User messages must NOT be logged in plaintext in `sealed` mode

4. **Structured logging** — All logs must be JSON-formatted for machine parsing

---

## Data Policy Expectations

### Data Boundaries

- **Federated nodes:** May share aggregated metrics (token counts, model usage) with registry, but NEVER user data
- **Sovereign nodes:** Keep all data local, no telemetry sharing

### Data Retention

- **Request logs:** Retained per `LOG_RETENTION_DAYS` setting
- **User data:** Ephemeral by default (not stored beyond request lifecycle)
- **Model outputs:** Not persisted unless explicitly configured

### Encryption

- **In transit:** All external communication MUST use TLS 1.3+
- **At rest:** Logs and any persisted data MUST be encrypted in `sealed` mode

---

## Versioning Contract

### Runtime Versions

- Runtime versions MUST follow semantic versioning: `node-vMAJOR.MINOR.PATCH`
- Breaking changes MUST increment MAJOR version
- New features MUST increment MINOR version
- Bug fixes MUST increment PATCH version

### Instance Pinning

- Each node instance MUST declare its `runtime_version` in registry
- Instances MUST NOT auto-upgrade across MAJOR versions
- Instances MAY auto-upgrade PATCH versions (security fixes)

---

## Compliance Checklist

A valid node runtime implementation MUST:

- [ ] Expose `/health`, `/ready`, `/chat/completions` endpoints
- [ ] Support all three execution modes (`sealed`, `standard`, `dev`)
- [ ] Accept all required environment variables
- [ ] Log all requests with required fields
- [ ] Respect policy_mode restrictions
- [ ] Encrypt logs in sealed mode
- [ ] Follow semantic versioning
- [ ] Respond to health checks within timeout

---

## Future Extensions

This contract may be extended to include:

- `/metrics` endpoint (Prometheus-compatible)
- `/admin/*` endpoints for node management
- WebSocket support for streaming responses
- Multi-model routing
- Federated query routing

All extensions MUST be backward-compatible or require MAJOR version bump.

---

**Contract Version:** 0.1.0  
**Last Updated:** 2026-02-03  
**Status:** Future specification — see note at top for current implementation mapping
