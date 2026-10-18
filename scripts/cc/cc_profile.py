"""cc_profile: the owner's profile interview for the CC console. Created 2026-10-18.

Imported by cc-bridge.py (same directory). Standard library only.

The brain asks a fixed list of questions about how it should talk to its owner (QUESTIONS; the reasoner
reads docs/profile-interview.md, which a test keeps in step with this list) and ends one answer with a
<profile>{"answers": {...}}</profile> block. The bridge stores the answers as a PROPOSAL; nothing is
written until the owner presses apply. Applied, the answers become a short "## How to talk to me" section
(to_persona_md) inside a managed block of the persona file (api/brain_persona.local.md), between BEGIN and
END. Text outside the block is never touched; a later apply replaces the block.

Free-text answers are untrusted (they pass through the reasoner): tags, markdown marks and newlines are
stripped and each answer is capped, so an answer can only ever be one plain line inside the block. The
"ask" answer maps to a RECOMMENDED posture (cards, auto, judged); applying never changes the posture.

Where it lives: <bridge state dir>/profile.json, beside layout.json: the last applied answers, answers
waiting for approval (proposals) and the ids of proposals already decided.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

PROPOSAL_CAP = 20
BEGIN = "<!-- profile:begin (managed by the profile interview; change it at /profile) -->"
END = "<!-- profile:end -->"
HEADING = "## How to talk to me"
PLACEHOLDERS = ("[BRAIN_NAME]", "[OWNER_NAME]")   # the blank template's tokens (api/persona_tools.py)


class ProfileError(ValueError):
    """Answers that do not satisfy the fixed list, or a persona file whose markers are broken."""


# ---- the interview: a fixed list; docs/profile-interview.md carries the same ids ----
# Each question: id, the words, and either options as (value, label) or "max" (free text, one line).
QUESTIONS = (
    {"id": "who", "ask": "Who are you and what do you do, in a sentence or two?", "max": 240},
    {"id": "for", "ask": "What do you want this brain for?", "max": 240},
    {"id": "length", "ask": "Answers short, medium, or full?",
     "options": (("short", "short"), ("medium", "medium"), ("full", "full"))},
    {"id": "tone", "ask": "Direct, warm, or playful?",
     "options": (("direct", "direct"), ("warm", "warm"), ("playful", "playful"))},
    {"id": "structure", "ask": "Prose, bullets, or a mix?",
     "options": (("prose", "prose"), ("bullets", "bullets"), ("mixed", "a mix"))},
    {"id": "language", "ask": "Which language should it answer in?", "max": 40},
    {"id": "never", "ask": "What should it never do? (for example flattery, templates, preaching)", "max": 240},
    {"id": "ask", "ask": "On your own box, should it just do routine work, use judgement and ask about the risky things, or always ask first?",
     "options": (("do", "just do it"), ("judge", "judge and ask on risk"), ("ask", "always ask"))},
    {"id": "keep", "ask": "Anything it should always keep in mind?", "max": 300},
)
_BY_ID = {q["id"]: q for q in QUESTIONS}
POSTURE = {"do": "auto", "judge": "judged", "ask": "cards"}

_LINES = {
    "length": {"short": "short: a few sentences, the answer first", "medium": "medium: the answer and the reasons that matter",
               "full": "full: complete answers with the reasoning shown"},
    "tone": {"direct": "direct: plain words, no padding", "warm": "warm: friendly and patient, still to the point",
             "playful": "playful: light and quick, never at the cost of being right"},
    "structure": {"prose": "prose paragraphs", "bullets": "bullet points", "mixed": "prose, with bullets where a list helps"},
    "ask": {"do": "routine work on my box without asking; say what you did",
            "judge": "use judgement: routine work without asking, ask before anything risky or hard to undo",
            "ask": "always ask before you change anything on my box"},
}
_LABELS = (("who", "Who I am"), ("for", "What I want you for"), ("length", "Answer length"), ("tone", "Tone"),
           ("structure", "Structure"), ("language", "Language"), ("never", "Never"), ("ask", "Acting on my box"),
           ("keep", "Always keep in mind"))

_TAG = re.compile(r"<[^>]*>|<|>")
_MARKS = re.compile(r"[*_`#|\[\]~\\]+")
_SPACE = re.compile(r"[\s\x00-\x1f\x7f]+")


def clean_text(s: str, cap: int) -> str:
    """One plain line: no tags, no markdown marks, no newlines or control characters, at most cap characters."""
    s = _TAG.sub(" ", s)
    s = _MARKS.sub(" ", s)
    s = _SPACE.sub(" ", s).strip()
    if len(s) > cap:
        s = s[:cap].rstrip()
    return s


def validate(answers) -> dict:
    """Return the normalized answers (free text cleaned and capped; empty answers dropped) or raise
    ProfileError. Unknown keys are refused, not dropped."""
    if not isinstance(answers, dict):
        raise ProfileError("answers must be an object")
    extra = set(answers) - set(_BY_ID)
    if extra:
        raise ProfileError(f"answers: unknown key {sorted(extra)[0]!r}")
    out = {}
    for q in QUESTIONS:
        k = q["id"]
        if k not in answers or answers[k] is None:
            continue
        v = answers[k]
        if "options" in q:
            allowed = [o[0] for o in q["options"]]
            if v not in allowed:
                raise ProfileError(f"answers.{k} must be one of {', '.join(allowed)}")
            out[k] = v
        else:
            if not isinstance(v, str):
                raise ProfileError(f"answers.{k} must be text")
            t = clean_text(v, q["max"])
            if t:
                out[k] = t
    return out


def recommended_posture(answers: dict) -> str | None:
    return POSTURE.get(validate(answers).get("ask"))


def to_persona_md(answers: dict) -> str:
    """The "## How to talk to me" section, one line per answered question, in the list's order."""
    a = validate(answers)
    lines = [HEADING, ""]
    for k, label in _LABELS:
        if k in a:
            lines.append(f"- {label}: {_LINES[k][a[k]] if k in _LINES else a[k]}")
    if len(lines) == 2:
        lines.append("- No preferences given yet.")
    return "\n".join(lines)


def block(md: str) -> str:
    return f"{BEGIN}\n{md.strip()}\n{END}"


def _span(text: str):
    """(start, end) of the managed block, None when there is none; ProfileError when the markers are broken."""
    nb, ne = text.count(BEGIN), text.count(END)
    if nb == 0 and ne == 0:
        return None
    i, j = text.find(BEGIN), text.find(END)
    if nb != 1 or ne != 1 or j < i:
        raise ProfileError("the persona's profile markers are broken (each must appear once, begin before end); "
                           "fix them at /persona, then apply again")
    return i, j + len(END)


def has_block(text: str) -> bool:
    try:
        return _span(text or "") is not None
    except ProfileError:
        return False


def replace_block(text: str, md: str) -> str:
    """The persona text with the managed block set to md: replaced in place when present, appended at the
    end when absent. Nothing outside the markers changes."""
    text = text or ""
    sp = _span(text)
    if sp is None:
        return (text.rstrip() + "\n\n" if text.strip() else "") + block(md) + "\n"
    return text[:sp[0]] + block(md) + text[sp[1]:]


def clip_persona(text: str, cap: int) -> str:
    """The persona cut to cap characters, always keeping the managed block whole: when the text is too
    long, the rest is cut and the block is kept at its end."""
    text = text or ""
    if len(text) <= cap:
        return text
    try:
        sp = _span(text)
    except ProfileError:
        sp = None
    if sp is None:
        return text[:cap]
    blk = text[sp[0]:sp[1]]
    rest = (text[:sp[0]].rstrip() + "\n\n" + text[sp[1]:].lstrip()).strip()
    room = max(0, cap - len(blk) - 2)
    return (rest[:room].rstrip() + "\n\n" + blk).strip()


def unnamed(text: str) -> bool:
    """True for a brain still on the blank template (or with no persona): apply waits until it has a name."""
    return not (text or "").strip() or any(t in text for t in PLACEHOLDERS)


def answers_id(answers: dict) -> str:
    return hashlib.sha256(json.dumps(validate(answers), sort_keys=True).encode()).hexdigest()[:12]


def parse_marker(text: str):
    """The reasoner's <profile>{"answers": {...}}</profile> block. Returns (text without the block,
    answers or None, error or None). Never applies anything."""
    m = re.search(r"<profile>\s*(.*?)\s*</profile>", text or "", re.S)
    if not m:
        return text, None, None
    clean = (text[:m.start()] + text[m.end():]).strip()
    try:
        obj = json.loads(m.group(1))
        if not isinstance(obj, dict) or set(obj) != {"answers"}:
            raise ProfileError('the block must be {"answers": {...}}')
        a = validate(obj["answers"])
    except (ValueError, TypeError) as e:
        return clean, None, str(e)[:200]
    return clean, a, None


# ---- the file ----

class Store:
    def __init__(self, state_dir: Path):
        self.path = Path(state_dir) / "profile.json"
        self.lock = threading.RLock()

    def _read(self) -> dict:
        try:
            d = json.loads(self.path.read_text())
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _write(self, d: dict) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        tmp.replace(self.path)

    def answers(self) -> dict:
        try:
            return validate(self._read().get("answers") or {})
        except ProfileError:
            return {}

    def saved(self, answers: dict) -> dict:
        """Record answers that were just written into the persona."""
        a = validate(answers)
        with self.lock:
            d = self._read()
            d["answers"] = a
            d["applied_t"] = int(time.time())
            self._write(d)
        return a

    def propose(self, answers: dict, source: str) -> dict:
        a = validate(answers)
        pid = answers_id(a)
        with self.lock:
            d = self._read()
            props = [p for p in (d.get("proposals") or []) if p.get("id") != pid]
            p = {"id": pid, "source": str(source)[:80], "t": int(time.time()), "answers": a}
            d["proposals"] = ([p] + props)[:PROPOSAL_CAP]
            (d.setdefault("decided", {})).pop(pid, None)
            self._write(d)
        return p

    def proposals(self) -> list:
        d = self._read()
        decided = d.get("decided") or {}
        out = []
        for p in d.get("proposals") or []:
            if p.get("id") in decided:
                continue
            try:
                a = validate(p.get("answers") or {})
            except ProfileError:
                continue   # a hand-edited proposal that no longer validates is not offered
            out.append({**p, "answers": a, "persona_md": to_persona_md(a), "posture": recommended_posture(a)})
        return out

    def proposal(self, pid: str) -> dict | None:
        return next((x for x in self.proposals() if x["id"] == pid), None)

    def decide(self, pid: str, how: str) -> bool:
        with self.lock:
            if self.proposal(pid) is None:
                return False
            d = self._read()
            d["proposals"] = [p for p in (d.get("proposals") or []) if p.get("id") != pid]
            decided = d.setdefault("decided", {})
            decided[pid] = how
            if len(decided) > 200:
                for k in list(decided)[:-200]:
                    decided.pop(k)
            self._write(d)
            return True
