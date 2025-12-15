from typing import Any
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Custom HTTP exception handler with standardized structure.

    Includes both FastAPI's conventional 'detail' field and a legacy 'error' key
    for backward compatibility with earlier clients.

    Preserves WWW-Authenticate header for 401 responses (RFC 7235 compliance).
    """
    # Preserve headers from the original exception (e.g., WWW-Authenticate for 401)
    headers = getattr(exc, "headers", None)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url),
        },
        headers=headers,
    )
