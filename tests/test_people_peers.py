"""People page (2026-10-17): introduce keeps the owner's name a peer discloses in /identity;
an unset placeholder or a name that is only the handle again is dropped."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import hbar_commands  # noqa: E402


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _introduce(monkeypatch, tmp_path, identity):
    import httpx

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Resp(identity)

    monkeypatch.setattr(hbar_commands, "_PEERS_PATH", tmp_path / "peers.json")
    monkeypatch.setattr(hbar_commands, "_validate_peer_url", lambda url: None)
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    asyncio.run(hbar_commands.handle_hbar_command(
        command="peers.introduce", payload={"endpoint": "https://anne.example"}, client_id="test"))
    return json.loads((tmp_path / "peers.json").read_text())[0]


def test_introduce_keeps_disclosed_name(monkeypatch, tmp_path):
    p = _introduce(monkeypatch, tmp_path, {"brain_id": "anne", "display_name": "Anne", "public_key": "k"})
    assert p["name"] == "Anne"
    assert p["public_key"] == "k"


def test_owner_name_wins_over_display_name(monkeypatch, tmp_path):
    p = _introduce(monkeypatch, tmp_path,
                   {"brain_id": "anne", "display_name": "Anne's brain", "owner_name": "Anne", "public_key": "k"})
    assert p["name"] == "Anne"


def test_placeholder_or_handle_is_not_a_name(monkeypatch, tmp_path):
    assert _introduce(monkeypatch, tmp_path, {"brain_id": "anne", "display_name": "${BRAIN_NAME}"})["name"] == ""
    (tmp_path / "peers.json").unlink()
    assert _introduce(monkeypatch, tmp_path, {"brain_id": "anne", "display_name": "anne"})["name"] == ""
    (tmp_path / "peers.json").unlink()
    assert _introduce(monkeypatch, tmp_path, {"brain_id": "anne"})["name"] == ""
