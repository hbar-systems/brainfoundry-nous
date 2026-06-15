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

# Built-in nav entries the brain ships with. The UI Nav renders ONLY these —
# installed apps live behind the single `_apps` hub at /apps, which lists
# them as cards. This keeps the nav clean as the install count grows.
#
# Keep this list in sync with FALLBACK_NAV in ui/components/Nav.js. The Nav
# fetches /apps/list at runtime; FALLBACK_NAV renders before the fetch
# resolves and on fetch failure. Drift = visible flicker.
BUILTIN_TABS: list[dict[str, Any]] = [
    {"id": "_dashboard",    "label": "Dashboard",    "route": "/",             "order": 10, "builtin": True},
    {"id": "_chat",         "label": "Chat",         "route": "/chat",         "order": 20, "builtin": True},
    {"id": "_persona",      "label": "Persona",      "route": "/persona",      "order": 25, "builtin": True},
    {"id": "_knowledge",    "label": "Knowledge",    "route": "/upload",       "order": 30, "builtin": True},
    {"id": "_apps",         "label": "Apps",         "route": "/apps",         "order": 35, "builtin": True},
    {"id": "_federation",   "label": "Federation",   "route": "/federation",   "order": 40, "builtin": True},
    {"id": "_economy",      "label": "Economy",      "route": "/economy",      "order": 45, "builtin": True},
    {"id": "_trace",        "label": "Trace",        "route": "/trace",        "order": 50, "builtin": True},
    {"id": "_settings",     "label": "Settings",     "route": "/settings",     "order": 60, "builtin": True},
    {"id": "_update",       "label": "Update",       "route": "/update",       "order": 70, "builtin": True},
    {"id": "_future",       "label": "Future",       "route": "/future",       "order": 80, "builtin": True},
]

# Routes that built-ins or the API itself occupy. Installed apps cannot use
# any of these for their tab.route.
RESERVED_ROUTES: set[str] = {t["route"] for t in BUILTIN_TABS} | {"/api"}


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


class UpdateRequest(BaseModel):
    accept_scope_change: bool = Field(
        False,
        description=(
            "Must be true to apply an update whose manifest changes the app's "
            "permissions or required memory layers. A pure code/version bump "
            "with unchanged scope updates without it."
        ),
    )


class UpdatePreviewResponse(BaseModel):
    id: str
    manifest: dict
    commit_sha: str          # HEAD of the repo right now
    current_sha: str         # the SHA the installed app is pinned to
    up_to_date: bool
    scope_changed: bool
    scope_diff: dict


class UpdateResponse(BaseModel):
    id: str
    manifest: dict
    commit_sha: str
    previous_sha: str
    scope_changed: bool


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


def _layer_key(layer: dict) -> str:
    return f"{layer.get('layer')}:{layer.get('mode')}"


def _scope_diff(installed: dict, manifest: dict) -> dict:
    """What the new manifest changes in the app's access scope vs the installed entry.

    Permissions and required memory layers are the security-relevant surface:
    a change here means the operator must re-approve before the update lands.
    """
    old_perms = set(installed.get("permissions") or [])
    new_perms = set(manifest.get("permissions") or [])
    old_layers = {_layer_key(l) for l in (installed.get("requires_layers") or [])}
    new_layers = {_layer_key(l) for l in (manifest.get("requires_layers") or [])}
    return {
        "added_permissions": sorted(new_perms - old_perms),
        "removed_permissions": sorted(old_perms - new_perms),
        "added_layers": sorted(new_layers - old_layers),
        "removed_layers": sorted(old_layers - new_layers),
    }


def _scope_changed(diff: dict) -> bool:
    return any(diff[k] for k in diff)


def _chown_to_host_owner(path: Path) -> None:
    """Re-own a tree to the bind-mount host owner.

    The api container runs as root, so files written by `git clone` here land
    root-owned on the host filesystem the operator sees. The operator then can
    not `rm` a stale dir without sudo, and a stale dir blocks reinstall with
    `app_dir_exists`. We re-own to either an explicit BRAIN_USER_UID/GID (env)
    or to whoever owns BRAIN_APPS_DIR itself (default — the bind-mount root,
    which on a normal brain is the host operator).

    Best-effort: failures log but never raise. A missed chown is an
    inconvenience, not a reason to fail an install.
    """
    try:
        uid_env = os.environ.get("BRAIN_USER_UID")
        gid_env = os.environ.get("BRAIN_USER_GID")
        if uid_env and gid_env:
            uid, gid = int(uid_env), int(gid_env)
        else:
            st = BRAIN_APPS_DIR.stat()
            uid, gid = st.st_uid, st.st_gid
        if not path.exists():
            return
        if path.is_symlink() or path.is_file():
            os.chown(path, uid, gid, follow_symlinks=False)
            return
        for root, dirs, files in os.walk(path, followlinks=False):
            try:
                os.chown(root, uid, gid)
            except OSError:
                pass
            for name in list(dirs) + list(files):
                try:
                    os.chown(os.path.join(root, name), uid, gid, follow_symlinks=False)
                except OSError:
                    pass
    except Exception as e:
        print(f"[brain-apps] chown skipped for {path}: {e}", flush=True)


def _chown_existing_app_dirs() -> None:
    """One-shot startup migration: re-own already-installed app dirs to the host.

    Catches the legacy state where prior installs left root-owned dirs on the
    bind mount. Iterates per-app subdirectories only; ignores dotfiles and the
    top-level template files (installed.json, README.md, .gitignore).
    """
    if not BRAIN_APPS_DIR.exists():
        return
    for child in BRAIN_APPS_DIR.iterdir():
        if child.name.startswith(".") or not child.is_dir():
            continue
        _chown_to_host_owner(child)


# ---------- router ----------

router = APIRouter(prefix="/apps", tags=["apps"])


@router.post("/install/preview", response_model=PreviewResponse)
def install_preview(req: InstallRequest) -> PreviewResponse:
    """Clone to a temp dir, parse and validate the manifest, return it. No state written."""
    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = BRAIN_APPS_DIR / f".preview-{secrets.token_hex(8)}"
    try:
        sha = _git_clone(req.repo_url, req.ref, tmp_dir)
        _chown_to_host_owner(tmp_dir)
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
        _chown_to_host_owner(staging)
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
    """Return the tab registry plus the installed-apps registry.

    `tabs` are the top-nav entries — built-ins only. The Nav renders these.
    `apps` is the installed apps list — surfaced by /apps (the hub page)
    which renders them as cards. Each enabled app is reachable at /apps/<id>
    via the dynamic-route iframe host shell.
    """
    state = _load_installed()
    apps = state.get("apps", [])
    tabs = sorted(BUILTIN_TABS, key=lambda t: (t.get("order", 100), t["label"]))
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


@router.post("/{app_id}/update/preview", response_model=UpdatePreviewResponse)
def update_preview(app_id: str) -> UpdatePreviewResponse:
    """Clone the app's repo at HEAD, validate, and report what an update would do.

    No state is written. The caller uses `up_to_date` / `scope_changed` to decide
    between a silent one-click update and a re-approval prompt.
    """
    state = _load_installed()
    entry = next((a for a in state.get("apps", []) if a["id"] == app_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail={"error": "app_not_found", "id": app_id})
    repo_url = entry.get("repo")
    if not repo_url:
        raise HTTPException(status_code=400, detail={"error": "app_has_no_repo", "id": app_id})

    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = BRAIN_APPS_DIR / f".update-preview-{secrets.token_hex(8)}"
    try:
        sha = _git_clone(repo_url, "HEAD", tmp_dir)
        _chown_to_host_owner(tmp_dir)
        manifest = _read_manifest(tmp_dir)
        _validate_manifest(manifest)
        if manifest.get("id") != app_id:
            raise HTTPException(
                status_code=409,
                detail={"error": "manifest_id_changed", "installed": app_id, "repo": manifest.get("id")},
            )
        diff = _scope_diff(entry, manifest)
        return UpdatePreviewResponse(
            id=app_id,
            manifest=manifest,
            commit_sha=sha,
            current_sha=entry.get("commit_sha", ""),
            up_to_date=(sha == entry.get("commit_sha")),
            scope_changed=_scope_changed(diff),
            scope_diff=diff,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/{app_id}/update", response_model=UpdateResponse)
def update_app(app_id: str, req: UpdateRequest, request: Request) -> UpdateResponse:
    """Re-fetch the app at repo HEAD, re-pin the SHA, swap the served bundle.

    A convenience wrapper over the install pipeline — no uninstall/reinstall,
    so the app token and install date survive. If the new manifest changes
    permissions or memory layers, this refuses unless `accept_scope_change`
    is set, so an update can never silently widen what an app can touch.
    """
    state = _load_installed()
    apps = state.get("apps", [])
    idx = next((i for i, a in enumerate(apps) if a["id"] == app_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail={"error": "app_not_found", "id": app_id})
    entry = apps[idx]
    repo_url = entry.get("repo")
    if not repo_url:
        raise HTTPException(status_code=400, detail={"error": "app_has_no_repo", "id": app_id})
    previous_sha = entry.get("commit_sha", "")

    BRAIN_APPS_DIR.mkdir(parents=True, exist_ok=True)
    staging = BRAIN_APPS_DIR / f".update-staging-{secrets.token_hex(8)}"
    try:
        commit_sha = _git_clone(repo_url, "HEAD", staging)
        _chown_to_host_owner(staging)
        manifest = _read_manifest(staging)
        _validate_manifest(manifest)
        if manifest.get("id") != app_id:
            raise HTTPException(
                status_code=409,
                detail={"error": "manifest_id_changed", "installed": app_id, "repo": manifest.get("id")},
            )
        # The route may have moved; check it against the OTHER installed apps.
        others = [a for a in apps if a["id"] != app_id]
        _check_route_collision(manifest["tab"]["route"], others)

        diff = _scope_diff(entry, manifest)
        scope_changed = _scope_changed(diff)
        if scope_changed and not req.accept_scope_change:
            raise HTTPException(
                status_code=409,
                detail={"error": "scope_change_requires_approval", "id": app_id, "scope_diff": diff},
            )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # Swap directories with a recoverable backup: rename the live dir aside,
    # move staging into place, then drop the backup. On any failure, restore.
    final_dir = BRAIN_APPS_DIR / app_id
    backup_dir = BRAIN_APPS_DIR / f".update-backup-{app_id}-{secrets.token_hex(4)}"
    try:
        if final_dir.exists():
            final_dir.rename(backup_dir)
        staging.rename(final_dir)
    except Exception:
        shutil.rmtree(final_dir, ignore_errors=True)
        if backup_dir.exists():
            backup_dir.rename(final_dir)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(backup_dir, ignore_errors=True)

    # Refresh manifest-derived fields; id, installed_at, enabled, token_hash
    # are identity and survive the update untouched.
    entry.update({
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "license": manifest["license"],
        "repo": manifest["repo"],
        "commit_sha": commit_sha,
        "updated_at": _now_iso(),
        "tab": manifest["tab"],
        "entries": manifest.get("entries", {}),
        "permissions": manifest.get("permissions", []),
        "requires_layers": manifest.get("requires_layers", []),
        "requires_endpoints": manifest.get("requires_endpoints", []),
    })
    apps[idx] = entry
    state["apps"] = apps
    _save_installed(state)

    # Hot-remount so the swapped bundle and routes serve without a restart.
    try:
        from api.apps_mount import mount_app as _mount_app, unmount_app as _unmount_app
        _unmount_app(request.app, app_id)
        _mount_app(request.app, entry)
    except Exception as e:
        print(f"[brain-apps] hot-remount failed for {app_id}: {e}", flush=True)

    return UpdateResponse(
        id=app_id,
        manifest=manifest,
        commit_sha=commit_sha,
        previous_sha=previous_sha,
        scope_changed=scope_changed,
    )
