"""Working State application service.

[INPUT]
myrm_agent_harness.api::LocalWorkingMemoryBlock (POS: 本地工作记忆块)

[OUTPUT]
ConsolidationService: 工作记忆实时快照与引导决策记录业务服务

[POS]
记忆工作台服务。连接执行端 LocalWorkingMemoryBlock 实时状态、会话级工作状态快照缓存与引导决策记录。
"""

from __future__ import annotations

import logging
import time

from myrm_agent_harness.api import LocalWorkingMemoryBlock

logger = logging.getLogger(__name__)


class ConsolidationService:
    """Service providing query and mutation facilities for runtime working boards."""

    _MAX_ACTIVE_SESSIONS: int = 100
    _active_sessions_state: dict[str, dict[str, object]] = {}

    @classmethod
    def record_steering_decision(
        cls,
        session_id: str,
        reply: str,
        question_context: str | None = None,
        call_id: str | None = None,
    ) -> None:
        """Record a confirmed non-blocking steering decision fact (<25 tokens) into working memory."""
        clean_reply = reply.strip()
        if not session_id or not clean_reply:
            return

        summary_val = (
            f"{question_context.strip()[:30]} -> {clean_reply[:40]}"
            if question_context and question_context.strip()
            else clean_reply[:60]
        )

        session_state = cls._active_sessions_state.setdefault(session_id, {})
        scratchpad = session_state.setdefault("scratchpad", {})
        if isinstance(scratchpad, dict):
            key = f"decision_{call_id[-6:]}" if call_id else f"decision_{int(time.time())}"
            scratchpad[key] = summary_val

        try:
            from myrm_agent_harness.api import LocalWorkingMemoryBlock

            memo_key = f"steer_{call_id[-6:]}" if call_id else "steer_decision"
            LocalWorkingMemoryBlock.set_scratchpad(memo_key, summary_val)
        except Exception:
            pass

    @classmethod
    def update_session_working_state(cls, session_id: str, state: dict[str, object]) -> None:
        """Register or update runtime execution working state snapshot for a chat session."""
        if not session_id:
            return
        if len(cls._active_sessions_state) >= cls._MAX_ACTIVE_SESSIONS and session_id not in cls._active_sessions_state:
            first_key = next(iter(cls._active_sessions_state))
            cls._active_sessions_state.pop(first_key, None)
        cls._active_sessions_state[session_id] = dict(state)

    @classmethod
    def clear_session_working_state(cls, session_id: str) -> None:
        """Clear cached working state snapshot for a terminated chat session."""
        cls._active_sessions_state.pop(session_id, None)

    @classmethod
    def get_live_working_state(cls, session_id: str | None = None) -> dict[str, object]:
        """Return the active execution workbench state as serialized dict.

        Prioritizes session snapshot if session_id is provided, otherwise falls back
        to coroutine-local state or the latest active session.
        """
        if session_id and session_id in cls._active_sessions_state:
            return dict(cls._active_sessions_state[session_id])

        local_state = LocalWorkingMemoryBlock.to_dict()
        has_local_content = (
            bool(local_state.get("subtasks"))
            or bool(local_state.get("traps"))
            or bool(local_state.get("scratchpad"))
        )
        if has_local_content:
            return local_state

        if not session_id and cls._active_sessions_state:
            last_key = next(reversed(cls._active_sessions_state))
            return dict(cls._active_sessions_state[last_key])

        return local_state
