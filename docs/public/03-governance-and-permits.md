# Governance and permits

This document describes BrainKernel — the governance kernel that sits inside every brain node. It explains the PROPOSE → CONFIRM flow, the permit model, and why consent-gated memory matters.

## Why governance

A brain is an AI system with the ability to act on your behalf, with your identity, against your data. That capability is the point. It is also the attack surface.

Without a governance boundary:

- A prompt injection in a chat message could trigger a destructive command.
- A compromised credential could mutate the brain's identity or wipe its memory.
- An autonomously running agent would have no structural check on its own actions.

BrainKernel is the structural answer. It sits between intent and execution. No mutation — to system state, persona, memory, connectors, or federation peers — happens in a single step.

## PROPOSE → CONFIRM

Every command hits the kernel in one of two forms: a proposal, or a confirmation with a token.

### Read-only commands

`help`, `list`, `show`, and other read verbs execute immediately. No token is needed, no proposal is issued, no audit entry beyond the query log is written.

### Mutating commands

`create`, `update`, `delete`, `execute`, and any verb that changes state enters the two-phase flow.

**Phase one — PROPOSE.** The command is parsed, normalized, and looked up in the command registry. The kernel returns a structured response:

```
INTENT:   interpreted meaning of the command
PLAN:     proposed plan of action
RISKS:    assessment of potential risks
OUTPUT:   (empty — nothing has run)
CONFIRMATION:
  status: PROPOSED
  token:  CONFIRM-<opaque-identifier>
  instructions: re-run with --confirm <token>
```

Nothing has mutated. The kernel has only described what it would do.

**Phase two — CONFIRM.** The caller re-submits the same command with the token:

```
<verb> <noun> [params] --confirm CONFIRM-<opaque-identifier>
```

The kernel verifies the token, checks the permit authorizing the action, validates the assertion that backs the permit, and only then executes.

Invalid or replayed tokens fail deterministically. Confirmation without a token fails. Confirmation with a token for a different command fails. Expired tokens fail.

### Why the asymmetry works

Proposals are cheap. An injected prompt can produce a proposal. That is fine — the proposal has no effect.

Confirmations are expensive. To confirm, you need the specific single-use token the kernel just issued for that specific proposal. The token appears only in the proposal response, which went to the original caller, not to an attacker who injected text into a chat.

An attacker who can inject prompts cannot also inject confirmations, because the token they would need was never given to them. The asymmetry between the two phases is the enforcement mechanism.

## Permits

Permits are the unit of authorization the kernel uses to decide whether a proposal can be confirmed. Every mutation requires a permit. The model cannot invent permits.

A permit is a signed, time-bounded, audience-bound token with a declared type. The canonical types:

| Permit type | Authorizes |
|---|---|
| `MEMORY_WRITE` | Appending memory to the node substrate |
| `CONNECTOR_READ` | Reading from an external connector (repo, docs, storage) |
| `CONNECTOR_WRITE` | Writing to an external connector |
| `COMMAND_EXECUTE` | Executing a specific named command |
| `EXPORT_DATA` | Exporting data out of the node |

Every permit declares a strain ID, a subject, an audience, a TTL, an issued-at and expires-at timestamp, and a reason. Permits carry constraints — rate limits, max bytes, path globs, data classes (public, internal, sensitive, sealed).

High-privilege actions require multi-party approval: any connector write to a sealed path, any export of sensitive or sealed data, any command that modifies identity or other permits.

## Loop permits

Loop permits are a specific permit type that gates the chat loop.

Before any `/chat/completions` or `/chat/rag` call, the API must present a valid loop permit and its caller-bound HMAC token. The token is returned exactly once, from `POST /v1/loops/request`, and is bound to the agent that requested it. A `permit_id` observed in a log cannot be replayed without the accompanying token.

Loop permits have a lifecycle:

```
REQUEST → ACTIVE → (expires) → INACTIVE
```

Requests without a valid permit are refused. Permits expire on their declared schedule; expired permits cannot be reused.

This is why the first line of every chat path is a permit check. The kernel is not optional.

## Audit log

Every kernel command, proposal, confirmation, and model call is written to an append-only audit log. Existing entries are never modified, truncated, or deleted. This is a hard invariant — the log is the proof of what was proposed, when, and whether it was confirmed or denied.

The audit log serves three purposes:

1. **Forensics.** If something unexpected mutated the brain, the log shows what command ran, what permit authorized it, what assertion backed the permit, and when.
2. **Provenance.** Memory written via the kernel carries a chain back to the command that wrote it. The brain can answer "where did this claim come from."
3. **Governance proof.** The log is the brain's public statement that its own activity is accountable. Nothing happens out of band.

## Error envelope

All kernel errors use a single stable envelope:

```
{
  "ok": false,
  "error_version": 1,
  "error": {
    "code": "<STABLE_ENUM>",
    "message": "<human-readable summary>",
    "details": {}
  }
}
```

Callers program against `error.code`. Messages are for humans; they can change. Structural changes to the envelope require a version bump. New error codes do not.

A tool that reads kernel errors today keeps working across any number of feature releases — only a renamed field or a removed field counts as breaking.

## Execution classes

Every command declares an execution class:

- **READ_ONLY** — executes immediately, no token needed.
- **MEMORY_APPEND** — writes to memory, requires proposal and `MEMORY_WRITE` permit.
- **STATE_MUTATION** — changes brain state, requires proposal and an appropriate permit.
- **EXTERNAL_SIDE_EFFECT** — performs an action in the outside world (git push, network write), requires proposal and a connector-write or command-execute permit.

A command's class determines the gate it must pass. The kernel refuses to execute a command whose class does not match the permit presented.

## What governance does not do

Governance is a structural boundary. It is not a content filter. It does not prevent the model from producing a bad answer, a biased answer, or a factually wrong answer. It prevents the brain from silently taking actions the owner did not authorize.

Content quality is a model-level concern. Action safety is a kernel-level concern. Governance sits at the second boundary.

## Why this matters for federation

When two brains talk, the receiving brain needs to know that an inbound action was authorized by the other brain's owner — not by a rogue node, an injected message, or a replay. The PROPOSE → CONFIRM model, combined with loop permits and federation identity, is what makes brain-to-brain action trustworthy rather than just technically possible.

The next document describes the federation protocol that carries these assertions between brains.
