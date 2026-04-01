# BrainFoundry Lifecycle Contract (v0.17)

This document defines the stable operator lifecycle API for BrainFoundry.

Base:
- Service binds locally: http://127.0.0.1:8090
- All non-health endpoints require x-operator-token header.

Authentication:
Header:
x-operator-token: <token>
Invalid or missing token returns 403.

Lifecycle availability:
If Docker daemon is unavailable, lifecycle endpoints return:
503 with detail "lifecycle disabled: ..."

------------------------------------------------------------

GET /health

Returns BrainFoundry health.

Response:
{"status":"ok","service":"brainfoundry"}

------------------------------------------------------------

GET /brains

Lists registered brains from registry.json.

Response:
{
  "brains": [
    {"brain_id":"hbar.brain.demo","service":"api_demo","port":8110}
  ]
}

------------------------------------------------------------

GET /brains?include_state=true

Adds state summary per brain:
- container_exists
- running
- reachable
- health_url
- health (only if reachable)

------------------------------------------------------------

POST /brains/{brain_id}/start

Idempotent semantics:
- already running  -> {"ok":true,"status":"already_running"}
- stopped exists   -> {"ok":true,"status":"resumed"}
- not created yet  -> {"ok":true,"status":"started"}

Errors:
404 not registered
409 lifecycle busy
503 lifecycle disabled
500 docker failure

------------------------------------------------------------

POST /brains/{brain_id}/stop

Idempotent semantics:
- already stopped -> {"ok":true,"status":"already_stopped"}
- running         -> {"ok":true,"status":"stopped"}

Errors:
404 not registered
409 lifecycle busy
503 lifecycle disabled
500 docker failure

------------------------------------------------------------

GET /brains/{brain_id}/status

Response:
{
  "brain_id":"hbar.brain.demo",
  "service":"api_demo",
  "registered": true,
  "container_exists": true,
  "running": true
}

------------------------------------------------------------

GET /brains/{brain_id}/healthcheck

Pings brain's /health endpoint.

Response (success):
{
  "brain_id":"hbar.brain.demo",
  "url":"http://127.0.0.1:8110/health",
  "reachable":true,
  "response":{"status":"ok"}
}

------------------------------------------------------------

DELETE /brains/{brain_id}

Steps:
1) best-effort stop
2) best-effort container remove
3) unregister from compose
4) update registry.json
5) remove instance directory

Idempotent:
Safe even if container or compose entry missing.

Errors:
404 not registered
409 lifecycle busy
503 lifecycle disabled
500 unexpected failure

------------------------------------------------------------

Concurrency Model:

Mutating lifecycle endpoints (start, stop, delete)
are protected by per-brain lock.

If busy:
409 "lifecycle busy"

