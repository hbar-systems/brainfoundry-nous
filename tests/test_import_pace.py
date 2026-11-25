"""Moving in at the pace a brain can take (IMPORT-PACE-1, 2026-11-24): api/import_pace.py and its wiring.

Synthetic files and names only. What a member's sitting showed and these tests hold:
- the first pass fits about 15 minutes of reading at the measured rate, named folders and recent small
  documents first, books overnight unless the person says now; the helper sends in that order;
- one true count: /documents/waiting counts every pending proposal (1,825, not a page of 200 or 1,000),
  the run's arrivals are counted exactly past the 500-row list;
- "Remember all" is one press for a kind, kept on disk, joined by the run's later files, never twice;
- a busy brain answers 503 "wait" before the file is charged, and the agent sends it again;
- refused files are listed by reason and "send these again" retries only the retryable ones.
Created 2026-11-24.
"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from tests.test_move_in_survey import NOW, _home, server, h, li, ls  # noqa: F401  (fixture and helpers)
from tests.test_laptop_agent import _run_line, needs_shell
from api import import_pace as pace
from api import laptop_agent as la
from api import chat_continue as cc

ROOT = Path(__file__).resolve().parents[1]
DAY = 86400


# ── the reading cost and the first pass ──

def test_read_seconds_follow_the_measured_rate():
    assert pace.SECONDS_PER_CHUNK == pace.MEASURED["seconds_per_chunk"]
    note = pace.read_seconds("Documents/n.md", 2700)                      # 400 words: one chunk
    assert note == pytest.approx(pace.FIXED_SECONDS + pace.SECONDS_PER_CHUNK)
    deck = pace.read_seconds("Work/deck.pdf", 60 * 1024)                  # ~1,500 words at 40 B a word
    assert 3 * pace.SECONDS_PER_CHUNK < deck < 5 * pace.SECONDS_PER_CHUNK
    book = pace.read_seconds("Books/b.pdf", 8 * 1024 ** 2)
    assert book > 30 * 60                                                 # a book is never a first-pass file
    assert pace.is_big("Books/b.pdf", 8 * 1024 ** 2) and not pace.is_big("Books/b.md", 8 * 1024 ** 2)


def test_first_pass_fits_the_budget_named_and_recent_first_books_overnight():
    rows = [(f"Archive/old-{i:03d}.md", 2700, NOW - 400 * DAY, "knowledge") for i in range(200)]
    rows += [(f"Documents/new-{i:03d}.md", 2700, NOW - 2 * DAY, "knowledge") for i in range(200)]
    rows += [("Thesis/chapter.md", 30_000, NOW - 900 * DAY, "knowledge")]
    rows += [("Books/big.pdf", 9 * 1024 ** 2, NOW, "knowledge"), ("Music/a.wav", 10 ** 7, NOW, "files")]
    first, order, est = pace.first_pass(rows, now=NOW, named=["Thesis"])
    assert est["first_seconds"] <= pace.FIRST_PASS_SECONDS
    assert "Thesis/chapter.md" in first                                   # named, though old
    assert "Books/big.pdf" not in first and est["big_files"] == 1         # overnight by default
    picked = [p for p in first if p.startswith(("Documents/", "Archive/"))]
    assert all(p.startswith("Documents/") for p in picked)                # recent before old
    assert est["first_files"] == len(first) and est["rest_files"] == 402 - len(first) and est["kept_files"] == 1
    assert order[:len(first)] == [p for p in order if p in first]          # first pass sent first
    assert order.index("Music/a.wav") == len(first)                       # then what is kept as files
    assert order[-1] == "Books/big.pdf"                                   # the rest, smallest first
    assert sorted(order) == sorted(r[0] for r in rows)                    # nothing lost, nothing added
    first_now, _o, _e = pace.first_pass(rows[-2:], now=NOW, big_now=True, budget=10 ** 6)
    assert "Books/big.pdf" in first_now


def test_first_pass_at_the_measured_rate_is_about_seventy_notes():
    rows = [(f"Documents/n{i:04d}.md", 2700, NOW, "knowledge") for i in range(1865)]
    _f, _o, est = pace.first_pass(rows, now=NOW)
    # 15 minutes at 15.9 s a chunk: the honest size of "usable in 15 minutes" on 2 cores
    assert 50 <= est["first_files"] <= 60
    assert est["rest_seconds"] / 3600 > 7                                 # the rest is a night's reading


# ── the one count, refusals ──

def test_split_waiting_uses_the_servers_chat_rule():
    names = ["laptop/Documents/a.md", "chatgpt_2025-01-01_x.md", "claude-code_y.md", "laptop/b.pdf"]
    assert pace.split_waiting(names, cc.CHAT_DOC) == {"documents": 2, "chats": 2, "total": 4}
    assert pace.kind_matches("codex_z.md", "chats", cc.CHAT_DOC)
    assert not pace.kind_matches("codex_z.md", "documents", cc.CHAT_DOC)
    assert pace.kind_matches("anything", "all", cc.CHAT_DOC)


@pytest.mark.parametrize("code,reason", [(413, "too_big"), (415, "type"), (503, "busy"), (0, "busy"), ("000", "busy"),
                                         (429, "busy"), (404, "gone"), (422, "other"), ("x", "busy")])
def test_refusal_reasons(code, reason):
    assert pace.refusal_reason(code) == reason


def test_tally_and_order():
    assert pace.tally_refused([{"reason": "busy"}, {"reason": "busy"}, {"reason": "nonsense"}]) == {"busy": 2, "other": 1}
    items = [{"proposal_id": "a", "source_refs": {"filename": "laptop/big.md"}},
             {"proposal_id": "b", "source_refs": {"filename": "laptop/small.md"}},
             {"proposal_id": "c", "source_refs": {"filename": "laptop/first.md"}}]
    size = {"a": 900, "b": 10, "c": 500}
    got = pace.reading_order(items, ["laptop/first.md"], lambda p: size[p["proposal_id"]])
    assert [p["proposal_id"] for p in got] == ["c", "b", "a"]


def test_read_gate_one_reader_short_queue():
    g = pace.ReadGate(readers=1, queue=1)
    assert g.enter(0.1)                       # reading
    out = []
    t = threading.Thread(target=lambda: out.append(g.enter(2.0)))
    t.start()
    time.sleep(0.1)                           # one waits in the queue
    assert g.enter(0.1) is False              # the next hears "wait" at once
    g.leave()
    t.join(3)
    assert out == [True]
    g.leave()


def test_chat_clock_steps_aside():
    c = pace.ChatClock()
    assert not c.busy()
    c.begin()
    assert c.busy()
    slept = []
    c.end()
    c.last -= pace.CHAT_QUIET_SECONDS + 1
    assert c.wait_quiet(sleep=slept.append) < 0.5 and slept == []


# ── the survey store: order, refused, retry ──

def _inv(rows):
    return ls.validate({"files": rows, "skipped": {}, "roots": []})


def test_choose_makes_the_first_pass_and_take_follows_it(tmp_path):
    st = ls.SurveyStore(tmp_path)
    key = "b" * 64
    rows = [[f"Documents/n{i:03d}.md", 2700, NOW] for i in range(120)]
    rows += [["Books/big.pdf", 9 * 1024 ** 2, NOW], ["Music/a.wav", 100, NOW]]
    st.put(key, _inv(rows), NOW)
    pub = ls.public(st.get(key)["groups"])
    assert all("meta" not in g and "paths" not in g for g in pub)
    books = [g for g in pub if g["folder"] == "Books"][0]
    assert books["big"] == 1 and books["big_bytes"] == 9 * 1024 ** 2
    caps = {"max_files": 1000, "max_bytes": 10 ** 11, "files": 0, "bytes": 0}
    t = st.choose(key, "proposed", caps)
    est = t["estimate"]
    assert est["first_files"] < 120 and est["big_files"] == 1 and est["big_now"] is False
    paths = [p for p, _k in st.take(key)["paths"]]
    first = set(st.get(key)["first"])
    assert set(paths[:len(first)]) == first and paths[-1] == "Books/big.pdf"
    assert len(paths) == len(set(paths)) == 122


def test_refused_and_retry(tmp_path):
    st = ls.SurveyStore(tmp_path)
    key = "c" * 64
    st.put(key, _inv([["Documents/a.md", 10, NOW], ["Documents/b.md", 10, NOW], ["Documents/c.pdf", 10, NOW]]), NOW)
    by = st.refused(key, [{"path": "Documents/a.md", "code": 503}, {"path": "Documents/b.md", "code": "413"},
                          {"path": "Elsewhere/x.md", "code": 503}])          # a name the run never listed is dropped
    assert by == {"busy": 1, "too_big": 1}
    assert st.retry_take(key) is None                                      # nothing until the owner asks
    assert st.ask_retry(key) == 1
    assert st.retry_take(key) == [["Documents/a.md", "knowledge"]]         # only the retryable
    assert la.lines_form("retry", {"paths": st.retry_take(key)}) == "state retry\nknowledge\tDocuments/a.md\n"


def test_arrival_counts_are_exact_past_the_list(tmp_path):
    store = li.TokenStore(tmp_path / "t.json")
    tok = store.mint(max_files=5000)["token"]
    for i in range(li.ARRIVALS_KEPT + 300):
        store.note(tok, {"path": f"d/{i}.md", "kind": "knowledge"})
    for i in range(21):
        store.note(tok, {"path": f"m/{i}.wav", "kind": "audio"})
    run = store.latest()
    assert len(run["arrived"]) == li.ARRIVALS_KEPT
    assert run["counts"] == {"knowledge": li.ARRIVALS_KEPT + 300, "audio": 21}


# ── the routes ──

def _api_env(monkeypatch, server, pending):
    m = server.m
    monkeypatch.setattr(m, "_REMEMBER_FILE", server.tmp / "remember_all.json")
    monkeypatch.setattr(m, "_pending_document_proposals", lambda: list(pending))
    started = []
    monkeypatch.setattr(m, "_approve_all_worker", lambda items: started.extend(p["proposal_id"] for p in items))
    m._APPROVE_ALL.update(running=False, total=0, done=0)
    m._APPROVE_SEEN.clear()
    return started


def _wait(cond, n=100):
    for _ in range(n):
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_waiting_is_the_one_true_count(monkeypatch, server):
    from fastapi.testclient import TestClient
    pending = [{"proposal_id": f"p{i}", "memory_type": "document_embedding",
                "source_refs": {"filename": f"laptop/Documents/n{i}.md"}} for i in range(1825)]
    pending += [{"proposal_id": f"c{i}", "memory_type": "document_embedding",
                 "source_refs": {"filename": f"chatgpt_2025-01-0{i}_t.md"}} for i in range(3)]
    _api_env(monkeypatch, server, pending)
    j = TestClient(server.m.app).get("/documents/waiting").json()
    assert (j["documents"], j["chats"], j["total"]) == (1825, 3, 1828)
    assert j["reading"]["running"] is False and j["remember"] is None


def test_remember_all_by_kind_is_kept_and_never_twice(monkeypatch, server):
    from fastapi.testclient import TestClient
    m = server.m
    pending = [{"proposal_id": f"p{i}", "memory_type": "document_embedding",
                "source_refs": {"filename": f"laptop/Documents/n{i}.md"}} for i in range(1200)]
    pending += [{"proposal_id": "c1", "memory_type": "document_embedding", "source_refs": {"filename": "claude_x.md"}}]
    started = _api_env(monkeypatch, server, pending)
    c = TestClient(m.app)
    j = c.post("/documents/approve-all", json={"kind": "documents"}).json()
    assert j["total"] == 1200                                               # every one, not a page of 1,000
    assert _wait(lambda: len(started) == 1200) and "c1" not in started
    assert json.loads((server.tmp / "remember_all.json").read_text())["kind"] == "documents"
    # a second press while the batch runs queues nothing twice
    m._APPROVE_ALL.update(running=True)
    j = c.post("/documents/approve-all", json={"kind": "documents"}).json()
    assert j["queued"] == 0 and j["total"] == 1200
    m._APPROVE_ALL.update(running=False)


def test_remember_follows_the_runs_later_files(monkeypatch, server):
    from fastapi.testclient import TestClient
    m = server.m
    started = _api_env(monkeypatch, server, [])
    c = TestClient(m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    c.post("/documents/approve-all", json={"kind": "documents", "follow": True})
    intent = json.loads((server.tmp / "remember_all.json").read_text())
    assert intent["follow"] == m._LAPTOP_TOKENS.latest_hash()
    m._remember_follow({"proposal_id": "late-1", "source_refs": {"filename": "laptop/Documents/late.md"}}, tok)
    m._remember_follow({"proposal_id": "late-2", "source_refs": {"filename": "chatgpt_x.md"}}, tok)   # not its kind
    assert _wait(lambda: started == ["late-1"])


def test_busy_brain_says_wait_before_charging(monkeypatch, server):
    from fastapi.testclient import TestClient
    m = server.m
    c = TestClient(m.app)
    tok = c.post("/documents/import-laptop/token").json()["token"]

    class Full:
        def enter(self, timeout=0):
            return False

        def leave(self):
            raise AssertionError("never entered")
    monkeypatch.setattr(m, "_READ_GATE", Full())
    r = c.post("/documents/import-laptop/file", data={"path": "Documents/a.md"},
               files={"file": ("a.md", b"hello", "text/markdown")}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 503 and r.headers["retry-after"] == str(pace.RETRY_AFTER_SECONDS)
    assert m._LAPTOP_TOKENS.latest()["files"] == 0                         # not charged


def test_plan_takes_books_now_or_overnight(monkeypatch, server):
    from fastapi.testclient import TestClient
    m = server.m
    c = TestClient(m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]
    inv = {"files": [["Documents/a.md", 2700, NOW], ["Books/b.pdf", 9 * 1024 ** 2, NOW]], "skipped": {}, "roots": []}
    assert c.post("/documents/import-laptop/check", json=inv, headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    t = c.post("/documents/import-laptop/plan", json={"take": "proposed", "big": "now"}).json()
    assert t["estimate"]["big_now"] is True
    st = c.get("/documents/import-laptop/status").json()["survey"]
    assert st["estimate"]["big_files"] == 1 and st["refused_total"] == 0


# ── the agent, end to end, with a busy brain ──

class FlakyGate:
    """Busy (wait) while .busy is set; a reader slot otherwise."""
    def __init__(self):
        self.busy = True
        self.refusals = 0

    def enter(self, timeout=0):
        if self.busy:
            self.refusals += 1
            return False
        return True

    def leave(self):
        pass


@needs_shell
def test_agent_waits_lists_refused_and_sends_them_again(monkeypatch, server, tmp_path):
    from fastapi.testclient import TestClient
    m = server.m
    gate = FlakyGate()
    monkeypatch.setattr(m, "_READ_GATE", gate)
    home = tmp_path / "home"
    _home(home)
    agent_tmp = tmp_path / "agent-tmp"
    agent_tmp.mkdir()
    c = TestClient(m.app)
    tok = c.post("/documents/import-laptop/token", json={"survey": True}).json()["token"]

    def owner():
        for _ in range(600):
            st = c.get("/documents/import-laptop/status").json()["survey"]
            if st and st.get("state") == "plan":
                ids = [g["id"] for g in st["groups"] if g["proposal"] != "leave"]
                assert c.post("/documents/import-laptop/plan", json={"take": ids}).status_code == 200
                break
            time.sleep(0.05)
        for _ in range(1200):
            st = c.get("/documents/import-laptop/status").json()["survey"]
            if st and st.get("refused_total"):
                assert st["refused_by"] == {"busy": 8}
                gate.busy = False
                assert c.post("/documents/import-laptop/retry").json() == {"retry": 8}
                return
            time.sleep(0.05)
    t = threading.Thread(target=owner)
    t.start()
    r = _run_line(server.url, tok, home, agent_tmp, extra_env={"BRAIN_AGENT_TRIES": "2", "BRAIN_AGENT_PAUSE": "1",
                                                               "BRAIN_AGENT_NO_TTY": "1"}, timeout=120)
    t.join(10)
    out = r.stdout
    assert r.returncode == 0, out + r.stderr
    assert "your brain is busy reading; trying again in 1 s" in out
    assert "Not taken, by reason: brain busy 8." in out
    assert "Sending the 8 again." in out
    assert "Done: 10 sent, 0 not taken." in out
    assert gate.refusals == 16                                             # 8 files, 2 tries each, none charged
    assert len(server.proposals) == 8
    assert list(agent_tmp.iterdir()) == []


def test_agent_words_both_languages():
    for lang in ("en", "ru"):
        for k in ("WAITBRAIN", "REFUSEDBY", "RETRYASK", "RETRYING", "REASON_busy", "REASON_too_big"):
            assert la.WORDS[lang][k]
    text = la.render("sh", "https://brain.example", "en")
    r = subprocess.run(["bash", "-n"], input=text, text=True, capture_output=True)
    assert r.returncode == 0, r.stderr


def test_home_words_and_rules_under_node():
    node = __import__("shutil").which("node")
    if not node:
        pytest.skip("node needed")
    js = r"""
const P = require(process.argv[1]);
const w = { reading: { running: true, done: 70, total: 1825, first_done: 58, first_total: 58, eta_seconds: 7 * 3600 } };
const r = P.readingState(w);
const line = P.planWords('en').readyNow(r.done, r.total, P.fmtHours(r.hours, 'en'));
const first = P.readingState({ reading: { running: true, done: 3, total: 1825, first_done: 3, first_total: 58 } });
const counts = P.arrivedCounts({ counts: { knowledge: 1825, audio: 21 }, arrived: new Array(500).fill({ kind: 'knowledge' }) });
const old = P.arrivedCounts({ arrived: [{ kind: 'knowledge' }, { kind: 'media' }] });
const ref = P.refusedState({ refused_by: { busy: 30, too_big: 10 }, refused_total: 40, refused: [] });
const big = P.bigTotals([{ id: 'a', big: 12, big_bytes: 5 }, { id: 'b', big: 1, big_bytes: 1 }], { a: true });
console.log(JSON.stringify({ line, first: first.step, counts, old, ref: [ref.total, ref.again], big, none: P.readingState(null).step,
  ru: P.planWords('ru').readyNow(1, 2, P.fmtHours(0.5, 'ru')) }));
"""
    r = subprocess.run([node, "-e", js, str(ROOT / "ui" / "lib" / "moveInPlan.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["line"] == "Ready to talk now. Still reading the rest: 70 of 1825, about 7 hours."
    assert j["first"] == "first" and j["none"] == "none"
    assert j["counts"] == {"docs": 1825, "audio": 21, "media": 0, "kept": 21}
    assert j["old"] == {"docs": 1, "audio": 0, "media": 1, "kept": 1}
    assert j["ref"] == [40, 30] and j["big"] == {"files": 12, "bytes": 5}
    assert j["ru"] == "Можно говорить. Дочитываю остальное: 1 из 2, меньше часа."


def test_onboarding_estimate_is_under_thirty_minutes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("onboarding_time", ROOT / "scripts" / "import" / "onboarding_time.py")
    ot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ot)
    est = ot.estimate()
    assert est["green"] and est["total_s"] < ot.TARGET_SECONDS
    assert est["first_pass_s"] <= pace.FIRST_PASS_SECONDS
    assert ot.main(["--estimate"]) == 0 and ot.main([]) == 2


def test_a_kept_yes_covers_only_what_it_was_given(monkeypatch, server):
    """After a restart the kept "Remember all" resumes the ids pressed on and that run's files, never a
    document proposed later by another door."""
    from fastapi.testclient import TestClient
    m = server.m
    pressed = [{"proposal_id": "p1", "memory_type": "document_embedding", "source_refs": {"filename": "laptop/Documents/a.md"}}]
    _api_env(monkeypatch, server, pressed)
    c = TestClient(m.app)
    c.post("/documents/approve-all", json={"kind": "documents"})
    intent = json.loads((server.tmp / "remember_all.json").read_text())
    later = {"proposal_id": "p9", "memory_type": "document_embedding", "source_refs": {"filename": "upload/other.md"}}
    assert m._remember_covers(intent, pressed[0]) and not m._remember_covers(intent, later)
    m._APPROVE_ALL.update(running=False)


def test_waiting_states_the_room(monkeypatch, server):
    """MEMBERS-15: the home states the plain limits beside the import (Anne's "do we have limits?")."""
    from fastapi.testclient import TestClient
    _api_env(monkeypatch, server, [])
    monkeypatch.setenv("BRAIN_LIMIT_DISK_GB", "15")
    room = TestClient(server.m.app).get("/documents/waiting").json()["room"]
    assert room["run_files"] == 20000 and room["share_gb"] == 15.0
    assert room["run_bytes"] is None or room["run_bytes"] >= 0
    monkeypatch.delenv("BRAIN_LIMIT_DISK_GB")
    assert TestClient(server.m.app).get("/documents/waiting").json()["room"]["share_gb"] is None


def test_room_words_both_languages():
    node = __import__("shutil").which("node")
    if not node:
        pytest.skip("node needed")
    js = r"""
const P = require(process.argv[1]);
const out = {};
for (const l of ['en', 'ru']) { const W = P.planWords(l); out[l] = [W.roomIn(1, 0), W.roomIn(600, 200), W.roomLimit(20000, '8 GB', 15), W.roomLimit(20000, '8 GB', null), W.roomSpoke]; }
console.log(JSON.stringify(out));
"""
    r = subprocess.run([node, "-e", js, str(ROOT / "ui" / "lib" / "moveInPlan.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["en"][0] == "Inside: 1 document."
    assert j["en"][1] == "Inside: 600 documents, 200 waiting for your yes."
    assert "15 GB" in j["en"][2] and "share" not in j["en"][3]
    assert j["ru"][1].startswith("Внутри: 600 документов, 200 ждут")
    assert all(len(s.split(". ")) <= 2 for s in (j["en"][4], j["ru"][4]))


def test_a_file_mid_read_at_a_restart_is_read_again(monkeypatch, server):
    """MEMBERS-16: the worker decides APPROVE before it reads, so a restart mid-read left that file approved and
    never stored (1 of 4 test notes on Elena's and Alexander's brains, 2026-11-25). The kept yes now takes it up
    again after the restart, read once, not decided twice; a stored one (text deleted) is not read again."""
    m = server.m
    tdir = server.tmp / "proposal_texts"
    tdir.mkdir(exist_ok=True)
    monkeypatch.setattr(m, "PROPOSAL_TEXT_DIR", tdir)
    doc = lambda pid, n: {"proposal_id": pid, "memory_type": "document_embedding",
                          "source_refs": {"filename": f"laptop/Documents/{n}.md"}}
    lists = {"PENDING": [doc("p3", "c"), doc("p4", "d")], "APPROVED": [doc("p1", "a"), doc("p2", "b"), doc("old", "z")]}
    monkeypatch.setattr(m, "_document_proposals", lambda status: [dict(p) for p in lists[status]])
    for pid, n in (("p2", "b"), ("old", "z"), ("p3", "c"), ("p4", "d")):   # p2 mid-read (text kept); p1 stored (deleted); old: not this yes
        m._save_proposal_text(pid, f"note {pid}", filename=f"laptop/Documents/{n}.md", content_type="text/markdown", size=6)
    intent = {"kind": "documents", "follow": None, "at": 0, "ids": ["p1", "p2", "p3", "p4"]}
    items = m._resume_items(intent)
    assert sorted(p["proposal_id"] for p in items) == ["p2", "p3", "p4"]
    assert [p.get("approved") for p in items if p["proposal_id"] == "p2"] == [True]
    decided, read = [], []
    monkeypatch.setattr(m, "_nodeos_decide_memory", lambda pid, *a, **k: decided.append(pid) or {"status": "APPROVED"})
    def ingest(**kw):
        read.append(kw["proposal_id"]); yield "event: done\ndata: {}\n\n"
    monkeypatch.setattr(m, "_stream_ingest_path_b", ingest)
    monkeypatch.setattr(m._pace, "PACE_SECONDS", 0)
    monkeypatch.setattr(m, "_REMEMBER_FILE", server.tmp / "remember_all.json")
    m._approve_all_worker(items)
    assert sorted(read) == ["p2", "p3", "p4"] and sorted(decided) == ["p3", "p4"]
    assert m._APPROVE_ALL["failed"] == []


def test_one_bring_in_never_passes_what_is_left_of_the_share(monkeypatch, server):
    """MEMBERS-16: on a shared box the run's byte cap is the smaller of the fixed cap and what is left of the
    brain's share (the hourly disk check's file), and the page says so."""
    from fastapi.testclient import TestClient
    m = server.m
    _api_env(monkeypatch, server, [])
    f = server.tmp / "disk_share.json"
    monkeypatch.setattr(m, "_DISK_SHARE_FILE", f)
    G = 1024 ** 3
    f.write_text(json.dumps({"quota_gb": 15, "used_bytes": 13 * G, "at": "2026-11-25T16:00:00Z"}))
    room = TestClient(m.app).get("/documents/waiting").json()["room"]
    assert room["share_gb"] == 15.0 and room["share_left_bytes"] == 2 * G
    assert room["run_bytes"] <= 2 * G                       # was 20 GB against a 15 GB share
    tok = TestClient(m.app).post("/documents/import-laptop/token", json={"survey": True}).json()
    assert tok.get("max_bytes", 0) <= 2 * G
    f.write_text(json.dumps({"quota_gb": 15, "used_bytes": 16 * G}))   # over the share: nothing more comes in
    assert TestClient(m.app).get("/documents/waiting").json()["room"]["run_bytes"] == 0
    f.unlink()
    assert TestClient(m.app).get("/documents/waiting").json()["room"]["share_gb"] is None


def test_share_words_both_languages():
    node = __import__("shutil").which("node")
    if not node:
        pytest.skip("node needed")
    js = r"""
const P = require(process.argv[1]);
console.log(JSON.stringify(['en', 'ru'].map(l => P.planWords(l).roomLimit('20,000', '12.4 GB', 15, '12.4 GB'))));
"""
    r = subprocess.run([node, "-e", js, str(ROOT / "ui" / "lib" / "moveInPlan.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    en, ru = json.loads(r.stdout)
    assert "the smaller of the fixed limit and what is left of this brain's 15 GB share" in en and "(12.4 GB left)" in en
    assert "меньшее из постоянного предела" in ru and "осталось 12.4 GB" in ru
