"""Retry, undo, sibling switching, and title generation mixin.

[INPUT]
- _base::_ChatServiceBase (POS: repository 协议和访问器)
- chat_helpers::RetryResult, RegenerateResult, UndoResult (POS: 操作结果 DTO)
- database.repositories.chat_repo::SiblingDetail (POS: 兄弟消息详情)

[OUTPUT]
- _ChatTurnMixin: 重试、撤销、重新生成、兄弟切换、标题生成

[POS]
对话轮次操作与标题生成编排层。提供消息重试、撤销、重新生成（含兄弟消息管理）
和 LLM 驱动的聊天标题生成。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from app.database.repositories.chat_repo import SiblingDetail
from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .chat_helpers import RegenerateResult, RetryResult, UndoResult

if TYPE_CHECKING:
    from app.database.dto import _TitleModelConfig

logger = logging.getLogger(__name__)


class _ChatTurnMixin(_ChatServiceBase):
    """Retry, undo, sibling, and title generation operations."""

    @staticmethod
    async def retry_last_turn(chat_id: str, user_id: str | None = None) -> RetryResult:
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(
                chat_id, load_messages=False
            )
            if not chat:
                return RetryResult(success=False, query="", deleted_count=0)
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return RetryResult(success=False, query="", deleted_count=0)
            deleted = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id, last_user, include_anchor=False
            )
            return RetryResult(
                success=True, query=last_user.content, deleted_count=deleted
            )

    @staticmethod
    async def regenerate_last_turn(chat_id: str) -> RegenerateResult:
        """Mark the last assistant responses as inactive siblings and return the original query.

        Retry deletes later messages; regenerate preserves inactive sibling
        responses so users can switch between generated versions.
        """
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(
                chat_id, load_messages=False
            )
            if not chat:
                return RegenerateResult(success=False, query="", sibling_group_id="")
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return RegenerateResult(success=False, query="", sibling_group_id="")
            query, group_id = await _ChatServiceBase._cr(
                uow
            ).deactivate_last_assistant_siblings(chat_id, last_user)
            return RegenerateResult(
                success=True, query=query, sibling_group_id=group_id
            )

    @staticmethod
    async def switch_sibling(sibling_group_id: str, target_message_id: str) -> bool:
        """Switch the active sibling in a group. Returns True on success."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).switch_active_sibling(
                sibling_group_id, target_message_id
            )

    @staticmethod
    async def get_sibling_info(sibling_group_id: str) -> list[SiblingDetail]:
        """Return ordered list of sibling summaries for a group."""
        async with UnitOfWork() as uow:
            return await _ChatServiceBase._cr(uow).get_sibling_info(sibling_group_id)

    @staticmethod
    async def undo_last_turn(chat_id: str, user_id: str | None = None) -> UndoResult:
        async with UnitOfWork() as uow:
            chat = await _ChatServiceBase._cr(uow).get_chat_by_id(
                chat_id, load_messages=False
            )
            if not chat:
                return UndoResult(success=False, deleted_count=0)
            last_user = await _ChatServiceBase._cr(uow).get_last_user_message(chat_id)
            if not last_user:
                return UndoResult(success=True, deleted_count=0)
            deleted = await _ChatServiceBase._cr(uow).delete_messages_after(
                chat_id, last_user, include_anchor=True
            )
            if deleted > 0:
                remaining = await _ChatServiceBase._cr(uow).get_latest_message(chat_id)
                new_last = ""
                if remaining:
                    from myrm_agent_harness.utils.text_sanitizer import (
                        extract_and_strip_think_blocks,
                    )

                    clean_content, _ = extract_and_strip_think_blocks(remaining.content)
                    new_last = clean_content[:100]
                await _ChatServiceBase._cr(uow).update_chat_fields(
                    chat_id, {"last_message": new_last}
                )
            return UndoResult(success=True, deleted_count=deleted)

    @staticmethod
    async def generate_chat_title(
        messages: list,
        title_model: "_TitleModelConfig | None" = None,
        fallback_title_model: "_TitleModelConfig | None" = None,
    ) -> str:
        """使用前端配置的轻量模型生成聊天标题，主模型失败时自动尝试备用模型"""
        from myrm_agent_harness.toolkits.llms.errors.resilient import resilient_llm_call

        user_messages = [msg.content for msg in messages if msg.role == "user"]
        if not user_messages:
            return "Untitled Chat"
        content = " ".join(user_messages[:3])[:500]
        if title_model is None:
            return _ChatTurnMixin._generate_fallback_title(content)
        try:
            return cast(
                str,
                await resilient_llm_call(
                    primary_fn=lambda: _ChatTurnMixin._call_llm_for_title(
                        content, title_model
                    ),
                    fallback_fn=(
                        (
                            lambda: _ChatTurnMixin._call_llm_for_title(
                                content, fallback_title_model
                            )
                        )
                        if fallback_title_model
                        else None
                    ),
                ),
            )
        except Exception as e:
            logger.error(f"❌ 生成聊天标题失败: {e}")
            return _ChatTurnMixin._generate_fallback_title(content)

    @staticmethod
    async def _call_llm_for_title(
        content: str, title_model: "_TitleModelConfig"
    ) -> str:
        """调用 LLM 生成标题"""
        from langchain_core.messages import HumanMessage
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.core.types import ModelConfig

        model_kwargs = dict(title_model.model_kwargs or {})
        model_kwargs.setdefault("temperature", 0.3)
        model_kwargs.setdefault("max_tokens", 1024)
        cfg = ModelConfig(
            model=title_model.model,
            api_key=title_model.api_key,
            base_url=title_model.base_url,
            model_kwargs=model_kwargs,
        )
        llm = await llm_manager.get_llm_from_config(cfg, streaming=False)
        prompt = f"用5-15个字给这段对话起个标题，只输出标题：\n{content[:200]}"
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        title = str(response.content).strip().strip("\"'「」【】：:。.")
        if len(title) < 2 or len(title) > 50:
            return _ChatTurnMixin._generate_fallback_title(content)
        return title

    @staticmethod
    def _generate_fallback_title(content: str) -> str:
        """后备标题（无模型配置或 LLM 调用失败时）"""
        title = content.strip()[:20]
        if len(title) < 3:
            return "Untitled Chat"
        return title + ("..." if len(content) > 20 else "")
