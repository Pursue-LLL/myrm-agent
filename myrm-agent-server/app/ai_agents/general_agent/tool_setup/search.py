"""搜索/抓取与澄清工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..ask_question_result import format_ask_question_result
from .base import ToolSetupBaseMixin

if TYPE_CHECKING:

    pass

from app.ai_agents.general_agent.tool_setup.common import _should_mount_ask_question_tool

logger = logging.getLogger(__name__)


class SearchToolsMixin(ToolSetupBaseMixin):
    """搜索/抓取与澄清工具。"""

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
            from myrm_agent_harness.toolkits.retriever.sufficiency import (
                SufficiencyConfig,
            )

            sufficiency_cfg = SufficiencyConfig(enabled=True)
            sufficiency_llm = LLMConfig(
                model=self.model_cfg.model,
                api_key=self.model_cfg.api_key,
                base_url=self.model_cfg.base_url,
            )

        from app.config.deploy_mode import is_local_mode as _is_local
        from app.core.agent.tool_description_locale import (
            resolve_tool_description_locale,
        )

        tool_description_locale = resolve_tool_description_locale(
            agent_locale=getattr(self, "prompt_locale", None) or getattr(self, "locale", None),
            channel=getattr(self, "channel_name", None),
        )

        web_fetch_enabled = bool(getattr(self, "enable_web_fetch", True))
        # web_fetch_tool offers fetch_and_extract only with both retrieval services; web_search recommends it only then.
        fetch_and_extract_available = web_fetch_enabled and reranker_cfg is not None and embedding_cfg is not None

        if web_fetch_enabled:
            tools.append(
                create_web_fetch_tool(
                    reranker_config=reranker_cfg,
                    embedding_config=embedding_cfg,
                    use_raw_markdown=self.fetch_raw_webpage,
                    allow_private_networks=_is_local(),
                    sufficiency_config=sufficiency_cfg,
                    sufficiency_llm_config=sufficiency_llm,
                    blocked_hostnames=getattr(self, "benchmark_blocked_hostnames", ()) or None,
                    description_locale=tool_description_locale,
                )
            )
            logger.info("Loaded web_fetch_tool [Turn1 baseline, no search API required]")

        if self.enable_web_search and self.search_service_cfg:
            tools.append(
                create_web_search_tool(
                    self.search_service_cfg,
                    sufficiency_config=sufficiency_cfg,
                    sufficiency_llm_config=sufficiency_llm,
                    description_locale=tool_description_locale,
                    fetch_and_extract_available=fetch_and_extract_available,
                    blocked_terms=getattr(self, "benchmark_blocked_terms", ()) or None,
                    blocked_hostnames=getattr(self, "benchmark_blocked_hostnames", ()) or None,
                )
            )

            logger.info("Loaded web_search_tool")

        self._setup_image_generation_tools(
            tools,
            task_user_id=getattr(self, "_task_user_id", "default"),
        )
        self._setup_video_generation_tools(
            tools,
            task_user_id=getattr(self, "_task_user_id", "default"),
        )
        self._setup_tts_tools(tools)

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
            from myrm_agent_harness.agent.meta_tools.clarification.ask_question import (
                AskQuestionInput,
            )
            from myrm_agent_harness.agent.meta_tools.clarification.clarification_agent_tools import (
                create_ask_question_tool,
            )

            from app.core.agent.tool_description_locale import (
                resolve_tool_description_locale,
            )

            tool_description_locale = resolve_tool_description_locale(
                agent_locale=getattr(self, "prompt_locale", None) or getattr(self, "locale", None),
                channel=getattr(self, "channel_name", None),
            )

            async def _on_ask_question(form: AskQuestionInput) -> str:
                from langgraph.types import interrupt

                payload = {"type": "ask_question", "form": form.model_dump()}

                # Use LangGraph's native interrupt to suspend execution statelessly
                return format_ask_question_result(form, interrupt(payload))

            tools.append(create_ask_question_tool(_on_ask_question, locale=tool_description_locale))
            logger.info("🙋 已加载 ask_question_tool (交互式澄清表单)")
        except Exception as e:
            logger.warning(f"⚠️ ask_question_tool 加载失败: {e}")
