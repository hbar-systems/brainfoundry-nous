"""
Brain app installation, registry, and the tab-list endpoint.

A brain app is an installable extension that adds a tab to the brain UI.
Each app is a public git repo with a `brain-app.yaml` manifest at its root,
validated against the brain-app/v1 schema. On install the brain clones the
repo at a pinned commit SHA, validates the manifest as a hard gate, and
registers the app in `brain-apps/installed.json` (the on-disk source of
truth).

Static-bundle and API-router mounting (the runtime side) live in
`api/apps_mount.py` and are wired by `api.main`. This file owns the
manifest, the registry, and the lifecycle endpoints (install / list /
uninstall / enable / disable).

Created: 2026-05-06
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from jsonschema import Draft7Validator
from pydantic import BaseModel, Field

# ---------- paths and constants ----------

BRAIN_APPS_DIR = Path(os.environ.get("BRAIN_APPS_DIR", "/app/brain-apps"))
SCHEMA_PATH = Path(__file__).parent / "schemas" / "brain-app.schema.json"
INSTALLED_JSON = BRAIN_APPS_DIR / "installed.json"

# Built-in nav entries the brain ships with. The UI composes nav from these
# plus installed apps. `builtin: True` is the marker the UI uses to know not
# to render an iframe shell for these — they have native pages.
#
# Keep this list in sync with FALLBACK_NAV in ui/components/Nav.js. The
# Nav fetches /apps/list at runtime; FALLBACK_NAV renders before the fetch
# resolves and on fetch failure. Drift between the two = visible flicker.
BUILTIN_TABS: list[dict[str, Any]] = [
    {"id": "_dashboard",    "label": "Dashboard",    "route": "/",             "order": 10, "builtin": True},
    {"id": "_chat",         "label": "Chat",         "route": "/chat",         "order": 20, "builtin": True},
    {"id": "_knowledge",    "label": "Knowledge",    "route": "/upload",       "order": 30, "builtin": True},
    {"id": "_federation",   "label": "Federation",   "route": "/federation",   "order": 40, "builtin": True},
    {"id": "_trace",        "label": "Trace",        "route": "/trace",        "order": 50, "builtin": True},
    {"id": "_settings",     "label": "Settings",     "route": "/settings",     "order": 60, "builtin": True},
    {"id": "_update",       "label": "Update",       "route": "/update",       "order": 70, "builtin": True},
    {"id": "_future",       "label": "Future",       "route": "/future",       "order": 80, "builtin": True},
]

# Routes that built-ins or the API itself occupy. Installed apps cannot use
# any of these for their tab.route.
RESERVED_ROUTES: set[str] = {t["route"] for t in BUILTIN_TABS} | {"/apps", "/api"}


# ---------- pydantic models ----------

class InstallRequest(BaseModel):
    repo_url: str = Field(..., description="Public git URL of the app to install.")
    ref: str = Field("HEAD", description="Branch, tag, or commit SHA. Defaults to HEAD.")


class PreviewResponse(BaseModel):
    manifest: dict
    commit_sha: str


class InstallResponse(BaseModel):
    id: str
    manifest: dict
    commit_sha: str
    app_token: str = Field(
        ...,
        description=(
            "One-time-returned bearer the host UI uses to make permission-checked "
            "bridge calls on behalf of this app. Only the sha256 hash is stored "
            "server-side; the raw value is never returned again."
        ),
    )


# ---------- helpers ----------

def _load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        return json.load(f)


def _load_installed() -> dict:
    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    if not INSTALLED_JSON.exists():
        empty = {"dialect": "brain-apps-installed/v1", "apps": []}
        INSTALLED_JSON.write_text(json.dumps(empty, indent=2) + "\n")
        return empty
    return json.loads(INSTALLED_JSON.read_text())


def _save_installed(data: dict) -> None:
    INSTALLED_JSON.write_text(json.dumps(data, indent=2) + "\n")


def _validate_manifest(manifest: dict) -> None:
    """Raises HTTPException(422) with structured errors if manifest fails the schema."""
    schema = _load_schema()
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "manifest_invalid",
                "issues": [
                    {"path": [str(p) for p in e.absolute_path], "message": e.message}
                    for e in errors
                ],
            },
        )


def _git_clone(repo_url: str, ref: str, dest: Path) -> str:
    """Clone repo_url at ref into dest. Returns the resolved commit SHA.

    Uses --depth 1 so install is fast and disk-cheap. ref may be a branch,
    tag, or commit SHA; "HEAD" means the default branch.
    """
    if dest.exists():
        raise HTTPException(status_code=409, detail={"error": "destination_exists", "path": str(dest)})
    cmd = ["git", "clone", "--depth", "1"]
    if ref and ref != "HEAD":
        cmd += ["--branch", ref]
    cmd += [repo_url, str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(status_code=504, detail={"error": "git_clone_timeout"})
    except subprocess.CalledProcessError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail={"error": "git_clone_failed", "stderr": e.stderr[:500] if e.stderr else ""},
        )
    sha_proc = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return sha_proc.stdout.strip()


def _read_manifest(app_dir: Path) -> dict:
    manifest_path = app_dir / "brain-app.yaml"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=400,
            detail={"error": "manifest_missing", "expected_at": "brain-app.yaml"},
        )
    try:
        loaded = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail={"error": "manifest_yaml_error", "message": str(e)[:500]})
    if not isinstance(loaded, dict):
        raise HTTPException(status_code=400, detail={"error": "manifest_not_object"})
    return loaded


def _check_route_collision(route: str, existing: list[dict]) -> None:
    if route in RESERVED_ROUTES:
        raise HTTPException(
            status_code=409,
            detail={"error": "route_reserved", "route": route},
        )
    for app in existing:
        if app.get("tab", {}).get("route") == route:
            raise HTTPException(
                status_code=409,
                detail={"error": "route_taken", "route": route, "by": app["id"]},
            )


def _check_id_collision(app_id: str, existing: list[dict]) -> None:
    for app in existing:
        if app["id"] == app_id:
            raise HTTPException(status_code=409, detail={"error": "id_taken", "id": app_id})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------- router ----------

router = APIRouter(prefix="/apps", tags=["apps"])


@router.post("/install/preview", response_model=PreviewResponse)
def install_preview(req: InstallRequest) -> PreviewResponse:
    """Clone to a temp dir, parse and validate the manifest, return it. No state written."""
    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = BRAIN_APPS_DIR / f".preview-{secrets.token_hex(8)}"
    try:
        sha = _git_clone(req.repo_url, req.ref, tmp_dir)
        manifest = _read_manifest(tmp_dir)
        _validate_manifest(manifest)
        return PreviewResponse(manifest=manifest, commit_sha=sha)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/install", response_model=InstallResponse)
def install_app(req: InstallRequest, request: Request) -> InstallResponse:
    """Install an app: validate, clone permanently, register in installed.json, mount live."""
    state = _load_installed()
    existing = state.get("apps", [])

    # First: a preview-style clone-validate-discard, so we don't half-install.
    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    staging = BRAIN_APPS_DIR / f".staging-{secrets.token_hex(8)}"
    try:
        commit_sha = _git_clone(req.repo_url, req.ref, staging)
        manifest = _read_manifest(staging)
        _validate_manifest(manifest)

        app_id = manifest["id"]
        _check_id_collision(app_id, existing)
        _check_route_collision(manifest["tab"]["route"], existing)

        final_dir = BRAIN_APPS_DIR / app_id
        if final_dir.exists():
            raise HTTPException(
                status_code=409,
                detail={"error": "app_dir_exists", "path": str(final_dir)},
            )
        staging.rename(final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    raw_token = secrets.token_urlsafe(32)
    entry = {
        "id": app_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "license": manifest["license"],
        "repo": manifest["repo"],
        "commit_sha": commit_sha,
        "installed_at": _now_iso(),
        "enabled": True,
        "tab": manifest["tab"],
        "entries": manifest.get("entries", {}),
        "permissions": manifest.get("permissions", []),
        "requires_layers": manifest.get("requires_layers", []),
        "requires_endpoints": manifest.get("requires_endpoints", []),
        "token_hash": _hash_token(raw_token),
    }
    existing.append(entry)
    state["apps"] = existing
    _save_installed(state)

    # Hot-mount the app on the live process so the next request hits the new
    # routes without a restart. Failures are logged but don't fail the install
    # — installed.json is the source of truth and a restart will pick it up.
    try:
        from api.apps_mount import mount_app as _mount_app
        _mount_app(request.app, entry)
    except Exception as e:
        print(f"[brain-apps] hot-mount failed for {app_id}: {e}", flush=True)

    return InstallResponse(
        id=app_id,
        manifest=manifest,
        commit_sha=commit_sha,
        app_token=raw_token,
    )


@router.get("/list")
def list_apps() -> dict:
    """Return tab registry: built-ins + installed apps. Used by the UI nav."""
    state = _load_installed()
    apps = state.get("apps", [])
    installed_tabs = [
        {
            "id": a["id"],
            "label": a["tab"]["label"],
            "route": a["tab"]["route"],
            "order": a["tab"].get("order", 100),
            "builtin": False,
            "enabled": a.get("enabled", True),
            "version": a["version"],
            "description": a["description"],
        }
        for a in apps
    ]
    tabs = BUILTIN_TABS + installed_tabs
    tabs.sort(key=lambda t: (t.get("order", 100), t["label"]))
    return {"tabs": tabs, "apps": apps}


@router.post("/{app_id}/uninstall")
def uninstall_app(app_id: str, request: Request) -> dict:
    state = _load_installed()
    apps = state.get("apps", [])
    target = next((a for a in apps if a["id"] == app_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail={"error": "app_not_found", "id": app_id})
    state["apps"] = [a for a in apps if a["id"] != app_id]
    _save_installed(state)
    app_dir = BRAIN_APPS_DIR / app_id
    if app_dir.exists():
        shutil.rmtree(app_dir, ignore_errors=True)
    try:
        from api.apps_mount import unmount_app as _unmount_app
        _unmount_app(request.app, app_id)
    except Exception as e:
        print(f"[brain-apps] hot-unmount failed for {app_id}: {e}", flush=True)
    return {"id": app_id, "uninstalled": True}


@router.post("/{app_id}/enable")
def enable_app(app_id: str) -> dict:
    return _set_enabled(app_id, True)


@router.post("/{app_id}/disable")
def disable_app(app_id: str) -> dict:
    return _set_enabled(app_id, False)


def _set_enabled(app_id: str, enabled: bool) -> dict:
    state = _load_installed()
    apps = state.get("apps", [])
    target = next((a for a in apps if a["id"] == app_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail={"error": "app_not_found", "id": app_id})
    target["enabled"] = enabled
    _save_installed(state)
    return {"id": app_id, "enabled": enabled}
