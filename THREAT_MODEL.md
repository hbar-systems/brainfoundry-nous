# Threat model — brainfoundry-nous

Created: 2026-06-07
Applies to: the brain runtime (`api/`), as deployed per SERVERS.md.
Companion: SECURITY.md (reporting + deployment hardening). This document states
the trust boundary so a contributor doesn't have to reverse-engineer it from the
auth stack. Practice adopted from Odysseus's `THREAT_MODEL.md` (MIT — see NOTICE).

## 1. What this system is

A BrainFoundry brain is a **sovereign substrate** owned by one person. It hosts a
frontier reasoner (cloud via BYOK, or a local model) as an *application* over the
owner's private memory. The brain is not the intelligence; it is the boundary
around it. One brain per person; systems connect to it through site-permitted API
endpoints, never the other way around.

The reasoner answers on the owner's behalf and — in agentic mode — can call
tools. It is fed content the owner did not write: web results, fetched pages, and
the **ingested corpus itself**. That asymmetry (privileged actor, untrusted
input) is the core of the threat model.

## 2. Trust boundary

| Surface | Trust | Handling |
|---|---|---|
| Owner's direct chat turn | trusted | the only source of instructions |
| Brain persona / charter `.md` | trusted (owner-authored) | system role |
| Retrieved knowledge-store documents | **untrusted** | wrapped (`api/security/untrusted.py`), demoted at retrieval (`api/memory_type.py`), scanned at ingest (`api/injection_scan.py`) |
| Web search / fetch tool output | **untrusted** | wrapped (`api/tools/safety.py` → `api/security/untrusted.py`) |
| Email / calendar / Drive / MCP tool output | **untrusted** | wrapped — an email body, calendar invite, file, or MCP server response can carry injection (`api/integrations/*`, all route through `api/security/untrusted.py`) |
| Saved memories, notes | **untrusted** | route through the wrapper |
| Tool *names/args* proposed by the model | **untrusted** | fail-closed gate (`api/tools.is_blocked_tool`) — but see Known Gap on MCP |
| Integration credentials (IMAP app password, Telegram bot token, OAuth refresh, MCP auth) | secret | settings sidecar; never returned to a client. **Plaintext at rest** — see Known Gaps |
| BYOK provider key | secret | env only; never logged, never returned to a client, never sent to a peer |

**Rule:** untrusted content never enters the system role. It is rendered as a
user-role data block with a do-not-follow header and hard delimiters. This is
mitigation, not prevention (see Known Gaps).

## 3. Roles × capabilities

| Role | Read own memory | Web (yellow) | Write/exec/send (red) | MCP tools | Settings |
|---|---|---|---|---|---|
| Owner (chat) | yes | yes, if toggle on | **blocked** (no approval flow yet) | **blocked** | via authed UI |
| Agentic loop (model-chosen) | yes (green) | yes, if toggle on | **blocked** | **blocked** | no |
| Untrusted content (injected) | — must not cause any of the above — | | | | |

## 4. Tool gate (fail-closed)

`api/tools.dispatch` runs `is_blocked_tool(name, admin=False)` **before** the
registry lookup and tier gate. Verdicts:

- non-string / empty name → **blocked** ("can't evaluate" ⇒ deny)
- `mcp__*` → **admin-only** (any MCP tool is privileged by default)
- `shell` / `file` / `email` / `settings` / memory-write families → **default-deny**,
  admin-only

The autonomous agentic loop always dispatches with `admin=False`, so a poisoned
document that smuggles "call delete_memory" past the model still dies at the gate.
RED-tier tools remain blocked wholesale until a per-call approval flow exists.

## 5. Key handling (BYOK)

The provider key lives in the environment (`.env`, never committed; see
`.gitignore`). It is never written to logs, never included in a response body,
and never forwarded on the federation path. Federation DMs and `brain_call` carry
content, never credentials.

## 6. Known gaps (honest list)

1. **Wrapping is not prevention.** The model still *sees* untrusted text every
   turn. The wrapper lowers injection success probability; it does not eliminate
   it. The hard backstop is the tool gate (§4), not the prompt.
2. **The tool gate is forward-looking insurance, not a hole closed today.** The
   gate sits only on `api.tools.dispatch`. The entire agentic tool surface today
   is three *read* tools (`web_search`, `search_memory`, `brain_call`) — no
   memory-mutation / file / send tool is registered. So an injected
   `call delete_memory` is denied, but that tool does not exist anyway and could
   not have run regardless. The gate's value is that *when a write tool is added
   later, it is already default-denied* — it pre-empts a future hole, it did not
   plug a currently-open one.
3. **Memory-poisoning persists through the write lane, which the gate cannot
   touch.** A poisoned document approved at ingest is re-injected into every
   session that retrieves it; `injection_scan.py` flags it at approval time, but
   approval is a fallible human judgement, and retrieved content is demoted to
   data but still *seen*. Critically, the brain's memory *formation* does not go
   through the tool gate at all — it persists via the kernel `MEMORY_APPEND`
   execution class and direct `INSERT INTO document_embeddings` SQL, a separate
   governance lane. If injected content can shape what `MEMORY_APPEND` persists,
   that poison re-injects every turn and the §4 gate provides no defense. This
   work demotes *reads* and gates *tools*; it does **not** close the write-lane
   poisoning path. That path is the principal residual memory-injection surface.
4. **No shell/filesystem sandbox.** The brain does not sandbox the (currently
   blocked) RED tools. Mitigation is the deployment discipline in SERVERS.md and
   routing untrusted installers to the quarantine box — not in-process isolation.
5. **`fetch_url` SSRF is DNS-rebinding-bypassable.** `fetch_url` validates the
   resolved address against the public-only allowlist, but httpx re-resolves the
   hostname at connect time — a low-TTL record can rebind to `169.254.169.254` or
   an internal host between the check and the fetch. It is YELLOW (operator
   standing authorization), not model-introducible, but the fix is to pin the
   connection to the validated IP. (Tracked in ROADMAP "harden the new integrations".)
6. **MCP tools bypass the fail-closed gate in the agentic loop.** `is_blocked_tool`
   declares `mcp__*` admin-only, but `_agentic_dispatch` routes `mcp__<server>__*`
   straight to the connected server, so a model-driven (injected) call can reach
   any tool of a *connected* server. This is a deliberate capability grant
   (connecting a server = authorizing its tools), but it means an injected
   document could drive a connected MCP tool. Don't connect an MCP server whose
   tools you wouldn't want the model to call unprompted.
7. **Integration secrets stored in plaintext.** IMAP app password, Telegram bot
   token, OAuth refresh token, and MCP auth live in the `/app/runtime/settings.json`
   sidecar in cleartext (on the operator's own server). Odysseus encrypts these
   (Fernet); we should too. Never returned by any API, but readable by anyone with
   host/file access.
8. **No SSRF guard on caller-supplied LLM endpoints.** No chat endpoint accepts a
   caller-supplied `base_url`. If one is ever added, validate scheme + resolved
   address against an allowlist and block link-local / metadata ranges first.
6. **Single-pass blast radius is small today, but growing.** v0 tool-calling is
   operator-driven; native agentic mode widens what an injection could attempt.
   The gate (§4) is sized for that growth; the approval flow for RED is not built.

## 7. Out of scope

Transport TLS, host hardening, OS patching, and physical access — owned by the
deployment (SERVERS.md), not this template.
