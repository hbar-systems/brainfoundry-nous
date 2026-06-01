"""
api/factcheck.py — a mathematical corroboration score for a set of sources.

The honest primitive behind the "FactChecker" idea: people struggle to gauge
whether something is true, so give them a *measured* signal instead of a vibe.
This does NOT claim to decide truth. It measures **corroboration** — how much
independent, mutually-agreeing, trustworthy sourcing backs a claim — and shows
its inputs so the number is auditable. ("A symbol attached to a calculated
equation attached to a measurement.")

v0 scores the result set of a web search (each result already carries its
source URL + snippet — provenance we have today). The same function will later
score RAG-document and cross-brain-federation claims once those carry per-chunk
provenance.

The score combines three measurable factors:

  independence  — count of DISTINCT registrable domains. Five copies of one
                  wire story is not corroboration; five domains is. Echo
                  chambers score low because distinct-domain count stays low.
  agreement     — mean pairwise cosine similarity of the source snippets
                  (brain's bge-large embeddings). Do the sources actually say
                  the same thing, or just share a topic? Outliers are surfaced
                  as dissenters rather than averaged away.
  trust         — mean per-domain trust prior from a small, operator-extensible
                  seed list (institutional/primary sources weigh more).

  score = 100 · (wᵢ·independence + wₐ·agreement + wₜ·trust)

Embeddings are injected (embed_fn) so this is fully testable and degrades
gracefully: with no embedder, agreement drops out and the weight redistributes.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse

# Weights for the three factors when all are present. Tunable; sum to 1.0.
_W_INDEPENDENCE = 0.35
_W_AGREEMENT = 0.35
_W_TRUST = 0.30

# Distinct-domain count at which independence is considered "full".
_INDEPENDENCE_TARGET = 3
# A source whose mean cosine to the others falls below this is a dissenter.
_DISSENT_THRESHOLD = 0.35
_DEFAULT_TRUST = 0.5

# Seed trust priors. v0, deliberately small and conservative; operator-
# extensible later. TLD-class rules (gov/edu) apply first, then domain lookup.
_TRUST_DOMAINS: Dict[str, float] = {
    "reuters.com": 0.92, "apnews.com": 0.92, "nature.com": 0.92,
    "science.org": 0.92, "arxiv.org": 0.85, "who.int": 0.9,
    "bbc.com": 0.85, "bbc.co.uk": 0.85, "nytimes.com": 0.82,
    "theguardian.com": 0.8, "ft.com": 0.82, "economist.com": 0.82,
    "wikipedia.org": 0.78, "github.com": 0.75,
}
# Multi-label public suffixes we must keep intact when finding the
# registrable domain (so bbc.co.uk -> bbc.co.uk, not co.uk).
_TWO_LEVEL_SUFFIXES = {
    "co.uk", "gov.uk", "ac.uk", "org.uk", "co.jp", "com.au", "co.nz",
    "co.in", "com.br", "gov.au", "edu.au",
}


def _registrable_domain(url: str) -> str:
    """Best-effort eTLD+1 without a public-suffix dependency."""
    try:
        host = (urlparse(url).hostname or "").lower().strip(".")
    except Exception:
        host = ""
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return last_two


def _trust_for(domain: str) -> float:
    if not domain:
        return _DEFAULT_TRUST
    # TLD-class rules first (covers .gov, .edu and their multi-label forms).
    for marker in (".gov", ".edu", ".int", ".mil"):
        if domain.endswith(marker) or f"{marker}." in f".{domain}":
            return 0.93
    return _TRUST_DOMAINS.get(domain, _DEFAULT_TRUST)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mean_pairwise_and_dissenters(vectors: List[Sequence[float]]):
    """Return (mean_pairwise_cosine, per_source_mean_cosine list)."""
    n = len(vectors)
    if n < 2:
        return None, [1.0] * n
    per_source = [0.0] * n
    total = 0.0
    pairs = 0
    for i in range(n):
        acc = 0.0
        for j in range(n):
            if i == j:
                continue
            c = _cosine(vectors[i], vectors[j])
            acc += c
            if j > i:
                total += c
                pairs += 1
        per_source[i] = acc / (n - 1)
    mean_pairwise = (total / pairs) if pairs else None
    return mean_pairwise, per_source


def _corroboration_core(
    *,
    identities: List[str],
    trusts: List[float],
    texts: List[str],
    labels: List[str],
    method: str,
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]] = None,
) -> Optional[Dict]:
    """The shared three-factor corroboration math, source-agnostic.

    - independence — distinct count of `identities` (registrable domains for web,
      document content_hash/name for RAG) over the target.
    - agreement    — mean pairwise cosine of the embedded `texts`.
    - trust        — mean of `trusts` (domain prior for web, per-chunk
      `source_trust` for RAG).
    `labels` are what gets reported in `dissenters`. Returns None when there are
    fewer than 2 items to compare. Returns a `n_distinct`; callers alias it to
    their domain-specific name (`n_domains` / `n_documents`) for back-compat.
    """
    n = len(identities)
    if n < 2:
        return None

    distinct = sorted({d for d in identities if d})
    n_distinct = len(distinct)
    independence = min(n_distinct / _INDEPENDENCE_TARGET, 1.0)

    mean_trust = (sum(trusts) / len(trusts)) if trusts else _DEFAULT_TRUST

    # ── Semantic agreement (optional) ────────────────────────────────────
    agreement: Optional[float] = None
    dissenters: List[str] = []
    if embed_fn is None:
        embed_fn = _default_embed
    try:
        vectors = embed_fn(texts)
        if vectors is not None and len(vectors) == n:
            mean_pairwise, per_source = _mean_pairwise_and_dissenters(list(vectors))
            if mean_pairwise is not None:
                # cosine is in [-1,1]; clamp to [0,1] for a score factor.
                agreement = max(0.0, min(1.0, mean_pairwise))
                for lbl, m in zip(labels, per_source):
                    if m < _DISSENT_THRESHOLD:
                        dissenters.append(lbl)
    except Exception:
        agreement = None  # degrade gracefully — never break the answer

    # ── Combine ──────────────────────────────────────────────────────────
    if agreement is not None:
        raw = (_W_INDEPENDENCE * independence
               + _W_AGREEMENT * agreement
               + _W_TRUST * mean_trust)
    else:
        # Redistribute the agreement weight across the two remaining factors.
        wi = _W_INDEPENDENCE / (_W_INDEPENDENCE + _W_TRUST)
        wt = _W_TRUST / (_W_INDEPENDENCE + _W_TRUST)
        raw = wi * independence + wt * mean_trust

    score = int(round(100 * max(0.0, min(1.0, raw))))
    return {
        "score": score,
        "n_sources": n,
        "n_distinct": n_distinct,
        "independence": round(independence, 3),
        "agreement": round(agreement, 3) if agreement is not None else None,
        "trust": round(mean_trust, 3),
        "dissenters": dissenters,
        "method": method,
    }


def score_corroboration(
    sources: List[Dict],
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]] = None,
) -> Optional[Dict]:
    """Score how well a set of WEB sources corroborate each other.

    sources: [{title, url, snippet}]. embed_fn(texts)->vectors; when None, the
    brain's bge-large model is used, and if that is unavailable the agreement
    term is dropped (weight redistributed). Returns None when there is nothing
    meaningful to score (fewer than 2 sourced results), so callers can treat
    "no score" as "not enough to corroborate".
    """
    items = [s for s in (sources or []) if s.get("url")]
    if len(items) < 2:
        return None

    domains = [_registrable_domain(s["url"]) for s in items]
    result = _corroboration_core(
        identities=domains,
        trusts=[_trust_for(d) for d in domains],
        texts=[f"{s.get('title', '')}. {s.get('snippet', '')}".strip() for s in items],
        labels=[s["url"] for s in items],
        method="corroboration v0 (independence·agreement·trust)",
        embed_fn=embed_fn,
    )
    if result is not None:
        result["n_domains"] = result["n_distinct"]  # back-compat: web UI reads this
    return result


def score_rag_corroboration(
    docs: List[Dict],
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]] = None,
) -> Optional[Dict]:
    """Score how well a set of RAG chunks corroborate the answer they grounded.

    The generalization the memory-type/provenance work unblocked: the same
    corroboration measurement, now over the brain's OWN documents instead of web
    results. Maps RAG provenance onto the three factors:

    - independence — distinct source DOCUMENTS (by `content_hash`, else
      `document_name`). Five chunks of one document are NOT five corroborating
      sources; five documents are.
    - trust        — per-chunk `source_trust` from provenance (semantic 1.0,
      reflective 0.9, untrusted 0.4). An answer grounded only in `untrusted`
      chunks scores low even if the chunks agree — the gap-#5 poisoning signal.
    - agreement    — mean pairwise cosine of the chunk contents.

    docs: the retrieval results [{document_name, content, metadata{...}}]. Returns
    None for fewer than 2 chunks. Presented, like the web score, as a MEASUREMENT
    of support — not a verdict on truth.
    """
    items = [d for d in (docs or []) if (d.get("content") or "").strip()]
    if len(items) < 2:
        return None

    def _identity(d: Dict) -> str:
        md = d.get("metadata") or {}
        return md.get("content_hash") or d.get("document_name") or ""

    def _trust(d: Dict) -> float:
        md = d.get("metadata") or {}
        t = md.get("source_trust")
        if isinstance(t, (int, float)):
            return float(t)
        # No explicit prior (legacy/untagged chunk) — fall back to the type prior.
        from api import memory_type
        return memory_type.trust_prior(md.get("mem_type"))

    result = _corroboration_core(
        identities=[_identity(d) for d in items],
        trusts=[_trust(d) for d in items],
        texts=[(d.get("content") or "")[:600] for d in items],
        labels=[d.get("document_name") or "" for d in items],
        method="corroboration v0 (rag: independence·agreement·trust)",
        embed_fn=embed_fn,
    )
    if result is not None:
        result["n_documents"] = result["n_distinct"]
    return result


def _default_embed(texts: List[str]) -> Optional[List[Sequence[float]]]:
    """Embed via the brain's loaded model. Returns None on any failure so the
    score still computes from independence + trust alone."""
    try:
        from api.embeddings.model import get_model
        vecs = get_model().encode(texts, normalize_embeddings=False)
        return [list(map(float, v)) for v in vecs]
    except Exception:
        return None
