# Security audit 2026-11-13 (SEC-PASS-1)

Created 2026-11-13. Branch `sec-pass-1`, not pushed.

Trigger: Odysseus (github.com/odysseus-dev/odysseus, AGPL) published three advisories.
Read through the GitHub advisory API on 2026-11-13:

- CVE-2026-70619 / GHSA-7jfx-c8jj-p569 (high): endpoint-management routes checked the session but not the admin role, so a non-admin could overwrite the server-wide embedding backend URL (all embedded text then went to that URL) or delete it.
- CVE-2026-70620 / GHSA-pp2c-7vpq-xf5f (medium): the same embedding endpoint setting fetched any URL with no scheme, host, IP-range or DNS-rebind check (loopback, RFC 1918, link-local, cloud metadata).
- GHSA-xwhc-f36c-v5vm (CVSS 9.9, non-admin runs OS commands): not found in the global advisory database or the repo's advisory list on 2026-11-13 (404). Unverified; audited as the class it names.

Auth model in nous: one principal holds power, the owner, by `BRAIN_API_KEY` (`api/main.py:341` `get_api_key`, constant-time compare). There is no in-brain non-admin user; members are separate brains. The non-owner callers are: the public (public chat, submissions), federation peers (signed assertions), installed app backends (`require_backend_caller`, `api/apps_mount.py:190`) and the model itself through tools (`api/tools/__init__.py`, tier gate). So "non-admin" below means any of those.

## Class 1: server-wide settings and privileged actions

Checked:
- Every POST/PUT/PATCH/DELETE route in the live route table (walked in a test, not by grep). All carry `get_api_key` or `_operator_auth` (`api/federation_dm.py`) or the app-backend gate, except seven public doors, each with its own authentication: `/v1/federation/assertion` (`api/main.py:558`, pinned peer key + replay cache), `/integrations/telegram/webhook` (bot secret header), `/v1/public/chat` (public scope, Turnstile, rate limit), `/v1/federation/query` and `/v1/ask` (public scope, signed assertion), `/documents/import-laptop/file|finish` (`api/main.py:5119`, one-run owner-minted token).
- Router mounts `api/main.py:1993-2051`: compute meter, appearance, export, brain-apps mounted with `dependencies=[Depends(get_api_key)]`; DM, publisher and harmonics gate per route (`_operator_auth`); `/harmonics/score` records only with the key.
- Settings writes (`/settings/*`, `api/main.py:699-1691`), integrations, `/admin/update` and `/admin/revert` (`api/main.py:8003`, `8066`): owner key.
- The embedding backend (the exact Odysseus target): `EMBED_SPOKE_URL` is env-only (`api/embeddings/model.py:91`); no route writes it.
- The model's tools: no tool writes settings; YELLOW needs operator authorization, RED is refused (`api/tools/__init__.py:183-236`).

Findings: none real. The route-level gate is server-side on every mutating route.

Fix: none needed. Added a regression test, `tests/test_sec_pass_1_routes.py` (commit 4c58db1): it fails if any new mutating route lands without the owner gate and outside the reviewed public list, and checks that settings/admin routes return 401 with no key and with a wrong key.

## Class 2: server fetches a caller-supplied URL (SSRF)

Checked:
- `api/tools/fetch_url.py:37-92,150-175`: http/https only, every resolved address through `ip_is_public` (private, loopback, link-local incl. 169.254.169.254, reserved, multicast, unspecified, 100.64.0.0/10 tailnet, IPv4-mapped IPv6), redirects followed by hand and re-checked per hop. Good. Used by `/tools/fetch-url` (`api/main.py:1098`) and the model tool.
- `api/submissions.py:260`, `api/radio_taste.py:146,150`, `api/orfeo_post.py:63`: `follow_redirects=False`.
- Federation assertion: endpoint must be a pinned peer before any fetch (`api/identity/peers.py:68`); substrate-depth fetch only for pinned peers.
- `api/integrations/mcp_client.py:86` (MCP connect) and `api/integrations/email_imap.py:82` (IMAP host): owner-only and pointed at owner-chosen servers, which may legitimately be on the LAN or localhost. Not changed; see "What remains".

Findings (all reachable only with the owner key, the same privilege level as CVE-2026-70620):
1. `api/integrations/calendar_ics.py:111` (before the fix): checked the first URL, then `httpx.Client(follow_redirects=True)`. A public feed URL that answers 302 to `http://169.254.169.254/...` or a tailnet address was followed unchecked.
2. `api/federation_dm.py:150` and `api/harmonics.py:390` (before the fix): `f"https://{handle}.brainfoundry.ai"` with `handle` from the request body (`/v1/federation/dm/send`, `/harmonics/contribute`). A handle like `169.254.169.254/latest#` or `evil.example/?` moved the request to any host.
3. `api/hbar_commands.py:29-50` (before the fix): `peers.introduce` / `peers.ping` resolved with `gethostbyname` (first IPv4 only) and the category flags, which admit 100.64.0.0/10 (the owner's tailnet) and skip IPv6 answers.

Fixes:
1. ed0d548: redirects followed by hand, each hop re-checked, max 3 (`api/integrations/calendar_ics.py:111-131`).
2. 2b9b410: `peer_endpoint()` (`api/federation_dm.py:147`) accepts one DNS label only, else 400; used by both fetchers.
3. 24a62c4: every `getaddrinfo` answer through `ip_is_public` (`api/hbar_commands.py:29`).
Tests: `tests/test_sec_pass_1.py` (commit 4c58db1).

## Class 3: request to subprocess / shell / eval

Checked: every `subprocess`, `os.system`, `eval`, `exec` in `api/` and `nodeos/main.py`. No `shell=True` and no `eval`/`exec` of request data anywhere. `api/main.py:770-813,7767-7830,8027,8090` (update, revert, version info) run fixed argv with no request input, owner-only. `api/system_status.py:97` fixed docker argv. `nodeos/main.py:504-890` git argv, paths after `--`. Installed app backends are loaded as code (`api/apps_mount.py:176-184`) by design; install is owner-only.

Finding (owner key needed):
4. `api/apps.py:257` `_git_clone`, reached from `/apps/install` and `/apps/install/preview` (`api/apps.py:910,925`), passed `req.repo_url` to `git clone` with no check and no `--`. A value starting with `-` is parsed by git as an option (the `--upload-pack=<cmd>` family runs a command), and `file://` or internal `http://` URLs made the server read local repositories or reach internal hosts (class 2 as well). The manifest schema already limits `repo` to `https://(github.com|gitlab.com|codeberg.org)/` (`api/schemas/brain-app.schema.json:55`); the install request did not.

Fix 4: 03ff522: `InstallRequest` validates `repo_url` against the same forge rule and `ref` against a plain-name rule (no leading `-`, no spaces, no `..`); `_git_clone` puts `--` before the positionals. Pack installs (`_install_default`) are untouched: they come from shipped, schema-checked pack files with pinned SHAs.

## Compose and auth default

- `docker-compose.yml`: every published port binds 127.0.0.1. No localhost or IP-based bypass in `get_api_key`.
- Images: `ollama/ollama:latest` (line 22) is a floating tag; `pgvector/pgvector:pg16`, `redis:7-alpine` and the Dockerfile bases `python:3.11-slim`, `node:18-alpine` are major-pinned, not digest-pinned.
- Auth default: `BRAIN_ENV` defaults to `dev` (lines 58, 208). In dev, an empty `BRAIN_API_KEY` makes every request unauthenticated (`api/main.py:346-351`, warning only). `scripts/start_docker.sh` fills `BRAIN_API_KEY` and `NODEOS_INTERNAL_KEY` when blank, so the normal path is keyed; a hand-written `.env` with no key and no `BRAIN_ENV` is open.

Not changed here (both change behaviour on every running brain at its next update, so they are owner decisions):
- Pin `ollama/ollama` to a tested version (or digest).
- Default `BRAIN_ENV` to `prod` in compose, or refuse to serve with an empty key unless an explicit `BRAIN_ALLOW_NO_KEY=1`. Needs a fleet check first that every brain's `.env` sets the identity secret, or brains would refuse to start.

## What remains

- DNS rebinding: `fetch_url`, calendar and peer checks resolve, then httpx resolves again. A host that answers public then private can slip between. Closing it needs connecting to the checked IP (custom transport). Not done.
- MCP connect URL and IMAP host: owner-set, no range check, because local MCP servers and LAN mail servers are legitimate. If the owner key is the only boundary that is acceptable; if the model or an app ever gets to set them, they need the `ip_is_public` rule with an explicit owner-allowed local list.
- `api/compute.py:75` probes declared compute URLs; traced to config, not to a request (unverified beyond reading).
- `/integrations/google/callback` compares the OAuth state with `!=` and any caller consumes the one-shot state (denial of the pending connection only).
- GHSA-xwhc-f36c-v5vm text not read (not published where it could be fetched); re-check when it appears.

## Tests

`bash scripts/test-gate.sh` before the changes: GREEN, 1525 passed, 8 skipped, 6 xfailed. After: GREEN, 1558 passed, 8 skipped, 6 xfailed (33 new tests). Browser gate skipped (no playwright in the test venv).
