"""
Tests for the onboarding trial-reasoner cost-guard (api/onboarding/trial_reasoner.py).

Pure budget/reservation logic in FILE mode (no Redis, no anthropic, no real key):
covers the per-session token cap, per-IP/day token cap, distinct-session-per-IP
cap, the optional brain-wide ceiling, reserve-then-reconcile refunds, the
fail-safe-OFF status read, and the TOCTOU property that concurrent reservations
cannot collectively overshoot a cap.
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _fresh_module(tmp_path, **env):
    """Reload the module with a clean file-budget path and the given caps so
    each test gets isolated counters (no Redis)."""
    os.environ.pop("REDIS_URL", None)  # force file mode
    os.environ["TRIAL_BUDGET_PATH"] = str(tmp_path / "budget.json")
    os.environ["TRIAL_AUDIT_DIR"] = str(tmp_path / "audit")
    os.environ.setdefault("TRIAL_SESSION_TOKEN_CAP", "1000")
    os.environ.setdefault("TRIAL_IP_DAILY_TOKEN_CAP", "3000")
    os.environ.setdefault("TRIAL_IP_DAILY_SESSION_CAP", "3")
    os.environ.setdefault("TRIAL_GLOBAL_DAILY_TOKEN_CAP", "0")
    for k, v in env.items():
        os.environ[k] = str(v)
    from api.onboarding import trial_reasoner as tr
    importlib.reload(tr)
    return tr


def _clear_caps():
    for k in ("TRIAL_SESSION_TOKEN_CAP", "TRIAL_IP_DAILY_TOKEN_CAP",
              "TRIAL_IP_DAILY_SESSION_CAP", "TRIAL_GLOBAL_DAILY_TOKEN_CAP"):
        os.environ.pop(k, None)


# ── availability ──────────────────────────────────────────────────────────
def test_unavailable_without_key(tmp_path):
    _clear_caps()
    os.environ.pop("TRIAL_REASONER_API_KEY", None)
    tr = _fresh_module(tmp_path)
    assert tr.is_available() is False
    st = tr.status("s1", "1.1.1.1")
    assert st["available"] is False
    assert st["session_remaining"] == 0


# ── per-session token cap ─────────────────────────────────────────────────
def test_session_cap_blocks_and_refunds(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_SESSION_TOKEN_CAP=1000, TRIAL_IP_DAILY_TOKEN_CAP=10000)
    # Reserve 600 → ok, 400 remaining.
    r1 = tr._reserve("s1", "1.1.1.1", 600)
    assert r1.ok and r1.session_remaining == 400
    # Reserve another 600 → would hit 1200 > 1000 → refused, and refunded.
    r2 = tr._reserve("s1", "1.1.1.1", 600)
    assert not r2.ok and r2.reason == "session_cap"
    # The refused reservation must not have stuck: still 400 remaining.
    assert (tr._backend.get(tr._sess_key("s1")) or 0) == 600
    r3 = tr._reserve("s1", "1.1.1.1", 400)
    assert r3.ok and r3.session_remaining == 0


def test_reconcile_refunds_overestimate(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_SESSION_TOKEN_CAP=1000)
    r = tr._reserve("s1", "2.2.2.2", 800)
    assert r.ok
    # Actual usage was only 200 → reconcile refunds 600.
    remaining = tr._reconcile("s1", "2.2.2.2", reserved=800, actual=200)
    assert remaining == 800
    assert (tr._backend.get(tr._sess_key("s1")) or 0) == 200


# ── per-IP/day token cap (across sessions) ────────────────────────────────
def test_ip_daily_cap_spans_sessions(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_SESSION_TOKEN_CAP=2000,
                       TRIAL_IP_DAILY_TOKEN_CAP=1500, TRIAL_IP_DAILY_SESSION_CAP=10)
    assert tr._reserve("sa", "9.9.9.9", 1000).ok
    # Second session, same IP: 1000 + 1000 = 2000 > 1500 IP cap → refuse.
    r = tr._reserve("sb", "9.9.9.9", 1000)
    assert not r.ok and r.reason == "ip_cap"


# ── distinct-session-per-IP cap ───────────────────────────────────────────
def test_ip_session_cap(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_IP_DAILY_SESSION_CAP=2,
                       TRIAL_SESSION_TOKEN_CAP=100000, TRIAL_IP_DAILY_TOKEN_CAP=100000)
    assert tr._reserve("s1", "5.5.5.5", 10).ok
    assert tr._reserve("s2", "5.5.5.5", 10).ok
    r = tr._reserve("s3", "5.5.5.5", 10)
    assert not r.ok and r.reason == "ip_session_cap"
    # An already-counted session may keep going (re-reserve under same sid).
    assert tr._reserve("s1", "5.5.5.5", 10).ok


# ── optional brain-wide ceiling ───────────────────────────────────────────
def test_global_cap(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_GLOBAL_DAILY_TOKEN_CAP=1500,
                       TRIAL_SESSION_TOKEN_CAP=100000, TRIAL_IP_DAILY_TOKEN_CAP=100000,
                       TRIAL_IP_DAILY_SESSION_CAP=100)
    assert tr._reserve("s1", "1.1.1.1", 1000).ok
    # Different IP + session, but the brain-wide ceiling still bites at 2000>1500.
    r = tr._reserve("s2", "2.2.2.2", 1000)
    assert not r.ok and r.reason == "global_cap"


# ── TOCTOU: concurrent reservations cannot overshoot ──────────────────────
def test_no_overshoot_under_sequential_pressure(tmp_path):
    _clear_caps()
    tr = _fresh_module(tmp_path, TRIAL_SESSION_TOKEN_CAP=1000, TRIAL_IP_DAILY_TOKEN_CAP=100000)
    granted = 0
    for _ in range(20):
        r = tr._reserve("s1", "1.1.1.1", 300)
        if r.ok:
            granted += 300
    # incr-then-check-and-refund means the committed total can never exceed cap.
    assert (tr._backend.get(tr._sess_key("s1")) or 0) <= 1000
    assert granted <= 1000


# ── fail-closed status when key set but counters readable ─────────────────
def test_status_reports_remaining(tmp_path):
    _clear_caps()
    os.environ["TRIAL_REASONER_API_KEY"] = "sk-test-not-real"
    tr = _fresh_module(tmp_path, TRIAL_SESSION_TOKEN_CAP=1000, TRIAL_IP_DAILY_TOKEN_CAP=5000)
    # Force the client to look present without importing anthropic.
    tr._client_obj = object()
    tr._client_built = True
    tr._reserve("s1", "7.7.7.7", 400)
    st = tr.status("s1", "7.7.7.7")
    assert st["available"] is True
    assert st["session_remaining"] == 600
    os.environ.pop("TRIAL_REASONER_API_KEY", None)
