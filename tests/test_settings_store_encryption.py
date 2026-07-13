"""Secrets-at-rest guards for the runtime settings sidecar (v0.9.2).

The sidecar (api/settings_store.py) stores operator-entered secrets: model
provider API keys, the IMAP app password, Google OAuth client/tokens, the
Telegram token. THREAT_MODEL.md item 7 flagged the previous plaintext-on-disk
form. These tests pin the encrypted-at-rest behaviour:

  - round-trip: values written while BRAIN_IDENTITY_SECRET is set land on
    disk as a Fernet token (no plaintext secret bytes), file mode 600, and
    read back intact;
  - migrate-on-read: a legacy plaintext settings.json is parsed once and
    immediately re-written encrypted;
  - rotated secret: an encrypted sidecar under a different secret reads as
    empty (fail closed), never crashes;
  - no-secret fallback: with BRAIN_IDENTITY_SECRET unset (dev-only path)
    the store still round-trips, in plaintext.
"""
import json
import stat

import pytest

from api import settings_store

SECRET = "test-identity-secret-for-settings-store"
IMAP_PASSWORD = "imap-app-password-hunter2"
API_KEY = "sk-ant-api03-FAKEKEYFORTESTSONLY123456"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings_store, "_WARNED_DECRYPT_FAILURE", False)
    monkeypatch.setenv("BRAIN_IDENTITY_SECRET", SECRET)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return settings_store


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_round_trip_is_encrypted_on_disk(store):
    store.set_key("anthropic", API_KEY)
    raw = store.SETTINGS_PATH.read_bytes()
    assert API_KEY.encode() not in raw
    assert not raw.lstrip().startswith(b"{")
    assert store._load()["keys"]["anthropic"] == API_KEY


def test_sidecar_file_mode_600(store):
    store.set_key("anthropic", API_KEY)
    assert _mode(store.SETTINGS_PATH) == 0o600


def test_imap_password_round_trip_encrypted(store):
    store.set_email_account("imap.example.com", 993, "alice@example.com",
                            IMAP_PASSWORD)
    raw = store.SETTINGS_PATH.read_bytes()
    assert IMAP_PASSWORD.encode() not in raw
    acct = store.get_email_account()
    assert acct["imap_password"] == IMAP_PASSWORD
    assert acct["imap_host"] == "imap.example.com"


def test_legacy_plaintext_migrates_on_read(store):
    legacy = {"keys": {"anthropic": API_KEY},
              "email_account": {"imap_host": "imap.example.com",
                                "imap_port": 993,
                                "imap_user": "alice@example.com",
                                "imap_ssl": True,
                                "imap_password": IMAP_PASSWORD}}
    store.SETTINGS_PATH.write_text(json.dumps(legacy))

    # First read returns the legacy data intact...
    assert store.get_email_account()["imap_password"] == IMAP_PASSWORD

    # ...and the plaintext copy no longer exists on disk.
    raw = store.SETTINGS_PATH.read_bytes()
    assert API_KEY.encode() not in raw
    assert IMAP_PASSWORD.encode() not in raw
    assert not raw.lstrip().startswith(b"{")
    assert _mode(store.SETTINGS_PATH) == 0o600

    # And it still decrypts to the same data.
    assert store._load()["keys"]["anthropic"] == API_KEY


def test_rotated_secret_reads_empty_not_crash(store, monkeypatch, capsys):
    store.set_key("anthropic", API_KEY)
    monkeypatch.setenv("BRAIN_IDENTITY_SECRET", "a-different-secret-entirely")
    assert store._load() == {}
    # The fail-closed read is announced (once per process, not per read).
    assert "WARNING" in capsys.readouterr().out
    store._load()
    assert "WARNING" not in capsys.readouterr().out


def test_no_secret_dev_fallback_is_plaintext(store, monkeypatch):
    monkeypatch.delenv("BRAIN_IDENTITY_SECRET", raising=False)
    store.set_calendar_ics("https://calendar.example.com/feed.ics")
    raw = store.SETTINGS_PATH.read_bytes()
    assert raw.lstrip().startswith(b"{")
    assert store.get_calendar_ics() == "https://calendar.example.com/feed.ics"
    assert _mode(store.SETTINGS_PATH) == 0o600
