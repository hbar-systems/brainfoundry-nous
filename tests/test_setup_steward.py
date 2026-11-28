"""The setup period (STEWARD-1, 2026-11-27): api/setup_steward.py and scripts/cc/cc_steward.py.
Synthetic data only; no network, no reasoner."""
import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
from api import setup_steward as ss  # noqa: E402
import cc_steward  # noqa: E402

OWNER = "owner-test-key"
GOOD_HASH = "$2b$12$" + "a" * 53


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _p(pid, name, created=0):
    return {"proposal_id": pid, "source_refs": {"filename": name}, "created_at": created}


# ---------------------------------------------------------------- the key

def test_mint_needs_the_consent_line_shown(tmp_path):
    k = ss.SetupKeys(tmp_path)
    with pytest.raises(ss.SetupError) as e:
        k.mint(lang="de", text_sha="0" * 64)
    assert e.value.status == 400
    out = k.mint(lang="de", text_sha=ss.consent_sha("de"))
    assert set(out) == {"scopes", "minted_at", "expires_at", "by"}       # the raw key is never returned
    assert out["expires_at"] - out["minted_at"] == ss.DEFAULT_TTL_HOURS * 3600


def test_key_file_is_private_and_status_shows_no_secret(tmp_path):
    k = ss.SetupKeys(tmp_path)
    k.mint(lang="en", text_sha=ss.consent_sha("en"))
    f = tmp_path / "steward.key"
    raw = f.read_text().strip()
    assert raw.startswith("stw_") and len(raw) > 40
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    blob = json.dumps(k.status()) + (tmp_path / "key.json").read_text() + (tmp_path / "log.jsonl").read_text()
    assert raw not in blob


def test_life_is_capped(tmp_path):
    k = ss.SetupKeys(tmp_path)
    with pytest.raises(ss.SetupError):
        k.mint(lang="en", text_sha=ss.consent_sha("en"), ttl_hours=ss.MAX_TTL_HOURS + 1)


def test_scopes_expiry_and_revoke(tmp_path):
    c = Clock()
    k = ss.SetupKeys(tmp_path, clock=c)
    k.mint(lang="en", text_sha=ss.consent_sha("en"), ttl_hours=2)
    raw = (tmp_path / "steward.key").read_text().strip()
    for s in ss.SCOPES:
        k.check(raw, s)
    for bad in ("delete", "persona", "settings", "password", "export"):
        with pytest.raises(ss.SetupError) as e:
            k.check(raw, bad)
        assert e.value.status == 403
    with pytest.raises(ss.SetupError):
        k.check("stw_" + "x" * 43, "state")
    c.t += 2 * 3600
    with pytest.raises(ss.SetupError) as e:
        k.check(raw, "state")
    assert "run out" in e.value.detail and not k.active()
    c.t -= 3600
    k.log("cleared copies", copies=3)
    out = k.revoke(by="hbar", why="handover")
    assert out["last_steward_action"]["action"] == "cleared copies"
    assert not (tmp_path / "steward.key").exists()
    with pytest.raises(ss.SetupError) as e:
        k.check(raw, "state")
    assert "ended" in e.value.detail


def test_password_kept_as_a_hash_only(tmp_path):
    k = ss.SetupKeys(tmp_path)
    with pytest.raises(ss.SetupError):
        k.keep_password_hash("short", lambda p: GOOD_HASH)
    with pytest.raises(ss.SetupError):
        k.keep_password_hash("aaaaaaaaaaaaaa", lambda p: GOOD_HASH)
    with pytest.raises(ss.SetupError):
        k.keep_password_hash("a-long-enough-one", lambda p: "plain")
    k.keep_password_hash("a-long-enough-one", lambda p: GOOD_HASH)
    kept = (tmp_path / "console-hash").read_text()
    assert kept.strip() == GOOD_HASH and "a-long-enough-one" not in kept
    assert stat.S_IMODE(os.stat(tmp_path / "console-hash").st_mode) == 0o600


# ---------------------------------------------------------------- copies and the person's yes

def test_duplicates_stored_pending_and_changed():
    long = "Vorlesung 1: Muskel. " + "Der Muskel wird erklaert. " * 20           # a synopsis is the first 400 characters
    stored = [{"name": "laptop/A/a.md", "synopsis": long[:400]},
              {"name": "laptop/A/b.md", "synopsis": "old start"}]
    texts = {"p1": long + " and the rest of it", "p2": "new start", "p3": "same", "p4": "same",
             "p5": "unique"}
    pending = [_p("p1", "laptop/A/a.md"), _p("p2", "laptop/A/b.md"), _p("p3", "laptop/B/x.md"),
               _p("p4", "laptop/B/deep/x.md"), _p("p5", "laptop/C/y.md"), _p("p6", "laptop/C/gone.md")]
    out = ss.duplicates(pending, stored, texts.get)
    got = {c["proposal_id"]: c["of"] for c in out["copies"]}
    assert got == {"p1": "stored", "p4": "pending"}       # the shorter path stays; a newer version is left
    assert out["changed"] == 1


def test_the_same_name_twice_keeps_one():
    texts = {"a": "x y z", "b": "x  y z"}
    out = ss.duplicates([_p("a", "laptop/n.md"), _p("b", "laptop/n.md")], [], texts.get)
    assert len(out["copies"]) == 1


def test_chosen_is_only_what_the_person_said_yes_to():
    chat = lambda n: n.split("/")[-1].startswith("chatgpt_")  # noqa: E731
    pend = [_p("1", "laptop/a.md", 100), _p("2", "chatgpt_x.md", 50), _p("3", "chatgpt_y.md", 200),
            _p("4", "upload.pdf", 300)]
    assert ss.chosen(pend, None, None, chat) == []
    assert [p["proposal_id"] for p in ss.chosen(pend, {"ids": ["4"]}, None, chat)] == ["4"]
    assert [p["proposal_id"] for p in ss.chosen(pend, {"kind": "chats"}, None, chat)] == ["2", "3"]
    sv = {"chosen": ["proposed"], "run_created": 150}
    assert [p["proposal_id"] for p in ss.chosen(pend, None, sv, chat)] == ["1", "3"]
    assert ss.chosen(pend, None, {"chosen": None, "run_created": 0}, chat) == []
    iso = _p("5", "chatgpt_z.md")
    iso["created_at"] = "2027-01-01T00:00:00Z"
    assert [p["proposal_id"] for p in ss.chosen([iso], None, sv, chat)] == ["5"]


def test_swap_console_hash_touches_one_line():
    cf = ("console.anne.brain.example {\n    basicauth @login {\n        anne $2a$14$" + "b" * 53 + "\n    }\n}\n"
          "console.paul.brain.example {\n    basicauth {\n        anne $2a$14$" + "c" * 53 + "\n    }\n}\n")
    out = ss.swap_console_hash(cf, "console.anne.", "anne", GOOD_HASH)
    assert GOOD_HASH in out.split("console.paul")[0] and "c" * 53 in out
    assert out.count("\n") == cf.count("\n")
    with pytest.raises(ValueError):
        ss.swap_console_hash(cf, "console.rocky.", "rocky", GOOD_HASH)
    with pytest.raises(ValueError):
        ss.swap_console_hash(cf, "console.anne.", "anne", "not-a-hash")


# ---------------------------------------------------------------- the doors

class Fake:
    def __init__(self):
        self.p = [_p("p1", "laptop/S/a.md"), _p("p2", "laptop/S/a.md"), _p("p3", "laptop/S/b.md"),
                  _p("p4", "laptop/S/risky.md")]
        self.texts = {"p1": "alpha", "p2": "alpha", "p3": "beta", "p4": "gamma"}
        self.rejected, self.approved = [], []

    def pending(self):
        return list(self.p)

    def stored(self):
        return [{"name": "laptop/Secret Title.md", "synopsis": "s"}, {"name": "chatgpt_private.md", "synopsis": "t"}]

    def text_of(self, pid):
        return self.texts.get(pid)

    def reject(self, pid, note):
        self.rejected.append(pid)
        self.p = [x for x in self.p if x["proposal_id"] != pid]

    def approve(self, items):
        self.approved = [x["proposal_id"] for x in items]
        return {"running": True}

    def waiting(self):
        return {"documents": len(self.p), "chats": 0, "total": len(self.p), "reading": {"running": False}}

    def intent(self):
        return None

    def survey(self):
        return {"state": "chosen", "chosen": ["proposed"], "refused_total": 2, "refused_by": {"type": 2}}

    def held_high(self, items):
        return [x for x in items if x["proposal_id"] == "p4"]

    def chat_doc(self, n):
        return n.startswith("chatgpt_")

    def facts(self):
        return {"version": "abc1234", "persona_chars": 900}


def _client(tmp_path):
    def get_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
        if x_api_key != OWNER:
            raise HTTPException(401, "Invalid API key")
        return x_api_key
    keys = ss.SetupKeys(tmp_path)
    fake = Fake()
    app = FastAPI()
    app.include_router(ss.make_router(keys, fake, get_api_key, hasher=lambda p: GOOD_HASH))
    return TestClient(app), keys, fake


def _consent(c, lang="de"):
    o = {"X-API-Key": OWNER}
    sha = c.get("/setup/consent", params={"lang": lang}, headers=o).json()["sha"]
    r = c.post("/setup/key", json={"consent": True, "lang": lang, "text_sha": sha}, headers=o)
    assert r.status_code == 200, r.text
    assert "stw_" not in r.text


def test_doors_end_to_end(tmp_path):
    c, keys, fake = _client(tmp_path)
    assert c.get("/setup/state").status_code == 401                         # no period open
    assert c.post("/setup/key", json={"lang": "de"}, headers={"X-API-Key": OWNER}).status_code == 400
    assert c.post("/setup/key", json={"consent": True}).status_code == 401  # only the owner's console mints
    _consent(c)
    raw = (tmp_path / "steward.key").read_text().strip()
    h = {ss.KEY_HEADER: raw}
    st = c.get("/setup/state", headers=h)
    assert st.status_code == 200
    body = st.json()
    assert "Secret Title" not in st.text and "private" not in st.text      # counts, never names
    assert body["knowledge"] == {"documents": 2, "chats": 1, "laptop": 1, "other": 0}
    assert body["duplicates"]["copies"] == 1 and body["held_for_a_look"] == 1
    r = c.post("/setup/duplicates/clear", json={"dry_run": True}, headers=h).json()
    assert r == {"copies": 1, "cleared": 0, "changed_left_for_the_person": 0} and fake.rejected == []
    r = c.post("/setup/duplicates/clear", json={}, headers=h).json()
    assert r["cleared"] == 1 and fake.rejected == ["p2"]
    r = c.post("/setup/approve", headers=h).json()
    assert r["queued"] == 2 and r["held_for_a_look"] == 1 and set(fake.approved) == {"p1", "p3"}
    # the owner's side: no setup key opens it
    assert c.post("/setup/revoke", json={}, headers=h).status_code == 401
    assert c.post("/setup/key/check", json={"key": raw, "scope": "ask"}, headers={"X-API-Key": OWNER}).json() == {"ok": True}
    assert c.post("/setup/key/check", json={"key": raw, "scope": "delete"}, headers={"X-API-Key": OWNER}).json()["ok"] is False
    assert c.post("/setup/handover/password", json={"password": "one-long-pass", "again": "other"},
                  headers={"X-API-Key": OWNER}).status_code == 400
    assert c.post("/setup/handover/password", json={"password": "one-long-pass", "again": "one-long-pass"},
                  headers={"X-API-Key": OWNER}).json() == {"password_chosen": True}
    logs = c.get("/setup/log", headers=h).json()["log"]
    assert [x["action"] for x in logs][:3] == ["key minted", "cleared copies", "reading what the person chose"]
    out = c.post("/setup/revoke", json={"by": "hbar"}, headers={"X-API-Key": OWNER}).json()
    assert out["active"] is False and out["last_steward_action"]["action"] == "reading what the person chose"
    assert c.get("/setup/state", headers=h).status_code == 401
    s = c.get("/setup/status", headers={"X-API-Key": OWNER}).json()
    assert s["active"] is False and s["password_chosen"] is True


def test_main_mounts_the_setup_doors():
    # main refuses to start without an identity secret; scratch runtime off-container (as test_chunker)
    import tempfile
    rt = tempfile.mkdtemp(prefix="steward-test-")
    os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
    os.environ.setdefault("BRAIN_RUNTIME_DIR", rt)
    os.environ.setdefault("SETTINGS_PATH", os.path.join(rt, "settings.json"))
    from api import main
    paths = set(main.app.openapi()["paths"])      # included routers are lazy objects in app.routes (fastapi 0.16x)
    assert {"/setup/state", "/setup/key", "/setup/revoke", "/setup/duplicates/clear", "/setup/approve",
            "/setup/handover/password", "/setup/key/check"} <= paths


# ---------------------------------------------------------------- the console side

def test_note_only_while_open():
    assert cc_steward.note(None) == "" and cc_steward.note({"active": False}) == ""
    n = cc_steward.note({"active": True, "expires_at": 1_800_000_000}, "de", "/cc/setup")
    assert "/cc/setup" in n and "keine Befehle" in n and "2027" in n
    assert cc_steward.note({"active": True}, "xx").startswith("A setup period")


def test_verdict_sees_advice_and_nothing_here_but_returns_no_text():
    v = cc_steward.verdict("Run curl -H 'Authorization: Bearer abc' https://x/import-laptop", [], [], False)
    assert v["setup_advice"] and "Bearer" not in json.dumps(v)
    v = cc_steward.verdict("Es ist noch kein Kursmaterial hochgeladen. Dein Ordner /home/hands/in ist leer", [], [], False)
    assert v["said_nothing_in"] and v["setup_advice"]
    v = cc_steward.verdict("Ich sehe keine Anatomie-Unterlagen von dir.", ["laptop/a.md"], ["Anatomie"], False)
    assert v["said_nothing_in"]
    v = cc_steward.verdict("Aus mikrobiologie-01 und deinem Chat: Sterilisation tötet alle Keime.",
                           ["laptop/Studium/mikrobiologie-01.md", "chatgpt_x.md"], ["Sterilisation", "Gram"], False)
    assert v == {**v, "answered": True, "drew_on": 2, "named_own": 1, "expect_hits": ["Sterilisation"],
                 "expect_total": 2, "setup_advice": False, "said_nothing_in": False}


def test_ask_runs_one_labelled_turn_and_logs():
    seen, logged = {}, []

    def turn(q, **kw):
        seen.update(kw, q=q)
        return 200, {"reply": "Deine Notiz zu Glykolyse sagt ...", "thread": "t9"}
    st, v = cc_steward.ask({"question": "Was weisst du zur Glykolyse?", "expect": ["Glykolyse"]}, turn,
                           lambda: ["laptop/biochemie-01.md"], logged.append)
    assert st == 200 and v["answered"] and v["expect_hits"] == ["Glykolyse"] and "reply" not in v
    assert seen["new"] is True and seen["label"] == "Setup check" and seen["source"] == "steward"
    assert logged and "test question" in logged[0]
    assert cc_steward.ask({"question": ""}, turn, list, logged.append)[0] == 400


def test_key_ok_fails_closed():
    def boom(*a):
        raise OSError("api down")
    assert cc_steward.key_ok(boom, "stw_" + "x" * 40, "ask") is False
    assert cc_steward.key_ok(lambda *a: {"ok": True}, "not-a-setup-key", "ask") is False
    assert cc_steward.key_ok(lambda *a: {"ok": True}, "stw_" + "x" * 40, "ask") is True
    assert cc_steward.key_ok(lambda *a: {"ok": "yes"}, "stw_" + "x" * 40, "ask") is False


def test_watch_caches_and_survives_errors():
    n = {"c": 0}
    t = {"v": 0.0}

    def fetch():
        n["c"] += 1
        if n["c"] == 2:
            raise OSError
        return {"active": True}
    w = cc_steward.Watch(fetch, ttl=60, clock=lambda: t["v"])
    assert w.status() == {"active": True} and w.status() == {"active": True} and n["c"] == 1
    t["v"] = 61
    assert w.status() is None


def test_console_state_reads_the_ready_items():
    s = cc_steward.console_state({"lang": "de", "current": {"start": "/apps/week", "panels": {"hero": False, "nav": False, "tools": False}}},
                                 {"auth": {"loggedIn": True}, "codex": {}}, 800, [{"error": True}, {}])
    assert s == {"seat": "claude", "lang": "de", "start": "/apps/week", "quiet": True, "persona_chars": 800,
                 "turns": 2, "turns_ok": 1, "last_failed": False}
    assert cc_steward.console_state(None, {}, 0, [])["seat"] == "none"


def _bridge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CC_CWD", str(tmp_path / "brain"))
    monkeypatch.delenv("BRAIN_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("cc_bridge_stw", ROOT / "scripts" / "cc" / "cc-bridge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cc_bridge_stw"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bridge_puts_the_setup_line_in_the_turn_only_while_open(monkeypatch, tmp_path):
    m = _bridge(monkeypatch, tmp_path)
    m.SETUP_WATCH = cc_steward.Watch(lambda: {"active": True, "expires_at": time.time() + 3600})
    prompt, _ = m._compose("bring my folder in")
    assert "<setup-period>" in prompt and "do not write commands" in prompt
    m.SETUP_WATCH = cc_steward.Watch(lambda: {"active": False})
    prompt, _ = m._compose("bring my folder in")
    assert "<setup-period>" not in prompt
    src = (ROOT / "scripts" / "cc" / "cc-bridge.py").read_text()
    # both steward routes check the setup key through the api before anything else runs
    for route, scope in (("/setup/state", "state"), ("/setup/ask", "ask")):
        i = src.index(f'if route == "{route}":')
        assert f'"{scope}")' in src[i:i + 400] and "key_ok" in src[i:i + 400]


def test_handover_script_parses_and_never_prints_the_secret():
    import subprocess
    sh = ROOT / "scripts" / "setup-handover.sh"
    assert subprocess.run(["bash", "-n", str(sh)]).returncode == 0
    src = sh.read_text()
    assert "--apply" in src and "caddy validate" in src and "/setup/revoke" in src
    for bad in ('echo "$HASH"', "echo $HASH", "set -x"):
        assert bad not in src
