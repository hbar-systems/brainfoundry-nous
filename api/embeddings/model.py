from __future__ import annotations

import os
import threading
from typing import Optional

from sentence_transformers import SentenceTransformer

_lock = threading.Lock()
_model: Optional[SentenceTransformer] = None
_model_error: Optional[str] = None

def _model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-large-en-v1.5")

def is_model_loaded() -> bool:
    return _model is not None

def model_error() -> Optional[str]:
    return _model_error

# The embedding spoke (2026-09-23). The same OLLAMA_SPOKE_URL that serves local inference can
# serve the embedding model too (Ollama's `bge-large` is BAAI/bge-large-en-v1.5, the default
# here, 1024 dimensions, so nothing is re-indexed). While the spoke answers and lists
# EMBED_SPOKE_MODEL in its tags, encode() goes there; otherwise in-process, as before.
# EMBED_SPOKE=0 turns it off with one variable. The probe (GET /api/tags) is remembered for
# EMBED_SPOKE_PROBE_SECONDS. A vector that comes back with the wrong width, or any error,
# falls back to in-process for that call, so a call never fails because of the spoke.
EMBED_SPOKE_URL = os.environ.get("OLLAMA_SPOKE_URL", "").strip().rstrip("/")
EMBED_SPOKE_MODEL = os.environ.get("EMBED_SPOKE_MODEL", "bge-large")
EMBED_SPOKE_ON = os.environ.get("EMBED_SPOKE", "1").strip().lower() not in ("0", "false", "off", "no")
EMBED_SPOKE_PROBE_SECONDS = float(os.environ.get("EMBED_SPOKE_PROBE_SECONDS", "30"))
EMBED_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
_spoke = {"at": 0.0, "up": False, "used": 0, "fell_back": 0}


def spoke_serves_model(now: float | None = None, probe=None) -> bool:
    """Does the spoke answer and list the embedding model? Cached; `probe` injectable."""
    if not (EMBED_SPOKE_ON and EMBED_SPOKE_URL):
        return False
    import time as _t
    now = _t.time() if now is None else now
    if now - _spoke["at"] < EMBED_SPOKE_PROBE_SECONDS:
        return _spoke["up"]
    if probe is None:
        def probe():
            import requests as _req
            r = _req.get(f"{EMBED_SPOKE_URL}/api/tags", timeout=2)
            names = {m.get("name", "") for m in r.json().get("models", [])} if r.ok else set()
            return EMBED_SPOKE_MODEL in names or f"{EMBED_SPOKE_MODEL}:latest" in names
    try:
        up = bool(probe())
    except Exception:
        up = False
    if up != _spoke["up"]:
        print(f"[embed-spoke] {EMBED_SPOKE_URL} {'serves ' + EMBED_SPOKE_MODEL + ', embeddings go there' if up else 'not serving ' + EMBED_SPOKE_MODEL + ', embeddings in-process'}", flush=True)
    _spoke.update(at=now, up=up)
    return up


def spoke_encode(texts: list, post=None) -> list:
    """One POST /api/embed on the spoke. Raises on any problem; the caller falls back."""
    if post is None:
        def post(body):
            import requests as _req
            r = _req.post(f"{EMBED_SPOKE_URL}/api/embed", json=body, timeout=120)
            r.raise_for_status()
            return r.json()
    d = post({"model": EMBED_SPOKE_MODEL, "input": list(texts)})
    vecs = d.get("embeddings")
    if not isinstance(vecs, list) or len(vecs) != len(texts) or any(len(v) != EMBED_DIM for v in vecs):
        raise ValueError(f"spoke returned {len(vecs) if isinstance(vecs, list) else 'no'} vectors of the wrong shape")
    return [[float(x) for x in v] for v in vecs]


def encode_texts(texts: list) -> list:
    """Embeddings for a list of texts as lists of floats: the spoke while it serves the model,
    in-process otherwise. Every caller that stores or searches vectors goes through here."""
    if spoke_serves_model():
        try:
            out = spoke_encode(texts)
            _spoke["used"] += len(texts)
            return out
        except Exception as e:
            _spoke["fell_back"] += len(texts)
            print(f"[embed-spoke] fell back in-process for {len(texts)} texts: {type(e).__name__}: {e}", flush=True)
    return get_model().encode(list(texts)).tolist()


def spoke_status() -> dict:
    return {"url": EMBED_SPOKE_URL or None, "model": EMBED_SPOKE_MODEL, "on": EMBED_SPOKE_ON,
            "serving": spoke_serves_model() if (EMBED_SPOKE_ON and EMBED_SPOKE_URL) else None,
            "texts_embedded_there": _spoke["used"], "texts_fell_back": _spoke["fell_back"]}


def get_model() -> SentenceTransformer:
    global _model, _model_error

    if _model is not None:
        return _model

    with _lock:
        if _model is not None:
            return _model
        try:
            name = _model_name()
            _model = SentenceTransformer(name)
            _model_error = None
            return _model
        except Exception as e:
            _model = None
            _model_error = f"{type(e).__name__}: {e}"
            raise
