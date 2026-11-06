"""记忆工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager

    from app.core.memory.adapters.types import ResolvedContextBinding

logger = logging.getLogger(__name__)


class MemoryToolsMixin(ToolSetupBaseMixin):
    """记忆工具。"""

    async def _create_memory_tools(
        self,
        tools: list[object],
        binding: ResolvedContextBinding,
    ) -> MemoryManager | None:
        """Create memory tools. Returns MemoryManager on success, None on failure."""
        try:
            from myrm_agent_harness.toolkits import create_memory_tools

            from app.core.memory.adapters.setup import (
                create_conflict_callback,
                create_memory_manager,
            )

            if self.embedding_config is None:
                # Embeddings-less degradation: memories persist through the
                # BM25 sparse mirror and stay retrievable by keyword instead
                # of dropping the memory tools entirely.
                logger.info("🧠 记忆工具以关键词模式加载（未配置 embedding）")

            time_decay_half_life_days = 90.0
            if self.memory_decay_profile == "permanent":
                time_decay_half_life_days = 3650.0
            elif self.memory_decay_profile == "fast":
                time_decay_half_life_days = 7.0

            on_conflict = create_conflict_callback(agent_id=self.agent_id)
            on_consolidation_complete = None
            if self.enable_wiki and not self.incognito_mode and self._lite_llm is not None:
                from app.services.wiki.consolidation_bridge import (
                    make_consolidation_wiki_bridge,
                )

                on_consolidation_complete = make_consolidation_wiki_bridge(
                    agent_id=self.agent_id,
                    llm=self._lite_llm,
                )
            manager = await create_memory_manager(
                binding,
                self.embedding_config,
                approval_required=self.memory_require_confirmation,
                dedup_llm=None,
                time_decay_half_life_days=time_decay_half_life_days,
                reranker_config=self.reranker_config if self.enable_advanced_retrieval else None,
                on_conflict=on_conflict,
                on_consolidation_complete=on_consolidation_complete,
                base_path=self.memory_base_path,
            )

            from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
                MemorySearchBackends,
                MemorySearchPolicy,
            )

            from app.core.agent.tool_description_locale import (
                resolve_tool_description_locale,
            )

            tool_description_locale = resolve_tool_description_locale(
                agent_locale=getattr(self, "prompt_locale", None) or getattr(self, "locale", None),
                channel=getattr(self, "channel_name", None),
            )

            is_external_channel = bool(getattr(self, "channel_name", None) and getattr(self, "channel_name", None) != "web_chat")
            search_policy = MemorySearchPolicy(
                allow_wiki=bool(self.enable_wiki and not self.incognito_mode),
                allow_sessions=bool(self.enable_conversation_search and not self.incognito_mode),
                allow_shared_write=not is_external_channel,
            )
            query_wiki = None
            wiki_structure = None
            conversation_provider = None
            if search_policy.allow_wiki and self._lite_llm is not None:
                from app.services.wiki.vault import get_wiki_archiver

                lite_llm = self._lite_llm
                wiki_structure = get_wiki_archiver(lite_llm, manager, agent_id=self.agent_id)._structure

                async def _query_wiki(question: str):
                    archiver = get_wiki_archiver(lite_llm, manager, agent_id=self.agent_id)
                    return await archiver.query_wiki(question)

                query_wiki = _query_wiki
            if search_policy.allow_sessions:
                from app.services.chat.conversation_search_service import (
                    ConversationHistorySearchProvider,
                )

                conversation_provider = ConversationHistorySearchProvider(
                    current_chat_id=binding.conversation_id,
                    agent_id=self.agent_id,
                    default_scope="same_source" if is_external_channel else None,
                )
            search_backends = MemorySearchBackends(
                query_wiki=query_wiki,
                wiki_agent_id=self.agent_id,
                wiki_structure=wiki_structure,
                conversation_provider=conversation_provider,
            )
            memory_tools = create_memory_tools(
                manager,
                search_policy=search_policy,
                search_backends=search_backends,
                description_locale=tool_description_locale,
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
