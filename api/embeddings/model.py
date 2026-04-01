from __future__ import annotations

import os
import threading
from typing import Optional

from sentence_transformers import SentenceTransformer

_lock = threading.Lock()
_model: Optional[SentenceTransformer] = None
_model_error: Optional[str] = None

def _model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

def is_model_loaded() -> bool:
    return _model is not None

def model_error() -> Optional[str]:
    return _model_error

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
