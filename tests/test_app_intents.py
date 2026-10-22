"""The base-shelf bridge intents (2026-10-22): each is gated by its manifest permission, sends fixed
fields only, and never lets an app widen what it reads (no include_local_only, no undeclared layer,
no route outside the console's own screens).

Runs ui/lib/appBridge.js under node with a recording fetch.
    pytest tests/test_app_intents.py -v
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

LIB = pathlib.Path(__file__).resolve().parents[1] / "ui" / "lib"

HARNESS = r"""
const { makeBridge } = require('./appBridge.js')
const calls = []
const body = %(body)s
const status = %(status)d
const fetch = (url, init) => { calls.push({ url, method: (init && init.method) || 'GET', body: init && typeof init.body === 'string' ? JSON.parse(init.body) : null }); return Promise.resolve({ status, ok: status < 400, json: () => Promise.resolve(body) }) }
const nav = []
const b = makeBridge({ appInfo: %(app)s, fetch, ls: null, brainName: 'x', theme: () => ({ tokens: { '--bg': '#000' } }), navigate: r => nav.push(r) })
b.handleIntent({ type: %(type)s, payload: %(payload)s, request_id: '1' }).then(r => console.log(JSON.stringify({ r, calls, nav })))
"""


def run(type_, payload=None, perms=(), layers=(), body=None, status=200):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    app = {"id": "today", "name": "Today", "version": "0.1.0", "permissions": list(perms),
           "requires_layers": [{"layer": l, "mode": m} for l, m in layers]}
    src = HARNESS % {"body": json.dumps(body or {}), "status": status, "app": json.dumps(app),
                     "type": json.dumps(type_), "payload": json.dumps(payload or {})}
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, cwd=str(LIB), timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("intent,perm", [
    ("memory.search", "memory.read"), ("tasks.list", "tasks.read"), ("tasks.add", "tasks.write"),
    ("tasks.complete", "tasks.write"), ("calendar.upcoming", "calendar.read"), ("email.recent", "email.read"),
    ("web.fetch", "network.outbound"), ("files.save", "files.write"), ("audio.transcribe", "audio.transcribe"),
])
def test_each_intent_needs_its_permission(intent, perm):
    out = run(intent, {"query": "x", "text": "x", "id": "abc", "url": "https://a.b", "name": "a.txt", "base64": "eA=="})
    assert out["r"]["ok"] is False and out["r"]["error"]["code"] == "permission_denied"
    assert perm in out["r"]["error"]["detail"]
    assert out["calls"] == []


def test_memory_search_scoped_to_declared_read_layers_open_view():
    out = run("memory.search", {"query": "Paul", "limit": 999, "include_local_only": True, "layers": ["procedural"]},
              perms=["memory.read"], layers=[("semantic", "read"), ("episodic", "append")],
              body={"results": [{"content": "c", "document_name": "d", "similarity": 0.9, "metadata": {}, "secret": 1}]})
    assert out["r"]["ok"] is True
    sent = out["calls"][0]
    assert sent["url"] == "/api/bf/documents/search"
    assert sent["body"] == {"query": "Paul", "limit": 20, "layers": ["semantic"]}
    assert out["r"]["result"]["results"] == [{"content": "c", "document_name": "d", "similarity": 0.9, "metadata": {}}]


def test_memory_search_without_read_layer_refused():
    out = run("memory.search", {"query": "x"}, perms=["memory.read"], layers=[("episodic", "append")])
    assert out["r"]["error"]["code"] == "layer_not_declared" and out["calls"] == []


def test_tasks_add_is_attributed_to_the_app():
    out = run("tasks.add", {"text": "call Paul", "due": "2026-10-23T09:00:00Z", "source": "forged"}, perms=["tasks.write"],
              body={"ok": True, "task": {"id": "a1"}})
    assert out["calls"][0]["body"] == {"text": "call Paul", "due": "2026-10-23T09:00:00Z", "source": "app:today"}


def test_tasks_complete_refuses_path_tricks():
    out = run("tasks.complete", {"id": "../admin"}, perms=["tasks.write"])
    assert out["r"]["error"]["code"] == "bad_id" and out["calls"] == []


def test_calendar_and_email_marked_untrusted():
    out = run("calendar.upcoming", {"max_results": 500}, perms=["calendar.read"], body={"source": "ics", "events": [{"summary": "x"}]})
    assert out["calls"][0]["url"] == "/api/bf/integrations/calendar/events?max_results=50"
    assert out["r"]["result"]["trust"] == "untrusted"
    out = run("email.recent", {"unread_only": True}, perms=["email.read"], body={"messages": []})
    assert out["calls"][0]["url"].startswith("/api/bf/integrations/email/messages?") and "unread_only=true" in out["calls"][0]["url"]


def test_web_fetch_http_only():
    out = run("web.fetch", {"url": "file:///etc/passwd"}, perms=["network.outbound"])
    assert out["r"]["error"]["code"] == "bad_url" and out["calls"] == []


def test_files_save_goes_to_the_desk_and_reports_route():
    out = run("files.save", {"name": "a.txt", "text": "hi"}, perms=["files.write"], body={"ok": True, "path": "/home/x/out/2026-10-22/a.txt"})
    assert out["calls"][0]["url"] == "/cc/files/save"
    assert out["calls"][0]["body"] == {"name": "a.txt", "app": "today", "text": "hi"}
    assert out["r"]["result"]["route"] == "/files?path=%2Fhome%2Fx%2Fout%2F2026-10-22%2Fa.txt"


def test_files_save_without_cc_says_no_door():
    out = run("files.save", {"name": "a.txt", "text": "hi"}, perms=["files.write"], status=404)
    assert out["r"]["error"]["code"] == "no_files_door"


@pytest.mark.parametrize("route,ok", [
    ("/files?path=%2Fhome%2Fx", True), ("/tasks", True), ("/apps/clip", True),
    ("https://evil.example", False), ("//evil.example", False), ("/settings", False), ("/api/bf/apps/list", False),
])
def test_ui_open_only_console_screens(route, ok):
    out = run("ui.open", {"route": route})
    assert out["r"]["ok"] is ok
    assert out["nav"] == ([route] if ok else [])


def test_meta_theme_needs_no_permission():
    out = run("meta.theme")
    assert out["r"]["result"]["tokens"]["--bg"] == "#000"
