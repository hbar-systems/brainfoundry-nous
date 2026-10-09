"""cc_layout: the owner's layout file for the CC console. Created 2026-10-09.

Imported by cc-bridge.py (same directory). Standard library only.

A layout is a small, versioned, closed JSON object: which blocks of the console show, which side
the pane sits on and how wide, the column width, a colour preset plus a few colour variables, a
font by name, a size and weight, the default view, voice. It is DATA, never CSS: every key and every
value is checked against a fixed list, so a layout that came from another brain (a pack) or from the
interview cannot carry a style rule, a url or a script. Unknown keys are refused, not dropped.

Where it lives: <bridge state dir>/layout.json, beside board.json and threads.json. That is the
owner's file on the brain's box, outside every tracked template file, so Update never touches it.
It holds the current layout, a short history (one step back, "undo"), the interview answers, layouts
waiting for approval (proposals) and the ids of proposals already decided.

Sharing: a layout travels as a brain-app-style pack (brain-app.yaml, layout.json, dist/index.html)
through the existing install pipeline. Installed, the pack's layout.json is found in
brain-apps/<id>/ and shown as a PROPOSAL; nothing applies until the owner presses apply.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

VERSION = 1
HISTORY_CAP = 10
PROPOSAL_CAP = 20

PANELS = ("hero", "hint", "handsfree", "files", "board", "gallery", "sidebyside")
FONTS = ("system", "inter", "lora", "crimson", "dm-mono", "jetbrains")   # the console's own font picker
COLUMNS = ("narrow", "wide", "full")
THEMES = ("default", "black", "light")
SIZES = ("small", "normal", "large")
WEIGHTS = ("normal", "thin")
VIEWS = ("talk", "gallery", "panes")
VAR_KEYS = ("--accent", "--bg", "--surface", "--surface2", "--text", "--muted", "--border")
PANE_MIN, PANE_MAX = 280, 1400
NAME_MAX = 40
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Colour presets. "default" is the console's own palette and sets nothing.
PRESETS = {
    "default": {},
    "black": {"--bg": "#000000", "--surface": "#050505", "--surface2": "#0b0b0b", "--text": "#e6e6e6",
              "--muted": "#7a7a7a", "--border": "#1c1c1c", "--user-bg": "#e6e6e6", "--user-text": "#000000",
              "--code-bg": "#000000"},
    "light": {"--bg": "#f6f6f3", "--surface": "#efefea", "--surface2": "#e8e8e2", "--text": "#161616",
              "--muted": "#6e6e68", "--border": "#cfcfc7", "--user-bg": "#161616", "--user-text": "#f6f6f3",
              "--code-bg": "#161616"},
}
SIZE_ZOOM = {"small": 0.92, "normal": 1.0, "large": 1.12}


class LayoutError(ValueError):
    """A layout (or answers) that does not satisfy the closed schema."""


DEFAULT = {
    "v": VERSION, "name": None,
    "panels": {k: True for k in PANELS},
    "pane": {"side": "right", "width": None},
    "column": "narrow", "theme": "default", "vars": {},
    "font": None, "size": "normal", "weight": "normal",
    "view": "talk", "voice": {"speak": False, "handsfree": False},
}
_TOP = set(DEFAULT)


def _only(d, allowed, where):
    if not isinstance(d, dict):
        raise LayoutError(f"{where} must be an object")
    extra = set(d) - set(allowed)
    if extra:
        raise LayoutError(f"{where}: unknown key {sorted(extra)[0]!r}")


def _enum(v, options, where):
    if v not in options:
        raise LayoutError(f"{where} must be one of {', '.join(map(str, options))}")
    return v


def validate(obj) -> dict:
    """Return the normalized layout (every key present) or raise LayoutError. A missing key takes the
    default; a key that is present must be valid; an unknown key is an error."""
    _only(obj, _TOP, "layout")
    if obj.get("v", VERSION) != VERSION:
        raise LayoutError(f"layout version {obj.get('v')!r} is not supported (this brain reads v{VERSION})")
    out = json.loads(json.dumps(DEFAULT))
    if obj.get("name") is not None:
        n = obj["name"]
        if not isinstance(n, str) or not n.strip() or len(n) > NAME_MAX or re.search(r"[<>\x00-\x1f]", n):
            raise LayoutError(f"name must be plain text up to {NAME_MAX} characters")
        out["name"] = n.strip()
    if "panels" in obj:
        _only(obj["panels"], PANELS, "panels")
        for k, v in obj["panels"].items():
            if not isinstance(v, bool):
                raise LayoutError(f"panels.{k} must be true or false")
            out["panels"][k] = v
    if "pane" in obj:
        _only(obj["pane"], ("side", "width"), "pane")
        if "side" in obj["pane"]:
            out["pane"]["side"] = _enum(obj["pane"]["side"], ("left", "right"), "pane.side")
        w = obj["pane"].get("width")
        if w is not None:
            if isinstance(w, bool) or not isinstance(w, int) or not PANE_MIN <= w <= PANE_MAX:
                raise LayoutError(f"pane.width must be a whole number of pixels from {PANE_MIN} to {PANE_MAX}, or null")
            out["pane"]["width"] = w
    if "column" in obj:
        out["column"] = _enum(obj["column"], COLUMNS, "column")
    if "theme" in obj:
        out["theme"] = _enum(obj["theme"], THEMES, "theme")
    if "vars" in obj:
        _only(obj["vars"], VAR_KEYS, "vars")
        for k, v in obj["vars"].items():
            if not isinstance(v, str) or not _HEX.match(v):
                raise LayoutError(f"vars.{k} must be a colour like #c9a96e (six hex digits, nothing else)")
            out["vars"][k] = v.lower()
    if obj.get("font") is not None:
        out["font"] = _enum(obj["font"], FONTS, "font")
    if "size" in obj:
        out["size"] = _enum(obj["size"], SIZES, "size")
    if "weight" in obj:
        out["weight"] = _enum(obj["weight"], WEIGHTS, "weight")
    if "view" in obj:
        out["view"] = _enum(obj["view"], VIEWS, "view")
    if "voice" in obj:
        _only(obj["voice"], ("speak", "handsfree"), "voice")
        for k, v in obj["voice"].items():
            if not isinstance(v, bool):
                raise LayoutError(f"voice.{k} must be true or false")
            out["voice"][k] = v
    return out


def resolve(layout: dict) -> dict:
    """What the page applies: the preset's variables with the layout's own on top, the zoom for the
    size, the font weight. Computed here so the page holds no second copy of the presets."""
    lay = validate(layout)
    css = {**PRESETS[lay["theme"]], **lay["vars"]}
    return {"vars": css, "zoom": SIZE_ZOOM[lay["size"]], "weight": 300 if lay["weight"] == "thin" else None}


def layout_id(layout: dict) -> str:
    return hashlib.sha256(json.dumps(validate(layout), sort_keys=True).encode()).hexdigest()[:12]


def summary(layout: dict) -> str:
    """One plain line for a proposal card: what this layout changes from the stock console."""
    lay, parts = validate(layout), []
    off = [k for k in PANELS if not lay["panels"][k]]
    if off:
        parts.append("hides " + ", ".join(off))
    if lay["pane"]["side"] != "right" or lay["pane"]["width"]:
        parts.append(f"pane {lay['pane']['side']}" + (f" at {lay['pane']['width']}px" if lay["pane"]["width"] else ""))
    if lay["column"] != "narrow":
        parts.append(f"{lay['column']} column")
    if lay["theme"] != "default" or lay["vars"]:
        parts.append(f"{lay['theme']} colours" + (f" with {len(lay['vars'])} set" if lay["vars"] else ""))
    if lay["font"]:
        parts.append(f"font {lay['font']}")
    if lay["size"] != "normal":
        parts.append(f"{lay['size']} text")
    if lay["weight"] != "normal":
        parts.append(f"{lay['weight']} type")
    if lay["view"] != "talk":
        parts.append(f"opens on {lay['view']}")
    if lay["voice"]["speak"] or lay["voice"]["handsfree"]:
        parts.append("voice " + ("hands-free" if lay["voice"]["handsfree"] else "on"))
    return "; ".join(parts) or "the stock console"


# ---- the interview: a fixed list; docs/personalize-interview.md carries the same ids ----
# Each question: id, the words, and the options as (value, label). "never" is a multiple choice.
QUESTIONS = (
    {"id": "first", "ask": "What do you open first when you sit down?",
     "options": (("talk", "the conversation"), ("gallery", "my conversations as a deck"), ("panes", "several conversations side by side"))},
    {"id": "never", "ask": "Which of these do you never use? Say none if all of them stay.", "multi": True,
     "options": (("board", "board"), ("gallery", "gallery"), ("files", "files link"), ("sidebyside", "side by side"),
                 ("handsfree", "hands-free row"), ("hint", "the starter hints"), ("hero", "the title block"))},
    {"id": "panes", "ask": "When the brain opens a screen for you, one at a time beside the chat, or do you work with several?",
     "options": (("one", "one"), ("several", "several"))},
    {"id": "side", "ask": "Which side should the pane sit on?", "options": (("right", "right"), ("left", "left"))},
    {"id": "tone", "ask": "Black, light, or the stock warm dark?", "options": (("black", "black"), ("light", "light"), ("default", "stock"))},
    {"id": "face", "ask": "Serif, mono or sans for the conversation?",
     "options": (("serif", "serif"), ("mono", "mono"), ("sans", "sans"))},
    {"id": "weight", "ask": "Thin type or normal?", "options": (("thin", "thin"), ("normal", "normal"))},
    {"id": "size", "ask": "Text small, normal or large?", "options": (("small", "small"), ("normal", "normal"), ("large", "large"))},
    {"id": "width", "ask": "Narrow column, wide, or the full width?", "options": (("narrow", "narrow"), ("wide", "wide"), ("full", "full"))},
    {"id": "voice", "ask": "Voice: off, answers read aloud, or hands-free?",
     "options": (("off", "off"), ("speak", "read aloud"), ("handsfree", "hands-free"))},
)
_FACE = {"serif": "lora", "mono": "jetbrains", "sans": "system"}


def validate_answers(answers) -> dict:
    ids = {q["id"]: q for q in QUESTIONS}
    _only(answers, ids, "answers")
    out = {}
    for k, v in answers.items():
        q = ids[k]
        allowed = [o[0] for o in q["options"]]
        if q.get("multi"):
            if not isinstance(v, list) or any(x not in allowed for x in v):
                raise LayoutError(f"answers.{k} must be a list of: {', '.join(allowed)}")
            out[k] = sorted(set(v))
        else:
            out[k] = _enum(v, allowed, f"answers.{k}")
    return out


def from_answers(answers: dict) -> dict:
    """Turn interview answers into a layout. Unanswered questions leave the default."""
    a = validate_answers(answers)
    lay = json.loads(json.dumps(DEFAULT))
    if "first" in a:
        lay["view"] = a["first"]
    for k in a.get("never", []):
        lay["panels"][k] = False
    if a.get("panes") == "one":
        lay["panels"]["sidebyside"] = False
    if "side" in a:
        lay["pane"]["side"] = a["side"]
    if "tone" in a:
        lay["theme"] = a["tone"]
    if "face" in a:
        lay["font"] = _FACE[a["face"]]
    if "weight" in a:
        lay["weight"] = a["weight"]
    if "size" in a:
        lay["size"] = a["size"]
    if "width" in a:
        lay["column"] = a["width"]
    if "voice" in a:
        lay["voice"] = {"speak": a["voice"] in ("speak", "handsfree"), "handsfree": a["voice"] == "handsfree"}
    return validate(lay)


def parse_marker(text: str):
    """The reasoner's <layout>...</layout> block: either {"answers": {...}} or a full layout.
    Returns (text without the block, layout or None, error or None). Never applies anything."""
    m = re.search(r"<layout>\s*(.*?)\s*</layout>", text or "", re.S)
    if not m:
        return text, None, None
    clean = (text[:m.start()] + text[m.end():]).strip()
    try:
        obj = json.loads(m.group(1))
        lay = from_answers(obj["answers"]) if isinstance(obj, dict) and set(obj) == {"answers"} else validate(obj)
    except (ValueError, KeyError, TypeError) as e:
        return clean, None, str(e)[:200]
    return clean, lay, None


# ---- the file ----

class Store:
    def __init__(self, state_dir: Path, packs_dir: Path | None = None):
        self.path = Path(state_dir) / "layout.json"
        self.packs_dir = Path(packs_dir) if packs_dir else None
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

    def get(self) -> dict | None:
        """The current layout, or None when the owner has not set one (the stock console)."""
        cur = self._read().get("current")
        if cur is None:
            return None
        try:
            return validate(cur)
        except LayoutError:
            return None   # a hand-edited file that no longer validates falls back to stock, never to half a layout

    def save(self, layout: dict, answers: dict | None = None) -> dict:
        lay = validate(layout)
        with self.lock:
            d = self._read()
            if d.get("current") is not None:
                d["history"] = ([{"layout": d["current"], "t": int(time.time())}] + (d.get("history") or []))[:HISTORY_CAP]
            d["current"] = lay
            if answers is not None:
                d["answers"] = validate_answers(answers)
            self._write(d)
        return lay

    def answers(self) -> dict:
        try:
            return validate_answers(self._read().get("answers") or {})
        except LayoutError:
            return {}

    def undo(self) -> dict | None:
        with self.lock:
            d = self._read()
            hist = d.get("history") or []
            if not hist:
                return None
            d["current"] = hist[0]["layout"]
            d["history"] = hist[1:]
            self._write(d)
            return self.get()

    def reset(self) -> None:
        with self.lock:
            d = self._read()
            if d.get("current") is not None:
                d["history"] = ([{"layout": d["current"], "t": int(time.time())}] + (d.get("history") or []))[:HISTORY_CAP]
            d["current"] = None
            self._write(d)

    # proposals: layouts that wait for the owner's yes
    def propose(self, layout: dict, source: str, note: str = "", answers: dict | None = None) -> dict:
        lay = validate(layout)
        pid = layout_id(lay)
        with self.lock:
            d = self._read()
            props = [p for p in (d.get("proposals") or []) if p.get("id") != pid]
            p = {"id": pid, "source": str(source)[:80], "note": str(note)[:240], "t": int(time.time()), "layout": lay}
            if answers:
                p["answers"] = validate_answers(answers)
            d["proposals"] = ([p] + props)[:PROPOSAL_CAP]
            (d.setdefault("decided", {})).pop(pid, None)
            self._write(d)
        return p

    def _pack_proposals(self) -> list:
        out = []
        if not self.packs_dir or not self.packs_dir.is_dir():
            return out
        for f in sorted(self.packs_dir.glob("*/layout.json")):
            try:
                if f.stat().st_size > 20000:
                    continue
                lay = validate(json.loads(f.read_text()))
            except (OSError, ValueError):
                continue   # an installed pack with a layout that does not validate is simply not offered
            out.append({"id": layout_id(lay), "source": f"pack {f.parent.name}", "note": lay.get("name") or "", "t": int(f.stat().st_mtime), "layout": lay})
        return out

    def proposals(self) -> list:
        d = self._read()
        decided = d.get("decided") or {}
        cur = self.get()
        cur_id = layout_id(cur) if cur else None
        seen, out = set(), []
        for p in (d.get("proposals") or []) + self._pack_proposals():
            if p["id"] in decided or p["id"] in seen or p["id"] == cur_id:
                continue
            seen.add(p["id"])
            out.append({**p, "summary": summary(p["layout"])})
        return out

    def _decide(self, pid: str, how: str) -> None:
        d = self._read()
        d["proposals"] = [p for p in (d.get("proposals") or []) if p.get("id") != pid]
        decided = d.setdefault("decided", {})
        decided[pid] = how
        if len(decided) > 200:
            for k in list(decided)[:-200]:
                decided.pop(k)
        self._write(d)

    def approve(self, pid: str) -> dict | None:
        with self.lock:
            p = next((x for x in self.proposals() if x["id"] == pid), None)
            if p is None:
                return None
            lay = self.save(p["layout"], answers=p.get("answers"))
            self._decide(pid, "applied")
            return lay

    def dismiss(self, pid: str) -> bool:
        with self.lock:
            if not any(x["id"] == pid for x in self.proposals()):
                return False
            self._decide(pid, "dismissed")
            return True


# ---- sharing: the layout as a brain-app-style pack ----

def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40].strip("-")
    return s if len(s) >= 2 else "mine"


def export_pack(layout: dict, name: str | None = None, repo: str | None = None, author: str | None = None) -> dict:
    """The files of a pack another brain installs through the Apps page: brain-app.yaml (brain-app/v1,
    description under the schema's 240 characters), layout.json, and a one-page dist/index.html (the
    manifest needs a UI bundle or an api; this page only points the owner to the layout page).
    `repo` is where the owner will publish it; until set, a placeholder that still passes the schema
    is written and `repo_set` is false."""
    lay = validate(layout)
    title = (name or lay.get("name") or "my layout").strip()[:NAME_MAX]
    lay["name"] = title
    slug = _slug(title)
    app_id = f"layout-{slug}"
    set_ = bool(repo and re.match(r"^https://(github\.com|gitlab\.com|codeberg\.org)/\S+$", repo))
    desc = f"A console layout for a BrainFoundry brain: {summary(lay)}. Installing it only proposes the layout; the owner approves before anything changes."
    if len(desc) > 240:
        desc = desc[:237].rstrip() + "..."
    q = json.dumps  # a JSON string is a valid YAML scalar
    yaml = "\n".join([
        "# A layout pack: data only (layout.json), proposed to the owner on install, never applied by itself.",
        'dialect: "brain-app/v1"',
        f"id: {q(app_id)}",
        f"name: {q('layout ' + title)}",
        'version: "0.1.0"',
        f"description: {q(desc)}",
        'license: "MIT"',
        "author:",
        f"  name: {q((author or 'a brain owner')[:80])}",
        f"repo: {q(repo if set_ else 'https://github.com/OWNER/REPO')}",
        "tab:",
        '  label: "Layout"',
        f"  route: {q('/' + app_id)}",
        "  order: 900",
        "entries:",
        '  ui_bundle: "dist"',
        "",
    ])
    html = ("<!doctype html><meta charset=utf-8><title>layout pack</title>"
            "<body style=\"background:#000;color:#bbb;font:300 14px ui-monospace,monospace;padding:24px\">"
            f"<p>layout pack: {re.sub(r'[<>&]', '', title)}</p>"
            "<p>Its layout is waiting as a proposal. Open the layout page in the console to look at it and apply or dismiss it.</p>")
    return {"id": app_id, "repo_set": set_, "description": desc,
            "files": {"brain-app.yaml": yaml, "layout.json": json.dumps(lay, indent=1) + "\n", "dist/index.html": html}}
