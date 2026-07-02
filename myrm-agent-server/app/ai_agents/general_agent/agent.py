"""General Agent — LangGraph-based autonomous agent with progressive disclosure.

[INPUT]
- tool_setup::ToolSetupMixin (POS: 工具初始化混入)
- checkpoint_helpers (POS: 浏览器 Checkpoint 辅助)
- compression_intent (POS: 压缩意图构建)
- llm_factory (POS: LLM 实例创建工厂)
- core.memory.adapters.setup (POS: 记忆系统适配器)

[OUTPUT]
- GeneralAgent: 通用 Agent 主类

[POS]
通用 Agent 核心实现。管理 Agent 生命周期（初始化、流式执行、资源释放），
工具创建委托给 ToolSetupMixin。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable, Coroutine, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from langchain_core.messages import BaseMessage
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.core.memory.adapters.setup import resolve_context_binding
from app.core.memory.adapters.types import ResolvedContextBinding
from app.core.types import MCPServerConfig, ModelConfig

from .compression_intent import build_compression_intent
from .tool_setup import ToolSetupMixin

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
    from myrm_agent_harness.api import SkillAgent
    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.toolkits.browser import (
        BrowserCheckpointHelper,
        BrowserSession,
    )
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.utils import CancellationToken
    from myrm_agent_harness.utils.runtime.steering import SteeringToken

    from app.ai_agents.agents import ImageGenerationParams, VideoGenerationParams

logger = logging.getLogger(__name__)

TOOL_CALL_PLACEHOLDER = "(tool calls only)"
SYSTEM_PROMPT_MARKER = "(system prompt detected"


class GeneralAgent(ToolSetupMixin):
    """General Agent - LangGraph-based autonomous agent.

    Uses LangGraph StateGraph for fully autonomous decision-making.
    Provides streaming events, progressive disclosure, and quality assessment.
    """

    def __init__(
        self,
        model_cfg: ModelConfig,
        mcp_config: list[MCPServerConfig] | None,
        search_service_cfg: SearchServiceConfig | None = None,
        user_instructions: str | None = None,
        chat_id: str | None = None,
        lite_model_cfg: ModelConfig | None = None,
        fallback_model_cfg: ModelConfig | None = None,
        safety_fallback_model_cfg: ModelConfig | None = None,
        fallback_lite_model_cfg: ModelConfig | None = None,
        vision_fallback_model_cfg: ModelConfig | None = None,
        memory_require_confirmation: bool = False,
        enable_memory_auto_extraction: bool = True,
        incognito_mode: bool = False,
        enable_advanced_retrieval: bool = False,
        embedding_config: "EmbeddingConfig | None" = None,
        reranker_config: "RerankerConfig | None" = None,
        enable_render_ui: bool = False,
        enable_web_search: bool = True,
        enable_browser: bool = False,
        enable_computer_use: bool = False,
        enable_file_ops: bool = True,
        enable_code_execute: bool = True,
        enable_wiki: bool = False,
        enable_kanban: bool = False,
        enable_canvas: bool = False,
        canvas_id: str | None = None,
        enable_answer_tool: bool = False,
        enable_planning: bool = False,
        enable_task_tracking: bool = False,
        kanban_tool_mode: str = "orchestrator",
        kanban_current_task_id: str | None = None,
        kanban_max_runtime_seconds: int | None = None,
        kanban_zombie_timeout_seconds: int = 120,
        auto_restore_domains: list[str] | None = None,
        skill_ids: list[str] | None = None,
        skill_configs: dict[str, dict] | None = None,
        fetch_raw_webpage: bool = False,
        enable_memory: bool = True,
        security_config_raw: dict[str, object] | None = None,
        agent_security_raw: dict[str, object] | None = None,
        channel_name: str = "web_chat",
        providers_dict: dict[str, object] | None = None,
        light_model_cfg: ModelConfig | None = None,
        reasoning_model_cfg: ModelConfig | None = None,
        memory_channel_id: str | None = None,
        memory_conversation_id: str | None = None,
        memory_task_id: str | None = None,
        memory_shared_context_ids: list[str] | None = None,
        declared_capabilities: tuple[str, ...] = (),
        declared_allowed_roots: tuple[str, ...] = (),
        external_agents_config: list[dict[str, object]] | None = None,
        image_generation_params: "ImageGenerationParams | None" = None,
        video_generation_params: "VideoGenerationParams | None" = None,
        tts_params: "dict[str, object] | None" = None,
        privacy_enabled: bool = False,
        privacy_s2_action: str = "warn",
        privacy_s3_action: str = "redact",
        privacy_routing_raw: dict[str, object] | None = None,
        privacy_custom_keywords_s2: list[str] | None = None,
        privacy_custom_keywords_s3: list[str] | None = None,
        privacy_custom_patterns_s2: list[str] | None = None,
        privacy_custom_patterns_s3: list[str] | None = None,
        privacy_sensitive_tools_s2: list[str] | None = None,
        privacy_sensitive_tools_s3: list[str] | None = None,
        privacy_deep_scan: bool = False,
        code_execution_allow_network: bool | None = None,
        event_log_backend: "EventLogBackend | None" = None,
        locale: str | None = None,
        agent_id: str | None = None,
        subagent_ids: list[str] | None = None,
        jit_subagents: dict[str, object] | None = None,
        task_adaptive_digest: dict[str, object] | None = None,
        max_iterations: int | None = None,
        memory_policy: AgentMemoryPolicy | None = None,
        memory_decay_profile: str | None = None,
        engine_params: dict[str, object] | None = None,
        quote: str | None = None,
        goal: dict[str, object] | None = None,
        openapi_services: list[dict[str, object]] | None = None,
        prompt_mode: str = "full",
        search_depth: str = "normal",
        tail_budget_ratio: float = 0.20,
        notify_targets: tuple[dict[str, str], ...] = (),
    ) -> None:
        self.model_cfg = model_cfg
        self.fallback_model_cfg = fallback_model_cfg
        self.safety_fallback_model_cfg = safety_fallback_model_cfg
        self.lite_model_cfg = lite_model_cfg
        self.fallback_lite_model_cfg = fallback_lite_model_cfg
        self.vision_fallback_model_cfg = vision_fallback_model_cfg
        self.mcp_config = mcp_config
        self.search_service_cfg = search_service_cfg
        self.user_instructions = user_instructions
        self.chat_id = chat_id
        self.agent_id = agent_id
        self.subagent_ids = subagent_ids
        self.jit_subagents = jit_subagents
        self.task_adaptive_digest = task_adaptive_digest
        self.skill_ids = skill_ids or []
        self.skill_configs = skill_configs
        self.memory_require_confirmation = memory_require_confirmation
        self.enable_memory_auto_extraction = enable_memory_auto_extraction
        self.incognito_mode = incognito_mode
        self.enable_advanced_retrieval = enable_advanced_retrieval
        self.embedding_config = embedding_config
        self.reranker_config = reranker_config
        self.enable_render_ui = enable_render_ui
        self.enable_web_search = enable_web_search
        self.enable_browser = enable_browser
        self.enable_computer_use = enable_computer_use
        self.enable_file_ops = enable_file_ops
        self.enable_code_execute = enable_code_execute
        self.enable_wiki = enable_wiki
        self.enable_kanban = enable_kanban
        self.enable_canvas = enable_canvas
        self.canvas_id = canvas_id
        self.enable_answer_tool = enable_answer_tool
        self.enable_planning = enable_planning
        self.enable_task_tracking = enable_task_tracking
        self.kanban_tool_mode = kanban_tool_mode
        self.kanban_current_task_id = kanban_current_task_id
        self.kanban_max_runtime_seconds = kanban_max_runtime_seconds
        self.kanban_zombie_timeout_seconds = kanban_zombie_timeout_seconds
        self.auto_restore_domains = auto_restore_domains or []
        self.fetch_raw_webpage = fetch_raw_webpage
        self.enable_memory = enable_memory
        self.security_config_raw = security_config_raw
        self.agent_security_raw = agent_security_raw
        self.channel_name = channel_name
        self.memory_channel_id = memory_channel_id
        self.memory_conversation_id = memory_conversation_id
        self.memory_task_id = memory_task_id
        self.memory_shared_context_ids = list(memory_shared_context_ids or [])
        self.declared_capabilities = declared_capabilities
        self.declared_allowed_roots = declared_allowed_roots
        self.external_agents_config = external_agents_config
        self.image_generation_params = image_generation_params
        self.video_generation_params = video_generation_params
        self.tts_params = tts_params
        self.privacy_enabled = privacy_enabled
        self.privacy_s2_action = privacy_s2_action
        self.privacy_s3_action = privacy_s3_action
        self.privacy_routing_raw = privacy_routing_raw
        self.privacy_custom_keywords_s2 = privacy_custom_keywords_s2 or []
        self.privacy_custom_keywords_s3 = privacy_custom_keywords_s3 or []
        self.providers_dict = providers_dict
        self.light_model_cfg = light_model_cfg
        self.reasoning_model_cfg = reasoning_model_cfg
        self.privacy_custom_patterns_s2 = privacy_custom_patterns_s2 or []
        self.privacy_custom_patterns_s3 = privacy_custom_patterns_s3 or []
        self.privacy_sensitive_tools_s2 = privacy_sensitive_tools_s2 or []
        self.privacy_sensitive_tools_s3 = privacy_sensitive_tools_s3 or []
        self.privacy_deep_scan = privacy_deep_scan
        self.code_execution_allow_network = code_execution_allow_network
        self.event_log_backend = event_log_backend
        self.locale = locale
        self.max_iterations = max_iterations
        self.memory_policy = memory_policy
        self.memory_decay_profile = memory_decay_profile
        self.engine_params = engine_params
        self.prompt_mode = prompt_mode
        self.search_depth = search_depth
        self.tail_budget_ratio = tail_budget_ratio
        self.approval_session_key: str | None = None
        self.agent: SkillAgent | None = None
        self._lite_llm: BaseChatModel | object | None = None
        self._browser_session: BrowserSession | None = None
        self._desktop_session: object | None = None
        self._executor = None
        self._current_chat_id: str | None = None
        self._session_vault = None
        self._checkpoint_helper: BrowserCheckpointHelper | None = None
        self._current_thread_id: str | None = None
        self._runtime_pool: RuntimePool | None = None
        self._skill_config_version: float = 0.0
        self.quote = quote
        self.goal = goal
        self.openapi_services = openapi_services or []
        self.notify_targets = notify_targets

    def _resolve_wiki_base_dir(self) -> str | None:
        """Resolve wiki base directory for the current user."""
        from pathlib import Path

        return str(Path("~/.myrm/users").expanduser() / "sandbox" / "wiki")

    def _build_wiki_search_fn(
        self,
    ) -> Callable[[str, list[Path]], Coroutine[None, None, list[tuple[Path, float]]]]:
        """Build BM25 search function for wiki query engine.

        Returns path for wiki storage.
        BM25 provides significantly better relevance than simple keyword overlap
        via TF-IDF weighting and document length normalization.
        """
        from myrm_agent_harness.toolkits.retriever.bm25_retrieval import bm25_retrieval

        async def _wiki_bm25_search(
            query: str,
            concept_paths: list[Path],
        ) -> list[tuple[Path, float]]:
            """BM25 search over wiki concept files."""
            docs: list[tuple[Path, str]] = []
            for p in concept_paths:
                try:
                    docs.append((p, p.read_text(encoding="utf-8")))
                except Exception:
                    continue

            if not docs:
                return []

            texts = [content for _, content in docs]
            paths = [path for path, _ in docs]

            scored = bm25_retrieval(texts, query, top_k=len(texts), only_relevant=True)
            return [(paths[idx], score) for idx, score in scored]

        return _wiki_bm25_search

    def _resolve_context_binding(self, effective_chat_id: str) -> ResolvedContextBinding | None:
        """Resolve the unified context binding contract for the current agent run."""

        if not self.enable_memory:
            return None

        task_root = self.declared_allowed_roots[0] if self.declared_allowed_roots else None
        return resolve_context_binding(
            namespaces=None,
            agent_id=self.agent_id or "default",
            channel_id=self.memory_channel_id or self.channel_name,
            conversation_id=self.memory_conversation_id or effective_chat_id,
            task_id=self.memory_task_id,
            shared_context_ids=self.memory_shared_context_ids,
            memory_policy=self.memory_policy,
            task_workspace_root=task_root,
        )

    def _build_runtime_context(
        self,
        *,
        query: object,
        chat_history: (list[list[str]] | list[list[str | object]] | Sequence[BaseMessage] | None),
        effective_chat_id: str,
    ) -> dict[str, object]:
        """Build server-layer runtime context passed into the harness."""
        context: dict[str, object] = {}
        from app.services.context.context_assembly import ContextAssemblyService

        bundle = ContextAssemblyService.build_facade(ensure_layout=False)
        context["workspaces_storage_root"] = str(bundle.harness_path().resolve())
        context["context_bundle_id"] = bundle.spec.bundle_id
        if self.agent_id:
            context["agent_id"] = self.agent_id
        if self.user_instructions:
            context["user_instructions"] = self.user_instructions
        if self.prompt_mode != "full":
            context["prompt_mode"] = self.prompt_mode

        session_id = f"chat_{effective_chat_id}"
        context["session_id"] = session_id

        if self.declared_allowed_roots:
            from myrm_agent_harness.agent.types import WorkspaceBinding

            context["workspace_binding"] = WorkspaceBinding(
                mode="chat",
                root_path=self.declared_allowed_roots[0],
                chat_id=effective_chat_id,
            )

        if self.approval_session_key:
            context["approval_session_key"] = self.approval_session_key

        context["chat_id"] = effective_chat_id
        if self.model_cfg.max_context_tokens:
            context["max_context_tokens"] = self.model_cfg.max_context_tokens

        if self.engine_params and self.engine_params.get("compress_start_ratio") is not None:
            context["compress_start_ratio"] = self.engine_params["compress_start_ratio"]

        context["supports_vision"] = self.model_cfg.supports_vision
        if self.vision_fallback_model_cfg:
            context["vision_fallback_model_cfg"] = self.vision_fallback_model_cfg

        history_messages: Sequence[BaseMessage] | None = None
        if chat_history is not None and len(chat_history) > 0:
            first = chat_history[0]
            if isinstance(first, BaseMessage):
                history_messages = cast(Sequence[BaseMessage], chat_history)
        compression_intent = build_compression_intent(
            query=query,
            chat_history=history_messages,
        )
        if compression_intent is not None:
            context["compression_intent"] = compression_intent

        if self.quote:
            from myrm_agent_harness.agent.types import QuoteAttachment

            context["quote_attachment"] = QuoteAttachment(
                source_message_id="",
                quoted_text=self.quote,
            )

        if hasattr(self, "goal") and self.goal:
            context["goal"] = self.goal

        return context

    async def process_stream(
        self,
        query: object,
        chat_history: list[list[str]] | list[list[str | object]] | None = None,
        message_id: str | None = None,
        chat_id: str | None = None,
        cancel_token: "CancellationToken | None" = None,
        steering_token: "SteeringToken | None" = None,
        timezone: str | None = None,
        force_delegate_agent: str | None = None,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        from .stream_pipeline import execute_stream_pipeline

        async for chunk in execute_stream_pipeline(
            self,
            query,
            chat_history,
            message_id,
            chat_id,
            cancel_token,
            steering_token,
            timezone,
            force_delegate_agent,
            extra_context=context,
        ):
            yield chunk

    async def _check_skill_config_staleness(self, effective_chat_id: str) -> None:
        """Check if skill config has changed and reinitialize agent if stale."""
        from app.core.skills.config_version import get_skill_config_version

        current_version = get_skill_config_version()
        if current_version > self._skill_config_version:
            logger.warning(
                "Skill config changed (%.2f -> %.2f), reinitializing agent",
                self._skill_config_version,
                current_version,
            )
            from myrm_agent_harness.agent.skills.runtime.loader import skill_md_loader

            skill_md_loader.clear_cache()

            if self.agent is not None:
                try:
                    await self.agent.close()
                except Exception as e:
                    logger.warning("Agent close during hot-reload failed: %s", e)
                self.agent = None
            await self._init_agent(effective_chat_id=effective_chat_id)

    async def _init_agent(self, *, effective_chat_id: str) -> None:
        """Build and attach the harness SkillAgent (used after hot-reload)."""
        from .factory import build_general_agent

        self.agent = await build_general_agent(self, effective_chat_id)

    async def close(self) -> None:
        """Close Agent and release resources."""
        if self._runtime_pool is not None:
            try:
                await self._runtime_pool.close_all()
            except Exception as e:
                logger.warning(f"⚠️ RuntimePool close failed: {e}")
            finally:
                self._runtime_pool = None

        if self._browser_session is not None:
            try:
                await self._browser_session.close()
                self._capture_session_recording_info()
            except Exception as e:
                logger.warning(f"⚠️ BrowserSession close failed: {e}")
            finally:
                self._browser_session = None

        if self._executor is not None and self._current_chat_id is not None:
            try:
                from myrm_agent_harness.runtime.context.offload import (
                    cleanup_session_context_files,
                )

                await cleanup_session_context_files(self._current_chat_id, self._executor)
            except Exception as e:
                logger.warning(f"⚠️ Context cleanup failed for chat_id={self._current_chat_id}: {e}")

        if self.agent is not None:
            try:
                await self.agent.close()
                logger.info("Agent 资源已完全释放")
            except Exception as e:
                logger.warning(f"⚠️ 关闭 Agent 时发生错误: {e}")
            finally:
                self.agent = None

    def _capture_session_recording_info(self) -> None:
        """Store session recording metadata for SSE delivery after close."""
        try:
            session = self._browser_session
            if session is None:
                return
            obs = getattr(session, "_observability", None)
            if obs is None or not obs.recording_enabled:
                return
            video_path = obs.video_path
            if video_path is None or not Path(video_path).exists():
                return

            from app.config.settings import get_settings

            harness_dir = get_settings().database.harness_dir
            relative_path = str(video_path)
            if relative_path.startswith(harness_dir):
                relative_path = relative_path[len(harness_dir):]
                if relative_path.startswith("/"):
                    relative_path = relative_path[1:]

            self._session_recording_info: dict[str, str] = {
                "filename": Path(video_path).name,
                "preview_url": f"/api/v1/files/vault/render?filepath={relative_path}&workspace={harness_dir}",
                "content_type": "video/webm",
            }
            logger.info("Session recording captured: %s", video_path)
        except Exception as e:
            logger.debug("Session recording capture skipped: %s", e)
