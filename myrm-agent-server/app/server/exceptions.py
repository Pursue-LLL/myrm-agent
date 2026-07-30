"""
[INPUT] app.database.standard_responses::create_error_response, BusinessCode
[OUTPUT] not_found_handler, general_exception_handler
[POS] FastAPI 全局异常响应适配层，负责 404/500 标准错误体输出。
"""

from __future__ import annotations

import logging
import traceback

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from app.database.standard_responses import BusinessCode, create_error_response

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
    print(f"!!! UNHANDLED EXCEPTION !!! {exc}")
    traceback.print_exc()
    logger.error(f"Unhandled exception for {request.url.path}: {exc}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content=create_error_response(
            code=BusinessCode.INTERNAL_ERROR,
            message="Internal server error",
        ).model_dump(mode="json"),
    )
