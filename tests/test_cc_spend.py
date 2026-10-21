"""Newcomer mode and the spend meter (scripts/cc/cc_spend.py, cc_layout.Store.mode, the bridge's
/layout/mode and job-end lines). Created 2026-10-17. No network, no reasoner.

    pytest tests/test_cc_spend.py -v
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
import cc_extras  # noqa: E402
import cc_layout as L  # noqa: E402
import cc_spend as S  # noqa: E402

from tests.test_cc_bridge import _load  # noqa: E402

NOW = 1_760_700_000.0   # a fixed moment; days are counted from it


def test_append_and_totals_by_window(tmp_path):
    led = S.Ledger(tmp_path)
    led.append("turn", "Anthropic", eur=1.0, tokens=100, minutes=0.5, t=NOW)
    led.append("job: build", "this server", minutes=3, t=NOW - 3 * 86400)       # this week, not today
    led.append("agent run", "Anthropic", eur=4.0, t=NOW - 20 * 86400)           # this month only
    led.append("old", "Anthropic", eur=100.0, t=NOW - 40 * 86400)               # outside every window
    tot = led.totals(NOW)
    assert tot["today"]["eur"] == 1.0 and tot["today"]["count"] == 1
    assert tot["week"]["eur"] == 1.0 and tot["week"]["minutes"] == 3.5 and tot["week"]["count"] == 2
    assert tot["month"]["eur"] == 5.0 and tot["month"]["tokens"] == 100 and tot["month"]["count"] == 3


def test_lines_are_the_ledger_shape_and_append_only(tmp_path):
    led = S.Ledger(tmp_path)
    led.append("turn", "Anthropic", usd=1.0, tokens=10, t=NOW, estimate=True)
    led.append("job: x", "this server", minutes=1, t=NOW)
    rows = [json.loads(l) for l in (tmp_path / "spend.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert set(rows[1]) == {"date", "what", "provider", "eur", "tokens", "minutes"}
    assert rows[0]["eur"] == round(S.EUR_PER_USD, 4) and rows[0]["estimate"] is True
    assert rows[1]["eur"] is None   # a job knows its minutes, not its price
    assert led.totals(NOW)["today"]["estimate"] is True


@pytest.mark.parametrize("kw", [{"eur": -1}, {"tokens": "many"}, {"minutes": True}, {"usd": float("nan")}])
def test_bad_numbers_are_refused(tmp_path, kw):
    with pytest.raises(ValueError):
        S.Ledger(tmp_path).append("x", "y", **kw)


def test_what_and_provider_required(tmp_path):
    with pytest.raises(ValueError):
        S.Ledger(tmp_path).append("", "Anthropic")


def test_torn_line_is_skipped(tmp_path):
    led = S.Ledger(tmp_path)
    led.append("turn", "Anthropic", eur=2.0, t=NOW)
    with (tmp_path / "spend.jsonl").open("a") as f:
        f.write('{"date": "2026-10\n')
    assert led.totals(NOW)["today"]["eur"] == 2.0


def test_cap_and_over(tmp_path):
    led = S.Ledger(tmp_path)
    assert led.cap() is None and led.over_cap(NOW) is False
    led.append("turn", "Anthropic", eur=6.0, t=NOW - 10 * 86400)
    assert led.set_cap(5) == 5.0
    assert led.over_cap(NOW) is True and led.view(NOW)["over"] is True
    led.set_cap(10)
    assert led.over_cap(NOW) is False
    led.set_cap(None)
    assert led.cap() is None and led.over_cap(NOW) is False
    with pytest.raises(ValueError):
        led.set_cap(-3)


# ---- newcomer mode ----

def test_new_brain_starts_with_the_full_console_and_it_sticks(tmp_path):
    st = L.Store(tmp_path)
    assert st.mode() == "operator"
    st.set_mode("newcomer")   # the owner's own choice in Settings is kept
    assert st.mode() == "newcomer"


@pytest.mark.parametrize("sign", L.USED_SIGNS)
def test_used_brain_starts_as_operator(tmp_path, sign):
    (tmp_path / sign).write_text("{}")
    assert L.Store(tmp_path).mode() == "operator"


def test_brain_with_a_layout_starts_as_operator(tmp_path):
    st = L.Store(tmp_path)
    st.save({"theme": "black"})
    assert st.mode() == "operator"


def test_set_mode_and_save_keeps_it(tmp_path):
    st = L.Store(tmp_path)
    assert st.mode() == "operator"
    assert st.set_mode("newcomer") == "newcomer"
    assert st.set_mode("operator") == "operator"
    st.save({"theme": "light"})
    assert st.mode() == "operator"
    with pytest.raises(L.LayoutError):
        st.set_mode("admin")


def test_tiers_do_not_overlap():
    seen = [t for tier in L.TIERS.values() for t in tier]
    assert len(seen) == len(set(seen))
    assert {"_chat", "_knowledge", "_files", "_guide", "_settings", "_apps"} == set(L.TIERS["standard"])


def test_bridge_mode_route(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    st, d = m._layout_api("GET", "/layout/mode", None, {})
    assert st == 200 and d["mode"] in L.MODES and d["tiers"] == L.TIERS
    st, d = m._layout_api("POST", "/layout/mode", {"mode": "newcomer"}, {})
    assert st == 200 and d["mode"] == "newcomer"
    st, d = m._layout_api("POST", "/layout/mode", {"mode": "root"}, {})
    assert st == 400


def test_bridge_job_end_writes_minutes(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, with_key=False)
    m._job_spent({"id": "J1", "title": "agent run", "started": 1000, "ended": 1120})
    m._job_spent({"id": "J2", "title": "still running", "started": 1000, "ended": None})
    rows = [json.loads(l) for l in m.SPEND.path.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["what"] == "job: agent run" and rows[0]["minutes"] == 2.0


def test_jobs_call_on_end(tmp_path):
    ended = []
    jobs = cc_extras.Jobs(tmp_path, lambda: None, on_end=ended.append)
    rec = jobs.start("true", None, "quick")
    for _ in range(50):
        if ended:
            break
        time.sleep(0.05)
    assert ended and ended[0]["id"] == rec["id"] and ended[0]["rc"] == 0
