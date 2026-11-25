"""A system's card (SURFACES-1, 2026-11-24).

GET /cc/surfaces serves the owner's register (<world>/registry/surfaces/*.json, scripts/cc/cc_surfaces.py); the chat
shows a card when a message is only a say-word, /systems tiles carry the pads. This file pins: the checks on every
register value (addresses stay on the console origin, one to five actions, a say-word belongs to one card), the
route behind the operator token, ui/lib/surfaces.js under node, and that the pages use the lib and the card.

Run from repo root:
    pytest tests/test_cc_surfaces.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_surfaces", ROOT / "scripts" / "cc" / "cc_surfaces.py")
S = importlib.util.module_from_spec(spec); sys.modules["cc_surfaces"] = S; spec.loader.exec_module(S)


def card(**kw):
    d = {"name": "music", "system": "hbar.music", "say": ["Music", "studio"], "hue": "#B5532F", "line": "make a track",
         "mark": "wave", "actions": [{"label": "Sing", "open": "/sing", "kind": "page", "note": "over a loop"},
                                     {"label": "Listen", "ask": "listen on orfeo", "kind": "ask"}]}
    d.update(kw)
    return d


def world(tmp_path, files):
    f = tmp_path / "w" / "registry" / "surfaces"
    f.mkdir(parents=True)
    for name, d in files.items():
        (f / name).write_text(d if isinstance(d, str) else json.dumps(d))
    return tmp_path / "w"


def test_a_good_card_comes_back_clean():
    s, why = S.surface(card())
    assert why == "" and s["say"] == ["music", "studio"] and s["hue"] == "#b5532f" and s["mark"] == "wave"
    assert s["actions"] == [{"label": "Sing", "note": "over a loop", "open": "/sing", "kind": "page"},
                            {"label": "Listen", "note": "", "ask": "listen on orfeo", "kind": "ask"}]


def test_an_ask_that_ends_in_a_space_keeps_it_for_typing_on():
    s, _ = S.surface(card(actions=[{"label": "Cut", "ask": "cut loops from this track: "}]))
    assert s["actions"][0]["ask"] == "cut loops from this track: "


@pytest.mark.parametrize("addr", ["//evil.example/x", "https://evil.example/x", "javascript:alert(1)", "http://console.x/a",
                                  "relative/path", "/a\nb", "/a\\b", ""])
def test_addresses_off_the_console_are_refused(addr):
    s, why = S.surface(card(actions=[{"label": "X", "open": addr}]), host="console.x")
    assert s is None and "address" in why


def test_an_address_on_the_console_host_is_cut_to_its_path():
    s, _ = S.surface(card(actions=[{"label": "K2", "open": "https://Console.X/cc/page/rooms/k2/?a=1"}]), host="console.x")
    assert s["actions"][0]["open"] == "/cc/page/rooms/k2/?a=1"
    s, _ = S.surface(card(actions=[{"label": "K2", "open": "https://console.x/cc/page/rooms/k2/"}]), host="")
    assert s is None


def test_thread_kind_is_read_from_the_address():
    s, _ = S.surface(card(actions=[{"label": "T", "open": "/talk?thread=abc"}]))
    assert s["actions"][0]["kind"] == "thread"


@pytest.mark.parametrize("bad,why", [
    ({"name": "Bad Name"}, "name"), ({"system": "../x"}, "system"), ({"say": []}, "say"), ({"say": ["!!"]}, "say"),
    ({"hue": "red"}, "hue"), ({"actions": []}, "actions"), ({"count_to": "soon"}, "count_to"),
    ({"actions": [{"label": "A", "open": "/a", "ask": "b"}]}, "one of them"),
    ({"actions": [{"label": "", "open": "/a"}]}, "label"),
    ({"actions": [{"label": str(i), "open": "/a"} for i in range(6)]}, "five"),
])
def test_bad_values_skip_the_whole_card(bad, why):
    s, w = S.surface(card(**bad))
    assert s is None and why in w


def test_unknown_mark_falls_back_and_count_to_is_kept():
    s, _ = S.surface(card(mark="laser", count_to="2026-12-07"))
    assert s["mark"] == "dot" and s["count_to"] == "2026-12-07"


def test_load_skips_bad_files_and_gives_a_say_word_to_the_first(tmp_path):
    w = world(tmp_path, {
        "a-music.json": card(),
        "b-studio.json": card(name="studio", system="hbar.studio", say=["studio", "booth"]),
        "c-dup.json": card(say=["other"]),
        "d-broken.json": "{",
        "e-bad.json": card(name="film", hue="nope"),
        "notes.txt": "ignored",
    })
    d = S.load(w, host="")
    assert [s["name"] for s in d["surfaces"]] == ["music", "studio"]
    assert d["surfaces"][1]["say"] == ["booth"]
    whys = {(x["file"], x["why"]) for x in d["skipped"]}
    assert ("b-studio.json", "say-word 'studio' is music's") in whys
    assert ("c-dup.json", "name music twice") in whys and ("d-broken.json", "not json") in whys and ("e-bad.json", "hue") in whys


def test_load_without_a_world_or_folder_is_empty(tmp_path):
    assert S.load(None) == {"surfaces": [], "skipped": []}
    assert S.load(tmp_path) == {"surfaces": [], "skipped": []}


def test_the_template_names_no_system():
    src = (ROOT / "scripts" / "cc" / "cc_surfaces.py").read_text().split('"""', 2)[2]
    for word in ("hbar.music", "orfeo", "court", "defense", "numa"):
        assert word not in src


# ---- the route ----
def _bridge(monkeypatch, tmp_path, w, token):
    monkeypatch.setenv("CC_BIN", "/bin/false")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_WORLD_DIR", str(w))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    monkeypatch.delenv("CC_CONSOLE_HOST", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    sp = importlib.util.spec_from_file_location("cc_bridge_surfaces", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(sp)
    sys.modules[sp.name] = m
    sp.loader.exec_module(m)
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/cc"


def _get(url, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_route_serves_the_register_behind_the_operator_token(monkeypatch, tmp_path):
    w = world(tmp_path, {"music.json": card(actions=[{"label": "Room", "open": "https://console.x/cc/page/rooms/studio/"}])})
    srv, base = _bridge(monkeypatch, tmp_path, w, "tok")
    try:
        st, _ = _get(base + "/surfaces")
        assert st == 403
        st, d = _get(base + "/surfaces", {"X-CC-Operator": "tok"})
        assert st == 200 and d["surfaces"] == [] and d["skipped"][0]["why"].endswith("address off the console")
        st, d = _get(base + "/surfaces", {"X-CC-Operator": "tok", "X-Forwarded-Host": "console.x"})
        assert st == 200 and d["surfaces"][0]["actions"][0]["open"] == "/cc/page/rooms/studio/"
    finally:
        srv.shutdown()


# ---- the lib and the pages ----
def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_surfaces_lib_under_node():
    d = _node(r"""
const L = require('./surfaces')
const S = [{ name: 'music', system: 'hbar.music', say: ['music', 'studio'], actions: [1, 2, 3] },
           { name: 'court', system: 'court', say: ['court'], actions: [1, 2, 3, 4, 5] }]
console.log(JSON.stringify({
  m: ['music', '  Music ', 'music.', 'MUSIC!', 'studio', 'court'].map(t => (L.sayMatch(t, S) || {}).name || null),
  no: ['music?', 'music please', 'musi', '', null, 'x'.repeat(50)].map(t => L.sayMatch(t, S)),
  bad: L.sayMatch('music', null),
  k: [['1', 3], ['3', 3], ['4', 3], ['5', 5], ['6', 5], ['0', 5], ['a', 5], [null, 5]].map(([k, n]) => L.keyIndex(k, n)),
  d: [L.daysLeft('2026-12-07', '2026-11-24T23:30:00'), L.daysLeft('2026-11-24', '2026-11-24T08:00:00'),
      L.daysLeft('2026-11-20', '2026-11-24T08:00:00'), L.daysLeft('soon')],
  sys: L.systemsFor([{ id: 'hbar.music' }, { id: 'world' }], S),
}))
""")
    assert d["m"] == ["music", "music", "music", "music", "music", "court"]
    assert d["no"] == [None] * 6 and d["bad"] is None
    assert d["k"] == [0, 2, -1, 4, -1, -1, -1, -1]
    assert d["d"] == [13, 0, -4, None]
    assert list(d["sys"]["bySystem"]) == ["hbar.music"] and [s["name"] for s in d["sys"]["alone"]] == ["court"]


def test_the_pages_use_the_card():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "sayMatch(text, surfacesRef.current)" in cc and "fetch('/cc/surfaces'" in cc and "<SurfaceCard" in cc
    # the card is shown before any model turn starts: the match returns before the busy/queue/send path
    i_match, i_busy = cc.index("sayMatch(text, surfacesRef.current)"), cc.index("const busyNow")
    assert i_match < i_busy
    sy = (ROOT / "ui" / "pages" / "systems" / "index.js").read_text()
    assert "systemsFor(tiles, surfs)" in sy and "fetch('/cc/surfaces'" in sy and "<SurfaceCard" in sy
