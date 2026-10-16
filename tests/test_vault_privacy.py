"""The private vault, the owner's local-readers allowlist, the read audit, the
session mark and privacy on /memory/append (2026-10-15).

Same method as test_memory_privacy: no Postgres (fake cursors that answer the
few statements each path issues), no model (providers.complete/stream are
recorders), so every assertion is on what would have reached a reasoner or
the database.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tarfile
import uuid

import pytest

from api import privacy as pv
from tests.test_memory_privacy import (  # noqa: F401  (fixtures by name)
    CLOSED_MODELS, LOCAL_MODEL, SECRET, FakeCursor, FakeDB, _chat, _run, m, sent,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
SID = str(uuid.uuid4())


@pytest.fixture
def audit_file(monkeypatch, tmp_path):
    from api.tools import audit as _audit
    p = tmp_path / "tool_audit.jsonl"
    monkeypatch.setattr(_audit, "AUDIT_PATH", p)
    return p


@pytest.fixture
def readers(monkeypatch):
    """Control the owner's allowlist (settings entry) per test."""
    from api import settings_store as _ss
    box = {"v": None}
    monkeypatch.setattr(_ss, "get_local_readers", lambda: box["v"])
    monkeypatch.delenv("BRAIN_LOCAL_READERS", raising=False)
    return box


# ── sessions in the fake database ───────────────────────────────────────────

class SessionCursor(FakeCursor):
    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        if flat.startswith("SELECT local_only_at FROM chat_sessions"):
            self.db.statements.append((sql, params))
            sid = params[0]
            self._result = [("2026-10-15",)] if sid in self.db.marked else ([(None,)] if sid in self.db.sessions else [])
            return
        if flat.startswith("UPDATE chat_sessions SET local_only_at"):
            self.db.statements.append((sql, params))
            self.db.marked.add(params[0])
            self._result = []
            return
        if flat.startswith("SELECT title FROM chat_sessions"):
            self._result = [("diary chat",)]
            return
        if flat.startswith("SELECT role, content, created_at FROM chat_messages"):
            self._result = [("user", "what is in my diary?", None), ("assistant", f"it says {SECRET}", None)]
            return
        if flat.startswith("INSERT INTO document_embeddings"):
            self.db.statements.append((flat, params))
            self.db.inserted.append(json.loads(params[3]))
            self._result = [(len(self.db.inserted),)]
            return
        super().execute(sql, params)


class SessionDB(FakeDB):
    def __init__(self):
        super().__init__()
        self.sessions = {SID}
        self.marked = set()
        self.inserted = []

    def cursor(self):
        return SessionCursor(self)


@pytest.fixture
def sdb(m, monkeypatch):
    db = SessionDB()
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    monkeypatch.setattr(m, "_verify_loop_permit", lambda pid, tok: {"agent_id": "ui"})
    return db


def _chat_s(m, model, session_id=SID):
    req = {"model": model, "session_id": session_id,
           "messages": [{"role": "user", "content": "what is in my diary?"}]}
    return _run(m.rag_chat_completion(req, http_request=None, api_key="k"))


# ── A. the owner's allowlist of local readers ───────────────────────────────

def test_no_list_means_every_local_model_reads(m, sent, readers):
    readers["v"] = None
    _chat(m, LOCAL_MODEL)
    assert any(SECRET in t for _m, t in sent)


def test_local_model_off_the_list_gets_the_open_view(m, sent, readers):
    readers["v"] = ["qwen2.5:14b"]
    out = _chat(m, LOCAL_MODEL)
    assert sent and not any(SECRET in t for _m, t in sent)
    assert "notes/diary.md" not in out["rag_metadata"]["sources"]
    assert out["rag_metadata"]["privacy"]["local_reader"] is False


def test_local_model_on_the_list_reads(m, sent, readers):
    readers["v"] = ["llama3.2:3b:latest", "qwen2.5:14b"]  # ':latest' is the same model
    _chat(m, LOCAL_MODEL)
    assert any(SECRET in t for _m, t in sent)


def test_empty_list_means_no_model_reads(m, sent, readers):
    readers["v"] = []
    _chat(m, LOCAL_MODEL)
    assert not any(SECRET in t for _m, t in sent)


def test_env_allowlist_when_no_setting(m, sent, readers, monkeypatch):
    monkeypatch.setenv("BRAIN_LOCAL_READERS", "qwen2.5:14b")
    _chat(m, LOCAL_MODEL)
    assert not any(SECRET in t for _m, t in sent)
    monkeypatch.setenv("BRAIN_LOCAL_READERS", "none")
    assert pv.local_readers() == []


def test_allowlist_never_lets_a_closed_model_in(m, sent, readers):
    readers["v"] = CLOSED_MODELS
    for model in CLOSED_MODELS:
        assert not pv.may_read_local_only(model)


# ── A. the read audit ───────────────────────────────────────────────────────

def test_local_read_writes_one_audit_line_without_content(m, sent, readers, audit_file):
    out = _chat(m, LOCAL_MODEL)
    lines = [json.loads(l) for l in audit_file.read_text().splitlines()]
    reads = [l for l in lines if l.get("kind") == "local_only_read"]
    assert len(reads) == 1
    r = reads[0]
    assert r["model"] == LOCAL_MODEL and r["endpoint_host"] == "ollama"
    assert r["documents"] == ["notes/diary.md", "notes/odd.md"] and r["chunks"] == 2
    assert r["ts"] and r["surface"] == "chat/rag"
    assert SECRET not in audit_file.read_text() and "SECRET-ODD" not in audit_file.read_text()
    meta = out["rag_metadata"]["privacy"]
    assert meta["local_only_used"] is True and "GREEN" in meta["rule"]


def test_closed_turn_writes_no_read_line(m, sent, readers, audit_file):
    out = _chat(m, CLOSED_MODELS[0])
    assert not audit_file.exists() or "local_only_read" not in audit_file.read_text()
    assert out["rag_metadata"]["privacy"] == {"local_reader": False, "local_only_used": False, "rule": None}


def test_recent_reads_lists_only_read_lines(audit_file):
    from api.tools import audit as _audit
    _audit.log({"tool": "web_search", "ok": True})
    pv.audit_local_read("llama3.2:3b", [{"document_name": "a.md", "metadata": {"privacy": "local-only"}}],
                        session_id="s", endpoint_host="ollama")
    assert pv.audit_local_read("x", [{"document_name": "b.md", "metadata": {}}]) is None
    rr = pv.recent_reads()
    assert len(rr) == 1 and rr[0]["documents"] == ["a.md"]


# ── A. the vault: ingest, lock, export ──────────────────────────────────────

class VaultDB:
    def __init__(self):
        self.rows = {}      # document_name -> [metadata]
        self.statements = []

    def cursor(self):
        db = self

        class C:
            def execute(self, sql, params=None):
                flat = " ".join(sql.split())
                db.statements.append((flat, params))
                if flat.startswith("DELETE FROM document_embeddings"):
                    db.rows.pop(params[0], None)
                elif flat.startswith("INSERT INTO document_embeddings"):
                    db.rows.setdefault(params[0], []).append((params[1], json.loads(params[3])))

            def close(self):
                pass
        return C()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def vault(tmp_path, monkeypatch):
    from api import vault as _vault
    root = tmp_path / "vault"
    (root / "diary").mkdir(parents=True)
    (root / "diary" / "2026-10.md").write_text(f"October. {SECRET}")
    (root / "notes.txt").write_text("a private note")
    (root / ".hidden.md").write_text("dotfile")
    (root / "photo.jpg").write_bytes(b"\xff\xd8")
    outside = tmp_path / "outside.md"
    outside.write_text("not in the vault")
    (root / "link.md").symlink_to(outside)
    monkeypatch.setenv("BRAIN_VAULT_MOUNT", str(root))
    monkeypatch.setenv("BRAIN_VAULT_DIR", "/home/owner/vault")
    monkeypatch.setenv("BRAIN_RUNTIME_DIR", str(tmp_path / "runtime"))
    db = VaultDB()

    def run(**kw):
        return _vault.scan(connect=lambda: db, chunker=lambda t: [t],
                           embedder=lambda cs: [[0.0] * 4 for _ in cs], **kw)
    return root, db, run, _vault


def test_vault_scan_ingests_local_only_with_vault_source(vault):
    root, db, run, _v = vault
    r = run()
    assert r["ok"] and {i["file"] for i in r["ingested"]} == {"diary/2026-10.md", "notes.txt"}
    assert set(db.rows) == {"vault/diary/2026-10.md", "vault/notes.txt"}  # no dotfile, jpg or symlink
    for name, chunks in db.rows.items():
        for _text, md in chunks:
            assert md["privacy"] == "local-only" and md["vault"] is True
            assert md["source"] == "vault:" + name[len("vault/"):]
            assert pv.level_of(md) == pv.LOCAL_ONLY and pv.is_vault_metadata(md)


def test_vault_rescan_skips_unchanged_and_reingests_changed(vault):
    root, db, run, _v = vault
    run()
    n = len(db.statements)
    r = run()
    assert r["unchanged"] == 2 and not r["ingested"] and len(db.statements) == n
    (root / "notes.txt").write_text("a changed private note")
    r = run()
    assert [i["file"] for i in r["ingested"]] == ["notes.txt"]
    assert db.rows["vault/notes.txt"][0][0] == "a changed private note"


def test_vault_state_holds_names_not_content(vault):
    root, db, run, _v = vault
    run()
    state = (pathlib.Path(os.environ["BRAIN_RUNTIME_DIR"]) / "vault_state.json").read_text()
    assert "diary/2026-10.md" in state and SECRET not in state and "private note" not in state


def test_vault_missing_files_reported_then_pruned(vault):
    root, db, run, _v = vault
    run()
    (root / "notes.txt").unlink()
    assert run()["missing"] == ["notes.txt"] and "vault/notes.txt" in db.rows
    r = run(prune=True)
    assert r["pruned"] == ["notes.txt"] and "vault/notes.txt" not in db.rows


def test_vault_scan_never_writes_outside_the_database(vault, tmp_path):
    root, db, run, _v = vault
    before = {p for p in tmp_path.rglob("*")}
    run()
    after = {p for p in tmp_path.rglob("*")}
    new = after - before
    assert {p.name for p in new if p.is_file()} <= {"vault_state.json"}
    assert not any(SECRET in p.read_text(errors="ignore") for p in new if p.is_file())


def test_no_vault_mounted(monkeypatch, tmp_path):
    from api import vault as _vault
    monkeypatch.setenv("BRAIN_VAULT_MOUNT", str(tmp_path / "absent"))
    assert _vault.status()["mounted"] is False
    r = _vault.scan(connect=lambda: None, chunker=lambda t: [t], embedder=lambda cs: [])
    assert r["ok"] is False and r["mounted"] is False


def test_vault_document_cannot_be_set_open(m, monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        m.set_document_privacy("vault/diary/2026-10.md", {"privacy": "open"}, api_key="k")
    assert e.value.status_code == 403 and e.value.detail["error"] == "vault_locked"
    # a document whose chunks carry a vault source, whatever its name
    monkeypatch.setattr(m, "_document_in_vault", lambda name: True)
    with pytest.raises(HTTPException) as e:
        m.set_document_privacy("renamed.md", {"privacy": "open"}, api_key="k")
    assert e.value.status_code == 403


def test_open_update_sql_carries_the_vault_guard(m):
    from tests.test_memory_privacy import IngestDB
    db = IngestDB(update_rowcount=1)
    m._set_document_privacy("x.md", "open", conn=db)
    sql, _ = db.statements[-1]
    assert "NOT LIKE 'vault:%%'" in sql
    m._set_document_privacy("x.md", "local-only", conn=db)
    assert "vault:" not in db.statements[-1][0]


def test_document_in_vault_fails_closed_without_db(m, monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(m, "get_db_connection", boom)
    assert m._document_in_vault("anything.md") is True


def test_upload_into_vault_namespace_is_local_only(m, monkeypatch):
    from tests.test_memory_privacy import IngestDB
    db = IngestDB()
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    events = list(m._stream_ingest_path_b(
        text="alpha beta " * 50, filename="vault/sneaky.md", content_type="text/plain",
        size=10, proposal_id="p", layer=None, privacy="open"))
    assert any(e.startswith("event: done") for e in events)
    assert set(db.inserted_privacy()) == {"local-only"}


def _export_rows(table):
    data = {
        "document_embeddings": [
            {"document_name": "a.md", "content": "open", "metadata": {"privacy": "open"}, "embedding": "[0]", "created_at": "t"},
            {"document_name": "vault/diary.md", "content": SECRET,
             "metadata": {"privacy": "local-only", "vault": True, "source": "vault:diary.md"}, "embedding": "[0]", "created_at": "t"},
            {"document_name": "renamed.md", "content": SECRET + "-2",
             "metadata": json.dumps({"privacy": "local-only", "source": "vault:x.md"}), "embedding": "[0]", "created_at": "t"},
        ],
        "chat_sessions": [], "chat_messages": [],
    }
    return iter(data[table])


def test_export_leaves_the_vault_out_by_default(tmp_path, monkeypatch):
    from api import export
    monkeypatch.setattr(export, "RUNTIME_DIR", tmp_path / "rt")
    out = export.build_export(tmp_path / "out", rows=_export_rows, probe=lambda: {"embedding_dim": 4})
    with tarfile.open(out, "r:gz") as tar:
        body = tar.extractfile("db/document_embeddings.jsonl").read().decode()
        manifest = json.loads(tar.extractfile("manifest.json").read())
    assert SECRET not in body and "a.md" in body
    assert manifest["contents"]["vault"] == {"included": False, "chunks": 2}
    assert manifest["contents"]["tables"]["document_embeddings"] == 1


def test_export_includes_the_vault_on_request(tmp_path, monkeypatch):
    from api import export
    monkeypatch.setattr(export, "RUNTIME_DIR", tmp_path / "rt")
    out = export.build_export(tmp_path / "out", rows=_export_rows, probe=lambda: {"embedding_dim": 4},
                              include_vault=True)
    with tarfile.open(out, "r:gz") as tar:
        body = tar.extractfile("db/document_embeddings.jsonl").read().decode()
    assert SECRET in body


def test_laptop_export_script_filters_vault_rows():
    import importlib.util
    spec = importlib.util.spec_from_file_location("export_brain", ROOT / "scripts" / "export_brain.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._vault_row({"document_name": "vault/a.md", "metadata": {}})
    assert mod._vault_row({"document_name": "a.md", "metadata": '{"source": "vault:a.md"}'})
    assert not mod._vault_row({"document_name": "a.md", "metadata": {"source": "upload"}})


def test_vault_setup_script_syntax_and_checks():
    script = ROOT / "scripts" / "vault-setup.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    src = script.read_text()
    assert "chmod 700" in src and ":/vault:ro" in src
    assert 'sudo -n -u "$u" ls "$VAULT_DIR"' in src            # the wall check
    assert "docker compose config -q" in src                    # edit validated, else restored
    assert "docker" in src and "gpasswd -d" in src              # closed users off the docker group
    assert "docker compose up" not in src.split("# ── 1.")[1].split("say \"done.")[0]  # never restarts


def test_export_sh_syntax():
    subprocess.run(["bash", "-n", str(ROOT / "scripts" / "export.sh")], check=True)


# ── B. the session mark ─────────────────────────────────────────────────────

def test_local_turn_marks_the_session(m, sent, readers, sdb):
    _chat_s(m, LOCAL_MODEL)
    assert SID in sdb.marked


def test_closed_turn_does_not_mark(m, sent, readers, sdb):
    _chat_s(m, CLOSED_MODELS[0])
    assert SID not in sdb.marked and sent


@pytest.mark.parametrize("model", CLOSED_MODELS)
def test_marked_session_never_reaches_a_closed_provider(m, sent, readers, sdb, model):
    from fastapi import HTTPException
    sdb.marked.add(SID)
    with pytest.raises(HTTPException) as e:
        _chat_s(m, model)
    assert e.value.status_code == 409
    assert e.value.detail["error"] == "session_local_only" and e.value.detail["offer"] == "new_session"
    assert sent == []  # nothing was sent anywhere


def test_marked_session_refused_for_local_model_off_the_list(m, sent, readers, sdb):
    from fastapi import HTTPException
    sdb.marked.add(SID)
    readers["v"] = ["qwen2.5:14b"]
    with pytest.raises(HTTPException):
        _chat_s(m, LOCAL_MODEL)
    assert sent == []


def test_marked_session_continues_on_an_allowed_local_model(m, sent, readers, sdb):
    sdb.marked.add(SID)
    _chat_s(m, LOCAL_MODEL)
    assert sent


def test_unmarked_and_unknown_sessions_unaffected(m, sent, readers, sdb):
    _chat_s(m, CLOSED_MODELS[0])
    _chat_s(m, CLOSED_MODELS[0], session_id="not-a-uuid")
    _chat_s(m, CLOSED_MODELS[0], session_id=None)
    assert len(sent) >= 3


def test_marked_session_db_error_fails_closed():
    class Boom:
        def cursor(self):
            raise RuntimeError("down")
    assert pv.session_is_marked(Boom(), SID) is True
    assert pv.session_is_marked(Boom(), "not-a-uuid") is False


def test_plain_chat_completions_refuses_marked_session(m, sent, readers, sdb):
    from fastapi import HTTPException
    sdb.marked.add(SID)
    req = {"model": "claude-opus-4-8", "session_id": SID, "permit_id": "p", "permit_token": "t",
           "messages": [{"role": "user", "content": "go on"}]}
    with pytest.raises(HTTPException) as e:
        _run(m.chat_completion(req, api_key="k"))
    assert e.value.status_code == 409 and sent == []


def test_consolidation_of_marked_session_refuses_closed_model(m, sent, readers, sdb, monkeypatch):
    from fastapi import HTTPException
    sdb.marked.add(SID)
    with pytest.raises(HTTPException) as e:
        _run(m.consolidate_session(SID, {"model": "claude-opus-4-8", "permit_id": "p", "permit_token": "t"}, api_key="k"))
    assert e.value.status_code == 409
    assert not any(SECRET in t for _m, t in sent)


def test_consolidation_of_marked_session_on_local_model_stores_local_only(m, sent, readers, sdb, monkeypatch):
    from api import substrate
    monkeypatch.setattr(substrate, "record_attestation_safe", lambda **kw: None)
    sdb.marked.add(SID)
    out = _run(m.consolidate_session(SID, {"permit_id": "p", "permit_token": "t"}, api_key="k"))
    assert out["privacy"] == "local-only"
    assert sdb.inserted and {md["privacy"] for md in sdb.inserted} == {"local-only"}
    assert {mdl for mdl, _t in sent} == {LOCAL_MODEL}


def test_consolidation_of_unmarked_session_unchanged(m, sent, readers, sdb, monkeypatch):
    from api import substrate
    monkeypatch.setattr(substrate, "record_attestation_safe", lambda **kw: None)
    out = _run(m.consolidate_session(SID, {"model": "claude-opus-4-8", "permit_id": "p", "permit_token": "t"}, api_key="k"))
    assert out["privacy"] == "open" and sent


def test_store_propose_refuses_closed_model_on_marked_session(m, sent, readers, sdb):
    from fastapi import HTTPException
    sdb.marked.add(SID)
    req = m.MemoryStoreProposeRequest(content=f"it says {SECRET}", model="gpt-4o", session_id=SID)
    with pytest.raises(HTTPException) as e:
        _run(m.memory_store_propose(req, api_key="k"))
    assert e.value.status_code == 409 and sent == []


def test_store_from_marked_session_is_local_only(m, readers, sdb, monkeypatch):
    sdb.marked.add(SID)
    monkeypatch.setattr(m, "_write_feedback", lambda *a, **k: None, raising=False)
    m.memory_store(m.MemoryStoreRequest(content="quote", session_id=SID, privacy="open"), api_key="k")
    assert sdb.inserted and {md["privacy"] for md in sdb.inserted} == {"local-only"}


def test_session_list_shows_the_mark():
    src = (ROOT / "api" / "main.py").read_text()
    assert "s.local_only_at" in src and '"local_only": len(session) > 6' in src
    ui = (ROOT / "ui" / "pages" / "chat.js").read_text()
    assert "s.local_only &&" in ui and "start a fresh session" in ui


class MigrateDB2:
    def __init__(self):
        self.indexes, self.columns, self.statements = set(), set(), []

    def cursor(self):
        db = self

        class C:
            def execute(self, sql, params=None):
                db.statements.append(sql)
                if "FROM pg_indexes" in sql:
                    self._r = (1,) if params[0] in db.indexes else None
                elif "information_schema.columns" in sql:
                    self._r = (1,) if params[0] in db.columns else None
                elif sql.startswith("CREATE INDEX IF NOT EXISTS"):
                    db.indexes.add(pv.INDEX_NAME); self._r = None
                elif sql.startswith("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS"):
                    db.columns.add(pv.SESSION_COLUMN); self._r = None
                else:
                    self._r = (0, 0, 0)

            def fetchone(self):
                return self._r

            def close(self):
                pass
        return C()

    def commit(self):
        pass


def test_session_mark_migration_is_idempotent():
    db = MigrateDB2()
    first, second = pv.migrate(db), pv.migrate(db)
    assert first["session_column_created"] is True and second["session_column_created"] is False
    alters = [s for s in db.statements if s.upper().startswith("ALTER")]
    assert alters == [pv.SESSION_COLUMN_SQL]  # once, and only ADD COLUMN IF NOT EXISTS
    assert not any(s.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT")) for s in db.statements)


def test_session_column_in_init_sql_and_startup():
    init_sql = " ".join((ROOT / "vector-db" / "init.sql").read_text().split())
    assert pv.SESSION_COLUMN_SQL + ";" in init_sql
    assert "cur.execute(_privacy.SESSION_COLUMN_SQL)" in (ROOT / "api" / "main.py").read_text()


# ── C. privacy on /memory/append ────────────────────────────────────────────

class AppendDB(FakeDB):
    def __init__(self, existing=()):
        super().__init__()
        self.existing = list(existing)
        self.inserted = []

    def cursor(self):
        db = self

        class C(FakeCursor):
            def execute(self, sql, params=None):
                flat = " ".join(sql.split())
                if flat.startswith("SELECT metadata FROM document_embeddings"):
                    self._result = [(md,) for md in db.existing]
                elif flat.startswith("INSERT INTO document_embeddings"):
                    db.inserted.append(json.loads(params[3]))
                    self._result = [(len(db.inserted),)]
                else:
                    self._result = []
        return C(db)


def _append(m, monkeypatch, db, **kw):
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    return m.memory_append(m.MemoryAppendRequest(layer="episodic", content="a note " * 20, source="poker-journal", **kw),
                           api_key="k")


def test_append_default_is_open(m, monkeypatch):
    db = AppendDB()
    out = _append(m, monkeypatch, db)
    assert out["privacy"] == "open" and {md["privacy"] for md in db.inserted} == {"open"}


def test_append_local_only(m, monkeypatch):
    db = AppendDB()
    out = _append(m, monkeypatch, db, privacy="local-only")
    assert out["privacy"] == "local-only" and {md["privacy"] for md in db.inserted} == {"local-only"}


def test_append_rejects_unknown_level(m, monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _append(m, monkeypatch, AppendDB(), privacy="secret")
    assert e.value.status_code == 400


def test_append_metadata_cannot_lower_the_level(m, monkeypatch):
    db = AppendDB()
    _append(m, monkeypatch, db, privacy="local-only", metadata={"privacy": "open"})
    assert {md["privacy"] for md in db.inserted} == {"local-only"}
    db = AppendDB()
    _append(m, monkeypatch, db, metadata={"privacy": "weird"})
    assert {md["privacy"] for md in db.inserted} == {"local-only"}


def test_append_stricter_wins_on_reappend(m, monkeypatch):
    db = AppendDB(existing=[{"privacy": "local-only"}])
    out = _append(m, monkeypatch, db, privacy="open")
    assert out["privacy"] == "local-only"
