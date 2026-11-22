"""Suite-wide: the tests need no embedding model. When sentence_transformers is not
installed (a plain venv, no torch), stand in a stub so every file imports api.main the
same way alone or in the full run. The real package is used when present."""
import sys
import types

import pytest

if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        _st = types.ModuleType("sentence_transformers")
        _st.SentenceTransformer = object
        sys.modules["sentence_transformers"] = _st


# The whole-computer import caps a run at "free disk less a tenth of the disk" (api/laptop_survey.py).
# On a box over 90% full that cap is 0, every plan answers 413 and the agent.sh tests wait until their
# timeout, leaving agents polling (2026-11-22: 77 of them, load 30, the push gate red for a day).
# These two modules test the import, not the host's disk: give them a roomy, fixed disk.
@pytest.fixture(autouse=True)
def _roomy_disk_for_import_tests(request, monkeypatch):
    if request.module.__name__.rsplit(".", 1)[-1] in ("test_laptop_agent", "test_move_in_survey"):
        import collections
        import shutil
        du = collections.namedtuple("usage", "total used free")(500 * 1024 ** 3, 100 * 1024 ** 3, 400 * 1024 ** 3)
        monkeypatch.setattr(shutil, "disk_usage", lambda *_a, **_k: du)
    yield
