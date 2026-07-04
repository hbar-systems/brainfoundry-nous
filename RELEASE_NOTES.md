# Release notes — v0.9.0 (draft)

Date: 2026-07-02 (draft — set on tag)

**Theme: pre-launch security hardening.** This release makes the default
configuration safe to expose publicly. Several defaults changed to fail
closed; read the upgrade notes before deploying, because two of them can stop
a mis-configured brain from starting (by design).

## ⚠ Upgrade impact — read before you deploy

1. **Non-dev brains refuse to start on a weak Postgres password.**
   When `BRAIN_ENV` is not `dev`, the API now refuses to boot if the Postgres
   password (from `DATABASE_URL`) is empty or the default `postgres`. Set a
   strong `POSTGRES_PASSWORD` in `.env` first:
   `openssl rand -hex 32`.

2. **Public chat now has a daily cost ceiling by default.**
   `PUBLIC_CHAT_DAILY_MAX` defaults to **2000** (was `0` = unlimited). A public
   brain that previously ran uncapped is now capped at 2000 `/v1/public/chat`
   calls per UTC day. Raise it for a high-traffic org brain, or set it to `0`
   to explicitly opt back into unlimited (only sane with a local model).

3. **`X-Forwarded-For` is no longer trusted by default.**
   Public-surface rate limiting now uses the real transport peer unless
   `TRUST_PROXY_HEADERS=true`. **If your brain sits behind Caddy (or any reverse
   proxy), set `TRUST_PROXY_HEADERS=true`** — otherwise every client is keyed by
   the proxy's IP and shares one rate-limit bucket. A brain reachable directly
   on its port must leave it `false`, or an attacker can spoof the header.

4. **The in-console Update tab is now opt-in.**
   `docker-compose.yml` no longer mounts `/var/run/docker.sock` into the api
   container by default. `/admin/update` returns a clear `503` until you enable
   it by copying `docker-compose.override.yml.example` →
   `docker-compose.override.yml` and uncommenting the two mounts. SSH-driven
   updates (`scripts/update_brain.sh`) are unaffected and remain the recommended
   path. See `docs/DEPLOYMENT.md`.

## Security hardening

- **Fail-closed Postgres password** in non-dev (`api/main.py`). Mirrors the
  existing `NODEOS_SIGNING_SECRET` / `BRAIN_API_KEY` startup refusals.
- **Safe public daily cap default** (`api/kernel/rate_limiter.py`): 2000/day.
- **Proxy-header trust flag** `TRUST_PROXY_HEADERS` (`api/main.py`), default
  `false`, so a directly-reachable brain can't be tricked into rate-limiting a
  spoofed IP.
- **`docker.sock` removed from the default compose file** — root-equivalent host
  access is now an explicit, documented opt-in.

## Docs & naming

- README rewritten: what/for-whom/quickstart up top, badges, demo placeholder,
  links to brainfoundry.ai + hbar.systems + the public demo.
- Naming standardized in prose: the product is **BrainFoundry**, a single
  install is **a BrainFoundry brain**, and the governance kernel is
  **BrainKernel** (internally `nodeos`). `nous` is reserved as an instance name
  (the operator's brain / public demo). Code/container renames are tracked
  (not applied) in `docs/NAMING.md`.
- `.env.example` documents all four hardening changes, including a loud warning
  that pointing `PUBLIC_CHAT_MODEL` at a paid API model makes
  `PUBLIC_CHAT_DAILY_MAX` and Turnstile mandatory.

## Tests

- New `tests/test_release_hardening.py` guards the daily-cap default, the
  `TRUST_PROXY_HEADERS` gating, and the import-time Postgres-password refusal.
- Internal: `PROPOSAL_TEXT_DIR` now derives from `RUNTIME_DIR` (override via
  `BRAIN_RUNTIME_DIR`) instead of a hardcoded `/app` path — prod default
  unchanged; enables off-container test runs.
