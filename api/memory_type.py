"""api/memory_type.py — cognitive-OS memory-type taxonomy + per-chunk provenance.

Gap #2 of the cognitive-OS hardening roadmap
(ops/prompts/2026-05-27_brain-cognitive-os-federation-direction.md). Phase 1+2:
tag every retrievable chunk with a MEMORY TYPE and PROVENANCE, and let retrieval
demote untrusted material instead of letting a poisoned chunk pose as a trusted
memory.

This is a DIFFERENT axis from the user-defined "memory layers"
(settings_store.get_memory_layers / metadata.layer), which are org/topic folders
the operator names. A chunk has BOTH: a `layer` (which folder) and a `mem_type`
(how much to trust it + where it came from). They never collide because they use
distinct metadata keys — note that a *layer* can even be named "semantic"
(episodic/semantic/procedural in the consolidation path); that string is a layer
name, unrelated to the `mem_type` of the same name.

The four types:
  semantic   — operator-curated stable knowledge (an approved upload). Trusted.
  reflective — derived/inferred summaries the brain wrote (chat consolidation).
  untrusted  — ingested-but-suspect material (an upload the injection scan
               flagged; later: scraped pages, forwarded email). Retrieved but
               demoted; never silently treated as trusted truth.
  ephemeral  — current-session scratch, never persisted to the vector store.

Pure logic — no DB, no network — so it is unit-testable in isolation and safe to
call on every ingest/retrieval hop.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SEMANTIC = "semantic"
REFLECTIVE = "reflective"
UNTRUSTED = "untrusted"
EPHEMERAL = "ephemeral"
MEM_TYPES = {SEMANTIC, REFLECTIVE, UNTRUSTED, EPHEMERAL}

OBSERVED = "observed"
INFERRED = "inferred"

# Retrieval trust multiplier applied to a chunk's similarity score. `semantic`
# is the 1.0 reference; `reflective` sits a touch below (inferred, not directly
# observed); `untrusted` is heavily demoted but NOT erased — the roadmap wants
# conflicting evidence surfaced, not hidden; `ephemeral` is excluded from
# retrieval entirely (rerank() drops it before this prior is ever applied).
# An untagged/legacy chunk (None) is treated as semantic: the backfill migration
# stamps existing operator-approved chunks as semantic, so None only appears
# transiently and must not be punished.
_TRUST_PRIOR = {
    SEMANTIC: 1.0,
    REFLECTIVE: 0.9,
    UNTRUSTED: 0.4,
    EPHEMERAL: 0.0,
}
_DEFAULT_TRUST = 1.0

# Injection-scan risk bands (api/injection_scan.py) that downgrade an approved
# upload from `semantic` to `untrusted`. The operator can still approve a
# flagged doc; it just lands demoted instead of fully trusted — which makes the
# gap-#3 injection defense STRUCTURAL (it changes how the chunk is retrieved
# forever), not only a one-time UI warning at approval.
_RISKY_BANDS = {"medium", "high"}


def trust_prior(mem_type: Optional[str]) -> float:
    """Retrieval weight for a memory type. Unknown/None -> semantic (1.0)."""
    return _TRUST_PRIOR.get(mem_type, _DEFAULT_TRUST)


def classify_upload(injection_risk: Optional[str]) -> str:
    """Memory type for an operator-approved document upload.

    `semantic` by default (the operator curated it by approving); `untrusted`
    if the injection scan flagged it medium/high risk.
    """
    if injection_risk and injection_risk.lower() in _RISKY_BANDS:
        return UNTRUSTED
    return SEMANTIC


def provenance(
    *,
    mem_type: str,
    source: str,
    derivation: str,
    content_hash: Optional[str] = None,
    ingested_at: Optional[str] = None,
    ingested_by: str = "operator",
) -> Dict[str, Any]:
    """Build the flat provenance block merged into a chunk's metadata JSONB.

    Flat keys (not nested) to match the existing `layer`/`scope` style and keep
    the partial-index expressions simple. `source_trust` is stored explicitly so
    a future per-source prior can override the type default without a migration.
    `content_hash` is the join key back to the signed `artifact_attestations`
    ledger (api/substrate.py) — the link that was missing between a chunk and
    its attested provenance.
    """
    block: Dict[str, Any] = {
        "mem_type": mem_type,
        "source": source,
        "derivation": derivation,            # OBSERVED | INFERRED
        "ingested_by": ingested_by,
        "source_trust": trust_prior(mem_type),
    }
    if content_hash:
        block["content_hash"] = content_hash
    if ingested_at:
        block["ingested_at"] = ingested_at
    return block


def effective_score(similarity_score: float, mem_type: Optional[str]) -> float:
    """Similarity scaled by the type's trust prior — the retrieval ranking key."""
    return similarity_score * trust_prior(mem_type)


def rerank(results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Drop ephemeral, demote by trust prior, keep the top `limit`.

    Stable: equal effective scores keep their incoming (pure-similarity) order,
    so an all-`semantic` result set is returned unchanged. Reads `mem_type` from
    each result's `metadata`; a result with no metadata/type is treated as
    `semantic` and therefore not demoted.
    """
    kept = [
        r for r in results
        if (r.get("metadata") or {}).get("mem_type") != EPHEMERAL
    ]
    kept.sort(
        key=lambda r: effective_score(
            r.get("similarity_score", 0.0),
            (r.get("metadata") or {}).get("mem_type"),
        ),
        reverse=True,
    )
    return kept[:limit]


def label(metadata: Optional[Dict[str, Any]]) -> str:
    """Short provenance label for a retrieved chunk, e.g. 'semantic, observed'
    or 'untrusted, inferred'. Empty string if the chunk carries no type tag."""
    md = metadata or {}
    mt = md.get("mem_type")
    if not mt:
        return ""
    deriv = md.get("derivation")
    return f"{mt}, {deriv}" if deriv else str(mt)
