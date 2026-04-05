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
- The CognitiveOS `POST /v1/memory/{id}/decide` endpoint (internal port 8001) has no authentication in the current release. It is blocked from browser access by the UI proxy denylist, but any service on the same Docker network can call it. This is a known limitation — do not expose port 8001 externally and keep the Docker network internal.
