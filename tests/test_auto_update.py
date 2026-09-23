"""Auto-update (api/settings_store: auto_update_due and the auto_update setting): the daily rule
and the setting. No network, no docker.

Run from repo root:
    pytest tests/test_auto_update.py -v
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest


def test_due_rule(monkeypatch, tmp_path):
    monkeypatch.setenv("SETTINGS_PATH", str(tmp_path / "settings.json"))
    from api import settings_store as s
    due = s.auto_update_due
    now = datetime(2026, 9, 23, 5, 0, 0)
    assert due({"enabled": True, "hour": 4, "last_run": None}, now, 3) is True
    assert due({"enabled": False, "hour": 4}, now, 3) is False            # off
    assert due({"enabled": True, "hour": 4}, now, 0) is False              # nothing to pull
    assert due({"enabled": True, "hour": 6}, now, 3) is False              # hour not reached
    assert due({"enabled": True, "hour": 4, "last_run": "2026-09-23T04:10:00Z"}, now, 3) is False   # ran today
    assert due({"enabled": True, "hour": 4, "last_run": "2026-09-22T04:10:00Z"}, now, 3) is True    # ran yesterday


def test_setting_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("SETTINGS_PATH", str(tmp_path / "settings.json"))
    import importlib
    from api import settings_store as s
    importlib.reload(s)
    assert s.get_auto_update() == {"enabled": False, "hour": 4, "last_run": None, "last_result": None}
    s.set_auto_update(enabled=True, hour=3)
    s.set_auto_update(last_run="2026-09-23T03:00:00Z", last_result="rc=0")
    assert s.get_auto_update() == {"enabled": True, "hour": 3, "last_run": "2026-09-23T03:00:00Z", "last_result": "rc=0"}
    with pytest.raises(ValueError):
        s.set_auto_update(hour=25)
