"""The surfaces register, read for the console (SURFACES-1, 2026-11-24).

hbar 2026-11-24: "every time I say I not liking this production service, you don't bring the proper one for me to
evolve into". Saying a system's name in the chat shows that system as a card: its three to five actions as buttons.
The names, words, colours and addresses live only in the owner's world, one file per system:

  <world>/registry/surfaces/<name>.json
    {"name": "music", "system": "hbar.music", "say": ["music", "studio"], "hue": "#b5532f",
     "line": "make a track", "mark": "wave", "count_to": "2026-12-07" (optional),
     "actions": [{"label": "Sing", "open": "/sing", "kind": "page", "note": "..."},
                 {"label": "Listen", "ask": "listen on orfeo", "kind": "ask", "note": "..."}]}

`load(world)` returns {"surfaces": [...], "skipped": [{"file", "why"}]}; this template carries no names. Every value
is checked here, so the page renders what it gets:
  - name and system: registry ids (lowercase, dots, dashes); say-words: one to eight short lowercase phrases, a
    word said by two files goes to the first (by file name) and the second is told in `skipped`;
  - hue: #rrggbb; mark: one of MARKS (the card's one strong element), else "dot";
  - actions: one to five; each has a label and exactly one of `open` (a path on the console origin, "/..." but never
    "//", or an https address on the console's own host when CC_CONSOLE_HOST is set) or `ask` (text for the
    composer); kind is page, thread or ask;
  - count_to: an ISO date, shown as days left;
  - instruments (WALL-5, optional): up to eight things you open, fanned out around a system on the wall
    [{"name": "sing", "label": "sing", "open": "/sing", "on": ["hbar.music"], "hue": "#..", "mark": "wave", "note": ".."}]
    name: a registry-style id, unique across the register (a second one is dropped and told in `skipped`); label: one
    short word shown (default the name); exactly one of `open` (console origin, as above) or `ask` (text put in the
    host system's box, nothing sent); on: the systems it fans around (default the file's system); hue and mark
    default to the file's.
A file that fails is skipped whole, never half shown.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
HUE_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
SAY_RE = re.compile(r"^[a-z0-9][a-z0-9 ._-]{0,39}$")
MARKS = ("dot", "wave", "frames", "stroke", "ring", "grain", "count", "scales")
KINDS = ("page", "thread", "ask")
MAX_ACTIONS = 5
MAX_INSTRUMENTS = 8
MAX_ON = 6
MAX_FILES = 64
MAX_BYTES = 64 * 1024


def _text(v, n: int) -> str:
    return " ".join(str(v).split())[:n] if isinstance(v, str) else ""


def _open_ok(addr: str, host: str) -> str | None:
    """A console-origin address, or None. Relative paths stay relative; an absolute one on the console's own host
    is cut to its path, so it opens beside the chat on the same origin (the doors and the sign-in hold there)."""
    if not isinstance(addr, str) or not addr or len(addr) > 600 or any(c in addr for c in "\r\n\t\\"):
        return None
    if addr.startswith("/") and not addr.startswith("//"):
        return addr
    try:
        u = urlsplit(addr)
    except ValueError:
        return None
    if u.scheme == "https" and host and (u.hostname or "").lower() == host.lower() and u.path.startswith("/"):
        return u.path + (f"?{u.query}" if u.query else "")
    return None


def _instruments(v, system: str, hue: str, mark: str, host: str) -> tuple[list | None, str]:
    """A file's instruments checked (WALL-5), or (None, why)."""
    if not isinstance(v, list) or len(v) > MAX_INSTRUMENTS:
        return None, f"instruments: a list of at most {MAX_INSTRUMENTS}"
    out, names = [], set()
    for a in v:
        if not isinstance(a, dict):
            return None, "instrument"
        name = a.get("name")
        if not (isinstance(name, str) and ID_RE.match(name)) or name in names:
            return None, "instrument name"
        label = _text(a.get("label"), 16) or name
        has_open, has_ask = "open" in a, "ask" in a
        if has_open == has_ask:
            return None, f"instrument {name}: open or ask, one of them"
        item = {"name": name, "label": label, "note": _text(a.get("note"), 80)}
        if has_open:
            o = _open_ok(a.get("open"), host)
            if o is None:
                return None, f"instrument {name}: address off the console"
            item["open"] = o
        else:
            ask = a.get("ask")
            if not isinstance(ask, str) or not ask.strip() or len(ask) > 400:
                return None, f"instrument {name}: ask"
            item["ask"] = ask if ask.endswith(" ") else ask.strip()
        on = a.get("on", [system])
        if not isinstance(on, list) or not on or len(on) > MAX_ON or not all(isinstance(x, str) and ID_RE.match(x) for x in on):
            return None, f"instrument {name}: on"
        item["on"] = list(dict.fromkeys(on))
        h = a.get("hue", hue)
        if not (isinstance(h, str) and HUE_RE.match(h)):
            return None, f"instrument {name}: hue"
        item["hue"] = h.lower()
        item["mark"] = a.get("mark") if a.get("mark") in MARKS else mark
        names.add(name)
        out.append(item)
    return out, ""


def surface(d, host: str = "") -> tuple[dict | None, str]:
    """One register entry checked, or (None, why)."""
    if not isinstance(d, dict):
        return None, "not an object"
    name, system = d.get("name"), d.get("system")
    if not (isinstance(name, str) and ID_RE.match(name)):
        return None, "name"
    if not (isinstance(system, str) and ID_RE.match(system)):
        return None, "system"
    say = d.get("say")
    if not isinstance(say, list):
        return None, "say"
    words = []
    for w in say[:8]:
        w = " ".join(str(w).lower().split()) if isinstance(w, str) else ""
        if SAY_RE.match(w) and w not in words:
            words.append(w)
    if not words:
        return None, "say"
    hue = d.get("hue")
    if not (isinstance(hue, str) and HUE_RE.match(hue)):
        return None, "hue"
    acts = d.get("actions")
    if not isinstance(acts, list) or not acts:
        return None, "actions"
    out = []
    for a in acts:
        if not isinstance(a, dict):
            return None, "action"
        label = _text(a.get("label"), 24)
        if not label:
            return None, "action label"
        kind = a.get("kind") if a.get("kind") in KINDS else None
        has_open, has_ask = "open" in a, "ask" in a
        if has_open == has_ask:
            return None, f"action {label}: open or ask, one of them"
        item = {"label": label, "note": _text(a.get("note"), 80)}
        if has_open:
            o = _open_ok(a.get("open"), host)
            if o is None:
                return None, f"action {label}: address off the console"
            item.update(open=o, kind=kind if kind in ("page", "thread") else ("thread" if "thread=" in o else "page"))
        else:
            ask = a.get("ask")
            if not isinstance(ask, str) or not ask.strip() or len(ask) > 400:
                return None, f"action {label}: ask"
            item.update(ask=ask if ask.endswith(" ") else ask.strip(), kind="ask")
        out.append(item)
    if len(out) > MAX_ACTIONS:
        return None, "more than five actions"
    mark = d.get("mark") if d.get("mark") in MARKS else "dot"
    s = {"name": name, "system": system, "say": words, "hue": hue.lower(), "line": _text(d.get("line"), 60),
         "mark": mark, "actions": out}
    if "instruments" in d:
        ins, why = _instruments(d.get("instruments"), system, s["hue"], mark, host)
        if ins is None:
            return None, why
        s["instruments"] = ins
    ct = d.get("count_to")
    if ct is not None:
        try:
            s["count_to"] = date.fromisoformat(str(ct)).isoformat()
        except ValueError:
            return None, "count_to"
    return s, ""


def load(world: str | os.PathLike | None, host: str | None = None) -> dict:
    host = (host if host is not None else os.environ.get("CC_CONSOLE_HOST", "")).strip()
    if not world:
        return {"surfaces": [], "skipped": []}
    folder = Path(world) / "registry" / "surfaces"
    try:
        files = sorted(p for p in folder.iterdir() if p.suffix == ".json" and p.is_file())[:MAX_FILES]
    except OSError:
        return {"surfaces": [], "skipped": []}
    seen: dict[str, str] = {}
    names: set[str] = set()
    tools: dict[str, str] = {}   # instrument name -> the file that has it (WALL-5)
    got, skipped = [], []
    for p in files:
        try:
            if p.stat().st_size > MAX_BYTES:
                skipped.append({"file": p.name, "why": "too large"}); continue
            d = json.loads(p.read_text())
        except (OSError, ValueError):
            skipped.append({"file": p.name, "why": "not json"}); continue
        s, why = surface(d, host)
        if s is None:
            skipped.append({"file": p.name, "why": why}); continue
        if s["name"] in names:
            skipped.append({"file": p.name, "why": f"name {s['name']} twice"}); continue
        taken = [w for w in s["say"] if w in seen]
        for w in taken:
            skipped.append({"file": p.name, "why": f"say-word '{w}' is {seen[w]}'s"})
        s["say"] = [w for w in s["say"] if w not in seen]
        if not s["say"]:
            continue
        for w in s["say"]:
            seen[w] = s["name"]
        if s.get("instruments"):
            keep = []
            for i in s["instruments"]:
                if i["name"] in tools:
                    skipped.append({"file": p.name, "why": f"instrument '{i['name']}' is {tools[i['name']]}'s"})
                else:
                    tools[i["name"]] = s["name"]; keep.append(i)
            s["instruments"] = keep
        names.add(s["name"])
        got.append(s)
    return {"surfaces": got, "skipped": skipped}
