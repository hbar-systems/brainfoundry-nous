"""DM receive bounds (audit 2026-11-13): size caps, a per-address window, daily counts.

No database: a fake connection counts rows in memory. Keys are fresh ED25519 pairs.
"""
import base64
import os
import sys
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api import federation_dm as dm  # noqa: E402


class FakeCursor:
    def __init__(self, rows):
        self.rows, self._one = rows, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        if sql.startswith("SELECT COUNT(*)"):
            if "from_pubkey" in sql:
                self._one = (sum(1 for r in self.rows if r["from_pubkey"] == params[0]),)
            else:
                self._one = (len(self.rows),)
        elif "INSERT INTO federation_inbox" in sql:
            self.rows.append({"from_pubkey": params[1], "message": params[2]})
            self._one = (len(self.rows),)

    def fetchone(self):
        return self._one


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return FakeCursor(self.rows)

    def commit(self):
        pass


@pytest.fixture
def client(monkeypatch):
    rows = []
    monkeypatch.setattr(dm, "_db", lambda: FakeConn(rows))
    monkeypatch.setattr(dm, "_receive_window", dm._AddrWindow())
    monkeypatch.setattr(dm, "_client_addr", lambda request: "203.0.113.9")
    app = FastAPI()
    app.include_router(dm.router)
    c = TestClient(app)
    c.rows = rows
    return c


def _dm(message="hello", key=None):
    key = key or Ed25519PrivateKey.generate()
    pub = base64.urlsafe_b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode().rstrip("=")
    payload = {"from_brain": "someone", "from_pubkey": pub, "message": message,
               "ts": int(time.time()), "nonce": uuid.uuid4().hex}
    sig = base64.urlsafe_b64encode(key.sign(dm._canonical(payload))).decode().rstrip("=")
    return {**payload, "signature": sig}


def test_ordinary_dm_received(client):
    r = client.post("/v1/federation/dm/receive", json=_dm())
    assert r.status_code == 200 and r.json()["received"] is True
    assert len(client.rows) == 1


def test_oversize_message_refused_before_storage(client):
    r = client.post("/v1/federation/dm/receive", json=_dm("x" * (dm.DM_MAX_MESSAGE_CHARS + 1)))
    assert r.status_code == 413 and client.rows == []


def test_one_address_is_bounded_whatever_its_keys(client, monkeypatch):
    monkeypatch.setenv("DM_RECEIVE_RATE_MAX", "3")
    codes = [client.post("/v1/federation/dm/receive", json=_dm()).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429] and len(client.rows) == 3


def test_daily_counts_per_sender_and_brain_wide(client, monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setenv("DM_PER_SENDER_DAILY_MAX", "2")
    codes = [client.post("/v1/federation/dm/receive", json=_dm(key=key)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    monkeypatch.setenv("DM_INBOX_DAILY_MAX", "3")
    assert client.post("/v1/federation/dm/receive", json=_dm()).status_code == 200
    assert client.post("/v1/federation/dm/receive", json=_dm()).status_code == 429
    assert len(client.rows) == 3
