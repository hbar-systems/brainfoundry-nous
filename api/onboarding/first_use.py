"""
api/onboarding/first_use.py — the first-use flow state (unreleased 0.10.0).

The three things a new owner does in the first hour, as one server-driven
checklist the console renders on the dashboard:
  1. add a model key (Settings, Keys)   — or accept the slow local model
  2. drop ten files (Knowledge)          — the starter corpus
  3. open one app (Apps)                 — the first pre-installed brain-app

Pure logic, no framework, no key: build_state() takes the facts and returns
the checklist; api.main's GET /onboarding/first-use gathers the facts. The
dashboard opens the first app on the very first login (client-side flag) when
the brain is fresh, which is what "one app opens on first login" means.

Created 2026-09-13.
"""
from __future__ import annotations

from typing import Iterable, Optional

TARGET_FILES = 10

# The starter prompt shown on the Knowledge tab until ten documents exist.
STARTER_PROMPT = (
    "Drop ten files. Anything in your own words works best: notes, a CV, "
    "emails you wrote, a project readme, a decision you made and why, "
    "a list of what you are working on. The brain answers from what you give it."
)

# Where a key comes from, per provider. Shown in Settings, Keys.
KEY_GUIDE = [
    {"provider": "anthropic", "label": "Anthropic (Claude)",
     "url": "https://console.anthropic.com/settings/keys", "pick": "claude-sonnet-5"},
    {"provider": "openai", "label": "OpenAI",
     "url": "https://platform.openai.com/api-keys", "pick": "gpt-4o"},
    {"provider": "gemini", "label": "Google Gemini",
     "url": "https://aistudio.google.com/app/apikey", "pick": "gemini-2.0-flash"},
    {"provider": "groq", "label": "Groq (fast, cheap)",
     "url": "https://console.groq.com/keys", "pick": "groq/llama-3.3-70b-versatile"},
]


def pick_first_app(installed: Iterable[dict], preferred: Iterable[str] = ("daybook", "hbar-ink", "oracle")) -> Optional[dict]:
    """The app the console opens first: a preferred id when present, else the
    first enabled app in install order. None when nothing is installed."""
    apps = [a for a in installed if a.get("enabled", True) and a.get("id")]
    by_id = {a["id"]: a for a in apps}
    for pid in preferred:
        if pid in by_id:
            return _app_view(by_id[pid])
    return _app_view(apps[0]) if apps else None


def _app_view(a: dict) -> dict:
    return {"id": a["id"], "name": a.get("name") or a["id"], "route": f"/apps/{a['id']}",
            "description": a.get("description", "")}


def build_state(*, has_key: bool, doc_count: int, chunk_count: int, session_count: int,
                installed: Iterable[dict], target_files: int = TARGET_FILES) -> dict:
    installed = list(installed)
    first_app = pick_first_app(installed)
    files_done = doc_count >= target_files
    fresh = doc_count == 0 and session_count == 0
    steps = [
        {"key": "key", "done": has_key, "label": "Add a model key",
         "sub": ("Paste an Anthropic, OpenAI, Gemini or Groq key in Settings. Without one the local "
                 "model answers, slowly."), "href": "/settings", "cta": "Settings"},
        {"key": "files", "done": files_done, "label": f"Drop ten files ({min(doc_count, target_files)} of {target_files})",
         "sub": STARTER_PROMPT, "href": "/upload", "cta": "Knowledge",
         "progress": {"done": doc_count, "target": target_files, "chunks": chunk_count}},
        {"key": "app", "done": session_count > 0 or first_app is None, "label":
            (f"Open {first_app['name']}" if first_app else "Install an app"),
         "sub": (first_app["description"] or "Your first brain-app is pre-installed; open it once.") if first_app
                else "No app is installed yet; install one from the Apps page.",
         "href": first_app["route"] if first_app else "/apps", "cta": "Open"},
    ]
    return {
        "steps": steps,
        "complete": all(s["done"] for s in steps),
        "fresh": fresh,
        "first_app": first_app,
        "installed_apps": len(installed),
        "target_files": target_files,
        "starter_prompt": STARTER_PROMPT,
        "key_guide": KEY_GUIDE,
    }
