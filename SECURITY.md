# Security Policy

## Supported versions

This project is a self-hosted template. You are responsible for keeping your own deployment up to date. Only the latest `main` branch receives security fixes.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues by emailing the maintainer directly (see the GitHub profile for contact). Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce
- Any relevant logs or proof-of-concept (with sensitive details redacted)

You will receive a response within 5 business days. If a fix is warranted, a patch will be issued and the issue disclosed after the fix is available.

## Security model

brainfoundry-nous is designed as a **personal, self-hosted node**. Its security assumptions are:

- The node runs on infrastructure you control
- `BRAIN_API_KEY` is kept secret and rotated if compromised
- `BRAIN_IDENTITY_SECRET` and `NODEOS_SIGNING_SECRET` are generated with `openssl rand -hex 32` and never reused
- The API is placed behind a TLS-terminating reverse proxy before being exposed to the internet
- `BRAIN_ENV=prod` is set in production to enforce startup secret validation
- Only ports `3010` (UI) and `8010` (API, protected) are exposed externally; all other ports are bound to `127.0.0.1`

## Known limitations

- The console UI at port 3010 forwards the `X-API-Key` header to the API, but does not implement its own session layer. Protect the UI with network-level controls (VPN, firewall, Tailscale) if you expose it.
- `BRAIN_ENV=dev` (the default) disables several enforcement checks. Never use dev mode in production.
- API keys for upstream model providers (Anthropic, OpenAI, …) are passed to containers as environment variables and are visible to anything with access to the Docker socket on the host. For multi-tenant or hostile-host environments, use Docker secrets or an external vault.

## Governance scope (v0.6)

BrainKernel (the `nodeos` container) is the authority for loop permits,
memory proposals, action proposals, and the append-only audit log.

**What it gates today:**

- Every `/chat/completions` and `/chat/rag` request must present both a valid
  `permit_id` AND its caller-bound `permit_token`. The token is
  `HMAC(permit_id + agent_id)` signed with NodeOS's signing secret and is
  returned only once, from `POST /v1/loops/request`. A bare `permit_id`
  observed in a log cannot be replayed.
- Brain-layer mutations (`remember`, `forget`, `audit.clear`) are routed
  through a NodeOS propose → approve → execute flow before any database
  write or audit-file wipe lands. Fail-closed: if NodeOS is unreachable or
  the permit is rejected, the mutation is denied.
- `git_push` and other external side-effect actions go through a strict
  preview-and-decide flow with a branch allowlist.
- Federation assertions require a non-empty `iss` claim; callers that fetch
  a peer's public key from a known endpoint can pin `expected_issuer` to
  reject assertions signed by a different brain.
- All state-mutating NodeOS endpoints require `X-Internal-Key`
  (service-to-service auth). NodeOS binds only to `127.0.0.1:8001` and has
  no browser proxy.

**What it does not yet gate (v0.6):**

- `context.set` / `context.clear` mutate an in-process dictionary that
  resets on container restart. These are not yet routed through NodeOS;
  they are session-local state, not long-term memory.
- Bulk document ingestion via `scripts/ingest_folder.py` runs outside the
  API container and writes directly to the database. The running-server
  path (`POST /documents/upload`) is fully gated; the offline script is
  intended for the single-owner bootstrap case only.

Treat BrainKernel in v0.6 as a strong authority for the chat loop, external
actions, and all long-term memory writes that transit the API.
