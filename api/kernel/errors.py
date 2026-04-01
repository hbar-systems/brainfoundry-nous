from typing import Optional, Dict, Any
from pydantic import BaseModel
from .error_codes import KernelErrorCode

class KernelError(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = {}


class KernelErrorResponse(BaseModel):
    ok: bool = False
    error_version: int = 1
    error: KernelError



def build_error(
    code: KernelErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> KernelErrorResponse:
    if not isinstance(code, KernelErrorCode):
        raise TypeError(f"build_error: code must be KernelErrorCode, got {type(code)}: {code!r}")
    code_str = code.value
    return KernelErrorResponse(
        error=KernelError(
            code=code_str,
            message=message,
            details=details or {},
        )
    )
