"""[INPUT]
- app.ai_agents.general_agent.external_agents::ExternalAgentsMixin (POS: 外部 Agent 委托层。负责 RuntimePool 初始化、CLI/ACP 后端注册、 本地模式自动检测（请求热路径使用 path-only 探测，版本探测留给设置态）， 以及绕过 LangChain 直接向前端流式转发外部 Agent 事件。)
- app.core.agent.tool_description_locale::resolve_tool_description_locale (POS: locale a tool description is rendered in)

[OUTPUT]
- ToolSetupBaseMixin: Mixin providing all tool initialization methods for GeneralAgent.

[POS]
各工具族 mixin 共同继承，避免重复声明宿主属性；并提供各工具族共用的宿主安全策略解析（`_merged_security_config`）
与工具描述语言解析（`_tool_description_locale`）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..external_agents import ExternalAgentsMixin

if TYPE_CHECKING:
    from myrm_agent_harness.agent.security.types import SecurityConfig
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.memory.config import RecallMode
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
        memory_recall_mode: RecallMode

        # 跨工具族调用：实现在对应 mixin，组合后由 MRO 解析。
        def _setup_image_generation_tools(self, tools: list[object], *, task_user_id: str = "default") -> None: ...
        def _setup_video_generation_tools(self, tools: list[object], *, task_user_id: str = "default") -> None: ...
        def _setup_tts_tools(self, tools: list[object]) -> None: ...

    def _merged_security_config(self) -> SecurityConfig:
        """The channel preset with the user's and the agent's overrides, as ``SecurityPolicyExtension`` resolves it.

        Tool families that carry their own network policy read it here: the browser builds its domain lists once, the
        web fetch tool reads the blocklist on every call, so a list edited mid-session applies to the next fetch.
        """
        from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config

        from app.config.deploy_mode import is_local_mode

        return build_channel_security_config(
            self.channel_name,
            self.security_config_raw,
            agent_security_raw=self.agent_security_raw,
            declared_capabilities=self.declared_capabilities,
            declared_allowed_roots=self.declared_allowed_roots,
            local_mode=is_local_mode(),
        )

    def _tool_description_locale(self) -> str:
        """The language the harness writes tool descriptions in for this session.

        The session language leads; an IM channel without one gets the channel's default, which is how a Feishu session
        reads Chinese descriptions.
        """
        from app.core.agent.tool_description_locale import resolve_tool_description_locale

        # getattr: a host that mounts only some tool families may carry no language attributes.
        return resolve_tool_description_locale(
            agent_locale=getattr(self, "locale", None),
            channel=getattr(self, "channel_name", None),
        )
