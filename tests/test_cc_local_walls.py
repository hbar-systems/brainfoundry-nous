"""The bridge's tokenless local doors belong to this brain's own users (audit 2026-11-13).

Created 2026-11-13. Findings cc-bridge-direct-local-reads-cross-member and
cc-bridge-operator-token-fail-open: loopback carries no Unix identity, and on a
shared box every member's users reach every bridge port on 127.0.0.1. The bridge
now reads the caller's socket owner from /proc/net/tcp and admits a tokenless
call (job list and tail, task list, /notify) only from its own user or its hands
user; with no operator token set, page routes open only to its own user and the
console's proxy. Runs a real bridge on 127.0.0.1:0; the "other member" is played
by pretending the allowed uid set does not contain this test's uid.
"""
import os
import sys

import pytest

if not sys.platform.startswith("linux"):
    pytest.skip("socket owners come from /proc/net/tcp (Linux only)", allow_module_level=True)

from tests.test_cc_systems import _bridge, _call  # noqa: E402

OTHER = {os.getuid() + 4242}


def test_peer_uid_reads_the_client_row(tmp_path):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("cc_bridge_walls", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "cc" / "cc-bridge.py")
    t = tmp_path / "tcp"
    t.write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 0100007F:1E0A 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1001        0 1\n"
        "   1: 0100007F:1E0A 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1001        0 2\n"
        "   2: 0100007F:D431 0100007F:1E0A 01 00000000:00000000 00:00000000 00000000  1007        0 3\n")
    src = spec.loader.get_source(spec.name)
    ns = {}
    start = src.index("def _peer_uid(")
    end = src.index("\ndef _uid_of(")
    exec("from pathlib import Path\n" + src[start:end], ns)
    peer = ns["_peer_uid"]
    assert peer(0xD431, 0x1E0A, tables=(str(t),)) == 1007        # the client's socket, not the server's
    assert peer(0xD432, 0x1E0A, tables=(str(t),)) is None        # no such connection: refuse
    assert peer(0xD431, 0x1E0A, tables=(str(tmp_path / "missing"),)) is None


def test_own_user_keeps_the_local_doors(monkeypatch, tmp_path):
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="tok")
    try:
        assert _call(base + "/jobs")[0] == 200                       # cc-job list from cron, no token
        assert _call(base + "/tasks")[0] in (200, 502)               # passes the wall (api stubbed)
        assert _call(base + "/notify", {"text": "watch: red"})[0] == 409   # reached _notify: no owner pinned
        assert _call(base + "/state")[0] == 403                      # page routes still need the token
    finally:
        srv.shutdown()


def test_other_local_user_is_refused_without_a_token(monkeypatch, tmp_path):
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="tok")
    monkeypatch.setattr(m, "_local_uids", lambda: set(OTHER))
    try:
        for r in ("/jobs", "/jobs/J1?tail=100000", "/tasks"):
            assert _call(base + r)[0] == 403, r
        assert _call(base + "/notify", {"text": "spoofed"})[0] == 403
        # the reasoner's ask token and the console's operator token still open them
        assert _call(base + "/jobs", headers={"X-CC-Ask": m.ASK_TOKEN})[0] == 200
        assert _call(base + "/jobs", headers={"X-CC-Operator": "tok"})[0] == 200
    finally:
        srv.shutdown()


def test_no_operator_token_fails_closed_to_other_users(monkeypatch, tmp_path):
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="")
    try:
        assert _call(base + "/state")[0] == 200                      # the bridge's own user / unsplit owner
        monkeypatch.setattr(m, "_proxy_uids", lambda: set(OTHER))
        monkeypatch.setattr(m, "_local_uids", lambda: set(OTHER))
        assert _call(base + "/state")[0] == 403
        assert _call(base + "/restart/cancel", {})[0] == 403
        assert _call(base + "/permits/approve", {"id": "x"})[0] == 403
        assert _call(base + "/health")[0] == 200                     # health stays open
    finally:
        srv.shutdown()


def test_job_tail_is_capped(monkeypatch, tmp_path):
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="")
    seen = []
    monkeypatch.setattr(m.JOBS, "get", lambda jid, tail=4000: seen.append(tail) or {"id": jid})
    try:
        assert _call(base + "/jobs/J1?tail=99999999")[0] == 200
        assert _call(base + "/jobs/J1?tail=junk")[0] == 200
        assert seen == [m.JOB_TAIL_MAX, 4000]
    finally:
        srv.shutdown()


def test_local_uid_sets(monkeypatch, tmp_path):
    m, srv, base, _ = _bridge(monkeypatch, tmp_path, token="")
    srv.shutdown()
    assert os.getuid() in m._local_uids() and os.getuid() in m._proxy_uids()
    monkeypatch.setenv("CC_LOCAL_USERS", "0, no-such-user-xyz")
    assert 0 in m._local_uids()
    monkeypatch.setattr(m, "HANDS_USER", "no-such-user-xyz")
    assert m._local_uids() == {os.getuid(), 0}
