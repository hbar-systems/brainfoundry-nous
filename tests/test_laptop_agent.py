"""Bring in this computer, the dial-out agent (SPOKE-3 "Courier", 2026-11-16).

agent.sh runs here exactly as the member runs it: `curl -fsSL <brain>/laptop/agent.sh | bash -s -- <token>`
against the api on 127.0.0.1 over a temp home (made-up cloud folders, secrets planted). It must list
what MOVE-IN-2's Python survey lists (one never-send list, rendered from brain_import.py), send the
inventory only, wait for the owner's choice, pull exactly that, never send a name it did not list,
close the key and leave nothing behind. agent.ps1 has no PowerShell here: it is checked statically
(rules rendered in, no blanks); its real run is owed on a Windows laptop.
"""
import gzip
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.test_move_in_survey import NOW, _home, server, h, li, ls  # noqa: F401  (fixture and helpers)
from api import laptop_agent as la

BASH = shutil.which("bash")
CURL = shutil.which("curl")
needs_shell = pytest.mark.skipif(not (BASH and CURL), reason="bash and curl needed")


def _run_line(url, token, home, tmp, extra_env=None, timeout=60):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "TMPDIR": str(tmp),
           "BRAIN_AGENT_POLL": "0.1", "LANG": "C.UTF-8"}
    env.update(extra_env or {})
    line = f"curl -fsSL {url}/laptop/agent.sh | bash -s -- {token}"
    r = subprocess.run(["bash", "-c", line], env=env, capture_output=True, text=True, timeout=timeout)
    return r


def _owner_chooses(c, pick=None):
    def go():
        for _ in range(400):
            st = c.get("/documents/import-laptop/status").json()["survey"]
            if st and st.get("state") == "plan":
                ids = pick(st["groups"]) if pick else [g["id"] for g in st["groups"] if g["proposal"] != "leave"]
                assert c.post("/documents/import-laptop/plan", json={"take": ids}).status_code == 200
                return
            time.sleep(0.05)
    t = threading.Thread(target=go)
    t.start()
    return t


def _survey_paths(m):
    data = m._LAPTOP_SURVEYS.get(m._LAPTOP_TOKENS.latest_hash())
    return sorted(p for g in data["groups"] for p in g["paths"]), data


# ── the one line, end to end ─────────────────────────────────────────

@needs_shell
def test_agent_sh_end_to_end_matches_the_python_survey(server, tmp_path):
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    before = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    t = _owner_chooses(c)
    r = _run_line(server.url, tok, home, agent_tmp)
    t.join(10)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    assert "Connected to your brain." in out and "Cloud folders: iCloud Drive, Google Drive, Dropbox." in out

    # the inventory is the Python helper's, name for name
    listed, data = _survey_paths(server.m)
    rows, skipped, _places, clouds = h.survey(home, system="darwin")
    assert listed == sorted(n for n, _s, _m in rows)
    assert data["roots"] == clouds == ["iCloud Drive", "Google Drive", "Dropbox"]
    assert data["skipped"] == skipped
    assert data["os"] == "linux"

    # exactly the chosen files came, documents proposed, music and pictures kept as files
    names = sorted(p["refs"]["filename"] for p in server.proposals)
    assert names == sorted("laptop/" + n for n in ["Desktop/todo.txt", "Documents/Lectures/one.pdf", "Documents/Lectures/two.docx",
                                                   "Documents/plan.md", "notes.txt", "iCloud Drive/Notes/idea.md",
                                                   "Google Drive/Work/brief.txt", "Dropbox/shared/sheet.csv"])
    assert "laptop/Downloads/old.pdf" not in names                    # proposed to leave, not chosen
    media = (next((tmp_path / "in").glob("*/import/media.tsv"))).read_text()
    audio = (next((tmp_path / "in").glob("*/import/audio.tsv"))).read_text()
    assert "Pictures/beach.jpg" in media and "Music/song.wav" in audio
    texts = " ".join(p.read_text() for p in (server.tmp / "proposal_texts").glob("*.txt"))
    for secret in ("sk-x", "OPENSSH", "hunter2", "From x", "key"):
        assert secret not in texts
    assert "[10/10]" in out and "Done: 10 sent, 0 not taken." in out

    # one run: the key is closed, nothing stays behind
    assert c.get("/documents/import-laptop/check", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert list(agent_tmp.iterdir()) == []
    assert sorted(str(p.relative_to(home)) for p in home.rglob("*")) == before   # no receipt, no file left


@needs_shell
def test_agent_sh_odd_names_links_and_private_folders(server, tmp_path):
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Documents" / 'say "hi"; ok, then.md').write_text("quote name")
    (home / "Documents" / "Лекция 1.txt").write_text("по-русски")
    (home / "Documents" / "new\nline.txt").write_text("never listed")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside the home")
    (home / "Documents" / "link.txt").symlink_to(outside)
    (home / "Documents" / "linkdir").symlink_to(tmp_path)
    shut = home / "Locked"
    shut.mkdir()
    (shut / "x.md").write_text("locked")
    shut.chmod(0)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    try:
        c = TestClient(server.m.app)
        tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
        t = _owner_chooses(c)
        r = _run_line(server.url, tok, home, agent_tmp)
        t.join(10)
    finally:
        shut.chmod(0o755)
    assert r.returncode == 0, r.stdout + r.stderr
    listed, data = _survey_paths(server.m)
    if os.geteuid() != 0:  # root reads a mode-0 folder
        assert "Locked" in r.stdout and "Locked: kept private by the system" in data["skipped"]
        assert "Locked/x.md" not in listed
    assert 'Documents/say "hi"; ok, then.md' in listed and "Documents/Лекция 1.txt" in listed
    assert not any("link" in p for p in listed)
    names = sorted(p["refs"]["filename"] for p in server.proposals)
    assert 'laptop/Documents/say "hi"; ok, then.md' in names and "laptop/Documents/Лекция 1.txt" in names
    assert len(names) == 2 and "outside the home" not in " ".join(p.read_text() for p in (server.tmp / "proposal_texts").glob("*.txt"))


@needs_shell
def test_agent_sh_never_sends_a_name_it_did_not_list(server, tmp_path, monkeypatch):
    """A brain (or anyone holding the plan) asking for more gets nothing more: the agent checks every
    chosen name against its own list."""
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    real = server.m._LAPTOP_SURVEYS.take

    def greedy(hsh):
        t = real(hsh)
        if t is not None:
            t["paths"] = [["Documents/.env", "knowledge"], [".ssh/id_rsa", "knowledge"],
                          ["Documents/id_ed25519", "knowledge"], ["../../etc/passwd", "knowledge"],
                          ["Documents/plan.md", "knowledge"]]
        return t
    monkeypatch.setattr(server.m._LAPTOP_SURVEYS, "take", greedy)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    t = _owner_chooses(c)
    r = _run_line(server.url, tok, home, agent_tmp)
    t.join(10)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "4 names the brain asked for were not on this computer's list" in r.stdout
    assert [p["refs"]["filename"] for p in server.proposals] == ["laptop/Documents/plan.md"]


@needs_shell
def test_agent_sh_refusals(server, tmp_path):
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    c = TestClient(server.m.app)
    r = _run_line(server.url, "not-a-token", home, tmp_path)
    assert r.returncode == 2 and "imp_" in r.stdout
    r = _run_line(server.url, "imp_" + "x" * 43, home, tmp_path)
    assert r.returncode == 4 and "(401)" in r.stdout
    folder = c.post("/documents/import-laptop/token").json()["token"]
    r = _run_line(server.url, folder, home, tmp_path)
    assert r.returncode == 4 and "another kind of import" in r.stdout
    # a second argument that is not https is refused before anything is sent
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(tmp_path)}
    r = subprocess.run(["bash", "-c", f"curl -fsSL {server.url}/laptop/agent.sh | bash -s -- {folder} http://evil.example"],
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "https://" in r.stdout


@needs_shell
def test_agent_sh_line_closed_while_waiting(server, tmp_path):
    """The owner presses New line (or the key expires) while the computer waits: nothing is sent."""
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]

    def replace():
        for _ in range(400):
            st = c.get("/documents/import-laptop/status").json()["survey"]
            if st and st.get("state") == "plan":
                c.post("/documents/import-laptop/token", json={"survey": True})  # closes the old line
                return
            time.sleep(0.05)
    t = threading.Thread(target=replace)
    t.start()
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    r = _run_line(server.url, tok, home, agent_tmp)
    t.join(10)
    assert r.returncode == 0 and "Nothing was sent." in r.stdout
    assert server.proposals == [] and list(agent_tmp.iterdir()) == []


@needs_shell
def test_agent_sh_in_russian(server, tmp_path):
    from fastapi.testclient import TestClient
    home = tmp_path / "home"
    _home(home)
    c = TestClient(server.m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    t = _owner_chooses(c, pick=lambda gs: [gs[0]["id"]])
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "TMPDIR": str(tmp_path), "BRAIN_AGENT_POLL": "0.1"}
    r = subprocess.run(["bash", "-c", f"curl -fsSL '{server.url}/laptop/agent.sh?lang=ru' | bash -s -- {tok}"],
                       env=env, capture_output=True, text=True, timeout=60)
    t.join(10)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Связь с вашим мозгом есть." in r.stdout and "Готово: отправлено" in r.stdout


# ── the routes and the rendering ─────────────────────────────────────

def test_script_routes_address_and_words(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    r = c.get("/laptop/agent.sh", headers={"Host": "elena.brainfoundry.ai"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers["cache-control"] == "no-store"
    assert 'BASE="${2:-https://elena.brainfoundry.ai/api/bf}"' in r.text
    assert "@@" not in r.text
    # behind the console's own proxy the api sees api:8000; the proxy's X-Forwarded-Host names the brain
    r = c.get("/laptop/agent.ps1", headers={"Host": "api:8000", "X-Forwarded-Host": "christos.brainfoundry.ai"})
    assert "'https://christos.brainfoundry.ai/api/bf'" in r.text and "@@" not in r.text
    assert c.get("/laptop/agent.sh", headers={"Host": "evil.example/x"}).status_code == 400
    assert c.get("/laptop/agent.sh", headers={"Host": "api:8000"}).status_code == 400
    ru = c.get("/laptop/agent.sh?lang=ru", headers={"Host": "b.example"}).text
    assert "Связь с вашим мозгом есть." in ru
    assert "Connected to your brain." in c.get("/laptop/agent.sh?lang=xx", headers={"Host": "b.example"}).text
    # no key, no state: the same text to anyone
    assert c.get("/laptop/agent.sh", headers={"Host": "b.example", "Authorization": "Bearer imp_" + "y" * 43}).text \
        == c.get("/laptop/agent.sh", headers={"Host": "b.example"}).text


def test_lines_form_of_the_check(server):
    from fastapi.testclient import TestClient
    c = TestClient(server.m.app)
    folder = c.post("/documents/import-laptop/token").json()["token"]
    assert c.get("/documents/import-laptop/check?form=lines", headers={"Authorization": f"Bearer {folder}"}).text == "state folder\n"
    sv = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    hd = {"Authorization": f"Bearer {sv}"}
    assert c.get("/documents/import-laptop/check?form=lines").status_code == 401
    assert c.get("/documents/import-laptop/check?form=lines", headers=hd).text == "state none\n"
    c.post("/documents/import-laptop/check", json={"files": [["Documents/a.md", 3, NOW], ["Music/b.wav", 9, NOW]]}, headers=hd)
    assert c.get("/documents/import-laptop/check?form=lines", headers=hd).text == "state waiting\n"
    c.post("/documents/import-laptop/plan", json={"take": "proposed"})
    lines = c.get("/documents/import-laptop/check?form=lines", headers=hd).text.splitlines()
    assert lines[0] == "state chosen" and sorted(lines[1:]) == ["files\tMusic/b.wav", "knowledge\tDocuments/a.md"]
    assert c.get("/documents/import-laptop/check", headers=hd).json()["plan"] == "chosen"  # JSON unchanged
    assert la.lines_form("chosen", {"paths": [["a\tb.md", "knowledge"], ["ok.md", "knowledge"]]}) == "state chosen\nknowledge\tok.md\n"


def test_never_send_rules_are_the_helpers_in_both_scripts():
    r = la.rules()
    sh = la.render("sh", "https://b.example/api/bf")
    ps = la.render("ps1", "https://b.example/api/bf")
    for d in h.SKIP_DIRS:
        assert f"'{d}'" in sh and f"'{d}'" in ps, d
    for p in h.SKIP_FILES:
        assert f"'{p}'" in ps, p
    for e in h.READABLE | h.AUDIO:
        assert f" {e} " in f" {' '.join(r['readable'])} {' '.join(r['audio'])} "
    assert str(h.MAX_FILE_BYTES) in sh and str(h.MAX_AUDIO_FILE_BYTES) in ps
    assert "@@" not in sh and "@@" not in ps


@pytest.mark.skipif(not shutil.which("awk"), reason="awk needed")
def test_secret_regex_in_awk_matches_fnmatch():
    names = ["id_rsa", "id_rsa.pub", "ID_ED25519", "server.pem", "x.key", "keys.txt", "my-passwords.txt", "pass.txt",
             "env.prod", "prod.env", "notes.md", "wallet.dat", "my seed phrase.txt", "seedphrase", "recovery codes.pdf",
             "cookies.sqlite", "cookbook.pdf", "a.kdbx", "tokenizer.py", "secretary.docx", "Inbox.mbox", "a.b.c",
             "x(1).md", "[draft].md", "plan^2.md", "a+b.txt", "c$d.txt"]
    want = [h.skip_file(n) == "secret" for n in names]
    assert want == [la.is_secret(n) for n in names]
    env = dict(os.environ, BA_SECRET_RE=la.rules()["secret_re"])
    r = subprocess.run(["awk", 'BEGIN { re = ENVIRON["BA_SECRET_RE"] } { print (tolower($0) ~ re ? 1 : 0) }'],
                       input="\n".join(names) + "\n", env=env, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stderr
    assert [x == "1" for x in r.stdout.split()] == want


def test_agent_scripts_hold_their_promises():
    """What the card says must be true in the scripts: dial-out only, one run, no install, no admin."""
    sh = (la.TEMPLATES["sh"]).read_text()
    ps = (la.TEMPLATES["ps1"]).read_text()
    for banned in ("sudo", "launchctl", "crontab", "LaunchAgents", "nc -l", "ssh ", "systemsetup", "tccutil", "osascript"):
        assert banned not in sh, banned
    for banned in ("Register-ScheduledTask", "New-Service", "Set-ExecutionPolicy", "Start-Process", "RunAs", "HttpListener",
                   "New-NetFirewallRule", "Set-ItemProperty", "Out-File", "Set-Content"):
        assert banned not in ps, banned
    assert 'trap cleanup EXIT' in sh and 'rm -rf "$TMP"' in sh and "main \"$@\"" in sh.rstrip().splitlines()[-1]
    assert "-H @\"$TMP/auth\"" in sh                         # the key never on curl's command line
    assert "Remove-Item Env:BRAIN_TOKEN" in ps and "finally" in ps


def test_bash_syntax_of_the_rendered_agent(tmp_path):
    if not BASH:
        pytest.skip("bash needed")
    p = tmp_path / "agent.sh"
    p.write_text(la.render("sh", "https://b.example/api/bf", "ru"))
    r = subprocess.run([BASH, "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_base_from_headers():
    assert la.base_from({"host": "b.example"}) == "https://b.example/api/bf"
    assert la.base_from({"host": "b.example:8443"}) == "https://b.example:8443/api/bf"
    assert la.base_from({"host": "127.0.0.1:5000"}) == "http://127.0.0.1:5000"
    assert la.base_from({"host": "api:8000", "x-forwarded-host": "c.example"}) == "https://c.example/api/bf"
    assert la.base_from({"host": "b.example", "x-forwarded-host": "evil.example"}) == "https://b.example/api/bf"
    for bad in ("", "a b", "b.example/x", "b.example@x", "-x.example", "x.example\r\nSet-Cookie: a"):
        assert la.base_from({"host": bad}) is None, bad


@needs_shell
def test_agent_sh_look_only_sends_nothing(server, tmp_path):
    """--look: the trial probe (which folders this computer lets Terminal read); no key, nothing sent."""
    home = tmp_path / "home"
    _home(home)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    r = _run_line(server.url, "--look", home, agent_tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Found 11 files" in r.stdout and "  Documents: 3" in r.stdout and "nothing was sent" in r.stdout
    assert server.m._LAPTOP_TOKENS.latest() is None and server.proposals == []
    assert list(agent_tmp.iterdir()) == []
