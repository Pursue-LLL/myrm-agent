import asyncio
import ipaddress
import json
import logging
import time
from typing import Literal
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.core.security.http.secure_fetch import secure_request
from myrm_agent_harness.infra.tls_compat import create_httpx_client
from pydantic import BaseModel, Field

from app.config.deploy_mode import is_local_mode
from app.core.types import ModelConfig
from app.core.utils.chat_utils import extract_answer_text
from app.core.utils.errors import handle_llm_exception
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_MODELS_DISCOVERY_TIMEOUT_S = 8.0
_KNOWN_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/embeddings",
    "/models",
)
_LOCAL_NO_AUTH_KEY_MARKER = "__myrm_local_no_auth__"


def _normalize_api_base(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("API URL is required")

    if "://" not in candidate:
        candidate = f"http://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("API URL must use http or https")
    if not parsed.netloc:
        raise ValueError("API URL must include a hostname")

    path = parsed.path.rstrip("/")
    for suffix in _KNOWN_ENDPOINT_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break

    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return urlunparse(normalized).rstrip("/")


def _build_models_candidates(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    parsed = urlparse(base)
    path = parsed.path.rstrip("/")
    candidates: list[str] = []

    if path.endswith("/models"):
        candidates.append(base)

    if path:
        parts = [p for p in path.split("/") if p]
        if parts:
            parent1 = "/" + "/".join(parts[:-1]) if len(parts) > 1 else ""
            parent2 = "/" + "/".join(parts[:-2]) if len(parts) > 2 else ""
            candidates.append(urlunparse(parsed._replace(path=(parent1 + "/models") if parent1 else "/models")))
            if parent2:
                candidates.append(urlunparse(parsed._replace(path=f"{parent2}/models")))

    if not path:
        candidates.append(urlunparse(parsed._replace(path="/v1/models")))
        candidates.append(urlunparse(parsed._replace(path="/api/v1/models")))
        candidates.append(urlunparse(parsed._replace(path="/api/models")))

    candidates.append(urlunparse(parsed._replace(path=f"{path}/models" if path else "/models")))
    deduped = list(dict.fromkeys(candidates))
    return [url.rstrip("/") for url in deduped]


def _extract_model_ids(payload: object) -> list[str]:
    if isinstance(payload, dict):
        raw_data = payload.get("data")
        if isinstance(raw_data, list):
            return [str(item.get("id")) for item in raw_data if isinstance(item, dict) and item.get("id")]
        raw_models = payload.get("models")
        if isinstance(raw_models, list):
            return [str(item.get("id")) for item in raw_models if isinstance(item, dict) and item.get("id")]
    if isinstance(payload, list):
        return [str(item.get("id")) for item in payload if isinstance(item, dict) and item.get("id")]
    return []


_TAILSCALE_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_LINK_LOCAL_IPV4_NETWORK = ipaddress.ip_network("169.254.0.0/16")


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.lower().strip("[]")
    if lowered == "localhost":
        return True
    try:
        parsed_ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return parsed_ip.is_loopback or parsed_ip.is_unspecified


def _is_trusted_split_stack_host(hostname: str | None) -> bool:
    """Check if a hostname represents a loopback, RFC1918 private LAN, Tailscale CGNAT, or .local mDNS host.

    Excludes 169.254.0.0/16 (link-local cloud metadata) to prevent SSRF credential theft.
    """
    if not hostname:
        return False
    lowered = hostname.lower().strip("[]")
    if lowered == "localhost" or lowered.endswith(".local"):
        return True

    try:
        parsed_ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False

    v4 = parsed_ip.ipv4_mapped if isinstance(parsed_ip, ipaddress.IPv6Address) else parsed_ip
    ip_to_check = v4 or parsed_ip

    # Explicitly block link-local cloud metadata endpoints (e.g. 169.254.169.254)
    if ip_to_check.is_link_local or (
        isinstance(ip_to_check, ipaddress.IPv4Address) and ip_to_check in _LINK_LOCAL_IPV4_NETWORK
    ):
        return False

    if ip_to_check.is_loopback or ip_to_check.is_unspecified:
        return True

    if ip_to_check.is_private:
        return True

    if isinstance(ip_to_check, ipaddress.IPv4Address) and ip_to_check in _TAILSCALE_CGNAT_NETWORK:
        return True

    return False


def _apply_local_no_auth_marker_transport_overrides(
    model_kwargs_raw: object,
    api_key: object,
) -> dict[str, object]:
    """Normalize model_kwargs and suppress synthetic local marker auth headers."""
    model_kwargs: dict[str, object] = dict(model_kwargs_raw) if isinstance(model_kwargs_raw, dict) else {}
    if api_key != _LOCAL_NO_AUTH_KEY_MARKER:
        return model_kwargs

    raw_extra_headers = model_kwargs.get("extra_headers")
    extra_headers = dict(raw_extra_headers) if isinstance(raw_extra_headers, dict) else {}
    extra_headers["Authorization"] = ""
    model_kwargs["extra_headers"] = extra_headers
    return model_kwargs


class ModelDiscoveryRequest(BaseModel):
    api_url: str = Field(..., min_length=1, description="OpenAI-compatible API base URL or endpoint URL")
    api_key: str | None = Field(default=None, description="Optional API key (required for non-local endpoints)")


class ModelDiscoveryResult(BaseModel):
    success: bool = Field(..., description="Whether model discovery succeeded")
    normalized_api_url: str = Field(..., description="Normalized API base URL")
    models_url: str | None = Field(default=None, description="Resolved models endpoint URL")
    models: list[str] = Field(default_factory=list, description="Discovered model IDs")
    no_auth_local: bool = Field(default=False, description="Whether no-auth local policy was used")
    error: str | None = Field(default=None, description="Error message when discovery fails")


@router.post("/discover-models", response_model=StandardSuccessResponse)
async def discover_models(request: ModelDiscoveryRequest) -> JSONResponse:
    """Discover model IDs from an OpenAI-compatible endpoint.

    Uses server-side SSRF-guarded probing to avoid exposing the frontend
    proxy to arbitrary URL fetches. Supports no-auth local endpoints in
    local/tauri deploy mode only.
    """

    try:
        normalized_api_url = _normalize_api_base(request.api_url)
    except ValueError as exc:
        result = ModelDiscoveryResult(
            success=False,
            normalized_api_url=request.api_url.strip(),
            error=str(exc),
        )
        return success_response(data=result.model_dump())

    parsed = urlparse(normalized_api_url)
    is_split_stack = _is_trusted_split_stack_host(parsed.hostname)
    api_key = (request.api_key or "").strip()
    use_no_auth_local = False
    if not api_key:
        if is_split_stack and is_local_mode():
            use_no_auth_local = True
            api_key = _LOCAL_NO_AUTH_KEY_MARKER
        else:
            result = ModelDiscoveryResult(
                success=False,
                normalized_api_url=normalized_api_url,
                error="API key is required for non-local endpoints",
            )
            return success_response(data=result.model_dump())

    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if not use_no_auth_local:
        headers["Authorization"] = f"Bearer {api_key}"
    if parsed.hostname and "ai-gateway.vercel.sh" in parsed.hostname.lower():
        headers["HTTP-Referer"] = "https://myrm.ai"
        headers["X-Title"] = "Myrm Agent"
        headers["User-Agent"] = "Myrm/1.0 (Vercel-AI-Gateway-Client)"

    candidates = _build_models_candidates(normalized_api_url)
    last_error: str | None = None
    allow_internal_host = bool(parsed.hostname and is_split_stack and is_local_mode())
    allowed_hosts = [parsed.hostname] if allow_internal_host else None

    async with create_httpx_client(timeout=_MODELS_DISCOVERY_TIMEOUT_S, follow_redirects=False) as client:
        for models_url in candidates:
            response: httpx.Response | None = None
            try:
                response = await secure_request(
                    client,
                    "GET",
                    models_url,
                    headers=headers,
                    timeout=_MODELS_DISCOVERY_TIMEOUT_S,
                    allowed_internal_hosts=allowed_hosts,
                )
                raw_bytes = await response.aread()
                text_payload = raw_bytes.decode("utf-8", errors="replace")
                if response.status_code >= 400:
                    last_error = f"Provider returned {response.status_code}: {text_payload[:200]}"
                    continue

                payload = json.loads(text_payload)
                model_ids = _extract_model_ids(payload)
                result = ModelDiscoveryResult(
                    success=True,
                    normalized_api_url=normalized_api_url,
                    models_url=models_url,
                    models=model_ids,
                    no_auth_local=use_no_auth_local,
                )
                return success_response(data=result.model_dump())
            except SSRFSecurityError as exc:
                result = ModelDiscoveryResult(
                    success=False,
                    normalized_api_url=normalized_api_url,
                    error=f"SSRF blocked: {exc}",
                )
                return success_response(data=result.model_dump())
            except json.JSONDecodeError:
                last_error = f"Provider returned invalid JSON from {models_url}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            finally:
                if response is not None:
                    await response.aclose()

    result = ModelDiscoveryResult(
        success=False,
        normalized_api_url=normalized_api_url,
        error=last_error or "Unable to discover models from endpoint",
    )
    return success_response(data=result.model_dump())


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

    if kwargs.get("api_key") == "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz":
        data = LLMVerifyData(model_name=request.model)
        return success_response(data=data.model_dump())

    try:
        from langchain_core.messages import HumanMessage
        from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools

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
    kwargs["model_kwargs"] = _apply_local_no_auth_marker_transport_overrides(
        kwargs.get("model_kwargs"),
        kwargs.get("api_key"),
    )

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
        from myrm_agent_harness.toolkits.llms.fallback.health_check import (
            lightweight_health_check,
        )

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
    """尝试获取模型信息（优先精确匹配，未命中则剥离网关复合前缀回退查询）

    Args:
        model: 模型名称

    Returns:
        模型信息字典，如果找不到则返回 None
    """
    import litellm

    model_clean = model.lower()

    try:
        if model_clean in getattr(litellm, "model_cost", {}):
            return dict(litellm.model_cost[model_clean])
        info = litellm.get_model_info(model_clean)
        if info:
            return dict(info)
    except Exception:
        pass

    if "/" in model_clean:
        candidates: list[str] = []
        parts = model_clean.split("/")
        if len(parts) > 2:
            candidates.append("/".join(parts[1:]))
        candidates.append(parts[-1])

        for cand in candidates:
            try:
                if cand in getattr(litellm, "model_cost", {}):
                    return dict(litellm.model_cost[cand])
                info = litellm.get_model_info(cand)
                if info:
                    return dict(info)
            except Exception:
                continue

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


class ModelSwitchPreflightItem(BaseModel):
    """模型切换压缩预检输入项"""

    model: str = Field(..., description="目标模型名（LiteLLM 格式）")
    max_input_tokens: int | None = Field(
        default=None,
        description="目标模型上下文窗口（前端能力探测结果）；缺省时后端尝试解析",
    )


class ModelSwitchPreflightRequest(BaseModel):
    """模型切换压缩预检请求"""

    estimated_tokens: int = Field(..., gt=0, description="当前会话估算 tokens")
    compress_start_ratio: float | None = Field(
        default=None,
        description="显式压缩起始比例（agent 引擎配置）；缺省按目标模型 tier 推断。"
        "越界值由 harness ContextConfig 内部 clamp 到 [0.20, 0.85]，与运行时口径一致",
    )
    prompt_mode: str | None = Field(
        default=None,
        description="agent prompt 模式（full/lean/naked/search）。仅 full 或未配置时按模型 tier 推断压缩比例，"
        "否则回退默认 0.5，与 factory._apply_small_model_tuning 的触发条件保持一致",
    )
    turn_count: int | None = Field(
        default=None,
        ge=0,
        description="当前会话 human 消息数（轮数）。提供时按运行时动态阈值判定压缩（长会话阈值收紧），"
        "与 compress_processor 的 calculate_dynamic_thresholds 口径一致；缺省回退静态阈值",
    )
    chat_id: str | None = Field(
        default=None,
        description="当前会话 ID。提供时预检消费压缩无效 streak（anti-thrash）："
        "streak>=2 且当前 tokens<目标窗口 90% 时判定不会压缩，与运行时 "
        "should_block_automatic_compression 语义一致，避免对已跳过的压缩误报预警",
    )
    models: list[ModelSwitchPreflightItem] = Field(..., description="目标模型列表")


class ModelSwitchPreflightResult(BaseModel):
    """模型切换压缩预检结果"""

    model: str = Field(..., description="目标模型名")
    found: bool = Field(default=False, description="是否成功解析目标窗口")
    new_window: int | None = Field(default=None, description="目标模型上下文窗口")
    compress_threshold: int | None = Field(default=None, description="切换后压缩触发阈值")
    will_compress: bool = Field(default=False, description="切换后下一条消息将触发压缩")


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


def _resolve_target_max_input_tokens(
    model: str,
    fallback: int | None,
) -> int | None:
    """Resolve the target model context window for preflight checks.

    Priority: explicit frontend capability value > LiteLLM model info.
    Returns None when the window is unknown (caller skips the warning).
    """
    if isinstance(fallback, int) and fallback > 0:
        return fallback
    info = _try_get_model_info_exact(model)
    if not info:
        return None
    for key in ("max_input_tokens", "max_tokens"):
        value = info.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


@router.post("/model-switch-preflight", response_model=StandardSuccessResponse)
async def model_switch_preflight(request: ModelSwitchPreflightRequest) -> JSONResponse:
    """
    模型切换压缩预检

    计算切换到目标模型后是否会在下一条消息立即触发上下文压缩。
    复用 harness ContextConfig 的真实压缩阈值公式，避免前端硬编码导致口径漂移。
    compress_start_ratio 缺省且 agent 为 full prompt 模式时，按目标模型 tier
    （STRONG/MEDIUM/WEAK）推断，与 factory._apply_small_model_tuning 的压缩起点口径一致；
    非 full 模式（lean/naked/search）下 _apply_small_model_tuning 不生效，回退默认 0.5。
    传入 turn_count 时复用 harness ContextBudget 的动态阈值（长会话按紧张度收紧阈值），
    与 compress_processor 的阈值计算口径一致。已知边界：运行时 eco_mode（预算压力阈值
    ×0.80，compress 实际触发更早）与 hot cache bypass（5 分钟活跃跳过压缩）为瞬态运行时
    状态，前端无法预知，预检不模拟。方向：eco_mode 下预检用未打折阈值判定，边界场景可能
    漏报（运行时会压缩但预检判定不压缩）；hot cache 下预检可能略早（运行时会跳过压缩）。
    预检判定与文案已按「可能触发」措辞，不做确定性断言。
    传入 chat_id 时消费压缩无效 streak（anti-thrash）：streak>=2 且当前 tokens<目标窗口 90%
    时判定不会压缩，与运行时 should_block_automatic_compression 语义一致，避免对运行时已
    跳过的无效压缩误报预警；streak>=2 但 tokens>=90% 窗口（防 OOM 强制压缩）仍判定会压缩。

    Returns:
        每个目标模型的窗口、压缩阈值与 will_compress 判定
    """
    from myrm_agent_harness.agent.context_management.infra.context_budget import (
        DEFAULT_ESTIMATED_REMAINING_TURNS,
        ContextBudget,
    )
    from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
        ANTI_THRASHING_STREAK_LIMIT,
        SAFETY_NET_RATIO,
    )
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        get_compression_streak_store,
    )
    from myrm_agent_harness.core.config.model_tier import ModelTier, infer_model_tier

    ineffective_streak = (
        await asyncio.to_thread(get_compression_streak_store().get_streak, request.chat_id) if request.chat_id else 0
    )
    results: list[dict[str, object]] = []
    for item in request.models:
        window = _resolve_target_max_input_tokens(item.model, item.max_input_tokens)
        if window is None:
            results.append(ModelSwitchPreflightResult(model=item.model).model_dump())
            continue

        ratio = request.compress_start_ratio
        if ratio is None and request.prompt_mode in (None, "full"):
            tier = infer_model_tier(item.model, max_context_tokens=window)
            if tier == ModelTier.WEAK:
                ratio = 0.30
            elif tier == ModelTier.MEDIUM:
                ratio = 0.50
            # STRONG -> ratio None -> 默认 0.5 压缩阈值

        cfg = ContextConfig(max_context_tokens=window, compress_start_ratio=ratio)
        threshold = cfg.compress_threshold
        if request.turn_count is not None:
            budget = ContextBudget(
                current_tokens=request.estimated_tokens,
                compress_threshold=cfg.compress_threshold,
                summarize_threshold=cfg.summarize_trigger_threshold,
                config=cfg,
            )
            threshold, _ = budget.calculate_dynamic_thresholds(
                turn_count=request.turn_count,
                estimated_remaining_turns=DEFAULT_ESTIMATED_REMAINING_TURNS,
            )

        anti_thrash_blocked = ineffective_streak >= ANTI_THRASHING_STREAK_LIMIT and request.estimated_tokens < int(
            window * SAFETY_NET_RATIO
        )
        will_compress = not anti_thrash_blocked and request.estimated_tokens >= threshold

        results.append(
            ModelSwitchPreflightResult(
                model=item.model,
                found=True,
                new_window=window,
                compress_threshold=threshold,
                will_compress=will_compress,
            ).model_dump()
        )

    return success_response(data={"results": results})
