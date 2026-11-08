"""cc_doors: the doors view of the console, a few large doors by activity. Created 2026-11-08.

Imported by cc-bridge.py (same directory). Standard library only.

hbar 2026-11-08 (Elena and Alexander after the welcome): "threads, with an option of view: traditional
(current) or their respective doors depending on which activity they want to do". The layout's view
"doors" (cc_layout.VIEWS) shows these on an empty thread; a door puts its opening line into the input of
that blank thread, the person finishes the sentence and sends. Nothing is sent by a door.

The doors are generated, never written per person: a fixed list of activities (ACTIVITIES), each lit by
words in the brain's persona (brain_persona.local.md) or by an installed brain app (its id, name and
description). The persona and app text only choose among the fixed doors; no text of theirs reaches a
door's title, line or prompt, so a persona or an app cannot write onto the page.
"""
from __future__ import annotations

import re

MAX_DOORS = 4

# id, title, line under it, the prompt it puts in the input, and the words (whole-word prefixes, lower
# case) in persona or app text that light it. Order is the order shown when several are lit.
ACTIVITIES = (
    {"id": "lectures", "title": "Lectures and decks", "line": "prepare a lecture, a talk or slides",
     "prompt": "Help me prepare a lecture on ",
     "words": ("lectur", "teach", "course", "slide", "deck", "seminar", "curricul", "professor", "student")},
    {"id": "university", "title": "Ask the university", "line": "a question to the study shelves and their sources",
     "prompt": "Ask the university: ",
     "words": ("universit", "study", "studies", "learn", "medicin", "doctor", "clinic", "research", "science", "physic")},
    {"id": "music", "title": "Music", "line": "a track, a loop, an idea to play",
     "prompt": "Let's work on music: ",
     "words": ("music", "song", "track", "beat", "loop", "produc", "guitar", "piano", "singer", "singing", "band", "ableton")},
    {"id": "reading", "title": "Reading", "line": "a book, a paper or a page, read with you",
     "prompt": "I'm reading ",
     "words": ("readi", "reade", "book", "paper", "article", "literat", "novel", "poem", "poet")},
    {"id": "writing", "title": "Writing", "line": "a letter, an essay, a draft",
     "prompt": "Help me write ",
     "words": ("writ", "essay", "blog", "letter", "draft", "journal")},
    {"id": "people", "title": "People", "line": "someone to remember or to write to",
     "prompt": "About someone I know: ",
     "words": ("people", "friend", "family", "contact")},
    {"id": "today", "title": "Today", "line": "the day: calendar, mail and tasks",
     "prompt": "What is on today?",
     "words": ("today", "calendar", "daybook", "schedul", "agenda")},
)
# The door every brain has, last: the plain thread.
TALK = {"id": "talk", "title": "Just talk", "line": "a blank thread, anything", "prompt": ""}
# A door lit by nothing still fills a short row, in this order.
FALLBACK = ("today", "reading", "writing")
_BY_ID = {a["id"]: a for a in ACTIVITIES}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _lit(words: list[str], activity: dict) -> int:
    return sum(1 for w in words if any(w.startswith(p) for p in activity["words"]))


def app_text(apps) -> str:
    """The words of the enabled installed apps (id, name, description), as one string."""
    out = []
    for a in apps or []:
        if not isinstance(a, dict) or not a.get("enabled", True):
            continue
        out.append(" ".join(str(a.get(k) or "") for k in ("id", "name", "description")).replace("-", " "))
    return " ".join(out)


def doors(persona: str = "", apps=None, limit: int = MAX_DOORS) -> list[dict]:
    """The doors for this brain: up to `limit` lit activities (persona words count twice, they are the
    person; an app is what is installed), the fallbacks when fewer than three are lit, then Just talk."""
    pw, aw = _words(persona), _words(app_text(apps))
    score = {a["id"]: 2 * _lit(pw, a) + _lit(aw, a) for a in ACTIVITIES}
    order = [a["id"] for a in ACTIVITIES]
    picked = sorted((i for i in order if score[i] > 0), key=lambda i: (-score[i], order.index(i)))[:limit]
    for i in FALLBACK:
        if len(picked) >= min(3, limit):
            break
        if i not in picked:
            picked.append(i)
    return [{k: _BY_ID[i][k] for k in ("id", "title", "line", "prompt")} for i in picked] + [dict(TALK)]
