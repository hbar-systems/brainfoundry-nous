"""appearance.py — "Customize your brain" v0 (constrained-config plane).

A per-brain APPEARANCE/LAYOUT config the owner edits from a Settings tab without
opening Claude Code. This is the appearance plane ONLY — NOT server control
(docker/ports/deploy stay in the hbar/nous CLI) and NOT code/file editing (the
gated "Claude Code in the brain" lane). The ONLY thing this can write is a
validated config object against a fixed, closed schema: no file writes beyond
the single config sidecar, no SQL, no shell, no template/source mutation. The
action space is a JSON object — that is what keeps the write-lane gate closed.

The brain stays thick: this changes presentation only. Reasoner, memory/RAG,
tools, and brain-apps are untouched.

Storage: a JSON sidecar at /app/runtime/appearance.json (the same named-volume
pattern as settings_store.py — a named docker volume, NOT a host bind-mount, so
the container-root-chown hazard does not apply). Holds the current config plus a
capped snapshot history for strict Revert + Reset.

Created 2026-06-21 (decision D48).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

APPEARANCE_PATH = Path(os.getenv("APPEARANCE_PATH", "/app/runtime/appearance.json"))
_LOCK = threading.RLock()
_HISTORY_CAP = 20

# ── Closed schema ────────────────────────────────────────────────────────────
# Themes are the [data-theme] palettes in ui/pages/_app.js (gold = default :root).
ALLOWED_THEMES = {
    "gold", "paper", "sapphire", "forest", "crimson", "mono", "fox", "octopus", "owl",
}
# Accent palette: "default" keeps the theme's own accent; otherwise a fixed set
# of hexes (the per-theme accents in _app.js) — a closed palette, not free input.
ACCENT_PALETTE = {
    "default", "#c9a96e", "#8a6e3c", "#6b8cce", "#88a868", "#c87878",
    "#b0b0b0", "#d77a3a", "#3a9ea0", "#5b4d80",
}
_MENU_TITLE_MAX = 40
# Tabs the owner must never be able to hide (would lock them out of this very
# config plane). Always rendered regardless of hiddenTabs.
_PROTECTED_TABS = {"_settings"}

ALLOWED_FIELDS = {"menuTitle", "theme", "accent", "hiddenTabs", "tabOrder"}

DEFAULT_CONFIG: Dict[str, Any] = {
    "menuTitle": None,      # None -> use the brain's default brand name
    "theme": "gold",
    "accent": "default",
    "hiddenTabs": [],
    "tabOrder": [],
}


def _known_tab_ids() -> List[str]:
    """The canonical built-in tab ids (source of truth: apps.BUILTIN_TABS)."""
    try:
        from api.apps import BUILTIN_TABS
        return [t["id"] for t in BUILTIN_TABS]
    except Exception:
        # Fallback mirrors apps.BUILTIN_TABS so validation still works in tests.
        return ["_dashboard", "_chat", "_persona", "_knowledge", "_apps",
                "_federation", "_tasks", "_research", "_integrations",
                "_economy", "_trace", "_settings", "_update", "_future"]


# ── Validation (reject anything not in the schema) ───────────────────────────

class AppearanceError(ValueError):
    """Raised when a write does not satisfy the closed schema."""


def validate(patch: Dict[str, Any], *, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge `patch` onto `base` (default config) and validate the RESULT against
    the closed schema. Returns the cleaned full config. Raises AppearanceError on
    any out-of-schema field, type, value, or unknown tab id."""
    if not isinstance(patch, dict):
        raise AppearanceError("config must be an object")
    unknown = set(patch) - ALLOWED_FIELDS
    if unknown:
        raise AppearanceError(f"unknown field(s): {sorted(unknown)}")

    cfg = dict(DEFAULT_CONFIG if base is None else base)
    cfg.update(patch)

    known = set(_known_tab_ids())

    # menuTitle
    mt = cfg.get("menuTitle")
    if mt is not None:
        if not isinstance(mt, str):
            raise AppearanceError("menuTitle must be a string or null")
        mt = mt.strip()
        if len(mt) > _MENU_TITLE_MAX:
            raise AppearanceError(f"menuTitle exceeds {_MENU_TITLE_MAX} chars")
        if re.search(r"[\x00-\x1f\x7f]", mt):
            raise AppearanceError("menuTitle contains control characters")
        mt = mt or None
    cfg["menuTitle"] = mt

    # theme
    if cfg.get("theme") not in ALLOWED_THEMES:
        raise AppearanceError(f"theme must be one of {sorted(ALLOWED_THEMES)}")

    # accent
    if cfg.get("accent") not in ACCENT_PALETTE:
        raise AppearanceError("accent must be 'default' or a hex from the fixed palette")

    # hiddenTabs
    hidden = cfg.get("hiddenTabs") or []
    if not isinstance(hidden, list) or not all(isinstance(x, str) for x in hidden):
        raise AppearanceError("hiddenTabs must be a list of tab ids")
    bad = [x for x in hidden if x not in known]
    if bad:
        raise AppearanceError(f"unknown tab id(s) in hiddenTabs: {bad}")
    protected = [x for x in hidden if x in _PROTECTED_TABS]
    if protected:
        raise AppearanceError(f"these tabs cannot be hidden: {protected}")
    cfg["hiddenTabs"] = list(dict.fromkeys(hidden))  # dedupe, keep order

    # tabOrder
    order = cfg.get("tabOrder") or []
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        raise AppearanceError("tabOrder must be a list of tab ids")
    bad = [x for x in order if x not in known]
    if bad:
        raise AppearanceError(f"unknown tab id(s) in tabOrder: {bad}")
    if len(set(order)) != len(order):
        raise AppearanceError("tabOrder has duplicates")
    cfg["tabOrder"] = order

    return cfg


# ── Storage (sidecar JSON, capped history) ───────────────────────────────────

def _load_raw() -> Dict[str, Any]:
    if not APPEARANCE_PATH.exists():
        return {"current": dict(DEFAULT_CONFIG), "history": []}
    try:
        data = json.loads(APPEARANCE_PATH.read_text())
        if not isinstance(data, dict) or "current" not in data:
            return {"current": dict(DEFAULT_CONFIG), "history": []}
        data.setdefault("history", [])
        return data
    except Exception:
        return {"current": dict(DEFAULT_CONFIG), "history": []}


def _save_raw(data: Dict[str, Any]) -> None:
    APPEARANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPEARANCE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(APPEARANCE_PATH)


def get_config() -> Dict[str, Any]:
    """Current appearance config, schema-normalized (so a brand-new brain renders
    exactly as today: default = current look)."""
    with _LOCK:
        cur = _load_raw().get("current", {})
    try:
        return validate(cur)
    except AppearanceError:
        return dict(DEFAULT_CONFIG)


def apply_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Validate `patch` against the current config, snapshot the prior config,
    then persist. Returns the new full config."""
    with _LOCK:
        raw = _load_raw()
        prior = raw.get("current", dict(DEFAULT_CONFIG))
        new_cfg = validate(patch, base=prior)
        history = raw.get("history", [])
        history.append({"ts": int(time.time()), "config": prior})
        raw["history"] = history[-_HISTORY_CAP:]
        raw["current"] = new_cfg
        _save_raw(raw)
        return new_cfg


def revert() -> Dict[str, Any]:
    """Restore the most recent snapshot (strict config restore, not a code undo).
    The reverted-from config is itself snapshotted so revert is repeatable."""
    with _LOCK:
        raw = _load_raw()
        history = raw.get("history", [])
        if not history:
            return raw.get("current", dict(DEFAULT_CONFIG))
        prior = history.pop()["config"]
        cur = raw.get("current", dict(DEFAULT_CONFIG))
        # Record the state we're leaving so the user can step forward again.
        history.append({"ts": int(time.time()), "config": cur})
        raw["history"] = history[-_HISTORY_CAP:]
        raw["current"] = validate(prior)
        _save_raw(raw)
        return raw["current"]


def reset() -> Dict[str, Any]:
    """Reset to the stock default look. Snapshots the prior config first."""
    return apply_config(dict(DEFAULT_CONFIG))


def history() -> List[Dict[str, Any]]:
    with _LOCK:
        return list(_load_raw().get("history", []))[::-1]  # newest first


# ── Apply config to the nav tab list (pure, testable) ────────────────────────

def apply_to_tabs(tabs: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None
                  ) -> List[Dict[str, Any]]:
    """Filter (hiddenTabs, never the protected ones) and reorder (tabOrder, with
    unlisted tabs kept in natural order after the listed ones). Pure function so
    the server-side nav transform is unit-testable."""
    cfg = config or get_config()
    hidden = set(cfg.get("hiddenTabs", [])) - _PROTECTED_TABS
    order = cfg.get("tabOrder", [])

    visible = [t for t in tabs if t.get("id") not in hidden]
    if not order:
        return visible
    rank = {tid: i for i, tid in enumerate(order)}
    # Listed tabs first (in tabOrder), then the rest in their incoming order.
    listed = [t for t in visible if t.get("id") in rank]
    listed.sort(key=lambda t: rank[t["id"]])
    rest = [t for t in visible if t.get("id") not in rank]
    return listed + rest


# ── Natural-language translator (thin: NL -> validated schema diff) ──────────

_NL_PROMPT = (
    "You translate a brain owner's plain-language request into a JSON DIFF for a "
    "fixed appearance-config schema. You may ONLY change these fields:\n"
    "  menuTitle: string (<=40 chars) or null\n"
    "  theme: one of {themes}\n"
    "  accent: 'default' or one of {accents}\n"
    "  hiddenTabs: array of tab ids from {tabs} (you may NOT hide _settings)\n"
    "  tabOrder: array of tab ids from {tabs}\n"
    "Return ONLY a JSON object with the fields to CHANGE (a diff), nothing else. "
    "If the request cannot be expressed as a change to these fields, return {{}}.\n"
    "You never emit code, files, SQL, or shell — only this JSON diff.\n\n"
    "CURRENT CONFIG: {current}\n"
    "TAB LABELS: {labels}\n\n"
    "REQUEST: {instruction}\n"
)


async def nl_to_diff(instruction: str, complete_fn=None, model: Optional[str] = None
                     ) -> Dict[str, Any]:
    """Translate an NL instruction into a PROPOSED, validated schema diff. Does
    NOT apply it — the caller shows the diff and applies on confirm via
    apply_config (same snapshot/revert path). Returns
    {"diff": {...}, "resulting": {...}} on success or {"diff": {}, "error": ...}
    when nothing valid could be expressed. `complete_fn` is injectable for tests.
    """
    import json as _json

    instruction = (instruction or "").strip()
    if not instruction:
        return {"diff": {}, "error": "empty instruction"}
    labels = {t["id"]: t["label"] for t in _builtin_tabs_safe()}
    prompt = (_NL_PROMPT
              .replace("{themes}", str(sorted(ALLOWED_THEMES)))
              .replace("{accents}", str(sorted(ACCENT_PALETTE)))
              .replace("{tabs}", str(_known_tab_ids()))
              .replace("{labels}", _json.dumps(labels))
              .replace("{current}", _json.dumps(get_config()))
              .replace("{instruction}", instruction))
    try:
        if complete_fn is None:
            from api import providers as _providers
            model = model or _providers.default_model()
            raw = await _providers.complete(
                model, [{"role": "user", "content": prompt}], max_tokens=400)
        else:
            raw = await complete_fn(prompt)
    except Exception as e:
        return {"diff": {}, "error": f"translation failed: {type(e).__name__}"}

    try:
        s = (raw or "").strip()
        start, end = s.find("{"), s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"diff": {}, "error": "no JSON object in response"}
        diff = _json.loads(s[start:end + 1])
        if not isinstance(diff, dict) or not diff:
            return {"diff": {}, "error": "request did not map to any config field"}
        # Keep only known fields, then validate the merged result.
        diff = {k: v for k, v in diff.items() if k in ALLOWED_FIELDS}
        if not diff:
            return {"diff": {}, "error": "request did not map to any config field"}
        resulting = validate(diff, base=get_config())
        return {"diff": diff, "resulting": resulting}
    except AppearanceError as e:
        return {"diff": {}, "error": str(e)}
    except Exception:
        return {"diff": {}, "error": "could not parse a valid diff"}


def _builtin_tabs_safe() -> List[Dict[str, Any]]:
    try:
        from api.apps import BUILTIN_TABS
        return BUILTIN_TABS
    except Exception:
        return [{"id": i, "label": i} for i in _known_tab_ids()]


# ── HTTP endpoints ───────────────────────────────────────────────────────────

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/appearance", tags=["appearance"])

    class PatchRequest(BaseModel):
        menuTitle: Optional[str] = None
        theme: Optional[str] = None
        accent: Optional[str] = None
        hiddenTabs: Optional[List[str]] = None
        tabOrder: Optional[List[str]] = None

        def to_patch(self) -> Dict[str, Any]:
            # Only the fields the client actually sent (exclude_unset) so a PUT
            # is a partial patch, not a full overwrite.
            return self.dict(exclude_unset=True)

    class NLRequest(BaseModel):
        instruction: str

    @router.get("")
    def get_appearance():
        """Current appearance config + the known tab registry (ids/labels) so the
        Settings UI can render controls. Public-read within the operator console."""
        return {
            "config": get_config(),
            "tabs": [{"id": t["id"], "label": t["label"]} for t in _builtin_tabs_safe()],
            "themes": sorted(ALLOWED_THEMES),
            "accents": sorted(ACCENT_PALETTE),
            "protected_tabs": sorted(_PROTECTED_TABS),
        }

    @router.put("")
    def put_appearance(req: PatchRequest):
        """Validate + snapshot + apply a partial config patch. 400 on any
        out-of-schema field/value."""
        try:
            return {"config": apply_config(req.to_patch())}
        except AppearanceError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/revert")
    def post_revert():
        """Restore the previous snapshot."""
        return {"config": revert()}

    @router.post("/reset")
    def post_reset():
        """Reset to the stock default look."""
        return {"config": reset()}

    @router.get("/history")
    def get_history():
        """Snapshot history, newest first."""
        return {"history": history()}

    @router.post("/nl")
    async def post_nl(req: NLRequest):
        """Translate an NL request into a PROPOSED validated diff (does not apply
        — the UI confirms, then PUTs)."""
        return await nl_to_diff(req.instruction)

except Exception:  # fastapi/pydantic absent (e.g. pure-logic test env)
    router = None
