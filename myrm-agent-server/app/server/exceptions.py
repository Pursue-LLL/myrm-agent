"""
[INPUT] app.schemas.responses::create_error_response, BusinessCode; app.middleware.observability::request_trace_id
[OUTPUT] not_found_handler, general_exception_handler
[POS] FastAPI 全局异常响应适配层，负责 404/500 标准错误体输出；500 的错误体与 X-Trace-Id 响应头携带请求的 trace id。
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from app.middleware.observability import request_trace_id
from app.schemas.responses import BusinessCode, create_error_response

logger = logging.getLogger(__name__)


async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        detail = exc.detail
        if "code" in detail and "message" in detail:
            return JSONResponse(status_code=404, content=detail)
    return JSONResponse(
        status_code=404,
        content=create_error_response(
            code=BusinessCode.RESOURCE_NOT_FOUND,
            message="Requested resource not found",
        ).model_dump(mode="json"),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, ClientDisconnect):
        raise exc
    # Starlette runs this handler outside TracingMiddleware: the context variable is already reset and the
    # middleware could not add its response header, so the id is read from the request it was stored on.
    trace_id = request_trace_id(request)
    logger.error("Unhandled exception for %s [trace=%s]", request.url.path, trace_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Internal server error",
            trace_id=trace_id,
        ).model_dump(mode="json"),
        headers={"X-Trace-Id": trace_id} if trace_id else None,
    )
