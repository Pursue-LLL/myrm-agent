"""[INPUT]
- app.ai_agents.general_agent.external_agents::ExternalAgentsMixin (POS: 外部 Agent 委托层。负责 RuntimePool 初始化、CLI/ACP 后端注册、)

[OUTPUT]
- ToolSetupBaseMixin: Mixin providing all tool initialization methods for GeneralAgent.

[POS]
各工具族 mixin 共同继承，避免重复声明宿主属性。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..external_agents import ExternalAgentsMixin

if TYPE_CHECKING:
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.ai_agents.agents import (
        ImageGenerationParams,
        TTSParams,
        VideoGenerationParams,
    )
    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


class ToolSetupBaseMixin(ExternalAgentsMixin):
    """Mixin providing all tool initialization methods for GeneralAgent."""

    if TYPE_CHECKING:
        enable_web_search: bool
        enable_web_fetch: bool
        benchmark_blocked_hostnames: tuple[str, ...]
        benchmark_blocked_terms: tuple[str, ...]
        search_service_cfg: SearchServiceConfig | None = None
        reranker_config: RerankerConfig | None
        enable_advanced_retrieval: bool
        embedding_config: EmbeddingConfig | None
        fetch_raw_webpage: bool
        enable_structured_clarify: bool
        image_generation_params: ImageGenerationParams | None
        video_generation_params: VideoGenerationParams | None
        tts_params: TTSParams | None
        chat_id: str | None
        declared_allowed_roots: tuple[str, ...]
        model_cfg: ModelConfig
        search_depth: str
        agent_id: str | None
        memory_require_confirmation: bool
        _lite_llm: object | None
        agent: SkillAgent | None
        approval_session_key: str | None
        _session_vault: object | None
        _browser_session: object | None
        _desktop_session: object | None
        _current_chat_id: str | None
        skill_ids: list[str]
        enable_cron_eager: bool
        enable_wiki: bool
        enable_memory: bool
        enable_conversation_search: bool
        incognito_mode: bool
        unattended_mode: bool
        channel_name: str
        prompt_mode: str
        enable_skill_manage: bool
        force_skill_manage: bool
        agent_security_raw: dict[str, object] | None
        security_config_raw: dict[str, object] | None
        declared_capabilities: tuple[str, ...]
        memory_base_path: str | None
        memory_decay_profile: str | None

        # 跨工具族调用：实现在对应 mixin，组合后由 MRO 解析。
        def _setup_image_generation_tools(
            self, tools: list[object], *, task_user_id: str = "default"
        ) -> None: ...
        def _setup_video_generation_tools(
            self, tools: list[object], *, task_user_id: str = "default"
        ) -> None: ...
        def _setup_tts_tools(self, tools: list[object]) -> None: ...
