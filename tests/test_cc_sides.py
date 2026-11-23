"""Talk in place (INLINE-1, 2026-11-23): a side conversation bound to one item on a page.

hbar: "I don't want to leave this page ... the convo/thread is happening right there on that page in that
little box ... if I need to send agents they go get it done and then I stay on this page and see it when
they're done. I also want to be notified about all this."

A write door (it runs the reasoner with tools), so this file pins: the console login and the app-frame
refusal, the same _turn() path as a typed turn (no seat, parent or posture of its own), that the side's
thread is made first and kept off the thread list (it never moves the box's current thread), one turn at a
time, the rate cap, that an agent's report and job land in the home thread's log, the Telegram line (title
only, only when away), the page folder served on the console origin while /cc/files/raw stays sandboxed,
and that inline.js never writes HTML.

Run from repo root:
    pytest tests/test_cc_sides.py -v
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cc_sides", ROOT / "scripts" / "cc" / "cc_sides.py")
S = importlib.util.module_from_spec(spec); sys.modules["cc_sides"] = S; spec.loader.exec_module(S)
spec = importlib.util.spec_from_file_location("cc_cardlog", ROOT / "scripts" / "cc" / "cc_cardlog.py")
L = importlib.util.module_from_spec(spec); sys.modules["cc_cardlog"] = L; spec.loader.exec_module(L)

sys.path.insert(0, str(ROOT / "tests"))
from test_cc_steer import _bridge, _serve, _call, CENTRAL, PLAIN, R  # noqa: E402

SIDE = "cccccccc-1111-2222-3333-444444444444"
ITEM = {"key": "court-tasks:T12", "title": "Fix the door", "text": "The door 403s after Update.", "link": "/cc/page/court/tasks/#T12",
        "page": "court-tasks"}


# ---- the store ----
def test_first_turn_carries_the_item_later_turns_do_not(tmp_path):
    s = S.Sides(tmp_path / "s.json")
    st, d = s.begin(ITEM["key"], "why does it 403?", **{k: v for k, v in ITEM.items() if k != "key"})
    assert st == 200 and "Item: Fix the door." in d["prompt"] and "The door 403s" in d["prompt"] and "/cc/page/court/tasks/#T12" in d["prompt"]
    assert d["prompt"].endswith("why does it 403?") and d["side"]["state"] == "running"
    assert s.begin(ITEM["key"], "again")[0] == 409                                  # one turn at a time
    assert s.by_prompt(d["prompt"]) == ITEM["key"]
    s.finish_thread(ITEM["key"], SIDE)
    s.finish(ITEM["key"], ok=True, reply="Because the token rotated.", thread="new:1")
    side = s.get(ITEM["key"])
    assert side["thread"] == SIDE and side["ready"] and side["state"] == "ready" and side["turns"][-1]["text"] == "Because the token rotated."
    assert s.ready_count() == 1 and s.read(ITEM["key"]) and s.ready_count() == 0
    st, d = s.begin(ITEM["key"], "fix it", mode="agent")
    assert "Item:" not in d["prompt"] and S.AGENT_LINE in d["prompt"] and d["prompt"].endswith("fix it")
    assert s.thread_ids() == {SIDE}


def test_store_refuses_bad_keys_links_and_sizes(tmp_path):
    s = S.Sides(tmp_path / "s.json")
    assert s.begin("../x", "hi")[0] == 400 and s.begin("", "hi")[0] == 400 and s.begin("ok", "  ")[0] == 400
    assert s.begin("ok", "x" * (S.MESSAGE_MAX + 1))[0] == 413
    for bad in ("javascript:alert(1)", "//evil.example/x", "data:text/html,x", "http://plain.example"):
        s2 = S.Sides(tmp_path / f"{abs(hash(bad))}.json")
        assert s2.begin("k", "hi", link=bad)[1]["side"]["link"] == ""
    assert S.Sides(tmp_path / "z.json").begin("k", "hi", link="https://console.example/x")[1]["side"]["link"] == "https://console.example/x"


def test_touch_thread_and_presence(tmp_path):
    s = S.Sides(tmp_path / "s.json")
    s.begin("k", "hi"); s.finish_thread("k", SIDE); s.finish("k", ok=True, reply="a"); s.read("k")
    assert s.touch_thread(SIDE)["ready"] and s.get("k")["state"] == "ready"
    assert s.touch_thread("other") is None
    assert s.away()                                         # nobody ever looked
    s.seen(); assert not s.away() and s.away(time.time() + S.AWAY + 1)


# ---- the bridge ----
def _sides_bridge(monkeypatch, tmp_path, token=""):
    m = _bridge(monkeypatch, tmp_path, token=token)
    m.CARDLOG = L.CardLog(tmp_path / "cardlog.json")
    m.SIDES = S.Sides(tmp_path / "sides.json")
    m.SIDE_SENT.clear()
    made = []

    def api(method, path, body=None):
        if method == "POST" and path == "/sessions":
            made.append(body)
            return {"session_id": SIDE}
        return None
    monkeypatch.setattr(m, "_brain_api", api)
    return m, made


def _turns(m, monkeypatch, calls, reply="It rotated.\nSee /cc/files/raw/x.md", status=200):
    def inner(message, **kw):
        calls.append({"message": message, **kw})
        return status, {"reply": reply, "thread": kw.get("thread"), "title": "CC: note", "error": status != 200, "stopped": False, "proposal": None}
    monkeypatch.setattr(m, "_turn_inner", inner)
    monkeypatch.setattr(m, "_drain_async", lambda t: None)
    monkeypatch.setattr(m, "_box_wait_next", lambda: None)


def test_door_needs_the_console_login_and_refuses_app_frames(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path, token="tok")
    calls = []
    _turns(m, monkeypatch, calls)
    srv, base = _serve(m)
    try:
        body = {**ITEM, "message": "why?"}
        assert _call(f"{base}/sides/say", body)[0] == 403
        assert _call(f"{base}/sides/say", body, {"X-CC-Ask": m.ASK_TOKEN})[0] == 403               # the hands cannot talk in place
        assert _call(f"{base}/sides/say", body, {"X-CC-Operator": "tok", "Origin": "null"})[0] == 403   # /cc/files/raw, an app frame
        assert _call(f"{base}/sides/say", body, {"X-CC-Operator": "tok", "Sec-Fetch-Site": "cross-site"})[0] == 403
        assert _call(f"{base}/sides?page=court-tasks")[0] == 403 and _call(f"{base}/sides/count")[0] == 403
        time.sleep(0.2)
        assert calls == []
        st, d = _call(f"{base}/sides/say", body, {"X-CC-Operator": "tok"})
        assert st == 202 and d["ok"]
    finally:
        srv.shutdown()
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    exempt = src.split("def do_POST", 1)[1].split('if route not in (', 1)[1].split(')', 1)[0]
    assert "/sides" not in exempt and "/cards" not in exempt


def test_a_note_is_a_typed_turn_in_its_own_thread_off_the_list(monkeypatch, tmp_path):
    m, made = _sides_bridge(monkeypatch, tmp_path)
    calls = []
    _turns(m, monkeypatch, calls)
    before = m._load_state()
    st, d = m._sides_post("/sides/say", {**ITEM, "message": "why?", "home": CENTRAL}, start=lambda f: f())
    assert st == 202 and len(made) == 1 and made[0]["title"].startswith("CC: note: Fix the door")
    c = calls[0]
    assert c["thread"] == SIDE and c["new"] is False and c["source"] == "note"           # explicit: the box's current thread stays
    assert c.get("reasoner") is None and c.get("parent") is None and c.get("queue") is False
    assert "Item: Fix the door." in c["message"] and c["message"].endswith("why?")
    assert m._load_state() == before
    side = m.SIDES.get(ITEM["key"])
    assert side["state"] == "ready" and side["ready"] and side["turns"][-1]["text"].startswith("It rotated.")
    assert side["home"] == CENTRAL
    assert SIDE not in [x["brain"] for x in m._threads_view()["threads"]]                    # not a new thread in the list
    assert SIDE in [x["brain"] for x in m._threads_load()]                                    # but continuable
    assert m.REPORTS.take(CENTRAL) == [] and m.CARDLOG.list(CENTRAL) == []                    # a question reports to nobody
    # the second turn goes to the same side thread, without the item again
    st, _ = m._sides_post("/sides/say", {"key": ITEM["key"], "message": "and now?"}, start=lambda f: f())
    assert st == 202 and len(made) == 1 and calls[1]["thread"] == SIDE and "Item:" not in calls[1]["message"]


def test_send_an_agent_reports_into_the_home_threads_log(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    calls = []
    _turns(m, monkeypatch, calls, reply="Fixed the door.\nCommit abc123.")
    st, _ = m._sides_post("/sides/say", {**ITEM, "message": "fix it", "mode": "agent", "home": CENTRAL}, start=lambda f: f())
    assert st == 202
    assert S.AGENT_LINE in calls[0]["message"]
    [card] = m.REPORTS.take(CENTRAL)
    assert card["child"] == SIDE and card["title"].startswith("note: Fix the door") and card["lines"][0] == "Fixed the door."
    assert [e["kind"] for e in m.CARDLOG.list(CENTRAL)] == ["report"]
    # a job the agent started ends: its card is in the side and in the home thread's log
    m._job_ended({"id": "J5", "title": "fix door", "rc": 0, "started": time.time() - 9, "ended": time.time(), "thread": SIDE,
                  "result": {"rc": 0, "text": "ok"}})
    assert [e["kind"] for e in m.CARDLOG.list(CENTRAL)] == ["report", "job"]
    assert [e["kind"] for e in m.CARDLOG.list(SIDE)] == ["job"] and m.SIDES.get(ITEM["key"])["ready"]
    # a home that is not a thread on this box (or is a side itself) is dropped, the note still answers in place
    st, _ = m._sides_post("/sides/say", {"key": "k2", "message": "x", "mode": "agent", "home": SIDE}, start=lambda f: f())
    assert m.SIDES.get("k2")["home"] is None


def test_busy_failed_and_rate(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    calls = []
    _turns(m, monkeypatch, calls, reply="This conversation is still answering.", status=409)
    m._sides_post("/sides/say", {**ITEM, "message": "x"}, start=lambda f: f())
    side = m.SIDES.get(ITEM["key"])
    assert side["state"] == "failed" and "still answering" in side["error"]
    monkeypatch.setattr(m, "_brain_api", lambda *a, **k: None)
    m._sides_post("/sides/say", {"key": "k3", "message": "x"}, start=lambda f: f())
    assert m.SIDES.get("k3")["state"] == "failed" and "did not open a thread" in m.SIDES.get("k3")["error"]
    m.SIDE_SENT[:] = [time.time()] * m.SIDE_RATE
    assert m._sides_post("/sides/say", {"key": "k4", "message": "x"}, start=lambda f: f())[0] == 429


def test_a_turn_that_waited_in_line_still_lands_in_its_side(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    calls = []
    _turns(m, monkeypatch, calls, status=202)
    m._sides_post("/sides/say", {**ITEM, "message": "x"}, start=lambda f: f())
    assert m.SIDES.get(ITEM["key"])["state"] == "waiting"
    pending = calls[0]["message"]
    _turns(m, monkeypatch, calls, reply="later answer")
    m._turn(pending, thread=SIDE, new=False, source="queue")           # the box's queue drains it
    assert m.SIDES.get(ITEM["key"])["state"] == "ready" and m.SIDES.get(ITEM["key"])["turns"][-1]["text"] == "later answer"


def test_telegram_line_only_when_away_and_title_only(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    sent = []

    class TG:
        def owner(self):
            return 42
    monkeypatch.setattr(m, "TG", TG())
    monkeypatch.setattr(m, "_notify", lambda text: (sent.append(text), (200, {"ok": True}))[1])
    calls = []
    _turns(m, monkeypatch, calls, reply="SECRET answer text")
    m._sides_post("/sides/say", {**ITEM, "message": "x"}, start=lambda f: f())
    assert sent == ["Note ready: Fix the door"]                                  # nobody looked: one line, no content
    m.SIDES.seen()
    m._sides_post("/sides/say", {**ITEM, "message": "y"}, start=lambda f: f())
    assert len(sent) == 1                                                         # the owner is looking: no phone line
    monkeypatch.setattr(m, "TG", None)
    m.SIDES.seen(time.time() - 3600)
    m._sides_post("/sides/say", {**ITEM, "message": "z"}, start=lambda f: f())
    assert len(sent) == 1                                                         # not paired: nothing


def test_reading_doors_over_http(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    calls = []
    _turns(m, monkeypatch, calls)
    m._sides_post("/sides/say", {**ITEM, "message": "x"}, start=lambda f: f())
    srv, base = _serve(m)
    try:
        st, d = _call(f"{base}/sides?page=court-tasks")
        assert st == 200 and d["ready"] == 1 and d["sides"][0]["key"] == ITEM["key"] and d["sides"][0]["cards"] == []
        assert "pending" not in d["sides"][0]
        assert _call(f"{base}/sides/count")[1]["items"][0]["title"] == "Fix the door"
        assert _call(f"{base}/sides/read", {"key": ITEM["key"]})[1]["ready"] == 0
        assert _call(f"{base}/sides/seen", {})[0] == 200 and not m.SIDES.away()
        assert _call(f"{base}/sides/nope", {})[0] == 404
        st, d = _call(f"{base}/sides?keys=nope")
        assert d["sides"] == []
    finally:
        srv.shutdown()


def test_inline_script_served_and_never_writes_html(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    import urllib.request
    srv, base = _serve(m)
    try:
        with urllib.request.urlopen(f"{base}/inline.js", timeout=10) as r:
            body = r.read().decode()
            assert r.headers["Content-Type"].startswith("text/javascript") and r.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        srv.shutdown()
    assert "window.ccInline" in body and "/sides/say" in body and "/sides/seen" in body
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert bad not in body, bad


def test_page_folder_is_on_the_console_origin_files_raw_stays_sandboxed(monkeypatch, tmp_path):
    m, _ = _sides_bridge(monkeypatch, tmp_path)
    out = tmp_path / "out"
    (out / "court" / "tasks").mkdir(parents=True, exist_ok=True)
    (out / "court" / "tasks" / "index.html").write_text("<p>tasks</p>")
    (out / "court" / "tasks" / "other.html").write_text("<p>x</p>")
    (out / "court" / "index.html").write_text("<p>court</p>")
    import cc_extras
    m.PAGES = cc_extras.Pages(out)
    import urllib.request
    import urllib.error

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)
    srv, base = _serve(m)
    try:
        with urllib.request.urlopen(f"{base}/page/court/tasks/", timeout=10) as r:
            assert r.read() == b"<p>tasks</p>" and "sandbox" not in r.headers["Content-Security-Policy"]
            assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
        with urllib.request.urlopen(f"{base}/page/court/tasks/other.html", timeout=10) as r:
            assert "sandbox" in r.headers["Content-Security-Policy"]            # a sibling stays an opaque origin
        try:
            op.open(f"{base}/page/court/tasks", timeout=10)
            raise AssertionError("expected a redirect")
        except urllib.error.HTTPError as e:
            assert e.code == 301 and e.headers["Location"].endswith("/page/court/tasks/")
        for bad in ("/page/court/../court/tasks/", "/page/court/Tasks/", "/page/court/tasks/x/y.html", "/page/court/nope/"):
            try:
                urllib.request.urlopen(f"{base}{bad}", timeout=10)
                raise AssertionError(bad)
            except urllib.error.HTTPError as e:
                assert e.code in (400, 404), bad
    finally:
        srv.shutdown()
