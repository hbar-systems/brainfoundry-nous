DATE: MARCH 11,2026.

hbar-brain Substrate Specification                                                                                                
                                                                                                                                    
  Version: v0.17-instantiator                                                                                                       
  Branch: v0.17-instantiator @ 42caae1                                                                                              
  Status: Integration-ready substrate, pre-external-wiring

  ---
  1. Project Identity and Purpose

  hbar-brain is a constitutional execution kernel for governed AI agent actions. Its function is to ensure that any mutation
  originating from an autonomous agent — file writes, git commits, git pushes — is permitted, proposed, explicitly decided,
  executed, and audited in a tamper-evident chain. No action occurs outside this chain.

  It is not a reasoning system. It is not a memory retrieval system. It is not a chat interface. It is the execution authority layer
   that sits between agents and the systems they act on.

  ---
  2. Core Architectural Principle

  Permit → Propose → Decide → Execute (atomic)

  No mutation occurs without:
  1. An ACTIVE permit with the exact required scope, not expired
  2. A proposal naming the permit, action type, and structured payload
  3. An explicit APPROVE decision made against that proposal
  4. Execution that happens atomically with the decision

  Every step produces a durable audit record. The audit trail is append-only and never rewritten.

  Unknown action types are rejected at the policy layer before any execution attempt.
  Unknown scopes are rejected at permit validation before any proposal is accepted.
  All failure modes are fail-closed.

  ---
  3. Major Components and Their Roles

  3.1 NodeOS (nodeos/)

  The constitutional kernel. FastAPI service, port 8001 (internal Docker, published to localhost).

  Responsibilities:
  - Permit issuance and expiry enforcement (HMAC-signed, SQLite-backed)
  - Action proposal creation and status tracking
  - Scope enforcement at both propose-time and execute-time (belt+suspenders)
  - Atomic decide+execute: APPROVE triggers immediate action execution; DENY produces an audit record with no state change
  - Push discipline: preview-before-push, snapshot binding, no force, branch allowlist, protected branch block
  - Write discipline: path prefix allowlist (scratch/, notes/, generated/), path traversal rejection, null-byte rejection, 256 KB
  size cap
  - Append-only audit log (SQLite audit_events + JSONL action_log.jsonl)
  - Append-only memory log (memory_log.jsonl)
  - Operator read surface: overview, proposals, permits, audit, action policy, identity

  Action policy table (as of v0.17):

  ┌──────────────────┬────────────────┬────────┬───────────────────┐
  │      Action      │ Scope Required │  Risk  │ Requires Approval │
  ├──────────────────┼────────────────┼────────┼───────────────────┤
  │ git_diff_preview │ git.preview    │ LOW    │ Yes               │
  ├──────────────────┼────────────────┼────────┼───────────────────┤
  │ write_file       │ fs.write       │ MEDIUM │ Yes               │
  ├──────────────────┼────────────────┼────────┼───────────────────┤
  │ git_commit       │ git.commit     │ HIGH   │ Yes               │
  ├──────────────────┼────────────────┼────────┼───────────────────┤
  │ git_push         │ git.push       │ HIGH   │ Yes               │
  └──────────────────┴────────────────┴────────┴───────────────────┘






  3.2 CLI (scripts/hbar.py)

  Subprocess-based operator CLI. Translates human commands into NodeOS HTTP calls. Never stores state; derives node_id live from
  /v1/operator/overview on each invocation.

  Read operations: status, proposals, proposal get, permits, permit get, audit
  Write operations: permit request, propose write/commit/preview/push
  Governance: proposal decide --approve|--deny

  3.3 Operator Shell (scripts/hbar_shell.py)

  Python REPL over hbar.py. Never calls NodeOS directly. All NodeOS interaction is mediated by the CLI subprocess.

  Phase 7 continuity layer (fully integrated on this branch):
  - 7A — Operator Identity: loads operator_id from ~/.hbar/identity.yaml; falls back to "operator". Substituted into all --agent-id
  and --decided-by fields. Shown in REPL prompt.
  - 7B — Session Log: append-only JSONL at ~/.hbar/log.jsonl. Events: session_start, command, proposal_created, proposal_decided,
  intent_run, session_end. Fire-and-forget, never blocks.
  - 7C — Intent Context Memory: last 3 successful write_commit extractions replayed as context block into the intent prompt.
  {recent_context} slot; empty when no history.
  - 7D — Orientation Surface: ~/.hbar/context.yaml persists focus string and pinned notes list. Commands: where, focus set/clear,
  note add/drop/clear. All mutations logged to session log.

  LLM intent system:
  - Transport: Ollama at localhost:11435 (default)
  - Model floor: llama3.2:3b (confirmed 10/10 intent probes; 1b is not viable)
  - Intent types: write_commit, write_commit_push, push, preview, unknown
  - Strict exact-key schema validation; unexpected keys at any level are hard-rejected
  - Semantic validator (_validate_write_commit_semantics): absolute path, traversal, metacharacters, empty content, wrapper content,
   generic messages, length bounds — all fail-closed before plan execution

  Governed plan sequences available:
  - plan push — 5-step: permit → preview → approve → push → approve
  - plan preview — 2-step: propose → approve
  - plan commit — 2-step: propose → approve
  - plan_write_commit — 5-step: permit → write → approve → commit → approve
  - plan_write_commit_push — 9-step: permit → write → approve → commit → approve → preview → approve → push → approve

  3.4 API Service (api/)

  Older brain API: semantic search over embedded documents, RAG, kernel routing, rate limiting. Runs on port 8010/8011. Uses
  PostgreSQL + pgvector + Redis + Ollama. Proxied through Next.js UI. This service is distinct from NodeOS and is not the governance
   kernel.

  3.5 UI (ui/)

  Next.js frontend. Proxies to both the API service and NodeOS. Provides a kernel.js page for NodeOS visibility. Not the primary
  operator surface for governed actions.

  3.6 Instances (instances/)

  Instantiation configs for hbar.brain.alpha, beta, demo, gamma. Each has a brain_identity.yaml, docker-compose.overlay.yml, and
  .env. These are template materializations of the substrate.

  3.7 Template (hbar-brain-template/)

  The substrate template from which new instances are molded. Contains the mold tooling (scripts/mold_new_brain.sh,
  scripts/register_instance.sh).

  3.8 brainfoundry / brainloop

  brainfoundry/: instance registry (registry.json), audit JSONL, coordination service.
  brainloop/brainloop_v1.py: loop runner scaffolding.
  Both are present as stubs and are not wired to the current governed execution path.

  ---
  4. Governance Invariants

  These hold on every code path. Violations are bugs, not configuration options.

  1. No action without permit. Every non-read-only action requires an ACTIVE permit with the correct scope. Missing scope → 403 at
  propose-time and again at execute-time.
  2. No permit forgery. Permits are HMAC-signed with NODEOS_SIGNING_SECRET. Token verification is constant-time.
  3. No expired permit execution. TTL is checked at propose-time and at execute-time. Both checks are independent.
  4. No push without preview. git_push requires a stored git_diff_preview snapshot on the exact same (branch, local_head) pair. No
  preview → 403. Preview from a different HEAD → 403.
  5. No push if origin changed since preview. Snapshot binding: if origin has advanced between preview and push, the push is
  rejected with 409 before git is called.
  6. No force push. git push is called as git push origin HEAD:refs/heads/{branch}. No --force flag exists in the code path.
  7. No push to protected branches. main is unconditionally blocked. Push requires the branch to match both the prefix allowlist and
   the explicit branch allowlist.
  8. No write outside path prefix. write_file path must begin with scratch/, notes/, or generated/ (configurable via
  NODEOS_WRITE_PATH_PREFIX_ALLOWLIST).
  9. No path traversal. Both resolve_workspace_path and the shell-side semantic validator independently reject .., null bytes,
  absolute paths, and paths that resolve outside the workspace root.
  10. Preview fails closed. When rev-list cannot determine ahead/behind (remote SHA not in local object store), will_fast_forward is
   returned as false, not true.
  11. Audit is append-only. audit_events table and action_log.jsonl are written to but never rewritten. Memory log
  (memory_log.jsonl) is also append-only.
  12. All executions are audited. Every approve/deny decision and every execution outcome produces an audit record.

  ---
  5. Stable Operator Surfaces

  NodeOS HTTP API (http://localhost:8001)

  ┌────────┬─────────────────────────────┬──────────────────────────────┐
  │ Method │          Endpoint           │             Role             │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /health                     │ Liveness                     │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/identity                │ Node identity                │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/operator/overview       │ Full operator state summary  │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/operator/proposals      │ Proposal ledger (filterable) │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/operator/proposals/{id} │ Full proposal detail         │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/operator/permits        │ Permit registry              │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/audit                   │ Audit event log              │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ GET    │ /v1/actions/policy          │ Action policy table          │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/loops/request           │ Permit issuance              │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/loops/revoke            │ Permit revocation            │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/actions/propose         │ Proposal creation            │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/actions/{id}/decide     │ Approve or deny execution    │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/memory/propose          │ Memory proposal              │
  ├────────┼─────────────────────────────┼──────────────────────────────┤
  │ POST   │ /v1/memory/{id}/decide      │ Memory approve/deny          │
  └────────┴─────────────────────────────┴──────────────────────────────┘





  CLI (scripts/hbar.py)

  Stable. Derives node_id live. Configurable via HBAR_NODEOS_URL. Outputs JSON via --json.

  Shell (scripts/hbar_shell.py)

  Stable REPL. Configurable via HBAR_NODEOS_URL, HBAR_LLM_URL, HBAR_LLM_MODEL. Identity from ~/.hbar/identity.yaml. Context from
  ~/.hbar/context.yaml. Session log at ~/.hbar/log.jsonl.

  ---
  6. Current Continuity and Identity Capabilities

  All state is local to the operator's machine (~/.hbar/). Nothing is stored in NodeOS.

  - Operator identity: ~/.hbar/identity.yaml → operator_id field. Falls back to "operator".
  - Session attribution: every audit action carries operator_id in the --agent-id and --decided-by fields submitted to NodeOS.
  - Session log: append-only JSONL, survives across sessions, provides local audit trail independent of NodeOS.
  - Intent context: last 3 successful write_commit extractions replayed into the LLM prompt automatically.
  - Orientation: focus string and pinned notes persisted in context.yaml, shown at startup and on where.
  - History: history N shows both local session log and NodeOS audit trail together.

  ---
  7. What Has Been Proven

  All of the following have been executed against a live NodeOS instance and produced durable audit records:

  ┌────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────┐
  │                  What                  │                                       Proof                                        │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Full governed push loop                │ Phase 5C: permit 052ed297, preview 03dda811, push e79027cc, commit 91d0f84         │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Non-fast-forward push correctly        │ Phase 6D-C: 409 before git was called; no unsafe write                             │
  │ blocked                                │                                                                                    │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Governed write+commit from natural     │ Phase 6C: permit e0b43f50, write 58029527, commit 34b1083d, resulting commit       │
  │ language                               │ 0615c6d                                                                            │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Preview fails closed on diverged       │ Phase 6D-C + fix bed0ce4: will_fast_forward:false when rev-list fails              │
  │ workspace                              │                                                                                    │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ 9-step write+commit+preview+push plan  │ Phase 6D-A: plan_write_commit_push smoke-tested                                    │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Intent extraction quality              │ 15/15 schema valid, 9/9 refusals correct, 3/3 unsafe paths blocked (test suite in  │
  │                                        │ scripts/test_intent_extraction.py)                                                 │
  ├────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────┤
  │ Operator identity, session log,        │ Phase 7 smoke tests: 7/7 pass                                                      │
  │ context persist                        │                                                                                    │
  └────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────┘




  ---
  8. Known Limitations

  1. NodeOS workspace divergence. The NodeOS container clones the repo into /data/repos/hbar-brain and does not git fetch before git
   diff preview. If the workspace has diverged from origin (i.e. origin has advanced since the last governed push), git ls-remote
  gets the real remote SHA but rev-list fails because that SHA is not in the local object store. bed0ce4 now returns
  will_fast_forward:false in this case, but the ahead/behind counts remain 0/0 rather than accurate values. A git fetch before
  preview would fix this; it is not implemented.
  2. No authentication on NodeOS. The API is CORS-open and assumes trusted network (Docker internal + localhost). Any process with
  network access to port 8001 can submit proposals. Securing this surface requires an auth layer not yet designed.
  3. Single-operator only. The permit and proposal schema includes decided_by and agent_id fields, but no multi-party approval logic
   is implemented. require_2of3_approval from the permit contract is declared but not enforced.
  4. LLM commit message quality. At llama3.2:3b, extracted commit messages tend to echo the intent phrase rather than generating
  conventional commit style. Workflow integrity is unaffected; message quality is the bottleneck.
  5. Shell intent covers only 4 types. write_commit, write_commit_push, push, preview. The commit type is excluded from the shell
  intent system by design (no standalone LLM-driven commit). Other action types (memory, arbitrary connectors) have no intent
  surface.
  6. API service (api/) is not governed. The semantic search / RAG API does not route actions through NodeOS. It is a parallel
  service on the same host, not integrated into the governance chain.
  7. brainfoundry and brainloop are stubs. Present in the repo but not wired to NodeOS or the shell.

  ---
  9. What Is Explicitly Out of Scope

  The following are explicitly deferred and not part of this substrate's current contract:

  - hbar.systems / hbar.world wiring. No external service integration exists.
  - brainfoundry integration. Instance registry exists; it is not connected to the governance kernel.
  - brainloop integration. Loop runner scaffolding exists; it is not connected to NodeOS.
  - Multi-party governance. No second-party approval, delegation, or rotation.
  - External authentication. No API keys, JWT, OAuth, or session tokens on the NodeOS surface.
  - Strain enforcement. The strain contract (STRAIN_CONTRACT.md) and permit types (PERMIT_TYPES.md) are formal specifications;
  strain-level enforcement is not implemented in NodeOS.
  - Embedding / semantic search governance. The api/ service embeddings are not governed through NodeOS.
  - Autonomous loop operation. No component in this branch runs an autonomous agent loop. All actions require an explicit human
  decision.
  - Git fetch before preview. Workspace accuracy across multiple governed sessions is not fully solved.
  - Role administration, delegation, audit export APIs. Described in spec documents but not implemented.

  ---
  10. External Connection Points

  The following describe what kinds of systems may connect to hbar-brain later, at a high level. No design is implied.

  Inbound (consume NodeOS as a kernel):
  - An instantiator that presents structured intent and awaits governed approval sequences
  - A brainloop that runs recurring governed mutation cycles against NodeOS
  - A brainfoundry that coordinates multi-instance registration and routing
  - Any external operator console that reads the /v1/operator/* surface and submits proposals

  Outbound (NodeOS acts on):
  - Any git remote accessible via GITHUB_TOKEN (governed push through workspace)
  - Any filesystem path within the allowlisted write prefix inside the NodeOS workspace volume

  Substrate-to-substrate:
  - A future hbar.systems or hbar.world layer may hold an array of substrate instances. Each instance would be a self-contained
  hbar-brain with its own NodeOS, its own permit space, and its own audit trail. Cross-substrate communication, if any, would
  require explicit cross-strain permits per the strain contract.

  The connection surface is: HTTP on port 8001, JSON payloads, NODEOS_SIGNING_SECRET for permit verification. That is the complete
  integration boundary as it exists today.

✻ Worked for 2m 43s

