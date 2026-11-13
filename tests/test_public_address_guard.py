"""Public-only fetch guards (audit 2026-11-13): tailnet (100.64.0.0/10) and other non-global
ranges are refused by fetch_url and the calendar ICS check. No network: DNS is faked."""
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.integrations import calendar_ics  # noqa: E402
from api.tools import fetch_url  # noqa: E402

BLOCKED = ["100.64.0.1", "100.101.102.103", "100.127.255.254", "10.0.0.5", "127.0.0.1",
           "169.254.169.254", "192.0.2.1", "198.18.0.1", "::ffff:100.100.1.1", "::ffff:10.0.0.1",
           "fd7a:115c:a1e0::1", "::1"]
ALLOWED = ["93.184.215.14", "1.1.1.1", "2606:4700:4700::1111"]


def _resolve_to(monkeypatch, addr):
    fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(fam, 1, 6, "", (addr, 0))])


@pytest.mark.parametrize("addr", BLOCKED)
def test_non_global_refused(monkeypatch, addr):
    _resolve_to(monkeypatch, addr)
    assert fetch_url._is_public_address("x.example") is False
    assert calendar_ics._public("x.example") is False


@pytest.mark.parametrize("addr", ALLOWED)
def test_global_allowed(monkeypatch, addr):
    _resolve_to(monkeypatch, addr)
    assert fetch_url._is_public_address("x.example") is True
    assert calendar_ics._public("x.example") is True
