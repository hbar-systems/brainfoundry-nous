"""PANES-FOCUS-1 (2026-11-27): GET /cc/systems tiles carry `open_rows` {n, his} from the world's ops/systems/<id>/open.tsv,
read only, for the marks right of a pane's name on /systems (ui/lib/steer.js paneMarks).

Run from repo root:  pytest tests/test_cc_systems_open.py -q
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
def _cc_systems():
    import sys
    sys.path.insert(0, str(ROOT / "scripts" / "cc"))
    import cc_systems
    return cc_systems


def test_open_rows_counts_like_health_line(tmp_path):
    S = _cc_systems()
    d = tmp_path / "ops" / "systems" / "hbar.music"
    d.mkdir(parents=True)
    rows = [["rank", "kind", "id", "state", "when", "what", "placed", "link", "ask"],
            ["1", "task", "t1", "open", "", "say the dates", "", "", ""],
            ["2", "court", "c1", "decision", "", "public repos", "", "", ""],
            ["3", "next", "n1", "candidate", "", "a next row", "", "", ""],
            ["4", "next", "n2", "in court c1", "", "held by c1", "", "", ""],
            ["5", "task", "t2", "open, dead by the 2026-11-25 check", "", "old", "", "", ""],
            ["6", "next", "n3", "taken", "", "running", "", "", ""]]
    (d / "open.tsv").write_text("\n".join("\t".join(r) for r in rows) + "\n")
    assert S.open_rows(tmp_path, "hbar.music") == {"n": 5, "his": 2}
    assert S.open_rows(tmp_path, "hbar.none") is None                          # no file: no number
    assert S.open_rows(tmp_path, "../hbar.music") is None and S.open_rows(tmp_path, "a/b") is None
    assert S.open_rows(None, "hbar.music") is None
    (d / "open.tsv").write_text("\t".join(rows[0]) + "\n")
    import os
    os.utime(d / "open.tsv", (1, 1))                                           # the mtime moved: read again
    assert S.open_rows(tmp_path, "hbar.music") == {"n": 0, "his": 0}


def test_board_tiles_carry_open(tmp_path):
    S = _cc_systems()
    (tmp_path / "registry").mkdir()
    (tmp_path / "registry" / "systems.json").write_text(json.dumps({"systems": [
        {"id": "hbar.music", "status": "active", "description": "music"}, {"id": "hbar.art", "status": "active", "description": "art"}]}))
    d = tmp_path / "ops" / "systems" / "hbar.music"
    d.mkdir(parents=True)
    (d / "open.tsv").write_text("rank\tkind\tid\tstate\n1\tcourt\tc\tdecision\n2\tnext\tn\tcandidate\n")
    tiles = {t["id"]: t for t in S.board(tmp_path, [])["tiles"]}
    assert tiles["hbar.music"]["open_rows"] == {"n": 2, "his": 1}
    assert tiles["hbar.art"]["open_rows"] is None


def test_bridge_view_keeps_open_rows_beside_the_instrument_page(monkeypatch, tmp_path):
    """GET /cc/systems through the bridge: `open` (an instrument's page, set after the board) does not clobber the count."""
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    import test_cc_wall_depth as WD
    m, _ = WD._depth_bridge(monkeypatch, tmp_path, WD.HIST)
    world = pathlib.Path(m.WORLD_DIR)
    d = world / "ops" / "systems" / "hbar.film"
    d.mkdir(parents=True, exist_ok=True)
    (d / "open.tsv").write_text("rank\tkind\tid\tstate\n1\ttask\tt\topen\n2\tnext\tn\tcandidate\n3\tnext\tm\tin court x\n")
    f = {t["id"]: t for t in m._systems_view()["tiles"]}["hbar.film"]
    assert f["open_rows"] == {"n": 2, "his": 1}
    assert "open" in f and not isinstance(f["open"], dict)                     # WALL-3's field, untouched
