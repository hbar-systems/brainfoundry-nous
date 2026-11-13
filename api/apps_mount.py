"""
Mount installed brain apps into the FastAPI app.

Called at startup to mount every enabled entry in `brain-apps/installed.json`,
and from `api/apps.py::install_app` immediately after install so the new app
is reachable without a process restart.

Each enabled app gets:
- a `StaticFiles` mount at `/apps/<id>/` serving the app's pre-built UI bundle
  (must contain `index.html`); the iframe host shell points at this path,
- if the manifest declares `entries.api`, the module's `router` is loaded
  via `importlib` and `include_router`-ed at `/apps/<id>/api/`.

Dynamic FastAPI route mutation works (FastAPI's `app.routes` is a plain list
that route resolution walks), but it is not part of the public contract.
For v0 we accept the risk: the alternative is a process restart per install,
which is jarring for first-time installers. Uninstall still requires restart
for now — see `unmount_app`.

Created: 2026-05-06
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import PlainTextResponse

from api.apps import BRAIN_APPS_DIR, _load_installed


def app_is_enabled(app_id: str) -> bool:
    """Is the app installed and enabled right now? Read per request, so a
    disable takes effect at once even if a route is still in app.routes."""
    try:
        from api import apps as _apps
        state = _apps._load_installed()
    except Exception:
        return False
    entry = next((a for a in state.get("apps", []) if a.get("id") == app_id), None)
    return bool(entry) and bool(entry.get("enabled", True))


class _AppStaticFiles(StaticFiles):
    """An app's static bundle that answers 404 once the app is disabled or gone."""

    def __init__(self, *args, app_id: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_id = app_id

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and not app_is_enabled(self.app_id):
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# The console's /api/bf proxy (ui/pages/api/bf/[...path].js) stamps every call it forwards to an
# app backend with this header: an HMAC of BRAIN_API_KEY, so it proves "came through the logged-in
# console" without handing the owner key to app frames. Same derivation on both sides.
APP_LANE_HEADER = "x-brain-app-lane"
_APP_LANE_LABEL = b"brain-app-lane/v1"


def app_lane_token(api_key: str) -> str:
    return hmac.new(api_key.encode(), _APP_LANE_LABEL, hashlib.sha256).hexdigest()


def require_backend_caller(request: Request) -> None:
    """An app backend answers the owner (x-api-key / Bearer BRAIN_API_KEY) or the console proxy
    (the app-lane header), never an anonymous caller that reaches the api vhost directly.
    A manifest that sets entries.api_public opts its backend out (audit 2026-11-13)."""
    key = os.getenv("BRAIN_API_KEY", "")
    if not key:
        if os.getenv("BRAIN_ENV", "dev").lower() == "dev":
            return
        raise HTTPException(status_code=500, detail="Server misconfigured: BRAIN_API_KEY not set.")
    presented = request.headers.get("x-api-key") or ""
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and not presented:
        presented = auth[len("Bearer "):]
    if presented and hmac.compare_digest(presented, key):
        return
    lane = request.headers.get(APP_LANE_HEADER) or ""
    if lane and hmac.compare_digest(lane, app_lane_token(key)):
        return
    raise HTTPException(status_code=401, detail="app backend needs the owner key or the console",
                        headers={"WWW-Authenticate": "Bearer"})


def _enabled_dependency(app_id: str):
    def _require_enabled() -> None:
        if not app_is_enabled(app_id):
            raise HTTPException(status_code=404, detail={"error": "app_not_enabled", "id": app_id})
    return _require_enabled


def _is_under(child: Path, parent: Path) -> bool:
    """Path-traversal guard: is `child` inside `parent` after resolving symlinks?"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def mount_app(app: FastAPI, entry: dict[str, Any]) -> None:
    """Mount a single app's optional API router and its UI bundle. Idempotent
    only in the sense that re-calling appends another route — FastAPI does not
    deduplicate. Caller is responsible for calling at most once per app per
    process.

    Ordering matters: the API router is registered BEFORE the static bundle.
    Route resolution walks `app.routes` in order and a StaticFiles `Mount` is a
    PREFIX match, so a static mount at `/apps/<id>` would otherwise shadow
    `/apps/<id>/api/*` and answer POSTs with 405 (StaticFiles rejects non-GET).
    Registering the router first lets its specific routes win; the static mount
    then catches only the remaining UI asset paths. The two steps are
    independent — a broken or missing API module never blocks the UI mount.
    """
    app_id = entry["id"]
    app_dir = BRAIN_APPS_DIR / app_id
    if not app_dir.exists():
        print(f"[brain-apps] mount skipped (clone missing): {app_id} at {app_dir}", flush=True)
        return

    entries = entry.get("entries") or {}

    api_path = entries.get("api")
    if api_path:
        _mount_api(app, app_id, app_dir, api_path, public=bool(entries.get("api_public")))

    ui_bundle = entries.get("ui_bundle")
    if ui_bundle:
        _mount_ui(app, app_id, app_dir, ui_bundle)


def _mount_ui(app: FastAPI, app_id: str, app_dir: Path, ui_bundle: str) -> None:
    """Mount the app's pre-built static bundle (must contain index.html) as a
    catch-all under /apps/<id>. Registered AFTER the API router so it does not
    shadow /apps/<id>/api/*."""
    bundle_dir = app_dir / ui_bundle
    if not _is_under(bundle_dir, app_dir):
        print(f"[brain-apps] refusing path-traversal ui_bundle for {app_id}: {ui_bundle}", flush=True)
        return
    if bundle_dir.exists() and (bundle_dir / "index.html").exists():
        app.mount(
            f"/apps/{app_id}",
            _AppStaticFiles(directory=str(bundle_dir), html=True, app_id=app_id),
            name=f"app-{app_id}",
        )
        print(f"[brain-apps] mounted ui {app_id} -> {bundle_dir}", flush=True)
    else:
        print(f"[brain-apps] ui_bundle missing or has no index.html for {app_id}: {bundle_dir}", flush=True)


def _mount_api(app: FastAPI, app_id: str, app_dir: Path, api_path: str, public: bool = False) -> None:
    """Load the app's API module via importlib and include its `router` at
    /apps/<id>/api. Registered BEFORE the static bundle (see mount_app). A
    failure here logs and returns without affecting the UI mount."""
    module_path = app_dir / api_path
    if not _is_under(module_path, app_dir):
        print(f"[brain-apps] refusing path-traversal api for {app_id}: {api_path}", flush=True)
        return
    if not module_path.exists():
        print(f"[brain-apps] api module missing for {app_id}: {module_path}", flush=True)
        return
    try:
        mod_name = f"brain_apps_{app_id.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(mod_name, str(module_path))
        if spec is None or spec.loader is None:
            print(f"[brain-apps] could not build module spec for {app_id}", flush=True)
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        api_router = getattr(module, "router", None)
        if api_router is None:
            print(f"[brain-apps] api module has no `router` attribute for {app_id}", flush=True)
            return
        deps = [Depends(_enabled_dependency(app_id))]
        if not public:
            deps.append(Depends(require_backend_caller))
        app.include_router(api_router, prefix=f"/apps/{app_id}/api", dependencies=deps)
        print(f"[brain-apps] mounted api {app_id}", flush=True)
    except Exception as e:
        print(f"[brain-apps] api mount failed for {app_id}: {e}", flush=True)


def _route_path(route) -> str:
    """A route's path; newer FastAPI keeps an included router as one lazy
    entry with no `path`, its prefix on `include_context`."""
    path = getattr(route, "path", None)
    if path is None:
        path = getattr(getattr(route, "include_context", None), "prefix", None)
    return path or ""


def unmount_app(app: FastAPI, app_id: str) -> None:
    """Best-effort removal of an app's routes from the live process.

    FastAPI keeps a flat `app.routes` list. We pop anything whose path starts
    with /apps/<id>/. This works for both StaticFiles mounts and APIRoutes,
    but is not officially supported and may leave orphan state in middleware
    layers. A process restart is the safe path; this is a convenience for v0.
    """
    prefix = f"/apps/{app_id}"
    keep = []
    removed = 0
    for route in app.routes:
        path = _route_path(route)
        if path == prefix or path.startswith(prefix + "/"):
            removed += 1
            continue
        keep.append(route)
    app.router.routes[:] = keep
    if removed:
        print(f"[brain-apps] unmounted {app_id} ({removed} routes removed)", flush=True)


def mount_installed_apps(app: FastAPI) -> None:
    """Walk installed.json and mount every enabled entry. Call once at startup."""
    # Migration: rehome any root-owned app dir to the bind-mount host owner.
    # The api container clones as root, so dirs from the old install path are
    # root-owned on the host — the operator cannot `rm` them without sudo and
    # a stale dir blocks reinstall. Re-own at boot so reinstall works.
    try:
        from api.apps import _chown_existing_app_dirs
        _chown_existing_app_dirs()
    except Exception as e:
        print(f"[brain-apps] startup chown migration skipped: {e}", flush=True)
    try:
        state = _load_installed()
    except Exception as e:
        print(f"[brain-apps] could not load installed.json: {e}", flush=True)
        return
    for entry in state.get("apps", []):
        if entry.get("enabled", True):
            mount_app(app, entry)
