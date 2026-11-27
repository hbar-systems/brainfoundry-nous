"""Tide (AUTO-UPDATE-1, 2026-11-27, docs/TIDE.md): the brain updates itself at a quiet moment.
scripts/cc/cc_tide.py (the rule, the lines, the store) on temp dirs, ui/lib/tide.js under node, the
bridge's routes over a real loopback socket (the root door refused to anyone but uid 0), and the root
runner and installer read as text (they need root and systemd; they are never run here).

Run from repo root:
    pytest tests/test_cc_tide.py -v
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_tide", ROOT / "scripts" / "cc" / "cc_tide.py")
T = importlib.util.module_from_spec(spec); sys.modules["cc_tide"] = T; spec.loader.exec_module(T)

NOW = 1_800_000_000.0
QUIET = {"on": True, "halt": None, "behind": 3, "latest": "b" * 40, "failed_sha": None, "updating": False,
         "last_update": None, "runs": 0, "cards": 0, "uploads": 0, "jobs": 0, "last_touch": NOW - 3600, "terminal": None}


def q(**kw):
    return T.quiet({**QUIET, **kw}, NOW)


# ---- the rule ----
def test_quiet_only_when_every_condition_holds():
    ok, why = q()
    assert ok and why.startswith("quiet: 3 commits to take")


@pytest.mark.parametrize("kw,words", [
    ({"member": True}, "off: a member's brain updates only by its owner's press"),
    ({"on": False}, "off: it waits for your press"),
    ({"halt": "HALT: owner"}, "waiting: the brain is halted (HALT: owner)"),
    ({"behind": None}, "waiting: the running version cannot be read"),
    ({"behind": 0}, "waiting: nothing new on origin/main"),
    ({"updating": True}, "waiting: an update is running"),
    ({"failed_sha": "b" * 40}, "waiting: the update to bbbbbbb failed its health check; no retry until a new commit"),
    ({"runs": 2}, "waiting: 2 conversations answering"),
    ({"runs": 1}, "waiting: 1 conversation answering"),
    ({"cards": 1}, "waiting: 1 card waits for your press"),
    ({"uploads": 1}, "waiting: an upload or a recording is coming in"),
])
def test_each_no_says_why(kw, words):
    ok, why = q(**kw)
    assert not ok and why == words


def test_his_last_touch_and_the_terminal():
    ok, why = q(last_touch=NOW - 4 * 60)
    assert not ok and why.startswith("waiting: you were here 4 min ago; quiet from ")
    ok, why = q(terminal=NOW - 60)
    assert not ok and why.startswith("waiting: you were in the terminal 1 min ago")
    assert q(last_touch=NOW - 21 * 60)[0] is True
    assert q(last_touch=None)[0] is True                     # never touched since the file began
    assert T.quiet({**QUIET, "last_touch": NOW - 10 * 60}, NOW, idle_min=5)[0] is True


def test_one_an_hour_and_a_failed_commit_is_not_retried():
    ok, why = q(last_update=NOW - 30 * 60)
    assert not ok and why.startswith("waiting: an update ran 30 min ago; the next from ")
    assert q(last_update=NOW - 61 * 60)[0] is True
    assert q(failed_sha="a" * 40)[0] is True                  # a new commit arrived since the failure


def test_jobs_survive_so_they_do_not_block_unless_asked():
    ok, why = q(jobs=2)
    assert ok and why.endswith("; 2 jobs run on (jobs survive an update)")
    ok, why = T.quiet({**QUIET, "jobs": 2}, NOW, jobs_block=True)
    assert not ok and why == "waiting: 2 jobs running"
    assert T.JOBS_BLOCK is False


def test_order_off_before_everything_and_missing_facts_never_say_yes():
    assert q(on=False, runs=3)[1].startswith("off")
    assert T.quiet({}, NOW)[0] is False
    assert T.quiet({"on": True}, NOW)[1] == "waiting: the running version cannot be read"


def test_touch_and_upload_routes():
    for r in ("/chat", "/permits/approve", "/presses", "/threads/abc/say", "/upload/big/start", "/autoupdate/switch"):
        assert T.touch_route(r), r
    for r in ("/jobs/start", "/notify", "/ask", "/spend/append", "/autoupdate/begin", "/threads/abc/title", "/update/check"):
        assert not T.touch_route(r), r
    assert T.upload_route("/upload") and T.upload_route("/upload/big/x") and T.upload_route("/booth/take")
    assert not T.upload_route("/chat")


# ---- the lines ----
def test_lines_before_and_after():
    assert T.begin_line(4, ["a fix", "b page", "c", "d"]) == "updating now: 4 commits: a fix; b page; c (+1 more)"
    assert T.begin_line(1, []) == "updating now: 1 commit"
    a, b = "a" * 40, "b" * 40
    assert T.end_line({"result": "healthy", "to": b, "head": b}) == "updated to bbbbbbb, healthy"
    assert T.end_line({"result": "failed", "rc": 1, "from": a, "to": b, "head": a}) == \
        "update to bbbbbbb failed (rc=1); the old version aaaaaaa still runs; no retry until a new commit"
    assert "Revert on /update goes back to aaaaaaa" in T.end_line({"result": "failed", "rc": 1, "from": a, "to": b, "head": b})
    assert T.end_line({"result": "busy"}).startswith("update skipped")
    assert T.end_line({"result": "unknown", "to": b}).startswith("the update to bbbbbbb never reported back")


# ---- the store ----
def test_switch_off_by_default_and_only_a_boolean(tmp_path):
    s = T.Store(tmp_path)
    assert s.on() is False and s.view()["on"] is False
    for bad in ("yes", 1, None):
        with pytest.raises(ValueError):
            s.set_on(bad)
    assert s.set_on(True)["on"] is True
    assert stat.S_IMODE(os.stat(tmp_path / T.FILE).st_mode) == 0o600
    assert T.Store(tmp_path).on() is True                      # kept across a restart


def test_begin_end_history_and_failed_sha(tmp_path):
    clock = [NOW]
    s = T.Store(tmp_path, clock=lambda: clock[0])
    a, b, c = "a" * 40, "b" * 40, "c" * 40
    with pytest.raises(ValueError):
        s.begin("x; rm", b, 1, [])
    s.begin(a, b, 2, ["one", "two"])
    assert s.facts()["updating"] is True and s.facts()["last_update"] == NOW
    with pytest.raises(ValueError):
        s.begin(a, b, 2, [])                                   # one at a time
    assert s.end(1, a, to=c) is None                           # not this run
    clock[0] += 120
    rec = s.end(1, a, to=b)
    assert rec["result"] == "failed" and s.facts()["failed_sha"] == b and s.facts()["updating"] is False
    clock[0] += 4000
    s.begin(a, c, 3, [])
    rec = s.end("0", c, to=c)
    assert rec["result"] == "healthy" and s.facts()["failed_sha"] is None
    assert [r["result"] for r in s.view()["recent"]] == ["healthy", "failed"]


def test_busy_does_not_start_the_hour_and_a_silent_run_expires(tmp_path):
    clock = [NOW]
    s = T.Store(tmp_path, clock=lambda: clock[0])
    a, b = "a" * 40, "b" * 40
    s.begin(a, b, 1, [])
    s.end(75, a, to=b)
    assert s.view()["recent"][0]["result"] == "busy" and not s.facts()["last_update"]
    s.begin(a, b, 1, [])
    clock[0] += T.BEGIN_TTL + 1
    f = s.facts()
    assert f["updating"] is False and s.view()["recent"][0]["result"] == "unknown"


def test_touch_kept_in_memory_and_saved_at_most_every_30_s(tmp_path):
    clock = [NOW]
    s = T.Store(tmp_path, clock=lambda: clock[0])
    s.touch()
    assert s.last_touch() == NOW and T.Store(tmp_path).last_touch() == NOW
    clock[0] += 5
    s.touch()
    assert s.last_touch() == NOW + 5 and T.Store(tmp_path).last_touch() == NOW
    clock[0] += 40
    s.touch()
    assert T.Store(tmp_path).last_touch() == NOW + 45
    s.upload_start(); s.upload_start(); s.upload_end()
    assert s.uploads() == 1
    s.upload_end(); s.upload_end()
    assert s.uploads() == 0


# ---- ui/lib/tide.js ----
def _node(script: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_page_line():
    d = json.loads(_node(r"""
const { tideView } = require('./tide')
const now = 1800000000
const out = {
  member: tideView({ member: true, on: true }, now),
  none: tideView(null, now),
  off: tideView({ on: false, next: 'off: it waits for your press', recent: [] }, now),
  on: tideView({ on: true, next: 'waiting: 2 conversations answering', asked: { at: now - 120 },
                 recent: [{ started: now - 7200, n: 4, result: 'healthy', head: 'abcdef1234' },
                          { started: now - 90000, n: 1, result: 'failed', rc: 1, to: 'bbbbbbb' },
                          { started: now - 99000, n: 2, result: 'busy' }, { n: 9, result: 'healthy' }] }, now),
  stale: tideView({ on: true, next: 'x', asked: { at: now - 3600 } }, now),
  begun: tideView({ on: true, next: 'x', begun: { n: 3 } }, now),
}
console.log(JSON.stringify(out))
"""))
    assert d["member"] is None and d["none"] is None
    assert d["off"]["label"] == "updates itself at quiet moments: off" and d["off"]["press"] == "Turn on"
    assert d["off"]["next"] == "off: it waits for your press"
    assert d["off"]["timer"].startswith("the box timer has not asked yet")
    on = d["on"]
    assert on["label"].endswith(": on") and on["press"] == "Turn off" and on["next"] == "waiting: 2 conversations answering"
    assert on["timer"] == "the box timer asked 2 min ago"
    assert len(on["recent"]) == 3
    assert on["recent"][0] == "2027-01-15 06:00 UTC: 4 commits, healthy at abcdef1"
    assert on["recent"][1].endswith("1 commit, failed (rc=1), no retry until a new commit")
    assert on["recent"][2].endswith("skipped (another update ran)")
    assert "may be stopped" in d["stale"]["timer"]
    assert d["begun"]["next"] == "updating now: 3 commits"


# ---- the bridge: routes over loopback ----
def _git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _repo(tmp_path) -> Path:
    """A checkout one commit behind its origin, fetched."""
    origin, brain, other = tmp_path / "origin.git", tmp_path / "brain", tmp_path / "other"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    _git("clone", str(origin), str(brain), cwd=tmp_path)
    (brain / "a").write_text("1")
    _git("add", "a", cwd=brain); _git("commit", "-m", "first", cwd=brain); _git("push", "origin", "HEAD:main", cwd=brain)
    _git("clone", str(origin), str(other), cwd=tmp_path)
    (other / "b").write_text("2")
    _git("add", "b", cwd=other); _git("commit", "-m", "the new page", cwd=other); _git("push", "origin", "HEAD:main", cwd=other)
    _git("fetch", "origin", cwd=brain)
    return brain


def _bridge(monkeypatch, tmp_path, member=""):
    brain = _repo(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(brain))
    monkeypatch.setenv("CC_HANDS_HOME", str(tmp_path))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", "tok")
    monkeypatch.setenv("CC_CENTRAL_THREAD", "central1")
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    monkeypatch.delenv("CC_WORLD_DIR", raising=False)
    if member:
        monkeypatch.setenv("CC_MEMBER", member)
    else:
        monkeypatch.delenv("CC_MEMBER", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_tide", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    said = []
    monkeypatch.setattr(m, "_notify", lambda text: said.append(text) or (200, {"ok": True}))
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return m, srv, f"http://127.0.0.1:{srv.server_address[1]}/cc", said, brain


def _call(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


OP = {"X-CC-Operator": "tok"}


def test_root_door_refuses_everyone_but_uid_0(monkeypatch, tmp_path):
    if os.getuid() == 0:
        pytest.skip("runs as root")
    m, srv, base, said, _ = _bridge(monkeypatch, tmp_path)
    try:
        assert _call(base + "/autoupdate/quiet")[0] == 403
        assert _call(base + "/autoupdate/quiet", headers=OP)[0] == 403          # the console's token is not root
        assert _call(base + "/autoupdate/begin", {"from": "a", "to": "b"}, headers=OP)[0] == 403
        assert _call(base + "/autoupdate/end", {"rc": 0}, headers=OP)[0] == 403
        assert _call(base + "/autoupdate")[0] == 403                              # the page's view needs the console
        assert said == []
    finally:
        srv.shutdown()


def test_switch_view_and_a_whole_quiet_update(monkeypatch, tmp_path):
    m, srv, base, said, brain = _bridge(monkeypatch, tmp_path)
    monkeypatch.setattr(m.Handler, "_peer_in", lambda self, uids: 0 in uids)    # the caller is root, as the timer is
    try:
        st, v = _call(base + "/autoupdate", headers=OP)
        assert st == 200 and v["on"] is False and v["next"] == "off: it waits for your press" and v["behind"] == 1
        assert _call(base + "/autoupdate/switch", {"on": "yes"}, headers=OP)[0] == 400
        st, v = _call(base + "/autoupdate/switch", {"on": True}, headers=OP)
        # the press on /update is itself his touch: the rule waits the idle minutes after it
        assert st == 200 and v["on"] is True and v["next"].startswith("waiting: you were here 0 min ago")
        m.TIDE._touch = 0.0
        st, a = _call(base + "/autoupdate/quiet?terminal=0")
        assert st == 200 and a["quiet"] is True and a["behind"] == 1 and a["lines"] == ["the new page"]
        assert m.TIDE.view()["asked"]["quiet"] is True
        # a wrong pair of commits is refused, the right one begins and says the line before
        assert _call(base + "/autoupdate/begin", {"from": a["head"], "to": a["head"]})[0] == 409
        st, b = _call(base + "/autoupdate/begin", {"from": a["head"], "to": a["latest"], "terminal": 0})
        assert st == 200 and said == ["updating now: 1 commit: the new page"]
        st, a2 = _call(base + "/autoupdate/quiet")
        assert a2["quiet"] is False and a2["why"] == "waiting: an update is running"
        st, e = _call(base + "/autoupdate/end", {"rc": 0, "head": a["latest"], "to": a["latest"]})
        assert st == 200 and e["result"] == "healthy" and said[-1] == f"updated to {a['latest'][:7]}, healthy"
        cards = m.REPORTS.take("central1")
        assert [c["lines"][0] for c in cards] == [said[0], said[1]] and all(c["child"] is None for c in cards)
        assert len(m.CARDLOG.list("central1")) == 2
        assert _call(base + "/autoupdate/end", {"rc": 0, "head": a["latest"]})[0] == 409   # nothing had begun
        st, v = _call(base + "/autoupdate", headers=OP)
        assert v["recent"][0]["result"] == "healthy"
    finally:
        srv.shutdown()


def test_a_turn_a_card_or_his_message_keeps_it_waiting(monkeypatch, tmp_path):
    m, srv, base, said, _ = _bridge(monkeypatch, tmp_path)
    monkeypatch.setattr(m.Handler, "_peer_in", lambda self, uids: 0 in uids)
    try:
        m.TIDE.set_on(True)
        monkeypatch.setattr(m, "_runs_active", lambda: [object(), object()])
        assert _call(base + "/autoupdate/quiet")[1]["why"] == "waiting: 2 conversations answering"
        monkeypatch.setattr(m, "_runs_active", lambda: [])
        m.ASKS["p1"] = {"event": None, "decision": None}
        assert _call(base + "/autoupdate/quiet")[1]["why"] == "waiting: 1 card waits for your press"
        m.ASKS.clear()
        assert _call(base + "/autoupdate/quiet")[1]["quiet"] is True
        assert _call(base + "/presses", {"kind": "nav", "name": "update"}, headers=OP)[0] == 200   # a press is his touch
        assert _call(base + "/autoupdate/quiet")[1]["why"].startswith("waiting: you were here")
        m.TIDE._touch = 0.0
        assert _call(base + "/autoupdate/quiet?terminal=%d" % int(__import__("time").time()))[1]["why"].startswith("waiting: you were in the terminal")
        (tmp_path / ".cc-bridge" / "HALT").write_text("stop\n")
        assert _call(base + "/autoupdate/quiet")[1]["why"].startswith("waiting: the brain is halted")
        assert said == []
    finally:
        srv.shutdown()


def test_member_brain_is_untouched(monkeypatch, tmp_path):
    m, srv, base, said, _ = _bridge(monkeypatch, tmp_path, member="ada")
    try:
        st, d = _call(base + "/autoupdate/switch", {"on": True}, headers=OP)
        assert st == 409 and m.TIDE.on() is False
        st, v = _call(base + "/autoupdate", headers=OP)
        assert v["member"] is True and v["next"].startswith("off: a member's brain")
    finally:
        srv.shutdown()


def test_bridge_wiring_in_the_source():
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    # the root door: uid 0 on loopback with no proxy header, checked before the operator token
    assert src.count("self._peer_in({0})") == 2
    assert src.index('if route == "/autoupdate/quiet":') < src.index('if route not in ("/health", "/tasks", "/threads/brief")')
    # his phone counts as his touch, both a message and a press
    assert src.count("TIDE.touch()") >= 3
    # the bridge never runs the update itself
    tide = src[src.index("# ---- Tide (AUTO-UPDATE-1"):src.index("# ---- the owner's layout file")]
    assert "update_brain" not in tide.replace("scripts/update_brain.sh)", "") and "subprocess.Popen" not in tide and "sudo" not in tide


# ---- the root runner and its installer (text only: they need root) ----
def test_runner_runs_only_the_same_update_and_checks_first():
    sh = (ROOT / "scripts" / "tide" / "brain-tide.sh").read_text()
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / "tide" / "brain-tide.sh")]).returncode == 0
    assert 'as_owner bash "$BRAIN_DIR/scripts/update_brain.sh" "$BRAIN_DIR"' in sh
    assert sh.count("update_brain.sh\" \"$BRAIN_DIR\"") == 1                     # one way in, nothing else runs
    assert '( checks ) && as_owner bash' in sh                                    # the checks again right before
    assert 'refuse "127.0.0.1:$CC_PORT belongs to uid' in sh                      # the answer only from the bridge's socket
    assert '[ -z "${INVOCATION_ID:-}" ]' in sh                                    # the update only from its unit
    code = [ln for ln in sh.split("set -euo pipefail", 1)[1].splitlines() if not ln.lstrip().startswith("#")]
    assert not any(__import__("re").search(r"(^|[;&|(]\s*)sudo\s", ln.split('echo', 1)[0]) for ln in code)   # never sudo itself


def test_installer_touches_no_sudoers_and_refuses_members():
    sh = (ROOT / "scripts" / "tide" / "install-tide.sh").read_text()
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / "tide" / "install-tide.sh")]).returncode == 0
    body = sh.split("set -euo pipefail", 1)[1]
    assert "sudoers" not in body and "visudo" not in body
    assert "CC_MEMBER=." in body and "--dry-run" in body
    unit = (ROOT / "scripts" / "tide" / "brain-tide.service").read_text()
    assert "ExecStart=/usr/local/sbin/brain-tide\n" in unit and "@BRAIN_DIR@" in unit
    timer = (ROOT / "scripts" / "tide" / "brain-tide.timer").read_text()
    assert "OnUnitActiveSec=5min" in timer


# ---- the root runner, run for real as this user (root's own steps replaced, every host command a fake) ----
def _runner_box(tmp_path, answer_quiet=True, chmod_script=0o755):
    """A checkout one commit behind its origin whose scripts/update_brain.sh pulls and leaves a mark; the
    runner copied with its root-only lines replaced; fake ss, runuser and curl on PATH. The fake curl
    answers like the bridge and logs every call."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    origin, brain, other = tmp_path / "origin.git", tmp_path / "brain", tmp_path / "other"
    _git("init", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    _git("clone", str(origin), str(brain), cwd=tmp_path)
    (brain / "scripts").mkdir()
    upd = brain / "scripts" / "update_brain.sh"
    upd.write_text('#!/bin/bash\nset -e\ncd "$1"\necho "update ran as $(id -un) in $1" > "$1/../update-mark"\n'
                   'git pull --ff-only origin main\n')
    upd.chmod(0o755)
    _git("add", "-A", cwd=brain); _git("commit", "-m", "first", cwd=brain); _git("push", "origin", "HEAD:main", cwd=brain)
    _git("clone", str(origin), str(other), cwd=tmp_path)
    (other / "b").write_text("2")
    _git("add", "b", cwd=other); _git("commit", "-m", "the new page", cwd=other); _git("push", "origin", "HEAD:main", cwd=other)
    upd.chmod(chmod_script)
    for p in (brain, brain / ".git", brain / ".git" / "config", brain / ".git" / "hooks", brain / "scripts"):
        p.chmod(p.stat().st_mode & ~0o022)
    head = subprocess.run(["git", "-C", str(brain), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    latest = subprocess.run(["git", "-C", str(other), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    fake = tmp_path / "bin"; fake.mkdir()
    (fake / "ss").write_text(f"#!/bin/bash\necho 'LISTEN 0 5 127.0.0.1:7682 0.0.0.0:* uid:{os.getuid()} ino:1'\n")
    (fake / "runuser").write_text('#!/bin/bash\nwhile [ "$1" != "--" ]; do shift; done; shift; exec "$@"\n')
    log = tmp_path / "curl.log"
    ans = {"quiet": answer_quiet, "why": "quiet: 1 commit to take" if answer_quiet else "waiting: 2 conversations answering",
           "head": head, "latest": latest}
    (tmp_path / "answer.json").write_text(json.dumps(ans))
    (fake / "curl").write_text(f'#!/bin/bash\necho "$@" >> {log}\n'
                               f'case "$*" in *autoupdate/quiet*) cat {tmp_path / "answer.json"};; *) echo "{{\\"ok\\":true}}";; esac\n')
    for f in fake.iterdir():
        f.chmod(0o755)
    sh = (ROOT / "scripts" / "tide" / "brain-tide.sh").read_text()
    for old, new in [('[ "$(id -u)" = 0 ] || {', 'true || {'),
                     ('install -d -o root -g root -m 755 "$STATE"', 'mkdir -p "$STATE"'),
                     ('case "$OWNER" in "$BRIDGE_USER"|hands|*-cc|*-hands) refuse', 'case "$OWNER" in __never__) refuse'),
                     ("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={fake}:/usr/local/bin:/usr/bin:/bin")]:
        assert sh.count(old) == 1, old
        sh = sh.replace(old, new)
    sh = sh.replace("sleep 15", "sleep 0")
    run = tmp_path / "brain-tide"; run.write_text(sh); run.chmod(0o755)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BRAIN_DIR": str(brain), "CC_PORT": "7682",
           "BRIDGE_USER": __import__("pwd").getpwuid(os.getuid()).pw_name, "TIDE_STATE": str(tmp_path / "state"),
           "INVOCATION_ID": "x", "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig")}
    return run, env, brain, log, head, latest


def test_runner_quiet_moment_runs_the_update_and_reports(tmp_path):
    run, env, brain, log, head, latest = _runner_box(tmp_path)
    r = subprocess.run([str(run)], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr + (tmp_path / "state" / "tide.log").read_text()
    assert (tmp_path / "update-mark").read_text().startswith("update ran as")
    assert subprocess.run(["git", "-C", str(brain), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() == latest
    calls = log.read_text().splitlines()
    assert "autoupdate/quiet?terminal=0" in calls[0] and "autoupdate/begin" in calls[1] and "autoupdate/end" in calls[2]
    assert f'"from":"{head}","to":"{latest}"' in calls[1] and f'"rc":0,"head":"{latest}"' in calls[2]
    last = json.loads((tmp_path / "state" / "last.json").read_text())
    assert last["rc"] == 0 and last["head"] == latest
    assert "yes: updating" in (tmp_path / "state" / "tide.log").read_text()


def test_runner_not_quiet_runs_nothing(tmp_path):
    run, env, brain, log, head, latest = _runner_box(tmp_path, answer_quiet=False)
    r = subprocess.run([str(run)], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    assert not (tmp_path / "update-mark").exists()
    assert len(log.read_text().splitlines()) == 1                                 # asked, nothing more
    assert "no: waiting: 2 conversations answering" in (tmp_path / "state" / "tide.log").read_text()


def test_runner_refuses_a_writable_script_and_a_call_outside_its_unit(tmp_path):
    run, env, brain, log, head, latest = _runner_box(tmp_path, chmod_script=0o777)
    r = subprocess.run([str(run)], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2 and "world-writable" in r.stderr and not log.exists()
    run, env, brain, log, head, latest = _runner_box(tmp_path / "b")
    r = subprocess.run([str(run)], env={k: v for k, v in env.items() if k != "INVOCATION_ID"}, capture_output=True, text=True)
    assert r.returncode == 2 and "brain-tide.service only" in r.stderr
    r = subprocess.run([str(run), "--dry-run"], env={k: v for k, v in env.items() if k != "INVOCATION_ID"}, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "bridge: quiet" in r.stdout and not (tmp_path / "b" / "update-mark").exists()
