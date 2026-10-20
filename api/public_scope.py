"""
One meaning of "public" in memory (2026-10-20).

Before: the public chat chose its chunks by `metadata.layer` (default "public") and checked
`metadata.scope` only when PUBLIC_CHAT_SCOPE was set; the ask door kept only `metadata.scope ==
"public"`. A chunk could be public to strangers and invisible to other brains, or the reverse, and
`layer` (what kind of memory: semantic, episodic, ...) was doing the job of a visibility mark.

Now `metadata.scope == "public"` is the one mark, read by every outside door: the public chat, the
older federation query and the ask door. `layer` is only the kind of memory again; PUBLIC_CHAT_LAYERS
may still narrow the public chat to some layers, never widen it. `privacy` (open or local-only, which
models may read a chunk) is a separate axis, and no outside door reads local-only memory.

Compatibility, so nothing a brain already shows strangers disappears:
- On start, chunks with layer "public" and no scope get scope "public" (MIGRATE_SQL, idempotent).
  They were already answered to any stranger on the public chat; from then on the ask door, which
  answers only introduced brains unless public asking is on, can use them too.
- A trigger gives every new or changed chunk with layer "public" and no scope the same mark, so
  every writer (upload, consolidation, scripts) follows the rule without each being changed.
- A local-only chunk is never marked public by either.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

PUBLIC = "public"

INDEX_SQL = ("CREATE INDEX IF NOT EXISTS document_embeddings_scope_idx "
             "ON document_embeddings ((metadata->>'scope')) WHERE metadata->>'scope' IS NOT NULL")

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION bf_public_scope() RETURNS trigger AS $$
BEGIN
  IF NEW.metadata IS NOT NULL
     AND NEW.metadata->>'layer' = 'public'
     AND NEW.metadata->>'scope' IS NULL
     AND COALESCE(NEW.metadata->>'privacy', 'open') = 'open' THEN
    NEW.metadata := NEW.metadata || '{"scope": "public"}'::jsonb;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS bf_public_scope ON document_embeddings;
CREATE TRIGGER bf_public_scope BEFORE INSERT OR UPDATE OF metadata ON document_embeddings
  FOR EACH ROW EXECUTE FUNCTION bf_public_scope();
"""

MIGRATE_SQL = """
UPDATE document_embeddings
SET metadata = metadata || '{"scope": "public"}'::jsonb
WHERE metadata->>'layer' = 'public'
  AND metadata->>'scope' IS NULL
  AND COALESCE(metadata->>'privacy', 'open') = 'open'
"""


def is_public(metadata: Optional[Dict[str, Any]]) -> bool:
    """The rule in Python, for a chunk already in hand: scope is public and it is not local-only."""
    m = metadata or {}
    return m.get("scope") == PUBLIC and (m.get("privacy") or "open") == "open"


def ensure(cur) -> int:
    """Index, trigger and the one-time mark, on a cursor with autocommit. Returns chunks newly marked."""
    cur.execute(INDEX_SQL)
    cur.execute(TRIGGER_SQL)
    cur.execute(MIGRATE_SQL)
    return max(cur.rowcount or 0, 0)


def layers_from_env(value: Optional[str]) -> Optional[list]:
    """PUBLIC_CHAT_LAYERS: a comma list that narrows the public chat to those layers, or None."""
    parts = [s.strip() for s in (value or "").split(",") if s.strip()]
    return parts or None
