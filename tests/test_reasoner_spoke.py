"""Reasoner spoke (api/providers.py: spoke_up, ollama_url): the box's local inference goes to
the owner's own machine while it answers, back to the box's Ollama when it does not.
No network: the probe is injected.

Run from repo root:
    pytest tests/test_reasoner_spoke.py -v
"""
from __future__ import annotations

import importlib
import os


def _providers(monkeypatch, tmp_path, spoke: str | None):
    monkeypatch.setenv("SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setenv("OLLAMA_URL", "http://ollama:11434")
    if spoke is None:
        monkeypatch.delenv("OLLAMA_SPOKE_URL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_SPOKE_URL", spoke)
    monkeypatch.setenv("OLLAMA_SPOKE_PROBE_SECONDS", "30")
    from api import providers as p
    return importlib.reload(p)


def test_no_spoke_means_the_box(monkeypatch, tmp_path):
    p = _providers(monkeypatch, tmp_path, None)
    assert p.spoke_up(probe=lambda: True) is False
    assert p.ollama_url() == "http://ollama:11434"


def test_spoke_answering_wins_and_is_cached(monkeypatch, tmp_path):
    p = _providers(monkeypatch, tmp_path, "http://100.1.2.3:11434/")
    calls = []
    probe = lambda: calls.append(1) or True
    assert p.spoke_up(now=1000.0, probe=probe) is True
    assert p.spoke_up(now=1010.0, probe=probe) is True      # within the window: no second probe
    assert len(calls) == 1
    assert p.OLLAMA_SPOKE_URL == "http://100.1.2.3:11434"    # trailing slash dropped


def test_spoke_asleep_falls_back_and_recovers(monkeypatch, tmp_path):
    p = _providers(monkeypatch, tmp_path, "http://100.1.2.3:11434")
    def down():
        raise ConnectionError("asleep")
    import time
    t0 = time.time()
    assert p.spoke_up(now=t0, probe=down) is False
    assert p.ollama_url() == "http://ollama:11434"                 # cached: the box, no probe
    assert p.spoke_up(now=t0 + 100, probe=lambda: True) is True   # window passed: probed, back
