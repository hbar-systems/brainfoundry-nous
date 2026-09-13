"""Tests for packs (unreleased 0.10.0): brain-apps/packs/<name>.json.

Covers the pack schema, the defaults.json compatibility alias, dependency
ordering, BRAIN_PACKS parsing, first-run seeding from packs, the pack
endpoints, and the manifest compute block (schema + scope diff). Cloning is
monkeypatched away; these tests exercise the gate logic, not git.

Created 2026-09-13.
"""
import json
import os

import pytest

from api import apps

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _pack(name, app_ids, requires=(), version="0.1.0", compute=None):
    return {
        "dialect": "brain-apps-pack/v1",
        "name": name,
        "version": version,
        "description": f"{name} pack",
        "requires": list(requires),
        "apps": [{"id": a, "repo_url": f"https://github.com/hbar-systems/{a}", "ref": "HEAD"} for a in app_ids],
        "compute": compute,
    }


@pytest.fixture(autouse=True)
def _tmp_apps(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "BRAIN_APPS_DIR", tmp_path)
    monkeypatch.setattr(apps, "INSTALLED_JSON", tmp_path / "installed.json")
    monkeypatch.setattr(apps, "DEFAULTS_JSON", tmp_path / "defaults.json")
    monkeypatch.setattr(apps, "PACKS_DIR", tmp_path / "packs")
    monkeypatch.delenv(apps.PACKS_ENV, raising=False)
    (tmp_path / "packs").mkdir()


def _write_pack(tmp_path, pack, name=None):
    (tmp_path / "packs" / f"{name or pack['name']}.json").write_text(json.dumps(pack))


def _fake_install(monkeypatch, fail=()):
    def fake(repo_url, ref, installed_ids, installed_routes):
        aid = repo_url.rsplit("/", 1)[-1]
        if aid in fail:
            raise RuntimeError(f"clone failed: {aid}")
        route = f"/{aid}"
        if aid in installed_ids or route in apps.RESERVED_ROUTES or route in installed_routes:
            return None
        return {"id": aid, "name": aid, "version": "0.1.0", "description": "d",
                "license": "AGPL-3.0", "repo": repo_url, "commit_sha": "deadbeef",
                "installed_at": "t", "enabled": True, "tab": {"label": aid, "route": route},
                "entries": {}, "permissions": [], "requires_layers": [],
                "requires_endpoints": [], "compute": None, "token_hash": "h",
                "preinstalled": True}
    monkeypatch.setattr(apps, "_install_default", fake)


# ── the shipped base pack ──────────────────────────────────────────────────

def test_shipped_base_pack_is_valid_and_is_defaults_plus_oracle():
    base = json.load(open(os.path.join(ROOT, "brain-apps", "packs", "base.json")))
    apps._validate_pack(base, "base")  # raises on schema failure
    defaults = json.load(open(os.path.join(ROOT, "brain-apps", "defaults.json")))
    default_ids = [a["id"] for a in defaults["apps"]]
    base_ids = [a["id"] for a in base["apps"]]
    assert base_ids[: len(default_ids)] == default_ids
    assert base_ids[len(default_ids):] == ["oracle"]
    oracle = next(a for a in base["apps"] if a["id"] == "oracle")
    assert oracle["repo_url"] == "https://github.com/hbar-systems/brain-app-oracle"
    assert oracle["ref"] == "v0.1.0"
    assert base["requires"] == []
    assert base["compute"] is None


# ── loader + alias ─────────────────────────────────────────────────────────

def test_load_pack_reads_packs_dir_first(tmp_path):
    _write_pack(tmp_path, _pack("base", ["xray"]))
    (tmp_path / "defaults.json").write_text(json.dumps({"apps": [
        {"id": "old-app", "repo_url": "https://github.com/hbar-systems/old-app"}]}))
    pack = apps.load_pack("base")
    assert [a["id"] for a in pack["apps"]] == ["xray"]
    assert pack["version"] == "0.1.0"


def test_load_pack_base_falls_back_to_defaults_alias(tmp_path):
    (tmp_path / "defaults.json").write_text(json.dumps({"apps": [
        {"id": "old-app", "repo_url": "https://github.com/hbar-systems/old-app"}]}))
    pack = apps.load_pack("base")
    assert [a["id"] for a in pack["apps"]] == ["old-app"]
    assert pack["version"] == "0.0.0-defaults"
    assert "base" in apps.list_pack_names()


def test_load_pack_missing_raises():
    with pytest.raises(apps.PackError):
        apps.load_pack("nope")
    with pytest.raises(apps.PackError):
        apps.load_pack("../etc")


def test_load_pack_rejects_schema_violation_and_name_mismatch(tmp_path):
    bad = _pack("music", ["deejay"]); bad["apps"][0]["repo_url"] = "http://evil.example/x"
    _write_pack(tmp_path, bad)
    with pytest.raises(apps.PackError):
        apps.load_pack("music")
    _write_pack(tmp_path, _pack("video", ["render"]), name="numa")
    with pytest.raises(apps.PackError):
        apps.load_pack("numa")


# ── env + dependency order ─────────────────────────────────────────────────

def test_requested_packs_defaults_to_base_and_keeps_base_first(monkeypatch):
    assert apps.requested_packs() == ["base"]
    monkeypatch.setenv(apps.PACKS_ENV, " music, base ,video,music ")
    assert apps.requested_packs() == ["base", "music", "video"]
    monkeypatch.setenv(apps.PACKS_ENV, "")
    assert apps.requested_packs() == ["base"]


def test_resolve_packs_orders_requirements_and_fails_soft(tmp_path):
    _write_pack(tmp_path, _pack("base", ["alpha"]))
    _write_pack(tmp_path, _pack("music", ["deejay"], requires=["base"]))
    _write_pack(tmp_path, _pack("video", ["render"], requires=["ghost"]))
    packs, failures = apps.resolve_packs(["video", "music"])
    assert [p["name"] for p in packs] == ["base", "music"]
    assert {f["name"] for f in failures} == {"ghost", "video"}


def test_resolve_packs_detects_cycle(tmp_path):
    _write_pack(tmp_path, _pack("alpha", ["xray"], requires=["beta"]))
    _write_pack(tmp_path, _pack("beta", ["yankee"], requires=["alpha"]))
    packs, failures = apps.resolve_packs(["alpha"])
    assert packs == []
    assert any("cycle" in f["error"] for f in failures)


# ── first-run seed from packs ──────────────────────────────────────────────

def test_seed_installs_requested_packs_in_order(tmp_path, monkeypatch):
    _fake_install(monkeypatch)
    _write_pack(tmp_path, _pack("base", ["alpha", "beta"]))
    _write_pack(tmp_path, _pack("music", ["deejay", "alpha"], requires=["base"]))
    monkeypatch.setenv(apps.PACKS_ENV, "music")
    apps.seed_default_apps()
    state = apps._load_installed()
    assert [x["id"] for x in state["apps"]] == ["alpha", "beta", "deejay"]
    assert state["packs"]["base"]["installed"] == ["alpha", "beta"]
    assert state["packs"]["music"]["installed"] == ["deejay"]
    assert state["packs"]["music"]["skipped"] == ["alpha"]   # install-if-absent across packs
    assert state.get("defaults_seeded")


def test_seed_one_bad_app_does_not_block_the_rest(tmp_path, monkeypatch):
    _fake_install(monkeypatch, fail=("beta",))
    _write_pack(tmp_path, _pack("base", ["alpha", "beta", "gamma"]))
    apps.seed_default_apps()
    state = apps._load_installed()
    assert [x["id"] for x in state["apps"]] == ["alpha", "gamma"]
    assert state["packs"]["base"]["failed"][0]["id"] == "beta"


def test_seed_never_touches_a_populated_brain(tmp_path, monkeypatch):
    _fake_install(monkeypatch)
    _write_pack(tmp_path, _pack("base", ["alpha"]))
    apps._save_installed({"dialect": "brain-apps-installed/v1",
                          "apps": [{"id": "mine", "tab": {"route": "/mine"}}]})
    apps.seed_default_apps()
    state = apps._load_installed()
    assert [x["id"] for x in state["apps"]] == ["mine"]
    assert "packs" not in state
    assert state.get("defaults_seeded")


def test_seed_unknown_pack_in_env_still_seeds_base(tmp_path, monkeypatch):
    _fake_install(monkeypatch)
    _write_pack(tmp_path, _pack("base", ["alpha"]))
    monkeypatch.setenv(apps.PACKS_ENV, "base,ghost")
    apps.seed_default_apps()
    state = apps._load_installed()
    assert [x["id"] for x in state["apps"]] == ["alpha"]
    assert list(state["packs"]) == ["base"]


# ── endpoints ──────────────────────────────────────────────────────────────

class _Req:
    class app:  # minimal stand-in; hot-mount is wrapped in try/except
        pass


def test_list_packs_reports_state(tmp_path, monkeypatch):
    _fake_install(monkeypatch)
    _write_pack(tmp_path, _pack("base", ["alpha"]))
    _write_pack(tmp_path, _pack("music", ["deejay"], requires=["base"],
                                compute={"endpoint": "https://spoke.example", "permit_class": "music.render"}))
    apps.seed_default_apps()
    out = apps.list_packs()
    by = {p["name"]: p for p in out["packs"]}
    assert by["base"]["installed"] is True and by["base"]["missing"] == []
    assert by["music"]["installed"] is False and by["music"]["missing"] == ["deejay"]
    assert by["music"]["compute"]["health_path"] if "health_path" in by["music"]["compute"] else True
    assert out["requested"] == ["base"]


def test_install_pack_later_installs_requirements_first(tmp_path, monkeypatch):
    _fake_install(monkeypatch)
    _write_pack(tmp_path, _pack("base", ["alpha"]))
    _write_pack(tmp_path, _pack("music", ["deejay"], requires=["base"]))
    res = apps.install_pack("music", _Req())
    state = apps._load_installed()
    assert [x["id"] for x in state["apps"]] == ["alpha", "deejay"]
    assert res["packs"]["base"]["installed"] == ["alpha"]
    assert res["packs"]["music"]["installed"] == ["deejay"]
    # idempotent: second call installs nothing
    res2 = apps.install_pack("music", _Req())
    assert res2["packs"]["music"]["installed"] == [] and res2["packs"]["music"]["skipped"] == ["deejay"]


def test_install_pack_unknown_is_404(tmp_path, monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        apps.install_pack("ghost", _Req())
    assert ei.value.status_code == 404


# ── manifest compute block ─────────────────────────────────────────────────

def _manifest(compute=None):
    m = {
        "dialect": "brain-app/v1", "id": "planner-bridge", "name": "planner bridge",
        "version": "0.1.0", "description": "d", "license": "AGPL-3.0",
        "author": {"name": "hbar"}, "repo": "https://github.com/hbar-systems/planner-bridge",
        "tab": {"label": "Planner", "route": "/planner"}, "entries": {"ui_bundle": "dist"},
    }
    if compute is not None:
        m["compute"] = compute
    return m


def test_manifest_compute_block_validates():
    from fastapi import HTTPException
    apps._validate_manifest(_manifest())
    apps._validate_manifest(_manifest({"endpoint": "https://music.example:8080",
                                       "permit_class": "music.als_build", "health_path": "/health"}))
    with pytest.raises(HTTPException):
        apps._validate_manifest(_manifest({"endpoint": "https://music.example"}))  # permit_class required
    with pytest.raises(HTTPException):
        apps._validate_manifest(_manifest({"endpoint": "ftp://x", "permit_class": "p"}))
    with pytest.raises(HTTPException):
        apps._validate_manifest(_manifest({"endpoint": "https://x", "permit_class": "p", "extra": 1}))


def test_compute_change_is_a_scope_change():
    installed = {"permissions": [], "requires_layers": [], "compute": None}
    same = apps._scope_diff(installed, _manifest())
    assert not apps._scope_changed(same)
    widened = apps._scope_diff(installed, _manifest({"endpoint": "https://x", "permit_class": "p"}))
    assert widened["compute_changed"] and apps._scope_changed(widened)
