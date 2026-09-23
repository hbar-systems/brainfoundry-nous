"""Embedding spoke (api/embeddings/model.py): encode on the owner's machine while it serves
the model, in-process otherwise; wrong shapes and errors fall back. No network, no model.

Run from repo root:
    pytest tests/test_embed_spoke.py -v
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest


def _module(monkeypatch, spoke: str | None, on: str = "1"):
    # sentence_transformers is heavy and absent here: stub it, the tests never load a model
    st = types.ModuleType("sentence_transformers")
    class _ST:  # noqa: D401
        def __init__(self, name): self.name = name
        def encode(self, texts, **kw):
            import numpy as np
            return np.ones((len(texts), 1024)) * 0.5
    st.SentenceTransformer = _ST
    monkeypatch.setitem(sys.modules, "sentence_transformers", st)
    if spoke is None:
        monkeypatch.delenv("OLLAMA_SPOKE_URL", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_SPOKE_URL", spoke)
    monkeypatch.setenv("EMBED_SPOKE", on)
    monkeypatch.setenv("EMBED_SPOKE_MODEL", "bge-large")
    from api.embeddings import model as em
    return importlib.reload(em)


def test_no_spoke_in_process(monkeypatch):
    em = _module(monkeypatch, None)
    assert em.spoke_serves_model(probe=lambda: True) is False
    out = em.encode_texts(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 1024 and out[0][0] == 0.5


def test_spoke_serving_is_used(monkeypatch):
    em = _module(monkeypatch, "http://100.1.2.3:11434")
    em.spoke_serves_model(now=1000.0, probe=lambda: True)
    monkeypatch.setattr(em, "spoke_serves_model", lambda now=None, probe=None: True)
    monkeypatch.setattr(em, "spoke_encode", lambda texts, post=None: [[1.0] * 1024 for _ in texts])
    out = em.encode_texts(["a"])
    assert out[0][0] == 1.0 and em.spoke_status()["texts_embedded_there"] == 1


def test_switch_off_with_one_variable(monkeypatch):
    em = _module(monkeypatch, "http://100.1.2.3:11434", on="0")
    assert em.spoke_serves_model(probe=lambda: True) is False
    assert em.spoke_status()["on"] is False


def test_wrong_width_falls_back(monkeypatch):
    em = _module(monkeypatch, "http://100.1.2.3:11434")
    monkeypatch.setattr(em, "spoke_serves_model", lambda now=None, probe=None: True)
    with pytest.raises(ValueError):
        em.spoke_encode(["a"], post=lambda body: {"embeddings": [[0.1] * 768]})
    out = em.encode_texts(["a"])           # the real spoke_encode fails (no server): in-process
    assert out[0][0] == 0.5 and em.spoke_status()["texts_fell_back"] == 1


def test_spoke_encode_shape(monkeypatch):
    em = _module(monkeypatch, "http://100.1.2.3:11434")
    seen = {}
    def post(body):
        seen.update(body)
        return {"embeddings": [[0.25] * 1024, [0.75] * 1024]}
    out = em.spoke_encode(["x", "y"], post=post)
    assert seen == {"model": "bge-large", "input": ["x", "y"]}
    assert out[1][0] == 0.75 and len(out) == 2
