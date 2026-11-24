"""A thread's skin and the console's default skin, on the box (SKIN-4, 2026-11-24).

hbar 2026-11-24: "I WANT SKINS TO CHANGE INDIVIDUALLY BY THREAD AND STOP RECHANGING COLOR WHEN I OPEN NEW THREAD,
OR RELOAD THE PAGE OR ANYTHING ELSE AS SUCH."

One source of truth, the bridge; the page only caches (ui/lib/skin.js).
  a thread's own look   the thread record's `style` (thread_style below), read by id at GET /cc/threads/style,
                        never through the filtered thread list, written only by that thread's own page
                        (POST /cc/threads/update).
  the console default   ~/.cc-bridge/skin.json {"skin", "font"} (GET/POST /cc/skin): what a thread with no skin
                        of its own wears, and every page that is not a thread. Changing it never writes a thread.
  a thread started from another thread (a choices button of mode "agent", REPORT-1) is born in its parent's
  skin and font, copied once when it is made (child_style). The parent is never written; after that the two
  are separate.
Pure functions plus two small file helpers, so the browser test's fake bridge runs the same rules.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SKINS = ("gold", "paper", "sapphire", "forest", "crimson", "mono", "fox", "octopus", "owl", "dusk", "ocean", "rose", "sage", "sand")
# the [data-font] tokens of ui/lib/skin.js FONT_SHAPES (SKIN-3)
FONTS = ("system", "inter", "lora", "crimson", "dm-mono", "jetbrains")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# what a child thread takes from its parent: the skin and the font, and the accent the wheel gave it
INHERITED = ("skin", "font", "accent", "tint")


def thread_style(raw) -> dict | None:
    """The look of one thread (2026-10-13, the tool line): accent colour, tint strength, text size, density, skin,
    font (SKIN-3), learning mode. Unknown keys and bad values are dropped, never stored; an empty dict clears the
    look. None when the value is not a dict at all."""
    if not isinstance(raw, dict):
        return None
    out = {}
    if isinstance(raw.get("accent"), str) and _HEX.match(raw["accent"]):
        out["accent"] = raw["accent"].lower()
    if isinstance(raw.get("tint"), (int, float)) and not isinstance(raw.get("tint"), bool):
        out["tint"] = max(0, min(30, int(raw["tint"])))
    if raw.get("text") in ("14px", "16px", "18px"):
        out["text"] = raw["text"]
    if raw.get("density") in ("compact", "comfortable"):
        out["density"] = raw["density"]
    if raw.get("skin") in SKINS:
        out["skin"] = raw["skin"]
    if raw.get("font") in FONTS:
        out["font"] = raw["font"]
    if raw.get("learn") is True:
        out["learn"] = True
    return out


def child_style(parent_style) -> dict:
    """The look a thread started from `parent_style`'s thread is born with: the parent's skin, font, accent and
    tint, nothing else. {} when the parent has none (the child then wears the default)."""
    s = thread_style(parent_style) or {}
    return {k: s[k] for k in INHERITED if k in s}


def default_skin(raw) -> dict:
    """The console default, cleaned: {"skin", "font"}, each only when valid."""
    out = {}
    if isinstance(raw, dict):
        if raw.get("skin") in SKINS:
            out["skin"] = raw["skin"]
        if raw.get("font") in FONTS:
            out["font"] = raw["font"]
    return out


def load_default(path: Path) -> dict:
    try:
        return default_skin(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        return {}


def save_default(path: Path, raw) -> dict:
    """Merge `raw` into the stored default (a skin alone keeps the font) and write it atomically."""
    cur = load_default(path)
    cur.update(default_skin(raw))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(cur, sort_keys=True))
    os.replace(tmp, p)
    return cur
