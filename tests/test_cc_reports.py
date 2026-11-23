"""Thread reports (REPORT-1, 2026-11-22): a thread started from another thread's choice button
(mode agent) leaves a short card for its parent each time it finishes a turn.
scripts/cc/cc_reports.py on temp dirs, ui/lib/reports.js under node, and the bridge's wiring
with no network and no reasoner.

Run from repo root:
    pytest tests/test_cc_reports.py -v
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
spec = importlib.util.spec_from_file_location("cc_reports", ROOT / "scripts" / "cc" / "cc_reports.py")
R = importlib.util.module_from_spec(spec); sys.modules["cc_reports"] = R; spec.loader.exec_module(R)


def test_first_lines_skip_markers_rules_and_fences():
    text = ("# Result\n\n---\n**Done.** The page builds.\n\n```\ncode\n```\n> quoted line\n"
            "fourth line\n<!--pane:/files-->\n<choices>[{\"label\": \"go\"}]</choices>")
    assert R.first_lines(text) == ["Result", "**Done.** The page builds.", "code"]
    assert R.first_lines("a\n\nb") == ["a", "b"]
    assert R.first_lines("") == [] and R.first_lines(None) == []
    assert R.first_lines("<choices>[1]") == []                      # an unclosed marker hides its tail, not shows it
    long = R.first_lines("x" * 500)[0]
    assert len(long) == R.WIDTH and long.endswith("…")
    assert R.first_lines("one\ntwo\nthree\nfour\nfive", n=3) == ["one", "two", "three"]


def test_state_of_most_urgent_first():
    assert R.state_of(reply="fine") == "done"
    assert R.state_of(reply="pick\n<choices>[]</choices>") == "asks you"
    assert R.state_of(card={"id": "p1"}, reply="<choices>[]</choices>") == "waits for your yes"
    assert R.state_of(card={"id": "p1", "auto": True}) == "done"    # a write done without asking waits for nobody
    assert R.state_of(stopped=True, card={"id": "p1"}) == "stopped"
    assert R.state_of(error=True, stopped=True) == "failed"
    assert set(R.STATES) == {"done", "asks you", "waits for your yes", "stopped", "failed"}


def test_card_goes_to_the_parent_only_and_once(tmp_path):
    s = R.Reports(tmp_path / "reports.json")
    assert s.link("child", "parent", "fix the page")
    card = s.post("child", title="CC: Take this on: ops/x.md", state="done", reply="Did it.\nTwo files.\nNo push.\nMore.")
    assert card["parent"] == "parent" and card["child"] == "child"
    assert card["title"] == "Take this on: ops/x.md" and card["state"] == "done"
    assert card["lines"] == ["Did it.", "Two files.", "No push."]
    assert s.waiting() == {"parent": 1}
    # the 2026-10-11 rule: no other thread's page gets it, not the child's own, not one without an id
    assert s.take("other") == [] and s.take("child") == [] and s.take(None) == [] and s.take("new:1") == []
    got = s.take("parent")
    assert [c["id"] for c in got] == [card["id"]]
    assert s.take("parent") == [] and s.waiting() == {}             # handed over once


def test_ordinary_thread_reports_to_nobody(tmp_path):
    s = R.Reports(tmp_path / "reports.json")
    assert s.post("lonely", title="CC: x", reply="hello") is None
    assert s.waiting() == {} and not (tmp_path / "reports.json").exists()


def test_every_later_turn_reports_and_an_unread_card_is_replaced(tmp_path):
    s = R.Reports(tmp_path / "reports.json")
    s.link("child", "parent")
    s.post("child", title="CC: job", state="asks you", reply="first")
    s.post("child", title="CC: job", state="done", reply="second")
    got = s.take("parent")
    assert len(got) == 1 and got[0]["lines"] == ["second"] and got[0]["state"] == "done"
    s.post("child", title="CC: job", state="done", reply="third")   # a turn after the parent read: a new card
    assert [c["lines"] for c in s.take("parent")] == [["third"]]


def test_links_first_wins_no_self_no_loop(tmp_path):
    s = R.Reports(tmp_path / "reports.json")
    assert not s.link("a", "a") and not s.link("new:1", "p") and not s.link("a", "new:2") and not s.link("a", "unknown")
    assert s.link("a", "p") and s.link("a", "p")
    assert not s.link("a", "q") and s.parent_of("a") == "p"         # a thread has one origin
    assert not s.link("p", "a")                                     # two threads never report to each other
    assert s.link("b", "a") and s.parent_of("b") == "a"             # a grandchild reports to its own parent
    s.post("b", title="CC: b", reply="x")
    assert s.take("p") == [] and len(s.take("a")) == 1
    assert s.unlink("a") and s.parent_of("a") is None and s.post("a", reply="x") is None


def test_first_turn_that_never_got_an_id_still_tells_the_parent(tmp_path):
    s = R.Reports(tmp_path / "reports.json")
    card = s.post(None, title=None, state="failed", reply="The bridge failed this turn: OSError", parent="parent", label="build X")
    assert card["child"] is None and card["title"] == "build X" and card["state"] == "failed"
    assert s.post(None, reply="x", parent="new:1") is None          # a parent without an id is no parent
    assert len(s.take("parent")) == 1


def test_survives_restart_broken_file_and_expires(tmp_path):
    f = tmp_path / "state" / "reports.json"
    s = R.Reports(f)
    s.link("child", "parent"); s.post("child", title="CC: t", reply="kept")
    again = R.Reports(f)                                            # the bridge restarted before the parent's page polled
    assert again.parent_of("child") == "parent" and [c["lines"] for c in again.take("parent")] == [["kept"]]
    f.write_text('{"links": {"chi')                                 # a short write reads as empty, never raises
    assert again.take("parent") == [] and again.parent_of("child") is None
    old = R.Reports(tmp_path / "old.json", ttl=1)
    old.link("c", "p"); old.post("c", reply="x")
    d = json.loads((tmp_path / "old.json").read_text()); d["cards"][0]["at"] = time.time() - 5
    (tmp_path / "old.json").write_text(json.dumps(d))
    assert old.take("p") == [] and old.waiting() == {}
    s2 = R.Reports(tmp_path / "s2.json"); s2.link("c", "p")
    assert s2.post("c", state="nonsense", reply="x")["state"] == "done"


def _node(script: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_ui_reports_stay_in_the_parent_thread():
    d = json.loads(_node(r"""
const R = require('./reports')
const cards = [{ id: 'R1', parent: 'abc', child: 'kid', title: 't', state: 'done', lines: ['a', '', 'b', 'c', 'd', 5] },
               { id: 'R2', parent: 'xyz', child: 'kid2', state: 'failed' }, { parent: 'abc' }, null,
               { id: 'R3', parent: 'abc', child: null, state: 'failed' }]
console.log(JSON.stringify({
  mine: R.mine(cards, 'abc').map(c => c.id), other: R.mine(cards, 'xyz').map(c => c.id),
  none: [R.mine(cards, 'new:1').length, R.mine(cards, null).length, R.mine(null, 'abc').length],
  href: [R.href(cards[0]), R.href(cards[4]), R.href({ child: 'new:9' }), R.href({ child: 'a b' })],
  tone: ['done', 'asks you', 'waits for your yes', 'stopped', 'failed', undefined].map(R.tone),
  lines: R.lines(cards[0]), nolines: R.lines({}),
  body: R.startBody({ send: 'do it', label: 'L'.repeat(200) }, 'abc'),
  bodyNew: R.startBody({ send: 'do it', label: 'x' }, 'new:3'), bodyNone: R.startBody({ send: 'do it' }, null),
}))"""))
    assert d["mine"] == ["R1", "R3"] and d["other"] == ["R2"] and d["none"] == [0, 0, 0]
    assert d["href"] == ["/talk?thread=kid", None, None, "/talk?thread=a%20b"]
    assert d["tone"] == ["good", "ask", "ask", "ask", "bad", "good"]
    assert d["lines"] == ["a", "b", "c"] and d["nolines"] == []
    assert d["body"]["parent"] == "abc" and len(d["body"]["label"]) == 120
    assert d["body"]["message"] == "do it" and d["body"]["new"] is True and d["body"]["stream"] is False
    # a page whose own conversation has no id yet names no parent: nothing to report to
    assert "parent" not in d["bodyNew"] and "parent" not in d["bodyNone"]


def test_page_wires_the_card_into_its_own_thread_only():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "JSON.stringify(reportStartBody(c, curRef.current))" in src       # the choice button names its thread
    assert "for (const rp of reportsMine(d.reports, cur))" in src            # only this thread's cards become bubbles
    assert "{t.report && <ReportCard report={t.report}" in src
    assert "function ReportCard({ report, onOpenHere })" in src and "href={url} target=\"_blank\"" in src


def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge"] = mod
    spec.loader.exec_module(mod)
    mod.REPORTS = R.Reports(tmp_path / "reports.json")
    return mod


def test_bridge_turn_reports_to_the_parent(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    seen = {}

    def inner(message, **kw):
        seen.update(kw)
        if kw["new"]:
            return 200, {"reply": "**Built it.**\nTests green.\nNot pushed.\nmore\n<choices>[{\"label\": \"push\"}]</choices>",
                         "thread": "kid", "title": "CC: Take this on: ops/x.md", "error": False, "stopped": False, "proposal": None}
        return 200, {"reply": "Second turn.", "thread": kw["thread"], "title": "CC: Take this on: ops/x.md",
                     "error": False, "stopped": True, "proposal": None}
    monkeypatch.setattr(m, "_turn_inner", inner)
    monkeypatch.setattr(m, "_drain_async", lambda t: None)
    monkeypatch.setattr(m, "_box_wait_next", lambda: None)

    m._turn("do it", thread=None, new=True, parent="mum", label="on x.md")
    assert seen["parent"] == "mum" and seen["label"] == "on x.md"
    got = m.REPORTS.take("mum")
    assert len(got) == 1 and got[0]["child"] == "kid" and got[0]["state"] == "asks you"
    assert got[0]["title"] == "Take this on: ops/x.md" and got[0]["lines"] == ["**Built it.**", "Tests green.", "Not pushed."]

    m._turn("and then?", thread="kid", new=False)                   # a later turn, sent in the child itself
    got = m.REPORTS.take("mum")
    assert len(got) == 1 and got[0]["state"] == "stopped" and got[0]["lines"] == ["Second turn."]

    m._turn("hello", thread="plain", new=False)                     # an ordinary thread reports to nobody
    m._turn("hello", thread="plain", new=False, parent="mum")       # and a parent is only taken for a NEW thread
    assert m.REPORTS.waiting() == {}

    monkeypatch.setattr(m, "_turn_inner", lambda message, **kw: (500, {"reply": "The bridge failed this turn: OSError", "error": True, "thread": None, "title": None}))
    m._turn("do it", thread=None, new=True, parent="mum", label="build X")
    got = m.REPORTS.take("mum")
    assert got[0]["state"] == "failed" and got[0]["child"] is None and got[0]["title"] == "build X"

    # a refused or queued turn (409, 202) is not a finished turn: no card
    monkeypatch.setattr(m, "_turn_inner", lambda message, **kw: (202, {"waiting": 1, "reply": "waits in line"}))
    m._turn("do it", thread=None, new=True, parent="mum", label="later")
    assert m.REPORTS.waiting() == {}

    # a report that cannot be written never fails the turn
    monkeypatch.setattr(m.REPORTS, "post", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert m._report_to_parent(200, {"reply": "x", "thread": "kid"}) is None


def test_bridge_wait_line_keeps_the_parent(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    assert '"parent": parent, "label": label}, front=waited)' in src           # a thread that waits for a slot still knows its parent
    assert '"parent": item.get("parent")' in src
    assert 'reports = REPORTS.take(th) if q.get("take") == "1" and th else []' in src and '"reports": reports,' in src   # only a page that names its thread takes
    assert 'any(x.get("brain") == parent for x in _threads_load())' in src     # a parent must be a thread on this box
