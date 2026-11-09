"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- register_exception_handlers

[POS]
API error utilities: the FastAPI exception handlers (register_exception_handlers).
"""

from __future__ import annotations

import traceback
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.schemas.responses import BusinessCode, create_error_response

from .base import MyrmError
from .constants import (
    logger,
)
from .redaction import redact_error_payload


def _memory_error_handler(status_code: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    """Answer a refused memory request with the error's caller-safe message under the ``detail`` contract.

    The request log keeps only the error type, never the memory content the message may describe.
    """

    async def handle(request: Request, exc: Exception) -> JSONResponse:
        logger.warning("[%s] memory request refused: %s", request.url.path, type(exc).__name__)
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handle


def register_exception_handlers(app: FastAPI) -> None:
    """Register global handlers that convert MyrmError into JSON responses.

    Must be called once during app startup.

    In debug mode (DEBUG=true), error responses include full stack traces
    for faster troubleshooting. In production, only structured error info is returned.
    """
    from myrm_agent_harness.toolkits.memory.manager import (
        MemoryNotFoundError,
        MemoryProtectedError,
        MemoryRejectedError,
        MemoryTaintedError,
    )

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

    # A refused memory request is the caller's to fix, never a 500. Writers that do not map these
    # themselves (profile/rule create, correction, conflict resolution, imports) share one contract.
    memory_error_status: dict[type[Exception], int] = {
        MemoryTaintedError: status.HTTP_400_BAD_REQUEST,  # the write scan rejected the content
        MemoryRejectedError: status.HTTP_400_BAD_REQUEST,  # the memory rules refuse the write
        MemoryProtectedError: status.HTTP_409_CONFLICT,  # the user protected this memory
        MemoryNotFoundError: status.HTTP_404_NOT_FOUND,  # the id is outside the caller's scope
    }
    for error_type, error_status in memory_error_status.items():
        app.add_exception_handler(error_type, _memory_error_handler(error_status))

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

    logger.info("✅ Global error handlers registered (MyrmError + memory errors + AttributeError + TypeError)")
