"""The technical surface (api/system_status.py): thresholds and warning lines. Pure, no
docker, no database.

Run from repo root:
    pytest tests/test_system_status.py -v
"""
from __future__ import annotations

from api import system_status as s


def test_level_thresholds():
    assert s.level(50, 80, 90) == "ok" and s.level(85, 80, 90) == "warn" and s.level(95, 80, 90) == "alert"
    assert s.level(20, 15, 7, lower_is_worse=True) == "ok"
    assert s.level(10, 15, 7, lower_is_worse=True) == "warn"
    assert s.level(3, 15, 7, lower_is_worse=True) == "alert"


def test_warnings_name_each_crossed_threshold():
    rep = {"host": {"disk": {"level": "warn", "pct": 85.0, "free_gb": 12.0},
                    "memory": {"level": "ok"}, "load": {"level": "alert", "five": 9.0, "cores": 4}},
           "docker": {"not_running": ["brain-ui-1"], "reclaimable_gb": 12.5},
           "backups": {"level": "warn", "count": 3, "age_days": 3.0},
           "database": {"level": "ok"}}
    w = s.warnings(rep)
    assert w[0].startswith("disk 85.0%") and any("load 9.0" in x for x in w)
    assert any("not running: brain-ui-1" in x for x in w) and any("12.5 GB reclaimable" in x for x in w)
    assert any("last backup 3.0 days ago" in x for x in w) and len(w) == 5
    assert s.warnings({"host": {}, "docker": {}, "backups": {"level": "ok", "count": 1}, "database": {}}) == []


def test_size_parsing():
    assert s._to_gb("12.56GB") == 12.56 and abs(s._to_gb("500MB") - 0.5) < 1e-9 and s._to_gb("0B") == 0.0


def test_host_reads_this_machine(tmp_path):
    h = s.host(str(tmp_path))
    assert "disk" in h and 0 <= h["disk"]["pct"] <= 100 and h["disk"]["level"] in ("ok", "warn", "alert")
