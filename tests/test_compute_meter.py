"""Tests for the compute meter (read-only token metering, v0).

Covers cost computation from the rate table, usage extraction across the three
provider response shapes, the uncosted-model flag, and token estimation. DB-
backed paths (record_usage / usage / ledger) are not exercised here — they
mirror the harmonics ledger and need Postgres.

Created 2026-06-19.
"""
from types import SimpleNamespace

from api import compute_meter as cm


def test_cost_from_rate_table():
    # claude-opus-4-8: list $5/$25 at 0.93 -> in 4.65, out 23.25 €/Mtoken.
    cost, uncosted = cm.est_cost_eur("claude-opus-4-8", 1_000_000, 1_000_000)
    assert uncosted is False
    assert round(cost, 6) == round(4.65 + 23.25, 6)


def test_uncosted_model_flagged():
    cost, uncosted = cm.est_cost_eur("some-unknown-model-xyz", 1000, 1000)
    assert cost == 0.0
    assert uncosted is True


def test_usage_extraction_anthropic():
    raw = SimpleNamespace(usage=SimpleNamespace(input_tokens=120, output_tokens=45))
    assert cm.usage_from_response("anthropic", raw) == (120, 45)


def test_usage_extraction_openai():
    raw = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=200, completion_tokens=80))
    assert cm.usage_from_response("openai_compat", raw) == (200, 80)


def test_usage_extraction_ollama():
    raw = {"prompt_eval_count": 33, "eval_count": 17, "done": True}
    assert cm.usage_from_response("ollama", raw) == (33, 17)


def test_usage_missing_returns_none():
    assert cm.usage_from_response("anthropic", SimpleNamespace(usage=None)) is None
    assert cm.usage_from_response("ollama", {"message": {"content": "hi"}}) is None


def test_estimate_tokens():
    assert cm.estimate_tokens("") == 0
    assert cm.estimate_tokens("a" * 40) == 10


def test_rate_table_loads_from_json():
    rates = cm._load_rates()
    assert "claude-opus-4-8" in rates
    assert rates["claude-opus-4-8"]["in"] > 0


# 2026-11-10 (RATES-1): list prices USD/Mtoken from the claude-api reference, x0.93.
import pytest

_USD = {
    "claude-opus-5": (5, 25), "claude-opus-5-5": (4, 20),
    "claude-sonnet-5": (2, 10), "claude-sonnet-5-5": (2, 10),
    "claude-fable-5": (10, 50), "claude-fable-5-1": (10, 50),
    "claude-haiku-4-5": (1, 5), "claude-opus-4-8": (5, 25), "claude-opus-4-7": (5, 25),
}


@pytest.mark.parametrize("model,usd", sorted(_USD.items()))
def test_claude_rows_match_reference(model, usd):
    r, status = cm.rate_lookup(model)
    assert status == "listed"
    assert r["in"] == pytest.approx(usd[0] * 0.93, abs=1e-3)
    assert r["out"] == pytest.approx(usd[1] * 0.93, abs=1e-3)
    cost, flagged = cm.est_cost_eur(model, 1_000_000, 0)
    assert cost > 0 and flagged is False


def test_unknown_claude_model_falls_back_to_family():
    r, status = cm.rate_lookup("claude-opus-9")
    assert status == "assumed"
    assert r == cm._load_rates()["claude-opus-5-5"]  # nearest listed version, not zero
    cost, flagged = cm.est_cost_eur("claude-opus-9", 1_000_000, 1_000_000)
    assert cost > 0 and flagged is True


def test_fallback_nearest_version_and_dated_ids():
    assert cm.rate_lookup("claude-sonnet-5-6")[0] == cm._load_rates()["claude-sonnet-5-5"]
    r, status = cm.rate_lookup("claude-haiku-4-5-20251001")
    assert status == "assumed" and r == cm._load_rates()["claude-haiku-4-5"]
    assert cm.rate_lookup("claude-mythos-5-1")[0] == cm._load_rates()["claude-fable-5-1"]


def test_non_claude_unknown_still_zero():
    assert cm.rate_lookup("gpt-9-turbo") == (None, "none")
    assert cm.est_cost_eur("gpt-9-turbo", 10, 10) == (0.0, True)


def test_listed_model_not_marked_assumed():
    assert cm.rate_lookup("gpt-4o")[1] == "listed"
