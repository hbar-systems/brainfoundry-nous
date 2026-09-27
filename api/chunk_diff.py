"""Chunk-level memory updates (2026-09-27).

Until now a changed document was re-ingested whole: every chunk re-embedded, the old chunks
retired afterwards. The operator noticed it on a document that changes with every push. Now
an ingest of a name that memory already holds keeps the chunks whose text did not change,
embeds only the new ones, and deletes only the ones that disappeared. Kept chunks get a fresh
created_at so the reconciler's "retire older chunks" step does not sweep them.

The plan is pure and tested here; the database work stays in api/main.py.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:24]


def plan_update(new_chunks: List[str], existing: Dict[str, List[int]]) -> Tuple[List[Tuple[int, str]], List[Tuple[int, int]], List[int]]:
    """Given the new chunks in order and the existing rows as {hash: [row ids]}, return
    (to_embed, reused, stale): the (index, text) pairs that need an embedding, the
    (index, row id) pairs kept as they are, and the row ids to delete. A hash present twice
    in the new text reuses two existing rows if there are two, else embeds the extra."""
    pool = {h: list(ids) for h, ids in existing.items()}
    to_embed, reused = [], []
    for i, c in enumerate(new_chunks):
        h = chunk_hash(c)
        if pool.get(h):
            reused.append((i, pool[h].pop(0)))
        else:
            to_embed.append((i, c))
    stale = [rid for ids in pool.values() for rid in ids]
    return to_embed, reused, stale
