"""LLM instance resolution for services and API layers (WebUI provider config).

[INPUT]
app.core.channel_bridge.config_loader (POS: WebUI 用户配置加载)
app.core.channel_bridge.model_resolver (POS: LiteLLM 模型名解析)

[OUTPUT]
get_llm_for_user / get_optional_llm_for_user

[POS]
服务层 LLM 访问入口；api.dependencies 仅 re-export。
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel


async def get_llm_for_user(model_id: str | None = None) -> BaseChatModel:
    """Return an LLM instance configured from WebUI provider settings."""
    from myrm_agent_harness.toolkits.llms import llm_manager

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.model_resolver import resolve_model_config

    configs = await load_user_configs()

    if model_id:
        model_cfg = resolve_model_config(configs.providers_dict, model_override=model_id)
    else:
        model_cfg = configs.model_cfg

    llm: BaseChatModel = await llm_manager.get_llm_from_config(
        model_cfg, streaming=False, api_keys=getattr(model_cfg, "api_keys", None)
    )
    return llm


async def get_optional_llm_for_user(model_id: str | None = None) -> BaseChatModel:
    """Return an LLM instance or a dummy model when provider config is missing."""
    try:
        return await get_llm_for_user(model_id)
    except Exception:
        from typing import Any

        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import BaseMessage
        from langchain_core.outputs import ChatResult

        class DummyChatModel(BaseChatModel):
            def _generate(
                self,
                messages: list[BaseMessage],
                stop: list[str] | None = None,
                run_manager: Any | None = None,
                **kwargs: Any,
            ) -> ChatResult:
                raise NotImplementedError("LLM is not configured")

            @property
            def _llm_type(self) -> str:
                return "dummy"

        return DummyChatModel()
