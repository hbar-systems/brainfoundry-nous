# api/kernel/exceptions.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class KernelException(Exception):
    """
    Canonical exception type for kernel-safe errors.

    Anything that raises this MUST be returned in the canonical envelope.
    """
    code: str
    message: str
    status_code: int = 400
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

