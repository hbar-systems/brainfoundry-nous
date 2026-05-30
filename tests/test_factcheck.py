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
