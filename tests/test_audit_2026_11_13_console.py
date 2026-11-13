"""Audit 2026-11-13, batch 1: the paths from a crafted link or a saved page to the console's owner key.

google-oauth-callback-reflected-xss, onboarding-start-param-javascript-url-navigation,
app-files-save-html-runs-unsandboxed-on-console-origin, cc-reply-pane-marker-unvalidated-iframe-src.
(The console token is in tests/test_app_lane.py.)
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_google_callback_escapes_error_and_sandboxes_page():
    src = (ROOT / "api" / "main.py").read_text()
    m = re.search(r"    def _page\(title: str, body: str, ok: bool\) -> HTMLResponse:\n(.*?)\n\n", src, re.S)
    assert m, "the callback's _page helper moved"
    ns: dict = {}
    from starlette.responses import HTMLResponse
    exec("def _page(title: str, body: str, ok: bool) -> HTMLResponse:\n" + m.group(1), {"HTMLResponse": HTMLResponse}, ns)
    r = ns["_page"]("Google connection failed", "Google returned: <script>alert(1)</script>", False)
    body = r.body.decode()
    assert "<script" not in body and "&lt;script&gt;" in body
    assert r.headers["content-security-policy"].startswith("sandbox")
    assert r.headers["x-content-type-options"] == "nosniff"


def _safe_start():
    html = (ROOT / "ui" / "public" / "onboarding" / "index.html").read_text()
    m = re.search(r"function safeStart\(s\)\{.*?catch\(e\)\{return '';\}\}", html)
    assert m, "safeStart moved"
    return m.group(0)


@pytest.mark.parametrize("value,want", [
    ("javascript:alert(1)", ""), ("//evil.example/x", ""), ("https://evil.example", ""),
    ("/\\evil.example", ""), ("JaVaScRiPt:alert(1)", ""), ("", ""),
    ("/talk", "/talk"), ("/apps/daybook?x=1", "/apps/daybook?x=1"),
])
def test_onboarding_start_only_same_origin_paths(value, want):
    fn = _safe_start()
    got = _node("var location={href:'https://console.example/onboarding/',origin:'https://console.example'};"
                + fn + "console.log(JSON.stringify(safeStart(%s)))" % json.dumps(value))
    assert got == want


def test_onboarding_sink_rechecks():
    html = (ROOT / "ui" / "public" / "onboarding" / "index.html").read_text()
    assert "location.href=cfg.start" not in html
    assert "location.href=safeStart(cfg.start)" in html


def test_files_viewer_never_grants_same_origin_to_desk_html():
    js = (ROOT / "ui" / "pages" / "files.js").read_text()
    m = re.search(r"const VIEW_SANDBOX = '([^']*)'", js)
    assert m and "allow-same-origin" not in m.group(1) and "allow-scripts" in m.group(1)
    for frame in re.findall(r"<iframe[^>]*>", js):
        if "sel.kind === 'html'" in frame or "raw(sel.path)" in frame:
            assert "sandbox=" in frame, frame


def test_bridge_serves_desk_html_sandboxed(tmp_path):
    import cc_extras as X
    out = tmp_path / "out"; out.mkdir()
    (out / "p.html").write_text("<script>1</script>"); (out / "n.txt").write_text("hi")
    f = X.Files({"out": str(out)})

    class H:
        def __init__(self):
            self.headers = {}; self.sent = {}; self.wfile = io.BytesIO(); self.code = None
        def send_response(self, c): self.code = c
        def send_header(self, k, v): self.sent[k] = v
        def end_headers(self): pass

    h = H(); f.serve(h, str(out / "p.html"))
    assert h.code == 200 and h.sent.get("Content-Security-Policy", "").startswith("sandbox")
    assert "allow-same-origin" not in h.sent["Content-Security-Policy"]
    h2 = H(); f.serve(h2, str(out / "n.txt"))
    assert "Content-Security-Policy" not in h2.sent and h2.sent["X-Content-Type-Options"] == "nosniff"


def test_pane_marker_only_console_paths():
    js = (ROOT / "ui" / "pages" / "cc.js").read_text()
    m = re.search(r"function safePaneRoute\(r\) \{.*?\n\}", js, re.S)
    assert m
    cases = ["/files?path=/home/hands/out/x", "/apps/daybook", "javascript:alert(1)", "//evil.example",
             "/\\evil.example", "https://evil.example", "/x onload=1", ""]
    got = _node(m.group(0) + ";console.log(JSON.stringify(%s.map(safePaneRoute)))" % json.dumps(cases))
    assert got == ["/files?path=/home/hands/out/x", "/apps/daybook", None, None, None, None, None, None]
