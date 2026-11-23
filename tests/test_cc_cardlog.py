"""Cards are a log (INLINE-1, 2026-11-23).

hbar, after Firefox crashed: "WHY DO CARDS DISAPPEAR IF THEY RELOAD! CARDS SHOULD BE KEPT. CARDS ARE LIKE LOGS NO?"
Job tiles and REPORT-1 cards were handed to the page once and lived only in its memory. This file pins the
fix at the source: every card is written to the thread's log when it is made (scripts/cc/cc_cardlog.py),
GET /cc/cards draws it again after a reload, in order, with its state, and only for its own thread.
Also ui/lib/cardlog.js under node (merge in time order, no doubles, answered on send) and the page wiring.

Run from repo root:
    pytest tests/test_cc_cardlog.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_cardlog", ROOT / "scripts" / "cc" / "cc_cardlog.py")
L = importlib.util.module_from_spec(spec); sys.modules["cc_cardlog"] = L; spec.loader.exec_module(L)

sys.path.insert(0, str(ROOT / "tests"))
from test_cc_steer import _bridge, _serve, _call, _fake_turn, FILM, CENTRAL, PLAIN, R  # noqa: E402


def _job(jid, thread, ended, text="done.\nwrote out/x.md"):
    return {"id": jid, "title": "make the cut", "rc": 0, "started": ended - 60, "ended": ended, "thread": thread,
            "log": f"/out/jobs/{jid}.log", "result": {"rc": 0, "secs": 60, "text": text, "files": []}}


# ---- the store ----
def test_log_keeps_cards_in_order_per_thread_and_survives_restart(tmp_path):
    f = tmp_path / "cardlog.json"
    log = L.CardLog(f)
    T = time.time()
    assert log.add(CENTRAL, "job", _job("J2", CENTRAL, T - 1000))
    assert log.add(CENTRAL, "report", {"id": "Rb", "parent": CENTRAL, "child": FILM, "title": "film", "state": "done", "lines": ["a"], "at": T - 1500})
    assert log.add(PLAIN, "job", _job("J9", PLAIN, T - 2000))
    got = L.CardLog(f).list(CENTRAL)                         # a bridge restart, a new page: the same cards
    assert [e["id"] for e in got] == ["report:Rb", "job:J2"] and all(not e["answered"] for e in got)
    assert [e["id"] for e in L.CardLog(f).list(PLAIN)] == ["job:J9"]          # the 2026-10-11 rule: its own thread only
    assert L.CardLog(f).list("new:1") == [] and log.add("unknown", "job", _job("J3", "unknown", 3)) is None


def test_same_card_again_keeps_place_and_state_and_text_is_capped(tmp_path):
    log = L.CardLog(tmp_path / "c.json")
    T = time.time()
    log.add(CENTRAL, "job", _job("J1", CENTRAL, T - 100, text="x" * 5000))
    assert log.answer(CENTRAL, "job:J1")
    log.add(CENTRAL, "job", _job("J1", CENTRAL, T - 100))        # taken by the page after it was logged at the end
    [e] = log.list(CENTRAL)
    assert e["answered"] and e["data"]["result"]["text"] == "done.\nwrote out/x.md"
    log.add(CENTRAL, "job", _job("J4", CENTRAL, T - 50, text="y" * 5000))
    big = log.list(CENTRAL)[-1]["data"]["result"]
    assert len(big["text"]) == L.TEXT_MAX and big["more"] is True


def test_answer_before_marks_only_older_open_cards(tmp_path):
    log = L.CardLog(tmp_path / "c.json")
    now = time.time()
    log.add(CENTRAL, "job", _job("J1", CENTRAL, now - 100))
    log.add(CENTRAL, "job", _job("J2", CENTRAL, now + 100))
    assert log.answer_before(CENTRAL, now) == 1
    assert [e["answered"] for e in log.list(CENTRAL)] == [True, False] and log.open_count(CENTRAL) == 1
    assert not log.answer(CENTRAL, "job:nope") and not log.answer(PLAIN, "job:J2")


def test_a_newer_report_of_the_same_child_replaces_an_open_one(tmp_path):
    log = L.CardLog(tmp_path / "c.json")
    T = time.time()
    log.add(CENTRAL, "report", {"id": "R1", "child": FILM, "at": T - 3})
    log.add(CENTRAL, "report", {"id": "R2", "child": FILM, "at": T - 2})
    assert [e["id"] for e in log.list(CENTRAL)] == ["report:R2"]
    log.answer(CENTRAL, "report:R2")
    log.add(CENTRAL, "report", {"id": "R3", "child": FILM, "at": T - 1})
    assert [e["id"] for e in log.list(CENTRAL)] == ["report:R2", "report:R3"]   # an answered card stays in the log


# ---- the bridge ----
def test_job_end_and_reports_are_logged_and_a_reload_draws_them(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.CARDLOG = L.CardLog(tmp_path / "cardlog.json")
    m._job_ended(_job("J7", CENTRAL, time.time()))           # Jobs.on_end, as a job finishes
    calls = []
    done = _fake_turn(m, monkeypatch, calls)
    srv, base = _serve(m)
    try:
        st, _ = _call(f"{base}/threads/{FILM}/say", {"message": "cut it", "from": CENTRAL})
        assert st == 202 and done.wait(10)
        st, d = _call(f"{base}/cards?thread={CENTRAL}")           # before any page took anything
        assert st == 200 and [e["kind"] for e in d["cards"]] == ["job", "report"]
        st, j = _call(f"{base}/jobs?take=1&thread={CENTRAL}")     # the page takes the report once, as before
        assert len(j["reports"]) == 1 and "sides_ready" in j
        st, d2 = _call(f"{base}/cards?thread={CENTRAL}")          # the reload after: the same cards, still there
        assert [e["id"] for e in d2["cards"]] == [e["id"] for e in d["cards"]]
        assert _call(f"{base}/cards?thread={PLAIN}")[1]["cards"] == []
        st, a = _call(f"{base}/cards/answered", {"thread": CENTRAL, "id": d["cards"][0]["id"]})
        assert st == 200 and a["ok"] and _call(f"{base}/cards?thread={CENTRAL}")[1]["cards"][0]["answered"]
    finally:
        srv.shutdown()


def test_the_cards_door_needs_the_console_login(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path, token="tok")
    m.CARDLOG = L.CardLog(tmp_path / "cardlog.json")
    m.CARDLOG.add(CENTRAL, "job", _job("J1", CENTRAL, time.time() - 5))
    srv, base = _serve(m)
    try:
        assert _call(f"{base}/cards?thread={CENTRAL}")[0] == 403
        assert _call(f"{base}/cards?thread={CENTRAL}", headers={"X-CC-Operator": "tok", "Origin": "null"})[0] == 403
        assert _call(f"{base}/cards/answered", {"thread": CENTRAL, "id": "job:J1"})[0] == 403
        assert len(_call(f"{base}/cards?thread={CENTRAL}", headers={"X-CC-Operator": "tok"})[1]["cards"]) == 1
    finally:
        srv.shutdown()


def test_a_typed_turn_answers_the_threads_open_cards_a_steer_does_not(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.CARDLOG = L.CardLog(tmp_path / "cardlog.json")
    m.CARDLOG.add(CENTRAL, "job", _job("J1", CENTRAL, time.time() - 5))
    m.CARDLOG.add(FILM, "job", _job("J2", FILM, time.time() - 5))
    _fake_turn(m, monkeypatch, [])
    m._turn("cut it", thread=FILM, new=False, source="steer")
    assert m.CARDLOG.open_count(FILM) == 1
    m._turn("ok, next", thread=CENTRAL, new=False)
    assert m.CARDLOG.open_count(CENTRAL) == 0


# ---- ui/lib/cardlog.js ----
def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_cardlog_lib_under_node():
    d = _node(r"""
const L = require('./cardlog')
const t0 = Date.parse('2026-11-23T17:00:00Z') / 1000
const msgs = [{ who: 'me', text: 'a', at: L.whenOf('2026-11-23T17:00:00') }, { who: 'brain', text: 'b', at: t0 + 10 },
              { who: 'me', text: 'c' }, { who: 'brain', text: 'd', at: t0 + 100 }]
const log = [{ id: 'job:J1', kind: 'job', at: t0 + 50, answered: true, data: { id: 'J1' } },
             { id: 'report:R1', kind: 'report', at: t0 + 500, answered: false, data: { id: 'R1' } },
             { id: 'x:1', kind: 'other', at: t0, data: { id: '1' } }]
const merged = L.merge(msgs, log)
let t = L.addLive(merged, 'job', { id: 'J1' })
const same = t === merged
t = L.addLive(t, 'job', { id: 'J2' })
console.log(JSON.stringify({
  bare: L.whenOf('2026-11-23T17:00:00') === t0, zoned: L.whenOf('2026-11-23T12:00:00-05:00') === t0, none: L.whenOf(null),
  order: merged.map(x => x.text || x.logId), answered: merged.filter(x => x.logId).map(x => x.answered),
  same, live: t.length, open: L.openCount(t), after: L.openCount(L.answerAll(t)),
}))
""")
    assert d["bare"] and d["zoned"] and d["none"] is None
    assert d["order"] == ["a", "b", "c", "job:J1", "d", "report:R1"]
    assert d["answered"] == [True, False] and d["same"] and d["live"] == 7 and d["open"] == 2 and d["after"] == 0


def test_page_draws_the_log_and_keeps_drafts():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "/cc/cards?thread=" in src and "setTurns(logMerge(msgs, log))" in src
    assert "setTurns(t => logAddLive(t, 'job', j))" in src and "setTurns(t => logAddLive(t, 'report', rp))" in src
    assert "/cc/cards/answered" in src and "<CardState" in src
    assert "'cc.draft.' + cur" in src and "localStorage.removeItem(key)" in src
