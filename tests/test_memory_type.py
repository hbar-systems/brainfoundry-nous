"""
Tests for the memory-type taxonomy + provenance helper (api/memory_type.py).

Pure-logic, no DB/network: covers type classification from injection-scan band,
the provenance block shape, the trust-prior weights, and the retrieval rerank
(ephemeral dropped, untrusted demoted, all-semantic order preserved).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import memory_type as mt  # noqa: E402


def _doc(mem_type, sim, name="d"):
    md = {} if mem_type is None else {"mem_type": mem_type}
    return {"document_name": name, "content": "c", "metadata": md, "similarity_score": sim}


# ── trust_prior ───────────────────────────────────────────────────────────

def test_trust_prior_ordering():
    assert mt.trust_prior(mt.SEMANTIC) == 1.0
    assert mt.trust_prior(mt.SEMANTIC) > mt.trust_prior(mt.REFLECTIVE) > mt.trust_prior(mt.UNTRUSTED)
    assert mt.trust_prior(mt.EPHEMERAL) == 0.0


def test_trust_prior_unknown_treated_as_semantic():
    # Legacy/untagged chunks must not be punished — backfill makes them semantic.
    assert mt.trust_prior(None) == 1.0
    assert mt.trust_prior("nonsense") == 1.0


# ── classify_upload ───────────────────────────────────────────────────────

def test_classify_upload_clean_is_semantic():
    assert mt.classify_upload(None) == mt.SEMANTIC
    assert mt.classify_upload("none") == mt.SEMANTIC
    assert mt.classify_upload("low") == mt.SEMANTIC


def test_classify_upload_flagged_is_untrusted():
    assert mt.classify_upload("medium") == mt.UNTRUSTED
    assert mt.classify_upload("high") == mt.UNTRUSTED
    assert mt.classify_upload("HIGH") == mt.UNTRUSTED  # case-insensitive


# ── classify_write (the write-lane gate) ──────────────────────────────────

def test_classify_write_operator_authored_always_semantic():
    # Operator-direct content is never demoted or quarantined, whatever the scan.
    for risk in (None, "none", "low", "medium", "high"):
        assert mt.classify_write(risk, operator_authored=True) == (mt.SEMANTIC, False)


def test_classify_write_automated_clean_is_untrusted_not_quarantined():
    # Nothing unvetted enters the corpus fully trusted — clean automated ingest
    # still lands untrusted (demoted), but is retrievable (not quarantined).
    for risk in (None, "none", "low", "medium"):
        assert mt.classify_write(risk, operator_authored=False) == (mt.UNTRUSTED, False)


def test_classify_write_automated_high_is_quarantined():
    assert mt.classify_write("high", operator_authored=False) == (mt.UNTRUSTED, True)
    assert mt.classify_write("HIGH", operator_authored=False) == (mt.UNTRUSTED, True)  # case-insensitive


# ── provenance ────────────────────────────────────────────────────────────

def test_provenance_block_shape():
    p = mt.provenance(
        mem_type=mt.SEMANTIC, source="upload", derivation=mt.OBSERVED,
        content_hash="sha256:abc", ingested_at="2026-05-31T00:00:00",
    )
    assert p["mem_type"] == mt.SEMANTIC
    assert p["source"] == "upload"
    assert p["derivation"] == mt.OBSERVED
    assert p["ingested_by"] == "operator"
    assert p["source_trust"] == 1.0
    assert p["content_hash"] == "sha256:abc"
    assert p["ingested_at"] == "2026-05-31T00:00:00"


def test_provenance_omits_empty_optionals():
    p = mt.provenance(mem_type=mt.UNTRUSTED, source="upload", derivation=mt.OBSERVED)
    assert "content_hash" not in p
    assert "ingested_at" not in p
    assert "injection_risk" not in p
    assert "quarantined" not in p
    assert p["source_trust"] == mt.trust_prior(mt.UNTRUSTED)


def test_provenance_records_scan_band_and_quarantine():
    p = mt.provenance(
        mem_type=mt.UNTRUSTED, source="memory/append", derivation=mt.OBSERVED,
        ingested_by="automated", injection_risk="high", quarantined=True,
    )
    assert p["injection_risk"] == "high"
    assert p["quarantined"] is True
    assert p["ingested_by"] == "automated"


def test_provenance_records_band_even_when_not_demoted():
    # An operator-authored note that scanned high stays semantic but keeps the band.
    p = mt.provenance(
        mem_type=mt.SEMANTIC, source="chat-store-button", derivation=mt.OBSERVED,
        injection_risk="high",
    )
    assert p["mem_type"] == mt.SEMANTIC
    assert p["source_trust"] == 1.0
    assert p["injection_risk"] == "high"
    assert "quarantined" not in p  # quarantined=False omitted


# ── effective_score / rerank ──────────────────────────────────────────────

def test_effective_score_applies_prior():
    assert mt.effective_score(0.8, mt.SEMANTIC) == 0.8
    assert mt.effective_score(0.8, mt.UNTRUSTED) == 0.8 * 0.4


def test_rerank_drops_ephemeral():
    out = mt.rerank([_doc(mt.EPHEMERAL, 0.99), _doc(mt.SEMANTIC, 0.5)], limit=5)
    assert [d["metadata"].get("mem_type") for d in out] == [mt.SEMANTIC]


def test_rerank_drops_quarantined():
    # A quarantined chunk is excluded entirely, even at very high similarity.
    quarantined = {"document_name": "q", "content": "c", "similarity_score": 0.99,
                   "metadata": {"mem_type": mt.UNTRUSTED, "quarantined": True}}
    semantic = _doc(mt.SEMANTIC, 0.30, name="s")
    out = mt.rerank([quarantined, semantic], limit=5)
    assert [d["document_name"] for d in out] == ["s"]


def test_rerank_demotes_untrusted_below_semantic():
    # Untrusted has higher raw similarity but loses after the trust multiplier.
    untrusted = _doc(mt.UNTRUSTED, 0.90, name="u")   # 0.90 * 0.4 = 0.36
    semantic = _doc(mt.SEMANTIC, 0.50, name="s")     # 0.50 * 1.0 = 0.50
    out = mt.rerank([untrusted, semantic], limit=2)
    assert [d["document_name"] for d in out] == ["s", "u"]


def test_rerank_preserves_all_semantic_order():
    docs = [_doc(mt.SEMANTIC, 0.9, "a"), _doc(mt.SEMANTIC, 0.7, "b"), _doc(mt.SEMANTIC, 0.5, "c")]
    out = mt.rerank(docs, limit=3)
    assert [d["document_name"] for d in out] == ["a", "b", "c"]


def test_rerank_truncates_to_limit():
    docs = [_doc(mt.SEMANTIC, s) for s in (0.9, 0.8, 0.7, 0.6)]
    assert len(mt.rerank(docs, limit=2)) == 2


def test_rerank_untagged_treated_as_semantic():
    untagged = _doc(None, 0.6, "legacy")
    untrusted = _doc(mt.UNTRUSTED, 0.9, "u")  # 0.9*0.4=0.36 < 0.6
    out = mt.rerank([untrusted, untagged], limit=2)
    assert out[0]["document_name"] == "legacy"


# ── label ─────────────────────────────────────────────────────────────────

def test_label():
    assert mt.label({"mem_type": "semantic", "derivation": "observed"}) == "semantic, observed"
    assert mt.label({"mem_type": "untrusted"}) == "untrusted"
    assert mt.label({}) == ""
    assert mt.label(None) == ""
