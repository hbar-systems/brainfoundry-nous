# STRAIN CONTRACT (v0.1)

A Strain defines a logical cognitive domain within the hbar.systems ecosystem.
Strains are logical boundaries. Nodes are physical boundaries.
Strains do not automatically trust each other.

All cross-strain interaction is deny-by-default and must be explicitly permitted.

---

## 1. Identity

- `strain_id` (globally unique string, e.g. `hbar.science`)
- `client_ids[]` (authorized service surfaces for this strain)
- `owners[]` (operator_ids with governance authority)
- `operators_allowed[]` (trust tiers allowed to operate this strain)
- `public_surface` (true|false)

Example:

- strain_id: hbar.science
- client_ids:
  - science-web
  - science-api
- owners:
  - HBAR-0001
- operators_allowed:
  - collab
  - operator
  - root
- public_surface: false

---

## 2. Capabilities (Declarative Only)

These define what this strain may request permits for.
This does NOT grant permission automatically.

### Commands
List of command names this strain may attempt to execute via PERMIT.COMMAND_EXECUTE.

Example:
- SCIENCE_PUBLISH
- SCIENCE_EDIT
- SCIENCE_RUN_EXPERIMENT

### Connectors

#### Read
List of allowed connector namespaces this strain may request read permits for.

Example:
- github:repos/hbar.science/**
- local:memory/hbar.science/**

#### Write
List of allowed connector namespaces this strain may request write permits for.

Example:
- github:repos/hbar.science/**
- local:memory/hbar.science/**

---

## 3. Data Classes

Each strain must classify its data.

Allowed values:
- PUBLIC
- INTERNAL
- SENSITIVE
- SEALED

Rules:

- PUBLIC may be exported without redaction.
- INTERNAL requires permit.
- SENSITIVE requires explicit EXPORT_DATA permit.
- SEALED requires multi-party approval.

---

## 4. Data Governance

### Retention Policy

- logs_days
- embeddings_days
- artifacts_days

Example:
- logs_days: 365
- embeddings_days: 180
- artifacts_days: 90

### Export Policy

- export_allowed (true|false)
- allowed_formats[] (json|md|pdf|zip)
- default_redaction_level (none|standard|strict)

### Cross-Strain Sharing

- cross_strain_default: deny
- allowed_targets[] (explicit strain_ids)

---

## 5. Minimum Permit Requirements

The following actions always require permits:

- Any memory append → PERMIT.MEMORY_WRITE
- Any connector read → PERMIT.CONNECTOR_READ
- Any connector write → PERMIT.CONNECTOR_WRITE
- Any command execution beyond READ_ONLY → PERMIT.COMMAND_EXECUTE
- Any data export → PERMIT.EXPORT_DATA

No strain may escalate its own privileges.

---

## 6. Governance Hooks (Future Enforcement)

These fields allow future exit and federation:

- requires_multi_party_for[] (permit types)
- steward_rotation_allowed (true|false)
- exportable (true|false)

---

## Notes

- Strain contracts are declarative.
- Enforcement happens in kernel.
- Strain contracts must be versioned.
- A strain must be operable without founder-specific knowledge.
- Cross-strain dominance is structurally disallowed.
