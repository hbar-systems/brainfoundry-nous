# BrainFoundry Control Plane Guardrails (v0)

BrainFoundry is a local operator control plane that manages sovereign brain instances via the Instantiator.

## Scope (v0)
- Local-only operation (not internet-facing)
- Single operator authentication
- Calls only deterministic Instantiator primitives:
  - scripts/mold_new_brain.sh
  - scripts/register_instance.sh
  - docker compose up/down
- Maintains an explicit registry of brains (file-based)

## Security
- Must not expose Docker socket to untrusted clients
- Bind to 127.0.0.1 or internal docker network only
- Require an operator token for all mutating endpoints
- No arbitrary command execution; only allowlisted actions

## Success Criteria
- POST /brains creates + starts an instance deterministically
- GET /brains lists registry + live status
- POST /brains/{id}/stop and /start work reliably
- DELETE /brains/{id} removes instance and registry entry
