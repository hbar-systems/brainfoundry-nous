"""cc_catalog: the personalization dictionary. Created 2026-10-29. Spec: docs/PERSONALIZATION.md.

Imported by cc_layout.py and the tests. Standard library only.

The catalog is the one list of personalizable things a console has (tabs, panes, views, panels,
doors, brain-apps, looks, voice, channels, seats, access). Each item has an id, a kind, what it does,
its default, who may see it, and the evidence that hbar has used it.

Rule (hbar, 2026-10-29): an item is "standard" only after hbar has used it (spike-to-system, about five
days of lived use), with the evidence named. Everything else the console has is a "candidate": it is
listed so the inventory is complete, but no arrangement may pick it until it is promoted with evidence.

An arrangement is per brain: which standard items, in which order, plus a preset name. It lives in the
owner's layout.json beside "mode" (cc_layout.Store.arrangement), never in a shared layout pack. Presets
are files in scripts/cc/presets/<id>.json: interview answers, a console mode, an access, and items.
Closed lists only: ids, never CSS, URLs or free text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KINDS = ("access", "tab", "pane", "view", "panel", "door", "app", "look", "voice", "channel", "seat")
AUDIENCES = ("owner", "member", "public")
STATUSES = ("standard", "candidate")
ACCESS = ("access:console", "access:telegram", "access:public-chat")
ITEMS_MAX = 80
PRESETS_DIR = Path(__file__).resolve().parent / "presets"
_ID = re.compile(r"^[a-z]+:[a-z0-9_/-]{1,64}$")

UNKNOWN = "unknown"


def _i(id, what, default, who, evidence, status="standard"):
    return {"id": id, "kind": id.split(":", 1)[0], "what": what, "default": default, "who": who,
            "evidence": evidence, "status": status if evidence != UNKNOWN else "candidate"}


O, M, P = ("owner",), ("owner", "member"), ("owner", "member", "public")

# Evidence is a path in hbar.world (ops/, mind/claude/) or a nous commit; UNKNOWN makes the item a candidate.
CATALOG = (
    # access: how the person reaches the brain at all
    _i("access:console", "the full console in a browser", "on", M, "mind/claude/project_claude_code_in_brain.md (live 2026-09-20)"),
    _i("access:telegram", "the Telegram door: text, voice notes and files into the brain", "off", M,
       "ops/2026-10-12_production-procedures.md (intake: Telegram, 20 MB cap)"),
    _i("access:public-chat", "a public chat page, no login, labelled answers", "off", P,
       "nous 3c6b6de (public chat footer, yury-ai kit); hbar.science rulings 2026-10-29"),
    # tabs: the console's nav (api/apps.py BUILTIN_TABS)
    _i("tab:_cc", "the conversation with the hands (CC)", "on", M, "mind/claude/project_claude_code_in_brain.md"),
    _i("tab:_chat", "plain chat with the brain's reasoner", "on", M, "mind/claude/project_brain_model_resolution.md"),
    _i("tab:_knowledge", "upload and search the brain's documents", "on", M, "mind/claude/project_mirror_corpus_ingest.md"),
    _i("tab:_files", "the box's files: out, in, work, world, brain", "on", M, "ops/2026-09-13_todo-plan.md (Files pane, session 2)"),
    _i("tab:_apps", "the brain-app shelf", "on", M, "mind/claude/project_brainapp_iframe_sandbox.md"),
    _i("tab:_settings", "settings: keys, model, look", "on", M, "mind/claude/project_brain_model_resolution.md (UI pick)"),
    _i("tab:_system", "the box: services, jobs, disk", "on", O, "mind/claude/project_claude_code_in_brain.md (System tab)"),
    _i("tab:_update", "pull the template and rebuild", "on", O, "mind/claude/reference_brain_deploy.md (Update tab)"),
    _i("tab:_persona", "the persona and charter files", "on", O, "mind/claude/project_brain_md_governance.md"),
    _i("tab:_federation", "peers and doors between brains", "on", O, "ops/sessions/2026-05-01_federation-dm-live.md"),
    _i("tab:_dashboard", "the overview page", "on", O, UNKNOWN),
    _i("tab:_tasks", "tasks", "on", M, UNKNOWN),
    _i("tab:_research", "research runs", "on", M, UNKNOWN),
    _i("tab:_integrations", "email, calendar, Telegram, MCP set-up", "on", O, UNKNOWN),
    _i("tab:_economy", "the economy page", "on", O, UNKNOWN),
    _i("tab:_trace", "the trace of tool calls", "on", O, UNKNOWN),
    _i("tab:_future", "the future page", "on", O, UNKNOWN),
    _i("tab:_graph", "the memory graph", "on", M, UNKNOWN),
    _i("tab:_guide", "the guide", "on", M, UNKNOWN),
    _i("tab:_terminal", "a terminal on the box", "on", O, UNKNOWN),
    # panes: screens the brain opens beside the conversation that are not nav tabs
    _i("pane:/board", "the board of running jobs and agents", "on", O, "mind/claude/feedback_fan_out_and_board.md (watch /board)"),
    _i("pane:/agents", "agent cards by tag", "on", O, "mind/claude/feedback_agent_tags_clickable.md"),
    _i("pane:/permits", "permit history, who decided", "on", O, UNKNOWN),
    _i("pane:/boxes", "the 2D body map of the boxes", "on", O, UNKNOWN),
    _i("pane:/profile", "how the brain talks (profile interview)", "on", M, UNKNOWN),
    _i("pane:/layout", "the layout chips and proposals", "on", M, UNKNOWN),
    # views: what the console opens on (layout "view")
    _i("view:talk", "the conversation", "on", M, "mind/claude/project_claude_code_in_brain.md"),
    _i("view:panes", "several conversations side by side", "off", M, "ops/2026-10-06_console-reading-space/README.md"),
    _i("view:gallery", "conversations as a deck", "off", M, UNKNOWN),   # idea register 10-12: live, mostly unseen
    # panels: blocks of the console page (layout "panels")
    _i("panel:handsfree", "the hands-free row", "on", M, "ops/2026-09-28_where-we-are.md (hands-free)"),
    _i("panel:files", "the files link", "on", M, "mind/claude/feedback_desk_files_group_readable.md"),
    _i("panel:board", "the board link", "on", O, "mind/claude/feedback_fan_out_and_board.md"),
    _i("panel:sidebyside", "the side by side button", "on", M, "ops/2026-10-06_console-reading-space/README.md"),
    _i("panel:hero", "the title block", "on", M, UNKNOWN),
    _i("panel:hint", "the starter hints", "on", M, UNKNOWN),
    _i("panel:gallery", "the gallery link", "on", M, UNKNOWN),
    # doors: things in an answer the person presses
    _i("door:choices", "choice buttons, each with a probability", "on", M, "nous c6dafd1; mind/claude/feedback_probability_recommendations.md"),
    _i("door:highlight", "a highlighted phrase opens its card", "on", M, "nous 0cd0d92; mind/claude/feedback_agent_tags_clickable.md"),
    _i("door:permit-card", "approve or refuse an action before it runs", "on", M, "mind/claude/feedback_human_approve_destructive_infra.md"),
    _i("door:job-tile", "a job or agent tile in the thread that started it", "on", M, "mind/claude/feedback_tiles_stay_in_thread.md"),
    _i("door:desk-link", "an exact link to a file on the desk", "on", M, "mind/claude/feedback_link_is_right_there.md"),
    # brain-apps (installed.json on hbar); installed is not used
    _i("app:poker-journal", "poker trainer", "off", M, UNKNOWN),
    _i("app:hbar-ink", "thought-drop instrument", "off", M, UNKNOWN),
    _i("app:mirror", "self-knowledge notes", "off", M, UNKNOWN),
    _i("app:daybook", "day log", "off", M, UNKNOWN),
    _i("app:today", "today", "off", M, UNKNOWN),
    _i("app:people", "people", "off", M, UNKNOWN),
    _i("app:weekly-review", "weekly review", "off", M, UNKNOWN),
    _i("app:toolbox", "small utilities", "off", M, UNKNOWN),
    _i("app:clip", "clip", "off", M, UNKNOWN),
    _i("app:thread-consolidator", "thread consolidator", "off", M, UNKNOWN),
    _i("app:quantum-room", "quantum room", "off", M, UNKNOWN),
    _i("app:cell-architecture-studio", "cell architecture studio", "off", M, UNKNOWN),
    _i("app:oracle", "oracle", "off", M, UNKNOWN),
    _i("app:science-experiment", "science experiment", "off", M, UNKNOWN),
    _i("app:hbar-health-letter-ingestion", "health letter ingestion", "off", M, UNKNOWN),
    # looks (layout theme); fonts, size, weight, width stay layout values, not items
    _i("look:default", "the stock warm dark palette", "on", M, "ui/pages/_app.js (stock)"),
    _i("look:black", "black palette", "off", M, UNKNOWN),
    _i("look:light", "light palette", "off", M, UNKNOWN),
    # voice
    _i("voice:speak", "answers read aloud (streamed, speed 1.2)", "off", M, "ops/2026-09-28_where-we-are.md"),
    _i("voice:handsfree", "talk without pressing", "off", M, "ops/2026-09-28_where-we-are.md"),
    # channels: other ways in, beside access
    _i("channel:phone-upload", "photos and files from the phone", "off", O, "mind/claude/project_photo_memory_pipeline.md"),
    # seats: which hands answer in the console
    _i("seat:claude-code", "Claude Code as the hands", "on", O, "mind/claude/project_claude_code_in_brain.md"),
    _i("seat:codex", "Codex as the hands", "off", O, "hbar.world ad0fa6a, 58baec7 (Codex hands, rulings 2026-10-29)"),
    _i("seat:local", "a local model, read-only", "off", O, "ops/2026-10-25_evening-handoff.md (local seat)"),
)
BY_ID = {it["id"]: it for it in CATALOG}
STANDARD = tuple(it["id"] for it in CATALOG if it["status"] == "standard")


class CatalogError(ValueError):
    """An arrangement or preset that does not satisfy the catalog."""


def validate_catalog() -> None:
    """The catalog's own invariants; the tests call it."""
    seen = set()
    for it in CATALOG:
        if not _ID.match(it["id"]) or it["id"] in seen:
            raise CatalogError(f"bad or repeated id {it['id']!r}")
        seen.add(it["id"])
        if it["kind"] not in KINDS or it["status"] not in STATUSES or not set(it["who"]) <= set(AUDIENCES):
            raise CatalogError(f"{it['id']}: kind, status or who outside the closed lists")
        if it["status"] == "standard" and it["evidence"] == UNKNOWN:
            raise CatalogError(f"{it['id']}: standard without evidence")


def validate_items(items, audience: str = "owner") -> list:
    """An ordered list of standard catalog ids that this audience may see, with at least one access."""
    if not isinstance(items, list) or len(items) > ITEMS_MAX:
        raise CatalogError(f"items must be a list of at most {ITEMS_MAX} ids")
    if audience not in AUDIENCES:
        raise CatalogError(f"audience must be one of {', '.join(AUDIENCES)}")
    out = []
    for x in items:
        if not isinstance(x, str) or x not in BY_ID:
            raise CatalogError(f"{x!r} is not in the catalog")
        if BY_ID[x]["status"] != "standard":
            raise CatalogError(f"{x} is a candidate: it enters an arrangement only after hbar has used it")
        if audience not in BY_ID[x]["who"]:
            raise CatalogError(f"{x} is not for a {audience}")
        if x in out:
            raise CatalogError(f"{x} is listed twice")
        out.append(x)
    if not any(x in ACCESS for x in out):
        raise CatalogError("an arrangement needs at least one access item")
    return out


def counts() -> dict:
    out = {}
    for it in CATALOG:
        k = out.setdefault(it["kind"], {"standard": 0, "candidate": 0})
        k[it["status"]] += 1
    return out


# ---- presets: files in presets/, read as data ----

def preset_ids() -> tuple:
    return tuple(sorted(p.stem for p in PRESETS_DIR.glob("*.json")))


def load_preset(name: str) -> dict:
    """The preset file, checked: answers by cc_layout.validate_answers, items by validate_items."""
    import cc_layout as L   # here, not at the top: cc_layout imports this module
    if name not in preset_ids():
        raise CatalogError(f"preset must be one of {', '.join(preset_ids())}")
    p = json.loads((PRESETS_DIR / f"{name}.json").read_text())
    allowed = {"id", "name", "audience", "mode", "answers", "items", "evidence"}
    if not isinstance(p, dict) or set(p) - allowed or p.get("id") != name:
        raise CatalogError(f"preset {name}: keys must be {sorted(allowed)} and id must match the file")
    if p.get("mode") not in L.MODES:
        raise CatalogError(f"preset {name}: mode must be one of {', '.join(L.MODES)}")
    p["answers"] = L.validate_answers(p.get("answers") or {})
    p["items"] = validate_items(p.get("items") or [], p.get("audience", "owner"))
    return p


def validate_arrangement(obj) -> dict:
    """{"preset": <id or null>, "items": [...]}: what a brain stores in layout.json."""
    if not isinstance(obj, dict) or set(obj) - {"preset", "items"}:
        raise CatalogError("arrangement keys are preset and items")
    pre = obj.get("preset")
    if pre is not None and pre not in preset_ids():
        raise CatalogError(f"preset must be one of {', '.join(preset_ids())}")
    aud = load_preset(pre).get("audience", "owner") if pre else "owner"
    return {"preset": pre, "items": validate_items(obj.get("items") or [], aud)}


def layout_to_answers(layout: dict) -> dict:
    """The interview answers that reproduce a layout's answerable parts (to measure the owner preset
    from a live layout.json). Fonts outside the three faces and colour vars are not answerable; dropped."""
    import cc_layout as L
    lay = L.validate(layout)
    face = {v: k for k, v in L._FACE.items()}
    a = {"first": lay["view"], "side": lay["pane"]["side"], "tone": lay["theme"], "weight": lay["weight"],
         "size": lay["size"], "width": lay["column"],
         "never": sorted(k for k in L.PANELS if not lay["panels"][k] and k != "sidebyside"),
         "panes": "one" if not lay["panels"]["sidebyside"] else "several",
         "voice": "handsfree" if lay["voice"]["handsfree"] else ("speak" if lay["voice"]["speak"] else "off")}
    if lay["font"] in face:
        a["face"] = face[lay["font"]]
    return L.validate_answers(a)


if __name__ == "__main__":
    # python3 scripts/cc/cc_catalog.py counts | measure [state_dir]
    #   measure: print the answers that reproduce this box's current layout (for presets/owner.json).
    cmd = sys.argv[1] if len(sys.argv) > 1 else "counts"
    if cmd == "measure":
        import cc_layout as L
        st = L.Store(Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / ".cc-bridge")
        cur = st.get()
        print(json.dumps({"answers": layout_to_answers(cur) if cur else {}, "stock": cur is None,
                          "mode": st._read().get("mode"), "interview": st.answers()}, indent=1))
    else:
        print(json.dumps(counts(), indent=1))
