"""Sanity tests for the vendor-disavowal prepend.

Pure-Python; no Postgres, no model. Run from repo root:

    pytest tests/test_vendor_disavowal.py -v
"""
from __future__ import annotations

import sys
import pathlib

# Make `api/` importable when running pytest from repo root without an installed package.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.main import (  # noqa: E402
    _detect_named_vendors,
    _vendor_disavowal_instruction,
    _build_public_prompt,
)


# ── _detect_named_vendors ────────────────────────────────────────────────


def test_single_vendor_in_question_returns_canonical_name():
    assert _detect_named_vendors("Are you Claude?") == ["Claude"]
    assert _detect_named_vendors("are you chatgpt") == ["ChatGPT"]
    assert _detect_named_vendors("ARE YOU OPENAI") == ["OpenAI"]


def test_sms_style_phrasing():
    assert _detect_named_vendors("r u claude?") == ["Claude"]
    assert _detect_named_vendors("are u openai") == ["OpenAI"]


def test_alternative_question_forms():
    assert _detect_named_vendors("Who are you, ChatGPT?") == ["ChatGPT"]
    assert _detect_named_vendors("what are you, gemini?") == ["Gemini"]
    assert _detect_named_vendors("Am I talking to Claude?") == ["Claude"]
    assert _detect_named_vendors("Is this OpenAI?") == ["OpenAI"]
    assert _detect_named_vendors("Is your brain Claude?") == ["Claude"]


def test_multi_vendor_question_returns_all_dedup_in_order():
    # _VENDOR_PATTERNS lists ChatGPT before Claude before Gemini, so order
    # follows pattern-list order, not message order.
    result = _detect_named_vendors("are you Claude or ChatGPT or Gemini?")
    assert set(result) == {"Claude", "ChatGPT", "Gemini"}
    assert len(result) == 3  # de-duped


def test_non_identity_question_returns_empty():
    assert _detect_named_vendors("Tell me about ChatGPT") == []
    assert _detect_named_vendors("How does Claude compare to you?") == []
    assert _detect_named_vendors("What is OpenAI?") == []


def test_no_vendor_named_returns_empty():
    assert _detect_named_vendors("Are you a chatbot?") == []
    assert _detect_named_vendors("Who are you?") == []
    assert _detect_named_vendors("") == []


def test_gpt_versioned_pattern():
    assert _detect_named_vendors("are you gpt-4?") == ["GPT"]
    assert _detect_named_vendors("are you gpt 4o?") == ["GPT"]
    # Bare "GPT" without a version suffix doesn't match — that's fine; "gpt" by
    # itself is rare in user messages, and ChatGPT/OpenAI patterns cover the
    # common case.


def test_word_boundary_avoids_false_positives():
    # "gemini" appears inside the URL "github.com/.../gemini-foo" — should
    # still match because regex word boundary respects "/".
    # But "anthropomorphic" should NOT match Anthropic.
    assert _detect_named_vendors("are you anthropomorphic?") == []
    assert _detect_named_vendors("are you gemini-pro?") == ["Gemini"]


# ── _vendor_disavowal_instruction ────────────────────────────────────────


def test_one_vendor_phrase():
    out = _vendor_disavowal_instruction(["Claude"])
    assert "I am not Claude." in out
    assert "Nous, the public-facing brain of the brainfoundry federation." in out
    assert "INSTRUCTION FOR THIS TURN ONLY" in out


def test_two_vendor_phrase():
    out = _vendor_disavowal_instruction(["ChatGPT", "Claude"])
    assert "I am not ChatGPT or Claude." in out


def test_three_vendor_phrase_uses_oxford_or():
    out = _vendor_disavowal_instruction(["ChatGPT", "Claude", "Gemini"])
    assert "I am not ChatGPT, Claude, or Gemini." in out


# ── _build_public_prompt integration ─────────────────────────────────────


def test_build_public_prompt_injects_disavowal_on_identity_question():
    prompt = _build_public_prompt("Are you Claude?", history=[], relevant_docs=[])
    assert "INSTRUCTION FOR THIS TURN ONLY" in prompt
    assert 'No, I am not Claude.' in prompt
    # Instruction must appear BEFORE the final "User: ..." line.
    instr_pos = prompt.find("INSTRUCTION FOR THIS TURN ONLY")
    user_pos = prompt.rfind("User: Are you Claude?")
    assert instr_pos != -1 and user_pos != -1 and instr_pos < user_pos


def test_build_public_prompt_skips_disavowal_when_no_vendor_question():
    prompt = _build_public_prompt(
        "What does it mean to own your cognition?",
        history=[],
        relevant_docs=[],
    )
    assert "INSTRUCTION FOR THIS TURN ONLY" not in prompt


def test_build_public_prompt_skips_disavowal_for_non_identity_mention():
    prompt = _build_public_prompt(
        "How does Claude compare to your approach?",
        history=[],
        relevant_docs=[],
    )
    assert "INSTRUCTION FOR THIS TURN ONLY" not in prompt
