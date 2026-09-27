"""Chunk-level memory updates (api/chunk_diff.py): the pure plan. No database.

Run from repo root:
    pytest tests/test_chunk_diff.py -v
"""
from __future__ import annotations

from api.chunk_diff import chunk_hash, plan_update


def test_unchanged_document_embeds_nothing():
    chunks = ["alpha", "beta", "gamma"]
    existing = {chunk_hash(c): [i + 1] for i, c in enumerate(chunks)}
    to_embed, reused, stale = plan_update(chunks, existing)
    assert to_embed == [] and stale == []
    assert reused == [(0, 1), (1, 2), (2, 3)]


def test_one_changed_chunk_embeds_one_and_retires_one():
    old = ["alpha", "beta", "gamma"]
    existing = {chunk_hash(c): [i + 1] for i, c in enumerate(old)}
    new = ["alpha", "beta changed", "gamma"]
    to_embed, reused, stale = plan_update(new, existing)
    assert to_embed == [(1, "beta changed")]
    assert reused == [(0, 1), (2, 3)]
    assert stale == [2]


def test_new_document_embeds_everything():
    to_embed, reused, stale = plan_update(["a", "b"], {})
    assert [i for i, _ in to_embed] == [0, 1] and reused == [] and stale == []


def test_duplicate_chunks_reuse_as_many_rows_as_exist():
    existing = {chunk_hash("same"): [7]}
    to_embed, reused, stale = plan_update(["same", "same"], existing)
    assert reused == [(0, 7)] and to_embed == [(1, "same")] and stale == []


def test_hash_ignores_surrounding_whitespace_only():
    assert chunk_hash("x\n") == chunk_hash("  x") and chunk_hash("x") != chunk_hash("y")
