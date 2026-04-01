# NodeOS Operator Interface Specification v1

## 1. Purpose

This document defines the functional operator interface requirements for NodeOS.

The operator interface is not a cosmetic dashboard.
It is the governed visibility and control surface through which human operators inspect, approve, reject, and audit NodeOS actions.

The interface must preserve fail-closed execution, permit-scoped governance, deterministic lineage discipline, and audit trace visibility.

This specification is multi-actor capable by design, while permitting a single-operator implementation as the initial deployment model.

## 2. Design Principles

- Fail-closed by default
- Visibility before action
- Approval before mutation
- Explicit identity attribution
- Audit-first inspection
- Minimal ambiguity in risk state
- Multi-actor extensibility without premature workflow complexity

## 3. Governance Model

### 3.1 Current Implementation Mode

Initial deployment may operate as a single-operator system.

In this mode:
- one operator may request permits
- one operator may propose actions
- one operator may approve or deny actions
- one operator may inspect audit and node state

### 3.2 Target Architecture Mode

The interface must remain compatible with future multi-actor governance.

Future actors may include:
- operator
- reviewer
- supervisor
- automation agent
- observer

The interface and backing data model must therefore preserve explicit actor attribution for every governed event.

## 4. Core Interface Responsibilities

The operator interface must allow a human operator to:

- inspect pending proposals
- inspect permit state
- inspect current node identity and branch state
- inspect preview lineage and commit binding
- approve or deny governed actions
- inspect execution outcomes
- inspect append-only audit history
- understand current failure conditions without ambiguity

## 5. Required Views

### 5.1 Proposal Queue

The interface must provide a proposal queue showing all pending and recently decided action proposals.

Each proposal entry must display:
- proposal_id
- action_type
- status
- actor_id or proposal owner
- permit_id
- risk class
- creation time
- target repository or resource
- summary of payload

For Git actions, the queue should also display when available:
- branch
- commit_hash
- preview_snapshot
- target paths

The proposal queue must support:
- approve
- deny
- inspect full payload
- inspect linked audit history

### 5.2 Permit Registry

The interface must provide a permit registry showing active, expired, and revoked permits.

Each permit entry must display:
- permit_id
- node_id
- agent_id
- loop_type
- scopes
- reason
- status
- created time
- expiration time

The permit registry should support filtering by:
- status
- scope
- actor
- time window

### 5.3 Audit View

The interface must provide an append-only audit view.

Each audit entry must display:
- event type
- action
- outcome
- timestamp
- actor identity when available
- proposal_id when applicable
- permit_id when applicable
- resource_id when applicable
- summarized metadata

Audit must be searchable by:
- proposal_id
- permit_id
- commit_hash
- action_type
- branch
- actor_id
- time range

### 5.4 Node State View

The interface must provide a node state panel showing current execution context.

At minimum it must display:
- node identity
- current branch
- current HEAD commit
- remote tracking branch state
- ahead/behind state when available
- allowlisted push branches
- service health
- database path
- workspace root or governed repo root

This view exists to reduce hidden state and operator confusion.

### 5.5 Action Policy View

The interface must expose current action policy.

At minimum it must display for each action:
- action_type
- enabled state
- required scopes
- risk level
- whether approval is required

This prevents implicit governance assumptions.

## 6. Proposal Detail Requirements

Selecting a proposal must open a detailed inspection view.

This view must show:
- raw payload
- normalized payload
- linked permit
- linked actor identity
- risk classification
- expected effect
- validation failures if any
- execution result if already decided

For Git proposals:

### 6.1 Git Diff Preview Detail

Display:
- repository
- branch
- local_head
- remote_head
- remote branch existence
- ahead/behind state
- will_fast_forward flag
- status_porcelain
- diff_stat
- diff text or truncation notice

### 6.2 Git Commit Detail

Display:
- commit message
- explicit paths
- preview_snapshot binding
- resulting commit hash after approval/execution
- execution stdout summary

### 6.3 Git Push Detail

Display:
- branch
- remote
- commit_hash
- preview_snapshot
- remote validation state
- push outcome

## 7. Identity Model Requirements

The interface must preserve explicit identity fields even if the first implementation uses one operator.

Fields that must be modeled:
- actor_id
- actor_role
- node_id
- proposal_owner
- permit_owner
- decided_by
- decision_origin

For initial single-operator deployment, these may all resolve to the same operator identity.

The schema must not assume permanent single-actor governance.

## 8. Decision Workflow Requirements

Approval controls must be explicit.

For each pending proposal, the interface must support:
- Approve
- Deny

Each decision must record:
- proposal_id
- permit_id used for decision
- decided_by
- decision
- decision note
- timestamp

No proposal may mutate state without explicit approval if policy requires approval.

## 9. Risk Signaling

The interface must surface risk clearly.

At minimum:
- LOW
- MEDIUM
- HIGH

Risk must be displayed near:
- action_type
- approval controls
- execution outcome

High-risk actions such as `git_commit` and `git_push` must be visually distinct from low-risk actions such as preview or read-only inspection.

## 10. Failure Clarity Requirements

The interface must expose exact failure reasons where possible.

Examples:
- permit expired
- permit scope missing
- preview required
- branch not allowlisted
- HEAD mismatch
- remote changed since preview
- git push auth failed
- non-fast-forward rejection

Failure presentation must prefer precise system language over vague generic error banners.

## 11. Single-Operator MVP Scope

The first implementation may limit itself to:

- proposal queue
- proposal detail view
- approve/deny controls
- permit registry
- audit view
- node state panel
- action policy panel

The first implementation does not require:
- multi-step approval chains
- delegation workflows
- actor switching UI
- collaboration messaging
- role administration

## 12. Multi-Actor Compatibility Requirements

Even if the MVP is single-operator, the following assumptions must remain false in the code and data model:

- only one actor will ever exist
- proposer and approver are always the same
- permits belong to one universal operator
- audit does not require actor attribution
- one node equals one human identity

## 13. Recommended Data Surfaces

The interface should read from existing and emerging system surfaces, including:

- `/v1/identity`
- `/v1/actions`
- `/v1/actions/{proposal_id}`
- `/v1/actions/{proposal_id}/commit`
- `/v1/actions/policy`
- `/v1/audit`
- `/v1/audit/events`
- loop permit tables and permit status endpoints
- future memory proposal endpoints

## 14. Non-Goals

This specification does not define:
- visual styling
- frontend framework choice
- database schema migration details
- memory semantics beyond visibility hooks
- autonomous approval logic

## 15. Versioning

This document defines Operator Interface Specification v1.

Breaking changes to operator workflow semantics, approval model, or identity assumptions require a version increment.
