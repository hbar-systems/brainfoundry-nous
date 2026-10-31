"""
Memory-removal audit (api/memory_audit.py, 2026-10-31).

Pins the D75 finding from the revert drill: every removal from memory leaves a
line. Trash, restore, empty trash, governance forget and onboarding fact delete
each write one JSON line; empty trash names what it destroyed, so the record
outlives the rows. A failed action (404) writes nothing.

No Postgres: the database is a fake cursor with scripted rowcounts. The log path
is redirected to tmp via MEMORY_AUDIT_PATH. Imports api.main (same
full-dependency environment as test_memory_privacy).
"""
from __future__ import annotations

import asyncio
import importlib
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
os.environ.setdefault("BRAIN_RUNTIME_DIR", tempfile.mkdtemp(prefix="memaudit-runtime-"))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._result = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        self.db.statements.append(flat)
        if flat.startswith("DELETE") and "RETURNING document_name" in flat:
            # one row per deleted chunk, as Postgres returns them
            self._result = [(name,) for name, n in self.db.trashed for _ in range(n)]
            self.rowcount = len(self._result)
        elif flat.startswith(("UPDATE", "DELETE")):
            self.rowcount = self.db.rowcount
        else:
            self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class FakeDB:
    def __init__(self, rowcount=0, trashed=()):
        self.rowcount = rowcount
        self.trashed = list(trashed)
        self.statements = []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_AUDIT_PATH", str(tmp_path / "memory_audit.jsonl"))
    from api import memory_audit
    importlib.reload(memory_audit)
    return memory_audit


@pytest.fixture
def m(audit, monkeypatch):
    from api import main as _m
    return _m


def _db(m, monkeypatch, **kw):
    db = FakeDB(**kw)
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    return db


# ── module ──────────────────────────────────────────────────────────────────

def test_record_and_tail_roundtrip(audit):
    audit.record(action="trash", document_name="a.md", chunks=3)
    audit.record(action="empty_trash", document_name=None, chunks=4,
                 documents=[{"name": "a.md", "chunks": 3}, {"name": "b.md", "chunks": 1}])
    t, e = audit.tail(10)
    assert t["action"] == "trash" and t["chunks"] == 3 and t["actor"] == "operator"
    assert "before" not in t and "documents" not in t and t["ts"]
    assert e["document_name"] is None
    assert e["documents"] == [{"name": "a.md", "chunks": 3}, {"name": "b.md", "chunks": 1}]


def test_tail_empty_when_no_file(audit):
    assert audit.tail(5) == []


def test_unwritable_path_never_raises(tmp_path, monkeypatch, audit):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(audit, "MEMORY_AUDIT_PATH", blocker / "sub" / "log.jsonl")
    audit.record(action="trash", document_name="a.md", chunks=1)  # no exception


# ── endpoints ───────────────────────────────────────────────────────────────

def test_trash_writes_line(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=5)
    m.delete_document_by_name("notes/x.md", api_key="k")
    (line,) = audit.tail(5)
    assert line["action"] == "trash" and line["document_name"] == "notes/x.md"
    assert line["chunks"] == 5 and "before" not in line


def test_trash_before_records_cutoff(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=2)
    m.delete_document_by_name("notes/x.md", before="2026-10-31T10:00:00Z", api_key="k")
    assert audit.tail(1)[0]["before"] == "2026-10-31T10:00:00Z"


def test_trash_404_writes_nothing(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=0)
    with pytest.raises(HTTPException):
        m.delete_document_by_name("notes/none.md", api_key="k")
    assert audit.tail(5) == []


def test_restore_writes_line(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=4)
    m.restore_document("notes/x.md", api_key="k")
    (line,) = audit.tail(5)
    assert line["action"] == "restore" and line["chunks"] == 4


def test_empty_trash_names_what_it_destroyed(m, audit, monkeypatch):
    db = _db(m, monkeypatch, trashed=[("junk.txt", 4), ("a.md", 3)])
    out = m.empty_trash(api_key="k")
    assert out["chunks_deleted"] == 7
    # names come from the DELETE itself (RETURNING), not a separate read that
    # a concurrent trash could make stale
    assert len(db.statements) == 1 and "RETURNING document_name" in db.statements[0]
    (line,) = audit.tail(5)
    assert line["action"] == "empty_trash" and line["chunks"] == 7
    assert line["documents"] == [{"name": "a.md", "chunks": 3}, {"name": "junk.txt", "chunks": 4}]


def test_empty_trash_when_empty_writes_nothing(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=0, trashed=[])
    m.empty_trash(api_key="k")
    assert audit.tail(5) == []


def test_fact_delete_writes_line(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=1)
    m.onboarding_fact_delete("42", api_key="k")
    (line,) = audit.tail(5)
    assert line["action"] == "fact_delete" and line["document_name"] == "onboarding-fact/42"


def test_log_endpoint_returns_events(m, audit, monkeypatch):
    _db(m, monkeypatch, rowcount=1)
    m.restore_document("a.md", api_key="k")
    out = m.memory_audit_log(limit=10, api_key="k")
    assert out["limit"] == 10 and out["events"][-1]["action"] == "restore"


def test_log_route_not_shadowed(m):
    # the first GET route matching the path must be the log, not /documents/trash
    # or any other /documents route
    from starlette.routing import Match
    scope = {"type": "http", "method": "GET", "path": "/documents/trash/log",
             "root_path": "", "query_string": b"", "headers": []}
    for r in m.app.router.routes:
        match, _ = r.matches(scope)
        if match == Match.FULL:
            assert r.endpoint is m.memory_audit_log
            break
    else:
        pytest.fail("no route for GET /documents/trash/log")


def test_vault_prune_is_wired():
    # a source check: the vault scan needs a filesystem and DB stand-in that
    # tests/test_vault_privacy.py builds for privacy, not for prune
    from api import vault
    src = pathlib.Path(vault.__file__).read_text()
    assert src.count('_maudit.record(action="vault_prune"') == 1


def test_forget_command_writes_line(audit, monkeypatch):
    from api import hbar_commands as hc
    db = FakeDB(rowcount=2)
    monkeypatch.setattr(hc, "_db", lambda: db)
    out = asyncio.run(hc.handle_hbar_command(command="forget", payload={"id": "m1"}, client_id="c"))
    assert out["forgotten"] is True
    (line,) = audit.tail(5)
    assert line["action"] == "forget" and line["document_name"] == "memory/m1" and line["chunks"] == 2


def test_export_never_ships_the_log():
    from api import export
    assert "memory_audit.jsonl" in export._NEVER
