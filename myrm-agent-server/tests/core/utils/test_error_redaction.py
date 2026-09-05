"""
[INPUT] app.core.utils.errors::MyrmError, register_exception_handlers, StandardHTTPException
[OUTPUT] test_myrm_error_redaction, test_standard_http_exception_redaction
[POS] 验证全局异常处理在输出错误响应体时执行自动凭证脱敏，防止 API 密钥或敏感路径外泄。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.utils.errors import MyrmError, register_exception_handlers, validation_error
from app.schemas.responses import BusinessCode


@pytest.mark.asyncio
async def test_myrm_error_message_is_automatically_redacted() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-error")
    async def trigger_error() -> None:
        raise MyrmError(
            code=BusinessCode.AI_AUTH_ERROR,
            message="Connection failed with token sk-proj-1234567890abcdef123456",
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/trigger-error")
        assert response.status_code == 401
        data = response.json()
        assert "sk-proj-1234567890abcdef123456" not in data["message"]
        assert "sk-p" in data["message"] or "***" in data["message"]


@pytest.mark.asyncio
async def test_standard_http_exception_message_is_redacted() -> None:
    exc = validation_error("Invalid payload with token sk-ant-api03-abcdefghijklmnopqrstuvwxyz123")
    detail = exc.detail
    assert isinstance(detail, dict)
    assert "abcdefghijklmnopqrstuvwxyz123" not in detail["message"]
    assert "sk-ant" in detail["message"] or "***" in detail["message"]


@pytest.mark.asyncio
async def test_raw_http_exception_detail_is_automatically_redacted() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-raw-http")
    async def trigger_raw_http() -> None:
        raise HTTPException(
            status_code=400,
            detail="Failed to connect to host with secret token sk-proj-supersecret998877665544",
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/trigger-raw-http")
        assert response.status_code == 400
        data = response.json()
        assert "supersecret998877665544" not in data["message"]
        assert "sk-p" in data["message"] or "***" in data["message"]


@pytest.mark.asyncio
async def test_raw_http_exception_list_detail_is_automatically_redacted() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-list-http")
    async def trigger_list_http() -> None:
        raise HTTPException(
            status_code=422,
            detail=[
                {"loc": ["body", "token"], "msg": "Invalid token sk-proj-nestedlisttoken1234567890"},
                "Plain string error with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz",
            ],
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/trigger-list-http")
        assert response.status_code == 422
        data = response.json()
        assert "nestedlisttoken1234567890" not in data["message"]
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz" not in data["message"]


