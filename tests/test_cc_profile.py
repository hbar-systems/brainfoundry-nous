"""Profile interview for the CC console (scripts/cc/cc_profile.py and the bridge's /profile routes).
Created 2026-10-18. No network, no reasoner.

    pytest tests/test_cc_profile.py -v
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_profile as P  # noqa: E402

FULL = {"who": "A composer who runs a small studio.", "for": "Memory for my projects.", "length": "short",
        "tone": "direct", "structure": "mixed", "language": "English", "never": "flattery, templates",
        "ask": "judge", "keep": "I work at night."}


def test_validate_normalizes_and_refuses():
    assert P.validate(FULL) == FULL
    assert P.validate({}) == {}
    assert P.validate({"who": "   ", "keep": None}) == {}   # empty answers are unanswered
    for bad in ({"nope": "x"}, {"length": "long"}, {"tone": None and "x" or 3}, {"who": 5}, {"ask": "auto"}, []):
        with pytest.raises(P.ProfileError):
            P.validate(bad)


def test_free_text_is_one_capped_plain_line():
    a = P.validate({"who": "<script>alert(1)</script>**bold**\n## heading\n" + P.BEGIN + " [link](x) " + P.END,
                    "language": "x" * 500})
    for bad in ("<", ">", "*", "#", "\n", "[", "]", "profile:begin -->"):
        assert bad not in a["who"], bad
    assert "alert(1)" in a["who"] and "bold" in a["who"]
    assert len(a["language"]) == 40


def test_to_persona_md():
    md = P.to_persona_md(FULL)
    lines = md.splitlines()
    assert lines[0] == "## How to talk to me" and lines[1] == ""
    assert "- Who I am: A composer who runs a small studio." in lines
    assert any(x.startswith("- Answer length: short") for x in lines)
    assert any(x.startswith("- Acting on my box: use judgement") for x in lines)
    assert len(lines) == 2 + len(P.QUESTIONS)
    assert P.to_persona_md({}).endswith("- No preferences given yet.")
    assert P.recommended_posture(FULL) == "judged" and P.recommended_posture({"ask": "ask"}) == "cards"
    assert P.recommended_posture({"ask": "do"}) == "auto" and P.recommended_posture({}) is None


def test_marker_replace_keeps_the_rest():
    base = "# Lyra\n\nYou are Lyra.\n"
    one = P.replace_block(base, P.to_persona_md({"tone": "warm"}))
    assert one.startswith(base.rstrip()) and P.has_block(one) and "warm" in one
    two = P.replace_block(one + "\nAfter text.\n", P.to_persona_md({"tone": "direct"}))
    assert "warm" not in two and "direct" in two and two.count(P.BEGIN) == 1
    assert two.startswith(base.rstrip()) and two.endswith("After text.\n")
    assert P.replace_block("", "## x") == P.block("## x") + "\n"
    for broken in (base + P.BEGIN, base + P.END, P.END + P.BEGIN, P.block("a") + P.block("b")):
        with pytest.raises(P.ProfileError):
            P.replace_block(broken, "## x")
        assert not P.has_block(broken)


def test_clip_always_keeps_the_block():
    long = "x" * 7000
    text = P.replace_block("start\n" + long, P.to_persona_md(FULL))
    cut = P.clip_persona(text, 6000)
    assert len(cut) <= 6000 and P.has_block(cut) and cut.startswith("start")
    assert P.clip_persona("short", 6000) == "short"
    assert P.clip_persona(long, 6000) == long[:6000]


def test_unnamed():
    assert P.unnamed("") and P.unnamed("You are [BRAIN_NAME].") and not P.unnamed("You are Lyra.")


def test_interview_doc_matches_question_list():
    doc = (ROOT / "docs" / "profile-interview.md").read_text()
    assert 8 <= len(P.QUESTIONS) <= 10
    assert "<profile>{\"answers\":" in doc
    for q in P.QUESTIONS:
        row = next((ln for ln in doc.splitlines() if ln.startswith(f"| {q['id']} |")), None)
        assert row, q["id"]
        if "options" in q:
            for value, _label in q["options"]:
                assert value in row, (q["id"], value)
        else:
            assert f"free, up to {q['max']} characters" in row, q["id"]
    assert "—" not in doc   # no em-dashes in docs


def test_parse_marker_never_raises():
    clean, a, err = P.parse_marker('Done.\n<profile>{"answers": {"tone": "warm"}}</profile>')
    assert clean == "Done." and a == {"tone": "warm"} and err is None
    clean, a, err = P.parse_marker('x <profile>{"answers": {"tone": "loud"}}</profile>')
    assert a is None and "tone" in err and clean == "x"
    assert P.parse_marker('<profile>{"tone": "warm"}</profile>')[2]
    assert P.parse_marker("<profile>not json</profile>")[2]
    assert P.parse_marker("no marker") == ("no marker", None, None)


def test_store_proposals(tmp_path):
    s = P.Store(tmp_path)
    assert s.proposals() == [] and s.answers() == {}
    p = s.propose(FULL, "interview")
    [shown] = s.proposals()
    assert shown["id"] == p["id"] and shown["posture"] == "judged" and shown["persona_md"].startswith("## How")
    assert s.decide(p["id"], "applied") and s.proposals() == [] and not s.decide(p["id"], "applied")
    s.saved(FULL)
    assert s.answers() == FULL
    with pytest.raises(P.ProfileError):
        s.propose({"nope": 1}, "interview")
