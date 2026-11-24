"""Working pages on the console origin (2026-11-16, COURT-8): /cc/page/<name>/ serves a brain-built page
(the court) without the sandbox the 2026-11-13 audit put on every desk HTML file, so it can read its
state.json and post rulings to /cc/chat; only names on the list, only the fixed file per name, only
siblings from its own folder; desk HTML under /cc/files/raw stays sandboxed."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))

import cc_extras as X  # noqa: E402


class _H:
    def __init__(self):
        self.headers = {}; self.sent = {}; self.wfile = io.BytesIO(); self.code = None
    def send_response(self, c): self.code = c
    def send_header(self, k, v): self.sent[k] = v
    def end_headers(self): pass


def _desk(tmp_path):
    out = tmp_path / "out"
    (out / "court" / "d").mkdir(parents=True)
    (out / "court" / "index.html").write_text("<script>fetch('state.json')</script>")
    (out / "court" / "state.json").write_text('{"session": {"id": "s3"}}')
    (out / "court" / "stats.html").write_text("<script>1</script>")
    (out / "court" / "d" / "x.json").write_text("{}")
    (out / "court" / ".hidden").write_text("no")
    (out / "secret").mkdir()
    (out / "secret" / "k.txt").write_text("key")
    (out / "court" / "out.json").symlink_to(out / "secret" / "k.txt")
    (out / "notlisted").mkdir()
    (out / "notlisted" / "index.html").write_text("<p>x</p>")
    return out


def test_allowlist_names_and_fixed_files(tmp_path):
    out = _desk(tmp_path)
    pg = X.Pages(out, names=("court",))
    assert pg.path("court") == (out / "court" / "index.html").resolve()
    assert pg.path("court", "state.json") == (out / "court" / "state.json").resolve()
    for name in ("notlisted", "secret", "Court", "", "..", "court/..", "../court", "court%2f.."):
        assert pg.path(name) is None, name
    for sub in ("../secret/k.txt", "d/x.json", "d", ".hidden", "out.json", "/etc/passwd", "%2e%2e", "..", "nope.json"):
        assert pg.path("court", sub) is None, sub


def test_default_list_and_env(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_PAGES", raising=False)
    assert "court" in X.Pages(tmp_path).names
    monkeypatch.setenv("CC_PAGES", "court, week ,bad/name,../x")
    assert X.Pages(tmp_path).names == ("court", "week")


def test_page_served_without_sandbox_sibling_html_keeps_it(tmp_path):
    out = _desk(tmp_path)
    pg = X.Pages(out, names=("court",))
    h = _H(); pg.serve(h, "court", "")
    assert h.code == 200 and h.sent["Content-Type"].startswith("text/html")
    assert "sandbox" not in h.sent["Content-Security-Policy"] and "frame-ancestors 'self'" in h.sent["Content-Security-Policy"]
    assert h.wfile.getvalue().startswith(b"<script>fetch")
    h = _H(); pg.serve(h, "court", "state.json")
    assert h.code == 200 and h.sent["Content-Type"].startswith("application/json")
    assert "sandbox" not in h.sent.get("Content-Security-Policy", "")
    h = _H(); pg.serve(h, "court", "stats.html")
    assert h.code == 200 and h.sent["Content-Security-Policy"].startswith("sandbox") and "allow-same-origin" not in h.sent["Content-Security-Policy"]
    h = _H(); pg.serve(h, "nope", "")
    assert h.code == 404


# ---------------------------------------------------------------- through the real bridge ----

def _bridge(monkeypatch, tmp_path, token="tok"):
    fake = tmp_path / "fake-claude"
    fake.write_text('''#!/usr/bin/env python3
import json
def p(o): print(json.dumps(o), flush=True)
p({"type": "system", "subtype": "init", "model": "claude-x", "session_id": "s9"})
p({"type": "result", "result": "rule d-1 yes: logged", "session_id": "s9", "is_error": False, "num_turns": 1, "usage": {"input_tokens": 1, "output_tokens": 1}, "modelUsage": {}})
''')
    fake.chmod(0o755)
    out = _desk(tmp_path)
    monkeypatch.setenv("CC_BIN", str(fake))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_HANDS_HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_PAGES", "court")
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location("cc_bridge_pages", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "_brain_api", lambda method, path, body=None: {"session_id": "t-court"} if path == "/sessions" else {})
    assert m.OUT_DIR == out
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return m, srv, f"http://127.0.0.1:{srv.server_address[1]}/cc"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


SAME = {"X-CC-Operator": "tok", "Sec-Fetch-Site": "same-origin"}


def test_route_serves_court_reads_state_and_refuses_the_rest(monkeypatch, tmp_path):
    m, srv, base = _bridge(monkeypatch, tmp_path)
    try:
        nav = {"X-CC-Operator": "tok", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        st, h, body = _get(base + "/page/court/", nav)
        assert st == 200 and h["Content-Type"].startswith("text/html") and "sandbox" not in h.get("Content-Security-Policy", "")
        st, h, _ = _get(base + "/page/court?start=1", nav)
        assert st == 301 and h["Location"] == "/cc/page/court/?start=1"
        # the page's own relative fetch, same origin
        st, h, body = _get(base + "/page/court/state.json?t=1", SAME)
        assert st == 200 and json.loads(body)["session"]["id"] == "s3"
        # unknown names, paths in the name or the file, dot files, folders
        for p in ("/page/notlisted/", "/page/secret/k.txt", "/page/court/d/x.json", "/page/court/..%2fsecret%2fk.txt",
                  "/page/court/.hidden", "/page/court/out.json", "/page/..%2fsecret/", "/page/", "/page", "/page/court/d"):
            assert _get(base + p, SAME)[0] == 404, p
        # behind the console login: no operator token, no page
        assert _get(base + "/page/court/", {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})[0] == 403
        # an opaque-origin frame is still refused
        assert _get(base + "/page/court/state.json", {"X-CC-Operator": "tok", "Origin": "null"})[0] == 403
        # desk html under /cc/files/raw keeps the audit's sandbox
        st, h, _ = _get(base + "/files/raw" + str(tmp_path / "out" / "court" / "index.html"), nav)
        assert st == 200 and h["Content-Security-Policy"].startswith("sandbox") and "allow-same-origin" not in h["Content-Security-Policy"]
    finally:
        srv.shutdown()


def test_court_page_posts_a_ruling_from_the_new_route(monkeypatch, tmp_path):
    m, srv, base = _bridge(monkeypatch, tmp_path)
    try:
        origin = base.rsplit("/cc", 1)[0]
        body = json.dumps({"message": "rule d-1 yes --page --seconds 4", "queue": True, "new": True}).encode()
        req = urllib.request.Request(base + "/chat", data=body, method="POST", headers={
            "Content-Type": "application/json", "X-CC-Operator": "tok", "Origin": origin,
            "Sec-Fetch-Site": "same-origin", "Referer": base + "/page/court/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            assert r.status in (200, 202)
        # the same post from the sandboxed raw copy (Origin null) is what broke on 2026-11-13
        req = urllib.request.Request(base + "/chat", data=body, method="POST", headers={
            "Content-Type": "application/json", "X-CC-Operator": "tok", "Origin": "null", "Sec-Fetch-Site": "cross-site"})
        try:
            urllib.request.urlopen(req, timeout=30)
            raise AssertionError("an opaque origin post went through")
        except urllib.error.HTTPError as e:
            assert e.code == 403
    finally:
        srv.shutdown()


def test_film_page_listed_and_serves_its_draft(monkeypatch, tmp_path):
    """FILM-PAGE-1 (2026-11-18): the film page is a working page; its draft.json and state.json are siblings it can
    read; a sibling html keeps the sandbox; nothing below its folder (film working folders) is served from here."""
    monkeypatch.delenv("CC_PAGES", raising=False)
    out = tmp_path / "out"
    (out / "film" / "k2" / "footage").mkdir(parents=True)
    (out / "film" / "index.html").write_text("<script>fetch('state.json')</script>")
    (out / "film" / "draft.json").write_text('{"fragments": []}')
    (out / "film" / "state.json").write_text('{"film": null}')
    (out / "film" / "v1.html").write_text("<p>v1</p>")
    (out / "film" / "k2" / "footage" / "a.mp4").write_bytes(b"x")
    pg = X.Pages(out)
    assert "film" in pg.names
    assert pg.path("film") == (out / "film" / "index.html").resolve()
    assert pg.path("film", "draft.json") == (out / "film" / "draft.json").resolve()
    for sub in ("k2", "k2/footage/a.mp4", "../film/draft.json", ".draft.json.tmp"):
        assert pg.path("film", sub) is None, sub
    h = _H(); pg.serve(h, "film", "draft.json")
    assert h.code == 200 and h.sent["Content-Type"].startswith("application/json")
    h = _H(); pg.serve(h, "film", "v1.html")
    assert "sandbox" in h.sent["Content-Security-Policy"]


def test_rooms_page_serves_each_track_room_on_the_console_origin(monkeypatch, tmp_path):
    """ART-1 (2026-11-23): /cc/page/rooms/<track>/ is a track's room (K2, Control) on the console origin, so it reads
    the console skin; its media stays under /cc/files/raw (two folders down is never served from here)."""
    monkeypatch.delenv("CC_PAGES", raising=False)
    out = tmp_path / "out"
    (out / "rooms" / "k2" / "media").mkdir(parents=True)
    (out / "rooms" / "index.html").write_text("<p>rooms</p>")
    (out / "rooms" / "skins.css").write_text(":root{}")
    (out / "rooms" / "k2" / "index.html").write_text("<script>localStorage.getItem('bf-theme')</script>")
    (out / "rooms" / "k2" / "media" / "a.mp3").write_bytes(b"x")
    pg = X.Pages(out)
    assert "rooms" in pg.names
    assert pg.path("rooms", "k2/") == (out / "rooms" / "k2" / "index.html").resolve()
    assert pg.path("rooms", "skins.css") == (out / "rooms" / "skins.css").resolve()
    assert pg.path("rooms", "k2/media/a.mp3") is None and pg.path("rooms", "k2/media") is None
    h = _H(); pg.serve(h, "rooms", "k2/")
    assert h.code == 200 and "sandbox" not in h.sent.get("Content-Security-Policy", "")
