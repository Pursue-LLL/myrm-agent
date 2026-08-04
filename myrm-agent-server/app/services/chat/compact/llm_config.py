"""LLM resolution for compaction.

[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs (POS: user model config)
- myrm_agent_harness.toolkits.llms::llm_manager (POS: LLM factory)

[OUTPUT]
- get_llm_for_user: compaction LLM + max_context_tokens for summarize + anti-thrash window

[POS]
Resolves the user's configured model for ``compact_chat`` summarize calls.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel


async def get_llm_for_user() -> tuple[BaseChatModel, int]:
    """Get LLM instance and real context window for user's configured model."""
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()
    model_cfg = configs.model_cfg

    llm: BaseChatModel = await llm_manager.get_llm_from_config(
        model_cfg, streaming=True, api_keys=getattr(model_cfg, "api_keys", None)
    )
    return llm, model_cfg.max_context_tokens or 128000
