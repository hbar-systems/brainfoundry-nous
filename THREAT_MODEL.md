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
| Installed brain-app code (the app's own JS in the console) | **untrusted** | opaque-origin sandbox; reaches the brain only through the postMessage bridge, which checks the manifest (§4b, 2026-10-16) |

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

## 4a. Memory privacy: `local-only` (added 2026-10-14)

Every memory chunk carries a privacy level in `metadata.privacy`
(`api/privacy.py`):

- `open` (default; also any chunk with no level): any reasoner may read it.
- `local-only`: only a reasoner on hardware the owner controls may read it:
  the box's own Ollama (`OLLAMA_URL`) or an Ollama on a tailnet spoke
  (`OLLAMA_SPOKE_URL`).

How the owner sets it: the Privacy chips (open / local-only) next to "Memory
layer" on the Knowledge tab before uploading; the per-document chip in
Knowledge → Browse to flip an existing document; or the API:
`POST /documents/upload` with form field `privacy=local-only`,
`POST /documents/{name}/privacy {"privacy": "local-only" | "open"}` (API key),
`POST /memory/store {"privacy": "local-only", ...}`,
`POST /memory/append {"privacy": "local-only", ...}` (brain apps pass it as
`privacy` in `memory.write`; added 2026-10-15). A re-upload of a local-only
document without a choice stays local-only; an append keeps the stricter of
the requested level, a level in its passthrough metadata (which cannot lower
it) and any chunk already stored with the same content.

**The private vault (2026-10-15).** A folder on the host that the Unix users
the closed reasoners run as (`hands`, `cc`) cannot read: mode 700, owned by
the owner (default `/home/<owner>/vault`, `BRAIN_VAULT_DIR`), mounted
read-only into the api container at `/vault`. Its text files are ingested
(every 10 minutes, `BRAIN_VAULT_SCAN_MINUTES`, or Knowledge -> Vault -> Scan
now, or `POST /vault/scan`) as documents `vault/<path>` with source
`vault:<path>`, always local-only; `POST /documents/{name}/privacy` refuses to
make them open (403 `vault_locked`, and the UPDATE itself skips vault chunks)
while the file is in the vault. Vault files are never copied anywhere: not to
`in/`, `out/`, the world checkout, the runtime volume, or an export (the
on-box export and `scripts/export_brain.py` leave vault documents out unless
`--include-vault`). Set up once by the owner with `scripts/vault-setup.sh`
(docs/architecture.md, "The private vault").

**The owner's allowlist of local readers (2026-10-15).** Locality says a
model can be trusted with local-only memory; the allowlist says the owner
does. With no list (the default) every model the locality rule accepts may
read it. The owner narrows it to named models with the chips in Knowledge ->
Vault (`POST /vault/readers`, settings entry `local_readers`) or
`BRAIN_LOCAL_READERS` (comma-separated, `none` for no model); a local model
not on the list gets the open view, exactly like a hosted one.

**The read audit (2026-10-15).** Every turn that put local-only chunks in
front of a model writes one line to the tool audit (`/tools/audit`, Trace
tab, and "Recent reads" in the Vault panel): time, model, endpoint host,
session id, surface, document names and chunk count. Never the content.

**The session mark (2026-10-15).** A chat session in which any turn put a
local-only chunk in front of a model is marked (`chat_sessions.local_only_at`;
init.sql, startup hook, `scripts/migrate_privacy.py`). Its history holds the
model's quotes and paraphrase, so only a reader that may see local-only
memory may continue it: `/chat/rag` and `/chat/completions` refuse a marked
session for a closed reasoner, a local model off the allowlist, or a brain
app (409 `session_local_only`, nothing sent; the console offers a fresh
session). "Save to memory" (consolidation) summarises a marked session only
with a model that may read it (the local default) and stores the summary
local-only; the Store button's classifier (`/memory/store/propose`, given the
`session_id`) refuses a closed model; anything stored from a marked session
lands local-only. The session list shows a "local-only" mark; the chat header
shows "local-only · GREEN tools only" with the rule.

**What it guarantees.** When a turn is answered by a closed provider
(Anthropic, OpenAI, Gemini, xAI, Groq, OpenRouter, Together, Mistral, an Ollama
`:cloud` model, or an Ollama endpoint on a public host), local-only chunks are
filtered out in the SQL query itself, filtered again in Python, and so are
never retrieved, never put in the prompt, and never sent to that provider.
This holds on every path that feeds memory to a model: `/chat/rag` (all three
retrieval architectures, the corroboration pass, the agentic `search_memory`
tool), brain-app `llm.complete`, Telegram, `/v1/public/chat`,
`/v1/federation/query`, the harmonics receiver context, the layer-scheme
proposal, and `/documents/search` (which the CC bridge uses to give Claude Code
memory; it returns local-only chunks only when the caller sends
`include_local_only: true`, which only the Knowledge tab does).

It fails closed: a model whose route cannot be resolved, a model name the
provider layer does not know, an unparseable or public Ollama URL, or a stored
level other than exactly `open` all count as closed / local-only. A retrieval
call that does not say who reads the result gets the closed view.

Local-only chunks are included only when the reasoner is local **and** the
answer returns to the owner on the console. They are withheld, even on a local
model, from: brain apps (the reply goes into third-party app code), Telegram
(the reply crosses Telegram's servers), public chat and federation (the reader
is not the owner), and the autonomy tick. Once a local turn holds local-only
memory, only GREEN tools (own memory, own task list) can be called; web search,
fetch, brain_call, mail, Drive, calendar and MCP tools are refused for the rest
of the turn, since their arguments leave the box. The "your mind" fact
extraction is skipped for that turn if its model is closed. The rule is
returned with every reply in `rag_metadata.privacy` (`local_reader`,
`local_only_used`, `rule`) and named in the chat header.

The vault adds a file-level wall to the chunk-level gate: the vault's files
are unreadable to `hands` and `cc` on the host (checked by
`scripts/vault-setup.sh` with `sudo -u hands ls` and a probe file), so the
Claude Code and Codex seats cannot read them from disk, and their memory
block (`/documents/search` without `include_local_only`) never carries their
chunks. Derived text is tracked per session: a session that quoted local-only
memory is not continued, summarised or classified by a closed model.

**What it does not guarantee.**

- Files outside the vault are not covered. A local-only document that is
  also a file in the world checkout, `in/` or `out/` is readable by Claude
  Code and Codex whatever its memory level. Put private files in the vault,
  not there.
- The wall is Unix permissions plus docker. Root on the host, any member of
  the `docker` group, and anyone holding the brain's API key can read vault
  content (the api is root in its container; the API's document routes and
  `/documents/search` with `include_local_only` return local-only chunks to
  the key holder). `vault-setup.sh` refuses when `hands` or `cc` is in the
  docker group, but it cannot see the key: keep `BRAIN_API_KEY` where hands
  and cc cannot read it (the brain's `.env` and the cc bridge's env file), or
  a Claude Code run could call the API itself.
- The session mark is per session. Text the owner copies out of a marked
  session by hand (a paste into a new session, a file) is ordinary text again.
  A client that replays a marked session's messages without its `session_id`
  is not caught: the console always sends it, but `/chat/completions` and
  `/chat/rag` take the history from the request body.
- Older sessions are unmarked. A session where a local model quoted
  local-only memory before this change carries no mark; start fresh sessions
  for hosted models, or delete those sessions.
- Backups are not filtered. `scripts/backup_brain.sh` dumps the database,
  vault documents included; the export leaves them out by default, a backup
  does not.
- It does not encrypt anything. A local-only chunk (vault chunks included) is
  plaintext in Postgres and in backups, and in exports when it is not a vault
  document; the gate controls which reasoner reads it, not who can read the
  database.
- Owner-controlled is judged from the address: a docker service name,
  localhost, private, link-local or Tailscale (100.64.0.0/10) addresses,
  `*.ts.net` / `*.local` / `*.internal` names, or hosts listed in
  `PRIVACY_LOCAL_HOSTS`. Pointing `OLLAMA_URL` at a private address you do not
  control defeats it.
- Embeddings are computed on the box (or on the embed spoke) for every chunk,
  whatever its level, vault files included. If the embed spoke is not owner
  hardware, local-only text reaches it at ingest.
- The allowlist names models, not weights. A model pulled under an allowed
  name (a different `llama3.2:3b` pushed to the same tag) is allowed.

## 4b. Brain apps: the app lane (added 2026-10-16)

**Finding (2026-10-16, from reading the console code, then reproduced in
headless Chromium).** An installed brain app ran in an iframe with
`sandbox="allow-scripts allow-same-origin"`, served from `/api/bf/apps/<id>/`
on the console's own origin. The console's `/api/bf` proxy
(`ui/pages/api/bf/[...path].js`) adds `BRAIN_API_KEY` to every request it
forwards. So app code had the owner's authority: it could `fetch`
`/api/bf/documents/search` with `include_local_only: true` (local-only
memory), `/api/bf/sessions` (chat history), `/api/bf/settings/*`, admin routes
such as `/api/bf/apps/install`; mint loop permits at `/api/permit`; and read the
raw owner key from `/api/cli-info`, which made the leak permanent (the key works
from anywhere). With allow-same-origin it could also reach `window.parent`
(the console page, its storage, its `fetch`). The same frame could post to the
CC bridge at `/cc/*` (Caddy adds the operator token after the console login)
and open the terminal websocket at `/claude/`. The manifest permissions and the
`llm.complete` open-view rule held only for apps that used the bridge as
intended. Severity: an app (or a script injected into an app, for example
through memory content it renders) could read everything the owner can and act
as the owner. Reproduced with a probe app: all of the above answered 200 with
the owner key attached upstream.

**Fix (2026-10-16).** Three layers, so no single one carries it:

1. *Opaque origin.* The iframe is sandboxed without `allow-same-origin`
   (`allow-scripts allow-downloads`, `ui/lib/appLane.js` `APP_SANDBOX`), and
   every app file is served with `Content-Security-Policy: sandbox
   allow-scripts allow-downloads`. An app document has an opaque origin
   however it is opened: framed by the console, or opened directly in a tab
   (the CSP header does it there). It cannot touch the console page, its
   storage, or its `fetch`.
2. *The doors refuse foreign pages.* The `/api/bf` proxy, `/api/permit`,
   `/api/cli-info`, `/api/proposal-decide` and the CC bridge refuse any request
   from a page other than the console itself: `Origin: null`,
   `Sec-Fetch-Site: cross-site` or `same-site`, or a `Referer` inside
   `/api/bf/apps/` (403 `app_frame_refused`). Only an app's own files
   (`GET`/`HEAD apps/<id>/<file>`) and an app's own backend
   (`apps/<id>/api/...`) pass, and both go upstream **without** the owner key
   and without the caller's credentials. Clients that are not browser pages
   (the CLI, curl, box processes) send none of these headers and are
   unaffected. The CC bridge allows one more thing: a top-level `GET`
   navigation (a link opened in a new tab), which an app frame cannot make.
   The terminal (ttyd) runs with `--check-origin`, so its websocket opens only
   from a page on the console's host (takes effect when `scripts/cc/install.sh`
   is run again).
3. *The bridge is the only way an app acts.* The host page
   (`ui/pages/apps/[id].js`, logic in `ui/lib/appBridge.js`) answers only
   messages whose `source` is the app's own frame window, and checks every
   permission-gated intent against the installed manifest: `memory.write`
   needs `memory.write` and a write/append layer in `requires_layers`;
   `llm.complete` needs `llm.invoke`. No bridge intent returns local-only
   memory: `llm.complete` is sent with a permit attributed `app:<id>`, and
   `/chat/rag` gives such a permit the open view on any model (§4a); its body
   is built from fixed fields, so an app cannot pass `session_id`,
   `include_local_only` or its own layers; `memory.write` returns only the new
   chunk's id, name and level; there is no memory-read intent.

To keep existing apps working in an opaque origin, the proxy puts a small shim
first in every app HTML page: `localStorage` becomes a store the host page
keeps per app id (seeded through the iframe's `name`, saved through
`storage.*` intents, at most 2,000,000 characters per app), `sessionStorage`
lives for the page, `fetch` and `XMLHttpRequest` to the app's own files carry
the console login, and a `Worker` from the app's own files starts through a
small loader. The app's own files get CORS headers for the opaque origin
(`Access-Control-Allow-Origin: null` with credentials); core routes never do.
On first load the host copies the keys the default-shelf apps wrote into the
console's own storage before the fix (`daybook:*`, `hbar-ink-*`,
`qr-progress`) into that app's store, and only those. Checked 2026-10-16 in
headless Chromium behind a basic-auth front: the nine apps installed on hbar
(quantum-room, cell-architecture-studio, daybook, hbar-ink,
hbar-health-letter-ingestion with its pdf.js and tesseract workers,
poker-journal, oracle, science-experiment, thread-consolidator) load with no
errors, keep their storage across visits, and a probe app's attempts on
`/api/bf/documents/search`, `/api/bf/sessions`, `/api/bf/apps/install`,
`/api/cli-info`, `/api/permit` and `window.parent` all fail, with no core
request reaching the API. Tests: `tests/test_app_lane.py`.

**What it does not cover.**

- *App backends.* An app whose manifest declares `entries.api` runs Python in
  the brain's API process. That code has the process's authority; the sandbox
  is about the app's browser code. Read an app's backend before installing it.
- *App backends are not per-app from the browser.* An app frame can call any
  installed app's `apps/<id>/api/...` route (without the owner key); the
  proxy cannot tell which app's frame sent it.
- *Apps that called the console directly.* An app that used `/api/bf/...`,
  `/cc/...` or the parent window itself (rather than the bridge) stops working.
  None of the apps installed on hbar does; `brain-app-scene` (reads
  `/api/bf/sessions`, posts to `/cc/chat`) does and needs a bridge intent or a
  place as a console page.
- *Fonts and anonymous-CORS media.* CSS `@font-face` files and elements with
  `crossorigin="anonymous"` created by script are fetched without the console
  login, so behind the console's basic auth they fail. Inline fonts as `data:`
  URLs or load them from a public CDN. No installed app is affected.
- *No IndexedDB, cookies or service workers* in an opaque origin.
- *The Files pane* still shows hand-made HTML from the box in a frame with
  `allow-same-origin` (`ui/pages/files.js` `VIEW_SANDBOX`, served by the CC
  bridge at `/cc/files/raw`). That is the same class of exposure for HTML
  files on the box (written by the reasoner or ingested), open as of this entry.

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
3. **Memory-poisoning through the write lane — now scanned + classified at every
   write, substantially narrowed.** A poisoned document re-injects into
   every session that retrieves it, and the §4 tool gate cannot touch memory
   *formation* — it persists via direct `INSERT INTO document_embeddings` SQL and
   the kernel `MEMORY_APPEND` class, a separate governance lane. Previously
   several of those write paths (`/memory/append`, `/memory/store`) wrote with no
   injection scan and no memory-type stamp, so the read-side rerank (which only
   demotes by an *already-stamped* `mem_type`) gave zero defense against them.
   That gap is now closed: **every** write path runs `injection_scan.scan_text`
   and stamps `mem_type` + provenance before persisting (`memory_type.classify_write`):
   - Operator-direct writes (chat Store button, approved upload) → `semantic`,
     not demoted — the operator's own curated memory is trusted, but the scan
     band is still recorded in provenance.
   - Non-interactive / external writes (a brain app via `/memory/append`,
     automated `brain_ingest`, a stored tool/peer answer) → `untrusted` (0.4× at
     retrieval) by default; a **high**-severity scan hit additionally
     **quarantines** the chunk (persisted with provenance, excluded from
     retrieval by `memory_type.rerank` until the operator releases it — logged,
     never silently dropped). Never `semantic`.
   - `brain_ingest` rides the already-hardened document-upload propose/approve
     flow (scan at propose, `classify_upload` at approve), so it is covered by
     the same mechanism with an operator approval in the loop.
   Residual: this is heuristic detection, not a guarantee — a novel injection
   phrasing the scanner misses still lands `untrusted` (demoted) on the
   non-interactive lanes but `semantic` on the operator-direct lanes, where the
   operator's judgement at Store/approve time remains the backstop. Retrieved
   content is also still *seen* (demoted to data, not erased). Narrowed from
   "principal residual surface" to "heuristic-coverage residual".
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
7. **Integration secrets encrypted at rest (v0.9.2).** IMAP app password,
   Telegram bot token, OAuth refresh token, and MCP auth live in the
   `/app/runtime/settings.json` sidecar — since v0.9.2 encrypted with a Fernet
   key derived from `BRAIN_IDENTITY_SECRET`, file mode 600, legacy plaintext
   migrated on first read (the Odysseus pattern). Residual exposure: anyone
   holding both the sidecar and `.env` can decrypt — this is at-rest
   protection, not a vault. Never returned by any API.
8. **No SSRF guard on caller-supplied LLM endpoints.** No chat endpoint accepts a
   caller-supplied `base_url`. If one is ever added, validate scheme + resolved
   address against an allowlist and block link-local / metadata ranges first.
6. **Single-pass blast radius is small today, but growing.** v0 tool-calling is
   operator-driven; native agentic mode widens what an injection could attempt.
   The gate (§4) is sized for that growth; the approval flow for RED is not built.

## 7. Out of scope

Transport TLS, host hardening, OS patching, and physical access — owned by the
deployment (SERVERS.md), not this template.
