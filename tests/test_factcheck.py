"""
Tests for the corroboration scorer (api/factcheck.py).

Pure-logic: the embedder is injected, so no model/network is touched. Covers
domain extraction, the three factors (independence / agreement / trust),
dissenter detection, graceful degradation with no embeddings, and the
not-enough-to-score case.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import factcheck  # noqa: E402


def _src(url, title="t", snippet="s"):
    return {"title": title, "url": url, "snippet": snippet}


# Deterministic fake embedders ------------------------------------------------

def _identical(texts):
    return [[1.0, 0.0, 0.0] for _ in texts]


def _orthogonal(texts):
    # Each source points a different axis → ~0 pairwise cosine.
    basis = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    return [basis[i % 3] for i in range(len(texts))]


def _no_embed(texts):
    return None


# ── not enough to score ──────────────────────────────────────────────────────

def test_single_source_returns_none():
    assert factcheck.score_corroboration([_src("https://a.com/x")]) is None


def test_empty_returns_none():
    assert factcheck.score_corroboration([]) is None


# ── domain extraction ────────────────────────────────────────────────────────

def test_registrable_domain_simple():
    assert factcheck._registrable_domain("https://www.example.com/a/b") == "example.com"


def test_registrable_domain_two_level_suffix():
    assert factcheck._registrable_domain("https://news.bbc.co.uk/x") == "bbc.co.uk"


def test_registrable_domain_bare_host():
    assert factcheck._registrable_domain("https://example.com") == "example.com"


# ── independence ─────────────────────────────────────────────────────────────

def test_independence_low_when_one_domain():
    # 5 results, all same domain → echo chamber → independence is low.
    srcs = [_src(f"https://x.com/{i}") for i in range(5)]
    r = factcheck.score_corroboration(srcs, embed_fn=_identical)
    assert r["n_domains"] == 1
    assert r["independence"] < 0.4


def test_independence_full_at_three_domains():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    r = factcheck.score_corroboration(srcs, embed_fn=_identical)
    assert r["n_domains"] == 3
    assert r["independence"] == 1.0


# ── trust ────────────────────────────────────────────────────────────────────

def test_trust_gov_edu_high():
    assert factcheck._trust_for("nasa.gov") >= 0.9
    assert factcheck._trust_for("mit.edu") >= 0.9
    assert factcheck._trust_for("gov.uk") >= 0.9


def test_trust_unknown_is_default():
    assert factcheck._trust_for("randomblog.xyz") == factcheck._DEFAULT_TRUST


def test_trust_seed_domain():
    assert factcheck._trust_for("reuters.com") > factcheck._DEFAULT_TRUST


# ── agreement + dissenters ───────────────────────────────────────────────────

def test_identical_sources_high_agreement():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    r = factcheck.score_corroboration(srcs, embed_fn=_identical)
    assert r["agreement"] == 1.0
    assert r["dissenters"] == []


def test_orthogonal_sources_low_agreement_and_dissenters():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    r = factcheck.score_corroboration(srcs, embed_fn=_orthogonal)
    assert r["agreement"] < 0.2
    # All disagree with each other → all flagged as dissenters.
    assert len(r["dissenters"]) == 3


# ── graceful degradation ─────────────────────────────────────────────────────

def test_no_embeddings_still_scores():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2")]
    r = factcheck.score_corroboration(srcs, embed_fn=_no_embed)
    assert r["agreement"] is None
    assert isinstance(r["score"], int)
    assert 0 <= r["score"] <= 100


# ── score bounds + monotonicity sanity ───────────────────────────────────────

def test_score_in_range():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    r = factcheck.score_corroboration(srcs, embed_fn=_identical)
    assert 0 <= r["score"] <= 100


def test_trusted_diverse_agreeing_beats_echo_chamber():
    # Three independent, agreeing, default-trust sources …
    good = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    # … vs five copies from one domain that also "agree" (same embeddings).
    echo = [_src(f"https://x.com/{i}") for i in range(5)]
    rg = factcheck.score_corroboration(good, embed_fn=_identical)
    re = factcheck.score_corroboration(echo, embed_fn=_identical)
    assert rg["score"] > re["score"]


# ── RAG corroboration (cognitive-OS gap #2/#4/#5 payoff) ──────────────────────

def _doc(name, content="text", trust=None, chash=None, mem_type=None):
    md = {}
    if trust is not None:
        md["source_trust"] = trust
    if chash is not None:
        md["content_hash"] = chash
    if mem_type is not None:
        md["mem_type"] = mem_type
    return {"document_name": name, "content": content, "metadata": md}


def test_rag_single_doc_returns_none():
    assert factcheck.score_rag_corroboration([_doc("a.md", trust=1.0)]) is None


def test_rag_empty_returns_none():
    assert factcheck.score_rag_corroboration([]) is None


def test_rag_blank_content_filtered_out():
    # Only one doc has real content -> nothing to corroborate.
    docs = [_doc("a.md", content="real", trust=1.0), _doc("b.md", content="   ", trust=1.0)]
    assert factcheck.score_rag_corroboration(docs) is None


def test_rag_distinct_documents_corroborate():
    docs = [_doc("a.md", trust=1.0, chash="sha256:a"),
            _doc("b.md", trust=1.0, chash="sha256:b"),
            _doc("c.md", trust=1.0, chash="sha256:c")]
    r = factcheck.score_rag_corroboration(docs, embed_fn=_identical)
    assert r["n_documents"] == 3
    assert r["n_sources"] == 3
    assert r["independence"] == 1.0          # 3 distinct docs hits the target
    assert r["trust"] == 1.0
    assert r["score"] > 90


def test_rag_same_document_chunks_are_not_independent():
    # Three chunks of ONE document (shared content_hash) -> independence is low.
    docs = [_doc("a.md", content=f"chunk{i}", trust=1.0, chash="sha256:same") for i in range(3)]
    r = factcheck.score_rag_corroboration(docs, embed_fn=_identical)
    assert r["n_documents"] == 1
    assert r["independence"] < 0.5


def test_rag_untrusted_scores_below_semantic():
    semantic = [_doc("a.md", trust=1.0, chash="sha256:a"), _doc("b.md", trust=1.0, chash="sha256:b")]
    untrusted = [_doc("c.md", trust=0.4, chash="sha256:c"), _doc("d.md", trust=0.4, chash="sha256:d")]
    rs = factcheck.score_rag_corroboration(semantic, embed_fn=_identical)
    ru = factcheck.score_rag_corroboration(untrusted, embed_fn=_identical)
    assert ru["trust"] < rs["trust"]
    assert ru["score"] < rs["score"]


def test_rag_trust_falls_back_to_mem_type_prior():
    # No explicit source_trust -> uses memory_type.trust_prior(mem_type).
    docs = [_doc("a.md", chash="sha256:a", mem_type="untrusted"),
            _doc("b.md", chash="sha256:b", mem_type="untrusted")]
    r = factcheck.score_rag_corroboration(docs, embed_fn=_identical)
    assert abs(r["trust"] - 0.4) < 1e-9


def test_rag_dissenter_uses_document_name():
    # Two agree, one points elsewhere -> the outlier is named by document_name.
    docs = [_doc("a.md", trust=1.0, chash="sha256:a"),
            _doc("b.md", trust=1.0, chash="sha256:b"),
            _doc("outlier.md", trust=1.0, chash="sha256:c")]
    def embed(texts):
        # a,b identical; outlier orthogonal
        return [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    r = factcheck.score_rag_corroboration(docs, embed_fn=embed)
    assert "outlier.md" in r["dissenters"]


def test_rag_degrades_without_embeddings():
    docs = [_doc("a.md", trust=1.0, chash="sha256:a"), _doc("b.md", trust=1.0, chash="sha256:b")]
    r = factcheck.score_rag_corroboration(docs, embed_fn=_no_embed)
    assert r["agreement"] is None
    assert r["score"] > 0                    # independence + trust still compute


# ── web shape regression (must stay byte-compatible for the existing UI) ──────

def test_web_shape_unchanged_after_refactor():
    good = [_src("https://reuters.com/a"), _src("https://apnews.com/b")]
    r = factcheck.score_corroboration(good, embed_fn=_identical)
    assert "n_domains" in r                   # UI reads corro.n_domains
    assert r["n_domains"] == 2
    assert set(["score", "dissenters", "n_sources", "independence", "agreement", "trust", "method"]).issubset(r)


# ── stance-aware corroboration (A+B) ──────────────────────────────────────────

import asyncio  # noqa: E402


def _stances(*labels):
    return [{"stance": s, "reason": ""} for s in labels]


def test_stance_contradict_lowers_score():
    # The core defect fix: a contradicting source must pull the signal DOWN,
    # where the legacy topical path raised it (on-topic == on-topic).
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    claim = "The treaty was signed in 1990."
    all_support = factcheck.score_corroboration(
        srcs, embed_fn=_identical, claim=claim, stances=_stances("support", "support", "support"))
    one_contra = factcheck.score_corroboration(
        srcs, embed_fn=_identical, claim=claim, stances=_stances("support", "support", "contradict"))
    assert one_contra["score"] < all_support["score"]
    assert one_contra["counts"]["contradict"] == 1
    assert "https://c.com/3" in one_contra["dissenters"]


def test_stance_components_returned_and_not_probability():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2")]
    r = factcheck.score_corroboration(
        srcs, embed_fn=_identical, claim="X is true", stances=_stances("support", "contradict"))
    assert r["is_probability"] is False
    assert "not a probability" in r["label"].lower()
    assert set(["counts", "weights", "per_source", "stance_score", "signal"]).issubset(r)
    assert len(r["per_source"]) == 2
    assert r["per_source"][0]["stance"] == "support"
    assert r["per_source"][1]["stance"] == "contradict"


def test_stance_neutral_does_not_inflate():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2"), _src("https://c.com/3")]
    two_support = factcheck.score_corroboration(
        srcs[:2], embed_fn=_identical, claim="X", stances=_stances("support", "support"))
    plus_neutral = factcheck.score_corroboration(
        srcs, embed_fn=_identical, claim="X", stances=_stances("support", "support", "neutral"))
    # A neutral source dilutes (never raises) the stance score.
    assert plus_neutral["stance_score"] <= two_support["stance_score"]


def test_stance_irrelevant_source_excluded_by_relevance_floor():
    srcs = [_src("https://a.com/1"), _src("https://b.com/2")]
    # embed order is [claim, a, b]: a aligned with claim, b orthogonal (off-topic).
    def embed(texts):
        return [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    r = factcheck.score_corroboration(
        srcs, embed_fn=embed, claim="X", stances=_stances("support", "contradict"))
    # b "contradicts" but is not about the claim -> excluded, not counted as dissent.
    assert r["counts"]["irrelevant"] == 1
    assert r["per_source"][1]["relevance"] == 0.0
    assert "https://b.com/2" not in r["dissenters"]


def test_classify_stances_parses_injected():
    async def fake_complete(prompt):
        return '[{"stance":"SUPPORT","reason":"confirms"},{"stance":"CONTRADICT","reason":"refutes"}]'
    out = asyncio.run(factcheck.classify_stances("X", ["s1", "s2"], complete_fn=fake_complete))
    assert out == [{"stance": "support", "reason": "confirms"},
                   {"stance": "contradict", "reason": "refutes"}]


def test_classify_stances_pads_short_response():
    async def fake(prompt):
        return '[{"stance":"SUPPORT","reason":"a"}]'
    out = asyncio.run(factcheck.classify_stances("X", ["s1", "s2", "s3"], complete_fn=fake))
    assert len(out) == 3 and out[1]["stance"] == "neutral"


def test_classify_stances_bad_json_returns_none():
    async def fake(prompt):
        return "not json at all"
    assert asyncio.run(factcheck.classify_stances("X", ["s1"], complete_fn=fake)) is None
