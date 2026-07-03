"""Release-prep security-hardening regression guards.

Covers three launch-blocker fixes:

  #2  Postgres password fail-closed — api/main.py refuses to start in a non-dev
      environment when the DB password is empty or the default "postgres".
  #3  Public daily cap default — api/kernel/rate_limiter.PublicRateLimiter now
      defaults PUBLIC_CHAT_DAILY_MAX to 2000 (safe non-zero ceiling), not 0.
  #4  X-Forwarded-For trust — api.main._public_client_ip only honours XFF when
      TRUST_PROXY_HEADERS is enabled; otherwise it uses the transport peer so a
      directly-reachable brain can't be spoofed.

Pure-Python; no Postgres, no model. The #2 guard fires at import time, so it is
exercised in a subprocess with a prod-like environment. Run from repo root:

    pytest tests/test_release_hardening.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── #3  PublicRateLimiter daily cap default ──────────────────────────────────

def test_public_daily_max_defaults_to_2000(monkeypatch):
    monkeypatch.delenv("PUBLIC_CHAT_DAILY_MAX", raising=False)
    from api.kernel.rate_limiter import PublicRateLimiter
    assert PublicRateLimiter().daily_max == 2000


def test_public_daily_max_respects_override(monkeypatch):
    monkeypatch.setenv("PUBLIC_CHAT_DAILY_MAX", "50")
    from api.kernel.rate_limiter import PublicRateLimiter
    assert PublicRateLimiter().daily_max == 50


def test_public_daily_max_zero_is_explicit_opt_out(monkeypatch):
    # 0 must still mean "unlimited" — an operator can deliberately opt out.
    monkeypatch.setenv("PUBLIC_CHAT_DAILY_MAX", "0")
    from api.kernel.rate_limiter import PublicRateLimiter
    assert PublicRateLimiter().daily_max == 0


# ── #4  _public_client_ip XFF trust flag ─────────────────────────────────────

class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    """Minimal stand-in for starlette Request: .headers.get + .client.host."""
    def __init__(self, xff=None, host="10.0.0.9"):
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}
        self.client = _FakeClient(host)


def test_xff_ignored_when_proxy_not_trusted(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)  # default = false
    from api.main import _public_client_ip
    req = _FakeRequest(xff="1.2.3.4", host="10.0.0.9")
    # Spoofed header must NOT win — the real transport peer is used.
    assert _public_client_ip(req) == "10.0.0.9"


def test_xff_last_hop_used_when_proxy_trusted(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    from api.main import _public_client_ip
    req = _FakeRequest(xff="1.2.3.4, 5.6.7.8", host="10.0.0.9")
    # Only the LAST hop (appended by the trusted proxy) is trusted.
    assert _public_client_ip(req) == "5.6.7.8"


def test_falls_back_to_peer_when_no_xff_even_if_trusted(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    from api.main import _public_client_ip
    req = _FakeRequest(xff=None, host="10.0.0.9")
    assert _public_client_ip(req) == "10.0.0.9"


# ── #2  Postgres password fail-closed (import-time guard) ─────────────────────

def _import_main(tmp_path, **env_overrides):
    """Import api.main in a subprocess with a prod-like env; return CompletedProcess.

    Baseline satisfies the earlier non-dev startup guards (identity secret, api
    key) so execution reaches the Postgres-password check, and points
    BRAIN_RUNTIME_DIR at a writable tmp dir so the persona-migration step (which
    runs after the guard) has somewhere to write off the container.
    """
    env = dict(os.environ)
    env.update({
        "BRAIN_ENV": "prod",
        "BRAIN_IDENTITY_SECRET": "a" * 48,
        "BRAIN_API_KEY": "b" * 48,
        "DEV_ENABLE_MEMORY_APPEND": "false",
        "BRAIN_RUNTIME_DIR": str(tmp_path),
    })
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import api.main"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )


def test_prod_refuses_default_postgres_password(tmp_path):
    proc = _import_main(
        tmp_path,
        DATABASE_URL="postgresql://postgres:postgres@postgres:5432/llm_db",
    )
    assert proc.returncode != 0, "import should have been refused"
    assert "Postgres password" in proc.stderr, proc.stderr[-2000:]


def test_prod_refuses_empty_postgres_password(tmp_path):
    proc = _import_main(
        tmp_path,
        DATABASE_URL="postgresql://postgres:@postgres:5432/llm_db",
    )
    assert proc.returncode != 0, "import should have been refused"
    assert "Postgres password" in proc.stderr, proc.stderr[-2000:]


def test_prod_accepts_strong_postgres_password(tmp_path):
    # A strong password must NOT trip the guard. (The import may still fail
    # downstream for unrelated env reasons in a bare subprocess, so we assert on
    # the specific message being absent rather than on a zero exit code.)
    proc = _import_main(
        tmp_path,
        DATABASE_URL="postgresql://postgres:9f3ac1e8b7d24f60a1c5@postgres:5432/llm_db",
    )
    assert "Postgres password" not in proc.stderr, proc.stderr[-2000:]


def test_dev_allows_default_postgres_password(tmp_path):
    # dev mode is explicitly exempt — the default must remain frictionless locally.
    proc = _import_main(
        tmp_path,
        BRAIN_ENV="dev",
        DATABASE_URL="postgresql://postgres:postgres@postgres:5432/llm_db",
    )
    assert "Postgres password" not in proc.stderr, proc.stderr[-2000:]
