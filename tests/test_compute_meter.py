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
    # claude-opus-4-8 seed: in 14, out 70 €/Mtoken.
    cost, uncosted = cm.est_cost_eur("claude-opus-4-8", 1_000_000, 1_000_000)
    assert uncosted is False
    assert round(cost, 6) == round(14.0 + 70.0, 6)


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
