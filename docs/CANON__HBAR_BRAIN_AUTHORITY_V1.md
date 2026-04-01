# HBAR-BRAIN AUTHORITY INTERFACE CANON V1

This document defines the canonical interface contract for the hbar-brain authority command endpoint. It establishes invariants, guarantees, and boundaries that MUST be preserved across all implementations.

## 1. Scope

This canon covers the hbar-brain authority interface specifically, which provides a command submission and confirmation workflow. It builds upon the NodeOS authority service (external canonical reference in NODEOS_SUMMARY.md and NODEOS_INTEGRATION.md) but focuses on the brain-specific command authority layer.

## 2. Endpoint Contract

### POST /v1/brain/command

#### Request Format
```json
{
  "command": "string",            // Required: Command to be proposed/confirmed
  "confirm_token": "string|null", // Optional: Token for confirmation flow
  "client_id": "string|null"      // Optional: Client identifier for tracking
}
```

#### Response Format - PROPOSE Flow (confirm_token is null)
```json
{
  "status": "PROPOSED",
  "token": "CONFIRM-xxxxxxxx",    // Confirmation token with CONFIRM- prefix
  "ttl_seconds": 1800,            // Token validity period (30 minutes)
  "instructions": "string"        // Human-readable next steps
}
```

#### Response Format - CONFIRM Flow (confirm_token provided)
```json
{
  "status": "CONFIRMED",
  "message": "Command confirmed successfully",
  "executed": false,              // Optional in v0.2, required in v0.3+
  "note": "NO EXECUTION IN V0"    // Optional in v0.2, required in v0.3+
}
```

#### Error Responses
- 401: Invalid API key
- 403: Confirmation failed - MUST include a machine-readable "reason" field with one of: "token_not_found", "token_expired", or "command_mismatch"
- 500: Internal server error

## 3. Core Invariants

### MUST
- Generate and verify tokens server-side only
- Implement fail-closed security (deny by default)
- Maintain append-only audit logs
- Require explicit confirmation via token for all commands
- Normalize commands before comparison
- Return consistent response formats

### MUST NEVER
- Execute commands that modify system state in v0.x
- Allow token forgery or client-side token generation
- Overwrite or delete audit logs
- Accept a command without proper confirmation
- Bypass authentication when API key is configured

### Definition: "Execution"
In this context, "execution" means any action that:
1. Modifies persistent system state
2. Affects other users or services
3. Changes configuration or permissions

Read-only operations that do not modify state may be permitted in future versions while maintaining the no-execution guarantee for v0.x.

## 4. Token Semantics

- **Format**: All tokens MUST begin with `CONFIRM-` prefix followed by an 8-character hexadecimal string
- **TTL**: 1800 seconds (30 minutes) from creation
- **Command Normalization**:
  - Trim leading/trailing whitespace
  - Collapse multiple whitespace characters to single spaces
  - Convert to lowercase
- **Verification Failures**:
  - Token not found: Return 403 with reason "token_not_found"
  - Token expired: Return 403 with reason "token_expired"
  - Command mismatch: Return 403 with reason "command_mismatch"

## 5. Logging Contract

### Paths
- Proposals: `ops/audit/proposals.jsonl`
- Audit Log: `ops/audit/command_audit.jsonl`

### Guarantees
- All logs MUST be append-only
- Logs MUST be created if they don't exist
- Each log entry MUST be a complete JSON object on a single line

### Required Fields
- **proposals.jsonl**:
  - `timestamp`: ISO 8601 datetime
  - `token`: Confirmation token
  - `normalized_command`: Normalized command string
  - `raw_command`: Original command string
  - `client_id`: Client identifier (if provided)

- **command_audit.jsonl**:
  - `timestamp`: ISO 8601 datetime
  - `client_id`: Client identifier (if provided)
  - `raw_command`: Original command string
  - `normalized_command`: Normalized command string
  - `confirm_token`: Token (if in confirmation flow)
  - `action`: "proposal_created" or "confirm_attempt"
  - `decision`: For confirmation attempts, outcome (e.g., "confirm_accepted_v0_no_execute", "confirm_rejected")
  - `reason`: Required only when decision indicates rejection (e.g., "token_expired")

## 6. Authentication Contract

- **Environment Variable**: `HBAR_BRAIN_API_KEY`
- **Behavior**:
  - If env var is set (non-empty): Require valid key; if missing/wrong → 401
  - If env var not set: Allow all requests (dev mode)
- **Accepted Headers** (either is sufficient):
  - `X-API-Key: <key>`
  - `Authorization: Bearer <key>`

## 7. Version Boundaries

### v0.2 (Current)
- PROPOSE/CONFIRM workflow
- Audit-only, no execution
- Authentication optional

### v0.3 (Future)
- May allow read-only command whitelist
- MUST still maintain PROPOSE/CONFIRM workflow
- MUST NOT allow state mutation
- MUST explicitly mark responses with `"effect": "read_only"`

### v1.0+ (Future)
- Any state mutation requires:
  1. Explicit version bump
  2. Canon update
  3. New guarantees and boundaries
