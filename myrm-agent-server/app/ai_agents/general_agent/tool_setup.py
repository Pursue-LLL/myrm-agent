"""Tool setup methods for GeneralAgent.

[INPUT]
- myrm_agent_harness.toolkits (POS: 框架工具创建工厂)
- core.memory.adapters.setup (POS: 记忆系统适配器)
- core.browser_vault (POS: 浏览器会话保险库)
- .external_agents::ExternalAgentsMixin (POS: 外部 Agent 委托层)

[OUTPUT]
- ToolSetupMixin: 提供所有工具初始化方法的 Mixin 基类

[POS]
GeneralAgent 的工具初始化混入。将搜索、图片/视频生成、
定时任务、记忆、浏览器等工具的创建逻辑从核心 Agent
类中解耦，保持 agent.py 聚焦于流式执行和生命周期管理。
外部 Agent 委托由 ExternalAgentsMixin 提供。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.core.artifacts.constants import ArtifactType

from .external_agents import ExternalAgentsMixin

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.agent.skill_agent import SkillAgent
    from myrm_agent_harness.toolkits.llms.image.models import MediaCallback, MediaMeta
    from myrm_agent_harness.toolkits.memory import MemoryManager
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
    from app.core.memory.adapters.types import ResolvedContextBinding
    from app.core.types import ModelConfig

logger = logging.getLogger(__name__)


class ToolSetupMixin(ExternalAgentsMixin):
    """Mixin providing all tool initialization methods for GeneralAgent."""

    if TYPE_CHECKING:
        enable_web_search: bool
        search_service_cfg: SearchServiceConfig | None = None
        reranker_config: RerankerConfig | None
        enable_advanced_retrieval: bool
        embedding_config: EmbeddingConfig | None
        fetch_raw_webpage: bool
        enable_render_ui: bool
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

    def _setup_search_and_basic_tools(self, tools: list[object], deferred_tools: list[object]) -> None:
        """Set up web search, web fetch, and basic utility tools."""
        from myrm_agent_harness.toolkits import (
            create_image_search_tool,
            create_web_fetch_tool,
            create_web_search_tool,
        )

        if self.enable_web_search and self.search_service_cfg:
            reranker_cfg = self.reranker_config if self.enable_advanced_retrieval else None
            embedding_cfg = self.embedding_config if self.enable_advanced_retrieval else None

            sufficiency_cfg = None
            sufficiency_llm = None
            if self.search_depth == "deep":
                from myrm_agent_harness.core.config.llm import LLMConfig
                from myrm_agent_harness.toolkits.retriever.sufficiency import SufficiencyConfig

                sufficiency_cfg = SufficiencyConfig(enabled=True)
                sufficiency_llm = LLMConfig(
                    model=self.model_cfg.model,
                    api_key=self.model_cfg.api_key,
                    base_url=self.model_cfg.base_url,
                )

            tools.append(
                create_web_search_tool(
                    self.search_service_cfg,
                    reranker_config=reranker_cfg,
                    sufficiency_config=sufficiency_cfg,
                    sufficiency_llm_config=sufficiency_llm,
                )
            )
            from app.config.deploy_mode import is_local_mode as _is_local

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
            try:
                tools.append(create_image_search_tool())
            except Exception:
                logger.info("image_search_tool skipped (ddgs not installed)")

            # Optional: X/Twitter search via xAI Live Search API
            try:
                from app.services.agent.platform_config import resolve_xai_search_config

                from .tools.x_search_provider import (
                    XSearchProviderConfig,
                    create_x_search_tool,
                )

                xai_creds = resolve_xai_search_config(self.providers_dict)
                if xai_creds:
                    api_key, base_url = xai_creds
                    tools.append(create_x_search_tool(XSearchProviderConfig(api_key=api_key, base_url=base_url)))
                    logger.info("🐦 已加载 x_search_tool (xAI Live Search)")
            except Exception as e:
                logger.debug("x_search_tool skipped: %s", e)

            logger.info(
                f"🔍 已加载 web_search_tool 和 web_fetch_tool "
                f"(advanced_retrieval={'ON' if self.enable_advanced_retrieval else 'OFF'})"
            )

        if self.enable_render_ui:
            from myrm_agent_harness.toolkits.interaction.render_ui_tool import (
                render_ui_tool,
            )

            deferred_tools.append(render_ui_tool)
            logger.info("🎨 已加载 render_ui_tool（交互式 UI 渲染）[Deferred]")

        self._setup_image_generation_tools(deferred_tools)
        self._setup_video_generation_tools(deferred_tools)
        self._setup_tts_tools(deferred_tools)

    def _setup_interaction_tools(self, tools: list[object], deferred_tools: list[object]) -> None:
        """Set up human-in-the-loop interaction tools."""
        try:
            from myrm_agent_harness.toolkits.interaction.clipboard_tools import (
                write_to_clipboard,
            )

            tools.append(write_to_clipboard)
            logger.info("📋 已加载 write_to_clipboard")
        except Exception as e:
            logger.warning(f"⚠️ write_to_clipboard 加载失败: {e}")

        if "ask_question_tool" not in self.declared_capabilities:
            return

        try:
            import json

            from myrm_agent_harness.toolkits.interaction.ask_question import (
                AskQuestionInput,
                AskQuestionTool,
            )

            async def _on_ask_question(form: AskQuestionInput) -> str:
                from langgraph.types import interrupt

                payload = {"type": "ask_question", "form": form.model_dump()}

                # Use LangGraph's native interrupt to suspend execution statelessly
                response = interrupt(payload)

                if not response:
                    return "User skipped the clarification. Please proceed with your best judgment or ask a different question."

                return json.dumps(response, ensure_ascii=False)

            tools.append(AskQuestionTool(callback=_on_ask_question))
            logger.info("🙋 已加载 ask_question_tool (交互式澄清表单)")
        except Exception as e:
            logger.warning(f"⚠️ ask_question_tool 加载失败: {e}")

    def _setup_image_generation_tools(self, deferred_tools: list[object]) -> None:
        """Register image generation/editing tools if configured."""
        if not self.image_generation_params:
            return

        try:
            from myrm_agent_harness.toolkits.llms.image import (
                ImageGenerationConfig,
                ImageGenerationTools,
            )

            params = self.image_generation_params
            config = ImageGenerationConfig(
                model=params.model,
                api_key=params.api_key,
                fallback_models=params.fallback_models,
                default_size=params.default_size,
                default_quality=params.default_quality,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=params.gateway_config,
                media_callback=self._create_media_library_callback(),
            )
            img_tools = ImageGenerationTools(
                config,
                on_artifact_created=_get_artifact_push_fn(),
            )
            deferred_tools.append(img_tools)
            logger.warning(
                "🖼️ Image generation tools loaded (model=%s, fallbacks=%s) [Deferred]",
                params.model,
                params.fallback_models,
            )
        except Exception as e:
            logger.warning("⚠️ Image generation tools failed to load: %s", e)

    def _create_media_library_callback(self) -> MediaCallback | None:
        """Create a media_callback for persisting images to the media library."""
        return self._create_media_persist_callback(
            model_name=(self.image_generation_params.model if self.image_generation_params else None),
            source="generate",
        )

    def _setup_video_generation_tools(self, deferred_tools: list[object]) -> None:
        """Register video generation tools if configured."""
        if not self.video_generation_params:
            return

        try:
            from myrm_agent_harness.toolkits.llms.video import (
                VideoGenerationConfig,
                VideoGenerationTools,
            )

            params = self.video_generation_params
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
            video_tools = VideoGenerationTools(
                config,
                on_artifact_created=_get_artifact_push_fn(),
            )
            deferred_tools.append(video_tools)
            logger.warning(
                "🎬 Video generation tools loaded (provider=%s, model=%s) [Deferred]",
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

    def _setup_tts_tools(self, deferred_tools: list[object]) -> None:
        """Register TTS tools if configured."""
        if not self.tts_params:
            return

        try:
            from myrm_agent_harness.toolkits.tts import TTSConfig, TTSTool

            params = self.tts_params
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
            tts_tool = TTSTool(
                config,
                on_artifact_created=_get_artifact_push_fn(),
            )
            deferred_tools.append(tts_tool)
            logger.warning(
                "🔊 TTS tool loaded (provider=%s, model=%s, voice=%s) [Deferred]",
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
        chat_id = self._current_chat_id if hasattr(self, "_current_chat_id") else self.chat_id

        async def _persist(
            media_bytes: bytes,
            mime_type: str,
            meta: MediaMeta,
        ) -> str:
            try:
                from app.core.media.service import media_library_service
                from app.platform_utils import get_session_factory, get_storage_provider

                storage = get_storage_provider()
                factory = get_session_factory()

                async with factory() as session:
                    record = await media_library_service.save_media(
                        session,
                        image_bytes=media_bytes,
                        content_type=mime_type,
                        prompt=meta.prompt,
                        model=meta.model or model_name,
                        resolution=meta.resolution,
                        source=source,
                        session_id=chat_id,
                    )
                    await session.commit()
                    url = await storage.get_url(record.storage_key)
                    return str(url)
            except Exception:
                logger.warning(
                    "Media persist failed (source=%s, non-blocking)",
                    source,
                    exc_info=True,
                )
                return ""

        return _persist

    async def _setup_cron_tools(
        self,
        tools: list[object],
        deferred_tools: list[object],
        user_id: str | None = None,
    ) -> None:
        """Set up scheduled task (cron) tools."""
        try:
            if not user_id:
                logger.warning("Cron tools load skipped: user_id is missing")
                return

            from myrm_agent_harness.toolkits import create_cron_tools

            from app.core.cron.adapters.setup import get_cron_manager

            cron_tools = create_cron_tools(
                get_cron_manager(),
                user_id=user_id,
                current_model=self.model_cfg.model,
                chat_id=self.chat_id,
                agent_id=self.agent_id,
            )
            deferred_tools.extend(cron_tools)
            logger.info(f"Loaded {len(cron_tools)} cron tools [Deferred]")
        except Exception as e:
            logger.warning(f"Cron tools load failed (degraded): {e}")

    async def _create_memory_tools(
        self,
        tools: list[object],
        deferred_tools: list[object],
        binding: ResolvedContextBinding,
    ) -> MemoryManager | None:
        """Create memory tools. Returns MemoryManager on success, None on failure."""
        try:
            from app.core.memory.adapters.setup import create_memory_tools_for_user

            if self.embedding_config is None:
                logger.warning("⚠️ 记忆工具未加载（缺少 embedding_config）")
                return None

            time_decay_half_life_days = 90.0
            if self.memory_decay_profile == "permanent":
                time_decay_half_life_days = 3650.0
            elif self.memory_decay_profile == "fast":
                time_decay_half_life_days = 7.0

            manager, memory_tools = await create_memory_tools_for_user(
                binding,
                self.embedding_config,
                approval_required=self.memory_require_confirmation,
                dedup_llm=self._lite_llm,
                time_decay_half_life_days=time_decay_half_life_days,
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
        deferred_tools: list[object],
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

            from app.config.deploy_mode import is_local_mode
            from app.core.security.browser_vault import get_global_session_vault

            pool = get_global_browser_pool()
            self._session_vault = get_global_session_vault()

            domain_allowlist = None
            agent_inst = self.agent
            if agent_inst is not None:
                nw = agent_inst.config.security_config.network_allowlist
                if nw:
                    domain_allowlist = DomainAllowlist.from_strings(nw)

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
            from myrm_agent_harness.toolkits.browser.captcha import ManualSolver

            browser_session = BrowserSession(
                pool,
                ContextType.AGENT,
                context_key=browser_context_key,
                session_vault=self._session_vault,
                domain_allowlist=domain_allowlist,
                captcha_solver=ManualSolver(),
                content_vault=ArtifactVault(os.getcwd()),
                allow_private_networks=is_local_mode(),
                auto_restore_domains=getattr(self, "auto_restore_domains", []),
                vision_llm=vision_llm,
                engine_preference=getattr(self, "browser_engine", None),
                launch_mode_preference=getattr(self, "browser_source", None),
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

    def _setup_computer_use_tools(self, tools: list[object], deferred_tools: list[object]) -> None:
        """Set up system-wide computer use tools (screenshot + action)."""
        try:
            from myrm_agent_harness.toolkits.computer_use import (
                create_desktop_session,
                create_desktop_tools,
            )
            from myrm_agent_harness.toolkits.computer_use.types import (
                ComputerUseConfig,
            )

            constraints = _select_image_constraints(self.model_cfg.model)
            config = ComputerUseConfig(image_constraints=constraints) if constraints else None
            session = create_desktop_session(config=config)
            computer_tools = create_desktop_tools(session)
            deferred_tools.extend(computer_tools)
            self._desktop_session = session
            logger.warning(
                "Loaded %d desktop control tools (model=%s, max_edge=%dpx) [Deferred]",
                len(computer_tools),
                self.model_cfg.model,
                session._config.image_constraints.max_edge_px,
            )
        except Exception as e:
            logger.warning("Computer use tools load failed (degraded): %s", e)

    def _setup_local_browser_data_tool(self, tools: list[object], deferred_tools: list[object]) -> None:
        """Load the local browser data search tool (Chrome/Edge bookmarks & history)."""
        try:
            from myrm_agent_harness.toolkits import create_local_browser_data_tool

            local_browser_tool = create_local_browser_data_tool()
            deferred_tools.append(local_browser_tool)
            logger.info("Loaded local browser data search tool [Deferred]")
        except Exception as e:
            logger.warning("Local browser data tool load failed (degraded): %s", e)


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
