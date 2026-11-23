"""Cards in message text open in flow, on a press, never as a hover overlay (MEMBERS-13, 2026-11-23).
hbar's screenshot: on a job report card, hovering a bold "Next:" showed a note over the text beside it,
and the tooltip "click: go deeper or send an agent" lay over the file links. Source checks on
ui/pages/cc.js; no network, no browser.

    pytest tests/test_cc_card_notes.py -v
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = (ROOT / "ui" / "pages" / "cc.js").read_text()
APP = (ROOT / "ui" / "pages" / "_app.js").read_text()


def _fn(name: str) -> str:
    start = CC.index(f"function {name}(")
    nxt = re.search(r"\n(?:function |const [A-Z]\w* = |// )", CC[start + 10:])
    return CC[start: start + 10 + (nxt.start() if nxt else len(CC))]


def test_info_card_lies_in_flow_not_over_the_text():
    box = _fn("InfoCard")
    assert "position: 'absolute'" not in box and "zIndex" not in box
    assert "position: 'static'" in box and "display: 'block'" in box
    assert 'data-infocard="1"' in box


def test_message_doors_carry_no_hover_note():
    for name in ("Highlight", "ActPhrase", "PathLink", "CommitLink", "LearnDoor", "InlineCode"):
        src = _fn(name)
        assert "onMouseEnter" not in src and "onMouseOver" not in src, name
    # the press target itself has no title= tooltip; CardDoor buttons inside an open card may keep theirs
    assert "go deeper or send an agent" in _fn("Highlight")
    for name, tag in (("Highlight", "<strong onClick"), ("ActPhrase", "<span data-nopick"), ("PathLink", "<a onClick"),
                      ("CommitLink", "<a data-nopick"), ("LearnDoor", "<a data-nopick"), ("InlineCode", "<code")):
        src = _fn(name)
        opener = src[src.index(tag):]
        opener = opener[: opener.index("style=")]   # the tag's attributes up to its style
        assert "title=" not in opener, name
        assert "aria-label=" in opener, name


def test_cut_job_result_lifts_while_a_card_is_open():
    assert 'className="cc-md cc-jobtext"' in CC
    assert ".cc-jobtext:has([data-infocard])" in APP
