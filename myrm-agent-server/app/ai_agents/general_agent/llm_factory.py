"""[INPUT]
- app.core.types::ModelConfig (POS: 业务层模型配置对象)
- myrm_agent_harness.toolkits.llms::{llm_manager, ManagedLLM, ScenarioType} (POS: LiteLLM/LangChain 实例创建与托管)

[OUTPUT]
- create_agent_llms(): 创建 main / lite / fallback / safety_fallback LLM 实例（lite LLM 自动注入 reasoning_effort='low'）
- apply_lite_context_downgrade(): Dynamic Ratio Shield — lite context 不足时降级到 main 配置；返回 (lite_llm, effective_lite_cfg)
- apply_lite_managed_fallback(): lite 模型 ManagedLLM 包装（fast search / 摘要路径 failover）
- _inject_low_reasoning_effort(): 为 ModelConfig 注入低推理力度参数，供 Dynamic Ratio Shield 降级复用

[POS]
LLM 实例工厂。负责把业务层 `ModelConfig` 转换为可执行的 LiteLLM/LangChain 实例。
主模型 failover 由 harness `stream_recovery` 在 API 报错时触发，不在启动阶段静默替换用户选择。
有 fallback 时 main 仍返回 raw_fallback_llm 供 StreamExecutor graph rebuild（ManagedLLM._astream 只调 main）。
"""

from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.llms import ManagedLLM, ScenarioType, llm_manager

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
    fallback_model_cfgs: list[ModelConfig] | None = None,
) -> tuple[BaseChatModel, BaseChatModel, BaseChatModel | None, BaseChatModel | None, list[BaseChatModel] | None]:
    """创建 Agent 所需的 LLM 实例，集成智能降级管理。

    如果提供 fallback_model_cfg 或 fallback_model_cfgs，将创建 ManagedLLM 包装器，自动提供：
    - 冷却期机制（避免重复调用失败的模型）
    - 错误驱动探测（自动尝试恢复到主模型）
    - 场景感知选择（根据场景选择最优模型）

    Args:
        model_cfg: 主模型配置
        lite_model_cfg: 过滤/摘要模型配置（None 时复用主模型）
        fallback_model_cfg: 备用主模型配置（单个）
        safety_fallback_model_cfg: 安全拦截备用模型
        fallback_model_cfgs: 有序备用主模型配置列表（多级）

    Returns:
        (main_llm, lite_llm, stream_fallback_llm, safety_fallback_llm, stream_fallback_llms)
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
        logger.info("Lite model: %s (dedicated instance, reasoning_effort=low)", model_cfg.model)

    # 3. 创建安全审核拦截降级模型
    safety_fallback_llm = None
    if safety_fallback_model_cfg is not None:
        try:
            safety_api_keys = getattr(safety_fallback_model_cfg, "api_keys", None)
            safety_fallback_llm = await llm_manager.get_llm_from_config(safety_fallback_model_cfg, api_keys=safety_api_keys)
            logger.info("Safety Fallback model: %s", safety_fallback_model_cfg.model)
        except Exception as e:
            logger.warning(f"Failed to create safety fallback LLM: {e}, proceeding without safety failover")

    # 4. 创建备用主模型并集成 ModelFallbackManager
    effective_fallbacks: list[ModelConfig] = []
    if fallback_model_cfgs:
        effective_fallbacks = list(fallback_model_cfgs)
    elif fallback_model_cfg is not None:
        effective_fallbacks = [fallback_model_cfg]

    if effective_fallbacks:
        from myrm_agent_harness.toolkits.llms import FallbackModel

        raw_fallback_llms: list[BaseChatModel] = []
        fallback_models_for_manager: list[FallbackModel] = []

        for fb_cfg in effective_fallbacks:
            try:
                fb_api_keys = getattr(fb_cfg, "api_keys", None)
                fb_llm = await llm_manager.get_llm_from_config(fb_cfg, api_keys=fb_api_keys)
                raw_fallback_llms.append(fb_llm)
                fallback_models_for_manager.append(
                    FallbackModel(
                        llm=fb_llm,
                        name=fb_cfg.model,
                    )
                )
                logger.info("Fallback candidate model: %s", fb_cfg.model)
            except Exception as e:
                logger.warning(f"Failed to create fallback candidate LLM '{fb_cfg.model}': {e}, skipping node")

        if fallback_models_for_manager:
            first_fallback_llm = raw_fallback_llms[0]
            managed_llm = ManagedLLM(
                main_llm=raw_main_llm,
                fallback_models=fallback_models_for_manager,
                main_model_name=model_cfg.model,
                scenario=ScenarioType.BALANCED,
            )
            logger.info(
                "ModelFallbackManager active: main=%s, %d fallback candidate(s)",
                model_cfg.model,
                len(fallback_models_for_manager),
            )
            return managed_llm, lite_llm, first_fallback_llm, safety_fallback_llm, raw_fallback_llms

    return raw_main_llm, lite_llm, None, safety_fallback_llm, None


async def apply_lite_managed_fallback(
    lite_llm: BaseChatModel,
    lite_model_cfg: ModelConfig,
    fallback_lite_model_cfg: ModelConfig | None,
) -> BaseChatModel:
    """Wrap lite LLM with ManagedLLM when a lite fallback is configured.

    Call after apply_lite_context_downgrade so Dynamic Ratio Shield runs first.
    Lite paths use agenerate (extraction/summary), not StreamExecutor graph rebuild.
    """
    if fallback_lite_model_cfg is None:
        return lite_llm

    try:
        fallback_api_keys = getattr(fallback_lite_model_cfg, "api_keys", None)
        raw_lite_fallback = await llm_manager.get_llm_from_config(fallback_lite_model_cfg, api_keys=fallback_api_keys)
        managed_lite = ManagedLLM(
            main_llm=lite_llm,
            fallback_llm=raw_lite_fallback,
            main_model_name=lite_model_cfg.model,
            fallback_model_name=fallback_lite_model_cfg.model,
            scenario=ScenarioType.BALANCED,
        )
        logger.info(
            "Lite ModelFallbackManager active: main=%s, fallback=%s",
            lite_model_cfg.model,
            fallback_lite_model_cfg.model,
        )
        return managed_lite
    except Exception as e:
        logger.warning(
            "Failed to create lite fallback LLM: %s, proceeding without lite failover",
            e,
        )
        return lite_llm


async def apply_lite_context_downgrade(
    main_llm: BaseChatModel,
    lite_llm: BaseChatModel,
    model_cfg: ModelConfig,
    lite_model_cfg: ModelConfig | None = None,
) -> tuple[BaseChatModel, ModelConfig]:
    """Degrade lite LLM to main model when lite context window is too small (Dynamic Ratio Shield).

    Returns the lite LLM instance and the ModelConfig that matches the running instance
    (main config after downgrade, otherwise lite or main when lite is unset).
    """
    from myrm_agent_harness.toolkits.llms.utils.model_utils import (
        get_model_context_limit,
    )

    effective_cfg = lite_model_cfg or model_cfg
    main_limit = get_model_context_limit(main_llm) or 128000
    lite_limit = get_model_context_limit(lite_llm)
    if not lite_limit or not main_limit:
        return lite_llm, effective_cfg

    if lite_limit >= main_limit * 0.85:
        return lite_llm, effective_cfg

    logger.warning(
        "Context capacity mismatch: main model %s (%s tokens) vs lite (%s tokens). Degrading lite LLM to main model.",
        model_cfg.model,
        main_limit,
        lite_limit,
    )
    main_api_keys = getattr(model_cfg, "api_keys", None)
    degraded_cfg = _inject_low_reasoning_effort(model_cfg)
    degraded_llm = await llm_manager.get_llm_from_config(degraded_cfg, api_keys=main_api_keys)
    return degraded_llm, degraded_cfg
