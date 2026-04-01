from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Tuple, Any, Set

class ExecutionClass(str, Enum):
    READ_ONLY = "read_only"
    STATE_MUTATION = "state_mutation"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    MEMORY_APPEND = "memory_append"


@dataclass(frozen=True)
class CommandSpec:
    command: str  # canonical command key (e.g. "version", "audit tail")
    execution_class: ExecutionClass
    description: str

    # v0.7 execution contract (fail-closed)
    allowed_fields: Set[str]  # command-specific JSON fields (excluding: command, client_id)
    required_fields: Set[str]
    idempotent: bool = True
    audit: bool = True
    requires_confirm: bool = False


# Fail-closed registry: every allowed command must appear here.
REGISTRY: Dict[str, CommandSpec] = {
    "health": CommandSpec(
        command="health",
        execution_class=ExecutionClass.READ_ONLY,
        description="Check system health status (read-only).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "whoami": CommandSpec(
        command="whoami",
        execution_class=ExecutionClass.READ_ONLY,
        description="Display brain identity and version (read-only).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "status": CommandSpec(
        command="status",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show detailed service status (read-only).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "help": CommandSpec(
        command="help",
        execution_class=ExecutionClass.READ_ONLY,
        description="List available read-only commands (read-only).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "version": CommandSpec(
        command="version",
        execution_class=ExecutionClass.READ_ONLY,
        description="Return server build/version metadata (read-only).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "audit tail": CommandSpec(
        command="audit tail",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show last N audit entries (read-only). Usage: audit tail N (default 50, max 1000).",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "echo": CommandSpec(
        command="echo",
        execution_class=ExecutionClass.READ_ONLY,
        description="Echo back provided text.",
        allowed_fields={"payload"},
        required_fields={"payload"},
    ),
    "memory append": CommandSpec(
        command="memory append",
        description="DEV: append a memory event (gated by assertion; not enabled unless DEV flag)",
        execution_class=ExecutionClass.MEMORY_APPEND,
        allowed_fields={"command", "client_id", "payload", "confirm_token"},
        required_fields={"command", "client_id", "payload"},
    ),
    "permit issue": CommandSpec(
        command="permit issue",
        execution_class=ExecutionClass.READ_ONLY,
        description="Issue a signed permit token (requires root assertion). Usage: permit issue <typ> <ttl_seconds> <reason>",
        allowed_fields=set(),
        required_fields=set(),
    ),

}


def parse_normalized_command(normalized_command: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Parse normalized command string into:
      - command_key: a canonical key used for registry lookup
      - params: structured params (e.g. {"n": 50})
    Fail-closed: return (None, {}) if command can't be parsed.
    """
    if not normalized_command:
        return None, {}

    if normalized_command == "memory append":
        return "memory append", {}

    parts = normalized_command.strip().split()
    if not parts:
        return None, {}

    # Exact single-word commands
    if len(parts) == 1:
        return parts[0], {}

    # "audit tail [N]"
    if len(parts) >= 2 and parts[0] == "audit" and parts[1] == "tail":
        n = 50
        if len(parts) >= 3:
            try:
                n = int(parts[2])
            except ValueError:
                n = 50
        n = max(1, min(n, 1000))
        return "audit tail", {"n": n}

    # "permit issue <typ> <ttl> <reason...>"
    if len(parts) >= 3 and parts[0] == "permit" and parts[1] == "issue":
        permit_typ = parts[2]
        ttl = 900
        reason = "issued"
        if len(parts) >= 4:
            try:
                ttl = int(parts[3])
            except ValueError:
                ttl = 900
        if len(parts) >= 5:
            reason = " ".join(parts[4:])
        return "permit issue", {"typ": permit_typ, "ttl": ttl, "reason": reason}


    # Unknown multi-word command
    return None, {}


def get_command_spec(command_key: str) -> Optional[CommandSpec]:
    if not command_key:
        return None
    return REGISTRY.get(command_key.strip())




# Command-specific payload allowlists (fail-closed)
PAYLOAD_ALLOWED_FIELDS = {
    "memory append": {"text"},
    "echo": {"text"},
}

PAYLOAD_REQUIRED_FIELDS = {
    "memory append": {"text"},
    "echo": {"text"},
}



def validate_command_payload(command_key: str, payload: Dict[str, Any]) -> None:
    """
    Fail-closed validation for command-specific JSON payload fields.
    payload here should EXCLUDE global keys: 'command', 'client_id'.
    """
    spec = get_command_spec(command_key)
    if spec is None:
        raise KeyError(command_key)

    allowed = PAYLOAD_ALLOWED_FIELDS.get(command_key, set())
    required = PAYLOAD_REQUIRED_FIELDS.get(command_key, set())

    unknown = set(payload.keys()) - allowed
    if unknown:
        raise ValueError(f"unknown_fields:{sorted(list(unknown))}")

    missing = required - set(payload.keys())
    if missing:
        raise ValueError(f"missing_fields:{sorted(list(missing))}")

# ── hbar custom commands ──────────────────────────────────────────────────────
REGISTRY.update({
    "remember": CommandSpec(
        command="remember",
        execution_class=ExecutionClass.READ_ONLY,
        description="Store a memory.",
        allowed_fields={"content", "tags"},
        required_fields={"content"},
        idempotent=False,
        audit=True,
    ),
    "recall": CommandSpec(
        command="recall",
        execution_class=ExecutionClass.READ_ONLY,
        description="Search memories.",
        allowed_fields={"query", "synthesize"},
        required_fields={"query"},
    ),
    "forget": CommandSpec(
        command="forget",
        execution_class=ExecutionClass.READ_ONLY,
        description="Delete a memory by id.",
        allowed_fields={"id"},
        required_fields={"id"},
        idempotent=False,
        audit=True,
    ),
    "memories": CommandSpec(
        command="memories",
        execution_class=ExecutionClass.READ_ONLY,
        description="List recent memories.",
        allowed_fields={"limit", "tag"},
        required_fields=set(),
    ),
    "context.show": CommandSpec(
        command="context.show",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show active context.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "context.set": CommandSpec(
        command="context.set",
        execution_class=ExecutionClass.READ_ONLY,
        description="Set a context key.",
        allowed_fields={"key", "value"},
        required_fields={"value"},
        idempotent=True,
        audit=True,
    ),
    "context.clear": CommandSpec(
        command="context.clear",
        execution_class=ExecutionClass.READ_ONLY,
        description="Clear context.",
        allowed_fields={"key"},
        required_fields=set(),
        idempotent=True,
        audit=True,
    ),
    "peers": CommandSpec(
        command="peers",
        execution_class=ExecutionClass.READ_ONLY,
        description="List peer brains.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "peers.introduce": CommandSpec(
        command="peers.introduce",
        execution_class=ExecutionClass.READ_ONLY,
        description="Introduce to a peer brain.",
        allowed_fields={"endpoint"},
        required_fields={"endpoint"},
        idempotent=False,
        audit=True,
    ),
    "peers.ping": CommandSpec(
        command="peers.ping",
        execution_class=ExecutionClass.READ_ONLY,
        description="Ping a peer brain.",
        allowed_fields={"endpoint", "id"},
        required_fields=set(),
    ),
    "peers.remove": CommandSpec(
        command="peers.remove",
        execution_class=ExecutionClass.READ_ONLY,
        description="Remove a peer.",
        allowed_fields={"id"},
        required_fields={"id"},
        idempotent=True,
        audit=True,
    ),
    "introduce": CommandSpec(
        command="introduce",
        execution_class=ExecutionClass.READ_ONLY,
        description="Return federation manifest.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "model": CommandSpec(
        command="model",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show current model.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "model.list": CommandSpec(
        command="model.list",
        execution_class=ExecutionClass.READ_ONLY,
        description="List available models.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "model.use": CommandSpec(
        command="model.use",
        execution_class=ExecutionClass.READ_ONLY,
        description="Switch active model.",
        allowed_fields={"model"},
        required_fields={"model"},
        idempotent=True,
        audit=True,
    ),
    "audit": CommandSpec(
        command="audit",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show audit log.",
        allowed_fields={"limit"},
        required_fields=set(),
    ),
    "audit.clear": CommandSpec(
        command="audit.clear",
        execution_class=ExecutionClass.READ_ONLY,
        description="Clear audit log.",
        allowed_fields=set(),
        required_fields=set(),
        idempotent=True,
        audit=True,
    ),
    "policy": CommandSpec(
        command="policy",
        execution_class=ExecutionClass.READ_ONLY,
        description="Show governance policy.",
        allowed_fields=set(),
        required_fields=set(),
    ),
    "ingest": CommandSpec(
        command="ingest",
        execution_class=ExecutionClass.READ_ONLY,
        description="Queue documents for RAG.",
        allowed_fields={"path"},
        required_fields=set(),
    ),
    "think": CommandSpec(
        command="think",
        execution_class=ExecutionClass.READ_ONLY,
        description="Natural language reasoning.",
        allowed_fields={"prompt", "text"},
        required_fields=set(),
    ),
})

PAYLOAD_ALLOWED_FIELDS.update({
    "remember":        {"content", "tags", "source", "trust"},
    "recall":          {"query", "synthesize"},
    "forget":          {"id"},
    "memories":        {"limit", "tag"},
    "context.show":    set(),
    "context.set":     {"key", "value"},
    "context.clear":   {"key"},
    "peers":           set(),
    "peers.introduce": {"endpoint"},
    "peers.ping":      {"endpoint", "id"},
    "peers.remove":    {"id"},
    "introduce":       set(),
    "model":           set(),
    "model.list":      set(),
    "model.use":       {"model"},
    "audit":           {"limit"},
    "audit.clear":     set(),
    "policy":          set(),
    "ingest":          {"path"},
    "think":           {"prompt", "text"},
})

PAYLOAD_REQUIRED_FIELDS.update({
    "remember":        {"content"},
    "recall":          {"query"},
    "forget":          {"id"},
    "peers.introduce": {"endpoint"},
    "model.use":       {"model"},
})

# ── patch parse_normalized_command to handle dotted + hbar single commands ───
_original_parse = parse_normalized_command

def parse_normalized_command(normalized_command: str):
    if not normalized_command:
        return None, {}
    parts = normalized_command.strip().split()
    if not parts:
        return None, {}
    # dotted commands e.g. context.show, peers.introduce, model.use
    if "." in parts[0]:
        return parts[0], {}
    # hbar single-word commands
    hbar_single = {
        "remember", "recall", "forget", "memories",
        "peers", "introduce", "model", "audit", "policy", "ingest", "think",
    }
    if parts[0] in hbar_single:
        return parts[0], {}
    # fall through to original
    return _original_parse(normalized_command)
