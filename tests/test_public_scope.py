"""One meaning of "public" (2026-10-20): api/public_scope.py and the doors that read it."""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st

os.environ.setdefault("BRAIN_IDENTITY_SECRET", "test-only-secret")
_RUNTIME = tempfile.mkdtemp(prefix="public-scope-test-")
os.environ.setdefault("BRAIN_RUNTIME_DIR", _RUNTIME)
os.environ.setdefault("SETTINGS_PATH", os.path.join(_RUNTIME, "settings.json"))

from api import ask  # noqa: E402
from api import main as m  # noqa: E402
from api import public_scope as ps  # noqa: E402

DOCS = [
    {"document_name": "a", "metadata": {"scope": "public"}},
    {"document_name": "b", "metadata": {"scope": "public", "privacy": "local-only"}},
    {"document_name": "c", "metadata": {"layer": "public"}},
    {"document_name": "d", "metadata": {"scope": "internal"}},
    {"document_name": "e", "metadata": None},
]


def test_is_public_needs_the_scope_and_open_privacy():
    assert [d["document_name"] for d in DOCS if ps.is_public(d["metadata"])] == ["a"]


def test_ask_door_uses_the_same_rule():
    assert [d["document_name"] for d in ask.public_only(DOCS)] == ["a"]


def test_layers_from_env():
    assert ps.layers_from_env(None) is None
    assert ps.layers_from_env("  ") is None
    assert ps.layers_from_env("semantic, public,") == ["semantic", "public"]


def test_sql_marks_only_open_public_layer_chunks_without_a_scope():
    for sql in (ps.MIGRATE_SQL, ps.TRIGGER_SQL):
        assert "'layer' = 'public'" in sql and "'scope' IS NULL" in sql and "'privacy', 'open') = 'open'" in sql


def test_ensure_runs_index_trigger_and_mark():
    class Cur:
        def __init__(self):
            self.sql, self.rowcount = [], 7

        def execute(self, s):
            self.sql.append(s)
    c = Cur()
    assert ps.ensure(c) == 7
    assert c.sql == [ps.INDEX_SQL, ps.TRIGGER_SQL, ps.MIGRATE_SQL]


def test_public_retrieve_asks_for_scope_public_and_drops_strays(monkeypatch):
    seen = {}

    def fake_search(query, limit=5, layers=None, architecture=None, scope=None, allow_local_only=False):
        seen.update(layers=layers, architecture=architecture, scope=scope, allow_local_only=allow_local_only)
        return DOCS
    monkeypatch.setattr(m, "search_similar_documents", fake_search)
    monkeypatch.delenv("PUBLIC_CHAT_LAYERS", raising=False)
    monkeypatch.setenv("PUBLIC_CHAT_SCOPE", "internal")            # no longer read
    assert [d["document_name"] for d in m._public_retrieve("q")] == ["a"]
    assert seen == {"layers": None, "architecture": "flat", "scope": "public", "allow_local_only": False}
    monkeypatch.setenv("PUBLIC_CHAT_LAYERS", "semantic")
    m._public_retrieve("q")
    assert seen["layers"] == ["semantic"] and seen["architecture"] is None and seen["scope"] == "public"
