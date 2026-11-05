"""[OUTPUT]
verify endpoints.

[POS]
Connection verification and lightweight model reachability probing.
"""

from __future__ import annotations

import hashlib
import time
from typing import Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.types import ModelConfig
from app.core.utils.chat_utils import extract_answer_text
from app.core.utils.errors import handle_llm_exception
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.provider_oauth_tokens import resolve_oauth_marker

from .common import _apply_local_no_auth_marker_transport_overrides, router


class LLMVerifyRequest(ModelConfig):
    """LLM验证请求模型"""

    pass


class LLMVerifyData(BaseModel):
    """LLM验证数据模型"""

    model_name: str = Field(..., description="模型名称")


@router.post("/verify", response_model=StandardSuccessResponse)
async def verify_llm_connection(request: LLMVerifyRequest) -> JSONResponse:
    """
    验证LLM连接是否成功

    Args:
        request: 包含模型信息的请求体

    Returns:
        验证结果 (成功时) 或引发 HTTPException (失败时)
    """
    # 使用request的所有参数创建字典
    kwargs = request.model_dump(exclude_none=True)
    kwargs["model_kwargs"] = _apply_local_no_auth_marker_transport_overrides(
        kwargs.get("model_kwargs"),
        kwargs.get("api_key"),
    )

    try:
        from langchain_core.messages import HumanMessage
        from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools

        await resolve_oauth_marker(kwargs)
        llm = await llm_tools.get_llm(**kwargs)

        test_message = HumanMessage(content="Hello")
        result = await llm.ainvoke([test_message], config={"tags": ["connection_test"]})

        # reasoning 模型（DeepSeek-R1/Qwen3 等）content 可能为空但 reasoning_content 有值，
        # 需按统一提取结果判定，避免误报"连接失败"
        if result is None or not extract_answer_text(result):
            raise ValueError("LLM returned empty response content, verification failed")

        # 如果没有抛出异常且内容非空，说明连接成功
        data = LLMVerifyData(model_name=request.model)

        return success_response(data=data.model_dump())

    except Exception as e:
        # 使用统一的异常处理函数
        handle_llm_exception(e, "LLM connection verification failed")


class ReachabilityResult(BaseModel):
    """Model reachability check result."""

    reachable: bool = Field(..., description="Whether the model endpoint is reachable")
    latency_ms: int | None = Field(default=None, description="Round-trip latency in milliseconds")
    error: str | None = Field(default=None, description="Error message if unreachable")
    error_kind: Literal["none", "timeout", "provider_error"] = Field(
        default="none",
        description="Failure classification: 'timeout' when the probe deadline elapsed, 'provider_error' when the "
        "provider answered with an error, 'none' on success",
    )
    cached: bool = Field(default=False, description="Whether result came from cache")


_REACHABILITY_CACHE_TTL_S = 30.0


_REACHABILITY_PROBE_TIMEOUT_S = 15.0


_reachability_cache: dict[str, tuple[float, ReachabilityResult]] = {}


def _cache_key(request: LLMVerifyRequest) -> str:
    """Cache key of one reachability question: a digest of the whole request.

    A different API key, endpoint, proxy or model argument is a different question and has to be asked again; the digest
    keeps the key itself out of a dict that lives as long as the process.
    """
    return hashlib.blake2b(request.model_dump_json(exclude_none=True).encode(), digest_size=16).hexdigest()


@router.post("/check-reachability", response_model=StandardSuccessResponse)
async def check_model_reachability(request: LLMVerifyRequest) -> JSONResponse:
    """Lightweight model reachability check using a single minimal prompt.

    Faster and cheaper than /verify — uses ``probe_llm_health`` which sends one minimal prompt and gives up
    after its deadline. The failure is classified (``timeout`` vs ``provider_error``) and the upstream reason is
    preserved, so the caller can tell "the endpoint did not answer in time" apart from "the provider rejected
    the request" instead of reading a generic "no response".
    Results are cached for 30 seconds per identical request (model, endpoint, API key, proxy and model arguments)
    to avoid redundant probes.

    Useful for local model (Ollama) configuration to quickly verify
    that the endpoint is up before committing configuration changes.
    """
    key = _cache_key(request)
    now = time.monotonic()

    cached_entry = _reachability_cache.get(key)
    if cached_entry and (now - cached_entry[0]) < _REACHABILITY_CACHE_TTL_S:
        cached_result = cached_entry[1].model_copy(update={"cached": True})
        return success_response(data=cached_result.model_dump())

    kwargs = request.model_dump(exclude_none=True)
    kwargs["model_kwargs"] = _apply_local_no_auth_marker_transport_overrides(
        kwargs.get("model_kwargs"),
        kwargs.get("api_key"),
    )

    try:
        from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools
        from myrm_agent_harness.toolkits.llms.fallback.health_check import (
            lightweight_health_check,
        )

        await resolve_oauth_marker(kwargs)
        llm = await llm_tools.get_llm(**kwargs)

        try:
            from myrm_agent_harness.toolkits.llms.fallback.health_check import (
                probe_llm_health,
            )
        except ImportError:
            # Harness without the structured probe: fall back to the boolean probe so the endpoint keeps
            # working instead of failing the whole request on an import error.
            reachable = await lightweight_health_check(llm, timeout_s=_REACHABILITY_PROBE_TIMEOUT_S)
            result = ReachabilityResult(
                reachable=reachable,
                latency_ms=None,
                error=None if reachable else "Health check returned no response",
                error_kind="none" if reachable else "provider_error",
            )
        else:
            probe = await probe_llm_health(llm, timeout_s=_REACHABILITY_PROBE_TIMEOUT_S)
            result = ReachabilityResult(
                reachable=probe.ok,
                latency_ms=probe.latency_ms,
                error=probe.error,
                error_kind=probe.error_kind,
            )

    except Exception as e:
        result = ReachabilityResult(
            reachable=False,
            error=f"{type(e).__name__}: {e!s}"[:300],
            error_kind="provider_error",
        )

    _reachability_cache[key] = (time.monotonic(), result)
    return success_response(data=result.model_dump())
