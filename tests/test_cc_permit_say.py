"""PERMIT-SAY-1 (2026-11-27): an Allow that fails says why in plain words, and an expired card comes back fresh.

hbar 2026-11-27: "That Allow did not reach the job: could not approve: PermitError - again issue!". Measured that
day: a card raised 12:37:23Z waited out its 15 minutes, the bridge told the job no and denied the permit at
12:52:24Z, and a later press met an already denied permit. These tests reproduce each way a press can miss
(expired, pressed twice, decided elsewhere, the asking job ended, the hook's own timeout) and pin that the gate
is not loosened: nothing expired, refused or orphaned is ever approved or run.

Run from repo root:
    pytest tests/test_cc_permit_say.py -v
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import timedelta

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
pytest.importorskip("permitd")

TTL = 2   # seconds: a card's whole life in these tests


@pytest.fixture(autouse=True)
def _no_posture(monkeypatch):
    monkeypatch.delenv("CC_POSTURE", raising=False)


def _load(monkeypatch, tmp_path, ttl=TTL):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.setenv("CC_BOX", "1")
    monkeypatch.setenv("CC_PERMIT_TTL", str(ttl))
    monkeypatch.delenv("ONE_SECRET", raising=False)
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    monkeypatch.delenv("CC_OPERATOR_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_say", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_say"] = mod
    spec.loader.exec_module(mod)
    mod.RUNS.clear(); mod.ASKS.clear(); mod.SETTLED.clear()
    return mod


def _run(m):
    cards = []
    run = m.Run(None, "do the thing"); m.RUNS[run.id] = run
    run.attach(lambda kind, payload: cards.append(payload) if kind == "ask" else None)
    return run, cards


def _ask(m, cards, command="touch /tmp/permit-say"):
    """The hook's call, in a thread: returns (thread, out) once the card is on the page."""
    out = {}
    n = len(cards)
    th = threading.Thread(target=lambda: out.setdefault("d", m._box_ask("Bash", {"command": command})))
    th.start()
    for _ in range(100):
        if len(cards) > n:
            break
        time.sleep(0.02)
    assert len(cards) > n, "no card was raised"
    return th, out, cards[-1]


def _no_class_names(payload):
    text = json.dumps(payload)
    assert "PermitError" not in text and "could not approve" not in text and "Exception" not in text


def _executed(m, pid):
    return m.GATE.get(pid).status == "executed"


# ---- 1. the case that hit him: the card expired, the bridge told the job no, then he pressed ----
def test_press_after_the_card_expired_says_so_and_runs_nothing(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    th.join(TTL + 3)
    # the job is told "expired, ask again", not "refused"
    msg = out["d"]["message"]
    assert out["d"]["behavior"] == "deny" and "expired" in msg and "fresh card" in msg and "not a refusal" in msg
    # his late press
    code, d = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    assert code == 409 and d["ok"] is False and d["reason"] == "already_denied"
    assert "expired" in d["error"] and "moved on" in d["error"] and "asks again" in d["error"]
    _no_class_names(d)
    assert m.GATE.get(card["id"]).status == "denied"        # never approved after the fact


def test_after_expiry_the_jobs_next_ask_raises_a_fresh_card(monkeypatch, tmp_path):
    """(b): one late press costs one more press, not a dead job: the same call again is a new permit and a new card,
    and that card's Allow works."""
    m = _load(monkeypatch, tmp_path)
    run, cards = _run(m)
    th, out, first = _ask(m, cards)
    th.join(TTL + 3)
    assert out["d"]["behavior"] == "deny"
    th2, out2, second = _ask(m, cards)
    assert second["id"] != first["id"] and second["summary"] == first["summary"]
    assert second["expires_at"] >= first["expires_at"]
    code, d = m._approve_permit(second["id"], m.GATE.get(second["id"]), "page")
    th2.join(3)
    assert code == 200 and d["ok"] is True and d["status"] == "allowed"
    assert out2["d"] == {"behavior": "allow"}


def test_reason_survives_a_bridge_restart_through_the_decision_log(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    th.join(TTL + 3)
    m.SETTLED.clear()                                         # a restart forgets the in-memory record
    assert "expired after" in m._permit_say("already_denied", card["id"])


def test_kernel_expiry_is_said_as_expired(monkeypatch, tmp_path):
    """A permit permitd itself expired (its clock ran past the ttl before anyone denied it)."""
    m = _load(monkeypatch, tmp_path, ttl=60)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    k = m.GATE.kernel
    real = k._now
    monkeypatch.setattr(k, "_now", lambda: real() + timedelta(seconds=120))
    code, d = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    assert code == 409 and d["reason"] == "already_expired" and "expired after 1 minute;" in d["error"]
    _no_class_names(d)
    assert m.GATE.get(card["id"]).status == "expired"
    m._box_settle(card["id"], "deny"); th.join(3)


# ---- 2. pressed twice (another tab, a double click) ----
def test_second_press_on_an_allowed_card_is_fine_not_an_error(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, ttl=30)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    code, d = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    th.join(3)
    assert code == 200 and d["status"] == "allowed" and out["d"] == {"behavior": "allow"}
    code2, d2 = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    assert code2 == 200 and d2["ok"] is True and d2["status"] == "already allowed" and "already allowed" in d2["said"]
    _no_class_names(d2)


def test_press_racing_another_press_reads_already_allowed(monkeypatch, tmp_path):
    """The other press won between our read and our approve: permitd raises already_approved; still fine."""
    m = _load(monkeypatch, tmp_path, ttl=30)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    stale = m.GATE.get(card["id"])                    # read while still proposed
    m.GATE.approve(card["id"])                        # the other tab's press lands first
    code, d = m._approve_permit(card["id"], stale, "page")
    assert code == 200 and d["status"] == "already allowed" and d["reason"] == "already_approved"
    m._box_settle(card["id"], "deny"); th.join(3)


# ---- 3. decided elsewhere (refused on Telegram or in another tab) ----
def test_press_after_a_refusal_elsewhere_says_refused(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, ttl=30)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    assert m._decide_permit(card["id"], "deny")["status"] == "denied"      # Telegram's Refuse
    th.join(3)
    code, d = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    assert code == 409 and d["reason"] == "already_denied" and "already refused" in d["error"]
    _no_class_names(d)
    # and Telegram's Allow on that card gets the same sentence
    t = m._decide_permit(card["id"], "allow")
    assert t["ok"] is False and t["reason"] == "already_denied" and "already refused" in t["error"]


# ---- 4. the job that asked has ended ----
def test_press_after_the_turn_was_stopped_closes_the_card_and_runs_nothing(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, ttl=30)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    run.stopped = True                                # Stop pressed: the reasoner is gone, the hook thread still waits
    code, d = m._approve_permit(card["id"], m.GATE.get(card["id"]), "page")
    th.join(3)
    assert code == 409 and d["reason"] == "no_waiter" and "has ended" in d["error"]
    assert m.GATE.get(card["id"]).status == "denied" and out["d"]["behavior"] == "deny"
    _no_class_names(d)


def test_press_on_a_box_card_nobody_waits_for_is_not_approved(monkeypatch, tmp_path):
    """After a bridge restart the permit is still proposed in permitd but no hook waits: never approve it."""
    m = _load(monkeypatch, tmp_path, ttl=30)
    r = m.GATE.call("box_act", {"platform": "box", "method": "Bash", "action_id": "touch",
                                "summary": "run on the box: touch x", "remember_ok": False})
    pid = r.permit["id"]
    code, d = m._approve_permit(pid, m.GATE.get(pid), "page")
    assert code == 409 and d["reason"] == "no_waiter" and m.GATE.get(pid).status == "denied"


def test_unknown_card_is_said_plainly(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    code, d = m._approve_permit("PRM-000000000000", None, "page")
    assert code == 404 and d["reason"] == "unknown_permit" and "does not know this card" in d["error"]
    assert m._decide_permit("PRM-000000000000", "allow")["reason"] == "unknown_permit"


# ---- 5. the hook's own timeout never cuts the bridge's answer short ----
def test_the_hook_waits_longer_than_the_card_lives(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, ttl=900)
    s = json.loads(m._hook_settings())
    assert s["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"] > m.PERMIT_TTL
    src = (ROOT / "scripts" / "cc" / "cc-permit-hook.py").read_text()
    assert '"900")) + 60' in src                          # the hook's HTTP wait is ttl + 60 s


def test_hook_with_no_bridge_denies_with_a_reason(monkeypatch, tmp_path):
    """The hook itself failing (bridge down, timeout) is a deny that says the bridge did not answer."""
    env = {"CC_PORT": "1", "CC_BASE": "/cc", "CC_ASK_TOKEN": "x", "CC_PERMIT_TTL": "1", "PATH": "/usr/bin:/bin"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "cc" / "cc-permit-hook.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                       capture_output=True, text=True, timeout=30, env=env)
    dec = json.loads(r.stdout)["hookSpecificOutput"]["decision"]
    assert dec["behavior"] == "deny" and "the bridge did not answer" in dec["message"]


# ---- the HTTP door the page uses ----
def _serve(m):
    srv = m.ThreadingHTTPServer(("127.0.0.1", 0), m.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/cc"


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_page_route_says_the_reason_and_logs_it(monkeypatch, tmp_path, capsys):
    m = _load(monkeypatch, tmp_path)
    srv, base = _serve(m)
    try:
        run, cards = _run(m)
        th, out, card = _ask(m, cards)
        th.join(TTL + 3)
        code, d = _post(base + "/permits/approve", {"id": card["id"]})
        assert code == 409 and d == {"ok": False, "error": m._permit_say("already_denied", card["id"]), "reason": "already_denied"}
        _no_class_names(d)
        # Refuse on the dead card says the same kind of thing, not a 500
        code, d = _post(base + "/permits/deny", {"id": card["id"]})
        assert code == 409 and d["reason"] == "already_denied"
        # a live card, allowed twice through the door
        th2, out2, c2 = _ask(m, cards, "touch /tmp/permit-say-2")
        code, d = _post(base + "/permits/approve", {"id": c2["id"]})
        th2.join(3)
        assert code == 200 and d["status"] == "allowed"
        code, d = _post(base + "/permits/approve", {"id": c2["id"]})
        assert code == 200 and d["ok"] is True and d["status"] == "already allowed"
        code, d = _post(base + "/permits/approve", {"id": "PRM-ffffffffffff"})
        assert code == 404 and d["reason"] == "unknown_permit"
    finally:
        srv.shutdown()
    logs = capsys.readouterr().out
    assert f"permit {card['id']} approve refused reason=already_denied via=page" in logs
    assert f"permit {c2['id']} approve again: already allowed via=page" in logs


def test_cards_carry_their_expiry(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path, ttl=900)
    run, cards = _run(m)
    th, out, card = _ask(m, cards)
    assert abs(card["expires_at"] - (time.time() + 900)) < 5
    pend = [m._permit_public(p) for p in m.GATE.pending()]
    assert pend and abs(pend[0]["expires_at"] - card["expires_at"]) <= 1
    m._box_settle(card["id"], "deny"); th.join(3)


def test_every_reason_reads_as_a_sentence(monkeypatch, tmp_path):
    m = _load(monkeypatch, tmp_path)
    for r in ("already_denied", "already_expired", "expired", "already_approved", "already_executed", "already_used",
              "unknown_permit", "no_waiter", "bad_signature", "args_mismatch", "something_new"):
        s = m._permit_say(r)
        assert s and s[0].islower() and "Error" not in s and "{" not in s


# ---- the page: the card's clock and the press words, under node ----
def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT / "ui" / "lib"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_card_clock_and_press_words_under_node():
    d = _node(r"""
const P = require('./permitClock')
const now = 1_000_000_000_000
const out = {
  fresh: P.cardClock(now / 1000 + 900, 900, now, now),
  last: P.cardClock(now / 1000 + 30, 900, now, now),
  zero: P.cardClock(now / 1000, 900, now, now),
  past: P.cardClock(now / 1000 - 5, 900, now, now),
  old: P.cardClock(null, 900, now + 901000, now),
  none: P.cardClock(null, null, now, now),
  again: P.pressWords({ ok: true, status: 'already allowed' }, 'approve'),
  fine: P.pressWords({ ok: true, status: 'allowed' }, 'approve'),
  bad: P.pressWords({ ok: false, error: 'this card expired after 15 minutes; nothing ran', reason: 'already_denied' }, 'approve'),
}
console.log(JSON.stringify(out))
""")
    assert d["fresh"]["label"] == "15 min left" and d["fresh"]["expired"] is False
    assert d["last"]["label"] == "under a minute left"
    assert d["zero"]["expired"] is True and d["zero"]["label"] == "expired" and d["past"]["expired"] is True
    assert d["old"]["expired"] is True                      # an older card without expires_at runs from when it was seen
    assert d["none"]["known"] is False
    assert d["again"] == {"error": False, "text": "Already allowed; nothing more to do."}
    assert d["fine"]["error"] is False
    assert d["bad"]["error"] is True and d["bad"]["text"] == "That Allow did nothing: this card expired after 15 minutes; nothing ran."


def test_page_uses_the_clock_and_the_words():
    src = (ROOT / "ui" / "pages" / "cc.js").read_text()
    assert "import { cardClock, pressWords } from '../lib/permitClock'" in src
    assert "cardClock(p.expires_at, p.ttl_seconds, now, seenRef.current)" in src
    assert "clock.expired ?" in src and "pressWords(data, action)" in src
    assert "did not reach the job" not in src
