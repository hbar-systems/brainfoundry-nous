"""Suite-wide: the tests need no embedding model. When sentence_transformers is not
installed (a plain venv, no torch), stand in a stub so every file imports api.main the
same way alone or in the full run. The real package is used when present."""
import sys
import types

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st
