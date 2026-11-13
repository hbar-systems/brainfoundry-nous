"""NAV-1 (2026-11-13): the brand (symbol and name) and the menu's Chat open the home,
the thread page with its thread list, on a brain with CC; /chat stays an address.

hbar 2026-11-13: "nobody knows that to press brain or hbar in upper right will give you
the thread page that should be main page. it has always been going to /chat".
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAV = (ROOT / "ui" / "components" / "Nav.js").read_text()
CC = (ROOT / "ui" / "pages" / "cc.js").read_text()

CC_TABS = "[{id:'_cc',href:'/'},{id:'_dashboard',href:'/dashboard'},{id:'_chat',href:'/chat'},{id:'_files',href:'/files'}]"
PLAIN_TABS = "[{id:'_dashboard',href:'/'},{id:'_chat',href:'/chat'}]"


def _node(tmp_path, expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    shutil.copy(ROOT / "ui" / "lib" / "home.js", tmp_path / "home.mjs")
    r = subprocess.run([node, "--input-type=module", "-e",
                        f"import('./home.mjs').then(m=>{{const cc={CC_TABS}, plain={PLAIN_TABS}; console.log(JSON.stringify({expr}))}})"],
                       capture_output=True, text=True, timeout=30, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    import json
    return json.loads(r.stdout)


def test_brand_goes_to_threads_home_on_cc_brain(tmp_path):
    assert _node(tmp_path, "[m.homeHref(cc), m.homeHref(plain), m.homeHref([]), m.homeHref(null)]") == \
        ["/?threads=1", "/", "/", "/"]


def test_menu_chat_is_the_home_on_cc_brain_only(tmp_path):
    got = _node(tmp_path, "[m.menuHref({id:'_chat',href:'/chat'},cc), m.menuHref({id:'_files',href:'/files'},cc),"
                          " m.menuHref({id:'_chat',href:'/chat'},plain)]")
    assert got == ["/?threads=1", "/files", "/chat"]


def test_threads_flag(tmp_path):
    got = _node(tmp_path, "['?threads=1','?threads=open','?thread=abc','','?threads=0'].map(m.wantsThreads)")
    assert got == [True, True, False, False, False]


def test_nav_uses_the_home_for_brand_and_menu():
    assert "<Link href={homeHref} onClick={goHome}" in NAV
    assert "const homeHref = homeOf(tabs)" in NAV
    assert "menuHref(t, tabs)" in NAV
    # pressing home while on it tells the mounted page to open its list
    assert "new Event('bf-home')" in NAV


def test_cc_page_opens_thread_list_from_home():
    assert "wantsThreads(window.location.search)" in CC
    assert "window.addEventListener('bf-home', open)" in CC


def test_chat_page_still_exists():
    # /chat keeps working as an address (the old page of many chats)
    assert (ROOT / "ui" / "pages" / "chat.js").exists()
