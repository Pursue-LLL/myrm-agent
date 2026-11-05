"""[INPUT]
- myrm_agent_harness.toolkits.llms.catalog::model_facts, known_models, is_deprecated (POS: built-in model catalog)
- fastapi / pydantic (POS: route + schema primitives)

[OUTPUT]
- get_model_info / get_model_info_batch: capability lookup for one model or a batch
- ModelCapabilities / ModelCandidate / ModelInfoResponse / ModelInfoRequest / ModelInfoBatchRequest
- _build_capabilities, _search_models_by_name

[POS]
Model metadata endpoints. The catalog lookup comes first (case-insensitive; a gateway name resolves to the model
behind it), then a name search over the catalog, so the settings page shows real capabilities instead of a
fabricated default.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.llms.catalog import is_deprecated, known_models, model_facts
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

from .common import logger, router


class ModelCapabilities(BaseModel):
    """模型能力信息"""

    supports_vision: bool = Field(default=False, description="是否支持视觉/图像输入")
    supports_function_calling: bool = Field(default=False, description="是否支持函数调用")
    supports_reasoning: bool = Field(default=False, description="是否支持推理")
    supports_web_search: bool = Field(default=False, description="是否支持网页搜索")
    supports_prompt_caching: bool = Field(default=False, description="是否支持提示词缓存")
    input_cost_per_token: float | None = Field(default=None, description="每个输入 token 的成本（美元）")
    output_cost_per_token: float | None = Field(default=None, description="每个输出 token 的成本（美元）")
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

    model: str = Field(..., description="模型名称（provider/model 格式）")


class ModelInfoBatchRequest(BaseModel):
    """批量模型信息请求"""

    models: list[str] = Field(..., description="模型名称列表")


def _build_capabilities(info: Mapping[str, object]) -> ModelCapabilities:
    """从模型目录条目构建能力对象"""
    return ModelCapabilities(
        supports_vision=bool(info.get("supports_vision")),
        supports_function_calling=bool(info.get("supports_function_calling")),
        supports_reasoning=bool(info.get("supports_reasoning")),
        supports_web_search=bool(info.get("supports_web_search")),
        supports_prompt_caching=bool(info.get("supports_prompt_caching")),
        input_cost_per_token=info.get("input_cost_per_token"),  # type: ignore[arg-type]
        output_cost_per_token=info.get("output_cost_per_token"),  # type: ignore[arg-type]
        max_input_tokens=info.get("max_input_tokens"),  # type: ignore[arg-type]
        max_output_tokens=info.get("max_output_tokens"),  # type: ignore[arg-type]
    )


def _search_models_by_name(model_name: str) -> list[ModelCandidate]:
    """在模型目录中搜索包含该模型名的所有条目

    Args:
        model_name: 要搜索的模型名称

    Returns:
        匹配的候选模型列表
    """
    model_name_lower = model_name.lower()
    candidates: list[ModelCandidate] = []

    for model_key, entry in known_models().items():
        # 已过弃用日期的条目仍可查事实，但不作为候选推荐给用户
        if model_name_lower in model_key.lower() and not is_deprecated(entry):
            # 提取提供商名称（键的第一部分）
            provider = model_key.split("/")[0] if "/" in model_key else "unknown"

            candidates.append(
                ModelCandidate(
                    provider=provider,
                    model_key=model_key,
                    capabilities=_build_capabilities(entry),
                )
            )

    return candidates


@router.post("/model-info", response_model=StandardSuccessResponse)
async def get_model_info(request: ModelInfoRequest) -> JSONResponse:
    """
    获取单个模型的能力信息

    目录命中（大小写不敏感；网关复合名回退到其背后的模型）时返回 found=true，否则返回候选列表供用户选择

    Args:
        request: 包含模型名称的请求体

    Returns:
        ModelInfoResponse: found=true 时返回 capabilities，否则返回 candidates 候选列表
    """
    # 1. 先查目录事实（大小写不敏感，网关复合名回退到其背后的模型）
    info = model_facts(request.model)
    if info:
        capabilities = _build_capabilities(info)
        response = ModelInfoResponse(found=True, capabilities=capabilities)
        return success_response(data=response.model_dump())

    # 2. 目录未命中，进行名称搜索
    # 提取模型名称部分（去除可能的提供商前缀）
    model_name = request.model.split("/")[-1] if "/" in request.model else request.model

    candidates = _search_models_by_name(model_name)

    logger.debug(f"Model info not found for {request.model}, found {len(candidates)} candidates")

    response = ModelInfoResponse(found=False, candidates=candidates)
    return success_response(data=response.model_dump())


@router.post("/model-info/batch", response_model=StandardSuccessResponse)
async def get_model_info_batch(request: ModelInfoBatchRequest) -> JSONResponse:
    """
    批量获取模型的能力信息（目录查找，规则同 /model-info）

    Args:
        request: 包含模型名称列表的请求体

    Returns:
        模型能力信息字典 {model_name: capabilities}
    """
    result: dict[str, dict[str, object]] = {}

    for model in request.models:
        info = model_facts(model)
        if info:
            capabilities = _build_capabilities(info)
            result[model] = capabilities.model_dump()
        else:
            # 模型不在模型目录中，返回空能力
            result[model] = ModelCapabilities().model_dump()

    return success_response(data=result)
