"""tests/browser/test_console_login.py: the console login, in a real browser (2026-11-05, E11).

Why: on 2026-11-03 two member consoles stopped letting people in (the basic-auth password did not
match the hash in the box's Caddyfile, or the username was wrong) and people found it first. Curl and
syntax checks never run a login. This test does, end to end, on this machine:

    Chromium (Playwright) -> caddy (the console block add-member.sh prints, real basicauth)
                          -> the built console (next standalone server.js)
                          -> a fake api + bridge (this file; answers the calls the chat page makes)

and checks: without credentials the login challenge is served (401 + Basic); with the right username
and password the chat page loads (composer enabled, "Ask your brain") with no script error; with a
staged break (wrong hash, wrong-case username, console process down) the login check reports problems.

Skips, so the normal suite (scripts/test-gate.sh) stays as it is, when any of these is missing:
  - python playwright (a user venv: /home/hands/.local/venvs/nous-browser has playwright 1.63.0 (the release whose browsers.json names chromium 1243) +
    pytest; browsers cached in ~/.cache/ms-playwright, chromium-1243),
  - caddy on PATH,
  - a console build: NOUS_CONSOLE_BUILD=<a ui/ dir after `npm ci && npm run build`>, default ui/ here.
    The ui/Dockerfile copy step (.next/static and public into .next/standalone) is done here if missing.

Run (green):
  NOUS_CONSOLE_BUILD=/tmp/e11-ui/ui LD_LIBRARY_PATH=$HOME/.local/chromelibs/root/usr/lib/aarch64-linux-gnu \
    /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser -q -p no:cacheprovider
Stage a break on the same login test (must go red):
  E11_STAGE_BREAK=hash_mismatch|username_case|console_down  ...same command...
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="python playwright not installed (browser tests)")

REPO = Path(__file__).resolve().parents[2]
ADD_MEMBER = REPO / "scripts" / "add-member.sh"
HANDLE = "probe"
PASSWORD = "e11-local-only-not-a-member-password"
BREAKS = ("hash_mismatch", "username_case", "console_down")

CADDY = shutil.which("caddy")
BUILD = Path(os.environ.get("NOUS_CONSOLE_BUILD", str(REPO / "ui")))
SERVER_JS = BUILD / ".next" / "standalone" / "server.js"

pytestmark = [
    pytest.mark.skipif(not CADDY, reason="caddy not on PATH"),
    pytest.mark.skipif(not SERVER_JS.exists(), reason=f"no console build at {BUILD} (npm ci && npm run build)"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, timeout: float = 30.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"nothing listening on 127.0.0.1:{port} after {timeout}s")


# ---------- fake api + bridge: just enough for the chat page to load as on a fresh member brain ----------

FAKE = {
    "/apps/list": {"apps": [], "ccHome": True},
    "/onboarding/first-use": {"steps": [], "complete": True, "fresh": False},
    "/onboarding/welcome": {"seen_version": 999},
    "/cc/health": {"ok": True, "auth": {"loggedIn": True}, "runs": [], "brain_session_id": None, "cards_waiting": 0},
    "/cc/permits": {"pending": [], "auto": []},
    "/cc/threads": {"threads": []},
    "/cc/agents": {"agents": []},
    "/cc/layout": {},
    "/cc/usage": {},
    "/cc/files/recent": {"files": []},
    "/cc/learn/due": {"due": []},
    "/cc/voices": {"voices": []},
    "/cc/login/state": {"loggedIn": True},
}


class FakeBackend(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):  # quiet
        pass

    def _answer(self):
        path = self.path.split("?", 1)[0]
        FakeBackend.seen.append((self.command, path))
        if path.startswith("/cc/") and path.endswith("/stream") or path == "/cc/live":
            body, ctype = b"", "text/event-stream"
        elif path == "/claude/throws":   # a page whose script throws: proves the error channel is live
            body, ctype = (b"<!doctype html><title>t</title><textarea placeholder='Ask your brain'></textarea>"
                           b"<script>null.boom()</script>"), "text/html"
        else:
            body, ctype = json.dumps(FAKE.get(path, {})).encode(), "application/json"
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_HEAD = _answer


# ---------- the Caddyfile: add-member.sh's own console block, ports and hash filled in ----------

def console_block(*, user: str, hash_line: str, console_port: int, api_front_port: int,
                  backend_port: int, ui_port: int) -> str:
    """Extract the heredoc add-member.sh prints for the operator and fill it the way the operator does.
    If the template changes shape this raises, so the test follows the shipped block, never a copy."""
    text = ADD_MEMBER.read_text()
    m = re.search(r"cat <<CADDY\n(.*?)\nCADDY\n", text, re.S)
    assert m, "add-member.sh no longer prints a CADDY heredoc; update this test with it"
    block = m.group(1)
    placeholder = "$HANDLE <hash of the member's console password: caddy hash-password>"
    assert placeholder in block, "the basicauth placeholder line in add-member.sh changed; update this test"
    block = block.replace(placeholder, f"{user} {hash_line}")
    block = block.replace("console.$HANDLE.brainfoundry.ai {", f"http://127.0.0.1:{console_port} {{")
    block = block.replace("$HANDLE.brainfoundry.ai {", f"http://127.0.0.1:{api_front_port} {{")
    block = block.replace("{\\$$TOKEN_VAR}", "{$E11_FAKE_OPERATOR_TOKEN}")
    for var in ("$M_API_PORT", "$M_TERM_PORT", "$M_CC_PORT"):
        block = block.replace(var, str(backend_port))
    block = block.replace("$M_UI_PORT", str(ui_port))
    assert "$" not in block.replace("{$E11_FAKE_OPERATOR_TOKEN}", "").replace(hash_line, ""), \
        f"unfilled variable in block:\n{block}"
    return "{\n\tadmin off\n\tauto_https off\n}\n\n" + block + "\n"


def caddy_hash(password: str) -> str:
    out = subprocess.run([CADDY, "hash-password", "--plaintext", password], check=True,
                         capture_output=True, text=True).stdout.strip()
    assert out.startswith("$2"), out
    return out


class Stack:
    """Caddy + console + fake backend on free localhost ports. `breaks` stages one failure."""

    def __init__(self, tmp: Path, breaks: str | None = None):
        assert breaks in (None, *BREAKS), breaks
        self.tmp, self.breaks, self.procs = tmp, breaks, []
        self.console_port, self.api_front, self.backend_port, self.ui_port = (free_port() for _ in range(4))
        self.url = f"http://127.0.0.1:{self.console_port}"

    def start(self) -> "Stack":
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.backend_port), FakeBackend)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

        standalone = SERVER_JS.parent
        if not (standalone / ".next" / "static").exists():          # ui/Dockerfile's copy step
            shutil.copytree(BUILD / ".next" / "static", standalone / ".next" / "static")
        if (BUILD / "public").exists() and not (standalone / "public").exists():
            shutil.copytree(BUILD / "public", standalone / "public")
        if self.breaks != "console_down":
            env = {**os.environ, "PORT": str(self.ui_port), "HOSTNAME": "127.0.0.1",
                   "API_INTERNAL_URL": f"http://127.0.0.1:{self.backend_port}", "NODE_ENV": "production"}
            env.pop("BRAIN_API_KEY", None)
            self.procs.append(subprocess.Popen(["node", str(SERVER_JS)], cwd=standalone, env=env,
                                               stdout=open(self.tmp / "console.log", "w"), stderr=subprocess.STDOUT))
            wait_port(self.ui_port)

        # the break the 2026-11-03 to-do names: the stored hash is of another password, or the
        # username in the block is not the one typed (basicauth usernames are case-sensitive)
        stored_pw = PASSWORD + "-old" if self.breaks == "hash_mismatch" else PASSWORD
        user = HANDLE.capitalize() if self.breaks == "username_case" else HANDLE
        cf = self.tmp / "Caddyfile"
        cf.write_text(console_block(user=user, hash_line=caddy_hash(stored_pw), console_port=self.console_port,
                                    api_front_port=self.api_front, backend_port=self.backend_port,
                                    ui_port=self.ui_port))
        cenv = {**os.environ, "HOME": str(self.tmp), "XDG_DATA_HOME": str(self.tmp / "data"),
                "XDG_CONFIG_HOME": str(self.tmp / "config"), "E11_FAKE_OPERATOR_TOKEN": "fake"}
        subprocess.run([CADDY, "validate", "--config", str(cf), "--adapter", "caddyfile"], check=True,
                       capture_output=True, env=cenv)
        self.procs.append(subprocess.Popen([CADDY, "run", "--config", str(cf), "--adapter", "caddyfile"], env=cenv,
                                           stdout=open(self.tmp / "caddy.log", "w"), stderr=subprocess.STDOUT))
        wait_port(self.console_port)
        return self

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        self.httpd.shutdown()


# ---------- the check itself: what a person does, in a browser ----------

def login_problems(url: str, username: str, password: str, shot: Path | None = None, path: str = "/") -> list[str]:
    """Log in like a person and reach the chat page. Returns [] when it works, else what went wrong."""
    problems: list[str] = []
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(http_credentials={"username": username, "password": password})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        resp = page.goto(url + path, wait_until="load", timeout=30000)
        status = resp.status if resp else None
        if status != 200:
            problems.append(f"login did not get in: HTTP {status}")
        else:
            box = page.locator("textarea[placeholder^='Ask your brain']")
            try:
                box.wait_for(state="visible", timeout=20000)
                if not box.is_enabled():
                    problems.append("chat composer present but disabled")
            except sync_api.TimeoutError:
                problems.append("chat page did not load: no 'Ask your brain' composer within 20 s")
            page.wait_for_timeout(1500)  # late effects (polls, lazy chunks) get their chance to throw
        problems += errors
        if shot:
            page.screenshot(path=str(shot), full_page=False)
        browser.close()
    return problems


def challenge(url: str) -> tuple[int | None, str]:
    """No credentials: what an outsider meets first. (status, WWW-Authenticate)."""
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        resp = page.goto(url + "/", wait_until="load", timeout=30000)
        out = (resp.status, resp.headers.get("www-authenticate", "")) if resp else (None, "")
        browser.close()
    return out


@pytest.fixture
def stack(tmp_path):
    s = Stack(tmp_path, breaks=os.environ.get("E11_STAGE_BREAK") or None).start()
    FakeBackend.seen = []
    yield s
    s.stop()


def test_login_challenge_served_without_credentials(stack):
    if stack.breaks == "console_down":
        pytest.skip("console_down stages the login, not the challenge")
    status, auth = challenge(stack.url)
    assert status == 401 and auth.lower().startswith("basic"), (status, auth)


def test_console_login_reaches_chat(stack, tmp_path):
    """THE gate. Green on a working console; red with E11_STAGE_BREAK set."""
    shot_dir = Path(os.environ.get("E11_SHOT_DIR") or tmp_path)
    problems = login_problems(stack.url, HANDLE, PASSWORD, shot=shot_dir / f"chat-{stack.breaks or 'ok'}.png")
    assert problems == [], "console login broken:\n  " + "\n  ".join(problems)
    # not vacuous: the page really went through caddy to the console and the console called the bridge
    assert ("GET", "/cc/health") in FakeBackend.seen, FakeBackend.seen


@pytest.mark.parametrize("mode", BREAKS)
def test_gate_reports_each_staged_break(tmp_path, mode):
    """The checker must see each break (kept in the normal run so the gate cannot go vacuous)."""
    s = Stack(tmp_path, breaks=mode).start()
    try:
        problems = login_problems(s.url, HANDLE, PASSWORD)
    finally:
        s.stop()
    assert problems, f"staged break {mode} went unnoticed"
    assert problems[0].startswith("login did not get in: HTTP "), problems
    want = "502" if mode == "console_down" else "401"
    assert problems[0].endswith(want), problems


def test_gate_reports_a_script_error(stack):
    """A page behind the same login whose script throws must be reported (the error channel is not dead)."""
    if stack.breaks:
        pytest.skip("needs a working login")
    problems = login_problems(stack.url, HANDLE, PASSWORD, path="/claude/throws")
    assert any(p.startswith("pageerror:") for p in problems), problems
