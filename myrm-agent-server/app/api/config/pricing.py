"""[INPUT]
- litellm.model_cost (POS: LiteLLM 内置权威模型单价字典)
- litellm.get_model_info (POS: 模型信息与别名解析器)

[OUTPUT]
- pricing_router: FastAPI APIRouter 实例，挂载 GET /model-pricing 端点
- ModelPricingItem, ModelPricingResponse: Pydantic 校验模型

[POS]
app/api/config/pricing.py — 提供四维单价矩阵与 Prompt Cache 经济学数据只读查询 API。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

pricing_router = APIRouter(tags=["pricing"])


class ModelPricingItem(BaseModel):
    """模型四维单价条目（单位：美元 / 每百万 tokens，USD / 1M tokens）"""

    model: str = Field(..., description="规范化模型名称或别名")
    input_cost_per_mtoken: float = Field(0.0, description="输入 Token 单价 ($/1M)")
    output_cost_per_mtoken: float = Field(0.0, description="输出 Token 单价 ($/1M)")
    cache_read_cost_per_mtoken: float | None = Field(
        None, description="Prompt Cache 命中读取单价 ($/1M)，若不支持则为 None"
    )
    cache_write_cost_per_mtoken: float | None = Field(
        None, description="Prompt Cache 写入创建单价 ($/1M)，若不支持则为 None"
    )
    cache_read_discount: float | None = Field(
        None, description="Prompt Cache 命中相对输入的折扣比率（例如 0.9 表示节省 90%）"
    )
    supports_prompt_caching: bool = Field(
        False, description="模型提供方是否支持 Prompt Caching"
    )


class ModelPricingResponse(BaseModel):
    """模型单价矩阵查询响应"""

    models: dict[str, ModelPricingItem] = Field(
        default_factory=dict, description="模型单价字典，key 为模型名"
    )


# 常见主流模型标杆，用于无特定参数时的默认对比视图
DEFAULT_REPRESENTATIVE_MODELS: tuple[str, ...] = (
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o3-mini",
    "deepseek-chat",
    "deepseek-reasoner",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "qwen-plus",
    "qwen-max",
)


def extract_model_pricing_item(model_name: str) -> ModelPricingItem | None:
    """从 LiteLLM 权威字典中安全提取四维单价并换算为 USD / 1M tokens。"""
    try:
        import litellm
        from litellm import model_cost

        cost_dict: dict[str, object] | None = model_cost.get(model_name)
        if not cost_dict:
            try:
                info = litellm.get_model_info(model_name)
                if isinstance(info, dict):
                    cost_dict = info
            except Exception:
                pass

        if not cost_dict:
            # 常见 Provider 别名候选
            candidates = [
                f"anthropic/{model_name}",
                f"openai/{model_name}",
                f"google/{model_name}",
            ]
            for cand in candidates:
                if cand in model_cost:
                    cost_dict = model_cost[cand]
                    break

        if not cost_dict:
            # 模糊前缀/子串匹配（例如匹配到 anthropic.claude-3-5-sonnet-20241022-v2:0）
            normalized = model_name.strip().lower()
            for key, val in model_cost.items():
                if normalized in key.lower() and isinstance(val, dict):
                    cost_dict = val
                    break

        if not cost_dict:
            return None

        # 换算系数：单 token 单价 -> 百万 token ($/1M)
        multiplier = 1_000_000.0

        raw_in = cost_dict.get("input_cost_per_token")
        in_cost = float(raw_in) * multiplier if isinstance(raw_in, (int, float)) else 0.0

        raw_out = cost_dict.get("output_cost_per_token")
        out_cost = (
            float(raw_out) * multiplier if isinstance(raw_out, (int, float)) else 0.0
        )

        raw_cache_read = cost_dict.get("cache_read_input_token_cost")
        cache_read_cost = (
            float(raw_cache_read) * multiplier
            if isinstance(raw_cache_read, (int, float))
            else None
        )

        raw_cache_write = cost_dict.get("cache_creation_input_token_cost")
        cache_write_cost = (
            float(raw_cache_write) * multiplier
            if isinstance(raw_cache_write, (int, float))
            else None
        )

        supports_cache = bool(
            cost_dict.get("supports_prompt_caching")
            or cache_read_cost is not None
            or cache_write_cost is not None
        )

        cache_discount: float | None = None
        if cache_read_cost is not None and in_cost > 0:
            discount = 1.0 - (cache_read_cost / in_cost)
            if discount > 0:
                cache_discount = round(discount, 4)

        return ModelPricingItem(
            model=model_name,
            input_cost_per_mtoken=round(in_cost, 4),
            output_cost_per_mtoken=round(out_cost, 4),
            cache_read_cost_per_mtoken=(
                round(cache_read_cost, 4) if cache_read_cost is not None else None
            ),
            cache_write_cost_per_mtoken=(
                round(cache_write_cost, 4) if cache_write_cost is not None else None
            ),
            cache_read_discount=cache_discount,
            supports_prompt_caching=supports_cache,
        )
    except Exception as exc:
        logger.debug("Failed to extract pricing for %s: %s", model_name, exc)
        return None


@pricing_router.get(
    "/model-pricing",
    response_model=ModelPricingResponse,
    summary="获取主流与指定模型的四维单价矩阵与 Cache 折扣",
)
async def get_model_pricing(
    model: Annotated[
        str | None,
        Query(
            description="可选指定单个模型名进行查询。若留空则返回常用主流模型定价矩阵。"
        ),
    ] = None,
) -> ModelPricingResponse:
    """返回以 $/1M tokens 计价的模型输入、输出、Cache 读写单价及节省率。"""
    result: dict[str, ModelPricingItem] = {}

    if model:
        # 查询特定模型
        item = extract_model_pricing_item(model.strip())
        if item:
            result[item.model] = item
        else:
            # 尝试根据前缀或别名在 model_cost 中匹配
            try:
                from litellm import model_cost

                normalized = model.strip().lower()
                for key in model_cost:
                    if normalized in key.lower():
                        match_item = extract_model_pricing_item(key)
                        if match_item:
                            result[key] = match_item
                            if len(result) >= 5:
                                break
            except Exception:
                pass
    else:
        # 默认返回代表性主流模型
        for rep_model in DEFAULT_REPRESENTATIVE_MODELS:
            item = extract_model_pricing_item(rep_model)
            if item:
                result[rep_model] = item

    return ModelPricingResponse(models=result)
