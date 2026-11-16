"""The spoke's box side (SPOKE-2A, 2026-11-14): spoke_config.py, spoke-install.sh (dry run and undo dry run
change nothing), spoke-door.sh against fake tailscale/headscale and an ssh that runs the laptop's real door.sh
on a scratch home, the bridge's /spoke door (cards for organise on and apply, never remembered, never judged),
cc-job spoke, and the laptop's network name. No network, no sudo."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOX = ROOT / "scripts" / "spoke" / "box"
sys.path.insert(0, str(BOX))
import spoke_config as SC  # noqa: E402


# ---- spoke_config.py ----

def test_ports_stay_out_of_member_blocks():
    for n in range(1, 100):
        p = SC.ports(n)
        assert p["socks"] == 8100 + 10 * n + 9                       # the member block's spare +9
        assert all(9100 <= p[k] < 9100 + 1000 for k in ("hs_http", "hs_metrics", "hs_grpc"))
    seen = [v for n in range(1, 100) for v in SC.ports(n).values()]
    assert len(seen) == len(set(seen))
    single = {8010, 3010, 8001, 54332, 3020, 11435, 7681, 7682}
    assert not single & set(seen)


@pytest.mark.parametrize("bad", ["", "a", "Paul", "paul-x", "1paul", "paul;rm", "a" * 17])
def test_handle_refused(bad):
    assert not SC.handle_ok(bad)
    assert SC.main(["config", bad, "1"]) == 2


def test_config_is_local_only_and_names_the_site():
    c = SC.config("paul", 1)
    assert "server_url: https://spoke.paul.brainfoundry.ai" in c
    for k in ("listen_addr", "metrics_listen_addr", "grpc_listen_addr"):
        line = next(l for l in c.splitlines() if l.startswith(k + ":"))
        assert line.split(": ")[1].startswith("127.0.0.1:")
    assert "/run/headscale/paul/headscale.sock" in c and "magic_dns: false" in c


def test_policy_brain_to_laptop_ssh_only():
    p = json.loads(SC.policy("paul"))
    assert p["acls"] == [{"action": "accept", "src": ["tag:brain"], "dst": ["paul@:22"]}]
    assert p["tagOwners"] == {"tag:brain": ["paul@"]}


def test_sudoers_line_names_every_verb_and_no_shell():
    s = SC.sudoers("paul")
    line = [l for l in s.splitlines() if not l.startswith("#")][0]
    assert line.startswith("paul-cc ALL=(paul-spoke) NOPASSWD: ")
    cmds = line.split("NOPASSWD: ", 1)[1].split(", ")
    assert all(c.startswith("/usr/local/sbin/spoke-door paul ") for c in cmds)
    verbs = {c.split(" ", 2)[2] for c in cmds}
    assert verbs == {"status", "inventory", "plan", "apply", "leave", "fingerprint", "bundle",
                     "organise on", "organise off", "undo *",
                     "bundle en", "bundle ru", "move-in", "move-in-status"}          # SWITCH-1, 2026-11-16
    assert SC.sudoers("hbar", "cc").startswith("# The spoke door of hbar")
    with pytest.raises(ValueError):
        SC.sudoers("paul", "bad user")


def test_caddy_block_proxies_the_local_port():
    c = SC.caddy("elena", 3)
    assert "spoke.elena.brainfoundry.ai {" in c and "reverse_proxy 127.0.0.1:9130" in c


def test_write_refuses_system_folders(tmp_path):
    assert SC.main(["write", "paul", "1", "/etc/headscale/paul"]) == 2
    assert SC.main(["write", "paul", "1", str(tmp_path / "s")]) == 0
    assert sorted(p.name for p in (tmp_path / "s").iterdir()) == ["Caddyfile.spoke", "config.yaml", "policy.json", "spoke.env", "sudoers"]


def test_env_console_must_be_https():
    assert SC.main(["env", "paul", "1", "--console", "http://x"]) == 2
    assert "CONSOLE_URL=https://console.paul.brainfoundry.ai" in SC.env("paul", 1)


# ---- spoke-install.sh ----

def _fakebin(tmp_path, names, log):
    b = tmp_path / "fakebin"
    b.mkdir(exist_ok=True)
    for n in names:
        f = b / n
        f.write_text(f"#!/bin/bash\necho \"{n} $*\" >> {log}\nexit 0\n")
        f.chmod(0o755)
    return b


def test_install_dry_run_changes_nothing(tmp_path):
    log = tmp_path / "calls.log"
    b = _fakebin(tmp_path, ["sudo", "systemctl", "useradd", "headscale", "tailscale", "caddy", "visudo"], log)
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "SPOKE_CADDYFILE": str(tmp_path / "Caddyfile")}
    (tmp_path / "Caddyfile").write_text("a.example {\n}\n")
    r = subprocess.run(["bash", str(BOX / "spoke-install.sh"), "paul", "--block", "1", "--dry-run"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "dry run: nothing is changed" in r.stdout and "Dry run: nothing was changed" in r.stdout
    assert not log.exists(), log.read_text()                         # no sudo, systemctl, headscale call ran
    assert (tmp_path / "Caddyfile").read_text() == "a.example {\n}\n"
    for want in ("useradd --system", "/etc/sudoers.d/spoke-paul", "spoke.paul.brainfoundry.ai", "headscale@paul", "spoke-node@paul",
                 "Caddyfile.bak-spoke-paul-", "127.0.0.1:9110"):
        assert want in r.stdout, want


def test_undo_dry_run_moves_aside_never_deletes(tmp_path):
    log = tmp_path / "calls.log"
    b = _fakebin(tmp_path, ["sudo"], log)
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(BOX / "spoke-install.sh"), "paul", "--block", "1", "--undo"],
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert not log.exists()
    cmds = [l for l in r.stdout.splitlines() if l.startswith("+ ")]
    assert cmds and not any(" rm " in l or "userdel" in l or "rm -" in l for l in cmds)
    assert any("mv /var/lib/spoke/paul /var/backups/spoke-paul-" in l for l in cmds)


def test_apply_refuses_the_wrong_host(tmp_path):
    r = subprocess.run(["bash", str(BOX / "spoke-install.sh"), "paul", "--block", "1", "--apply", "--host", "not-this-box-xyz"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "STOPPED: this is" in r.stdout


def test_install_bad_args():
    for a in (["Paul", "--block", "1"], ["paul", "--block", "100"], ["paul"]):
        r = subprocess.run(["bash", str(BOX / "spoke-install.sh"), *a], capture_output=True, text=True, timeout=30)
        assert r.returncode == 2


# ---- spoke-door.sh, end to end against the laptop's real door.sh ----

@pytest.fixture
def rig(tmp_path):
    """A box side (etc, var, fake tailscale/headscale/ssh/nc) and a laptop home with .brain-spoke."""
    etc, var, home = tmp_path / "etc", tmp_path / "var", tmp_path / "home"
    etc.mkdir(); (var / "key").mkdir(parents=True); home.mkdir()
    (etc / "paul.env").write_text(SC.env("paul", 1))
    d = home / ".brain-spoke"; d.mkdir()
    for f in ("door.sh", "inventory.sh"):
        shutil.copy(ROOT / "scripts" / "spoke" / f, d / f)
    (d / "mode").write_text("look\n")
    (home / "Documents").mkdir(); (home / "Documents" / "a.pdf").write_text("x" * 100)
    (home / "Downloads").mkdir(); (home / "Downloads" / "b.pdf").write_text("y")
    (home / ".ssh").mkdir(); (home / ".ssh" / "authorized_keys").write_text("ssh-ed25519 AAAA other\nfrom=\"x\" ssh-ed25519 BBBB brain-spoke:paul\n")
    b = tmp_path / "bin"; b.mkdir()
    state = tmp_path / "online"; state.write_text("true")
    (b / "tailscale").write_text(f"""#!/bin/bash
case "$*" in
  *"status --json"*) echo '{{"Peer": {{"k1": {{"HostName": "paul-laptop--friend", "TailscaleIPs": ["100.64.0.2", "fd7a::2"], "Online": '$(cat {state})', "LastSeen": "2026-11-14T01:00:00Z"}}}}}}' ;;
  *"ip -4"*) echo 100.64.0.1 ;;
esac
""")
    (b / "headscale").write_text(f"""#!/bin/bash
echo "headscale $*" >> {tmp_path}/hs.log
case "$*" in
  *"users list"*) echo '[{{"id": 7, "name": "paul"}}]' ;;
  *"nodes list"*) echo '[{{"id": 3, "given_name": "paul-laptop--friend"}}, {{"id": 1, "given_name": "paul-brain"}}]' ;;
  *"preauthkeys create"*) echo '{{"key": "hskey-auth-0123456789abcdef"}}' ;;
esac
""")
    # the ssh hop: run the laptop's door.sh as its forced command, the way sshd would
    (b / "ssh").write_text(f"""#!/bin/bash
echo "ssh $*" >> {tmp_path}/ssh.log
cmd="${{@: -1}}"
HOME={home} SSH_ORIGINAL_COMMAND="$cmd" exec bash {d}/door.sh
""")
    for f in b.iterdir():
        f.chmod(0o755)
    return {"tmp": tmp_path, "etc": etc, "var": var, "home": home, "bin": b, "online": state}


def sdoor(rig, verb, *args, stdin=""):
    env = {"PATH": os.environ["PATH"], "SPOKE_DOOR_TEST": "1", "SPOKE_TEST_BIN": str(rig["bin"]),
           "SPOKE_ETC": str(rig["etc"]), "SPOKE_VAR": str(rig["var"]), "SPOKE_SHARE": str(ROOT / "scripts" / "spoke"),
           "HOME": str(rig["tmp"])}
    return subprocess.run(["bash", str(BOX / "spoke-door.sh"), "paul", verb, *args], env=env, input=stdin,
                          capture_output=True, text=True, timeout=120)


def test_door_refuses_wrong_user_without_test_flag(rig):
    r = subprocess.run(["bash", str(BOX / "spoke-door.sh"), "paul", "status"], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"], "SPOKE_VAR": str(rig["var"]), "SPOKE_ETC": str(rig["etc"])})
    assert r.returncode == 3 and "runs as paul-spoke" in r.stderr


def test_door_status_sees_the_laptop_and_its_mode(rig):
    r = sdoor(rig, "status")
    assert r.returncode == 0, r.stderr
    assert "laptop\tpaul-laptop--friend\t100.64.0.2\tonline" in r.stdout and "mode\tlook" in r.stdout
    ssh = (rig["tmp"] / "ssh.log").read_text()
    assert "friend@100.64.0.2" in ssh and "nc -X 5 -x 127.0.0.1:8119" in ssh and "BatchMode=yes" in ssh


def test_door_asleep_laptop_refused_for_inventory(rig):
    rig["online"].write_text("false")
    r = sdoor(rig, "status")
    assert "asleep" in r.stdout
    r = sdoor(rig, "inventory")
    assert r.returncode == 3 and "asleep" in r.stderr


def test_door_inventory_kept_and_no_names(rig):
    r = sdoor(rig, "inventory")
    assert r.returncode == 0, r.stderr
    latest = rig["var"] / "inventory" / "latest.tsv"
    assert latest.is_symlink() and latest.read_text() == r.stdout
    assert "a.pdf" not in r.stdout and "b.pdf" not in r.stdout
    assert "meta\tfinished" in r.stdout


@pytest.mark.parametrize("plan,why", [
    ("rm\tDownloads/b.pdf\n", "only mkdir and mv"),
    ("mv\tDownloads/b.pdf\t/tmp/x\n", "path"),
    ("mv\t../x\tDocuments/x\n", "path"),
    ("mkdir\tLibrary/Mail/x\n", "path"),
    ("mkdir\t.ssh/x\n", "path"),
    ("mkdir\tDocuments/PDFs\textra\n", "one folder"),
    ("", "empty plan"),
])
def test_door_plan_refusals_never_reach_the_laptop(rig, plan, why):
    r = sdoor(rig, "apply", stdin=plan)
    assert r.returncode == 3 and why in r.stderr
    assert not (rig["tmp"] / "ssh.log").exists()
    assert "REFUSED" in (rig["var"] / "door.log").read_text()


def test_door_plan_checks_without_touching_the_laptop(rig):
    r = sdoor(rig, "plan", stdin="mkdir\tDocuments/PDFs\nmv\tDownloads/b.pdf\tDocuments/PDFs/b.pdf\n")
    assert r.returncode == 0 and "1 folders\t1 moves" in r.stdout
    assert not (rig["tmp"] / "ssh.log").exists()
    assert (rig["home"] / "Downloads" / "b.pdf").exists()


def test_door_organise_apply_undo_round_trip(rig):
    plan = "mkdir\tDocuments/PDFs\nmv\tDownloads/b.pdf\tDocuments/PDFs/b.pdf\n"
    r = sdoor(rig, "apply", stdin=plan)
    assert r.returncode != 0 and "organise" in (r.stderr + r.stdout)          # the laptop is in look mode
    assert sdoor(rig, "organise", "on").returncode == 0
    r = sdoor(rig, "apply", stdin=plan)
    assert r.returncode == 0, r.stderr
    assert (rig["home"] / "Documents" / "PDFs" / "b.pdf").exists() and not (rig["home"] / "Downloads" / "b.pdf").exists()
    uid = r.stdout.strip().rsplit(" ", 1)[1]
    assert sdoor(rig, "undo", "x; rm -rf /").returncode == 3
    r = sdoor(rig, "undo", uid)
    assert r.returncode == 0, r.stderr
    assert (rig["home"] / "Downloads" / "b.pdf").exists() and not (rig["home"] / "Documents" / "PDFs").exists()
    assert sdoor(rig, "organise", "maybe").returncode == 3


def test_door_leave_removes_key_line_and_node(rig):
    r = sdoor(rig, "leave")
    assert r.returncode == 0, r.stderr
    assert "brain-spoke:" not in (rig["home"] / ".ssh" / "authorized_keys").read_text()
    assert "other" in (rig["home"] / ".ssh" / "authorized_keys").read_text()
    hs = (rig["tmp"] / "hs.log").read_text()
    assert "nodes delete --identifier 3 --force" in hs and "--identifier 1" not in hs


def test_door_unknown_verb_and_words(rig):
    assert sdoor(rig, "shell").returncode == 3
    assert sdoor(rig, "status", "extra").returncode == 3
    assert sdoor(rig, "inventory", "--all").returncode == 3


@pytest.mark.skipif(not shutil.which("ssh-keygen") or not shutil.which("sha256sum"), reason="ssh-keygen and sha256sum needed")
def test_door_bundle_signs_a_zip_with_a_one_hour_key(rig):
    for k in ("door", "signing"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(rig["var"] / "key" / k)], check=True)
    r = sdoor(rig, "bundle")
    assert r.returncode == 0, r.stderr
    kv = dict(l.split("\t", 1) for l in r.stdout.splitlines())
    z = pathlib.Path(kv["bundle"])
    assert z.name == "join-my-brain-paul.zip" and stat.S_IMODE(z.stat().st_mode) == 0o640
    assert kv["signing"].startswith("SHA256:")
    assert "preauthkeys create --user 7 --expiration 1h" in (rig["tmp"] / "hs.log").read_text()
    assert not (rig["var"] / "tmp" / "authkey").exists()                  # the key file does not stay
    import zipfile
    with zipfile.ZipFile(z) as zf:
        s = zf.read("Join my brain.app/Contents/Resources/spoke.sh").decode()     # the app since SWITCH-1
    assert 'AUTHKEY="hskey-auth-0123456789abcdef"' in s and 'BRAIN_IP="100.64.0.1"' in s
    assert 'LOGIN_SERVER="https://spoke.paul.brainfoundry.ai"' in s


# ---- the laptop's network name ----

def test_laptop_name_carries_the_user():
    s = (ROOT / "scripts" / "spoke" / "spoke.sh").read_text()
    assert '--hostname="$HANDLE-laptop--$me"' in s


# ---- the bridge ----

def _bridge(monkeypatch, tmp_path, on=True):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_SPOKE", "1" if on else "")
    monkeypatch.setenv("CC_SPOKE_HANDLE", "paul")
    monkeypatch.setenv("CC_SPOKE_VAR", str(tmp_path / "spoke"))
    spec = importlib.util.spec_from_file_location("cc_bridge", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge"] = mod
    spec.loader.exec_module(mod)
    return mod


class _Door:
    def __init__(self, rc=0, out="ok\n"):
        self.calls, self.rc, self.out = [], rc, out

    def __call__(self, verb, args, stdin):
        self.calls.append((verb, list(args), stdin))
        return self.rc, self.out, ""


def test_bridge_off_says_why(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, on=False)
    code, d = m._spoke({"verb": "status"}, door=_Door())
    assert code == 409 and "CC_SPOKE=1" in d["error"]


def test_bridge_status_runs_without_a_card(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    door, asks = _Door(), []
    code, d = m._spoke({"verb": "status"}, ask=lambda *a: asks.append(a) or {"behavior": "allow"}, door=door)
    assert code == 200 and door.calls == [("status", [], None)] and not asks


@pytest.mark.parametrize("body", [
    {"verb": "shell"}, {"verb": "organise", "args": ["maybe"]}, {"verb": "undo", "args": ["x;y"]},
    {"verb": "status", "args": ["x"]}, {"verb": "apply", "plan": "rm\tDownloads/x\n"},
    {"verb": "apply", "plan": "mv\tDownloads/x\t../y\n"}, {"verb": "apply", "plan": "mkdir\tLibrary/x\n"},
    {"verb": "apply", "plan": "mkdir\tdocs/.hidden\n"}, {"verb": "plan", "plan": ""},
])
def test_bridge_refuses_before_any_card(monkeypatch, tmp_path, body):
    m = _bridge(monkeypatch, tmp_path)
    door, asks = _Door(), []
    code, d = m._spoke(body, ask=lambda *a: asks.append(a) or {"behavior": "allow"}, door=door)
    assert code == 400 and not door.calls and not asks


def test_bridge_organise_on_and_apply_ask_first(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    for body in ({"verb": "organise", "args": ["on"]}, {"verb": "apply", "plan": "mkdir\tDocuments/PDFs\nmv\tDownloads/a.pdf\tDocuments/PDFs/a.pdf\n"}):
        door, asks = _Door(), []
        code, d = m._spoke(body, ask=lambda *a: asks.append(a) or {"behavior": "deny", "message": "the person refused this action"}, door=door)
        assert code == 403 and not door.calls and asks and asks[0][0] == "spoke"
        door, asks = _Door(), []
        code, d = m._spoke(body, ask=lambda *a: asks.append(a) or {"behavior": "allow"}, door=door)
        assert code == 200 and len(door.calls) == 1
    assert door.calls[0][2] == "mkdir\tDocuments/PDFs\nmv\tDownloads/a.pdf\tDocuments/PDFs/a.pdf\n"


def test_bridge_organise_off_and_undo_need_no_card(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    for body in ({"verb": "organise", "args": ["off"]}, {"verb": "undo", "args": ["20261114T010203Z"]}, {"verb": "plan", "plan": "mkdir\tDocuments/X\n"}):
        door, asks = _Door(), []
        code, _ = m._spoke(body, ask=lambda *a: asks.append(a) or {"behavior": "deny"}, door=door)
        assert code == 200 and not asks and door.calls


def test_spoke_cards_never_remembered_never_judged(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    inp = m._spoke_card("apply", [], [["mkdir", "Documents/PDFs"]] + [["mv", f"Downloads/{i}.pdf", f"Documents/PDFs/{i}.pdf"] for i in range(20)])
    aid, summary, remember = m._box_key("spoke", inp)
    assert remember is False and aid == "spoke apply"
    assert "1 new folders, 20 moves" in summary and "Nothing is deleted" in summary and "9 more lines" in summary
    assert "new folder Documents/PDFs" in summary and "move Downloads/0.pdf  ->  Documents/PDFs/0.pdf" in summary
    aid, summary, remember = m._box_key("spoke", m._spoke_card("organise", ["on"], []))
    assert remember is False and "Let your brain organise this laptop?" in summary
    assert "spoke" in m.BOX_ALWAYS_ASK and "orfeo_post" in m.BOX_ALWAYS_ASK
    assert not m._codex_auto_allows("spoke", inp)


def test_bridge_apply_card_reaches_the_page_with_the_full_plan(monkeypatch, tmp_path):
    """Through the real ask path: a card on the watching run, the whole plan as 'full', no checkbox."""
    import threading
    import time
    m = _bridge(monkeypatch, tmp_path)

    class _Gate:
        def call(self, *_a, **_k):
            return type("R", (), {"permit": {"id": "p-spoke-1", "ttl_seconds": 60}, "error": None, "reason": None})()

        def get(self, pid):
            return {}

        def deny(self, pid):
            pass

    monkeypatch.setattr(m, "BOX_ENABLED", True)
    monkeypatch.setattr(m, "GATE", _Gate())
    monkeypatch.setattr(m, "_posture_current", lambda: "judged")
    monkeypatch.setattr(m, "_judge", lambda *a: pytest.fail("a spoke card is never judged"))
    monkeypatch.setattr(m, "_decision_log", lambda *a, **k: None)
    monkeypatch.setattr(m, "_run_permit", lambda *a: "ok")
    cards = []

    class _Run:
        id, done, waiting, allowed = "r1", False, 0, set()

        def emit(self, kind, card):
            cards.append(card)
    run = _Run()
    monkeypatch.setitem(m.RUNS, "r1", run)
    door = _Door()
    out = {}
    plan = "mkdir\tDocuments/PDFs\nmv\tDownloads/a.pdf\tDocuments/PDFs/a.pdf\n"
    th = threading.Thread(target=lambda: out.setdefault("r", m._spoke({"verb": "apply", "plan": plan, "run": "r1"}, door=door)))
    th.start()
    for _ in range(100):
        if cards:
            break
        time.sleep(0.02)
    assert cards and cards[0]["method"] == "spoke" and cards[0]["remember_ok"] is False
    assert cards[0]["full"] == plan.rstrip("\n")
    m._box_settle("p-spoke-1", "allow")
    th.join(5)
    assert out["r"][0] == 200 and door.calls and door.calls[0][0] == "apply"


def test_bridge_bundle_and_one_download(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    (tmp_path / "spoke" / "out").mkdir(parents=True)
    (tmp_path / "spoke" / "out" / "join-my-brain-paul.zip").write_bytes(b"PK zip")
    door = _Door(out=f"bundle\t{tmp_path}/spoke/out/join-my-brain-paul.zip\nsigning\tSHA256:abc\nexpires\t2026-11-14T02:00:00Z\n")
    code, d = m._spoke_bundle(door=door)
    assert code == 200 and d["fingerprint"] == "SHA256:abc" and d["url"].endswith("/spoke/download/join-my-brain-paul.zip")
    assert m._spoke_download("join-my-brain-paul.zip") == (200, b"PK zip")
    assert m._spoke_download("join-my-brain-paul.zip") == (404, None)     # once
    assert m._spoke_download("../../etc/passwd") == (404, None)
    code, d = m._spoke_bundle(door=_Door(out="bundle\t/etc/passwd\n"))
    assert code == 502


def test_bridge_state_reads_status_and_fingerprint(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)

    def door(verb, args, stdin):
        if verb == "status":
            return 0, "handle\tpaul\nbrain\t100.64.0.1\nlaptop\tpaul-laptop--friend\t100.64.0.2\tasleep\t2026-11-14T01:00:00Z\n", ""
        return 0, "signing\tSHA256:abc\n", ""
    code, d = m._spoke_state(door=door)
    assert code == 200 and d["ready"] and d["fingerprint"] == "SHA256:abc"
    assert d["status"]["laptop"]["state"] == "asleep" and d["inventory"] is False


# ---- cc-job spoke ----

def test_cc_job_spoke_posts_the_plan(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("cc_job", ROOT / "scripts" / "cc" / "cc-job.py")
    j = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(j)
    sent = []
    monkeypatch.setattr(j, "_call", lambda method, route, body=None, timeout=30: sent.append((route, body)) or {"ok": True, "out": "applied 2 steps; undo id 20261114T010203Z\n"})
    p = tmp_path / "plan.tsv"
    p.write_text("mkdir\tDocuments/PDFs\n")
    assert j.main(["spoke", "apply", "--plan", str(p)]) == 0
    assert sent[0][0] == "/spoke" and sent[0][1]["verb"] == "apply" and sent[0][1]["plan"] == "mkdir\tDocuments/PDFs\n"
    assert j.main(["spoke", "undo", "20261114T010203Z"]) == 0 and sent[1][1]["args"] == ["20261114T010203Z"]
    assert j.main(["spoke", "apply", "--plan"]) == 2
