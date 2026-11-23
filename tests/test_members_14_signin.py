"""MEMBERS-14 2026-11-23: the sign-in screen for a person who has never seen a terminal, and the console in the
member's own language with English one press away.

- layout: six console languages; the member's own language (lang_home) survives a switch to English
- every console language has every word: console, first run, sign-in screen
- the door's sign-in link: only a fresh claude.ai/claude.com https link is handed to the page
- door.sh login, run for real against a fake Claude Code: the link is kept while the sign-in runs, the code the
  person types is never written anywhere, the words follow the language argument, the link file is gone after
- the reasoner answers in the console language when Settings names none
- the page: a start pressed before the sign-in waits instead of failing; the three-step screen on brains without
  the page-driven sign-in; the switch sits in the top bar
"""
import getpass
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_layout as L  # noqa: E402


def _node(lib, body):
    r = subprocess.run(["node", "-e", f"const m=require('./{lib}');{body}"], capture_output=True, text=True,
                       timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_layout_six_languages_and_home(tmp_path):
    st = L.Store(tmp_path)
    assert L.LANGS == ("en", "ru", "sk", "de", "el", "rue")
    assert st.lang() == "en" and st.lang_home() == ""
    assert st.set_lang("rue") == "rue" and st.lang_home() == "rue"
    assert st.set_lang("en") == "en" and st.lang() == "en" and st.lang_home() == "rue"   # English is the switch, not the home
    assert st.set_lang("rue") == "rue"
    with pytest.raises(L.LayoutError):
        st.set_lang("uk")


def test_layout_home_from_a_console_set_before(tmp_path):
    f = tmp_path / "layout.json"
    f.write_text(json.dumps({"lang": "ru"}))
    assert L.Store(tmp_path).lang_home() == "ru"


def test_every_language_has_every_word():
    langs = list(L.LANGS)
    out = _node("consoleText.js", "console.log(JSON.stringify({langs:m.LANGS,native:Object.keys(m.NATIVE),"
                "miss:m.LANGS.map(l=>Object.keys(m.TEXT.en).filter(k=>!(k in m.TEXT[l]))).flat()}))")
    assert out["langs"] == langs and sorted(out["native"]) == sorted(langs) and out["miss"] == []
    out = _node("firstRun.js", "console.log(JSON.stringify(Object.keys(m.FIRST_TEXT).map(l=>[l,"
                "Object.keys(m.FIRST_TEXT.en).filter(k=>!(k in m.FIRST_TEXT[l])),Object.keys(m.FIRST_TEXT[l].about).length])))")
    assert sorted(l for l, _, _ in out) == sorted(langs)
    assert all(miss == [] for _, miss, _ in out)
    assert all(n == 8 for l, _, n in out if l != "en")
    out = _node("signinText.js", "console.log(JSON.stringify(Object.keys(m.SIGNIN_TEXT).map(l=>[l,"
                "Object.keys(m.SIGNIN_TEXT.en).filter(k=>!(k in m.SIGNIN_TEXT[l])),m.SIGNIN_TEXT[l].pending('x').includes('x')])))")
    assert sorted(l for l, _, _ in out) == sorted(langs)
    assert all(miss == [] and ok for _, miss, ok in out)


def test_rusyn_words_are_cyrillic_only():
    """A mixed-script slip (a Latin letter inside a Cyrillic word) was caught by eye once; this keeps it caught."""
    import re
    for lib, name in (("consoleText.js", "TEXT"), ("firstRun.js", "FIRST_TEXT"), ("signinText.js", "SIGNIN_TEXT")):
        out = _node(lib, f"const t=m.{name}.rue;console.log(JSON.stringify(Object.values(t).map(v=>typeof v==='function'?v('x',1):v)))")
        text = json.dumps(out, ensure_ascii=False)
        assert not re.search(r"[A-Za-z][\u0400-\u04FF]|[\u0400-\u04FF][A-Za-z]|\u0131", text), lib


def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("ccb_m14", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.DOOR_URL_FILE = tmp_path / "login-url"
    return m


def test_door_url_only_a_fresh_claude_link(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    f = m.DOOR_URL_FILE
    assert m._door_login_url() is None
    good = "https://claude.ai/oauth/authorize?code=true&client_id=abc-123&response_type=code&scope=user%3Ainference&state=Zz9"
    f.write_text(good)
    assert m._door_login_url() == good
    for bad in ("http://claude.ai/oauth/authorize?x=1", "https://claude.ai.evil.example/x", "https://evil.example/?u=https://claude.ai/",
                good + " and more", "javascript:alert(1)", good + "\"><script>"):
        f.write_text(bad)
        assert m._door_login_url() is None, bad
    f.write_text(good)
    old = time.time() - 700
    os.utime(f, (old, old))
    assert m._door_login_url() is None   # older than ten minutes: a sign-in that is over


def test_console_language_is_the_answer_language(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.LAYOUT = L.Store(tmp_path / "st")
    assert m._console_lang_line() == ""
    m.LAYOUT.set_lang("rue")
    line = m._console_lang_line()
    assert "Rusyn" in line and "Cyrillic" in line and "English" in line
    m.LAYOUT.set_lang("en")
    assert m._console_lang_line() == ""   # switched to English: English answers


FAKE_CLAUDE = '''#!/usr/bin/env bash
here="$(dirname "$0")"
if [ "$1 $2" = "auth status" ]; then if [ -f "$here/csigned" ]; then echo '{"loggedIn": true}'; else echo '{"loggedIn": false}'; fi; exit 0; fi
if [ "$1 $2" = "auth login" ]; then
  echo "Browser didn't open? Use the url below to sign in:"
  printf '\\033[1mhttps://claude.ai/oauth/authorize?code=true&client_id=FAKE&state=S1\\033[0m\\n'
  printf 'Paste code here if prompted > '
  for i in 1 2 3 4 5 6 7 8 9 10; do [ -s "$HOME/.cc-bridge/login-url" ] && break; sleep 0.5; done; cat "$HOME/.cc-bridge/login-url" > "$here/seen-url" 2>/dev/null
  read -r code; echo "$code" > "$here/code-got"
  [ "$code" = "CODE-SECRET-42" ] && touch "$here/csigned"; exit 0
fi
exit 2
'''


def _door(tmp_path):
    src = (ROOT / "scripts" / "cc" / "install.sh").read_text()
    body = src.split("<<'DOOR'\n", 1)[1].split("\nDOOR\n", 1)[0]
    home = tmp_path / "hands"
    body = body.replace("/home/__LOGIN_USER__", str(home)).replace("__LOGIN_USER__", getpass.getuser())
    body = body.replace("__CODEX_INSTALL__", "x")
    door = tmp_path / "door.sh"
    door.write_text(body)
    bin_ = home / ".local" / "bin"
    bin_.mkdir(parents=True)
    (home / ".cc-bridge").mkdir()
    for name, text in (("clear", "#!/bin/sh\n"), ("claude", FAKE_CLAUDE)):
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    # the 3600 s wait at the end of the door: a sleep that only waits for short times
    (bin_ / "sleep").write_text('#!/bin/sh\n[ "$1" -gt 5 ] 2>/dev/null && exit 0; exec /bin/sleep "$@"\n')
    (bin_ / "sleep").chmod(0o755)

    def run(*args, code):
        r = subprocess.run(["bash", str(door), *args], input=code + "\n", capture_output=True, text=True, timeout=40,
                           env={"HOME": str(home), "PATH": f"{bin_}:/usr/bin:/bin"})
        return r.stdout
    return home, bin_, run


@pytest.mark.skipif(not Path("/usr/bin/script").exists(), reason="util-linux script not installed")
def test_door_keeps_only_the_link_and_never_the_code(tmp_path):
    home, bin_, run = _door(tmp_path)
    out = run("login", "ru", code="CODE-SECRET-42")
    assert "Вход в Claude, на вашем сервере." in out and "Вход выполнен." in out
    assert (bin_ / "seen-url").read_text() == "https://claude.ai/oauth/authorize?code=true&client_id=FAKE&state=S1"
    assert (bin_ / "code-got").read_text().strip() == "CODE-SECRET-42"   # the code reached Claude Code itself
    assert not (home / ".cc-bridge" / "login-url").exists()               # the link is gone once the sign-in is over
    left = [p for p in (home / ".cc-bridge").iterdir()]
    assert left == []                                                      # no fifo, no log left behind
    for p in tmp_path.rglob("*"):
        if p.is_file() and p.name not in ("code-got", "claude"):   # the fake CLI and its own record hold it by design
            assert "CODE-SECRET-42" not in p.read_text(errors="replace"), p   # the code is written nowhere


def test_door_words_follow_the_language_and_fall_back_to_english(tmp_path):
    home, bin_, run = _door(tmp_path)
    out = run("login", "rue", code="wrong")
    assert "Приголошіня до Claude, на твоїм сервері." in out and "Іщі не єсь приголошена." in out
    out = run("login", code="wrong")
    assert "Claude's own sign-in, on your server." in out and "Not signed in yet." in out


def test_page_wires_the_screen_the_wait_and_the_switch():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "import SignInSteps from '../components/SignInSteps'" in cc
    assert "health.signin_proxy\n          ? <SignIn" in cc and ": <SignInSteps lang={lang}" in cc   # the old card only where the page-driven sign-in is on
    assert "if (health && !loggedIn && typeof forced === 'string' && !paneMode) { setPendingStart(text); return }" in cc
    steps = (ROOT / "ui" / "components" / "SignInSteps.js").read_text()
    assert "/cc/login/door-url" in steps and "/claude/?arg=login&arg=" in steps
    assert "/cc/login/code" not in steps   # the code never passes through this page
    nav = (ROOT / "ui" / "components" / "Nav.js").read_text()
    assert nav.count("<LangSwitch />") == 2   # both bars: the drawer bar and the tab bar
