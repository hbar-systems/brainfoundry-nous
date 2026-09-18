"""CC tab (0.11.0): opt-in built-in tab gated by BRAIN_CC_ENABLED.

Pure-Python; no Postgres, no model. Run from repo root:
    pytest tests/test_cc_tab.py -v
"""
from __future__ import annotations

import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_apps(monkeypatch, value: str | None):
    if value is None:
        monkeypatch.delenv("BRAIN_CC_ENABLED", raising=False)
    else:
        monkeypatch.setenv("BRAIN_CC_ENABLED", value)
    import api.apps as apps  # noqa: E402
    return importlib.reload(apps)


def test_cc_tab_absent_by_default(monkeypatch):
    apps = _load_apps(monkeypatch, None)
    ids = [t["id"] for t in apps.BUILTIN_TABS]
    assert "_cc" not in ids
    assert apps.CC_ENABLED is False
    # The route stays reserved so an installed app cannot squat on it.
    assert "/cc" in apps.RESERVED_ROUTES


def test_cc_tab_first_when_enabled(monkeypatch):
    apps = _load_apps(monkeypatch, "true")
    assert apps.CC_ENABLED is True
    tabs = sorted(apps.BUILTIN_TABS, key=lambda t: (t.get("order", 100), t["label"]))
    assert tabs[0]["id"] == "_cc"
    assert tabs[0]["label"] == "CC"
    assert tabs[0]["route"] == "/"          # CC is the home screen (D54)
    assert tabs[1]["id"] == "_dashboard" and tabs[1]["route"] == "/dashboard"
    assert any(x["id"] == "_graph" and x["route"] == "/graph" for x in tabs)
    assert {"/cc", "/dashboard", "/"} <= apps.RESERVED_ROUTES


def test_cc_flag_values(monkeypatch):
    for v in ("1", "yes", "on", "TRUE"):
        assert _load_apps(monkeypatch, v).CC_ENABLED is True
    for v in ("", "0", "false", "no"):
        assert _load_apps(monkeypatch, v).CC_ENABLED is False
    # Leave the module in its default (off) state for other tests.
    _load_apps(monkeypatch, None)
