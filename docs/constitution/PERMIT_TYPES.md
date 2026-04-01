# PERMIT TYPES (v0.1)

All permits are **deny-by-default** and must be explicit, bounded, and auditable.
Permits are capabilities issued by the Authority Root and verified by the kernel.
The model cannot invent permits.

---

## Core Grammar

`PERMIT.<TYPE>(strain_id, scope, ttl_seconds, reason, constraints...)`

### Required fields (all permits)
- `permit_id` (unique, e.g. UUID or ULID)
- `permit_type` (one of the types below)
- `strain_id`
- `subject` (operator_id / service_id the permit is issued to)
- `audience` (client_id / service that may present it)
- `ttl_seconds`
- `issued_at` (UTC ISO8601)
- `expires_at` (UTC ISO8601)
- `reason` (human readable)

### Global constraints (optional)
- `rate_limit` (e.g. `{"per_minute": 10}`)
- `max_bytes`
- `max_items`
- `require_mfa` (bool)
- `require_2of3_approval` (bool)
- `tags` (array of strings)

---

## Permit Types

### 1) MEMORY_WRITE
Grants permission to append memory into the node memory substrate.

**Scope**
- `scope` = namespace/path-like keyspace (e.g. `memory/hbar.science/*`)

**Constraints**
- `keys_allowed[]`
- `max_bytes`
- `max_items`
- `data_class` (PUBLIC | INTERNAL | SENSITIVE | SEALED)

---

### 2) CONNECTOR_READ
Grants permission to read from an external connector surface (repos, docs, storage).

**Scope**
- `scope` = connector name + path glob (e.g. `github:repos/hbar.science/**`)

**Constraints**
- `path_glob`
- `max_files`
- `max_bytes`
- `data_class`

---

### 3) CONNECTOR_WRITE
Grants permission to write to an external connector surface.

**Scope**
- `scope` = connector name + path glob (e.g. `github:repos/hbar.ink/**`)

**Constraints**
- `path_glob`
- `max_files`
- `max_bytes`
- `require_review` (true|false)
- `data_class`

---

### 4) COMMAND_EXECUTE
Grants permission to execute a specific command (usually STATE_MUTATION or EXTERNAL_SIDE_EFFECT).

**Scope**
- `scope` = command name (e.g. `SCIENCE_PUBLISH`, `INK_RENDER`, `NODE_RECONFIGURE`)

**Constraints**
- `params_schema_hash` (hash of allowed schema for params)
- `rate_limit`
- `max_bytes`
- `require_2of3_approval` (for high privilege)

---

### 5) EXPORT_DATA
Grants permission to export data out of the node.

**Scope**
- `scope` = export target (e.g. `EXPORT:strain=hbar.science,class=INTERNAL`)

**Constraints**
- `format` (json|md|pdf|zip)
- `redaction_level` (none|standard|strict)
- `max_bytes`
- `data_class`
- `require_2of3_approval` (for SENSITIVE/SEALED)

---

## High-Privilege Policy (v0.1)

The following **must** require `require_2of3_approval=true` (or equivalent governance gate):

- Any `CONNECTOR_WRITE` to `SEALED` paths
- Any `EXPORT_DATA` of `SENSITIVE` or `SEALED`
- Any `COMMAND_EXECUTE` that modifies infra / identity / permits
- Any permit with `ttl_seconds` above a configured maximum

---

## Kernel Enforcement Rules (v0.1)

Kernel must verify on every privileged request:

1. Permit exists (no implicit permit).
2. Permit not expired.
3. Permit `audience` matches presenting client_id.
4. Permit `strain_id` matches request context.
5. Constraints enforced (size, rate, paths, schema hash).
6. Decision is logged to append-only audit.

---

## Notes

- Permits are intended to be short-lived and specific.
- The system must be designed so the Architect can later step back:
  power is issued procedurally, not personally.
