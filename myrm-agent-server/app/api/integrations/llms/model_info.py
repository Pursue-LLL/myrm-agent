"""[INPUT]
- myrm_agent_harness.toolkits.llms.catalog::model_facts (POS: built-in model catalog)
- fastapi / pydantic (POS: route + schema primitives)

[OUTPUT]
- get_model_info_batch: capability lookup for a batch of models
- ModelCapabilities / ModelInfoBatchRequest
- _build_capabilities

[POS]
Model metadata endpoint. Each name is looked up in the catalog (case-insensitive; a gateway name resolves to the
model behind it), so the settings page shows real capabilities; a name the catalog does not know gets an empty
capability set.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.llms.catalog import model_facts
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

from .common import router


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


class ModelInfoBatchRequest(BaseModel):
    """批量模型信息请求"""

    models: list[str] = Field(..., description="模型名称列表")


def _build_capabilities(info: Mapping[str, object]) -> ModelCapabilities:
    """从模型目录条目构建能力对象"""
    return ModelCapabilities.model_validate(
        {
            "supports_vision": bool(info.get("supports_vision")),
            "supports_function_calling": bool(info.get("supports_function_calling")),
            "supports_reasoning": bool(info.get("supports_reasoning")),
            "supports_web_search": bool(info.get("supports_web_search")),
            "supports_prompt_caching": bool(info.get("supports_prompt_caching")),
            "input_cost_per_token": info.get("input_cost_per_token"),
            "output_cost_per_token": info.get("output_cost_per_token"),
            "max_input_tokens": info.get("max_input_tokens"),
            "max_output_tokens": info.get("max_output_tokens"),
        }
    )


@router.post("/model-info/batch", response_model=StandardSuccessResponse)
async def get_model_info_batch(request: ModelInfoBatchRequest) -> JSONResponse:
    """
    批量获取模型的能力信息（目录查找，大小写不敏感；网关复合名回退到其背后的模型）

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
