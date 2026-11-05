"""tests/browser/test_console_login.py: the console login, in a real browser (2026-11-05, E11).

Why: on 2026-11-03 two member consoles stopped letting people in (the basic-auth password did not
match the hash in the box's Caddyfile, or the username was wrong) and people found it first. Curl and
syntax checks never run a login. This test does, end to end, on this machine:

    Chromium (Playwright) -> caddy (the console block add-member.sh prints, real basicauth)
                          -> the built console (next standalone server.js)
                          -> a fake api + bridge (this file; answers the calls the chat page makes)

and checks: without credentials the login challenge is served (401 + Basic); a wrong password gets 401;
with the right username and password the chat page loads (composer enabled, "Ask your brain") with no
script error, and every /cc and /claude call reached its own fake upstream carrying the X-CC-Operator
token the block injects; with a staged break (wrong hash, wrong-case username, console process down,
the block's `header_up X-CC-Operator` lines dropped) the login check reports problems.

The fake api, term (/claude) and cc (/cc) upstreams listen on three ports, so a block that swaps two
upstreams is caught (misrouted calls answer 421). cc and term answer 401 without the operator token.
Unknown paths answer 404 and are listed in the failure.

The gate is the whole file (`pytest tests/browser`), not one test: the staged-break tests run in the
normal pass so the green test cannot go vacuous.

Not covered (referees 2026-11-05, systems/hbar.science/ops/2026-11-04_autonomy-e10-e11/e11_referee.md in
hbar.world): primary brains whose Caddyfile is not add-member.sh's block, hand-edited Caddyfiles on the
boxes, and the deployed Caddyfile of any live box.

Skips when any of these is missing (scripts/test-gate.sh then prints "browser gate: SKIPPED (<reason>)"):
  - python playwright (a user venv: /home/hands/.local/venvs/nous-browser has playwright 1.63.0 (the release whose browsers.json names chromium 1243) +
    pytest; browsers cached in ~/.cache/ms-playwright, chromium-1243),
  - caddy on PATH,
  - a console build: NOUS_CONSOLE_BUILD=<a ui/ dir after `npm ci && npm run build`>, default ui/ here.
    The build is never written to: .next/standalone is copied once per run into a pytest tmp dir and
    the ui/Dockerfile copy step (.next/static and public into it) is done on the copy.

Run (green):
  NOUS_CONSOLE_BUILD=/tmp/e11-ui/ui LD_LIBRARY_PATH=$HOME/.local/chromelibs/root/usr/lib/aarch64-linux-gnu \
    /home/hands/.local/venvs/nous-browser/bin/python -m pytest tests/browser -q -p no:cacheprovider
Stage a break on the same login test (must go red):
  E11_STAGE_BREAK=hash_mismatch|username_case|console_down|no_operator_header  ...same command...
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
OPERATOR_TOKEN = "e11-fake-operator-token-not-a-real-one"
BREAKS = ("hash_mismatch", "username_case", "console_down", "no_operator_header")

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
# Three upstreams on three ports, as on a box: api (the console's /api/bf proxy and the api front),
# term (/claude, the terminal bridge) and cc (/cc, the cc bridge). Each answers only its own paths.

FAKE = {
    "api": {
        "/apps/list": {"apps": [], "ccHome": True},
        "/onboarding/first-use": {"steps": [], "complete": True, "fresh": False},
        "/onboarding/welcome": {"seen_version": 999},
        "/v1/federation/peers": {"peers": []},
        "/admin/system": {"warnings": []},
    },
    "cc": {
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
        "/cc/layout/mode": {"mode": "full"},
        "/cc/activity": {"threads": {}},
        "/cc/jobs": {"finished": [], "others": []},
        "/cc/system": {"warnings": []},
    },
    "term": {},
}


def role_of(path: str) -> str:
    if path == "/cc" or path.startswith("/cc/"):
        return "cc"
    if path == "/claude" or path.startswith("/claude/"):
        return "term"
    return "api"


class FakeBackend(BaseHTTPRequestHandler):
    seen: list = []        # (role, method, path) answered
    rejected: list = []    # (role, method, path) refused: no or wrong X-CC-Operator
    misrouted: list = []   # (role, method, path) a path that belongs to another upstream
    unknown: list = []     # (role, method, path) answered 404

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _answer(self):
        role = self.server.role
        path = self.path.split("?", 1)[0]
        rec = (role, self.command, path)
        if role_of(path) != role:
            FakeBackend.misrouted.append(rec)
            return self._send(421, b'{"error":"misrouted"}')
        if role in ("cc", "term") and self.headers.get("X-CC-Operator") != OPERATOR_TOKEN:
            FakeBackend.rejected.append(rec)          # the real bridges refuse without the operator token
            return self._send(401, b'{"error":"operator token required"}')
        FakeBackend.seen.append(rec)
        if role == "cc" and path.endswith("/stream") or path == "/cc/live":
            return self._send(200, b"", "text/event-stream")
        if path == "/claude/throws":   # a page whose script throws: proves the error channel is live
            return self._send(200, b"<!doctype html><title>t</title><textarea placeholder='Ask your brain'></textarea>"
                                   b"<script>null.boom()</script>", "text/html")
        if path not in FAKE[role]:
            FakeBackend.unknown.append(rec)
            return self._send(404, b'{"error":"not in the fake"}')
        return self._send(200, json.dumps(FAKE[role][path]).encode())

    do_GET = do_POST = do_HEAD = _answer

    @classmethod
    def reset(cls):
        cls.seen, cls.rejected, cls.misrouted, cls.unknown = [], [], [], []


def fake_server(role: str) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeBackend)
    httpd.role = role
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ---------- the Caddyfile: add-member.sh's own console block, ports and hash filled in ----------

def console_block(*, user: str, hash_line: str, console_port: int, api_front_port: int,
                  ports: dict, ui_port: int, add_member: Path | None = None) -> str:
    """Extract the heredoc add-member.sh prints for the operator and fill it the way the operator does.
    If the template changes shape this raises, so the test follows the shipped block, never a copy."""
    text = (add_member or ADD_MEMBER).read_text()
    m = re.search(r"cat <<CADDY\n(.*?)\nCADDY\n", text, re.S)
    assert m, "add-member.sh no longer prints a CADDY heredoc; update this test with it"
    block = m.group(1)
    placeholder = "$HANDLE <hash of the member's console password: caddy hash-password>"
    assert placeholder in block, "the basicauth placeholder line in add-member.sh changed; update this test"
    block = block.replace(placeholder, f"{user} {hash_line}")
    block = block.replace("console.$HANDLE.brainfoundry.ai {", f"http://127.0.0.1:{console_port} {{")
    block = block.replace("$HANDLE.brainfoundry.ai {", f"http://127.0.0.1:{api_front_port} {{")
    block = block.replace("{\\$$TOKEN_VAR}", "{$E11_FAKE_OPERATOR_TOKEN}")
    for var, role in (("$M_API_PORT", "api"), ("$M_TERM_PORT", "term"), ("$M_CC_PORT", "cc")):
        block = block.replace(var, str(ports[role]))
    block = block.replace("$M_UI_PORT", str(ui_port))
    assert "$" not in block.replace("{$E11_FAKE_OPERATOR_TOKEN}", "").replace(hash_line, ""), \
        f"unfilled variable in block:\n{block}"
    return "{\n\tadmin off\n\tauto_https off\n}\n\n" + block + "\n"


def caddy_hash(password: str) -> str:
    out = subprocess.run([CADDY, "hash-password", "--plaintext", password], check=True,
                         capture_output=True, text=True).stdout.strip()
    assert out.startswith("$2"), out
    return out


def without_operator_header(src: Path, dst: Path) -> Path:
    """A copy of add-member.sh whose console block forgets to inject the operator token."""
    lines = src.read_text().splitlines(keepends=True)
    kept = [l for l in lines if "header_up X-CC-Operator" not in l]
    assert len(kept) < len(lines), "add-member.sh has no header_up X-CC-Operator line to drop"
    dst.write_text("".join(kept))
    return dst


class Stack:
    """Caddy + console + fake upstreams on free localhost ports. `breaks` stages one failure."""

    def __init__(self, tmp: Path, console_dir: Path, breaks: str | None = None, add_member: Path | None = None):
        assert breaks in (None, *BREAKS), breaks
        self.tmp, self.console_dir, self.breaks, self.procs = tmp, console_dir, breaks, []
        self.add_member = add_member
        if breaks == "no_operator_header":
            self.add_member = without_operator_header(add_member or ADD_MEMBER, tmp / "add-member.no-header.sh")
        self.console_port, self.api_front, self.ui_port = (free_port() for _ in range(3))
        self.url = f"http://127.0.0.1:{self.console_port}"

    def start(self) -> "Stack":
        self.servers = {role: fake_server(role) for role in ("api", "term", "cc")}
        ports = {role: srv.server_address[1] for role, srv in self.servers.items()}
        if self.breaks != "console_down":
            env = {**os.environ, "PORT": str(self.ui_port), "HOSTNAME": "127.0.0.1",
                   "API_INTERNAL_URL": f"http://127.0.0.1:{ports['api']}", "NODE_ENV": "production"}
            env.pop("BRAIN_API_KEY", None)
            self.procs.append(subprocess.Popen(["node", "server.js"], cwd=self.console_dir, env=env,
                                               stdout=open(self.tmp / "console.log", "w"), stderr=subprocess.STDOUT))
            wait_port(self.ui_port)

        # the break the 2026-11-03 to-do names: the stored hash is of another password, or the
        # username in the block is not the one typed (basicauth usernames are case-sensitive)
        stored_pw = PASSWORD + "-old" if self.breaks == "hash_mismatch" else PASSWORD
        user = HANDLE.capitalize() if self.breaks == "username_case" else HANDLE
        cf = self.tmp / "Caddyfile"
        cf.write_text(console_block(user=user, hash_line=caddy_hash(stored_pw), console_port=self.console_port,
                                    api_front_port=self.api_front, ports=ports, ui_port=self.ui_port,
                                    add_member=self.add_member))
        cenv = {**os.environ, "HOME": str(self.tmp), "XDG_DATA_HOME": str(self.tmp / "data"),
                "XDG_CONFIG_HOME": str(self.tmp / "config"), "E11_FAKE_OPERATOR_TOKEN": OPERATOR_TOKEN}
        subprocess.run([CADDY, "validate", "--config", str(cf), "--adapter", "caddyfile"], check=True,
                       capture_output=True, env=cenv)
        self.procs.append(subprocess.Popen([CADDY, "run", "--config", str(cf), "--adapter", "caddyfile"], env=cenv,
                                           stdout=open(self.tmp / "caddy.log", "w"), stderr=subprocess.STDOUT))
        wait_port(self.console_port)
        FakeBackend.reset()
        return self

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        for srv in self.servers.values():
            srv.shutdown()


@pytest.fixture(scope="session")
def console_dir(tmp_path_factory) -> Path:
    """A private copy of the standalone console, so the build (or the repo's ui/) is never written to."""
    d = tmp_path_factory.mktemp("console") / "standalone"
    shutil.copytree(SERVER_JS.parent, d, symlinks=True)
    if not (d / ".next" / "static").exists():                       # ui/Dockerfile's copy step
        shutil.copytree(BUILD / ".next" / "static", d / ".next" / "static")
    if (BUILD / "public").exists() and not (d / "public").exists():
        shutil.copytree(BUILD / "public", d / "public")
    return d


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
def stack(tmp_path, console_dir):
    s = Stack(tmp_path, console_dir, breaks=os.environ.get("E11_STAGE_BREAK") or None).start()
    yield s
    s.stop()


def test_login_challenge_served_without_credentials(stack):
    if stack.breaks == "console_down":
        pytest.skip("console_down stages the login, not the challenge")
    status, auth = challenge(stack.url)
    assert status == 401 and auth.lower().startswith("basic"), (status, auth)


def test_console_login_reaches_chat(stack, tmp_path):
    """The main check (the gate is the whole file). Green on a working console; red with E11_STAGE_BREAK set."""
    shot_dir = Path(os.environ.get("E11_SHOT_DIR") or tmp_path)
    if stack.breaks != "console_down":
        # the lock is a lock: a wrong password is refused at caddy
        wrong = login_problems(stack.url, HANDLE, PASSWORD + "-wrong")
        assert wrong and wrong[0] == "login did not get in: HTTP 401", wrong
        FakeBackend.reset()
    problems = login_problems(stack.url, HANDLE, PASSWORD, shot=shot_dir / f"chat-{stack.breaks or 'ok'}.png")
    if FakeBackend.rejected:
        problems.append(f"bridge refused calls without the operator token: {FakeBackend.rejected}")
    if FakeBackend.misrouted:
        problems.append(f"calls reached the wrong upstream: {FakeBackend.misrouted}")
    if FakeBackend.unknown:
        problems.append(f"calls the fake does not know (404): {FakeBackend.unknown}")
    assert problems == [], "console login broken:\n  " + "\n  ".join(problems)
    # not vacuous: the page really went through caddy to the console and the console called the bridge
    assert ("cc", "GET", "/cc/health") in FakeBackend.seen, FakeBackend.seen


@pytest.mark.parametrize("mode", BREAKS)
def test_gate_reports_each_staged_break(tmp_path, console_dir, mode):
    """The checker must see each break (kept in the normal run so the gate cannot go vacuous)."""
    s = Stack(tmp_path, console_dir, breaks=mode).start()
    try:
        problems = login_problems(s.url, HANDLE, PASSWORD)
    finally:
        s.stop()
    if mode == "no_operator_header":
        # the login works, but every bridge call is refused: the console must not look healthy
        assert FakeBackend.rejected, f"no bridge call was refused: {FakeBackend.seen}"
        assert problems, f"staged break {mode} went unnoticed by the browser check"
        return
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
