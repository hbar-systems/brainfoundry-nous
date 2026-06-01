"""
api/tools — the brain's external-capability layer (the "hands and eyes").

This is the registry + dispatcher every tool slots into. It exists *before*
any specific tool so that web search, fetch, calendar, mail, and the future
`brain_call` federation tool do not each reinvent permitting, provenance, and
audit. One registry shape; one dispatch path; one place the governance gate
lives.

Design (ROADMAP §v1.1+ "tool registry", cognitive-OS roadmap 2026-05-27):

  - **Permission tiers** on every tool:
      GREEN  — read/summarize over the brain's own memory. Always allowed.
      YELLOW — external API read (web search, calendar read, fetch). Allowed
               only with the operator's STANDING authorization (a settings
               toggle). Audited + budget-capped.
      RED    — shell, file write, credential use, send-message, federation
               write. Requires per-call operator approval. NOT yet wired —
               dispatch refuses RED tools until the approval flow exists, by
               design (read-only first, write second, autonomous third).

  - **Untrusted by default.** A tool result is external data, never a trusted
    memory and never a command. `safety.wrap_untrusted` delimits it and tells
    the model so. Provenance (source + URL + retrieval time) rides with it.

  - **Audited + budget-capped.** Every dispatch is logged (`audit`) and counted
    against a monthly cap (`budget`) so a runaway loop can't drain an API quota.

v0 wiring is deterministic: the chat client asks for a tool explicitly
(operator-driven). Native model-driven tool-calling lands later, alongside the
permission-tier *enforcement* it depends on — same registry, no rework.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

# ── Permission tiers ────────────────────────────────────────────────────────
GREEN = "green"    # read/summarize over own memory — always allowed
YELLOW = "yellow"  # external API read — standing operator authorization
RED = "red"        # write / exec / send — per-call approval (not yet wired)

_TIER_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}


@dataclass
class ToolResult:
    """The uniform return shape for every tool.

    `content` is human/model-readable text already SAFETY-WRAPPED when it
    carries external/untrusted data — the dispatcher does not re-wrap. The
    caller injects `content` into the prompt verbatim. `provenance` is the
    machine-readable source list surfaced to the operator (UI "where did this
    come from"). `ok=False` + `error` means the tool did not produce usable
    output (tier refusal, budget exhaustion, API failure)."""
    ok: bool
    content: str = ""
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    tier: str
    # input_schema is a JSON-schema-ish dict; used today for documentation /
    # the /tools listing, and reused verbatim as the function schema when
    # native model-driven tool-calling is wired.
    input_schema: Dict[str, Any]
    run: Callable[..., Awaitable[ToolResult]]


REGISTRY: Dict[str, Tool] = {}


def register(tool: Tool) -> None:
    if tool.tier not in _TIER_ORDER:
        raise ValueError(f"tool {tool.name!r}: unknown tier {tool.tier!r}")
    REGISTRY[tool.name] = tool


def get(name: str) -> Optional[Tool]:
    return REGISTRY.get(name)


def list_tools() -> List[Dict[str, Any]]:
    """Public inventory for the /tools surface — no callables, no secrets."""
    return [
        {"name": t.name, "description": t.description, "tier": t.tier,
         "input_schema": t.input_schema}
        for t in sorted(REGISTRY.values(), key=lambda t: t.name)
    ]


async def dispatch(
    name: str,
    args: Dict[str, Any],
    *,
    operator_authorized: bool = False,
    approval_token: Optional[str] = None,
) -> ToolResult:
    """Run a registered tool through the governance gate.

    `operator_authorized` is the caller's assertion that the operator has
    granted standing authorization for YELLOW-tier execution (in practice: the
    relevant settings toggle is on). RED tools additionally require a valid
    per-call `approval_token`, which is not yet issued anywhere — so RED is
    refused until that flow exists. Failures are returned as `ok=False`
    ToolResults, never raised, so a tool call can never crash the chat turn.
    """
    from api.tools import audit, budget

    tool = REGISTRY.get(name)
    if tool is None:
        return ToolResult(ok=False, error=f"unknown tool: {name}")

    # ── Tier gate ────────────────────────────────────────────────────────
    if tool.tier == YELLOW and not operator_authorized:
        audit.log({"tool": name, "tier": tool.tier, "ok": False,
                   "reason": "not_authorized"})
        return ToolResult(ok=False, error=f"{name} is a yellow-tier tool and "
                          "requires the operator to enable it first.")
    if tool.tier == RED:
        # Per-call approval is intentionally not yet implemented. Fail closed.
        audit.log({"tool": name, "tier": tool.tier, "ok": False,
                   "reason": "red_tier_blocked"})
        return ToolResult(ok=False, error=f"{name} is a red-tier tool "
                          "(write/exec/send) — per-call approval is not yet "
                          "available, so it is blocked.")

    # ── Budget gate ──────────────────────────────────────────────────────
    if not budget.under_cap(name):
        audit.log({"tool": name, "tier": tool.tier, "ok": False,
                   "reason": "budget_exceeded",
                   "usage": budget.usage(name), "cap": budget.cap(name)})
        return ToolResult(ok=False, error=f"{name} has hit its monthly budget "
                          f"cap ({budget.cap(name)} calls). Raise it in "
                          "Settings or wait for the month to roll over.")

    # ── Run ──────────────────────────────────────────────────────────────
    try:
        result = tool.run(**args)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ToolResult):
            result = ToolResult(ok=True, content=str(result))
    except Exception as e:  # a tool must never crash the chat turn
        audit.log({"tool": name, "tier": tool.tier, "ok": False,
                   "reason": "exception", "error": str(e)})
        return ToolResult(ok=False, error=f"{name} failed: {e}")

    # A call that reached the provider counts against budget even if it
    # returned zero results — the quota was spent.
    budget.record(name)
    entry = {
        "tool": name, "tier": tool.tier, "ok": result.ok,
        "args": _summarize(args),
        "result": (result.error if not result.ok
                   else f"{len(result.provenance)} source(s)"),
    }
    # Keep the actual sources (title + url) on the record so the audit surface
    # can let the operator click through to what the brain actually read — not
    # just a count. Capped so the log line stays small.
    if result.ok and result.provenance:
        entry["sources"] = [
            {"title": p.get("title"), "url": p.get("url")}
            for p in result.provenance if p.get("url")
        ][:10]
    audit.log(entry)
    return result


def _summarize(args: Dict[str, Any]) -> Dict[str, Any]:
    """Trim arg values for the audit log so we don't store huge payloads."""
    out: Dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    return out


# Registering a tool is a side effect of importing its module. Keep this at the
# bottom so the names above (Tool, register, tiers) already exist.
from api.tools import web_search      # noqa: E402,F401  (yellow)
from api.tools import memory_search   # noqa: E402,F401  (green)
