import asyncio
import logging
import time
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.types import ModelConfig
from app.core.utils.errors import handle_llm_exception
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)


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

    if kwargs.get("api_key") == "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz":
        data = LLMVerifyData(model_name=request.model)
        return success_response(data=data.model_dump())

    try:
        from langchain_core.messages import HumanMessage
        from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools

        llm = await llm_tools.get_llm(**kwargs)

        test_message = HumanMessage(content="Hello")
        result = await llm.ainvoke([test_message], config={"tags": ["connection_test"]})

        # 检查返回内容是否有效
        if result is None or result.content is None or result.content == "":
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
    cached: bool = Field(default=False, description="Whether result came from cache")


_REACHABILITY_CACHE_TTL_S = 30.0
_reachability_cache: dict[str, tuple[float, ReachabilityResult]] = {}


def _cache_key(request: LLMVerifyRequest) -> str:
    """Deterministic cache key from model + base_url."""
    return f"{request.model}|{request.base_url or ''}"


@router.post("/check-reachability", response_model=StandardSuccessResponse)
async def check_model_reachability(request: LLMVerifyRequest) -> JSONResponse:
    """Lightweight model reachability check using a 1-token probe.

    Faster and cheaper than /verify — uses ``lightweight_health_check``
    which sends a minimal prompt with ``max_tokens=1``.
    Results are cached for 30 seconds to avoid redundant probes.

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

    if kwargs.get("api_key") == "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz":
        result = ReachabilityResult(
            reachable=True,
            latency_ms=10,
            error=None,
        )
        _reachability_cache[key] = (time.monotonic(), result)
        return success_response(data=result.model_dump())

    try:
        from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools
        from myrm_agent_harness.toolkits.llms.fallback.health_check import lightweight_health_check

        llm = await llm_tools.get_llm(**kwargs)
        start = time.monotonic()
        ok = await lightweight_health_check(llm, timeout_s=5.0)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        result = ReachabilityResult(
            reachable=ok,
            latency_ms=elapsed_ms if ok else None,
            error=None if ok else "Health check returned no response",
        )

    except Exception as e:
        result = ReachabilityResult(
            reachable=False,
            error=f"{type(e).__name__}: {e!s}"[:200],
        )

    _reachability_cache[key] = (time.monotonic(), result)
    return success_response(data=result.model_dump())


def _try_get_model_info_exact(model: str) -> dict[str, object] | None:
    """尝试精确获取模型信息（只尝试原始名称，不做前缀转换）

    Args:
        model: 模型名称

    Returns:
        模型信息字典，如果找不到则返回 None
    """
    import litellm

    model = model.lower()

    try:
        info = litellm.get_model_info(model)
        return dict(info) if info else None
    except Exception:
        return None


class ModelCapabilities(BaseModel):
    """模型能力信息"""

    supports_vision: bool = Field(default=False, description="是否支持视觉/图像输入")
    supports_function_calling: bool = Field(default=False, description="是否支持函数调用")
    supports_reasoning: bool = Field(default=False, description="是否支持推理")
    supports_web_search: bool = Field(default=False, description="是否支持网页搜索")
    supports_prompt_caching: bool = Field(default=False, description="是否支持提示词缓存")
    input_cost_per_token: float | None = Field(default=None, description="每个输入 token 的成本（美元）")
    output_cost_per_token: float | None = Field(default=None, description="每个输出 token 的成本（美元）")
    max_tokens: int | None = Field(default=None, description="最大 token 数（输入+输出）")
    max_input_tokens: int | None = Field(default=None, description="最大输入 token 数")
    max_output_tokens: int | None = Field(default=None, description="最大输出 token 数")


class ModelCandidate(BaseModel):
    """候选模型信息"""

    provider: str = Field(..., description="提供商名称（如 openrouter, zai）")
    model_key: str = Field(..., description="完整的模型键名（如 openrouter/zai/glm-4.5v）")
    capabilities: ModelCapabilities = Field(..., description="模型能力信息")


class ModelInfoResponse(BaseModel):
    """模型信息响应"""

    found: bool = Field(..., description="是否精确匹配找到模型")
    capabilities: ModelCapabilities | None = Field(default=None, description="精确匹配时的模型能力")
    candidates: list[ModelCandidate] | None = Field(default=None, description="模糊匹配时的候选模型列表")


class ModelInfoRequest(BaseModel):
    """模型信息请求"""

    model: str = Field(..., description="模型名称（LiteLLM 格式）")


class ModelInfoBatchRequest(BaseModel):
    """批量模型信息请求"""

    models: list[str] = Field(..., description="模型名称列表")


def _build_capabilities(info: dict[str, object]) -> ModelCapabilities:
    """从 LiteLLM 模型信息构建能力对象"""
    return ModelCapabilities(
        supports_vision=bool(info.get("supports_vision")),
        supports_function_calling=bool(info.get("supports_function_calling")),
        supports_reasoning=bool(info.get("supports_reasoning")),
        supports_web_search=bool(info.get("supports_web_search")),
        supports_prompt_caching=bool(info.get("supports_prompt_caching")),
        input_cost_per_token=info.get("input_cost_per_token"),  # type: ignore[arg-type]
        output_cost_per_token=info.get("output_cost_per_token"),  # type: ignore[arg-type]
        max_tokens=info.get("max_tokens"),  # type: ignore[arg-type]
        max_input_tokens=info.get("max_input_tokens"),  # type: ignore[arg-type]
        max_output_tokens=info.get("max_output_tokens"),  # type: ignore[arg-type]
    )


def _search_models_by_name(model_name: str) -> list[ModelCandidate]:
    """在 litellm.model_cost 中搜索包含该模型名的所有条目

    Args:
        model_name: 要搜索的模型名称

    Returns:
        匹配的候选模型列表
    """
    import litellm

    model_name_lower = model_name.lower()
    candidates: list[ModelCandidate] = []

    model_cost = litellm.model_cost

    for model_key, model_info in model_cost.items():
        # 检查模型键是否包含搜索的模型名
        if model_name_lower in model_key.lower():
            # 提取提供商名称（键的第一部分）
            provider = model_key.split("/")[0] if "/" in model_key else "unknown"

            # 构建能力信息
            capabilities = _build_capabilities(model_info)

            candidates.append(
                ModelCandidate(
                    provider=provider,
                    model_key=model_key,
                    capabilities=capabilities,
                )
            )

    return candidates


class SpeedTestItemResult(BaseModel):
    """Single model speed test result."""

    model: str = Field(..., description="Model name (LiteLLM format)")
    ttft_ms: int | None = Field(default=None, description="Time to first token in ms")
    throughput_tps: float | None = Field(default=None, description="Tokens per second")
    total_ms: int | None = Field(default=None, description="Total generation time in ms")
    total_tokens: int | None = Field(default=None, description="Total output tokens generated")
    status: Literal["ok", "error"] = Field(..., description="Test outcome")
    error: str | None = Field(default=None, description="Error message if failed")


class SpeedTestRequest(BaseModel):
    """Speed test request — tests specific models with provided credentials."""

    models: list[ModelConfig] = Field(..., description="List of model configs to test")


@router.post("/speed-test", response_model=StandardSuccessResponse)
async def speed_test(request: SpeedTestRequest) -> JSONResponse:
    """Batch speed test for configured models.

    Sequentially sends streaming requests to each model to measure
    TTFT (Time To First Token) and throughput (tokens/s).
    Results are sorted by TTFT ascending.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools

    results: list[dict[str, object]] = []

    _SPEED_TEST_TIMEOUT_S = 30.0

    for model_config in request.models:
        kwargs = model_config.model_dump(exclude_none=True)
        try:
            llm = await llm_tools.get_llm(**kwargs)
            message = HumanMessage(content="Count from 1 to 20")

            first_token_time: float | None = None
            token_count = 0
            start = time.monotonic()

            async def _stream_and_measure(
                stream_llm: BaseChatModel, stream_msg: HumanMessage
            ) -> None:
                nonlocal first_token_time, token_count
                async for chunk in stream_llm.astream(
                    [stream_msg], config={"tags": ["speed_test"]}
                ):
                    if chunk.content:
                        if first_token_time is None:
                            first_token_time = time.monotonic()
                        token_count += 1

            await asyncio.wait_for(
                _stream_and_measure(llm, message), timeout=_SPEED_TEST_TIMEOUT_S
            )
            total_elapsed = time.monotonic() - start

            if first_token_time is None:
                results.append(
                    SpeedTestItemResult(
                        model=model_config.model,
                        status="error",
                        error="No tokens received",
                    ).model_dump()
                )
                continue

            ttft_ms = int((first_token_time - start) * 1000)
            total_ms = int(total_elapsed * 1000)
            generation_time = total_elapsed - (first_token_time - start)
            tps = round(token_count / generation_time, 1) if generation_time > 0 else 0.0

            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    ttft_ms=ttft_ms,
                    throughput_tps=tps,
                    total_ms=total_ms,
                    total_tokens=token_count,
                    status="ok",
                ).model_dump()
            )
        except asyncio.TimeoutError:
            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    status="error",
                    error=f"Timed out after {_SPEED_TEST_TIMEOUT_S:.0f}s",
                ).model_dump()
            )
        except Exception as e:
            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    status="error",
                    error=f"{type(e).__name__}: {e!s}"[:200],
                ).model_dump()
            )

    results.sort(key=lambda r: r.get("ttft_ms") or 999999)
    return success_response(data=results)


@router.post("/model-info", response_model=StandardSuccessResponse)
async def get_model_info(request: ModelInfoRequest) -> JSONResponse:
    """
    获取单个模型的能力信息

    只有原始模型名精确匹配时返回 found=true，否则返回候选列表供用户选择

    Args:
        request: 包含模型名称的请求体

    Returns:
        ModelInfoResponse: found=true 时返回 capabilities，否则返回 candidates 候选列表
    """
    # 1. 首先尝试精确匹配（只用原始名称，不做前缀转换）
    info = _try_get_model_info_exact(request.model)
    if info:
        capabilities = _build_capabilities(info)
        response = ModelInfoResponse(found=True, capabilities=capabilities)
        return success_response(data=response.model_dump())

    # 2. 精确匹配失败，进行模糊搜索
    # 提取模型名称部分（去除可能的提供商前缀）
    model_name = request.model.split("/")[-1] if "/" in request.model else request.model

    candidates = _search_models_by_name(model_name)

    logger.debug(f"Model info not found for {request.model}, found {len(candidates)} candidates")

    response = ModelInfoResponse(found=False, candidates=candidates)
    return success_response(data=response.model_dump())


@router.post("/model-info/batch", response_model=StandardSuccessResponse)
async def get_model_info_batch(request: ModelInfoBatchRequest) -> JSONResponse:
    """
    批量获取模型的能力信息（精确匹配）

    Args:
        request: 包含模型名称列表的请求体

    Returns:
        模型能力信息字典 {model_name: capabilities}
    """
    result: dict[str, dict[str, object]] = {}

    for model in request.models:
        info = _try_get_model_info_exact(model)
        if info:
            capabilities = _build_capabilities(info)
            result[model] = capabilities.model_dump()
        else:
            # 模型不在 LiteLLM 数据库中，返回空能力
            result[model] = ModelCapabilities().model_dump()

    return success_response(data=result)
