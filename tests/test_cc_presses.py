"""The console's private usage log (scripts/cc/cc_presses.py, the bridge's /presses routes,
ui/lib/presses.js). Created 2026-11-22 (USAGE-1). No network, no reasoner.

    pytest tests/test_cc_presses.py -v
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_presses as P  # noqa: E402

from tests.test_cc_bridge import _load  # noqa: E402

NOW = 1_800_000_000.0
DAY = 86400.0


def test_log_writes_time_thread_and_nothing_else(tmp_path):
    s = P.Store(tmp_path)
    assert s.log("nav", "/files", "", now=NOW) is True
    assert s.log("slash", "model", "3f2a-thread", now=NOW + 1) is True
    lines = [json.loads(x) for x in (tmp_path / P.EVENTS).read_text().splitlines()]
    assert [set(x) for x in lines] == [{"t", "ts", "kind", "name", "thread"}] * 2
    assert lines[1] == {"t": "2027-01-15T08:00:01Z", "ts": NOW + 1, "kind": "slash", "name": "model", "thread": "3f2a-thread"}
    assert stat.S_IMODE((tmp_path / P.EVENTS).stat().st_mode) == 0o600


@pytest.mark.parametrize("kind,name,thread", [
    ("click", "/files", ""),                       # not a kind
    ("nav", "/files?path=/home/me/secret.txt", ""),  # a query would carry a file's name
    ("slash", "model opus", ""),                   # an argument
    ("choice", "Yes, send the email to Anna", ""),  # a choice's words
    ("pane", "", ""),
    ("pane", "/" + "a" * 90, ""),
    ("nav", "/Files", ""),
    ("nav", ["/files"], ""),
    ("nav", "/files", "a thread with spaces"),
    ("nav", "/files", {"id": 1}),
])
def test_content_shaped_events_are_refused(tmp_path, kind, name, thread):
    s = P.Store(tmp_path)
    with pytest.raises(P.UsageError):
        s.log(kind, name, thread, now=NOW)
    assert not (tmp_path / P.EVENTS).exists()


def test_off_switch_writes_nothing_and_survives_a_new_store(tmp_path):
    s = P.Store(tmp_path)
    assert s.on() is True                      # on until the owner says otherwise
    s.log("nav", "/tasks", now=NOW)
    s.set_on(False)
    assert s.log("nav", "/tasks", now=NOW) is False
    assert P.Store(tmp_path).on() is False
    assert len((tmp_path / P.EVENTS).read_text().splitlines()) == 1   # off keeps what was there
    s.set_on(True)
    assert s.log("nav", "/tasks", now=NOW) is True
    with pytest.raises(P.UsageError):
        s.set_on("yes")


def test_unreadable_switch_reads_as_off(tmp_path):
    (tmp_path / P.SWITCH).write_text("{not json")
    s = P.Store(tmp_path)
    assert s.on() is False and s.log("nav", "/tasks", now=NOW) is False


def test_counts_for_7_and_30_days(tmp_path):
    s = P.Store(tmp_path)
    for age, kind, name, th in [(0.5, "nav", "/files", "a"), (3, "nav", "/files", "b"), (10, "nav", "/files", "a"),
                                (40, "nav", "/files", "c"), (2, "slash", "new", "a"), (29, "pane", "/graph", "d"),
                                (31, "choice", "reply-1", "e")]:
        s.log(kind, name, th, now=NOW - age * DAY)
    v = s.view(now=NOW)
    rows = {(r["kind"], r["name"]): r for r in v["controls"]}
    assert (rows[("nav", "/files")]["d7"], rows[("nav", "/files")]["d30"], rows[("nav", "/files")]["all"]) == (2, 3, 4)
    assert (rows[("slash", "new")]["d7"], rows[("slash", "new")]["d30"]) == (1, 1)
    assert (rows[("pane", "/graph")]["d7"], rows[("pane", "/graph")]["d30"]) == (0, 1)
    assert (rows[("choice", "reply-1")]["d7"], rows[("choice", "reply-1")]["d30"]) == (0, 0)
    assert v["controls"][0]["name"] == "/files"          # sorted by the 30-day count
    assert (v["d7"], v["d30"], v["events"]) == (3, 5, 7)
    assert (v["threads7"], v["threads30"]) == (2, 3)
    assert v["on"] is True and v["what"] == P.WHAT and v["file"].endswith(P.EVENTS)


def test_clear_deletes_the_file(tmp_path):
    s = P.Store(tmp_path)
    s.log("nav", "/files", now=NOW); s.log("nav", "/tasks", now=NOW)
    assert s.clear() == 2
    assert not (tmp_path / P.EVENTS).exists()
    assert s.view(now=NOW)["events"] == 0 and s.clear() == 0


def test_trim_keeps_the_last_90_days(tmp_path, monkeypatch):
    s = P.Store(tmp_path)
    s.log("nav", "/old", now=NOW - 200 * DAY)
    s.log("nav", "/recent", now=NOW - 5 * DAY)
    monkeypatch.setattr(P, "MAX_BYTES", 10)
    s.log("nav", "/now", now=NOW)
    assert [r["name"] for r in s.view(now=NOW)["controls"]] == ["/now", "/recent"]


def test_a_damaged_line_does_not_break_the_view(tmp_path):
    s = P.Store(tmp_path)
    s.log("nav", "/files", now=NOW)
    with open(tmp_path / P.EVENTS, "a") as f:
        f.write("garbage\n{\"kind\": \"other\"}\n")
    assert s.view(now=NOW)["events"] == 1


def test_no_outside_service():
    """The log stays on the box: the module opens no connection and the page posts only to the bridge."""
    src = (ROOT / "scripts" / "cc" / "cc_presses.py").read_text()
    for word in ("urllib", "requests", "socket", "http.client", "subprocess", "httpx"):
        assert not re.search(r"^\s*(import|from)\s+" + re.escape(word), src, re.M), word
    js = (ROOT / "ui" / "lib" / "presses.js").read_text()
    assert re.findall(r"fetch\(\s*'([^']+)'", js) == ["/cc/presses"]
    assert "http://" not in js and "https://" not in js and "sendBeacon" not in js
    page = (ROOT / "ui" / "pages" / "usage.js").read_text()
    assert set(re.findall(r"'(/cc/[^']+)'", page)) == {"/cc/presses", "/cc/presses/switch", "/cc/presses/clear"}
    assert "http://" not in page and "https://" not in page


# ---- the bridge routes ----

def test_bridge_routes(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=True)
    assert m.PRESSES.events == tmp_path / ".cc-bridge" / "surface-events.jsonl"
    st, d = m._presses_api("GET", "/presses", None)
    assert st == 200 and d["on"] is True and d["events"] == 0
    assert m._presses_api("POST", "/presses", {"kind": "pane", "name": "/files", "thread": "t1"}) == (200, {"logged": True})
    st, d = m._presses_api("POST", "/presses", {"kind": "pane", "name": "/files?path=/x"})
    assert st == 400 and "name" in d["error"]
    assert m._presses_api("POST", "/presses", None)[0] == 404
    st, d = m._presses_api("POST", "/presses/switch", {"on": False})
    assert st == 200 and d["on"] is False
    assert m._presses_api("POST", "/presses", {"kind": "pane", "name": "/files"}) == (200, {"logged": False})
    assert m._presses_api("POST", "/presses/switch", {"on": "no"})[0] == 400
    st, d = m._presses_api("POST", "/presses/clear", {})
    assert st == 200 and d["cleared"] == 1 and d["events"] == 0
    assert m._presses_api("POST", "/presses/elsewhere", {})[0] == 404
    assert m.PANE_ROUTES["/usage"] == "Usage"


def test_routes_sit_behind_the_operator_token():
    """/presses is not on either list of doors that open without the console's token."""
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    for ln in src.splitlines():
        if "_operator_ok()" in ln and "route not in (" in ln:
            assert "/presses" not in ln


# ---- the page glue under node (ui/lib/presses.js) ----

def _node_json(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_page_names_carry_no_content():
    out = _node_json(r"""
      const p = require('./presses.js')
      const known = [{ c: '/new' }, { c: '/model' }, { c: '/pane' }]
      console.log(JSON.stringify({
        files: p.routeName('/files?path=/home/me/secret.txt'),
        app: p.routeName('/apps/poker-journal/'),
        threads: p.routeName('#threads'),
        layout: p.routeName('/layout?step=surfaces'),
        abs: p.routeName('https://example.org/Some/Path?q=1'),
        bad: p.routeName('/a b'), empty: p.routeName(''), nul: p.routeName(null),
        model: p.slashName('/model opus-secret-arg', known),
        custom: p.slashName('/my-private-command do the thing', known),
        notslash: p.slashName('hello', known),
        c1: p.choiceName({ mode: 'reply', label: 'Send it to Anna', send: 'x' }, 0),
        c2: p.choiceName({ mode: 'agent', label: 'y' }, 2),
        c3: p.choiceName({ label: 'y' }),
        t1: p.threadName('3f2a:9'), t2: p.threadName('has space'),
      }))
    """)
    assert out == {"files": "/files", "app": "/apps/poker-journal", "threads": "#threads", "layout": "/layout",
                   "abs": "/some/path", "bad": None, "empty": None, "nul": None,
                   "model": "model", "custom": "other", "notslash": None,
                   "c1": "reply-1", "c2": "agent-3", "c3": "reply-0", "t1": "3f2a:9", "t2": ""}
    for name in ("files", "app", "threads", "layout", "abs", "model", "custom", "c1", "c2", "c3"):
        assert P.NAME_RE.match(out[name]), name       # what the page sends, the box accepts


def test_press_points_are_wired_and_disclosed():
    cc = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "press('slash', slashName(text, SLASH)" in cc
    assert "press('choice', choiceName(c, i)" in cc
    assert "press('pane', routeName(paneRoute)" in cc
    assert "press('nav', routeName(" in (ROOT / "ui" / "components" / "Nav.js").read_text()
    assert "press('surface', routeName(window.location.pathname))" in (ROOT / "ui" / "pages" / "_app.js").read_text()
    settings = (ROOT / "ui" / "pages" / "settings.js").read_text()
    assert "<UsageLogPanel />" in settings and "/cc/presses/switch" in settings
    guide = (ROOT / "ui" / "pages" / "guide.js").read_text()
    assert "What the console counts" in guide and "surface-events.jsonl" in guide
    doc = (ROOT / "docs" / "CC.md").read_text()
    assert "surface-events.jsonl" in doc and "no outside service" in doc
