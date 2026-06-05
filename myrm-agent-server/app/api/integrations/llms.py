import asyncio
import logging
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
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


class HardwareRecommendationResponse(BaseModel):
    """硬件推荐响应"""

    hardware_detected: bool = Field(..., description="是否成功检测到硬件")
    os_type: str | None = Field(default=None, description="操作系统类型")
    cpu_arch: str | None = Field(default=None, description="CPU架构")
    total_ram_gb: float | None = Field(default=None, description="总内存(GB)")
    has_gpu: bool | None = Field(default=None, description="是否有GPU")
    gpu_name: str | None = Field(default=None, description="GPU名称")
    gpu_vram_gb: float | None = Field(default=None, description="GPU显存(GB)")
    is_unified_memory: bool | None = Field(default=None, description="是否为统一内存(如Apple Silicon)")

    ollama_running: bool = Field(default=False, description="本地 Ollama 是否正在运行")
    recommendations: list[dict[str, object]] = Field(default_factory=list, description="推荐模型列表")


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

            async def _stream_and_measure(stream_llm: BaseChatModel, stream_msg: HumanMessage) -> None:
                nonlocal first_token_time, token_count
                async for chunk in stream_llm.astream([stream_msg], config={"tags": ["speed_test"]}):
                    if chunk.content:
                        if first_token_time is None:
                            first_token_time = time.monotonic()
                        token_count += 1

            await asyncio.wait_for(_stream_and_measure(llm, message), timeout=_SPEED_TEST_TIMEOUT_S)
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


_HARDWARE_PROFILE_CACHE: tuple[float, object] | None = None
_HARDWARE_PROFILE_LOCK = asyncio.Lock()

_MODEL_SPECS_CACHE: tuple[float, list[dict[str, object]]] | None = None
_MODEL_SPECS_LOCK = asyncio.Lock()

_FALLBACK_MODEL_SPECS = [
    {
        "id": "ollama/qwen2.5:0.5b",
        "name": "Qwen 2.5 (0.5B)",
        "description": "极速响应，适合简单任务和低配机器",
        "req_vram_gb": 1.5,
        "params_b": 0.5,
    },
    {
        "id": "ollama/qwen2.5:3b",
        "name": "Qwen 2.5 (3B)",
        "description": "速度与能力的良好平衡，适合主流轻薄本",
        "req_vram_gb": 3.0,
        "params_b": 3.0,
    },
    {
        "id": "ollama/llama3.2:8b",
        "name": "Llama 3.2 (8B)",
        "description": "强大的通用模型，适合主流开发机",
        "req_vram_gb": 6.0,
        "params_b": 8.0,
    },
    {
        "id": "ollama/qwen2.5:14b",
        "name": "Qwen 2.5 (14B)",
        "description": "极强的推理能力，适合高配工作站",
        "req_vram_gb": 10.0,
        "params_b": 14.0,
    },
    {
        "id": "ollama/deepseek-r1:32b",
        "name": "DeepSeek R1 (32B)",
        "description": "专家级推理模型，需要顶级硬件",
        "req_vram_gb": 22.0,
        "params_b": 32.0,
    },
    {
        "id": "ollama/llama3.1:70b",
        "name": "Llama 3.1 (70B)",
        "description": "超大规模模型，仅限顶级工作站",
        "req_vram_gb": 40.0,
        "params_b": 70.0,
    },
]


async def _get_cached_hardware_profile() -> object | None:
    """获取硬件探针结果（带内存缓存，避免阻塞事件循环）"""
    global _HARDWARE_PROFILE_CACHE
    now = time.monotonic()

    if _HARDWARE_PROFILE_CACHE and (now - _HARDWARE_PROFILE_CACHE[0]) < 3600.0:
        return _HARDWARE_PROFILE_CACHE[1]

    async with _HARDWARE_PROFILE_LOCK:
        if _HARDWARE_PROFILE_CACHE and (now - _HARDWARE_PROFILE_CACHE[0]) < 3600.0:
            return _HARDWARE_PROFILE_CACHE[1]

        from myrm_agent_harness.runtime.maintenance import detect_hardware_profile

        # 在线程池中执行同步的探针函数，避免阻塞 FastAPI
        profile = await asyncio.to_thread(detect_hardware_profile)
        _HARDWARE_PROFILE_CACHE = (now, profile)
        return profile


async def _get_dynamic_model_specs() -> list[dict[str, object]]:
    """动态拉取模型规格字典（带本地 Fallback）"""
    global _MODEL_SPECS_CACHE
    now = time.monotonic()

    if _MODEL_SPECS_CACHE and (now - _MODEL_SPECS_CACHE[0]) < 3600.0:
        return _MODEL_SPECS_CACHE[1]

    async with _MODEL_SPECS_LOCK:
        if _MODEL_SPECS_CACHE and (now - _MODEL_SPECS_CACHE[0]) < 3600.0:
            return _MODEL_SPECS_CACHE[1]

        specs = _FALLBACK_MODEL_SPECS
        try:
            # 尝试从云端拉取，设置 3 秒超时
            # async with httpx.AsyncClient(timeout=3.0) as client:
            #     # TODO: 替换为真实的云端 URL，目前演示使用 Fallback
            #     response = await client.get("https://raw.githubusercontent.com/yululiu/open-perplexity/main/cookbook_specs.json")
            #     if response.status_code == 200:
            #         specs = response.json()
            pass
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic model specs, using fallback: {e}")

        _MODEL_SPECS_CACHE = (now, specs)
        return specs


async def _get_ollama_status() -> tuple[bool, list[str]]:
    """探测 Ollama 状态并获取已安装模型列表"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get("http://localhost:11434/api/tags")
            if res.status_code == 200:
                data = res.json()
                models = [m.get("name") for m in data.get("models", []) if "name" in m]
                return True, models
    except Exception:
        pass
    return False, []


class OllamaPullRequest(BaseModel):
    model_name: str = Field(..., description="Ollama 模型名称，例如 qwen2.5:0.5b")


@router.post("/hardware/ollama/pull")
async def pull_ollama_model(request: OllamaPullRequest) -> StreamingResponse:
    """代理 Ollama 的 /api/pull 接口，返回流式进度"""
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    if get_deploy_mode() == DeployMode.SANDBOX:
        raise HTTPException(status_code=403, detail="Not available in SaaS mode")

    async def _stream_pull():
        try:
            # 使用 httpx 流式请求代理 Ollama
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", "http://localhost:11434/api/pull", json={"name": request.model_name}
                ) as response:
                    if response.status_code != 200:
                        yield f'{{"error": "Ollama returned status {response.status_code}"}}\n'.encode("utf-8")
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception as e:
            yield f'{{"error": "{str(e)}"}}\n'.encode("utf-8")

    return StreamingResponse(_stream_pull(), media_type="application/x-ndjson")


@router.get("/hardware/recommendations", response_model=StandardSuccessResponse)
async def get_hardware_recommendations() -> JSONResponse:
    """
    获取基于本地硬件的模型推荐 (Fit Score)

    在 SaaS 模式下，或硬件检测失败时，返回 hardware_detected=False
    """
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    # 1. 如果是 SaaS 模式，直接返回未检测（云端硬件对用户无意义）
    if get_deploy_mode() == DeployMode.SANDBOX:
        return success_response(data=HardwareRecommendationResponse(hardware_detected=False).model_dump())

    # 2. 调用异步缓存的探针获取物理硬件信息
    profile = await _get_cached_hardware_profile()
    if not profile:
        return success_response(data=HardwareRecommendationResponse(hardware_detected=False).model_dump())

    # 3. 动态获取模型规格字典
    model_specs = await _get_dynamic_model_specs()

    # 4. 探测 Ollama 状态
    is_ollama_running, installed_models = await _get_ollama_status()

    # 5. 计算可用显存上限
    available_vram = 0.0
    if getattr(profile, "is_unified_memory", False):
        available_vram = max(0.0, getattr(profile, "total_ram_gb", 0.0) - 4.0)
    elif getattr(profile, "has_gpu", False) and getattr(profile, "gpu_vram_gb", None):
        available_vram = getattr(profile, "gpu_vram_gb", 0.0)
    else:
        available_vram = getattr(profile, "total_ram_gb", 0.0) * 0.5

    # 6. 计算 Fit Score 和推荐列表
    recommendations = []
    for spec in model_specs:
        req_vram = float(spec["req_vram_gb"])
        model_id = spec["id"]

        # 提取用于匹配的纯模型名 (例如 "qwen2.5:0.5b")
        ollama_model_name = model_id.split("/")[-1] if "/" in model_id else model_id
        is_installed = ollama_model_name in installed_models

        if available_vram >= req_vram:
            ratio = available_vram / req_vram
            if ratio >= 2.0:
                score = 95
                fit_level = "perfect"
            elif ratio >= 1.5:
                score = 85
                fit_level = "good"
            else:
                score = 75
                fit_level = "fair"
        else:
            ratio = available_vram / req_vram
            score = int(ratio * 50)
            fit_level = "poor"

        recommendations.append(
            {
                "model_id": model_id,
                "name": spec["name"],
                "description": spec["description"],
                "req_vram_gb": req_vram,
                "fit_score": score,
                "fit_level": fit_level,
                "is_installed": is_installed,
            }
        )

    recommendations.sort(key=lambda x: int(x["fit_score"]), reverse=True)

    response = HardwareRecommendationResponse(
        hardware_detected=True,
        os_type=getattr(profile, "os_type", None),
        cpu_arch=getattr(profile, "cpu_arch", None),
        total_ram_gb=round(getattr(profile, "total_ram_gb", 0.0), 1),
        has_gpu=getattr(profile, "has_gpu", False),
        gpu_name=getattr(profile, "gpu_name", None),
        gpu_vram_gb=round(getattr(profile, "gpu_vram_gb", 0.0), 1) if getattr(profile, "gpu_vram_gb", None) else None,
        is_unified_memory=getattr(profile, "is_unified_memory", False),
        ollama_running=is_ollama_running,
        recommendations=recommendations,
    )

    return success_response(data=response.model_dump())
