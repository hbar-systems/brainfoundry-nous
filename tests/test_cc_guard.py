"""A job's reasoner keeps the turn's permission shape (2026-10-19): scripts/cc/cc_guard.py."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shlex
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_guard as G  # noqa: E402

S = G.hook_settings("cards", "/usr/bin/python3", "/x/cc-permit-hook.py", "/x/cc-post-hook.py", 900)
Q = shlex.quote(S)


SS = " --setting-sources user"      # project and local layers are not merged (audit 2026-11-13)


@pytest.fixture(autouse=True)
def _default_sources(monkeypatch):
    monkeypatch.delenv("CC_SETTING_SOURCES", raising=False)


def test_hook_settings_shape():
    s = json.loads(S)
    assert s["hooks"]["PermissionRequest"][0]["hooks"][0]["command"] == "/usr/bin/python3 /x/cc-permit-hook.py"
    assert s["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"] == 960
    assert s["permissions"] == {"deny": G.DENY_ALWAYS}             # the .env rule rides with the hook (2026-11-13)
    assert json.loads(G.hook_settings("auto", "p", "h", "q", 1))["permissions"]["ask"] == G.ASK_ALWAYS


@pytest.mark.parametrize("cmd,want", [
    ("claude -p hi", f"claude --settings {Q}{SS} -p hi"),
    ("cd /srv && FOO=1 claude -p 'a b' | tee log", f"cd /srv && FOO=1 claude --settings {Q}{SS} -p 'a b' | tee log"),
    ("env -u X A=1 nohup timeout 10m /usr/local/bin/claude -p x",
     f"env -u X A=1 nohup timeout 10m /usr/local/bin/claude --settings {Q}{SS} -p x"),
    ("npx -y @anthropic-ai/claude-code -p z", f"npx -y @anthropic-ai/claude-code --settings {Q}{SS} -p z"),
    ("echo a; (claude -p one) && claude -p two",
     f"echo a; (claude --settings {Q}{SS} -p one) && claude --settings {Q}{SS} -p two"),
])
def test_injects_settings(cmd, want):
    assert G.check_job(cmd, "cards", S) == want


def test_auto_posture_reaches_the_job():
    assert G.check_job("claude -p hi", "auto", S) == f"claude --settings {Q}{SS} --permission-mode auto -p hi"
    assert G.check_job("claude --permission-mode plan -p hi", "auto", S) == f"claude --settings {Q}{SS} --permission-mode plan -p hi"
    assert G.check_job("claude -p hi", "cards", S) == f"claude --settings {Q}{SS} -p hi"
    assert G.check_job("claude -p hi", "auto", None) == "claude -p hi"


def test_injects_inside_sh_c():
    out = G.check_job("""bash -lc 'cd x && claude -p "hi there"'""", "cards", S)
    inner = shlex.split(out)[2]
    assert inner == f'cd x && claude --settings {Q}{SS} -p "hi there"'


@pytest.mark.parametrize("cmd", ["grep claude notes.md", "ls ~/.claude", "git commit -m 'claude -p in words'",
                                 'echo "$(date)" ${A:+--x "$B"}', "python3 -m pytest -q"])
def test_leaves_other_commands_alone(cmd):
    assert G.check_job(cmd, "cards", S) == cmd


def test_box_off_injects_nothing_but_still_refuses():
    assert G.check_job("claude -p hi", "cards", None) == "claude -p hi"
    with pytest.raises(G.Refused):
        G.check_job("claude --dangerously-skip-permissions -p hi", "auto", None)


@pytest.mark.parametrize("posture", ["cards", "auto", "judged"])
@pytest.mark.parametrize("cmd", [
    "claude --dangerously-skip-permissions -p x",
    "claude --allow-dangerously-skip-permissions -p x",
    "claude --permission-mode bypassPermissions -p x",
    "claude --permission-mode=bypassPermissions -p x",
    "sh -c 'claude --dangerously-skip-permissions -p x'",
    "echo $(claude -p x)",
    'echo "`claude -p x`"',
    "echo x | xargs claude -p",
    "claude --settings /tmp/loose.json -p x",
    "claude --permission-mode $MODE -p x",
])
def test_always_refused(posture, cmd):
    with pytest.raises(G.Refused):
        G.check_job(cmd, posture, S)


@pytest.mark.parametrize("cmd", [
    "claude --permission-mode auto -p x",
    "claude --permission-mode=acceptEdits -p x",
    "FOO=1 bash -c 'claude --permission-mode auto -p x'",
    "claude --allowedTools Bash -p x",
])
def test_loose_modes_need_the_auto_posture(cmd):
    for posture in ("cards", "judged", "nonsense"):
        with pytest.raises(G.Refused, match="auto posture"):
            G.check_job(cmd, posture, S)
    assert "--settings" in G.check_job(cmd, "auto", S)


def test_plain_modes_pass_in_every_posture():
    for posture in G.POSTURES:
        assert G.check_job("claude --permission-mode plan -p x", posture, S).startswith("claude --settings ")


def _agents(monkeypatch, tmp_path, posture):
    spec = importlib.util.spec_from_file_location("cc_agents_g", ROOT / "scripts" / "cc" / "cc_agents.py")
    ag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ag)
    monkeypatch.setattr(ag, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setenv("CC_POSTURE", posture)
    a = ag.create({"name": "Disk watch", "mission": "Check disk and backups, propose fixes.", "ground": str(tmp_path / "work"),
                   "every_minutes": 60, "budget_usd": 1})
    d = tmp_path / "agents" / a["id"]
    sp = d / "settings.json"
    sp.write_text(json.dumps(ag.settings(a)))
    return ag.job_command(a, d / "prompt.md", sp), sp


def _agent_ok(tmp_path):
    return lambda p: G.agent_settings_path_ok(p, tmp_path / "agents") and G.agent_settings_ok(pathlib.Path(p).read_text())


@pytest.mark.parametrize("posture", ["cards", "auto"])
def test_agents_command_line_still_accepted(monkeypatch, tmp_path, posture):
    line, _ = _agents(monkeypatch, tmp_path, posture)
    assert G.check_job(line, posture, S, _agent_ok(tmp_path)) == line      # kept as written, nothing injected


def test_agents_settings_must_carry_the_hook(monkeypatch, tmp_path):
    line, sp = _agents(monkeypatch, tmp_path, "cards")
    s = json.loads(sp.read_text())
    s["permissions"]["defaultMode"] = "bypassPermissions"
    sp.write_text(json.dumps(s))
    with pytest.raises(G.Refused):
        G.check_job(line, "cards", S, _agent_ok(tmp_path))
    s = json.loads(sp.read_text())
    del s["permissions"]["defaultMode"]
    s["hooks"]["PermissionRequest"] = []
    sp.write_text(json.dumps(s))
    with pytest.raises(G.Refused):
        G.check_job(line, "cards", S, _agent_ok(tmp_path))


def test_agent_settings_path():
    assert G.agent_settings_path_ok("/home/h/agents/A-001/settings.json", "/home/h/agents")
    assert not G.agent_settings_path_ok("/home/h/agents/../x/settings.json", "/home/h/agents")
    assert not G.agent_settings_path_ok("/tmp/A-001/settings.json", "/home/h/agents")
    assert not G.agent_settings_path_ok("/home/h/agents/A-001/x/settings.json", "/home/h/agents")
    assert not G.agent_settings_path_ok("/home/h/agents/A-001/other.json", "/home/h/agents")


def test_setting_sources_pinned_and_refused_wider():
    """Audit 2026-11-13 (cc-bridge-claude-turn-trusts-hands-writable-settings-layers)."""
    assert G.setting_sources_args() == ["--setting-sources", "user"]
    with pytest.raises(G.Refused):
        G.check_job("claude --setting-sources user,project -p x", "cards", S)
    with pytest.raises(G.Refused):
        G.check_job("claude --setting-sources=local -p x", "cards", S)
    assert G.check_job("claude --setting-sources user -p x", "cards", S) == f"claude --settings {Q} --setting-sources user -p x"
    # an agent's own settings line gets the pin too when it lacks one
    ok = lambda path: path == "/a/x/settings.json"
    assert G.check_job("claude --settings /a/x/settings.json -p x", "cards", S, ok) == \
        "claude --setting-sources user --settings /a/x/settings.json -p x"


def test_setting_sources_owner_override(monkeypatch):
    monkeypatch.setenv("CC_SETTING_SOURCES", "user,project")
    assert G.setting_sources_args() == ["--setting-sources", "user,project"]
    monkeypatch.setenv("CC_SETTING_SOURCES", "off")
    assert G.setting_sources_args() == []
