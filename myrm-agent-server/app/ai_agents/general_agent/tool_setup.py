"""Tool setup methods for GeneralAgent.

[INPUT]
- myrm_agent_harness.toolkits (POS: 框架工具创建工厂)
- core.memory.adapters.setup (POS: 记忆系统适配器)
- core.browser_vault (POS: 浏览器会话保险库)
- .external_agents::ExternalAgentsMixin (POS: 外部 Agent 委托层)

[OUTPUT]
- ToolSetupMixin: 提供所有工具初始化方法的 Mixin 基类
- _should_mount_ask_question_tool: interactive web_chat clarify mount predicate
- _should_mount_render_ui_tools: inline A2UI mount predicate (WEB_CHAT + web/tauri surface)
- _setup_x_live_search_tool: skill 绑定后 Turn1 eager x_search_tool（独立于 enable_web_search）

[POS]
GeneralAgent 的工具初始化混入。用户开关 ON（`enabled_builtin_tools` / skill 绑定）→ Turn1 eager；
所有内置工具开启即 Turn1 eager，不开即不加载。搜索、媒体生成（AgentDeclared eager →
`media_tools/`）、定时任务、记忆、浏览器等工具的创建逻辑从核心 Agent
类中解耦，保持 agent.py 聚焦于流式执行和生命周期管理。
外部 Agent 委托由 ExternalAgentsMixin 提供。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.artifacts.constants import ArtifactType

from app.core.skills.oauth_availability import X_LIVE_SEARCH_SKILL_ID

from .external_agents import ExternalAgentsMixin

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.browser.captcha.protocols import CaptchaSolver
    from myrm_agent_harness.toolkits.cron.types import DeliveryConfig
    from myrm_agent_harness.toolkits.llms.image.models import MediaCallback
    from myrm_agent_harness.toolkits.memory import MemoryManager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
    from app.core.memory.adapters.types import ResolvedContextBinding
    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


def _should_mount_ask_question_tool(
    *,
    unattended_mode: bool,
    channel_name: str,
    prompt_mode: str,
    enable_structured_clarify: bool,
) -> bool:
    """Return True when structured HITL clarification is safe and product-appropriate."""
    if not enable_structured_clarify:
        return False
    if unattended_mode:
        return False
    if prompt_mode == "search":
        return False
    from myrm_agent_harness.agent.security.channel_presets import (
        ChannelType,
        resolve_channel_type,
    )

    return resolve_channel_type(channel_name) == ChannelType.WEB_CHAT


def _should_mount_render_ui_tools(
    *,
    enable_render_ui: bool,
    channel_name: str,
    client_surface: str | None = None,
) -> bool:
    """Return True when inline A2UI tools are safe and renderable for this session."""
    if not enable_render_ui:
        return False
    from myrm_agent_harness.agent.meta_tools.interaction.inline_ui_capability import (
        resolve_client_surface,
        supports_inline_interactive_ui,
    )
    from myrm_agent_harness.agent.security.channel_presets import resolve_channel_type

    return supports_inline_interactive_ui(
        resolve_channel_type(channel_name),
        client_surface=resolve_client_surface(client_surface),
    )


def _configured_media_api_key(api_key: str | None) -> bool:
    return bool((api_key or "").strip())


def _media_gateway_configured(gateway_config: dict[str, object] | None) -> bool:
    if not gateway_config:
        return False
    use_gateway = bool(gateway_config.get("use_gateway") or gateway_config.get("useGateway"))
    if not use_gateway:
        return False
    auth_token = gateway_config.get("auth_token") or gateway_config.get("authToken")
    gateway_url = gateway_config.get("gateway_url") or gateway_config.get("gatewayUrl")
    return bool(
        auth_token
        and str(auth_token).strip()
        and gateway_url
        and str(gateway_url).strip()
    )


def _is_media_credential_configured(
    api_key: str | None,
    gateway_config: dict[str, object] | None,
) -> bool:
    return _configured_media_api_key(api_key) or _media_gateway_configured(gateway_config)


def _video_generation_credential_configured(params: VideoGenerationParams) -> bool:
    if _is_media_credential_configured(params.api_key, params.gateway_config):
        return True
    return any(
        _configured_media_api_key(str(fb.get("api_key")) if fb.get("api_key") is not None else None)
        for fb in params.fallback_providers
        if isinstance(fb, dict)
    )


class ToolSetupMixin(ExternalAgentsMixin):
    """Mixin providing all tool initialization methods for GeneralAgent."""

    if TYPE_CHECKING:
        enable_web_search: bool
        enable_web_fetch: bool
        enable_web_crawl: bool
        search_service_cfg: SearchServiceConfig | None = None
        reranker_config: RerankerConfig | None
        enable_advanced_retrieval: bool
        embedding_config: EmbeddingConfig | None
        fetch_raw_webpage: bool
        enable_render_ui: bool
        enable_structured_clarify: bool
        image_generation_params: ImageGenerationParams | None
        video_generation_params: VideoGenerationParams | None
        tts_params: TTSParams | None
        chat_id: str | None
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
        _current_thread_id: str | None
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

    def _setup_x_live_search_tool(self, tools: list[object]) -> None:
        """Register eager x_search_tool when x-live-search skill is enabled.

        Independent of enable_web_search — xAI Live Search does not require Tavily/Brave.
        Skill binding is user opt-in; mounted Turn1 like other enabled capabilities.
        """
        if X_LIVE_SEARCH_SKILL_ID not in (self.skill_ids or []):
            return
        try:
            from app.services.integrations.tools.x_live_search import create_x_live_search_tool

            tools.append(create_x_live_search_tool())
            logger.info("Loaded x_search_tool (%s skill) [Turn1]", X_LIVE_SEARCH_SKILL_ID)
        except Exception as e:
            logger.debug("x_search_tool skipped: %s", e)

    def _setup_search_and_basic_tools(self, tools: list[object]) -> None:
        """Set up web fetch (baseline), web search (opt-in), and basic utility tools."""
        from myrm_agent_harness.toolkits import (
            create_web_fetch_tool,
            create_web_search_tool,
        )

        reranker_cfg = self.reranker_config if self.enable_advanced_retrieval else None
        embedding_cfg = self.embedding_config if self.enable_advanced_retrieval else None

        sufficiency_cfg = None
        sufficiency_llm = None
        if self.search_depth == "deep":
            from myrm_agent_harness.api import LLMConfig
            from myrm_agent_harness.toolkits.retriever.sufficiency import SufficiencyConfig

            sufficiency_cfg = SufficiencyConfig(enabled=True)
            sufficiency_llm = LLMConfig(
                model=self.model_cfg.model,
                api_key=self.model_cfg.api_key,
                base_url=self.model_cfg.base_url,
            )

        from app.config.deploy_mode import is_local_mode as _is_local

        if getattr(self, "enable_web_fetch", True):
            tools.append(
                create_web_fetch_tool(
                    reranker_config=reranker_cfg,
                    embedding_config=embedding_cfg,
                    use_raw_markdown=self.fetch_raw_webpage,
                    allow_private_networks=_is_local(),
                    sufficiency_config=sufficiency_cfg,
                    sufficiency_llm_config=sufficiency_llm,
                )
            )
            logger.info("Loaded web_fetch_tool [Turn1 baseline, no search API required]")

        if self.enable_web_search and self.search_service_cfg:
            tools.append(
                create_web_search_tool(
                    self.search_service_cfg,
                    reranker_config=reranker_cfg,
                    sufficiency_config=sufficiency_cfg,
                    sufficiency_llm_config=sufficiency_llm,
                )
            )

            logger.info(
                f"🔍 已加载 web_search_tool "
                f"(advanced_retrieval={'ON' if self.enable_advanced_retrieval else 'OFF'})"
            )

        self._setup_x_live_search_tool(tools)

        if _should_mount_render_ui_tools(
            enable_render_ui=self.enable_render_ui,
            channel_name=getattr(self, "channel_name", "web_chat"),
            client_surface=getattr(self, "client_surface", None),
        ):
            from myrm_agent_harness.agent.meta_tools.interaction.a2ui_spec import (
                seed_reference_to_workspace,
            )
            from myrm_agent_harness.agent.meta_tools.interaction.render_ui_tool import (
                render_ui_tool,
            )
            from myrm_agent_harness.agent.meta_tools.interaction.update_ui_data_tool import (
                update_ui_data_tool,
            )

            workspace_roots: tuple[str, ...] = getattr(self, "declared_allowed_roots", ())
            if workspace_roots:
                try:
                    seed_reference_to_workspace(Path(workspace_roots[0]))
                except OSError as exc:
                    logger.warning("Failed to seed A2UI reference to workspace: %s", exc)

            tools.append(render_ui_tool)
            tools.append(update_ui_data_tool)
            logger.info("🎨 已加载 render_ui_tool / update_ui_data_tool（交互式 UI）[Turn1]")

        self._setup_image_generation_tools(
            tools,
            task_user_id=getattr(self, "_task_user_id", "default"),
        )
        self._setup_video_generation_tools(
            tools,
            task_user_id=getattr(self, "_task_user_id", "default"),
        )
        self._setup_tts_tools(tools)

    def _setup_web_crawl_tool(
        self,
        tools: list[object],
        *,
        chat_id: str | None = None,
        workspace_root: str | None = None,
    ) -> None:
        """Register web_crawl_tool when enabled (EXTENDED, opt-in)."""
        if not getattr(self, "enable_web_crawl", False):
            return
        from myrm_agent_harness.api.hooks import create_web_crawl_tool

        from app.config.deploy_mode import is_local_mode as _is_local

        data_dir: str | None = None
        if workspace_root and chat_id:
            data_dir = str(Path(workspace_root) / ".crawl" / chat_id)

        tools.append(
            create_web_crawl_tool(
                allow_private_networks=_is_local(),
                data_dir=data_dir,
            )
        )
        logger.info("Loaded web_crawl_tool [EXTENDED opt-in]")

    def _setup_clarification_tools(self, tools: list[object]) -> None:
        """Set up ask_question HITL clarification tool for interactive web_chat sessions."""
        if not _should_mount_ask_question_tool(
            unattended_mode=getattr(self, "unattended_mode", False),
            channel_name=getattr(self, "channel_name", "web_chat"),
            prompt_mode=getattr(self, "prompt_mode", "full"),
            enable_structured_clarify=getattr(self, "enable_structured_clarify", False),
        ):
            return

        try:
            import json

            from myrm_agent_harness.agent.meta_tools.clarification.ask_question import AskQuestionInput
            from myrm_agent_harness.agent.meta_tools.clarification.clarification_agent_tools import (
                create_ask_question_tool,
            )

            async def _on_ask_question(form: AskQuestionInput) -> str:
                from langgraph.types import interrupt

                payload = {"type": "ask_question", "form": form.model_dump()}

                # Use LangGraph's native interrupt to suspend execution statelessly
                response = interrupt(payload)

                if not response:
                    return (
                        "User did not answer the clarification (skipped or timed out). "
                        "Proceed with your best judgment; do not wait for further input."
                    )

                return json.dumps(response, ensure_ascii=False)

            tools.append(create_ask_question_tool(_on_ask_question))
            logger.info("🙋 已加载 ask_question_tool (交互式澄清表单)")
        except Exception as e:
            logger.warning(f"⚠️ ask_question_tool 加载失败: {e}")

    def _setup_image_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register image generation/editing tools if configured (AgentDeclared eager mount)."""
        if not self.image_generation_params:
            return

        params = self.image_generation_params
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("Image generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.image import (
                ImageGenerationConfig,
                ImageGenerationTools,
            )

            from app.ai_agents.media_tools.image_agent_tool import create_image_generation_tool
            from app.ai_agents.media_tools.media_persist import create_media_persist_callback
            from app.config.deploy_mode import is_local_mode

            chat_id = self.chat_id or getattr(self, "_current_chat_id", None)
            agent_id = getattr(self, "agent_id", None)
            config = ImageGenerationConfig(
                model=params.model,
                api_key=params.api_key,
                fallback_models=params.fallback_models,
                default_size=params.default_size,
                default_quality=params.default_quality,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=params.gateway_config,
                media_callback=create_media_persist_callback(
                    chat_id=chat_id,
                    model_name=params.model,
                    source="generate",
                ),
            )
            img_engine = ImageGenerationTools(
                config,
                allow_private_networks=is_local_mode(),
                on_artifact_created=_get_artifact_push_fn(),
            )
            tools.append(
                create_image_generation_tool(
                    img_engine,
                    allow_private_networks=is_local_mode(),
                    async_config=config,
                    task_user_id=task_user_id,
                    agent_id=agent_id,
                    chat_id=chat_id,
                )
            )
            logger.warning(
                "🖼️ Image generation tool loaded (model=%s, fallbacks=%s) [AgentDeclared]",
                params.model,
                params.fallback_models,
            )
        except Exception as e:
            logger.warning("⚠️ Image generation tools failed to load: %s", e)

    def _setup_video_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register video generation tools if configured (AgentDeclared eager mount)."""
        if not self.video_generation_params:
            return

        params = self.video_generation_params
        if not _video_generation_credential_configured(params):
            logger.debug("Video generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.video import (
                VideoGenerationConfig,
                VideoGenerationTools,
            )

            from app.ai_agents.media_tools.video_agent_tool import create_video_generation_tool

            fallback_configs = []
            for fb in params.fallback_providers:
                fallback_configs.append(
                    VideoGenerationConfig(
                        provider=fb.get("provider", "openai"),
                        model=fb.get("model", "sora"),
                        api_key=fb.get("api_key"),
                        gateway_config=params.gateway_config,
                    )
                )

            config = VideoGenerationConfig(
                provider=params.provider,
                model=params.model,
                api_key=params.api_key,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                fallback_configs=fallback_configs,
                default_aspect_ratio=params.default_aspect_ratio,
                default_resolution=params.default_resolution,
                default_duration_seconds=params.default_duration_seconds,
                gateway_config=params.gateway_config,
                media_callback=self._create_video_media_callback(),
            )
            video_engine = VideoGenerationTools(
                config,
                on_artifact_created=_get_artifact_push_fn(),
            )
            tools.append(
                create_video_generation_tool(
                    video_engine,
                    async_config=config,
                    task_user_id=task_user_id,
                    agent_id=getattr(self, "agent_id", None),
                    chat_id=self.chat_id or getattr(self, "_current_chat_id", None),
                )
            )
            logger.warning(
                "🎬 Video generation tool loaded (provider=%s, model=%s) [AgentDeclared]",
                params.provider,
                params.model,
            )
        except Exception as e:
            logger.warning("⚠️ Video generation tools failed to load: %s", e)

    def _create_video_media_callback(self) -> MediaCallback | None:
        """Create a media_callback for persisting generated videos to the media library."""
        return self._create_media_persist_callback(
            model_name=(self.video_generation_params.model if self.video_generation_params else None),
            source="video_generate",
        )

    def _setup_tts_tools(self, tools: list[object]) -> None:
        """Register TTS tools if configured (AgentDeclared eager mount)."""
        if not self.tts_params:
            return

        params = self.tts_params
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("TTS tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.tts import TTSConfig

            from app.ai_agents.media_tools.tts_agent_tool import create_tts_tool

            config = TTSConfig(
                provider=params.provider,
                model=params.model,
                voice=params.voice,
                api_key=params.api_key,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=params.gateway_config,
                media_callback=self._create_tts_media_callback(),
            )
            tts_tool = create_tts_tool(
                config,
                on_artifact_created=_get_artifact_push_fn(),
            )
            tools.append(tts_tool)
            logger.warning(
                "🔊 TTS tool loaded (provider=%s, model=%s, voice=%s) [AgentDeclared]",
                params.provider,
                params.model,
                params.voice,
            )
        except Exception as e:
            logger.warning("⚠️ TTS tool failed to load: %s", e)

    def _create_tts_media_callback(self) -> MediaCallback | None:
        """Create a media_callback for persisting generated audio to the media library."""
        return self._create_media_persist_callback(
            model_name=(self.tts_params.model if self.tts_params else None),
            source="tts_generate",
        )

    def _create_media_persist_callback(
        self,
        *,
        model_name: str | None,
        source: str,
    ) -> MediaCallback | None:
        """Generic media persist callback factory."""
        from app.ai_agents.media_tools.media_persist import create_media_persist_callback

        chat_id = self._current_chat_id if hasattr(self, "_current_chat_id") else self.chat_id
        return create_media_persist_callback(
            chat_id=chat_id,
            model_name=model_name,
            source=source,
        )

    def _resolve_cron_default_delivery(self) -> DeliveryConfig | None:
        """Default IM delivery when creating cron jobs from a messaging channel."""
        from myrm_agent_harness.toolkits.cron.types import DeliveryConfig

        channel = getattr(self, "channel_name", "web_chat")
        if channel in ("web_chat", "cron", "subagent"):
            return None

        from myrm_agent_harness.agent.security.channel_presets import ChannelType, resolve_channel_type

        if resolve_channel_type(channel) == ChannelType.WEB_CHAT:
            return None

        recipient = getattr(self, "memory_conversation_id", None) or getattr(self, "chat_id", None)
        if not recipient:
            return None
        return DeliveryConfig(channel=channel, target=str(recipient))

    async def _setup_cron_tools(
        self,
        tools: list[object],
        user_id: str | None = None,
    ) -> None:
        """Set up scheduled task (cron) tools as Turn1 eager.

        Only called when ``enable_cron_eager=True`` (user opted in).
        """
        try:
            if not user_id:
                logger.warning("Cron tools load skipped: user_id is missing")
                return

            from myrm_agent_harness.toolkits import create_cron_tools

            from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery
            from app.core.cron.adapters.setup import get_cron_manager
            from app.core.cron.blueprints import (
                BlueprintFillError,
                fill_blueprint,
                get_blueprints_for_tool_description,
            )

            agent_locale = getattr(self, "locale", None) or "en"

            def _blueprint_filler(
                bp_id: str, values: dict[str, str], tz: str | None
            ) -> tuple[dict[str, str | int | None], str, str, tuple[str, ...], tuple[str, ...] | None] | None:
                try:
                    result = fill_blueprint(bp_id, values, locale=agent_locale, tz=tz)
                except BlueprintFillError as exc:
                    raise ValueError(str(exc)) from exc
                if not result:
                    return None
                sched = result.schedule
                sched_dict: dict[str, str | int | None] = {
                    "kind": sched.kind,
                    "expr": sched.expr,
                    "tz": sched.tz,
                    "interval_ms": sched.interval_ms,
                }
                return (
                    sched_dict,
                    result.prompt,
                    result.name,
                    result.required_capabilities,
                    result.tools_allowed,
                )

            cron_tools = create_cron_tools(
                get_cron_manager(),
                user_id=user_id,
                current_model=self.model_cfg.model,
                chat_id=self.chat_id,
                agent_id=self.agent_id,
                blueprint_filler=_blueprint_filler,
                blueprint_catalog_provider=lambda: get_blueprints_for_tool_description(agent_locale),
                delivery_resolver=resolve_cron_delivery,
                default_delivery=self._resolve_cron_default_delivery(),
            )
            tools.extend(cron_tools)
            logger.info("Loaded %d cron tools [Turn1 eager]", len(cron_tools))
        except Exception as e:
            logger.warning(f"Cron tools load failed (degraded): {e}")

    async def _create_memory_tools(
        self,
        tools: list[object],
        binding: ResolvedContextBinding,
    ) -> MemoryManager | None:
        """Create memory tools. Returns MemoryManager on success, None on failure."""
        try:
            from myrm_agent_harness.toolkits import create_memory_tools

            from app.core.memory.adapters.setup import create_conflict_callback, create_memory_manager

            if self.embedding_config is None:
                logger.warning("⚠️ 记忆工具未加载（缺少 embedding_config）")
                return None

            time_decay_half_life_days = 90.0
            if self.memory_decay_profile == "permanent":
                time_decay_half_life_days = 3650.0
            elif self.memory_decay_profile == "fast":
                time_decay_half_life_days = 7.0

            on_conflict = create_conflict_callback(agent_id=self.agent_id)
            manager = await create_memory_manager(
                binding,
                self.embedding_config,
                approval_required=self.memory_require_confirmation,
                dedup_llm=self._lite_llm,
                time_decay_half_life_days=time_decay_half_life_days,
                on_conflict=on_conflict,
            )

            from myrm_agent_harness.toolkits.memory.memory_search_policy import (
                MemorySearchBackends,
                MemorySearchPolicy,
            )

            search_policy = MemorySearchPolicy(
                allow_wiki=bool(self.enable_wiki and not self.incognito_mode),
                allow_sessions=bool(self.enable_conversation_search and not self.incognito_mode),
            )
            query_wiki = None
            conversation_provider = None
            if search_policy.allow_wiki and self._lite_llm is not None:
                from app.services.wiki.vault_service import get_wiki_archiver

                lite_llm = self._lite_llm

                async def _query_wiki(question: str) -> str:
                    archiver = get_wiki_archiver(lite_llm, manager, agent_id=self.agent_id)
                    return await archiver.query_wiki(question)

                query_wiki = _query_wiki
            if search_policy.allow_sessions:
                from app.services.chat.conversation_search_service import ConversationHistorySearchProvider

                conversation_provider = ConversationHistorySearchProvider(
                    current_chat_id=binding.conversation_id,
                    agent_id=self.agent_id,
                    memory_manager=manager,
                )
            search_backends = MemorySearchBackends(
                query_wiki=query_wiki,
                conversation_provider=conversation_provider,
            )
            memory_tools = create_memory_tools(
                manager,
                search_policy=search_policy,
                search_backends=search_backends,
            )
            # Memory tools are high frequency for a personal assistant, keep them in tools
            tools.extend(memory_tools)
            logger.warning(
                "🧠 已加载 %d 个记忆工具 (approval=%s, channel=%s, conversation=%s)",
                len(memory_tools),
                manager.approval_required,
                binding.channel_id or "",
                binding.conversation_id or "",
            )
            return manager
        except Exception as e:
            logger.warning(f"⚠️ 记忆工具加载失败（功能降级）: {e}")
            return None

    async def _setup_browser_tools(
        self,
        tools: list[object],
        effective_chat_id: str,
        vision_llm: "BaseChatModel" | None = None,
        memory_manager: object | None = None,
    ) -> None:
        """Set up browser automation tools and session."""
        try:
            from myrm_agent_harness.toolkits import create_browser_tools
            from myrm_agent_harness.toolkits.browser import (
                BrowserSession,
                DomainAllowlist,
            )
            from myrm_agent_harness.toolkits.browser.pool import (
                ContextType,
                get_global_browser_pool,
            )

            from app.config.browser import get_browser_launch_options, get_browser_pool_config
            from app.config.deploy_mode import is_local_mode
            from app.core.security.browser_vault import get_agent_session_vault, get_global_session_vault

            pool = get_global_browser_pool(
                config=get_browser_pool_config(),
                launch_options=get_browser_launch_options(),
            )
            if self.agent_id and self.agent_id != "default":
                self._session_vault = get_agent_session_vault(self.agent_id)
            else:
                self._session_vault = get_global_session_vault()

            domain_allowlist = None
            domain_blocklist = None
            # BrowserSession is created before BaseAgent init (self.agent is still None).
            # Resolve merged network policy the same way SecurityPolicyExtension does.
            from myrm_agent_harness.agent.security.channel_presets import (
                build_channel_security_config,
            )

            merged_security = build_channel_security_config(
                self.channel_name,
                self.security_config_raw,
                agent_security_raw=self.agent_security_raw,
                declared_capabilities=self.declared_capabilities,
                declared_allowed_roots=self.declared_allowed_roots,
                local_mode=is_local_mode(),
            )
            if merged_security.network_allowlist:
                domain_allowlist = DomainAllowlist.from_strings(merged_security.network_allowlist)
            if merged_security.network_blocklist:
                domain_blocklist = DomainAllowlist.from_strings(merged_security.network_blocklist)

            thread_id = self.approval_session_key or f"chat_{effective_chat_id}"
            self._current_thread_id = thread_id

            # Determine context_key for browser session
            # 1. Custom Agents (have agent_id) should share browser state across chats
            # 2. Default/Temporary agents fallback to thread_id (chat session)
            if self.agent_id and self.agent_id != "default":
                browser_context_key = f"agent_{self.agent_id}"
            else:
                browser_context_key = thread_id

            from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
            from myrm_agent_harness.toolkits.browser.observability import (
                BrowserObservability,
                RecordingConfig,
            )

            observability: BrowserObservability | None = None
            recording_mode = getattr(self, "session_recording", None)
            if recording_mode and recording_mode != "off":
                from app.config.settings import get_settings

                recordings_dir = str(Path(get_settings().database.harness_dir) / "recordings")
                observability = BrowserObservability(
                    RecordingConfig(
                        enabled=True,
                        output_dir=recordings_dir,
                        save_on_failure=True,
                        save_on_success=(recording_mode == "always"),
                    )
                )

            from app.services.extension.bridge import get_extension_bridge

            ext_bridge = get_extension_bridge() if not is_local_mode() else None

            browser_session = BrowserSession(
                pool,
                ContextType.AGENT,
                context_key=browser_context_key,
                session_vault=self._session_vault,
                observability=observability,
                domain_allowlist=domain_allowlist,
                domain_blocklist=domain_blocklist,
                captcha_solver=await self._build_captcha_solver(),
                content_vault=ArtifactVault(os.getcwd()),
                vision_llm=vision_llm,
                extension_bridge=ext_bridge,
                allow_private_networks=is_local_mode(),
                auto_restore_domains=getattr(self, "auto_restore_domains", []),
                engine_preference=None,
                launch_mode_preference=getattr(self, "browser_source", None),
                dialog_policy=getattr(self, "dialog_policy", None),
            )

            if memory_manager is not None:
                from myrm_agent_harness.toolkits.browser.session import SessionMemoryBridge

                bridge = SessionMemoryBridge(memory_manager)
                browser_session.set_session_lifecycle_hook(bridge)
                logger.info("SessionMemoryBridge wired: browser sessions → memory profile")

            logger.warning(f"BrowserSession created: context_key={browser_context_key} (thread_id={thread_id})")

            browser_tools = create_browser_tools(browser_session)
            # Browser tools are high frequency if enabled
            tools.extend(browser_tools)
            self._browser_session = browser_session
            logger.info(f"Loaded {len(browser_tools)} browser tools")
        except Exception as e:
            logger.warning(f"Browser tools load failed (degraded): {e}")

    async def _build_captcha_solver(self) -> CaptchaSolver:
        """Build the CAPTCHA solver based on user configuration.

        Returns FallbackSolver(ApiSolver, ManualSolver) if configured,
        otherwise plain ManualSolver (preserving existing behavior).
        """
        from myrm_agent_harness.toolkits.browser.captcha import (
            ApiSolver,
            FallbackSolver,
            ManualSolver,
        )

        capsolver_key = await self._get_capsolver_api_key()
        if capsolver_key:
            return FallbackSolver(ApiSolver(capsolver_key), ManualSolver())
        return ManualSolver()

    async def _get_capsolver_api_key(self) -> str | None:
        """Read CapSolver API key from user config (DB-stored, encrypted)."""
        try:
            from app.services.config.service import config_service

            record = await config_service.get("captchaSolverConfig")
            if record and isinstance(record.value, dict):
                if record.value.get("enabled") and record.value.get("api_key"):
                    return str(record.value["api_key"])
        except Exception:
            pass
        return None

    def _setup_computer_use_tools(self, tools: list[object]) -> None:
        """Set up system-wide computer use tools (screenshot + action)."""
        try:
            from myrm_agent_harness.toolkits.computer_use import (
                create_desktop_session,
                create_desktop_tools,
            )
            from myrm_agent_harness.toolkits.computer_use.types import (
                ComputerUseConfig,
                ExecutionMode,
            )

            from app.ai_agents.desktop_control.gate import DesktopControlGate
            from app.config.computer_use_deploy import is_computer_use_deploy_supported
            from app.config.deploy_mode import is_local_mode, is_sandbox

            constraints = _select_image_constraints(self.model_cfg.model)
            workspace_root = (
                self.declared_allowed_roots[0] if getattr(self, "declared_allowed_roots", ()) else None
            )
            auto_grant = is_sandbox() and is_computer_use_deploy_supported() and not is_local_mode()
            execution_mode = (
                ExecutionMode.background_strict
                if is_local_mode()
                else ExecutionMode.background_best_effort
            )
            gate = DesktopControlGate(workspace_root=workspace_root, auto_grant=auto_grant)
            config_kwargs: dict[str, object] = {"execution_mode": execution_mode}
            if constraints:
                config_kwargs["image_constraints"] = constraints
            config = ComputerUseConfig(**config_kwargs)
            session = create_desktop_session(config=config, permission_callback=gate)
            computer_tools = create_desktop_tools(session)
            tools.extend(computer_tools)
            self._desktop_session = session
            logger.warning(
                "Loaded %d desktop control tools (model=%s, mode=%s, max_edge=%dpx) [Turn1]",
                len(computer_tools),
                self.model_cfg.model,
                execution_mode.value,
                session._config.image_constraints.max_edge_px,
            )
        except Exception as e:
            logger.warning("Computer use tools load failed (degraded): %s", e)

def _select_image_constraints(model_name: str) -> object | None:
    """Select optimal ImageConstraints based on model family.

    Returns None to use defaults (Claude constraints).
    """
    from myrm_agent_harness.toolkits.computer_use.types import (
        CLAUDE_OPUS_47_IMAGE_CONSTRAINTS,
        GPT4V_IMAGE_CONSTRAINTS,
    )

    model_lower = model_name.lower()

    if any(k in model_lower for k in ("gpt-4", "gpt4", "o1", "o3", "o4")):
        return GPT4V_IMAGE_CONSTRAINTS

    if "opus-4" in model_lower or "claude-opus-4" in model_lower:
        return CLAUDE_OPUS_47_IMAGE_CONSTRAINTS

    return None


def _get_artifact_push_fn() -> Callable[[str, str, ArtifactType, str], None] | None:
    """Create an artifact push callback for image/video generation tools.

    Returns the ``push_inline_artifact`` function from the agent layer,
    or ``None`` when the agent runtime is unavailable.
    """
    try:
        from myrm_agent_harness.agent.artifacts import push_inline_artifact

        def _push(filename: str, preview_url: str, artifact_type: ArtifactType, content_type: str) -> None:
            push_inline_artifact(
                filename=filename,
                preview_url=preview_url,
                artifact_type=artifact_type,
                content_type=content_type,
            )

        return _push
    except Exception:
        return None
