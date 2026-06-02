"""[INPUT]
- app.core.channel_bridge.model_resolver::_extract_all_active_keys / _to_litellm_model (POS: 模型解析与 provider 密钥提取辅助)
- app.core.types::ModelConfig (POS: 业务层模型配置对象)
- litellm::supports_function_calling (POS: LiteLLM provider 能力探测)

[OUTPUT]
- select_tool_capable_model_cfg(): 在 GeneralAgent 启动时选择支持 function calling 的主模型
- create_agent_llms(): 创建 main / lite / fallback / safety_fallback LLM 实例

[POS]
LLM 实例工厂。负责把业务层 `ModelConfig` 转换为可执行的 LiteLLM/LangChain 实例，
并在必要时为 GeneralAgent 选择支持工具调用的主模型，保证文件写入、编辑等动作型任务可执行。
"""

from __future__ import annotations

import logging

import litellm
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.llms import llm_manager
from myrm_agent_harness.toolkits.llms.fallback import ManagedLLM, ScenarioType

from app.core.channel_bridge.model_resolver import (
    _extract_all_active_keys,
    _to_litellm_model,
)
from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


def _supports_function_calling(model_name: str) -> bool:
    # Explicitly support known custom models that litellm might not know about
    if any(m in model_name.lower() for m in ["mimo", "deepseek", "minimax", "qwen"]):
        return True
    try:
        return bool(litellm.supports_function_calling(model=model_name))
    except Exception as exc:
        logger.debug("LiteLLM capability probe failed for %s: %s", model_name, exc)
        return False


def _iter_provider_model_names(provider: dict[str, object]) -> list[str]:
    model_names: list[str] = []
    for key in ("enabledModels", "models"):
        raw_value = provider.get(key)
        if isinstance(raw_value, list):
            for item in raw_value:
                if isinstance(item, str) and item and item not in model_names:
                    model_names.append(item)
        elif isinstance(raw_value, str) and raw_value and raw_value not in model_names:
            model_names.append(raw_value)

    for key in ("model", "defaultModel", "selectedModel", "primaryModel"):
        raw_value = provider.get(key)
        if isinstance(raw_value, str) and raw_value and raw_value not in model_names:
            model_names.append(raw_value)

    return model_names


def _build_model_config_from_provider(
    provider: dict[str, object],
    raw_model: str,
) -> ModelConfig | None:
    provider_id = str(provider.get("id", ""))
    if not provider_id:
        return None

    api_keys = _extract_all_active_keys(provider)
    if not api_keys:
        return None

    provider_type = str(provider.get("providerType", "")) or None
    litellm_model = _to_litellm_model(provider_id, raw_model, provider_type)
    if not _supports_function_calling(litellm_model):
        return None

    api_url = str(provider.get("apiUrl") or provider.get("baseURL") or "") or None
    return ModelConfig(
        model=litellm_model,
        api_key=api_keys[0],
        base_url=api_url,
        api_keys=api_keys if len(api_keys) > 1 else None,
    )


def select_tool_capable_model_cfg(
    model_cfg: ModelConfig,
    lite_model_cfg: ModelConfig | None = None,
    fallback_model_cfg: ModelConfig | None = None,
    safety_fallback_model_cfg: ModelConfig | None = None,
    providers_dict: dict[str, object] | None = None,
) -> tuple[ModelConfig, str]:
    """Select a main model that can actually call tools.

    Returns:
        (selected_model_cfg, selection_source)
        selection_source is one of: "main", "lite", "fallback", "safety_fallback",
        or "provider_scan".
    """
    if _supports_function_calling(model_cfg.model):
        return model_cfg, "main"

    for source_name, candidate in (
        ("fallback", fallback_model_cfg),
        ("lite", lite_model_cfg),
        ("safety_fallback", safety_fallback_model_cfg),
    ):
        if candidate is None:
            continue
        if _supports_function_calling(candidate.model):
            logger.warning(
                "GeneralAgent main model %s lacks function calling support; using %s model %s instead.",
                model_cfg.model,
                source_name,
                candidate.model,
            )
            return candidate, source_name

    if providers_dict:
        providers_raw = providers_dict.get("providers")
        if isinstance(providers_raw, list):
            for provider in providers_raw:
                if not isinstance(provider, dict):
                    continue
                if not (provider.get("isEnabled") or provider.get("enabled")):
                    continue

                provider_id = str(provider.get("id", ""))
                if not provider_id:
                    continue

                api_keys = _extract_all_active_keys(provider)
                if not api_keys:
                    continue

                for raw_model in _iter_provider_model_names(provider):
                    candidate = _build_model_config_from_provider(provider, raw_model)
                    if candidate is None:
                        continue
                    logger.warning(
                        "GeneralAgent main model %s lacks function calling support; auto-selected %s from provider %s for tool-capable execution.",
                        model_cfg.model,
                        candidate.model,
                        provider_id,
                    )
                    return candidate, "provider_scan"

    logger.warning(
        "GeneralAgent main model %s lacks function calling support and no tool-capable fallback was found; proceeding with the original model.",
        model_cfg.model,
    )
    return model_cfg, "main"


async def create_agent_llms(
    model_cfg: ModelConfig,
    lite_model_cfg: ModelConfig | None,
    fallback_model_cfg: ModelConfig | None,
    safety_fallback_model_cfg: ModelConfig | None = None,
) -> tuple[BaseChatModel, BaseChatModel, BaseChatModel | None, BaseChatModel | None]:
    """创建 Agent 所需的 LLM 实例，集成智能降级管理。

    如果提供 fallback_model_cfg，将创建 ManagedLLM 包装器，自动提供：
    - 冷却期机制（避免重复调用失败的模型）
    - 错误驱动探测（自动尝试恢复到主模型）
    - 场景感知选择（根据场景选择最优模型）

    Args:
        model_cfg: 主模型配置
        lite_model_cfg: 过滤/摘要模型配置（None 时复用主模型）
        fallback_model_cfg: 备用主模型配置（None 时无备用）

    Returns:
        (main_llm, lite_llm, fallback_llm_for_legacy_compatibility, safety_fallback_llm)
        - main_llm: ManagedLLM（如果有fallback）或原始LLM（如果无fallback）
        - lite_llm: 过滤/摘要模型
        - fallback_llm: None（已集成到main_llm中，仅为保持接口兼容性）

    Raises:
        ValueError: 主模型或过滤模型创建失败
    """
    # 1. 创建主模型
    try:
        main_api_keys = getattr(model_cfg, "api_keys", None)
        raw_main_llm = await llm_manager.get_llm_from_config(model_cfg, api_keys=main_api_keys)
        pool_info = f" (pool={len(main_api_keys)} keys)" if main_api_keys else ""
        logger.info("Main model: %s%s", model_cfg.model, pool_info)
    except Exception as e:
        raise ValueError(
            f"Failed to create main LLM with model '{model_cfg.model}': {e}. "
            "Please check your model configuration (model name, API key, base URL)."
        ) from e

    # 2. 创建过滤/摘要模型
    if lite_model_cfg is not None:
        try:
            filter_api_keys = getattr(lite_model_cfg, "api_keys", None)
            lite_llm = await llm_manager.get_llm_from_config(lite_model_cfg, api_keys=filter_api_keys)
            logger.info("Lite model: %s (independent)", lite_model_cfg.model)
        except Exception as e:
            raise ValueError(
                f"Failed to create lite LLM with model '{lite_model_cfg.model}': {e}. "
                "Please check your filter model configuration."
            ) from e
    else:
        lite_llm = raw_main_llm
        logger.info("Lite model: %s (reusing main)", model_cfg.model)

    # 4. 创建安全审核拦截降级模型
    safety_fallback_llm = None
    if safety_fallback_model_cfg is not None:
        try:
            safety_api_keys = getattr(safety_fallback_model_cfg, "api_keys", None)
            safety_fallback_llm = await llm_manager.get_llm_from_config(safety_fallback_model_cfg, api_keys=safety_api_keys)
            logger.info("Safety Fallback model: %s", safety_fallback_model_cfg.model)
        except Exception as e:
            logger.warning(f"Failed to create safety fallback LLM: {e}, proceeding without safety failover")

    # 3. 创建备用主模型并集成 ModelFallbackManager
    if fallback_model_cfg is not None:
        try:
            fallback_api_keys = getattr(fallback_model_cfg, "api_keys", None)
            raw_fallback_llm = await llm_manager.get_llm_from_config(fallback_model_cfg, api_keys=fallback_api_keys)
            logger.info("Fallback model: %s", fallback_model_cfg.model)

            # 创建 ManagedLLM 包装器，集成智能降级管理
            managed_llm = ManagedLLM(
                main_llm=raw_main_llm,
                fallback_llm=raw_fallback_llm,
                main_model_name=model_cfg.model,
                fallback_model_name=fallback_model_cfg.model,
                scenario=ScenarioType.BALANCED,
            )
            logger.info("ModelFallbackManager active: main=%s, fallback=%s", model_cfg.model, fallback_model_cfg.model)

            # 返回 ManagedLLM 作为主模型，fallback_llm=None（已集成）
            return managed_llm, lite_llm, None, safety_fallback_llm

        except Exception as e:
            logger.warning(f"Failed to create fallback LLM: {e}, proceeding without failover")
            # 降级处理失败，返回原始 LLM
            return raw_main_llm, lite_llm, None, safety_fallback_llm
    else:
        # 无备用模型，返回原始 LLM
        return raw_main_llm, lite_llm, None, safety_fallback_llm
