"""The app lane (2026-10-16): a brain app cannot use the owner key.

Finding: installed apps ran in an iframe sandboxed with allow-same-origin, so app code shared the
console's origin; the /api/bf proxy adds BRAIN_API_KEY to every request and /api/cli-info hands the
key out. An app could read local-only memory (/documents/search include_local_only), chat history
(/sessions), call admin routes (/apps/install) and copy the owner key.

These tests run the real console code under node (ui/lib/appLane.js, ui/lib/appBridge.js, the
/api/bf proxy handler and /api/permit, /api/cli-info) and the cc-bridge's rule in Python. The browser
side (opaque origin, the nine installed apps loading through the shim) was checked in headless
Chromium on 2026-10-16; see THREAT_MODEL.md.

Run from repo root:
    pytest tests/test_app_lane.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIB = ROOT / "ui" / "lib"

# Headers a browser sends from an app frame (opaque origin) and from the console's own page.
FRAME = {"origin": "null", "sec-fetch-site": "cross-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty"}
CONSOLE = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty",
           "referer": "https://console.example/apps/poker-journal"}
# The pre-fix case: a frame that kept the console's origin (allow-same-origin) still names itself in
# the Referer; refused too, as a second line if the sandbox were ever undone.
SAME_ORIGIN_FRAME = {"sec-fetch-site": "same-origin", "referer": "https://console.example/api/bf/apps/poker-journal/index.html"}


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    return node


def _node_json(script: str, cwd: pathlib.Path = LIB, timeout: int = 30):
    r = subprocess.run([_node(), "-e", script], capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _decide(parts, method, headers):
    return _node_json("const l=require('./appLane.js');console.log(JSON.stringify(l.decide(%s,%s,%s)))"
                      % (json.dumps(parts), json.dumps(method), json.dumps(headers)))


# ---- the proxy's rule (ui/lib/appLane.js decide) ----

CORE_ROUTES = [
    (["documents", "search"], "POST"),
    (["sessions"], "GET"),
    (["sessions", "abc", "messages"], "GET"),
    (["apps", "install"], "POST"),           # admin: install an app
    (["apps", "list"], "GET"),
    (["apps", "poker-journal", "uninstall"], "POST"),
    (["settings", "model"], "GET"),
    (["memory", "append"], "POST"),
    (["chat", "rag"], "POST"),
    (["documents", "search"], "OPTIONS"),    # a preflight gets nothing either
]


def test_app_frame_core_routes_refused():
    cases = [(parts, method, headers) for parts, method in CORE_ROUTES
             for headers in (FRAME, SAME_ORIGIN_FRAME, {"origin": "null"}, {"sec-fetch-site": "same-site"})]
    out = _node_json("const l=require('./appLane.js');console.log(JSON.stringify(%s.map(c=>l.decide(c[0],c[1],c[2]))))"
                     % json.dumps(cases))
    for case, d in zip(cases, out):
        assert d == {"action": "refuse", "status": 403, "error": "app_frame_refused"}, (case, d)


def test_console_page_and_cli_keep_owner_authority():
    for headers in (CONSOLE, {}, {"sec-fetch-site": "none"}):
        d = _decide(["documents", "search"], "POST", headers)
        assert d["action"] == "forward" and d["ownerKey"] is True and d["cors"] is False


def test_app_static_files_served_without_owner_key():
    for headers in (FRAME, CONSOLE):
        for method in ("GET", "HEAD"):
            d = _decide(["apps", "poker-journal", "assets", "index.js"], method, headers)
            assert d["action"] == "forward" and d["ownerKey"] is False and d["appFile"] is True
    assert _decide(["apps", "poker-journal", "index.html"], "GET", FRAME)["cors"] is True


def test_app_backend_from_frame_goes_without_owner_key():
    d = _decide(["apps", "poker-journal", "api", "hands"], "POST", FRAME)
    assert d["action"] == "forward" and d["ownerKey"] is False and d["cors"] is True and d["appFile"] is False


def test_paths_that_climb_out_are_refused():
    for parts in (["apps", "x1", "..", "..", "documents", "search"], ["apps", "poker-journal", "."],
                  ["apps", "poker-journal", "a/../../sessions"], ["apps", "poker-journal", ""]):
        assert _decide(parts, "GET", FRAME)["action"] == "refuse"


def test_non_get_to_app_path_is_core():
    # POST apps/<id>/index.html is not a file read; from a frame it is refused like any core route.
    assert _decide(["apps", "poker-journal", "index.html"], "POST", FRAME)["action"] == "refuse"


# ---- the shim and the iframe ----

def test_inject_shim_first_in_head_and_module_scripts_carry_login():
    html = ('<!doctype html><html><head><meta charset="utf-8"><script type="module" crossorigin src="/a.js"></script>'
            '<link rel="stylesheet" crossorigin href="/a.css"><script type="module" src="/b.js"></script>'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            '<script type="module" crossorigin src="https://cdn.example/x.js"></script></head><body></body></html>')
    out = _node_json("const l=require('./appLane.js');console.log(JSON.stringify(l.injectShim(%s)))" % json.dumps(html))
    assert out.index("<script data-bf-app-shim>") == out.index("<head>") + len("<head>")
    assert out.count('crossorigin="use-credentials"') == 3
    assert ' crossorigin src="/a.js"' not in out and ' crossorigin href="/a.css"' not in out
    # another host keeps its anonymous CORS (a CDN with "*" refuses credentials)
    assert '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' in out
    assert '<script type="module" crossorigin src="https://cdn.example/x.js">' in out


def test_shim_gives_storage_in_an_opaque_origin():
    """Run the shim in a window whose localStorage getter throws (what an opaque origin does)."""
    script = r"""
const vm = require('vm'); const l = require('./appLane.js')
const posted = []
const win = { name: 'bf-app-storage:' + JSON.stringify({ a: '1' }), location: { protocol: 'https:', host: 'console.example', href: 'https://console.example/api/bf/apps/app1/index.html' },
  parent: { postMessage: (m, t) => posted.push([m, t]) } }
Object.defineProperty(win, 'localStorage', { get() { throw new Error('SecurityError') }, configurable: true })
win.window = win; win.URL = URL; win.JSON = JSON; win.Object = Object; win.Math = Math; win.String = String
vm.createContext(win); vm.runInContext(l.SHIM_JS, win)
const ls = vm.runInContext('localStorage', win)
const before = ls.getItem('a'); ls.setItem('b', '2'); ls.removeItem('a')
console.log(JSON.stringify({ before, b: ls.getItem('b'), a: ls.getItem('a'), len: ls.length, name: win.name,
  posted: posted.map(([m, t]) => [m.type, m.payload, t]) }))
"""
    out = _node_json(script)
    assert out["before"] == "1" and out["b"] == "2" and out["a"] is None and out["len"] == 1
    assert out["name"] == ""          # the seed is cleared once read
    assert out["posted"] == [["storage.set", {"key": "b", "value": "2"}, "*"], ["storage.remove", {"key": "a"}, "*"]]


def test_iframe_has_no_allow_same_origin():
    src = (ROOT / "ui" / "pages" / "apps" / "[id].js").read_text()
    assert "sandbox={APP_SANDBOX}" in src
    assert not re.search(r'sandbox="[^"]*allow-same-origin', src)
    sandbox = _node_json("console.log(JSON.stringify(require('./appLane.js').APP_SANDBOX))")
    flags = set(sandbox.split())
    assert "allow-scripts" in flags
    assert not flags & {"allow-same-origin", "allow-forms", "allow-popups", "allow-top-navigation",
                        "allow-top-navigation-by-user-activation", "allow-modals"}
    csp = _node_json("console.log(JSON.stringify(require('./appLane.js').APP_CSP))")
    assert csp == "sandbox " + sandbox


# ---- the real proxy handler, end to end under node ----

PROXY_SCRIPT = r"""
const http = require('http')
const seen = []
const up = http.createServer((req, res) => {
  seen.push({ method: req.method, url: req.url, key: req.headers['x-api-key'] || null, auth: req.headers['authorization'] || null })
  if (req.url.startsWith('/apps/app1/')) {
    if (req.url.endsWith('.html')) { res.setHeader('content-type', 'text/html'); return res.end('<html><head><title>a</title></head><body>app</body></html>') }
    res.setHeader('content-type', 'text/javascript'); return res.end('console.log(1)')
  }
  res.setHeader('content-type', 'application/json'); res.end(JSON.stringify({ secret: 'local-only' }))
})
up.listen(0, '127.0.0.1', async () => {
  process.env.API_INTERNAL_URL = 'http://127.0.0.1:' + up.address().port
  process.env.BRAIN_API_KEY = 'OWNER-KEY'
  const mod = await import(process.argv[2])
  const { Readable } = require('stream')
  async function call(path, method, headers) {
    const req = Readable.from([])
    req.method = method; req.url = '/api/bf/' + path.join('/'); req.headers = headers; req.query = { path }
    return await new Promise(resolve => {
      const out = { status: 200, headers: {}, body: '' }
      const res = {
        status(s) { out.status = s; return res }, setHeader(k, v) { out.headers[k.toLowerCase()] = v },
        json(o) { out.body = JSON.stringify(o); resolve(out) }, send(b) { out.body = Buffer.from(b).toString(); resolve(out) },
        end(b) { if (b) out.body = String(b); resolve(out) }, write() {},
      }
      mod.default(req, res)
    })
  }
  const FRAME = %(frame)s, CONSOLE = %(console)s
  const r = {}
  r.search = await call(['documents', 'search'], 'POST', { ...FRAME, 'content-type': 'text/plain' })
  r.sessions = await call(['sessions'], 'GET', FRAME)
  r.admin = await call(['apps', 'install'], 'POST', { ...FRAME, 'content-type': 'text/plain', authorization: 'Basic b3A6cHc=' })
  r.preflight = await call(['documents', 'search'], 'OPTIONS', { ...FRAME, 'access-control-request-method': 'POST' })
  r.file = await call(['apps', 'app1', 'index.html'], 'GET', { ...FRAME, authorization: 'Basic b3A6cHc=' })
  r.asset = await call(['apps', 'app1', 'main.js'], 'GET', FRAME)
  r.console = await call(['sessions'], 'GET', CONSOLE)
  console.log(JSON.stringify({ r, seen }))
  up.close()
})
"""


def _script(tmp_path, text: str) -> str:
    """A script file, not node -e: dynamic import() from an -e script segfaults node 18 now and then."""
    f = tmp_path / "run.cjs"
    f.write_text(text)
    return str(f)


def _esm_copy(tmp_path, rel: str, name: str) -> pathlib.Path:
    """The handlers are ES modules Next compiles; node needs .mjs and an absolute lib path."""
    src = (ROOT / "ui" / "pages" / rel).read_text()
    src = re.sub(r"""from ['"](?:\.\./)+lib/(\w+)['"]""", lambda m: f"from '{LIB / (m.group(1) + '.js')}'", src)
    dst = tmp_path / name
    dst.write_text(src)
    return dst


def test_proxy_refuses_app_frame_and_serves_app_files(tmp_path):
    proxy = _esm_copy(tmp_path, "api/bf/[...path].js", "proxy.mjs")
    script = PROXY_SCRIPT % {"frame": json.dumps(FRAME), "console": json.dumps(CONSOLE)}
    r = subprocess.run([_node(), _script(tmp_path, script), str(proxy)], capture_output=True, text=True, timeout=30, cwd=str(LIB))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    res, seen = out["r"], out["seen"]
    for k in ("search", "sessions", "admin", "preflight"):
        assert res[k]["status"] == 403 and json.loads(res[k]["body"]) == {"error": "app_frame_refused"}, k
    # nothing from the frame reached a core route upstream
    assert [s["url"] for s in seen] == ["/apps/app1/index.html", "/apps/app1/main.js", "/sessions"]
    # app files went without the owner key and without the caller's login
    assert seen[0]["key"] is None and seen[0]["auth"] is None and seen[1]["key"] is None
    assert res["file"]["status"] == 200 and res["asset"]["status"] == 200
    assert res["file"]["headers"]["content-security-policy"] == "sandbox allow-scripts allow-downloads"
    assert res["file"]["headers"]["access-control-allow-origin"] == "null"
    assert res["file"]["body"].startswith("<html><head><script data-bf-app-shim>")
    assert res["asset"]["body"] == "console.log(1)"
    # the console's own page still has owner authority
    assert seen[2]["key"] == "OWNER-KEY" and res["console"]["status"] == 200


HANDLER_SCRIPT = r"""
(async () => {
  const mod = await import(process.argv[2])
  const out = await new Promise(resolve => {
    const res = { status(s) { this.s = s; return this }, json(o) { resolve({ status: this.s, body: o }) }, end() { resolve({ status: this.s }) }, setHeader() {} }
    mod.default({ method: process.argv[3], headers: JSON.parse(process.argv[4]), body: {} }, res)
  })
  console.log(JSON.stringify(out))
})()
"""


@pytest.mark.parametrize("rel,method", [("api/cli-info.js", "GET"), ("api/permit.js", "POST"), ("api/proposal-decide.js", "POST")])
def test_console_api_routes_refuse_app_frame(tmp_path, rel, method):
    h = _esm_copy(tmp_path, rel, pathlib.Path(rel).stem + ".mjs")
    r = subprocess.run([_node(), _script(tmp_path, HANDLER_SCRIPT), str(h), method, json.dumps(FRAME)],
                       capture_output=True, text=True, timeout=30, cwd=str(LIB), env={"BRAIN_API_KEY": "OWNER-KEY", "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out == {"status": 403, "body": {"error": "app_frame_refused"}}
    assert "OWNER-KEY" not in r.stdout


def test_cli_info_still_answers_the_console(tmp_path):
    h = _esm_copy(tmp_path, "api/cli-info.js", "cli-info.mjs")
    r = subprocess.run([_node(), _script(tmp_path, HANDLER_SCRIPT), str(h), "GET", json.dumps(CONSOLE)],
                       capture_output=True, text=True, timeout=30, cwd=str(LIB), env={"BRAIN_API_KEY": "OWNER-KEY", "PATH": "/usr/bin:/bin"})
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["status"] == 200 and out["body"]["api_key"] == "OWNER-KEY"


# ---- the bridge (ui/lib/appBridge.js) ----

BRIDGE_SCRIPT = r"""
const b = require('./appBridge.js')
const calls = []
const fetch = async (url, opts) => {
  calls.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null })
  const json = url === '/api/bf/settings/model' ? { active: 'm1' }
    : url === '/api/permit' ? { permit_id: 'p', permit_token: 't' }
    : url === '/api/bf/chat/rag' ? { model: 'm1', choices: [{ message: { content: 'hi' } }], rag_metadata: { sources: [{ document: 'open.md' }] } }
    : { id: 1, doc_name: 'd.md', privacy: 'open' }
  return { ok: true, status: 200, json: async () => json }
}
const mem = {}; const ls = { get length() { return Object.keys(mem).length }, key: i => Object.keys(mem)[i], getItem: k => k in mem ? mem[k] : null, setItem: (k, v) => { mem[k] = String(v) } }
ls.setItem('hbar-ink-drops-v8', '[1]'); ls.setItem('cc.hidden', '{}'); ls.setItem('daybook:x', 'y')
const llmApp = { id: 'oracle', name: 'Oracle', version: '1', permissions: ['llm.invoke'], requires_layers: [{ layer: 'semantic', mode: 'read' }] }
const inkApp = { id: 'hbar-ink', name: 'ink', version: '1', permissions: ['memory.write'], requires_layers: [{ layer: 'episodic', mode: 'append' }] }
;(async () => {
  const o = b.makeBridge({ appInfo: llmApp, fetch, ls, brainName: 'hbar' })
  const r = {}
  r.llm = await o.handleIntent({ type: 'llm.complete', payload: { messages: [{ role: 'user', content: 'q' }], session_id: 's1', include_local_only: true, layers: ['episodic'], max_tokens: 4000 } })
  r.llmCalls = calls.splice(0)
  r.writeUndeclared = await o.handleIntent({ type: 'memory.write', payload: { layer: 'episodic', content: 'x' } })
  r.read = await o.handleIntent({ type: 'memory.read', payload: { layer: 'semantic', query: 'q' } })
  r.callsAfterRefusals = calls.length
  const ink = b.makeBridge({ appInfo: inkApp, fetch, ls, brainName: 'hbar' })
  r.inkStore = ink.store
  r.writeOtherLayer = await ink.handleIntent({ type: 'memory.write', payload: { layer: 'semantic', content: 'x' } })
  r.write = await ink.handleIntent({ type: 'memory.write', payload: { layer: 'episodic', content: 'x', privacy: 'local-only' } })
  r.writeCall = calls.splice(0)
  r.llmUndeclared = await ink.handleIntent({ type: 'llm.complete', payload: { messages: [{ role: 'user', content: 'q' }] } })
  await ink.handleIntent({ type: 'storage.set', payload: { key: 'hbar-ink-theme', value: 'dark' } })
  r.saved = JSON.parse(mem['bf.app-storage.hbar-ink'])
  r.oracleStore = JSON.parse(mem['bf.app-storage.oracle'])
  const frame = {}, other = {}
  r.accept = [b.acceptMessage({ source: frame, data: { type: 'ping', request_id: '1' } }, frame),
              b.acceptMessage({ source: other, data: { type: 'ping', request_id: '1' } }, frame),
              b.acceptMessage({ source: frame, data: { type: 'reply', request_id: '1' } }, frame),
              b.acceptMessage({ source: frame, data: { type: 'ping' } }, frame)]
  console.log(JSON.stringify(r))
})()
"""


def test_bridge_declared_intent_works_undeclared_refused():
    r = _node_json(BRIDGE_SCRIPT)
    assert r["llm"] == {"ok": True, "result": {"text": "hi", "model": "m1", "sources": [{"document": "open.md"}]}}
    urls = [c["url"] for c in r["llmCalls"]]
    assert urls == ["/api/bf/settings/model", "/api/permit", "/api/bf/chat/rag"]
    permit, rag = r["llmCalls"][1]["body"], r["llmCalls"][2]["body"]
    # the permit is attributed to the app, so /chat/rag gives it the open view only
    assert permit["agent_id"] == "app:oracle"
    # the body is built from fixed fields: the app's session_id / include_local_only / layers do not pass
    assert set(rag) == {"model", "messages", "permit_id", "permit_token", "max_tokens", "layers"}
    assert rag["layers"] == ["semantic"] and rag["max_tokens"] == 4000
    assert r["writeUndeclared"]["error"]["code"] == "permission_denied"
    assert r["read"]["error"]["code"] == "unknown_intent"       # no memory read intent exists
    assert r["callsAfterRefusals"] == 0
    assert r["writeOtherLayer"]["error"]["code"] == "layer_not_declared"
    assert r["write"] == {"ok": True, "result": {"id": 1, "doc_name": "d.md", "privacy": "open"}}
    assert r["writeCall"][0]["url"] == "/api/bf/memory/append" and r["writeCall"][0]["body"]["privacy"] == "local-only"
    assert r["llmUndeclared"]["error"]["code"] == "permission_denied"


def test_bridge_storage_is_per_app_and_migrates_only_known_keys():
    r = _node_json(BRIDGE_SCRIPT)
    # first load copied the app's own legacy key out of the console's storage; cc.* and daybook:* stayed
    assert r["inkStore"] == {"hbar-ink-drops-v8": "[1]", "hbar-ink-theme": "dark"}
    assert r["saved"] == {"hbar-ink-drops-v8": "[1]", "hbar-ink-theme": "dark"}
    assert r["oracleStore"] == {}          # no console keys, no other app's keys
    assert r["accept"] == [True, False, False, False]


# ---- the cc bridge (scripts/cc/cc-bridge.py) ----

def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    spec = importlib.util.spec_from_file_location("cc_bridge_lane", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_lane"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cc_bridge_refuses_app_frames(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    H = lambda d: {k.title(): v for k, v in d.items()}   # http.server headers are case-insensitive; dict here
    assert m.foreign_page(H(FRAME), "POST") is True
    assert m.foreign_page(H(FRAME), "GET") is True
    assert m.foreign_page(H(SAME_ORIGIN_FRAME), "GET") is True
    assert m.foreign_page(H(CONSOLE), "POST") is False
    assert m.foreign_page({}, "POST") is False            # box processes (hooks, cc-job) send none
    # a link opened in a new top-level tab is a navigation, not a page acting on the bridge
    nav = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
    assert m.foreign_page(nav, "GET") is False and m.foreign_page(nav, "POST") is True
    # an app frame navigating itself is dest iframe: refused
    assert m.foreign_page({**nav, "Sec-Fetch-Dest": "iframe"}, "GET") is True


def test_terminal_checks_origin():
    unit = (ROOT / "scripts" / "cc" / "install.sh").read_text()
    line = next(l for l in unit.splitlines() if l.startswith("ExecStart=/usr/bin/ttyd"))
    assert " -O " in line
