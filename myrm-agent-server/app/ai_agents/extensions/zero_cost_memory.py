from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from myrm_agent_harness.agent.context_management.infra.schemas import EvictedToolCall
from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

EvictionCallback = Callable[
    [list[EvictedToolCall], str],
    Coroutine[object, object, None],
]


class ZeroCostMemoryExtension(AgentExtension):
    """Extension that intercepts evicted tool calls/responses from the ContextPipeline
    and automatically extracts long-term memories using an LLM in the background.

    The eviction callback is built eagerly via ``build_eviction_callback()`` so that
    ``factory.py`` can pass it to ``create_context_pipeline_middleware`` before the
    agent graph is created.
    """

    def __init__(
        self,
        enable_memory_auto_extraction: bool,
        is_subagent: bool,
        channel_name: str,
        memory_manager: MemoryManager | None,
        effective_chat_id: str,
        extractor_llm: BaseChatModel,
        *,
        deep_scan: bool = False,
    ) -> None:
        self.enable_memory_auto_extraction = enable_memory_auto_extraction
        self.is_subagent = is_subagent
        self.channel_name = channel_name
        self.memory_manager = memory_manager
        self.effective_chat_id = effective_chat_id
        self.extractor_llm = extractor_llm
        self.deep_scan = deep_scan

    @property
    def name(self) -> str:
        return "ZeroCostMemoryExtension"

    def build_eviction_callback(self) -> EvictionCallback | None:
        """Build the compress-eviction callback for the context pipeline middleware.

        Returns ``None`` when memory extraction is disabled or unavailable.
        Must be called before ``create_context_pipeline_middleware``.
        """
        if not self.enable_memory_auto_extraction or self.memory_manager is None:
            return None

        if self.is_subagent or self.channel_name == "subagent":
            logger.info("🧠 [Zero-Cost Memory] Skipped for subagent to prevent global memory pollution.")
            return None

        from myrm_agent_harness.api.hooks import (
            create_extraction_llm_func,
            persist_extracted_memories,
        )
        from myrm_agent_harness.toolkits.memory.strategies.extractor import ExtractionConfig, MemoryExtractor

        llm_func = create_extraction_llm_func(self.extractor_llm)
        config = ExtractionConfig(enable_task_digest=False)
        extractor = MemoryExtractor(config=config, llm_func=llm_func)
        memory_manager = self.memory_manager
        effective_chat_id = self.effective_chat_id
        deep_scan_llm = llm_func if self.deep_scan else None

        async def _compress_eviction_cb(
            evicted_pairs: list[EvictedToolCall],
            user_goal_hint: str,
        ) -> None:
            messages_for_extraction: list[dict[str, str]] = []
            if user_goal_hint:
                messages_for_extraction.append({"role": "system", "content": f"User Goal Context: {user_goal_hint}"})

            for evicted in evicted_pairs:
                messages_for_extraction.append(
                    {
                        "role": "assistant",
                        "content": f"{evicted.ai_msg.content}\nToolCalls: {getattr(evicted.ai_msg, 'tool_calls', [])}",
                    }
                )
                messages_for_extraction.append(
                    {
                        "role": "user",
                        "content": f"ToolResult ({getattr(evicted.tool_msg, 'name', 'unknown')}):\n{evicted.original_content}",
                    }
                )

            async def _extract_background() -> None:
                try:
                    result = await extractor.extract(
                        messages_for_extraction,
                        correction_detected=False,
                    )
                    if result.memories:
                        await persist_extracted_memories(
                            result.memories,
                            memory_manager,
                            effective_chat_id,
                            deep_scan_llm_func=deep_scan_llm,
                        )
                        count = len(result.memories)
                        logger.info(
                            "🧠 [Zero-Cost Memory] Auto-extracted %d memories from %d evicted tools",
                            count,
                            len(evicted_pairs),
                        )
                        try:
                            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

                            get_event_bus().publish(
                                AppEvent(
                                    event_type=AppEventType.MEMORY_OPERATION,
                                    data={
                                        "operation": "auto_memory_extracted",
                                        "count": count,
                                        "source": "eviction",
                                        "chat_id": effective_chat_id,
                                    },
                                )
                            )
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Eviction memory extraction failed: %s", e)

            asyncio.create_task(_extract_background())

        return _compress_eviction_cb

    async def on_agent_init(self, agent: BaseAgent) -> None:
        pass

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        pass

    def get_tools(self) -> list[BaseTool] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None
