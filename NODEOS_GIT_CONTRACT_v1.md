# NodeOS Git Governance Contract v1

## 1. Purpose

This document defines the deterministic, fail-closed governance rules under which NodeOS performs Git actions.

NodeOS does not perform implicit Git mutations.
All Git mutations must be explicitly proposed, permitted, approved, executed, and audited.

## 2. Design Principles

- Fail-closed execution
- Deterministic lineage binding
- Permit-scoped authority
- Preview-before-mutation
- Remote safety enforcement
- Auditable action trace

## 3. Action Model

### 3.1 Propose → Approve → Execute

No direct Git mutation is allowed outside the governed lifecycle.

All Git mutations must:
- Be proposed
- Receive scoped permit authorization
- Be approved
- Execute within permit constraints
- Be recorded in the audit log

## 4. Permit Model

Every governed Git action requires a valid, unexpired permit.

A permit must define:
- action type
- target branch
- repository
- scope constraints
- expiration window

Typical required scopes include:
- `git.preview`
- `git.commit`
- `git.push`

Permit-governed actions include:
- commit
- push
- rebase
- branch operations

Permits:
- are time-bound (`ttl_seconds`)
- are validated at propose-time
- are validated again at execute-time
- must not contain secret material

## 5. Diff Preview Rule

Before any governed mutation dependent on repository state, a `git_diff_preview` must be proposed and approved.

At minimum, before any push:
- a `git_diff_preview` must exist
- the preview must bind branch
- the preview must bind commit hash
- the preview must bind local/remote divergence state

The preview snapshot ID must be supplied in `git_push`.

No preview → push rejected.

## 6. Commit Rules

A governed commit must:
- specify explicit paths
- reference an approved preview snapshot
- produce a full 40-character SHA-1 hash
- return a commit hash that matches repository `HEAD`

Short hashes are invalid.

If the approved preview does not match the execution target, commit execution must fail closed.

## 7. Push Rules

A governed push executes only if:
- `commit_hash` is a full 40-character hexadecimal SHA-1
- `commit_hash` matches local `HEAD`
- an approved preview snapshot exists
- the preview commit matches the push commit
- the target branch is in `NODEOS_PUSH_BRANCH_ALLOWLIST`
- remote fast-forward is possible
- required GitHub authentication token is present via environment injection

Any violation → push rejected.

## 8. Divergence Handling

If local and remote branches diverge:
- push is rejected

Operator must:
- fetch remote
- rebase or merge
- generate a new preview
- submit a new push proposal

No force push is permitted under this contract.

## 9. Secrets Handling

- No secrets may be committed to the repository
- GitHub PAT must be injected via environment variable
- No implicit credential fallback is allowed
- Secret rotation must be supported operationally
- No permit may contain secret material

## 10. Audit Guarantees

All governed actions must record:
- permit_id
- proposal_id
- action_type
- payload
- permit scope
- decision metadata
- execution result
- commit hash, where applicable
- timestamp

Actor identity is a required future expansion field.

Audit log is append-only.

## 11. Failure Conditions

NodeOS must fail closed on:
- scope violation
- missing preview
- invalid commit hash
- preview/target mismatch
- branch policy violation
- remote divergence without reconciliation
- missing required authentication material

## 12. Versioning

This document defines Git Governance Contract v1.

Any breaking semantic change to these rules requires a contract version increment.
