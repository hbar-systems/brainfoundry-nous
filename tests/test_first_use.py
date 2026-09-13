"""Tests for api/onboarding/first_use.py (unreleased 0.10.0). Created 2026-09-13."""
from api.onboarding import first_use as fu


APPS = [{"id": "poker-journal", "name": "Poker", "enabled": True},
        {"id": "daybook", "name": "Daybook", "enabled": True, "description": "twice-daily prompt"},
        {"id": "off", "name": "Off", "enabled": False}]


def test_pick_first_app_prefers_daybook_then_first_enabled():
    assert fu.pick_first_app(APPS)["id"] == "daybook"
    assert fu.pick_first_app(APPS[:1])["id"] == "poker-journal"
    assert fu.pick_first_app([{"id": "off", "enabled": False}]) is None
    assert fu.pick_first_app([]) is None


def test_fresh_brain_state():
    s = fu.build_state(has_key=False, doc_count=0, chunk_count=0, session_count=0, installed=APPS)
    assert s["fresh"] is True and s["complete"] is False
    keys = [x["key"] for x in s["steps"]]
    assert keys == ["key", "files", "app"]
    assert s["steps"][1]["label"] == "Drop ten files (0 of 10)"
    assert s["steps"][2]["label"] == "Open Daybook" and s["steps"][2]["href"] == "/apps/daybook"
    assert s["first_app"]["route"] == "/apps/daybook"


def test_progress_and_completion():
    s = fu.build_state(has_key=True, doc_count=4, chunk_count=40, session_count=0, installed=APPS)
    assert s["steps"][0]["done"] is True
    assert s["steps"][1]["done"] is False and s["steps"][1]["progress"] == {"done": 4, "target": 10, "chunks": 40}
    assert s["fresh"] is False
    s2 = fu.build_state(has_key=True, doc_count=12, chunk_count=300, session_count=3, installed=APPS)
    assert s2["complete"] is True
    assert s2["steps"][1]["label"] == "Drop ten files (10 of 10)"


def test_no_apps_installed_points_to_apps_page():
    s = fu.build_state(has_key=True, doc_count=10, chunk_count=1, session_count=0, installed=[])
    app_step = s["steps"][2]
    assert app_step["done"] is True and app_step["href"] == "/apps"   # nothing to open; not a blocker
    assert s["first_app"] is None
