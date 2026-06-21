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

# ── Stance-aware corroboration (A+B) ────────────────────────────────────────
# The defect this fixes: the legacy "agreement" factor is mean pairwise cosine
# BETWEEN sources — topical similarity. A source that loudly contradicts the
# claim is just as "on topic" as one that confirms it, so it raised the score
# identically. Related is not true. When a `claim` is supplied we instead split
# TWO signals per source: topical relevance (cosine source↔claim) and stance
# (SUPPORT | CONTRADICT | NEUTRAL toward the claim), and score real agreement —
# supporting weight minus contradicting weight over RELEVANT sources only.
# Kept deliberately simple; it will be recalibrated under D (calibration gate),
# so it is NOT presented as a probability of truth yet (see `is_probability`).
_W_STANCE_INDEPENDENCE = 0.25
_W_STANCE = 0.55
_W_STANCE_TRUST = 0.20
# A source whose cosine to the claim is below this is not "about" the claim and
# does not contribute support OR contradiction.
_RELEVANCE_FLOOR = 0.20
_STANCES = ("support", "contradict", "neutral")

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


def _relevance_to_claim(
    claim: str,
    texts: List[str],
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]],
) -> Optional[List[float]]:
    """Per-source topical relevance: cosine(source, claim), clamped to [0,1].

    This is signal (1) of the A-split — "is this source about the claim at all?"
    — kept SEPARATE from stance. Returns None when no embedder is available, in
    which case the caller treats every source as relevant (relevance is unknown,
    not zero) and leans entirely on stance.
    """
    if embed_fn is None:
        embed_fn = _default_embed
    try:
        vecs = embed_fn([claim] + list(texts))
        if vecs is None or len(vecs) != len(texts) + 1:
            return None
        claim_vec = vecs[0]
        return [max(0.0, min(1.0, _cosine(claim_vec, v))) for v in vecs[1:]]
    except Exception:
        return None


def _corroboration_stance_core(
    *,
    identities: List[str],
    trusts: List[float],
    texts: List[str],
    labels: List[str],
    claim: str,
    stances: List[Dict],
    method: str,
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]] = None,
) -> Optional[Dict]:
    """Stance-aware corroboration (A+B). `stances[i]` is
    {"stance": "support|contradict|neutral", "reason": str} aligned to the
    sources. The rolled-up number is a corroboration SIGNAL, not a probability
    of truth (D not done) — `is_probability` is False and the components are
    returned prominently.
    """
    n = len(identities)
    if n < 2:
        return None

    rel = _relevance_to_claim(claim, texts, embed_fn)
    relevance = rel if rel is not None else [1.0] * n  # unknown → treat as relevant

    support_w = contradict_w = neutral_w = 0.0
    counts = {"support": 0, "contradict": 0, "neutral": 0, "irrelevant": 0}
    per_source: List[Dict] = []
    supporting_domains = set()
    relevant_domains = set()
    relevant_trusts: List[float] = []
    dissenters: List[str] = []

    for i in range(n):
        st = (stances[i].get("stance") if i < len(stances) and isinstance(stances[i], dict) else None)
        st = st.lower().strip() if isinstance(st, str) else "neutral"
        if st not in _STANCES:
            st = "neutral"
        reason = (stances[i].get("reason", "") if i < len(stances) and isinstance(stances[i], dict) else "")
        r = relevance[i]
        t = trusts[i] if i < len(trusts) else _DEFAULT_TRUST
        is_relevant = r >= _RELEVANCE_FLOOR
        weight = t * r

        per_source.append({
            "label": labels[i] if i < len(labels) else "",
            "domain": identities[i],
            "relevance": round(r, 3),
            "stance": st,
            "reason": reason[:200],
            "trust": round(t, 3),
        })

        if not is_relevant:
            counts["irrelevant"] += 1
            continue
        relevant_domains.add(identities[i])
        relevant_trusts.append(t)
        counts[st] += 1
        if st == "support":
            support_w += weight
            if identities[i]:
                supporting_domains.add(identities[i])
        elif st == "contradict":
            contradict_w += weight
            dissenters.append(labels[i] if i < len(labels) else "")
        else:
            neutral_w += weight

    denom = support_w + contradict_w + neutral_w
    # B: real agreement — supporting minus contradicting over relevant sources.
    # Contradiction pulls DOWN; neutral dilutes but never inflates.
    stance_score = max(0.0, (support_w - contradict_w) / denom) if denom > 0 else 0.0

    independence = min(len(supporting_domains) / _INDEPENDENCE_TARGET, 1.0)
    mean_trust = (sum(relevant_trusts) / len(relevant_trusts)) if relevant_trusts else _DEFAULT_TRUST

    raw = (_W_STANCE_INDEPENDENCE * independence
           + _W_STANCE * stance_score
           + _W_STANCE_TRUST * mean_trust)
    signal = int(round(100 * max(0.0, min(1.0, raw))))

    return {
        "score": signal,            # back-compat key (UI reads corro.score)
        "signal": signal,
        "is_probability": False,    # honesty guardrail: D not done
        "label": "corroboration signal — supporting vs contradicting sources, "
                 "not a probability of truth",
        "n_sources": n,
        "n_distinct": len(relevant_domains),
        "independence": round(independence, 3),
        "stance_score": round(stance_score, 3),
        "agreement": None,          # superseded by stance_score in this path
        "trust": round(mean_trust, 3),
        "counts": counts,
        "weights": {
            "support": round(support_w, 3),
            "contradict": round(contradict_w, 3),
            "neutral": round(neutral_w, 3),
        },
        "per_source": per_source,
        "dissenters": dissenters,   # now: relevant sources that CONTRADICT
        "method": method,
    }


# ── Stance classifier (LLM bridge — the default per-source stance step) ──────

_STANCE_PROMPT = (
    "You are a strict fact-checking classifier. Given a CLAIM and a numbered list "
    "of SOURCE snippets, decide each source's stance TOWARD THE CLAIM:\n"
    "  SUPPORT    — the source asserts the claim is true / confirms it\n"
    "  CONTRADICT — the source asserts the claim is false / refutes it\n"
    "  NEUTRAL    — the source is unclear, off-point, or neither confirms nor denies\n"
    "Topical overlap is NOT support. A source about the same subject that does not "
    "confirm the claim is NEUTRAL. A source that says the opposite is CONTRADICT.\n"
    "Return ONLY a JSON array, one object per source IN ORDER, like:\n"
    '[{"stance":"SUPPORT","reason":"<=12 words"}, ...]\n\n'
    "CLAIM: {claim}\n\nSOURCES:\n{sources}\n"
)


async def classify_stances(
    claim: str,
    texts: List[str],
    complete_fn=None,
    model: Optional[str] = None,
) -> Optional[List[Dict]]:
    """Classify each source's stance toward `claim` via the brain's own LLM
    bridge (api.providers.complete). Returns a list aligned to `texts` of
    {"stance", "reason"}, or None on any failure (caller then falls back to the
    legacy topical path — graceful, clearly method-labeled). `complete_fn` is
    injectable for tests so no model/network is touched."""
    import json as _json

    claim = (claim or "").strip()
    if not claim or not texts:
        return None
    numbered = "\n".join(f"[{i + 1}] {(t or '')[:500]}" for i, t in enumerate(texts))
    prompt = _STANCE_PROMPT.replace("{claim}", claim).replace("{sources}", numbered)

    try:
        if complete_fn is None:
            from api import providers as _providers
            model = model or _providers.default_model()
            raw = await _providers.complete(
                model, [{"role": "user", "content": prompt}], max_tokens=600)
        else:
            raw = await complete_fn(prompt)
    except Exception:
        return None

    try:
        s = (raw or "").strip()
        start, end = s.find("["), s.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        arr = _json.loads(s[start:end + 1])
        out: List[Dict] = []
        for item in arr:
            st = str((item or {}).get("stance", "")).lower().strip()
            if st not in _STANCES:
                st = "neutral"
            out.append({"stance": st, "reason": str((item or {}).get("reason", ""))[:200]})
        # Pad/trim to align with sources (model may drop/add entries).
        if len(out) < len(texts):
            out += [{"stance": "neutral", "reason": ""}] * (len(texts) - len(out))
        return out[:len(texts)]
    except Exception:
        return None


def score_corroboration(
    sources: List[Dict],
    embed_fn: Optional[Callable[[List[str]], List[Sequence[float]]]] = None,
    claim: Optional[str] = None,
    stances: Optional[List[Dict]] = None,
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
    texts = [f"{s.get('title', '')}. {s.get('snippet', '')}".strip() for s in items]
    if claim and stances is not None:
        # A+B: stance-aware path — relevance to claim + SUPPORT/CONTRADICT/NEUTRAL.
        result = _corroboration_stance_core(
            identities=domains,
            trusts=[_trust_for(d) for d in domains],
            texts=texts,
            labels=[s["url"] for s in items],
            claim=claim,
            stances=stances,
            method="corroboration v1 (web: relevance·stance·trust)",
            embed_fn=embed_fn,
        )
    else:
        # Legacy topical path (no claim): measures inter-source agreement only.
        result = _corroboration_core(
            identities=domains,
            trusts=[_trust_for(d) for d in domains],
            texts=texts,
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
    claim: Optional[str] = None,
    stances: Optional[List[Dict]] = None,
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

    identities = [_identity(d) for d in items]
    trusts = [_trust(d) for d in items]
    texts = [(d.get("content") or "")[:600] for d in items]
    labels = [d.get("document_name") or "" for d in items]
    if claim and stances is not None:
        result = _corroboration_stance_core(
            identities=identities, trusts=trusts, texts=texts, labels=labels,
            claim=claim, stances=stances,
            method="corroboration v1 (rag: relevance·stance·trust)",
            embed_fn=embed_fn,
        )
    else:
        result = _corroboration_core(
            identities=identities, trusts=trusts, texts=texts, labels=labels,
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
