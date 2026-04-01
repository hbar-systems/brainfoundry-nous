# NodeOS Operator API Specification v1

## 1. Purpose

This document defines the operator-facing API layer for NodeOS.

This layer is not the governed execution kernel itself.
It is a read-oriented aggregation and normalization surface designed to support the operator interface.

Its purpose is to present NodeOS state in a form suitable for human governance without forcing the UI to reconstruct system meaning from low-level kernel endpoints.

The operator API must not weaken fail-closed execution, permit-scoped control, deterministic lineage enforcement, or append-only audit discipline.

## 2. Design Goals

- Provide a stable operator-facing backend contract
- Reduce frontend dependence on low-level endpoint choreography
- Preserve exact proposal, permit, and audit identifiers
- Normalize kernel state into operator-readable views
- Keep mutation semantics delegated to governed action endpoints unless explicitly promoted
- Support single-operator MVP while preserving multi-actor-compatible fields

## 3. Architectural Position

The operator API sits above the governed kernel and below the operator interface.

It should:
- aggregate existing NodeOS state
- normalize read models
- expose operator-ready summaries
- avoid altering core approval or execution semantics

It should not:
- bypass approval requirements
- invent hidden state
- mutate governed resources outside existing permit and proposal rules
- collapse audit lineage into opaque UI-only abstractions

## 4. Initial Scope

The first version of the operator API should be read-heavy.

It should provide normalized access to:
- operator overview state
- proposals
- proposal detail
- permits
- audit events
- node state
- action policy

Mutation may remain delegated to existing endpoints such as:
- `/v1/actions/propose`
- `/v1/actions/{proposal_id}/decide`
- `/v1/loops/request`
- `/v1/loops/revoke`

## 5. Endpoint Set

### 5.1 GET /v1/operator/overview

Returns a compact system overview for the operator landing view.

Response should include:
- node identity summary
- current branch and HEAD
- remote tracking summary when available
- count of pending proposals
- count of active permits
- count of recent failed actions
- count of recent approved actions
- service health summary
- database path
- governed repo root or workspace root

Example response shape:

    {
      "ok": true,
      "node": {
        "node_id": "nodeos-dev",
        "health": "ok"
      },
      "repo": {
        "branch": "v0.17-instantiator",
        "head": "cba1133c18db4c0d03c1f0a0927dbddcc627821c",
        "remote_branch": "origin/v0.17-instantiator",
        "ahead": 1,
        "behind": 0
      },
      "counts": {
        "pending_proposals": 2,
        "active_permits": 5,
        "recent_failures": 1,
        "recent_approvals": 8
      },
      "paths": {
        "db_path": "/data/nodeos.db",
        "workspace_root": "/data/repos"
      }
    }

### 5.2 GET /v1/operator/proposals

Returns proposals in operator-oriented normalized form.

Supported query parameters:
- `status`
- `action_type`
- `limit`
- `offset`
- `sort`
- `descending`

Each proposal item should include:
- proposal_id
- permit_id
- action_type
- status
- created_at
- decided_at
- decided_by
- decision_note
- actor_id when available
- actor_role when available
- risk
- summary
- target resource summary

For Git actions, include when available:
- repo
- branch
- commit_hash
- preview_snapshot
- paths

Example response shape:

    {
      "ok": true,
      "items": [
        {
          "proposal_id": "uuid",
          "permit_id": "uuid",
          "action_type": "git_push",
          "status": "PENDING",
          "created_at": "2026-03-08T18:00:00Z",
          "decided_at": null,
          "decided_by": null,
          "risk": "HIGH",
          "summary": "Push commit to allowlisted branch",
          "target": {
            "repo": "/data/repos/hbar-brain",
            "branch": "v0.17-instantiator",
            "commit_hash": "fullsha"
          }
        }
      ],
      "total": 1
    }

### 5.3 GET /v1/operator/proposals/{proposal_id}

Returns full normalized proposal detail.

Must include:
- full stored payload
- normalized payload
- permit linkage
- action policy summary
- risk classification
- proposal status
- decision metadata
- execution result when available
- linked audit references when available

For Git preview proposals, include:
- local_head
- remote_head
- ahead
- behind
- will_fast_forward
- status_porcelain
- diff_stat
- diff text or truncation metadata

For Git commit proposals, include:
- commit message
- paths
- preview_snapshot
- resulting commit hash if executed

For Git push proposals, include:
- branch
- remote
- commit_hash
- preview_snapshot
- execution outcome

### 5.4 GET /v1/operator/permits

Returns permit registry view.

Supported query parameters:
- `status`
- `scope`
- `agent_id`
- `node_id`
- `limit`
- `offset`
- `sort`
- `descending`

Each permit item should include:
- permit_id
- node_id
- agent_id
- loop_type
- scopes
- reason
- trace_id
- status
- created_at when available
- expires_at_unix
- seconds_remaining when active

Example response shape:

    {
      "ok": true,
      "items": [
        {
          "permit_id": "uuid",
          "node_id": "nodeos-dev",
          "agent_id": "operator",
          "loop_type": "governed_git",
          "scopes": ["git.preview"],
          "reason": "Preview operator spec",
          "status": "ACTIVE",
          "expires_at_unix": 1773002065,
          "seconds_remaining": 3120
        }
      ],
      "total": 1
    }

### 5.5 GET /v1/operator/audit

Returns audit events in operator-readable normalized form.

Supported query parameters:
- `event_type`
- `action`
- `outcome`
- `proposal_id`
- `permit_id`
- `resource_id`
- `limit`
- `offset`
- `sort`
- `descending`

Each audit item should include:
- event_type
- action
- outcome
- timestamp
- actor_id when available
- proposal_id when available
- permit_id when applicable
- resource_id when applicable
- metadata summary
- raw metadata optionally behind a flag

This endpoint is intended for operator browsing, not raw archival export.

### 5.6 GET /v1/operator/node-state

Returns current NodeOS execution context.

Must include:
- node identity
- service health
- current branch
- current HEAD
- remote tracking branch
- ahead/behind
- allowlisted push branches
- database path
- workspace root
- governed repos summary when applicable

Example response shape:

    {
      "ok": true,
      "node": {
        "node_id": "nodeos-dev",
        "health": "ok"
      },
      "git": {
        "branch": "v0.17-instantiator",
        "head": "fullsha",
        "remote_branch": "origin/v0.17-instantiator",
        "ahead": 0,
        "behind": 0,
        "allowlisted_push_branches": ["v0.17-instantiator"]
      },
      "paths": {
        "db_path": "/data/nodeos.db",
        "workspace_root": "/data/repos"
      }
    }

### 5.7 GET /v1/operator/action-policy

Returns operator-facing action policy summary.

Each action entry should include:
- action_type
- enabled
- required_scopes
- risk
- requires_approval

This endpoint may be a thin normalized wrapper around the existing policy endpoint.

## 6. Normalization Rules

The operator API must preserve original identifiers:
- proposal_id
- permit_id
- commit_hash
- resource_id

The operator API may add:
- summaries
- counts
- normalized field names
- convenience status indicators
- derived timing fields

The operator API must not:
- rewrite IDs
- hide approval status
- hide failure reason
- invent success semantics not present in kernel state

## 7. Read vs Mutate Boundary

The operator API v1 should be read-first.

Read endpoints:
- `/v1/operator/overview`
- `/v1/operator/proposals`
- `/v1/operator/proposals/{proposal_id}`
- `/v1/operator/permits`
- `/v1/operator/audit`
- `/v1/operator/node-state`
- `/v1/operator/action-policy`

Mutating actions remain delegated to existing governed kernel endpoints until explicitly promoted.

This avoids accidental duplication of governance semantics.

## 8. Failure Semantics

Operator API endpoints must return precise failure states.

Examples:
- `404` when referenced proposal or permit does not exist
- `400` when query parameters are invalid
- `500` only for genuine server faults
- normalized `detail` messages preserved where useful

Read aggregation should degrade gracefully where possible.
If one optional subcomponent fails, the response may include partial data only if the missing segment is clearly marked.

## 9. Single-Operator MVP Compatibility

The first implementation may assume one visible operator in the UI.

However, responses should preserve fields for future expansion:
- actor_id
- actor_role
- proposal_owner
- permit_owner
- decided_by
- decision_origin

These may currently default to the same identity.

## 10. Multi-Actor Compatibility

The operator API must not structurally assume:
- one permanent operator
- proposer equals approver
- one node equals one human
- audit entries do not need actor attribution

Future multi-actor governance must be additive, not destructive to v1 semantics.

## 11. Suggested Implementation Strategy

The first implementation should be a thin backend read-model layer.

Suggested approach:
- reuse existing DB tables
- reuse existing kernel endpoints where appropriate
- compute normalized summaries server-side
- avoid changing approval execution paths in this phase

Priority order:
1. `/v1/operator/overview`
2. `/v1/operator/proposals`
3. `/v1/operator/proposals/{proposal_id}`
4. `/v1/operator/permits`
5. `/v1/operator/node-state`
6. `/v1/operator/action-policy`
7. `/v1/operator/audit`

## 12. Non-Goals

This specification does not define:
- frontend rendering
- authentication model
- role administration
- delegation workflows
- memory state projections
- autonomous action logic

## 13. Versioning

This document defines Operator API Specification v1.

Breaking changes to endpoint semantics, field meaning, or governance boundaries require a version increment.
