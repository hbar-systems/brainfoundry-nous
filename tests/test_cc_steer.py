"""The steer door and several system threads (BOARD-5, 2026-11-23).

POST /cc/threads/<id>/say: the central chat sends one turn into a system's standing thread. A
security-relevant door, so this file pins: the operator token and the app-frame refusal (the same
door as a typed turn), the target rule (only a standing system thread), the "from" rule, the busy
refusal, that the turn goes through _turn() (the hook, posture and cards of a typed turn) and never
another path, and that the steered turn reports back to the steering thread once (REPORT-1).
Also ui/lib/steer.js under node, the reasoner's line, and the /systems page wiring.

Run from repo root:
    pytest tests/test_cc_steer.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_reports", ROOT / "scripts" / "cc" / "cc_reports.py")
R = importlib.util.module_from_spec(spec); sys.modules["cc_reports"] = R; spec.loader.exec_module(R)

FILM = "11111111-2222-3333-4444-555555555555"
CENTRAL = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PLAIN = "99999999-8888-7777-6666-555555555555"


# ---- the report mark (cc_reports.expect) ----
def test_expect_reports_the_next_turn_once_then_falls_back(tmp_path):
    s = R.Reports(tmp_path / "r.json")
    assert s.post(FILM, title="CC: film: standing thread", reply="x") is None      # a standing thread reports to nobody
    assert s.expect(FILM, CENTRAL, label="film: cut the trailer")
    assert s.expected(FILM) == CENTRAL
    card = s.post(FILM, title="CC: film: standing thread", reply="Cut it.\nTwo files.")
    assert card["parent"] == CENTRAL and card["steered"] is True and card["lines"] == ["Cut it.", "Two files."]
    assert card["title"] == "film: standing thread"
    assert s.expected(FILM) is None
    assert s.post(FILM, title="CC: film", reply="a later turn typed in film itself") is None   # once
    assert [c["id"] for c in s.take(CENTRAL)] == [card["id"]]


def test_expect_refuses_self_and_placeholders_and_unexpect_clears(tmp_path):
    s = R.Reports(tmp_path / "r.json")
    assert not s.expect(FILM, FILM) and not s.expect("new:1", CENTRAL) and not s.expect(FILM, "new:2") and not s.expect(FILM, "")
    assert s.expect(FILM, CENTRAL) and s.unexpect(FILM) and not s.unexpect(FILM)
    assert s.post(FILM, reply="x") is None


def test_expect_wins_over_a_link_for_one_turn(tmp_path):
    s = R.Reports(tmp_path / "r.json")
    s.link(FILM, PLAIN)
    s.expect(FILM, CENTRAL)
    assert s.post(FILM, reply="steered")["parent"] == CENTRAL
    assert s.post(FILM, reply="ordinary")["parent"] == PLAIN
    assert len(s.take(CENTRAL)) == 1 and len(s.take(PLAIN)) == 1


def test_expect_expires_and_survives_restart(tmp_path):
    f = tmp_path / "r.json"
    R.Reports(f).expect(FILM, CENTRAL)
    assert R.Reports(f).expected(FILM) == CENTRAL                                 # a bridge restart keeps the mark
    d = json.loads(f.read_text()); d["expect"][FILM]["at"] = time.time() - R.EXPECT_TTL - 5; f.write_text(json.dumps(d))
    assert R.Reports(f).post(FILM, reply="x") is None                             # an old mark sends nothing
    assert R.first_lines("<steer>{\"system\": \"film\", \"say\": \"x\"}</steer>\nreal line") == ["real line"]


# ---- the bridge ----
def _world(tmp_path):
    w = tmp_path / "world"
    (w / "registry").mkdir(parents=True)
    (w / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.film", "description": "film"}, {"id": "hbar.music", "description": "music"}]}))
    return w


def _bridge(monkeypatch, tmp_path, token=""):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_WORLD_DIR", str(_world(tmp_path)))
    monkeypatch.setenv("CC_OPERATOR_TOKEN", token)
    monkeypatch.setenv("CC_SYSTEMS_SEED", str(tmp_path / "no-seed.json"))
    monkeypatch.setenv("CC_SYSTEMS_BOARD", str(tmp_path / "board.json"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    (tmp_path / "brain").mkdir(exist_ok=True)
    sp = importlib.util.spec_from_file_location("cc_bridge_steer", ROOT / "scripts" / "cc" / "cc-bridge.py")
    m = importlib.util.module_from_spec(sp)
    sys.modules[sp.name] = m
    sp.loader.exec_module(m)
    m.REPORTS = R.Reports(tmp_path / "reports.json")
    m.SYSTEMS_THREADS._save({"hbar.film": {"thread": FILM}})
    now = "2026-11-23T10:00:00Z"
    m._threads_save([{"brain": FILM, "claude": None, "title": "CC: hbar.film: standing thread", "started": now, "last": now, "via": "systems", "system": "hbar.film"},
                     {"brain": CENTRAL, "claude": None, "title": "CC: world: standing thread", "started": now, "last": now},
                     {"brain": PLAIN, "claude": None, "title": "CC: a plain thread", "started": now, "last": now}])
    return m


def _serve(m):
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/cc"


def _call(url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _fake_turn(m, monkeypatch, calls, reply="Cut the trailer.\nkept in out/film.", status=200):
    done = threading.Event()

    def inner(message, **kw):
        calls.append({"message": message, **kw})
        return status, {"reply": reply, "thread": kw.get("thread"), "title": "CC: hbar.film: standing thread",
                        "error": status != 200, "stopped": False, "proposal": None}
    monkeypatch.setattr(m, "_turn_inner", inner)
    monkeypatch.setattr(m, "_drain_async", lambda t: None)
    monkeypatch.setattr(m, "_box_wait_next", lambda: done.set())
    return done


def test_door_needs_the_operator_token_and_refuses_app_frames(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, token="tok")
    calls = []
    _fake_turn(m, monkeypatch, calls)
    srv, base = _serve(m)
    try:
        url = f"{base}/threads/{FILM}/say"
        body = {"message": "cut the trailer", "from": CENTRAL}
        assert _call(url, body)[0] == 403                                                   # no token: the hands, any box process
        assert _call(url, body, {"X-CC-Operator": "wrong"})[0] == 403
        assert _call(url, body, {"X-CC-Operator": "tok", "Origin": "null"})[0] == 403        # a brain app's frame inside the console
        assert _call(url, body, {"X-CC-Operator": "tok", "Sec-Fetch-Site": "cross-site"})[0] == 403
        assert _call(url, body, {"X-CC-Ask": m.ASK_TOKEN})[0] == 403                          # the hook's token is not the owner's
        time.sleep(0.2)
        assert calls == [] and m.REPORTS.expected(FILM) is None
        st, d = _call(url, body, {"X-CC-Operator": "tok"})
        assert st == 202 and d == {"ok": True, "system": "hbar.film", "thread": FILM, "reports_to": CENTRAL}
    finally:
        srv.shutdown()


def test_door_runs_a_typed_turn_and_reports_to_the_steering_thread(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    started = []
    _fake_turn(m, monkeypatch, calls)
    st, d = m._steer(FILM, {"message": "cut the trailer", "from": CENTRAL}, start=lambda f: (started.append(f), f()))
    assert st == 202 and d["ok"] and d["thread"] == FILM and len(started) == 1
    c = calls[0]
    # the same turn path as /chat: an existing thread, never a new one, no parent, no seat or posture of its own
    assert c["thread"] == FILM and c["new"] is False and c["source"] == "steer"
    assert c.get("reasoner") is None and c.get("parent") is None and c.get("queue") is False
    assert c["message"] == "(Steered from the central chat.) cut the trailer"
    got = m.REPORTS.take(CENTRAL)
    assert len(got) == 1 and got[0]["child"] == FILM and got[0]["steered"] and got[0]["lines"] == ["Cut the trailer.", "kept in out/film."]
    assert m.REPORTS.take(PLAIN) == [] and m.REPORTS.take(FILM) == []                     # the 2026-10-11 rule
    # the same steer again within a minute is a second press, not a second turn
    st, d = m._steer(FILM, {"message": "cut the trailer", "from": CENTRAL}, start=lambda f: f())
    assert st == 202 and d.get("duplicate") and len(calls) == 1


def test_door_without_from_reports_to_nobody(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    _fake_turn(m, monkeypatch, calls)
    st, d = m._steer(FILM, {"message": "a note"}, start=lambda f: f())
    assert st == 202 and d["reports_to"] is None and len(calls) == 1 and m.REPORTS.waiting() == {}


def test_door_target_and_from_rules(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    _fake_turn(m, monkeypatch, calls)
    run = lambda f: f()   # noqa: E731
    assert m._steer(PLAIN, {"message": "x", "from": CENTRAL}, start=run)[0] == 404                 # not a standing thread
    assert m._steer("no-such", {"message": "x"}, start=run)[0] == 404
    assert m._steer(FILM, {"message": "  "}, start=run)[0] == 400
    assert m._steer(FILM, {"message": "x" * (m.STEER_MAX + 1)}, start=run)[0] == 413
    assert m._steer(FILM, {"message": "x", "from": FILM}, start=run)[0] == 400                    # never steers itself
    assert m._steer(FILM, {"message": "x", "from": "new:3"}, start=run)[0] == 400
    assert m._steer(FILM, {"message": "x", "from": "bbbbbbbb-0000-0000-0000-000000000000"}, start=run)[0] == 400  # not on this box
    # a standing thread dropped from the list is not steerable until /systems opens it again
    m._threads_save([x for x in m._threads_load() if x["brain"] != FILM])
    assert m._steer(FILM, {"message": "x"}, start=run)[0] == 404
    assert calls == [] and m.REPORTS.expected(FILM) is None


def test_door_refuses_a_busy_thread_and_leaves_no_mark(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    _fake_turn(m, monkeypatch, calls)
    monkeypatch.setattr(m, "_run_for_thread", lambda t: object() if t == FILM else None)
    st, d = m._steer(FILM, {"message": "x", "from": CENTRAL}, start=lambda f: f())
    assert st == 409 and d["busy"] and "hbar.film" in d["error"]
    assert calls == [] and m.REPORTS.expected(FILM) is None


def test_a_turn_that_never_ran_clears_its_mark(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    _fake_turn(m, monkeypatch, calls, status=409)                     # it got busy between the check and the start
    st, _ = m._steer(FILM, {"message": "x", "from": CENTRAL}, start=lambda f: f())
    assert st == 202 and m.REPORTS.expected(FILM) is None and m.REPORTS.waiting() == {}
    assert m.SENT.seen((FILM, "(Steered from the central chat.) x")) is None   # a later press is not a duplicate


def test_door_over_http_end_to_end(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    calls = []
    done = _fake_turn(m, monkeypatch, calls)
    srv, base = _serve(m)
    try:
        st, d = _call(f"{base}/threads/{FILM}/say", {"message": "cut the trailer", "from": CENTRAL})
        assert st == 202 and d["thread"] == FILM
        assert done.wait(10)
        st, j = _call(f"{base}/jobs?take=1&thread={CENTRAL}")
        assert st == 200 and len(j["reports"]) == 1 and j["reports"][0]["steered"]
        assert _call(f"{base}/threads/{FILM}/nope", {"message": "x"})[0] == 404
    finally:
        srv.shutdown()


def test_the_steer_route_is_not_a_box_door():
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    exempt = src.split("def do_POST", 1)[1].split('if route not in (', 1)[1].split(')', 1)[0]
    assert "/threads" not in exempt and "say" not in exempt          # the POST doors open without the token stay as they were
    assert 'status, _ = _turn(text, thread=tid, new=False, source="steer")' in src
    assert "Steering a system thread" in src and "nothing is sent until the person presses it" in src
    assert "<steer>.*?</steer>|" in src                                # never spoken aloud


# ---- ui/lib/steer.js ----
def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_steer_lib_under_node():
    d = _node(r"""
const S = require('./steer')
const t = 'I will ask film.\n<steer>{"system": "hbar.film", "say": "cut the trailer"}</steer>\n' +
  '<steer>{"system": "Bad Id", "say": "x"}</steer>\n<steer>{"system": "hbar.music", "say": ""}</steer>\n' +
  'Prose mentions <steer> as a word.\n<steer>{"system": "hbar.film", "say": "cut it shorter"}</steer>\n<choices>[]</choices>'
const many = Array.from({length: 6}, (_, i) => `<steer>{"system": "s${i}", "say": "go"}</steer>`).join('\n')
console.log(JSON.stringify({
  a: S.splitSteer(t),
  open: S.splitSteer('Asking now.\n<steer>{"system": "hbar.fi').body,
  none: S.splitSteer(null),
  many: S.splitSteer(many).steers.length,
  body1: S.steerBody({ say: 'go' }, 'aaaa-1'), body2: S.steerBody({ say: 'go' }, 'new:1'), body3: S.steerBody({ say: 'go' }, null),
  url: S.sayUrl('a/b'),
  read: [S.readOpen('["hbar.film","hbar.film","BAD","a","b","c","d"]'), S.readOpen(null, 'hbar.music'), S.readOpen('{', null)],
  tog: [S.toggleOpen([], 'a'), S.toggleOpen(['a', 'b'], 'a'), S.toggleOpen(['a', 'b', 'c', 'd'], 'e')],
  grid: [0, 1, 2, 3, 4, 9].map(S.gridOf),
}))
""")
    a = d["a"]
    assert [s["system"] for s in a["steers"]] == ["hbar.film"] and a["steers"][0]["say"] == "cut it shorter"   # last word wins
    assert "Bad Id" in a["body"] and "Prose mentions <steer> as a word." in a["body"]       # an invalid block stays visible
    assert '"hbar.film"' not in a["body"] and a["body"].endswith("<choices>[]</choices>")   # choices stay anchored to the end
    assert d["open"] == "Asking now." and d["none"] == {"body": "", "steers": []} and d["many"] == 4
    assert d["body1"] == {"message": "go", "from": "aaaa-1"} and d["body2"] == {"message": "go"} and d["body3"] == {"message": "go"}
    assert d["url"] == "/cc/threads/a%2Fb/say"
    assert d["read"] == [["a", "b", "c", "d"], ["hbar.music"], []]
    assert d["tog"] == [["a"], ["b"], ["b", "c", "d", "e"]]
    assert d["grid"] == [{"cols": 1, "rows": 1}, {"cols": 1, "rows": 1}, {"cols": 2, "rows": 1}, {"cols": 3, "rows": 1},
                         {"cols": 2, "rows": 2}, {"cols": 2, "rows": 2}]


def test_pages_wire_the_steer_and_keep_v1():
    sy = (ROOT / "ui" / "pages" / "systems" / "index.js").read_text()
    assert "from '../../lib/steer'" in sy and "toggleOpen(l, sid)" in sy and "localStorage.setItem(OPEN_KEY" in sy
    assert "const CENTRAL = 'world'" in sy
    v1 = (ROOT / "ui" / "pages" / "systems" / "v1.js").read_text()
    assert "kept at /systems/v1" in v1 and "<Head><title>Systems v1</title></Head>" in v1
    assert not (ROOT / "ui" / "pages" / "systems.js").exists()               # one /systems route, no clash
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "import { splitSteer, steerBody, sayUrl } from '../lib/steer'" in cc
    assert "<SteerLines steers={steers} cur={cur} />" in cc and "cur={cur} />" in cc
    assert "fetch(sayUrl(d.thread)" in cc                                     # the press sends; nothing auto-sends
