"""[INPUT]
- myrm_agent_harness.toolkits.llms::create_chat_model (POS: myrm_agent_harness.toolkits.llms)
- myrm_agent_harness.toolkits.llms.utils.proxy::probe_proxy_health / validate_proxy_url (POS: Network utility module for proxy URL normalization, validation, security masking,)

[OUTPUT]
- TestLocalModelRequest: TestLocalModelRequest
- TestLocalModelResponse: TestLocalModelResponse
- _classify_local_model_error: Map internal exceptions to user-friendly connection test messages.
- test_local_model: Test connectivity to a local LLM (e.g. Ollama).
- TestProxyRequest: TestProxyRequest
- TestProxyResponse: TestProxyResponse
- test_proxy: Test outbound connectivity of an egress proxy.

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class TestLocalModelRequest(BaseModel):
    model: str
    base_url: str | None = None
    api_key: str | None = None


class TestLocalModelResponse(BaseModel):
    success: bool
    message: str
    latency_ms: int


# Stays below the 15 s request abort of the settings UI so a slow model is reported with a
# classified message instead of the page giving up first.
_LOCAL_MODEL_TEST_TIMEOUT_S = 12.0
# How the resolvers of Windows, macOS and Linux report a host name that does not exist.
_DNS_FAILURE_PHRASES = ("dns", "name resolution", "getaddrinfo", "nodename nor servname", "name or service not known")


def _classify_local_model_error(exc: Exception) -> str:
    """Map internal exceptions to user-friendly connection test messages."""
    if isinstance(exc, TimeoutError):
        # The request deadline expired without an answer: a model that is still loading is
        # indistinguishable from a wrong address, so the message names both.
        return (
            f"No response within {_LOCAL_MODEL_TEST_TIMEOUT_S:g} seconds"
            " — the model may still be loading, or check the server address"
        )
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "refused" in msg or "connectionrefused" in name:
        return "Connection refused — is the model server running?"
    if "timeout" in msg or "timed out" in msg or "timeout" in name:
        return "Connection timed out — check the server address"
    if "401" in msg or "unauthorized" in msg or "auth" in name:
        return "Authentication failed — check your API key"
    if "404" in msg or "not found" in msg:
        return "Model not found — check the model name"
    if any(phrase in msg for phrase in _DNS_FAILURE_PHRASES):
        return "DNS resolution failed — check the base URL"
    if "ssl" in msg or "certificate" in msg:
        return "SSL/TLS error — check your server's certificate"
    if isinstance(exc, httpx.ConnectError):
        # The HTTP client reports a refused connection as "All connection attempts failed" and says nothing more;
        # DNS and TLS failures are named above, so what is left is a server that is not there.
        return "Could not connect — is the model server running?"
    return "Connection test failed"


@router.post("/test-local-model", response_model=TestLocalModelResponse)
async def test_local_model(request: TestLocalModelRequest) -> TestLocalModelResponse:
    """Test connectivity to a local LLM (e.g. Ollama).

    Sends a minimal request to verify the model is reachable and responsive; the request is
    abandoned after ``_LOCAL_MODEL_TEST_TIMEOUT_S`` seconds.
    """
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.toolkits.llms import create_chat_model

    start = time.monotonic()
    try:
        llm = create_chat_model(
            model=request.model,
            base_url=request.base_url,
            api_key=request.api_key or "",
            temperature=0.0,
            streaming=False,
        )
        await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content="hi")]),
            timeout=_LOCAL_MODEL_TEST_TIMEOUT_S,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        return TestLocalModelResponse(success=True, message="OK", latency_ms=elapsed)
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning("Local model test failed: %s: %s", type(exc).__name__, exc)
        user_msg = _classify_local_model_error(exc)
        return TestLocalModelResponse(
            success=False,
            message=user_msg,
            latency_ms=elapsed,
        )


class TestProxyRequest(BaseModel):
    proxy_url: str = Field(..., description="Proxy URL to test (http, https, socks5, socks5h)")
    target_url: str | None = Field(default=None, description="Optional target URL to probe through proxy")


class TestProxyResponse(BaseModel):
    success: bool
    latency_ms: int | None = None
    error: str | None = None


@router.post("/test-proxy", response_model=TestProxyResponse)
async def test_proxy(request: TestProxyRequest) -> TestProxyResponse:
    """Test outbound connectivity of an egress proxy.

    Validates URL schema, credentials, and probes connectivity to target URL.
    """
    from myrm_agent_harness.toolkits.llms.utils.proxy import (
        probe_proxy_health,
        validate_proxy_url,
    )

    is_valid, err_msg = validate_proxy_url(request.proxy_url)
    if not is_valid:
        return TestProxyResponse(
            success=False,
            error=err_msg or "Invalid proxy URL",
        )

    target = (request.target_url or "").strip() or "https://1.1.1.1"
    start = time.monotonic()
    success, err_msg = await probe_proxy_health(
        proxy_url=request.proxy_url,
        target_url=target,
        timeout_s=5.0,
        cache_ttl_s=0.0,
    )
    elapsed = int((time.monotonic() - start) * 1000)

    return TestProxyResponse(
        success=success,
        latency_ms=elapsed if success else None,
        error=err_msg if not success else None,
    )
