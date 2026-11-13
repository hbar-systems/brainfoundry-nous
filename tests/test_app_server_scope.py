"""Brain apps keep to their declared scope on the server (security audit 2026-11-13, batch b4).

Cloning is monkeypatched to copy a fixture dir; FastAPI routes are exercised on a real app object
with TestClient where a request is needed. Created 2026-11-13.
    pytest tests/test_app_server_scope.py -q
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import apps

BACKEND = '''from fastapi import APIRouter
router = APIRouter()

@router.get("/whoami")
def whoami():
    return {"me": "app"}
'''


def _manifest(app_id="demo", api=None, perms=("llm.invoke",), layers=(), **extra):
    entries = {"ui_bundle": "./"}
    if api:
        entries["api"] = api
    m = {"dialect": "brain-app/v1", "id": app_id, "name": app_id.title(), "version": "0.1.0",
         "description": "dummy app for tests", "license": "AGPL-3.0",
         "author": {"name": "t"}, "repo": f"https://github.com/example/{app_id}",
         "tab": {"label": app_id.title(), "route": f"/{app_id}"}, "entries": entries,
         "permissions": list(perms), "requires_layers": [{"layer": l, "mode": md} for l, md in layers]}
    m.update(extra)
    return m


class Upstream:
    """A fake repo: write() sets HEAD's files, _fetch_source copies them and returns the sha."""

    def __init__(self, root: Path):
        self.root = root
        self.sha = "sha-0"
        self.n = 0

    def write(self, manifest, backend=None):
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        (self.root / "brain-app.yaml").write_text(yaml.safe_dump(manifest))
        (self.root / "index.html").write_text("<html><head></head><body>app</body></html>")
        if backend:
            (self.root / manifest["entries"]["api"].lstrip("./")).write_text(backend)
        self.n += 1
        self.sha = f"sha-{self.n}"

    def fetch(self, dest, repo_url=None, ref="HEAD", shipped=None):
        shutil.copytree(self.root, dest)
        return self.sha


@pytest.fixture
def env(tmp_path, monkeypatch):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    monkeypatch.setattr(apps, "BRAIN_APPS_DIR", apps_dir)
    monkeypatch.setattr(apps, "INSTALLED_JSON", apps_dir / "installed.json")
    from api import apps_mount
    monkeypatch.setattr(apps_mount, "BRAIN_APPS_DIR", apps_dir)
    up = Upstream(tmp_path / "upstream")
    monkeypatch.setattr(apps, "_fetch_source", up.fetch)
    monkeypatch.setattr(apps, "_git_clone", lambda url, ref, dest: up.fetch(dest))
    monkeypatch.setattr(apps, "_chown_to_host_owner", lambda p: None)
    return up


class _Req:
    def __init__(self, app):
        self.app = app


def _install(up, app, manifest, backend=None):
    up.write(manifest, backend)
    return apps.install_app(apps.InstallRequest(repo_url=manifest["repo"]), _Req(app))


def _entry(app_id="demo"):
    return next(a for a in apps._load_installed()["apps"] if a["id"] == app_id)


# ── app-update-scope-diff-omits-backend-entry ─────────────────────────────

def test_adding_a_backend_is_a_scope_change(env):
    app = FastAPI()
    _install(env, app, _manifest())
    env.write(_manifest(api="backend.py"), BACKEND)
    pv = apps.update_preview("demo")
    assert pv.scope_changed and pv.scope_diff["backend_changed"] and pv.scope_diff["backend"] == "backend.py"
    with pytest.raises(HTTPException) as e:
        apps.update_app("demo", apps.UpdateRequest(accept_scope_change=False), _Req(app))
    assert e.value.status_code == 409
    assert e.value.detail["error"] == "scope_change_requires_approval"
    assert "api" not in (_entry()["entries"] or {})
    assert not any(p.startswith("/apps/demo/api") for p in _routes(app))
    out = apps.update_app("demo", apps.UpdateRequest(accept_scope_change=True), _Req(app))
    assert out.scope_changed and _entry()["entries"]["api"] == "backend.py"


def test_new_code_in_an_existing_backend_needs_approval(env):
    installed = {"permissions": [], "requires_layers": [], "compute": None,
                 "entries": {"ui_bundle": "./", "api": "backend.py"}, "commit_sha": "a"}
    m = _manifest(api="backend.py", perms=())
    assert apps._scope_changed(apps._scope_diff(installed, m, "b"))
    assert not apps._scope_changed(apps._scope_diff(installed, m, "a"))


def test_frontend_only_update_stays_one_click(env):
    installed = {"permissions": ["llm.invoke"], "requires_layers": [], "compute": None,
                 "entries": {"ui_bundle": "./"}, "commit_sha": "a"}
    assert not apps._scope_changed(apps._scope_diff(installed, _manifest(), "b"))


# ── app-disable-does-not-unmount-routes ──────────────────────────────────

def _routes(app, app_id="demo"):
    from api.apps_mount import _route_path
    return [_route_path(r) for r in app.routes if _route_path(r).startswith(f"/apps/{app_id}")]


def test_disable_takes_routes_down_at_once_and_enable_brings_them_back(env):
    app = FastAPI()
    _install(env, app, _manifest(api="backend.py"), BACKEND)
    c = TestClient(app)
    assert c.get("/apps/demo/api/whoami").status_code == 200
    assert c.get("/apps/demo/index.html").status_code == 200
    apps.disable_app("demo", _Req(app))
    assert _routes(app) == []
    assert c.get("/apps/demo/api/whoami").status_code == 404
    assert c.get("/apps/demo/index.html").status_code == 404
    apps.enable_app("demo", _Req(app))
    assert c.get("/apps/demo/api/whoami").status_code == 200
    apps.enable_app("demo", _Req(app))  # no stacking
    assert len(_routes(app)) == 2


def test_mounted_routes_check_enabled_per_request(env):
    app = FastAPI()
    _install(env, app, _manifest(api="backend.py"), BACKEND)
    c = TestClient(app)
    state = apps._load_installed()
    state["apps"][0]["enabled"] = False
    apps._save_installed(state)  # flag flipped with routes still in app.routes
    assert _routes(app)
    assert c.get("/apps/demo/api/whoami").status_code == 404
    assert c.get("/apps/demo/index.html").status_code == 404
    assert c.get("/apps/demo/").status_code == 404


def test_update_does_not_remount_a_disabled_app(env):
    app = FastAPI()
    _install(env, app, _manifest(api="backend.py"), BACKEND)
    apps.disable_app("demo", _Req(app))
    env.write(_manifest(api="backend.py", version="0.2.0"), BACKEND)
    apps.update_app("demo", apps.UpdateRequest(accept_scope_change=True), _Req(app))
    assert _routes(app) == [] and _entry()["enabled"] is False


def test_uninstall_removes_the_backend_router_too(env):
    app = FastAPI()
    _install(env, app, _manifest(api="backend.py"), BACKEND)
    apps.uninstall_app("demo", _Req(app))
    assert _routes(app) == []
    assert TestClient(app).get("/apps/demo/api/whoami").status_code == 404
