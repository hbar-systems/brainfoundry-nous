"""The Week app (WEEK-APP-1, 2026-11-10): a shipped app, the files.read bridge intent, and the
interview's "first" answer week.

- brain-apps/shipped/week is a valid brain-app, in the base pack as {"id": "week", "shipped": "week"}.
- A shipped app installs by copy (api/apps.py install_shipped, and the pack seed), its pin is a
  content hash, and Update copies it again; reserved ids (packs, shipped) are refused.
- files.read reads one desk file through the host page: the desk root from /cc/files, the file from
  /cc/files/raw/<desk>/<name>; no '..', no absolute name, 404/403 map to not_found/forbidden.
- ui.open accepts /talk (a thread link in the week page).
- from_answers({"first": "week"}) opens the conversation with /apps/week beside it.

    pytest tests/test_week_app.py -v
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest
import yaml

from api import apps

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "ui" / "lib"
WEEK = ROOT / "brain-apps" / "shipped" / "week"
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout as L  # noqa: E402


class _Req:
    class app:  # hot-mount is wrapped in try/except
        pass


# ---- the shipped app ----

def test_week_manifest_is_valid_and_reads_one_permission():
    m = yaml.safe_load((WEEK / "brain-app.yaml").read_text())
    apps._validate_manifest(m)
    assert m["id"] == "week" and m["permissions"] == ["files.read"]
    assert not m.get("requires_layers")
    for f in ("index.html", "README.md", "LICENSE"):
        assert (WEEK / f).is_file(), f
    html = (WEEK / "index.html").read_text()
    assert "No week page on this brain yet. hbar.world's scripts/week-page.py writes it." in html
    assert "'files.read'" in html and "week/index.html" in html


def test_week_is_in_the_base_pack_and_the_alias():
    for rel in ("packs/base.json", "defaults.json"):
        data = json.loads((ROOT / "brain-apps" / rel).read_text())
        assert {"id": "week", "shipped": "week"} in data["apps"], rel
    apps._validate_pack(json.loads((ROOT / "brain-apps" / "packs" / "base.json").read_text()), "base")


def test_pack_entry_needs_exactly_one_source():
    base = {"dialect": "brain-apps-pack/v1", "name": "x1", "version": "0.1.0", "description": "d"}
    for bad in ({"id": "week"}, {"id": "week", "shipped": "week", "repo_url": "https://github.com/a/b"},
                {"id": "week", "shipped": "../etc"}):
        with pytest.raises(apps.PackError):
            apps._validate_pack({**base, "apps": [bad]}, "x1")


@pytest.fixture
def tmp_apps(tmp_path, monkeypatch):
    monkeypatch.setattr(apps, "BRAIN_APPS_DIR", tmp_path)
    monkeypatch.setattr(apps, "INSTALLED_JSON", tmp_path / "installed.json")
    monkeypatch.setattr(apps, "DEFAULTS_JSON", tmp_path / "defaults.json")
    monkeypatch.setattr(apps, "PACKS_DIR", tmp_path / "packs")
    monkeypatch.setattr(apps, "SHIPPED_DIR", tmp_path / "shipped")
    monkeypatch.delenv(apps.PACKS_ENV, raising=False)
    shutil.copytree(WEEK, tmp_path / "shipped" / "week")
    monkeypatch.setattr(apps, "_git_clone", lambda *a, **k: pytest.fail("a shipped app never clones"))
    return tmp_path


def test_install_shipped_copies_registers_and_lists(tmp_apps):
    assert [x["name"] for x in apps.list_shipped()["shipped"]] == ["week"]
    assert apps.list_shipped()["shipped"][0]["installed"] is False
    r = apps.install_shipped("week", _Req())
    assert r.id == "week" and len(r.commit_sha) == 40
    assert (tmp_apps / "week" / "index.html").read_text() == (WEEK / "index.html").read_text()
    entry = apps._load_installed()["apps"][0]
    assert entry["shipped"] == "week" and entry["permissions"] == ["files.read"] and entry["tab"]["route"] == "/week"
    assert apps.list_shipped()["shipped"][0]["installed"] is True
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:          # twice is refused, nothing half-installed
        apps.install_shipped("week", _Req())
    assert ei.value.status_code == 409
    assert not [p for p in tmp_apps.iterdir() if p.name.startswith(".staging-")]
    for bad in ("../week", "ghost", "Week"):
        with pytest.raises(HTTPException):
            apps.install_shipped(bad, _Req())


def test_update_recopies_a_shipped_app(tmp_apps):
    apps.install_shipped("week", _Req())
    pv = apps.update_preview("week")
    assert pv.up_to_date is True
    (tmp_apps / "shipped" / "week" / "index.html").write_text("<p>new</p>")
    pv = apps.update_preview("week")
    assert pv.up_to_date is False and pv.scope_changed is False
    r = apps.update_app("week", apps.UpdateRequest(accept_scope_change=False), _Req())
    assert r.commit_sha != r.previous_sha
    assert (tmp_apps / "week" / "index.html").read_text() == "<p>new</p>"
    assert apps._load_installed()["apps"][0]["shipped"] == "week"


def test_pack_seed_installs_a_shipped_app(tmp_apps):
    (tmp_apps / "packs").mkdir()
    (tmp_apps / "packs" / "base.json").write_text(json.dumps({
        "dialect": "brain-apps-pack/v1", "name": "base", "version": "0.1.0", "description": "d",
        "apps": [{"id": "week", "shipped": "week"}]}))
    apps.seed_default_apps()
    state = apps._load_installed()
    assert [a["id"] for a in state["apps"]] == ["week"]
    assert state["apps"][0]["preinstalled"] is True and state["apps"][0]["shipped"] == "week"
    assert state["packs"]["base"]["installed"] == ["week"]


def test_reserved_ids_are_refused():
    from fastapi import HTTPException
    for rid in ("packs", "shipped"):
        with pytest.raises(HTTPException):
            apps._check_reserved_id(rid)
    apps._check_reserved_id("week")


# ---- the bridge intent (ui/lib/appBridge.js under node) ----

HARNESS = r"""
const { makeBridge } = require('./appBridge.js')
const routes = %(routes)s
const calls = []
const fetch = (url, init) => {
  calls.push(url)
  const hit = routes[url]
  if (hit === undefined) return Promise.reject(new Error('no route ' + url))
  const [status, body] = hit
  return Promise.resolve({ status, ok: status < 400,
    json: () => Promise.resolve(typeof body === 'string' ? JSON.parse(body) : body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)) })
}
const nav = []
const b = makeBridge({ appInfo: { id: 'week', name: 'Week', version: '0.1.0', permissions: %(perms)s },
  fetch, ls: null, brainName: 'x', theme: () => ({}), navigate: r => nav.push(r) })
b.handleIntent({ type: %(type)s, payload: %(payload)s, request_id: '1' }).then(r => console.log(JSON.stringify({ r, calls, nav })))
"""

ROOTS = [200, {"path": None, "roots": [{"label": "out", "path": "/home/hands/out"}, {"label": "world", "path": "/home/hands/world"}]}]
RAW = "/cc/files/raw/home/hands/out/week/index.html"


def bridge(type_, payload, routes, perms=("files.read",)):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    src = HARNESS % {"routes": json.dumps(routes), "perms": json.dumps(list(perms)),
                     "type": json.dumps(type_), "payload": json.dumps(payload)}
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, cwd=str(LIB), timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_files_read_reads_the_desk_file():
    out = bridge("files.read", {"name": "week/index.html"}, {"/cc/files": ROOTS, RAW: [200, "<h1>week</h1>"]})
    assert out["r"] == {"ok": True, "result": {"path": "/home/hands/out/week/index.html", "text": "<h1>week</h1>"}}
    assert out["calls"] == ["/cc/files", RAW]


@pytest.mark.parametrize("status,code", [(404, "not_found"), (403, "forbidden"), (500, "files_read_failed")])
def test_files_read_maps_missing_and_closed(status, code):
    out = bridge("files.read", {"name": "week/index.html"}, {"/cc/files": ROOTS, RAW: [status, {"error": "x"}]})
    assert out["r"]["ok"] is False and out["r"]["error"]["code"] == code


def test_files_read_needs_the_permission_and_a_desk_name():
    out = bridge("files.read", {"name": "week/index.html"}, {}, perms=())
    assert out["r"]["error"]["code"] == "permission_denied" and out["calls"] == []
    for bad in ("../world/.env", "week/../../x", "/etc/passwd", "", "a//b", "week/./x"):
        out = bridge("files.read", {"name": bad}, {"/cc/files": ROOTS})
        assert out["r"]["error"]["code"] == "bad_name", bad
        assert out["calls"] == [], bad


def test_files_read_without_cc_says_no_door():
    out = bridge("files.read", {"name": "week/index.html"}, {"/cc/files": [404, {}]})
    assert out["r"]["error"]["code"] == "no_files_door"
    out = bridge("files.read", {"name": "week/index.html"}, {"/cc/files": [200, {"roots": [{"label": "world", "path": "/w"}]}]})
    assert out["r"]["error"]["code"] == "no_files_door"


def test_ui_open_accepts_a_thread_link():
    out = bridge("ui.open", {"route": "/talk?thread=9d090818-82cf-4d09-9ca4-0e4c82aaae6b"}, {}, perms=())
    assert out["r"]["ok"] is True and out["nav"] == ["/talk?thread=9d090818-82cf-4d09-9ca4-0e4c82aaae6b"]


def test_apps_shipped_is_the_router_not_an_app():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const l=require('./appLane.js');console.log(JSON.stringify(l.classify(['apps','shipped','week'],'GET')))"],
                       capture_output=True, text=True, cwd=str(LIB), timeout=30)
    assert json.loads(r.stdout) == {"kind": "core"}


# ---- the interview ----

def test_first_week_opens_the_week_app_beside_the_conversation():
    lay = L.from_answers({"first": "week"})
    assert lay["start"] == "/apps/week" and lay["view"] == "talk"
    assert "week beside the chat" in L.summary(lay)
    q = next(q for q in L.QUESTIONS if q["id"] == "first")
    assert "week" in [v for v, _ in q["options"]]
