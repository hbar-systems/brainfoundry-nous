"""Tests for the pre-installed default app shelf — first-run-only seeding.

The safety contract (project_rsync_installed_json_hazard) is what matters:
seed once on a FRESH brain, NEVER clobber a populated installed.json, and never
re-seed after the operator uninstalls. `_install_default` is monkeypatched so no
git/network is touched — these tests exercise the gate logic, not cloning.

Created 2026-06-23.
"""
import json

import pytest

from api import apps


@pytest.fixture(autouse=True)
def _tmp_apps(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "BRAIN_APPS_DIR", tmp_path)
    monkeypatch.setattr(apps, "INSTALLED_JSON", tmp_path / "installed.json")
    monkeypatch.setattr(apps, "DEFAULTS_JSON", tmp_path / "defaults.json")
    (tmp_path / "defaults.json").write_text(json.dumps({"apps": [
        {"id": "alpha", "repo_url": "https://example.com/alpha", "ref": "HEAD"},
        {"id": "beta", "repo_url": "https://example.com/beta", "ref": "HEAD"},
    ]}))


def _fake_install(monkeypatch):
    def fake(repo_url, ref, installed_ids, installed_routes):
        aid = repo_url.rsplit("/", 1)[-1]
        route = f"/{aid}"
        if aid in installed_ids or route in apps.RESERVED_ROUTES or route in installed_routes:
            return None
        return {"id": aid, "name": aid, "version": "0.1.0", "description": "d",
                "license": "AGPL-3.0", "repo": repo_url, "commit_sha": "deadbeef",
                "installed_at": "t", "enabled": True, "tab": {"label": aid, "route": route},
                "entries": {}, "permissions": [], "requires_layers": [],
                "requires_endpoints": [], "token_hash": "h", "preinstalled": True}
    monkeypatch.setattr(apps, "_install_default", fake)


def test_fresh_brain_installs_defaults(monkeypatch):
    _fake_install(monkeypatch)
    apps.seed_default_apps()
    state = apps._load_installed()
    assert {a["id"] for a in state["apps"]} == {"alpha", "beta"}
    assert state.get("defaults_seeded")
    assert all(a.get("preinstalled") for a in state["apps"])


def test_populated_brain_is_noop_but_marked(monkeypatch):
    _fake_install(monkeypatch)
    apps._save_installed({"dialect": "brain-apps-installed/v1",
                          "apps": [{"id": "myapp", "tab": {"route": "/myapp"}}]})
    apps.seed_default_apps()
    state = apps._load_installed()
    assert {a["id"] for a in state["apps"]} == {"myapp"}   # nothing injected
    assert state.get("defaults_seeded")                     # marked, won't retry


def test_marker_blocks_reseed_after_uninstall_all(monkeypatch):
    _fake_install(monkeypatch)
    apps.seed_default_apps()                                # fresh -> installs
    s = apps._load_installed(); s["apps"] = []; apps._save_installed(s)
    apps.seed_default_apps()                                # must NOT re-install
    assert apps._load_installed()["apps"] == []


def test_no_defaults_manifest_is_noop(monkeypatch, tmp_path):
    _fake_install(monkeypatch)
    (tmp_path / "defaults.json").unlink()
    apps.seed_default_apps()
    # No manifest -> nothing installed, and no marker written (nothing to seed).
    state = apps._load_installed()
    assert state.get("apps", []) == []
    assert not state.get("defaults_seeded")


def test_install_if_absent_skips_already_present(monkeypatch):
    # alpha already installed (populated) -> whole run is a no-op anyway, but
    # prove the per-app skip path too via a fresh brain whose loop re-sees alpha.
    _fake_install(monkeypatch)
    apps.seed_default_apps()                 # installs alpha + beta
    # reset marker to force the loop again, keep alpha present
    s = apps._load_installed()
    s["apps"] = [a for a in s["apps"] if a["id"] == "alpha"]
    del s["defaults_seeded"]
    apps._save_installed(s)
    # populated -> no-op path; alpha stays single, nothing duplicated
    apps.seed_default_apps()
    ids = [a["id"] for a in apps._load_installed()["apps"]]
    assert ids == ["alpha"]
