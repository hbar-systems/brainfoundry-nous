# KERNEL CONTRACT (HBAR-BRAIN)
Version: 1.0
Status: GOVERNANCE FREEZE — Task 2
Scope: Sovereign execution boundary of the hbar-brain kernel

---

## 0. Normative Language

The keywords MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative requirements.

This document is constitutional.

---

## 1. Scope & Authority

This contract defines and freezes the sovereign execution semantics of hbar-brain.

It governs:

- Command parsing
- Command normalization
- Registry lookup
- Execution class enforcement
- Proposal → Confirm lifecycle
- Permit validation
- Assertion validation
- Error envelope structure
- Rate limiting semantics
- DEV mode semantics

Any semantic deviation requires explicit contract revision.

---

## 2. Deterministic Boot & Readiness Model

### 2.1 Boot Constraints

Boot MUST:
- Perform no network calls
- Perform no model loading
- Perform no external side effects
- Load registry and configuration only

Import-time heavy operations are prohibited.

### 2.2 Health Semantics

/health MUST indicate:
- Process running
- Routing initialized
- Identity secret present
- Registry loaded

It MUST NOT trigger model loading.

### 2.3 Ready Semantics

/ready MAY indicate dependency readiness.
It MUST NOT force-load optional dependencies.

---

## 3. Command Parsing & Normalization

### 3.1 Input

Requests MUST include:
- command (string)

### 3.2 Canonical Normalization

Before registry lookup the kernel MUST:
1. Trim leading/trailing whitespace
2. Collapse multiple whitespace to single space
3. Convert to lowercase

The kernel MUST NOT:
- Fuzzy match
- Prefix match
- Autocorrect
- Infer intent

### 3.3 Unknown Command Invariant

Unknown commands MUST:
- Return error.code = KERNEL_UNKNOWN_COMMAND
- Not mutate state
- Not produce PROPOSED action

---

## 4. Execution Classes

Canonical classes:

- READ_ONLY
- MEMORY_APPEND
- STATE_MUTATION
- EXTERNAL_SIDE_EFFECT

READ_ONLY executes immediately.

All others MUST follow PROPOSE → CONFIRM.

Unknown execution_class MUST fail closed.

---

## 5. Two-Phase Commit

### 5.1 Proposal

Non-READ_ONLY commands MUST return:
- status = PROPOSED
- confirm_token (opaque)

No mutation occurs.

### 5.2 Confirm

Confirm requires:
- valid confirm_token
- valid assertion
- valid permit (if required)

Mutation occurs only after validation passes.

Confirm without token MUST fail deterministically.

---

## 6. Error Envelope (Frozen)

All failures MUST return:

{
  "ok": false,
  "error_version": 1,
  "error": {
    "code": "<ENUM>",
    "message": "<string>",
    "details": {}
  }
}

### 6.1 Structural Requirements

- ok MUST exist
- error_version MUST exist
- error.code MUST be stable enum
- error.message MUST NOT be programmatically relied upon
- error.details if present MUST be object

### 6.2 Versioning Rules

Increment error_version ONLY if:
- Required field removed
- Field renamed
- Structure changed

Adding new error codes does NOT require version bump.

No silent structural mutation permitted.

---

## 7. Permit Model (v1)

Permit MUST include:
- v
- typ
- exp
- aud
- strain_id

Permit valid only if:
- Signature valid
- exp > now
- aud matches client_id
- strain_id matches assertion.strain_id
- typ satisfies execution_class requirements

Permit TTL MUST be enforced strictly.

---

## 8. Assertion Model

Assertion MUST include:
- iss
- aud
- sub
- exp
- trust_tier
- strain_id

Assertion valid only if:
- Signature valid
- exp > now
- exp within allowed max bound
- aud matches kernel audience
- trust_tier sufficient

Assertion expiration MUST always be enforced.

Assertion authorizes permit issuance.
Permit authorizes mutation.

This separation MUST NOT invert.

---

## 9. Rate Limiting

Rate limiting MUST:
- Apply before proposal
- Be deterministic
- Return structured error
- Never partially execute

---

## 10. DEV Mode

DEV_MODE=0: strict deny-by-default.

DEV_MODE=1: only explicitly listed relaxations.

DEV mode MUST NOT silently widen authorization semantics.

---

## 11. Invariants

The following MUST always hold:

- Unknown commands return KERNEL_UNKNOWN_COMMAND
- Confirm without token fails
- Invalid permit fails deterministically
- Permit TTL strictly enforced
- Assertion expiration strictly enforced
- Execution class mismatch blocks confirm
- Error envelope structure always stable
- No silent semantic shifts

---

## 12. Contract Evolution

The following require explicit revision + invariant updates:

- Command normalization changes
- Error envelope changes
- Permit validation changes
- Assertion claim changes
- Two-phase lifecycle changes

Backward compatibility MUST be declared.

