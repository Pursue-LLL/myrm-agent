"""[INPUT]
- app.core.types::ModelConfig (POS: 业务层模型配置对象)
- myrm_agent_harness.toolkits.llms::llm_manager (POS: LiteLLM/LangChain 实例创建)

[OUTPUT]
- create_agent_llms(): 创建 main / lite / fallback / safety_fallback LLM 实例（lite LLM 自动注入 reasoning_effort='low'）
- apply_lite_context_downgrade(): Dynamic Ratio Shield — lite context 不足时降级到 main 配置
- _inject_low_reasoning_effort(): 为 ModelConfig 注入低推理力度参数，供 Dynamic Ratio Shield 降级复用

[POS]
LLM 实例工厂。负责把业务层 `ModelConfig` 转换为可执行的 LiteLLM/LangChain 实例。
主模型 failover 由 harness `stream_recovery` 在 API 报错时触发，不在启动阶段静默替换用户选择。
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.llms import llm_manager
from myrm_agent_harness.toolkits.llms.fallback import ManagedLLM, ScenarioType

from app.core.types import ModelConfig

logger = logging.getLogger(__name__)

_LOW_REASONING_EFFORT = "low"


def _inject_low_reasoning_effort(cfg: ModelConfig) -> ModelConfig:
    """Return a ModelConfig copy with reasoning_effort='low' merged into model_kwargs.

    Unsupported models silently ignore the parameter via litellm.drop_params=True.
    """
    existing = cfg.model_kwargs or {}
    if existing.get("reasoning_effort") == _LOW_REASONING_EFFORT:
        return cfg
    merged = {**existing, "reasoning_effort": _LOW_REASONING_EFFORT}
    return cfg.model_copy(update={"model_kwargs": merged})


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
        raw_main_llm = await llm_manager.get_llm_from_config(
            model_cfg, api_keys=main_api_keys
        )
        pool_info = f" (pool={len(main_api_keys)} keys)" if main_api_keys else ""
        logger.info("Main model: %s%s", model_cfg.model, pool_info)
    except Exception as e:
        raise ValueError(
            f"Failed to create main LLM with model '{model_cfg.model}': {e}. "
            "Please check your model configuration (model name, API key, base URL)."
        ) from e

    # 2. 创建过滤/摘要模型（注入 reasoning_effort='low' 降低辅助任务推理开销）
    if lite_model_cfg is not None:
        try:
            filter_api_keys = getattr(lite_model_cfg, "api_keys", None)
            lite_cfg_with_low_effort = _inject_low_reasoning_effort(lite_model_cfg)
            lite_llm = await llm_manager.get_llm_from_config(
                lite_cfg_with_low_effort,
                api_keys=filter_api_keys,
            )
            logger.info(
                "Lite model: %s (independent, reasoning_effort=low)",
                lite_model_cfg.model,
            )
        except Exception as e:
            raise ValueError(
                f"Failed to create lite LLM with model '{lite_model_cfg.model}': {e}. "
                "Please check your filter model configuration."
            ) from e
    else:
        lite_cfg_with_low_effort = _inject_low_reasoning_effort(model_cfg)
        main_api_keys = getattr(model_cfg, "api_keys", None)
        lite_llm = await llm_manager.get_llm_from_config(
            lite_cfg_with_low_effort,
            api_keys=main_api_keys,
        )
        logger.info(
            "Lite model: %s (dedicated instance, reasoning_effort=low)", model_cfg.model
        )

    # 4. 创建安全审核拦截降级模型
    safety_fallback_llm = None
    if safety_fallback_model_cfg is not None:
        try:
            safety_api_keys = getattr(safety_fallback_model_cfg, "api_keys", None)
            safety_fallback_llm = await llm_manager.get_llm_from_config(
                safety_fallback_model_cfg, api_keys=safety_api_keys
            )
            logger.info("Safety Fallback model: %s", safety_fallback_model_cfg.model)
        except Exception as e:
            logger.warning(
                f"Failed to create safety fallback LLM: {e}, proceeding without safety failover"
            )

    # 3. 创建备用主模型并集成 ModelFallbackManager
    if fallback_model_cfg is not None:
        try:
            fallback_api_keys = getattr(fallback_model_cfg, "api_keys", None)
            raw_fallback_llm = await llm_manager.get_llm_from_config(
                fallback_model_cfg, api_keys=fallback_api_keys
            )
            logger.info("Fallback model: %s", fallback_model_cfg.model)

            # 创建 ManagedLLM 包装器，集成智能降级管理
            managed_llm = ManagedLLM(
                main_llm=raw_main_llm,
                fallback_llm=raw_fallback_llm,
                main_model_name=model_cfg.model,
                fallback_model_name=fallback_model_cfg.model,
                scenario=ScenarioType.BALANCED,
            )
            logger.info(
                "ModelFallbackManager active: main=%s, fallback=%s",
                model_cfg.model,
                fallback_model_cfg.model,
            )

            # 返回 ManagedLLM 作为主模型，fallback_llm=None（已集成）
            return managed_llm, lite_llm, None, safety_fallback_llm

        except Exception as e:
            logger.warning(
                f"Failed to create fallback LLM: {e}, proceeding without failover"
            )
            # 降级处理失败，返回原始 LLM
            return raw_main_llm, lite_llm, None, safety_fallback_llm
    else:
        # 无备用模型，返回原始 LLM
        return raw_main_llm, lite_llm, None, safety_fallback_llm


async def apply_lite_context_downgrade(
    main_llm: BaseChatModel,
    lite_llm: BaseChatModel,
    model_cfg: ModelConfig,
) -> BaseChatModel:
    """Degrade lite LLM to main model when lite context window is too small (Dynamic Ratio Shield)."""
    from myrm_agent_harness.toolkits.llms.utils.model_utils import (
        get_model_context_limit,
    )

    main_limit = get_model_context_limit(main_llm) or 128000
    lite_limit = get_model_context_limit(lite_llm)
    if not lite_limit or not main_limit:
        return lite_llm

    if lite_limit >= main_limit * 0.85:
        return lite_llm

    logger.warning(
        "Context capacity mismatch: main model %s (%s tokens) vs lite (%s tokens). "
        "Degrading lite LLM to main model.",
        model_cfg.model,
        main_limit,
        lite_limit,
    )
    main_api_keys = getattr(model_cfg, "api_keys", None)
    fallback_lite_cfg = _inject_low_reasoning_effort(model_cfg)
    return await llm_manager.get_llm_from_config(
        fallback_lite_cfg, api_keys=main_api_keys
    )
