"""[INPUT]
- .common (POS: headers / keys / provider/model naming)
- myrm_agent_harness.toolkits.llms.catalog::register_model (POS: the model catalog the cost engine reads)

[OUTPUT]
- register_custom_model_pricing

[POS]
Model resolver: user-defined model pricing registration into the model catalog.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.llms.catalog import register_model

from .common import (
    _build_provider_type_map,
    _to_route_model_id,
)

logger = logging.getLogger(__name__)


def register_custom_model_pricing(providers_dict: dict[str, object] | None) -> int:
    """Register user-defined model pricing into the model catalog.

    Reads customModelInfo from providers config and registers input/output
    cost for models that have user-defined pricing. This lets the cost engine
    return meaningful costs for self-hosted models (Ollama, vLLM, LM Studio)
    that have no built-in price table.

    Note: Frontend stores costs as $/million-tokens (matching models.dev),
    while the catalog holds $/token. This function performs the conversion.

    Returns the number of models registered.
    """
    if not providers_dict or not isinstance(providers_dict, dict):
        return 0

    custom_info = providers_dict.get("customModelInfo")
    if not isinstance(custom_info, dict) or not custom_info:
        return 0

    provider_type_map = _build_provider_type_map(providers_dict)

    registered = 0
    for model_key, info in custom_info.items():
        if not isinstance(info, dict):
            continue

        input_cost_per_m = info.get("input_cost_per_million")
        output_cost_per_m = info.get("output_cost_per_million")

        if not isinstance(input_cost_per_m, (int, float)) or not isinstance(output_cost_per_m, (int, float)):
            continue
        if input_cost_per_m <= 0 and output_cost_per_m <= 0:
            continue

        parts = model_key.split("/", 1)
        if len(parts) != 2:
            continue
        provider_id, raw_model = parts[0], parts[1]

        ptype = provider_type_map.get(provider_id)
        routed_model = _to_route_model_id(provider_id, raw_model, ptype)

        # 确定合法 provider 前缀，避免被判定为未知提供商
        inferred_provider = "custom_openai"
        if "/" in routed_model:
            model_prefix = routed_model.split("/", 1)[0]
            if model_prefix in ("openai", "anthropic", "deepseek", "gemini", "groq", "mistral", "openrouter"):
                inferred_provider = model_prefix

        cost_entry: dict[str, object] = {
            "input_cost_per_token": float(input_cost_per_m) / 1_000_000,
            "output_cost_per_token": float(output_cost_per_m) / 1_000_000,
            "provider": inferred_provider,
        }
        window = info.get("max_input_tokens")
        if isinstance(window, (int, float)) and window > 0:
            cost_entry["max_input_tokens"] = int(window)

        # 可选缓存读单价
        cache_read_m = info.get("cache_read_cost_per_million") or info.get("cache_cost_per_million")
        if isinstance(cache_read_m, (int, float)) and cache_read_m > 0:
            cost_entry["cache_read_input_token_cost"] = float(cache_read_m) / 1_000_000

        # 双向注册：限定名与裸模型名均可命中价表
        register_model(routed_model, cost_entry)
        if raw_model != routed_model:
            register_model(raw_model, {**cost_entry, "provider": "openai"})

        registered += 1

    if registered:
        logger.info("Registered custom pricing for %d model(s)", registered)

    return registered
