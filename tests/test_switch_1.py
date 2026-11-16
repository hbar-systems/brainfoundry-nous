"""SWITCH-1 "Usher" (2026-11-16): the spoke for a person who never opens Terminal, and the first sign-in order.

- the laptop's door.sh move-in: organise mode only, the token on stdin (never argv, never logged), the home's
  own helper started detached against the brain address the join wrote;
- spoke-door move-in end to end through the fake ssh hop into the real door.sh;
- make-bundle.sh: one "Join my brain.app" in the zip, executable, plist readable, every file signed, the language;
- the app on a fake osascript: a swapped file stops it, "Not now" changes nothing;
- the en and ru words of the Mac side carry the same keys;
- the bridge: move-in over the spoke (organise on first, token on stdin), the reasoner's move-in is a card, the
  look returns counts, the bundle takes the console's language, the first-run state;
- ui/lib/firstRun.js and ui/lib/connectComputer.js under node.
No network, no sudo, no Mac (the real Mac run is in the SWITCH-1 report)."""
from __future__ import annotations

import json
import os
import pathlib
import plistlib
import shutil
import stat
import subprocess
import zipfile

import pytest

from tests.test_spoke_box import _bridge, _Door, rig, sdoor  # noqa: F401  (rig is a fixture)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPOKE = ROOT / "scripts" / "spoke"
TOKEN = "imp_" + "A" * 43


# ---- the laptop: door.sh move-in ----

@pytest.fixture
def lap(tmp_path):
    home = tmp_path / "home"; d = home / ".brain-spoke"; d.mkdir(parents=True)
    for f in ("door.sh", "inventory.sh"):
        shutil.copy(SPOKE / f, d / f)
    (d / "brain_import.py").write_text("# the helper\n")
    (d / "brain_url").write_text("https://console.paul.brainfoundry.ai/api/bf\n")
    (d / "mode").write_text("organise\n")
    b = tmp_path / "bin"; b.mkdir()
    # a python3 that writes down how it was started, then exits
    (b / "python3").write_text(f"""#!/bin/bash
printf 'argv=%s\\n' "$*" > {tmp_path}/py.txt
printf 'token=%s\\n' "${{BRAIN_IMPORT_TOKEN:-}}" >> {tmp_path}/py.txt
""")
    (b / "python3").chmod(0o755)
    return {"home": home, "d": d, "bin": b, "tmp": tmp_path}


def door(lap, *args, stdin=""):
    env = {"HOME": str(lap["home"]), "PATH": f"{lap['bin']}:/usr/bin:/bin"}
    return subprocess.run(["bash", str(lap["d"] / "door.sh"), *args], env=env, input=stdin,
                          capture_output=True, text=True, timeout=30)


def _wait_for(p: pathlib.Path):
    import time
    for _ in range(50):
        if p.exists() and "token=" in p.read_text():
            return p.read_text()
        time.sleep(0.1)
    raise AssertionError("the helper did not start")


def test_move_in_starts_the_helper_with_the_token_in_the_environment(lap):
    r = door(lap, "move-in", stdin=TOKEN + "\n")
    assert r.returncode == 0, r.stderr
    assert "move-in started" in r.stdout
    got = _wait_for(lap["tmp"] / "py.txt")
    assert f"token={TOKEN}" in got
    assert TOKEN not in got.split("token=")[0]                        # never on the command line
    assert "--survey --brain https://console.paul.brainfoundry.ai/api/bf" in got
    assert TOKEN not in (lap["d"] / "door.log").read_text()          # never in the log
    r = door(lap, "move-in", "status")
    assert r.returncode == 0 and r.stdout.splitlines()[0] in ("running", "not running")


@pytest.mark.parametrize("tok", ["", "imp_", "xyz_" + "A" * 40, "imp_" + "A" * 40 + ";rm", "imp_" + "A" * 80])
def test_move_in_refuses_a_bad_token(lap, tok):
    r = door(lap, "move-in", stdin=tok + "\n")
    assert r.returncode == 3 and not (lap["tmp"] / "py.txt").exists()


def test_move_in_needs_organise_and_a_brain_address(lap):
    (lap["d"] / "mode").write_text("look\n")
    assert door(lap, "move-in", stdin=TOKEN).returncode == 3
    assert "REFUSED" in (lap["d"] / "door.log").read_text()
    (lap["d"] / "mode").write_text("organise\n")
    (lap["d"] / "brain_url").write_text("http://evil.example\n")
    assert door(lap, "move-in", stdin=TOKEN).returncode == 3
    (lap["d"] / "brain_url").write_text("https://a.example/$(id)\n")
    assert door(lap, "move-in", stdin=TOKEN).returncode == 3
    (lap["d"] / "brain_url").unlink()
    assert door(lap, "move-in", stdin=TOKEN).returncode == 3
    assert door(lap, "move-in", "--all").returncode == 3
    assert not (lap["tmp"] / "py.txt").exists()


def test_helper_reads_the_token_from_the_environment():
    s = (ROOT / "scripts" / "import" / "brain_import.py").read_text()
    assert 'os.environ.get("BRAIN_IMPORT_TOKEN")' in s


# ---- the box: spoke-door move-in through the ssh hop ----

def test_spoke_door_move_in_reaches_the_laptop(rig):
    d = rig["home"] / ".brain-spoke"
    (d / "mode").write_text("organise\n")
    (d / "brain_url").write_text("https://console.paul.brainfoundry.ai/api/bf\n")
    (d / "brain_import.py").write_text("import time\n")
    r = sdoor(rig, "move-in", stdin="not-a-token\n")
    assert r.returncode == 3 and "move-in token" in r.stderr
    assert sdoor(rig, "move-in", "extra", stdin=TOKEN).returncode == 3
    r = sdoor(rig, "move-in", stdin=TOKEN + "\n")
    assert r.returncode == 0, r.stderr
    assert "move-in started" in r.stdout
    assert TOKEN not in (rig["tmp"] / "ssh.log").read_text()          # not on the ssh line either
    assert TOKEN not in (rig["var"] / "door.log").read_text()
    r = sdoor(rig, "move-in-status")
    assert r.returncode == 0 and r.stdout.splitlines()[0] in ("running", "not running")


def test_spoke_door_bundle_language(rig):
    assert sdoor(rig, "bundle", "de").returncode == 3
    assert sdoor(rig, "bundle", "en", "ru").returncode == 3


# ---- make-bundle.sh: the app ----

@pytest.fixture
def bundle(tmp_path):
    if not shutil.which("ssh-keygen") or not shutil.which("sha256sum"):
        pytest.skip("ssh-keygen and sha256sum needed")
    for k in ("sign", "door"):
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / k)], check=True)
    (tmp_path / "ak").write_text("hskey-auth-0123456789abcdef\n")

    def make(lang="ru"):
        out = tmp_path / ("out-" + lang)
        r = subprocess.run(["bash", str(SPOKE / "make-bundle.sh"), "--handle", "elena", "--console", "https://console.elena.brainfoundry.ai",
                            "--login-server", "https://spoke.elena.brainfoundry.ai", "--authkey-file", str(tmp_path / "ak"),
                            "--brain-ip", "100.64.0.1", "--brain-pubkey", str(tmp_path / "door.pub"), "--signing-key", str(tmp_path / "sign"),
                            "--out", str(out), "--lang", lang], capture_output=True, text=True, timeout=60)
        return r, out / "join-my-brain-elena.zip"
    return make


def test_bundle_is_one_signed_app(bundle, tmp_path):
    r, z = bundle("ru")
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert all(n.startswith("Join my brain.app/Contents/") for n in names)       # one thing in Downloads
        modes = {i.filename: (i.external_attr >> 16) for i in zf.infolist()}
        assert modes["Join my brain.app/Contents/MacOS/join-my-brain"] & 0o111
        pl = plistlib.loads(zf.read("Join my brain.app/Contents/Info.plist"))
        assert pl["CFBundleExecutable"] == "join-my-brain" and pl["LSMinimumSystemVersion"] == "13.0"
        res = "Join my brain.app/Contents/Resources/"
        for f in ("spoke.sh", "door.sh", "inventory.sh", "brain_import.py", "words.sh", "lang", "SHA256SUMS", "SHA256SUMS.sig",
                  "allowed_signers", "allowed_signers.pub", "Join my brain.command", "WHAT-THIS-DOES.txt"):
            assert res + f in names, f
        assert zf.read(res + "lang").decode().strip() == "ru"
        sp = zf.read(res + "spoke.sh").decode()
        assert 'SPOKE_LANG="ru"' in sp and "@@" not in sp.split("set -u", 1)[1].split('D="$HOME', 1)[0]
        sums = zf.read(res + "SHA256SUMS").decode()
        for f in ("../Info.plist", "../MacOS/join-my-brain", "brain_import.py", "words.sh", "lang", "spoke.sh"):
            assert f in sums, f
        zf.extractall(tmp_path / "x")
    rd = tmp_path / "x" / "Join my brain.app" / "Contents" / "Resources"
    v = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", "allowed_signers", "-I", "brain", "-n", "brain-spoke", "-s", "SHA256SUMS.sig"],
                       cwd=rd, input=(rd / "SHA256SUMS").read_text(), capture_output=True, text=True)
    assert v.returncode == 0, v.stderr
    assert subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=rd, capture_output=True).returncode == 0


def test_bundle_refuses_other_languages(bundle):
    r, _ = bundle("de")
    assert r.returncode == 2 and "lang" in r.stderr


def _fake_mac(tmp_path, press="last"):
    b = tmp_path / "fb"; b.mkdir(exist_ok=True)
    (b / "osascript").write_text(f"""#!/bin/bash
printf '%s\\n' "$*" | tr '\\n' ' ' >> {tmp_path}/dialogs.log; echo >> {tmp_path}/dialogs.log
eval "last=\\${{$#}}"
[ "{press}" = last ] && echo "$last" || echo "{press}"
""")
    (b / "open").write_text(f"#!/bin/bash\necho \"open $*\" >> {tmp_path}/open.log\n")
    if not shutil.which("shasum"):
        (b / "shasum").write_text("#!/bin/bash\nshift 2; exec sha256sum \"$@\"\n")
    for f in b.iterdir():
        f.chmod(0o755)
    return b


def _run_app(tmp_path, app, b):
    home = tmp_path / "h"; home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "PATH": f"{b}:{os.environ['PATH']}"}
    return subprocess.run(["bash", str(app / "Contents" / "MacOS" / "join-my-brain")], env=env, capture_output=True, text=True, timeout=60), home


def test_app_stops_on_a_swapped_file(bundle, tmp_path):
    r, z = bundle("en")
    zipfile.ZipFile(z).extractall(tmp_path / "x")
    app = tmp_path / "x" / "Join my brain.app"
    with open(app / "Contents" / "Resources" / "door.sh", "a") as f:
        f.write("\n# swapped\n")
    r, home = _run_app(tmp_path, app, _fake_mac(tmp_path))
    assert r.returncode == 1
    assert "not the ones your brain signed" in (tmp_path / "dialogs.log").read_text()
    assert not (home / ".brain-spoke").exists()


def test_app_not_now_changes_nothing(bundle, tmp_path):
    r, z = bundle("ru")
    zipfile.ZipFile(z).extractall(tmp_path / "x")
    app = tmp_path / "x" / "Join my brain.app"
    r, home = _run_app(tmp_path, app, _fake_mac(tmp_path, press="Не сейчас"))
    assert r.returncode == 0, r.stderr
    log = (tmp_path / "dialogs.log").read_text()
    assert "Мозг подключится" in log and "SHA256:" in log           # the intro in her language, with the key
    assert not (home / ".brain-spoke").exists() and not (home / ".ssh").exists()


def test_app_join_off_a_mac_stops_with_its_words(bundle, tmp_path):
    r, z = bundle("en")
    zipfile.ZipFile(z).extractall(tmp_path / "x")
    r, home = _run_app(tmp_path, tmp_path / "x" / "Join my brain.app", _fake_mac(tmp_path))   # presses Join
    assert r.returncode == 0
    assert "Stopped: this program is for a Mac" in (tmp_path / "dialogs.log").read_text()
    assert not (home / ".brain-spoke").exists()
    assert "== exit 1" in (home / "Library" / "Logs" / "join-my-brain.log").read_text()


def test_words_carry_every_key_in_both_languages():
    import re
    s = (SPOKE / "words.sh").read_text()
    keys = sorted(set(re.findall(r"(?:^\s+|;; )([a-z_]+)\)", s.split("w() {", 1)[1].split("\ndialog()", 1)[0], re.M)))
    assert len(keys) >= 20
    for lang in ("en", "ru"):
        r = subprocess.run(["bash", "-c", '. "$0"; for k in "$@"; do printf "%s=%s\\n" "$k" "$(w "$k" X)"; done', str(SPOKE / "words.sh"), *keys],
                           env={"SPOKE_LANG": lang, "PATH": os.environ["PATH"]}, capture_output=True, text=True, timeout=30)
        got = dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l and not l.startswith(" "))
        for k in keys:
            assert got.get(k) and got[k] != k, (lang, k)                 # a real sentence, not the key echoed back


def test_spoke_dry_run_writes_the_brain_address_and_asks_for_tools():
    r = subprocess.run(["bash", str(SPOKE / "spoke.sh"), "join", "--dry-run"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "brain_url" in r.stdout and "Apple's developer tools" in r.stdout
    assert "Leave my brain.app" in r.stdout


# ---- the bridge ----

def test_bridge_move_in_organise_first_token_on_stdin(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    d = _Door(out="move-in started\n")
    code, j = m._spoke_move_in(TOKEN, door=d)
    assert code == 200 and j["started"]
    assert d.calls == [("organise", ["on"], None), ("move-in", [], TOKEN + "\n")]
    for bad in ("", "imp_x", "imp_" + "A" * 43 + "\nmore", "x" * 50):
        assert m._spoke_move_in(bad, door=_Door())[0] == 400


def test_bridge_reasoner_move_in_is_a_card_and_mints(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    asks, d = [], _Door()
    code, j = m._spoke({"verb": "move-in"}, ask=lambda *a: asks.append(a) or {"behavior": "deny", "message": "no"}, door=d)
    assert code == 403 and asks and asks[0][0] == "spoke" and not d.calls
    assert "names, sizes and dates" in m._spoke_summary(asks[0][1])
    code, j = m._spoke_move_in(None, door=d, mint=lambda: {"token": TOKEN})
    assert code == 200 and d.calls[-1] == ("move-in", [], TOKEN + "\n")
    assert m._spoke_move_in(None, door=_Door(), mint=lambda: None)[0] == 400


def test_bridge_look_counts(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    code, j = m._spoke_look(door=_Door(out="meta\tos\tmacOS 15.7\ntotal\t48211\t91234567890\nmeta\tfinished\tx\n"))
    assert code == 200 and j == {"ok": True, "files": 48211, "bytes": 91234567890}
    assert m._spoke_look(door=_Door(rc=3))[0] == 502


def test_bridge_bundle_passes_the_language(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    d = _Door(out="bundle\t/x/join-my-brain-paul.zip\n")
    m._spoke_bundle(door=d, lang="ru")
    m._spoke_bundle(door=d, lang="de")
    assert d.calls == [("bundle", ["ru"], None), ("bundle", ["en"], None)]


def test_bridge_first_run_state(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.FIRST_RUN_FILE = tmp_path / "fr.json"
    assert m._first_run_get()["steps"] == {} and m._first_run_get()["finished"] is None
    assert m._first_run_post({"step": "seat", "state": "maybe"})[0] == 400
    assert m._first_run_post({"step": "oven", "state": "done"})[0] == 400
    code, j = m._first_run_post({"step": "seat", "state": "skipped"})
    assert code == 200 and j["steps"] == {"seat": "skipped"} and not j["finished"]
    m._first_run_post({"step": "ways", "state": "done"})
    code, j = m._first_run_post({"step": "home", "state": "done"})
    assert j["finished"] and j["steps"]["home"] == "done"
    assert m._first_run_get()["finished"] == j["finished"]            # remembered
    assert m._first_run_post({"reset": True})[1]["finished"] is None


def test_bridge_routes_are_operator_only():
    s = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    open_post = s.split('if route not in ("/ask", "/jobs/start"', 1)[1].split(")", 1)[0]
    for r in ("/spoke/look", "/spoke/move-in", "/first-run"):
        assert r not in open_post


# ---- the console's logic, under node ----

def _node(mod: str, script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", f"const m=require('./{mod}');" + script], capture_output=True, text=True,
                       timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_first_run_order_and_picks():
    out = _node("firstRun.js", """console.log(JSON.stringify([
      m.currentStep({steps:{}}, false), m.currentStep({steps:{}}, true), m.currentStep({steps:{seat:'skipped'}}, false),
      m.currentStep({steps:{seat:'done', ways:'skipped', movein:'done'}}, false), m.currentStep({steps:{}, finished:'x'}, false),
      m.showFirstRun({member:true}, true), m.showFirstRun({member:false}, true), m.showFirstRun({member:true}, false),
      m.startPicks(null, ['chat','decisions','talkthrough']), m.startPicks({surfaces:['chat','systems']}, []),
      m.togglePick(['chat','talkthrough'], 'chat', ['chat','talkthrough']), m.togglePick(['chat','talkthrough'], 'talkthrough', ['chat','talkthrough']),
      Object.keys(m.FIRST_TEXT.en).filter(k => !(k in m.FIRST_TEXT.ru)), Object.keys(m.FIRST_TEXT.ru.about)]))""")
    assert out[:5] == ["seat", "ways", "ways", "home", None]
    assert out[5:8] == [True, False, False]
    assert out[8] == ["chat", "talkthrough"] and out[9] == ["chat", "systems"]
    assert out[10] == ["chat", "talkthrough"] and out[11] == ["chat"]
    assert out[12] == []
    from_bridge = [l.split('"')[1] for l in (ROOT / "scripts" / "cc" / "cc_layout.py").read_text().split("SURFACE_LIST = (", 1)[1].split("\n)", 1)[0].splitlines() if l.strip().startswith('("')]
    assert sorted(out[13]) == sorted(from_bridge)                        # a Russian line for every way of working


def test_first_run_seat_card_says_the_small_model_is_not_chatgpt():
    out = _node("firstRun.js", "console.log(JSON.stringify([m.FIRST_TEXT.en.seatLocal, m.FIRST_TEXT.ru.seatLocal]))")
    assert "llama3.2" in out[0] and "cannot replace ChatGPT" in out[0]
    assert "llama3.2" in out[1] and "заменить ChatGPT не может" in out[1]


def test_connect_card_steps():
    out = _node("connectComputer.js", """const on={ready:true,status:{laptop:{state:'online'}}};
      console.log(JSON.stringify([m.spokeStep(null), m.spokeStep({ready:false}), m.spokeStep({ready:true,status:{laptop:null}}),
      m.spokeStep({ready:true,status:{}}, {made:true}), m.spokeStep({ready:true,status:{laptop:{state:'asleep'}}}),
      m.spokeStep(on), m.spokeStep({...on, inventory:true}), m.spokeStep(on, {looked:true, moving:true}),
      m.osOf('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'), m.osOf('Windows NT 10.0'), m.osOf('iPhone'),
      Object.keys(m.CONNECT_TEXT.en).filter(k => !(k in m.CONNECT_TEXT.ru)), m.CONNECT_TEXT.en.steps.length, m.CONNECT_TEXT.ru.steps.length,
      m.CONNECT_TEXT.en.why, m.CONNECT_TEXT.en.win]))""")
    assert out[:8] == ["off", "off", "get", "made", "asleep", "look", "looked", "moving"]
    assert out[8:11] == ["mac", "windows", "phone"]
    assert out[11] == [] and out[12] == out[13] == 7
    assert "Apple Developer ID" in out[14] and "OpenSSH Server" in out[15]
