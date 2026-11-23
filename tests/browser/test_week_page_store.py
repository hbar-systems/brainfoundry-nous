"""tests/browser/test_week_page_store.py: a week page keeps its own choices across console loads (MEMBERS-13, 2026-11-23).

Why: a member's start page (week/index.html) runs inside the Week app, in a sandbox with no storage of its
own, so a page's language choice and "gift opened" were asked again after every console load (hbar
2026-11-23: Alexander's language choice not remembered, "APPROVED. ALSO ELENA SHOULD HAVE CHOICE TOO").
The Week app now gives the page an in-page store seeded from the app's own store (keys "page:<key>") and
keeps each write there; the host keeps the app's store per app (bridge storage.set, appLane shim).

This test runs the real Week app (brain-apps/shipped/week/index.html with the real appLane shim) in a
sandboxed frame of a small host page that does what ui/pages/apps/[id].js does for storage and files.read
(seed window.name, keep storage.set / storage.remove in its own localStorage), loads a page that stores a
choice, reloads the host, and checks the choice came back; and that a page cannot put more than the caps.

Skips without python playwright. Run:
  LD_LIBRARY_PATH=$HOME/.local/chromelibs/root/usr/lib/aarch64-linux-gnu \\
    /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser/test_week_page_store.py -q -p no:cacheprovider
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")

REPO = Path(__file__).resolve().parents[2]
WEEK = REPO / "brain-apps" / "shipped" / "week" / "index.html"
LIB = REPO / "ui" / "lib"

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>p</title></head><body>
<b id="v">?</b><button id="en">English</button><button id="big">big</button><button id="many">many</button>
<script>
var v=document.getElementById('v');v.textContent=localStorage.getItem('start-lang')||'none';
document.getElementById('en').onclick=function(){localStorage.setItem('start-lang','en');v.textContent='en'};
document.getElementById('big').onclick=function(){localStorage.setItem('huge',new Array(3000).join('x'))};
document.getElementById('many').onclick=function(){for(var i=0;i<80;i++)localStorage.setItem('k'+i,'1')};
</script></body></html>"""

HOST = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>
var APP = %(app)s, PAGE = %(page)s;
var store = JSON.parse(localStorage.getItem('st') || '{}');
var f = document.createElement('iframe');              // as the console renders it: name and sandbox first
f.id = 'f'; f.setAttribute('sandbox', 'allow-scripts'); f.style.cssText = 'width:800px;height:400px';
f.name = 'bf-app-storage:' + JSON.stringify(store);
f.srcdoc = APP;
document.body.appendChild(f);
function keep(){ localStorage.setItem('st', JSON.stringify(store)) }
window.asked = [];
window.addEventListener('message', function (e) {
  var m = e.data; if (e.source !== f.contentWindow || !m || !m.type || m.type === 'reply') return;
  var p = m.payload || {}, res = { ok: true, result: {} };
  if (m.type === 'storage.set') { store[p.key] = p.value; keep() }
  else if (m.type === 'storage.remove') { delete store[p.key]; keep() }
  else if (m.type === 'storage.clear') { store = {}; keep() }
  else if (m.type === 'files.read') res.result = { path: '/home/x/out/week/index.html', text: PAGE };
  else if (m.type === 'chat.ask') { window.asked.push(p.text); res.result = { placed: 'console' } }
  f.contentWindow.postMessage({ type: 'reply', request_id: m.request_id, ok: res.ok, result: res.result }, '*');
});
</script></body></html>"""


def _app_html() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", "const l=require('./appLane.js');process.stdout.write(l.injectShim(require('fs').readFileSync(process.argv[1],'utf8')))", str(WEEK)],
                       capture_output=True, text=True, cwd=str(LIB), timeout=30)
    assert r.returncode == 0, r.stderr
    assert "bf-app-storage:" in r.stdout
    return r.stdout


@pytest.fixture
def host_url():
    body = (HOST % {"app": json.dumps(_app_html()).replace("</", "<\\/"),
                    "page": json.dumps(PAGE).replace("</", "<\\/")}).encode()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


# chromium needs nss libs this box keeps in user space (no sudo); same place SKIN-2 points the login test at
LIBS = Path.home() / ".local/chromelibs/root/usr/lib/aarch64-linux-gnu"


def _launch(p):
    env = dict(os.environ)
    if LIBS.is_dir():
        env["LD_LIBRARY_PATH"] = f"{LIBS}:{env.get('LD_LIBRARY_PATH', '')}"
    return p.chromium.launch(args=["--no-sandbox"], env=env)


def _page_frame(pg):
    pg.wait_for_function("() => document.getElementById('f').contentWindow.frames.length > 0", timeout=10000)
    for fr in pg.frames:
        if fr.parent_frame and fr.parent_frame.parent_frame:      # host > Week app > page
            fr.wait_for_selector("#v", timeout=10000)
            return fr
    raise AssertionError("page frame not found")


def test_page_choice_survives_a_console_reload(host_url):
    with sync_api.sync_playwright() as p:
        b = _launch(p)
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(host_url)
        fr = _page_frame(pg)
        assert fr.inner_text("#v") == "none"
        fr.click("#en")
        pg.wait_for_function("() => (localStorage.getItem('st') || '').indexOf('page:start-lang') >= 0", timeout=5000)
        st = json.loads(pg.evaluate("localStorage.getItem('st')"))
        assert st == {"page:start-lang": "en"}
        pg.reload()                                             # the console loads again
        fr = _page_frame(pg)
        assert fr.inner_text("#v") == "en"
        # the caps: one value at most 2000 characters, at most 50 keys
        fr.click("#big")
        fr.click("#many")
        pg.wait_for_timeout(500)
        st = json.loads(pg.evaluate("localStorage.getItem('st')"))
        assert "page:huge" not in st
        assert len([k for k in st if k.startswith("page:")]) == 50
        assert errs == []
        b.close()
