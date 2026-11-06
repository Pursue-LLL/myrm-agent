"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- register_exception_handlers

[POS]
API error utilities: the FastAPI exception handlers (register_exception_handlers).
"""

from __future__ import annotations

import traceback

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.schemas.responses import BusinessCode, create_error_response

from .base import MyrmError
from .constants import (
    logger,
)
from .redaction import redact_error_payload


def register_exception_handlers(app: FastAPI) -> None:
    """Register global handlers that convert MyrmError into JSON responses.

    Must be called once during app startup.

    In debug mode (DEBUG=true), error responses include full stack traces
    for faster troubleshooting. In production, only structured error info is returned.
    """
    from myrm_agent_harness.toolkits.memory.manager import MemoryTaintedError

    from app.config.env import is_debug_mode

    @app.exception_handler(MyrmError)
    async def _handle_myrm_error(
        request: Request,
        exc: MyrmError,
    ) -> JSONResponse:
        path = request.url.path
        if exc.status_code >= 500:
            logger.error("[%s] MyrmError %s: %s", path, exc.code.name, exc.message)
        else:
            logger.warning("[%s] MyrmError %s: %s", path, exc.code.name, exc.message)

        safe_message = str(redact_error_payload(exc.message))
        body = create_error_response(
            code=exc.code,
            message=safe_message,
            details=exc.details,
        ).model_dump(mode="json")

        # In debug mode, append full traceback
        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)

        return JSONResponse(
            status_code=exc.status_code,
            content=body,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle raw HTTPException ensuring the whole detail payload is redacted.

        ``HTTPException`` is the legacy contract: the error payload stays in
        ``detail`` (a redacted string, list, or ``{"code", "message"}`` dict), which
        API tests and the frontend error parsers read. Only a detail that is already
        a full structured envelope (``{"code", "message"}``) is passed through
        unchanged. Callers wanting the canonical ``StandardErrorResponse`` envelope
        raise ``MyrmError`` / ``StandardHTTPException`` instead — those go through
        the dedicated handlers, so this handler never rewrites the envelope shape.
        """
        path = request.url.path
        if exc.status_code >= 500:
            logger.error("[%s] HTTPException %s: %s", path, exc.status_code, exc.detail)
        else:
            logger.warning("[%s] HTTPException %s: %s", path, exc.status_code, exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": redact_error_payload(exc.detail)},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(MemoryTaintedError)
    async def _handle_memory_tainted(request: Request, exc: MemoryTaintedError) -> JSONResponse:
        """A memory the write scan rejected is a client error, never a 500.

        Writers that do not map it themselves (profile/rule create, correction, conflict
        resolution, imports) all surface the same user-safe ``detail`` under the legacy contract.
        """
        logger.warning("[%s] memory write rejected by the security scan", request.url.path)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(AttributeError)
    async def _handle_attribute_error(request: Request, exc: AttributeError) -> JSONResponse:
        """Handle AttributeError (e.g., 'str' object has no attribute 'id')."""
        path = request.url.path
        logger.error(
            "[AttributeError] %s: %s\nTraceback:\n%s",
            path,
            exc,
            traceback.format_exc(),
        )

        body = create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Data type mismatch detected. Please contact support.",
        ).model_dump(mode="json")

        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
            body["exception_type"] = "AttributeError"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body,
        )

    @app.exception_handler(TypeError)
    async def _handle_type_error(request: Request, exc: TypeError) -> JSONResponse:
        """Handle TypeError (e.g., None is not subscriptable)."""
        path = request.url.path
        logger.error(
            "[TypeError] %s: %s\nTraceback:\n%s",
            path,
            exc,
            traceback.format_exc(),
        )

        body = create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Type error detected. Please contact support.",
        ).model_dump(mode="json")

        if is_debug_mode():
            body["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
            body["exception_type"] = "TypeError"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body,
        )

    logger.info("✅ Global error handlers registered (MyrmError + AttributeError + TypeError)")
