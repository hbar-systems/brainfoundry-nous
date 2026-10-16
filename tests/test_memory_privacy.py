"""Memory privacy gate (api/privacy.py, 2026-10-14).

Pins the invariant: a `local-only` chunk is never retrieved for, put in a prompt
for, or sent to a closed reasoner (Anthropic, OpenAI, Groq, any hosted API); a
local Ollama reasoner on owner hardware does get it; unknown locality fails
closed; the default level is open; the migration is idempotent.

No Postgres, no model: the database is a fake cursor that applies the privacy
SQL clause the way Postgres would, and providers.complete is replaced by a
recorder, so a test can assert on every byte that would have reached a model.
Imports api.main (same full-dependency environment as test_public_chat_injection).
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from api import privacy as pv  # noqa: E402

SECRET = "SECRET-LOCAL-ONLY-diary-entry-7731"
OPEN_TEXT = "open note about the garden"

LOCAL_MODEL = "llama3.2:3b"
CLOSED_MODELS = ["claude-opus-4-8", "gpt-4o", "groq/llama-3.3-70b-versatile",
                 "openrouter/deepseek/deepseek-chat", "gemini-2.0-flash"]


# ── fake database ───────────────────────────────────────────────────────────

ROWS = [
    ("notes/garden.md", OPEN_TEXT, {"mem_type": "semantic"}, 0.10),
    ("notes/diary.md", SECRET, {"mem_type": "semantic", "privacy": "local-only"}, 0.05),
    ("notes/legacy.md", "legacy chunk with no metadata", None, 0.20),
    ("notes/odd.md", "SECRET-ODD-level", {"privacy": "LOCALISH"}, 0.15),
]


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._result = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        self.db.statements.append((sql, params))
        flat = " ".join(sql.split())
        if "embedding <->" in flat and flat.startswith("SELECT"):
            rows = list(self.db.rows)
            if "COALESCE(metadata->>'privacy', 'open') = 'open'" in flat:
                rows = [r for r in rows if (r[2] or {}).get("privacy", "open") == "open"]
            self._result = rows
        else:
            self._result = []

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class FakeDB:
    def __init__(self, rows=ROWS):
        self.rows = rows
        self.statements = []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def m(monkeypatch, tmp_path):
    from api import main as _m
    from api import providers as _p
    from api import settings_store as _ss
    db = FakeDB()
    monkeypatch.setattr(_m, "get_db_connection", lambda: db)
    monkeypatch.setattr(_m, "generate_embeddings", lambda texts: [[0.0] * 4 for _ in texts])
    # No network: the local Ollama has no tags, so routing is by name.
    monkeypatch.setattr(_p, "_local_ollama_models", lambda: set())
    monkeypatch.setattr(_p, "OLLAMA_URL", "http://ollama:11434")
    monkeypatch.setattr(_p, "OLLAMA_SPOKE_URL", "")
    monkeypatch.setattr(_ss, "get_retrieval_architecture", lambda: "flat")
    monkeypatch.setattr(_ss, "get_agentic_tools_enabled", lambda: False)
    monkeypatch.setattr(_ss, "get_web_search_enabled", lambda: False)
    monkeypatch.setattr(_ss, "get_mind_panel_shown", lambda: False)
    monkeypatch.setattr(_m, "_onboarding_active", lambda: False)
    monkeypatch.setattr(_m, "_persist_chat_turn", lambda *a, **k: None)
    _m._test_db = db
    return _m


@pytest.fixture
def sent(monkeypatch):
    """Record every (model, text) that would have gone to any reasoner."""
    from api import providers as _p
    calls = []

    async def fake_complete(model, messages, max_tokens=2048):
        calls.append((model, json.dumps(messages)))
        return "ok"

    async def fake_stream(model, messages, max_tokens=2048):
        calls.append((model, json.dumps(messages)))
        yield "ok"

    monkeypatch.setattr(_p, "complete", fake_complete)
    monkeypatch.setattr(_p, "stream", fake_stream)
    return calls


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── levels ──────────────────────────────────────────────────────────────────

def test_default_level_is_open():
    assert pv.normalize_level(None) == pv.OPEN
    assert pv.normalize_level("") == pv.OPEN
    assert pv.level_of(None) == pv.OPEN
    assert pv.level_of({}) == pv.OPEN
    assert pv.level_of({"privacy": "open"}) == pv.OPEN


def test_levels_normalise_and_reject_unknown():
    assert pv.normalize_level("Local-Only") == pv.LOCAL_ONLY
    assert pv.normalize_level("local_only") == pv.LOCAL_ONLY
    with pytest.raises(ValueError):
        pv.normalize_level("secret")


def test_unknown_stored_level_is_treated_as_local_only():
    assert pv.level_of({"privacy": "LOCALISH"}) == pv.LOCAL_ONLY
    assert pv.filter_docs([{"metadata": {"privacy": "weird"}}], False) == []


# ── locality of a reasoner ──────────────────────────────────────────────────

def _res(kind):
    return lambda model: (kind, None, model)


def test_box_ollama_is_local():
    assert pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"),
                                ollama_urls=["http://ollama:11434"])


def test_tailnet_spoke_is_local():
    for url in ("http://100.101.7.3:11434", "http://laptop.tail1234.ts.net:11434",
                "http://192.168.1.20:11434", "http://localhost:11434"):
        assert pv.reasoner_is_local("qwen2.5:14b", resolve=_res("ollama"),
                                    ollama_urls=["http://ollama:11434", url]), url


def test_closed_providers_are_not_local():
    for kind in ("anthropic", "openai_compat"):
        assert not pv.reasoner_is_local("x", resolve=_res(kind),
                                        ollama_urls=["http://ollama:11434"])


def test_ollama_on_a_public_host_is_not_local():
    assert not pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"),
                                    ollama_urls=["https://ollama.example.com"])
    # one public endpoint among the candidates is enough to fail closed
    assert not pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"),
                                    ollama_urls=["http://ollama:11434", "http://8.8.8.8:11434"])


def test_owner_can_vouch_for_a_host(monkeypatch):
    monkeypatch.setenv("PRIVACY_LOCAL_HOSTS", "gpu.myhome.example")
    assert pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"),
                                ollama_urls=["http://gpu.myhome.example:11434"])


def test_ollama_cloud_models_are_not_local():
    for model in ("gpt-oss:120b-cloud", "deepseek-v3.1:671b-cloud", "qwen3-coder:cloud"):
        assert not pv.reasoner_is_local(model, resolve=_res("ollama"),
                                        ollama_urls=["http://ollama:11434"]), model


def test_unknown_locality_fails_closed():
    def boom(model):
        raise RuntimeError("cannot resolve")
    assert not pv.reasoner_is_local("mystery", resolve=boom, ollama_urls=["http://ollama:11434"])
    assert not pv.reasoner_is_local(None)
    assert not pv.reasoner_is_local("")
    assert not pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"), ollama_urls=[])
    assert not pv.reasoner_is_local("llama3.2:3b", resolve=_res("ollama"), ollama_urls=["not a url"])


def test_real_provider_routing(m):
    for model in CLOSED_MODELS:
        assert not pv.reasoner_is_local(model), model
    assert pv.reasoner_is_local(LOCAL_MODEL)


# ── retrieval ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arch", ["flat", "layer_scoped", "tiered"])
def test_search_default_is_closed_view(m, arch):
    layers = ["notes"] if arch == "layer_scoped" else None
    docs = m.search_similar_documents("q", limit=10, layers=layers, architecture=arch)
    text = json.dumps(docs)
    assert SECRET not in text and "SECRET-ODD" not in text
    assert OPEN_TEXT in text and "legacy chunk" in text
    # filtered in SQL: every similarity query carried the clause
    sims = [s for s, _ in m._test_db.statements if "embedding <->" in s]
    assert sims and all(pv.SQL_OPEN_ONLY.strip(" AND") in " ".join(s.split()) for s in sims)


def test_search_local_view_includes_local_only(m):
    docs = m.search_similar_documents("q", limit=10, architecture="flat", allow_local_only=True)
    assert SECRET in json.dumps(docs)


def test_python_filter_backs_up_sql(m):
    # Even if the database ignored the clause, the closed view drops the chunk.
    m._test_db.rows = ROWS
    orig = FakeCursor.execute

    def no_filter(self, sql, params=None):
        orig(self, sql.replace("COALESCE(metadata->>'privacy', 'open') = 'open'", "TRUE"), params)
    FakeCursor.execute = no_filter
    try:
        docs = m.search_similar_documents("q", limit=10, architecture="flat")
    finally:
        FakeCursor.execute = orig
    assert SECRET not in json.dumps(docs)


def test_rag_prompt_for_closed_model_has_no_local_only(m):
    for model in CLOSED_MODELS:
        prompt, docs = m._build_rag_prompt([{"role": "user", "content": "q"}], "q", None, 5, model=model)
        assert SECRET not in prompt and SECRET not in json.dumps(docs), model
        assert OPEN_TEXT in prompt


def test_rag_prompt_for_local_model_includes_local_only(m):
    prompt, _ = m._build_rag_prompt([{"role": "user", "content": "q"}], "q", None, 5, model=LOCAL_MODEL)
    assert SECRET in prompt


def test_rag_prompt_unknown_model_fails_closed(m, monkeypatch):
    from api import providers as _p
    monkeypatch.setattr(_p, "_resolve", lambda model: (_ for _ in ()).throw(RuntimeError("x")))
    prompt, _ = m._build_rag_prompt([{"role": "user", "content": "q"}], "q", None, 5, model="whatever")
    assert SECRET not in prompt


# ── /chat/rag end to end ────────────────────────────────────────────────────

def _chat(m, model, permit=None):
    req = {"model": model, "messages": [{"role": "user", "content": "what is in my diary?"}]}
    if permit:
        req.update(permit_id="p", permit_token="t")
    return _run(m.rag_chat_completion(req, http_request=None, api_key="k"))


@pytest.mark.parametrize("model", CLOSED_MODELS)
def test_closed_reasoner_never_receives_local_only(m, sent, model):
    out = _chat(m, model)
    assert sent, "the model was called"
    for _model, text in sent:
        assert SECRET not in text
    assert "notes/diary.md" not in out["rag_metadata"]["sources"]


def test_local_reasoner_receives_local_only(m, sent):
    out = _chat(m, LOCAL_MODEL)
    assert any(SECRET in text for _model, text in sent)
    assert "notes/diary.md" in out["rag_metadata"]["sources"]
    # the corroboration pass ran on the SAME local model, not the default one
    assert {mdl for mdl, _ in sent} == {LOCAL_MODEL}


def test_brain_app_llm_complete_gets_open_view_even_on_local_model(m, sent, monkeypatch):
    monkeypatch.setattr(m, "_verify_loop_permit", lambda pid, tok: {"agent_id": "app:poker-journal"})
    _chat(m, LOCAL_MODEL, permit=True)
    for _model, text in sent:
        assert SECRET not in text


def test_operator_ui_permit_keeps_local_view(m, sent, monkeypatch):
    monkeypatch.setattr(m, "_verify_loop_permit", lambda pid, tok: {"agent_id": "ui"})
    _chat(m, LOCAL_MODEL, permit=True)
    assert any(SECRET in text for _model, text in sent)


def test_mind_extraction_skips_closed_model_after_local_only_turn(m, sent, monkeypatch):
    from api import providers as _p
    from api import settings_store as _ss
    monkeypatch.setattr(_ss, "get_mind_panel_shown", lambda: True)
    monkeypatch.setattr(_p, "cheap_extraction_model", lambda: "claude-haiku-4-5")
    out = _run(m._maybe_extract_mind_facts("q", f"your diary says {SECRET}", used_local_only=True))
    assert out is None
    assert not any(SECRET in text for _model, text in sent)


# ── other model-feeding paths ───────────────────────────────────────────────

def test_search_memory_tool_defaults_closed_and_follows_turn(m):
    from api.tools import memory_search
    assert SECRET not in memory_search.run("diary").content
    tok = pv.set_turn_allows_local_only(True)
    try:
        assert SECRET in memory_search.run("diary").content
    finally:
        pv.reset_turn(tok)
    assert SECRET not in memory_search.run("diary").content


def test_telegram_answer_gets_open_view_even_on_local_model(m, sent, monkeypatch):
    from api import providers as _p
    from api.integrations import telegram
    monkeypatch.setattr(_p, "default_model", lambda: LOCAL_MODEL)
    _run(telegram.answer("what is in my diary?"))
    assert sent and not any(SECRET in text for _model, text in sent)


def test_documents_search_excludes_local_only_unless_asked(m):
    out = m.search_documents({"query": "diary", "limit": 10}, api_key="k")
    assert SECRET not in json.dumps(out)
    out = m.search_documents({"query": "diary", "limit": 10, "include_local_only": True}, api_key="k")
    assert SECRET in json.dumps(out)


# ── setting the level ───────────────────────────────────────────────────────

class IngestCursor:
    def __init__(self, db):
        self.db = db
        self._result = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        flat = " ".join(sql.split())
        self.db.statements.append((flat, params))
        if flat.startswith("SELECT id, content, metadata FROM document_embeddings"):
            self._result = self.db.existing
        else:
            self._result = []
        if flat.startswith("UPDATE document_embeddings"):
            self.rowcount = self.db.update_rowcount

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0] if self._result else None

    def close(self):
        pass


class IngestDB(FakeDB):
    def __init__(self, existing=(), update_rowcount=0):
        super().__init__()
        self.existing = list(existing)
        self.update_rowcount = update_rowcount

    def cursor(self):
        return IngestCursor(self)

    def inserted_privacy(self):
        return [json.loads(p[3]).get("privacy") for s, p in self.statements if s.startswith("INSERT")]


def _ingest(m, monkeypatch, db, privacy=None):
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    events = list(m._stream_ingest_path_b(
        text="alpha beta gamma " * 50, filename="notes/new.md", content_type="text/plain",
        size=10, proposal_id="prop-1", layer=None, privacy=privacy))
    assert any(e.startswith("event: done") for e in events), events
    return db


def test_upload_default_is_open(m, monkeypatch):
    db = _ingest(m, monkeypatch, IngestDB())
    assert db.inserted_privacy() and set(db.inserted_privacy()) == {"open"}


def test_upload_local_only(m, monkeypatch):
    db = _ingest(m, monkeypatch, IngestDB(), privacy="local-only")
    assert set(db.inserted_privacy()) == {"local-only"}


def test_reupload_without_choice_keeps_local_only(m, monkeypatch):
    db = _ingest(m, monkeypatch, IngestDB(existing=[(1, "old text", {"privacy": "local-only"})]))
    assert set(db.inserted_privacy()) == {"local-only"}


def test_upload_rejects_unknown_level(m):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _run(m.upload_document(file=None, proposal_id=None, permit_id=None, layer=None,
                               privacy="top-secret", api_key="k"))
    assert e.value.status_code == 400


def test_set_document_privacy_endpoint(m, monkeypatch):
    from fastapi import HTTPException
    db = IngestDB(update_rowcount=3)
    monkeypatch.setattr(m, "get_db_connection", lambda: db)
    out = m.set_document_privacy("notes/diary.md", {"privacy": "local-only"}, api_key="k")
    assert out == {"document_name": "notes/diary.md", "privacy": "local-only", "chunks_updated": 3}
    sql, params = db.statements[-1]
    assert sql.startswith("UPDATE document_embeddings") and params == ("local-only", "notes/diary.md")
    with pytest.raises(HTTPException) as e:
        m.set_document_privacy("notes/diary.md", {"privacy": "nope"}, api_key="k")
    assert e.value.status_code == 400
    db.update_rowcount = 0
    with pytest.raises(HTTPException) as e:
        m.set_document_privacy("missing.md", {"privacy": "open"}, api_key="k")
    assert e.value.status_code == 404


# ── migration ───────────────────────────────────────────────────────────────

class MigrateDB:
    """pg_indexes + document_embeddings, just enough for privacy.migrate."""

    def __init__(self):
        self.indexes = set()
        self.statements = []

    def cursor(self):
        db = self

        class C:
            def execute(self, sql, params=None):
                db.statements.append(sql)
                if "FROM pg_indexes" in sql:
                    self._r = (1,) if params[0] in db.indexes else None
                elif sql.startswith("CREATE INDEX IF NOT EXISTS"):
                    db.indexes.add(pv.INDEX_NAME)
                    self._r = None
                else:
                    self._r = (2, 1, 10)

            def fetchone(self):
                return self._r

            def close(self):
                pass
        return C()

    def commit(self):
        pass


def test_migration_is_idempotent():
    db = MigrateDB()
    first = pv.migrate(db)
    second = pv.migrate(db)
    assert first["index_created"] is True
    assert second["index_created"] is False
    assert second["local_only_chunks"] == 2 and second["unknown_level_chunks"] == 1
    # it never rewrites a row
    assert not any(s.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT", "ALTER"))
                   for s in db.statements)


def test_init_sql_and_startup_carry_the_same_index():
    init_sql = " ".join((ROOT / "vector-db" / "init.sql").read_text().split())
    assert " ".join(pv.INDEX_SQL.split()) in init_sql
    main_src = (ROOT / "api" / "main.py").read_text()
    assert "cur.execute(_privacy.INDEX_SQL)" in main_src
