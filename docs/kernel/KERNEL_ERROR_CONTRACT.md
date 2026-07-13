# Kernel Error Contract (v1)

All API error responses MUST follow this canonical envelope:

{
  "ok": false,
  "error_version": 1,
  "error": {
    "code": "SOME_ERROR_CODE",
    "message": "Human-readable summary",
    "details": {}
  }
}

Rules:
- ok MUST be false
- error_version MUST be 1
- error.code MUST be a stable string from KernelErrorCode enum
- error.message MUST be non-empty string
- error.details MUST be an object (may be empty)
- Handlers MUST return JSONResponse(content=build_error(...).model_dump())
- No raw Pydantic models may be returned
- No ad-hoc error strings outside KernelErrorCode

HTTP mapping:
- 4xx → client mistakes
- 5xx → server faults

This file freezes the error interface.
