"""GET /cc/systems/done: what each system already finished (SYSTEMS-PAGES-1, 2026-11-27)."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
sys.path.insert(0, str(ROOT / "tests"))
import cc_systems_done as d  # noqa: E402
from test_cc_systems import _bridge, _call  # noqa: E402

TH = "0cfff3e2-0397-453b-82ad-38476d33a166"
DOC = {"built": "2026-11-27T15:00:00Z", "days": 14, "counts": {"hbar.music": 5, "world": 1},
       "systems": {"hbar.music": [{"ts": f"2026-11-2{i}T10:00:00Z", "what": f"take {i}", "state": "pushed", "job": "MIX-2",
                                   "thread": TH if i == 5 else "manual", "link": "out/x/REPORT.md", "repo": "world"} for i in range(1, 6)],
                   "world": [{"ts": "2026-11-27T09:00:00Z", "what": "", "state": "pushed"}]}}


def test_view_counts_and_rows():
    st, b = d.view(DOC)
    assert st == 200 and b["counts"] == {"hbar.music": 5, "world": 1} and "rows" not in b
    st, b = d.view(DOC, "hbar.music")
    assert st == 200 and b["count"] == 5 and [r["what"] for r in b["rows"]] == ["take 5", "take 4", "take 3"]
    assert b["rows"][0]["thread"] == TH and b["rows"][1]["thread"] == ""     # "manual" is not a thread
    assert len(d.view(DOC, "hbar.music", "60")[1]["rows"]) == 5
    assert len(d.view(DOC, "hbar.music", "x")[1]["rows"]) == 3
    assert len(d.view(DOC, "hbar.music", 0)[1]["rows"]) == 1
    assert d.view(DOC, "world")[1]["rows"] == []                              # a row with no words is dropped
    assert d.view(DOC, "../etc")[0] == 400
    assert d.view(None, "hbar.music") == (200, {"ok": True, "built": None, "days": None, "system": "hbar.music", "count": 0, "rows": []})


def test_odd_state_reads_as_pushed():
    doc = {"systems": {"a": [{"ts": "2026-11-27", "what": "x", "state": "<b>"}]}}
    assert d.view(doc, "a")[1]["rows"][0]["state"] == "pushed"


def test_route_reads_the_file(monkeypatch, tmp_path):
    f = tmp_path / "systems-done.json"
    f.write_text(json.dumps(DOC))
    monkeypatch.setenv("CC_SYSTEMS_DONE", str(f))
    m, srv, base, made = _bridge(monkeypatch, tmp_path)
    try:
        st, b = _call(base + "/systems/done?system=hbar.music&n=2")
        assert st == 200 and b["count"] == 5 and len(b["rows"]) == 2
        st, b = _call(base + "/systems/done")
        assert st == 200 and b["counts"]["hbar.music"] == 5
        f.unlink()
        st, b = _call(base + "/systems/done?system=hbar.music")
        assert st == 200 and b["rows"] == []
    finally:
        srv.shutdown()


def test_route_needs_the_operator(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_SYSTEMS_DONE", str(tmp_path / "none.json"))
    m, srv, base, made = _bridge(monkeypatch, tmp_path, token="tok")
    try:
        assert _call(base + "/systems/done")[0] == 403
        assert _call(base + "/systems/done", headers={"X-CC-Operator": "tok"})[0] == 200
    finally:
        srv.shutdown()
