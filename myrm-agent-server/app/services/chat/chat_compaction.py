"""Compaction drain and summary update mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- conversation_recall_index_service::ConversationRecallIndexService (POS: Conversation Recall 索引生命周期服务)

[OUTPUT]
- _ChatCompactionMixin: compaction summary 更新、后台 drain 调度与执行

[POS]
Compaction drain 编排层。提供 compaction summary 字段更新、后台 drain 任务调度
和冷缓存离线摘要生成（含 LLM 调用和乐观并发控制）。
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)


class _ChatCompactionMixin(_ChatServiceBase):
    """Compaction drain and summary operations."""

    @staticmethod
    async def update_compaction_summary(chat_id: str, summary: str) -> None:
        async with UnitOfWork() as uow:
            await _ChatServiceBase._cr(uow).update_chat_fields(
                chat_id, {"compacted_summary": summary}
            )
            sess = uow.session
            assert sess is not None
            await sess.flush()
            await ConversationRecallIndexService.rebuild_chat(sess, chat_id)

    @staticmethod
    def schedule_background_drain(chat_id: str) -> None:
        """Schedule a background task to drain compaction debt (cold cache drain)"""
        import asyncio

        asyncio.create_task(_ChatCompactionMixin.flush_compaction_debt(chat_id))

    @staticmethod
    async def flush_compaction_debt(chat_id: str) -> None:
        """Background Drain Worker: Process deferred compaction debt with Optimistic MVCC."""
        import asyncio

        # 1. Wait for cache to get cold
        await asyncio.sleep(300)

        try:
            async with UnitOfWork() as uow:
                latest_msg = await _ChatServiceBase._cr(uow).get_latest_message(chat_id)
                if not latest_msg:
                    return
                snapshot_id = latest_msg.id

                chat = await _ChatServiceBase._cr(uow).get_chat_by_id(
                    chat_id, load_messages=False
                )
                if not chat:
                    return

                age_seconds = (
                    datetime.utcnow() - latest_msg.created_at
                ).total_seconds()
                if age_seconds < 290:
                    logger.info(
                        f"❄️ [Drain] Cache still hot for {chat_id}, deferring drain."
                    )
                    return

            logger.info(
                f"❄️ [Drain] Cache is cold for {chat_id}, starting offline summarization for snapshot {snapshot_id}."
            )

            async with UnitOfWork() as uow:
                all_msgs = await _ChatServiceBase._cr(uow).get_all_messages(chat_id)

            target_msgs = []
            for msg in all_msgs:
                target_msgs.append(msg)
                if msg.id == snapshot_id:
                    break

            from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

            langchain_msgs = []
            for m in target_msgs:
                if m.role == "user":
                    langchain_msgs.append(HumanMessage(content=m.content))
                elif m.role == "assistant":
                    langchain_msgs.append(AIMessage(content=m.content))
                elif m.role == "tool":
                    tc_id = m.extra_data.get("tool_call_id", "") if m.extra_data else ""
                    langchain_msgs.append(
                        ToolMessage(content=m.content, tool_call_id=str(tc_id))
                    )

            from myrm_agent_harness.agent.context_management.infra.schemas import (
                ContextConfig,
            )
            from myrm_agent_harness.agent.context_management.strategies.summarizer import (
                generate_structured_summary,
            )
            from myrm_agent_harness.toolkits.llms import llm_manager

            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            providers_dict = configs.providers_dict if configs else None

            model_cfg = None
            if providers_dict:
                from app.services.agent.params.models import ModelSelection
                from app.services.agent.params.resolvers import _resolve_model_config

                default_model_cfg = providers_dict.get("defaultModelConfig", {})
                if isinstance(default_model_cfg, dict):
                    lite_model = default_model_cfg.get("liteModel") or {}
                    selection = lite_model.get("primary") or lite_model.get(
                        "selection"
                    )
                    if selection and isinstance(selection, dict):
                        provider_id = selection.get("providerId")
                        model = selection.get("model")
                        if provider_id and model:
                            ms = ModelSelection(
                                provider_id=str(provider_id), model=str(model)
                            )
                            try:
                                model_cfg = await _resolve_model_config(
                                    ms, providers_dict
                                )
                            except Exception:
                                pass
            if not model_cfg:
                from app.core.channel_bridge.model_resolver import resolve_model_config

                model_cfg = resolve_model_config(providers_dict)

            llm = await llm_manager.get_llm_from_config(
                model_cfg, api_keys=getattr(model_cfg, "api_keys", None)
            )

            context_config = ContextConfig(max_context_tokens=128000)
            _, summary = await generate_structured_summary(
                langchain_msgs, llm, chat_id, config=context_config
            )

            async with UnitOfWork() as uow:
                current_chat = await _ChatServiceBase._cr(uow).get_chat_by_id(chat_id, load_messages=False)
                if not current_chat:
                    return

                success = await _ChatServiceBase._cr(uow).cas_update_compaction(
                    chat_id=chat_id,
                    old_before_id=current_chat.compacted_before_id,
                    new_summary=summary.to_json(),
                    new_before_id=snapshot_id,
                )

                if success:
                    logger.info(
                        f"✅ [Drain] Optimistic MVCC update successful for chat {chat_id}, new snapshot: {snapshot_id}"
                    )
                else:
                    logger.info(
                        f"⚠️ [Drain] MVCC update failed for chat {chat_id} "
                        f"(concurrent modification), discarding summary."
                    )

        except Exception as e:
            logger.error(f"❌ [Drain] Background drain failed for {chat_id}: {e}")
