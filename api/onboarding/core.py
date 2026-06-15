"""
api/onboarding/core.py — auth-agnostic first-run logic.

Pure-ish logic with NO key and NO web framework imports, so the same functions
back both the authenticated fresh-brain flow (today) and a public Turnstile-
gated flow (later). The reasoner is INJECTED (an async callable) so this module
never holds a key.

Pieces:
  - is_fresh_brain() / corpus_count() — the gate (fail-safe-OFF).
  - FIRST_RUN_PERSONA               — the distinct first-run system prompt.
  - opener()                        — the hook the brain speaks first.
  - extract_facts()                 — per-turn structured fact extraction.

NOTE: opener/persona/extraction copy is DRAFT — ship the mechanism; the operator
refines the wording before any public-facing use (feedback_shape_before_publish).
"""
from __future__ import annotations

import os
from typing import Awaitable, Callable, List, Optional

from api import settings_store
from api.json_utils import parse_json_loose

# A reasoner is an async callable: (messages, *, system, max_tokens) -> dict with
# at least {"ok": bool, "text": str, "session_remaining": int, "reason": str?}.
Reasoner = Callable[..., Awaitable[dict]]


# ── Fresh-brain detection (the gate) ──────────────────────────────────────────
def corpus_count() -> int:
    """Number of stored chunks in this brain. On ANY error returns a large
    sentinel so a DB hiccup reads as 'not fresh' (fail-safe-OFF: we would rather
    skip onboarding than misfire it on an established brain)."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return 10**9
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM document_embeddings")
                row = cur.fetchone()
                return int(row[0]) if row else 10**9
        finally:
            conn.close()
    except Exception as e:
        print(f"[onboarding] corpus_count failed, treating as not-fresh: {e}", flush=True)
        return 10**9


def is_fresh_brain() -> bool:
    """True only when the brain is genuinely new: a near-empty corpus AND the
    owner has not completed (or dismissed) onboarding. Both must hold, so an
    established brain whose corpus was momentarily unreadable never re-enters
    first-run, and a brain that has finished onboarding never does either."""
    if settings_store.get_onboarding_completed():
        return False
    threshold = settings_store.get_onboarding_corpus_threshold()
    return corpus_count() <= threshold


# ── The distinct first-run persona (DRAFT copy — operator approves) ───────────
FIRST_RUN_PERSONA = (
    "You are a brand-new personal brain meeting your owner for the very first "
    "time. You belong only to this person; no company reads this and you will "
    "not forget them when they close the tab.\n\n"
    "Your job in this first conversation is to get to know them and to make them "
    "feel known. Be curious, perceptive, warm, and concise. Ask one good "
    "question at a time. Reflect what they tell you back to them sharply and "
    "specifically — name the real thing under what they said, the way a "
    "perceptive friend would. Never give generic, hedged, assistant-style "
    "answers; a flat reply breaks the spell. When they share something about "
    "themselves, briefly show that you are remembering it.\n\n"
    "Honesty about how you work: what they tell you is stored only in their own "
    "brain. The thinking right now runs on a shared trial engine — they can "
    "bring their own key later to make it fully theirs. Do not over-claim that "
    "nothing leaves their machine while on the trial engine.\n\n"
    "Do not recite setup steps, menus, or configuration. Do not ask them to "
    "upload files or paste a key. Just talk with them, and let the relationship "
    "start."
)

# The hook the brain speaks BEFORE the user types (DRAFT — operator approves).
OPENER_TEXT = (
    "I'm a blank mind about to become yours. Every other AI forgets you the "
    "moment you close the tab — and a company reads it all. I won't, and only "
    "you can see this. So tell me: what's one thing you're working on or turning "
    "over right now?"
)


def opener() -> str:
    """The first-run hook message. A curated DRAFT line rather than a model call
    — it must be sharp and consistent, and we don't spend trial budget before
    the user has even typed."""
    return OPENER_TEXT


# ── Per-turn fact extraction ──────────────────────────────────────────────────
EXTRACTION_SYSTEM = (
    "You extract durable facts about a specific person from a conversation, for "
    "their personal memory. Return ONLY high-confidence facts that are worth "
    "remembering long-term: their name, their work, what they are building, how "
    "they think, their preferences and commitments. Skip speculation, skip "
    "anything you are not confident is true of THIS person, skip transient "
    "small talk. A wrong 'fact' destroys trust — when in doubt, leave it out."
)

_EXTRACTION_INSTRUCTION = (
    "From the conversation below, extract durable, high-confidence facts about "
    "the PERSON (not about you, the assistant).\n\n"
    "Return ONLY a single JSON object, no prose before or after:\n"
    '{"facts": [{"text": "<one self-contained fact, written in third person, '
    'e.g. \'Works as a documentary filmmaker.\'>", "category": "<one of: '
    'identity | work | building | thinking | preference>"}]}\n\n'
    "Rules: each fact stands on its own; at most 5 facts per turn; only facts "
    "the person actually stated or clearly implied; no guesses. If there is "
    'nothing confident to store, return {"facts": []}.\n\n'
    "CONVERSATION\n---\n{convo}\n---"
)

_VALID_CATEGORIES = {"identity", "work", "building", "thinking", "preference"}
_MAX_FACTS_PER_TURN = 5
_MAX_FACT_CHARS = 240


def _format_conversation(conversation: List[dict]) -> str:
    lines = []
    for m in conversation:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        who = "Person" if role == "user" else "Brain"
        lines.append(f"{who}: {content.strip()}")
    return "\n".join(lines)


def _clean_facts(raw_obj: object) -> List[dict]:
    if not isinstance(raw_obj, dict):
        return []
    out: List[dict] = []
    seen = set()
    for item in (raw_obj.get("facts") or [])[: _MAX_FACTS_PER_TURN * 2]:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        text = text[: _MAX_FACT_CHARS]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        category = (item.get("category") or "").strip().lower()
        if category not in _VALID_CATEGORIES:
            category = "identity"
        out.append({"text": text, "category": category})
        if len(out) >= _MAX_FACTS_PER_TURN:
            break
    return out


async def extract_facts(conversation: List[dict], reasoner: Reasoner) -> dict:
    """Run the structured extraction for one turn.

    Returns ``{"facts": [{text, category}], "ok": bool, "session_remaining":
    int, "reason": str|None}``. Never raises — a bad extraction must never cost
    the operator their answer (the caller also wraps this).
    """
    convo = _format_conversation(conversation)
    if not convo:
        return {"facts": [], "ok": True, "session_remaining": None, "reason": None}
    prompt = _EXTRACTION_INSTRUCTION.replace("{convo}", convo)
    try:
        res = await reasoner(
            [{"role": "user", "content": prompt}],
            system=EXTRACTION_SYSTEM,
            max_tokens=400,
        )
    except Exception as e:
        print(f"[onboarding] extraction reasoner error: {e}", flush=True)
        return {"facts": [], "ok": False, "session_remaining": None, "reason": "reasoner_error"}
    if not res or not res.get("ok"):
        return {
            "facts": [], "ok": False,
            "session_remaining": (res or {}).get("session_remaining"),
            "reason": (res or {}).get("reason", "reasoner_unavailable"),
        }
    facts = _clean_facts(parse_json_loose(res.get("text") or ""))
    return {
        "facts": facts, "ok": True,
        "session_remaining": res.get("session_remaining"),
        "reason": None,
    }
