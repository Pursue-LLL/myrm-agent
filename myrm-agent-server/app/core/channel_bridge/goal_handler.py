"""ChannelGoalCommandHandler — business-layer handler for /goal slash commands.

Delegates parsed /goal subcommands to the GoalProvider (via GoalRegistry)
for the current session. Returns human-readable status strings back to the
channel user.

[INPUT]
- app.channels.types::InboundMessage (POS: inbound message)
- app.channels.protocols.goal_command (POS: handler protocol)
- app.services.agent.goal_registry::GoalRegistry (POS: per-session GoalProvider lookup)
- app.services.chat.chat_service::ChatService (POS: channel_session_key -> chat_id resolution)

[OUTPUT]
- ChannelGoalCommandHandler: GoalCommandHandler protocol implementation

[POS]
Business-layer adapter that connects /goal slash commands from channels
to the Goal engine. The framework calls `handle_goal` with parsed subcommand;
this handler resolves the GoalProvider via GoalRegistry and executes the
requested lifecycle operation. Uses ChatService to map channel session keys
to DB chat_ids, ensuring consistency with the agent executor's GoalProvider.
"""

from __future__ import annotations

import dataclasses
import logging
import time

from myrm_agent_harness.agent.goals.types import GoalBudget, GoalStatus

from app.channels.i18n import get_text
from app.channels.protocols.goal_command import (
    GoalSubcommand,
    SubgoalSubcommand,
)
from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)

_STATUS_KEYS: dict[GoalStatus, str] = {
    GoalStatus.QUEUED: "goal_status_queued",
    GoalStatus.ACTIVE: "goal_status_label",
    GoalStatus.PAUSED: "goal_status_paused",
    GoalStatus.PENDING_APPROVAL: "goal_status_pending_approval",
    GoalStatus.BUDGET_LIMITED: "goal_status_budget_limited",
    GoalStatus.COMPLETE: "goal_status_complete",
    GoalStatus.CANCELLED: "goal_status_cancelled",
    GoalStatus.NEEDS_HUMAN_REVIEW: "goal_status_needs_review",
}


async def _resolve_chat_id(msg: InboundMessage) -> str | None:
    """Resolve channel message to DB chat_id via ChatService.

    Builds a SessionKey (matching agent executor convention) and queries the
    Chat table to find the latest chat_id for this channel peer. Returns None
    if no chat exists yet (first interaction).
    """
    from app.channels.types import SessionKey

    peer_kind = "group" if msg.is_group else "dm"
    peer_id = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
    if not peer_id:
        peer_id = f"channel-{msg.channel}"

    sk = SessionKey(
        channel=msg.channel,
        peer_kind=peer_kind,
        peer_id=peer_id,
        thread_id=msg.thread_id,
    )
    base_key = sk.to_str()

    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_channel_chat_by_key(base_key)
    if chat:
        return chat.id

    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import Chat

    async with get_session() as session:
        result = await session.execute(
            select(Chat.id)
            .where(Chat.channel_session_key.like(f"{base_key}%"))
            .order_by(Chat.updated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row


class ChannelGoalCommandHandler:
    """Handles /goal subcommands by delegating to the GoalProvider."""

    async def handle_goal(
        self,
        msg: InboundMessage,
        subcommand: GoalSubcommand,
        args: str,
    ) -> str:
        chat_id = await _resolve_chat_id(msg)

        match subcommand:
            case GoalSubcommand.SET:
                return await self._set_goal(msg, chat_id, args)
            case GoalSubcommand.STATUS:
                return await self._show_status(msg, chat_id)
            case GoalSubcommand.PAUSE:
                return await self._pause_goal(msg, chat_id)
            case GoalSubcommand.RESUME:
                return await self._resume_goal(msg, chat_id)
            case GoalSubcommand.CLEAR:
                return await self._clear_goal(msg, chat_id)
            case GoalSubcommand.BUDGET:
                return await self._set_budget(msg, chat_id, args)

    async def get_kickoff_message(
        self,
        msg: InboundMessage,
        goal_text: str,
    ) -> InboundMessage | None:
        return dataclasses.replace(
            msg,
            content=goal_text,
            sent_at=time.time(),
        )

    async def _set_goal(
        self, msg: InboundMessage, chat_id: str | None, objective: str
    ) -> str:
        from app.services.agent.goal_registry import GoalRegistry

        if not objective.strip():
            return get_text(msg, "usage_goal")

        if not chat_id:
            return get_text(msg, "goal_set", goal=objective)

        from app.services.agent.goal_registry import check_and_handle_branch_stash

        await check_and_handle_branch_stash(chat_id)
        provider = GoalRegistry.get_or_create_provider(chat_id)
        goal = await provider.create_goal(session_id=chat_id, objective=objective)

        from myrm_agent_harness.agent.goals.types import GoalStatus

        if goal.status == GoalStatus.QUEUED:
            return get_text(msg, "goal_queued", goal=goal.objective)
        return get_text(msg, "goal_set", goal=goal.objective)

    async def _show_status(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_goal_is_set")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_is_set")

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_goal_is_set")

        status_key = _STATUS_KEYS.get(goal.status, "goal_status_label")
        label = get_text(msg, status_key)
        lines = [
            get_text(msg, "goal_status_header", objective=goal.objective),
            get_text(msg, "goal_status_line", status=label),
        ]

        if goal.budget:
            budget = goal.budget
            parts: list[str] = []
            if budget.max_tokens:
                parts.append(
                    get_text(
                        msg,
                        "goal_budget_tokens",
                        used=goal.tokens_used or 0,
                        max=budget.max_tokens,
                    )
                )
            if budget.max_turns:
                parts.append(
                    get_text(
                        msg,
                        "goal_budget_turns",
                        used=goal.turns_used or 0,
                        max=budget.max_turns,
                    )
                )
            if parts:
                lines.append(
                    get_text(msg, "goal_budget_header", parts=" | ".join(parts))
                )

        return "\n".join(lines)

    async def _pause_goal(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_to_pause")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_to_pause")

        goal = await provider.get_active_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_to_pause")

        await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
        return get_text(msg, "goal_paused", objective=goal.objective[:60])

    async def handle_subgoal(
        self,
        msg: InboundMessage,
        subcommand: SubgoalSubcommand,
        args: str,
    ) -> str:
        chat_id = await _resolve_chat_id(msg)
        if not chat_id:
            return get_text(msg, "no_active_goal_session")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            from myrm_agent_harness.agent.goals.manager import GoalManager

            from app.platform_utils import get_storage_provider

            provider = GoalManager(get_storage_provider())

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_subgoals")

        match subcommand:
            case SubgoalSubcommand.ADD:
                if not args.strip():
                    return get_text(msg, "usage_subgoal_add")
                subgoal = await provider.add_subgoal(goal.goal_id, args)
                return get_text(msg, "subgoal_added", text=subgoal["text"])
            case SubgoalSubcommand.LIST:
                if not goal.subgoals:
                    return get_text(msg, "no_subgoals_defined")
                lines = [get_text(msg, "current_subgoals")]
                for i, sg in enumerate(goal.subgoals):
                    lines.append(f"{i}. {sg['text']}")
                return "\n".join(lines)
            case SubgoalSubcommand.REMOVE:
                try:
                    index = int(args.strip())
                    removed = await provider.remove_subgoal(goal.goal_id, index)
                    return get_text(msg, "subgoal_removed", text=removed["text"])
                except ValueError:
                    return get_text(msg, "usage_subgoal_remove")
                except IndexError:
                    return get_text(
                        msg, "subgoal_index_out_of_range", index=args.strip()
                    )
            case SubgoalSubcommand.CLEAR:
                count = await provider.clear_subgoals(goal.goal_id)
                return get_text(msg, "cleared_subgoals", count=count)

    async def _resume_goal(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_goal_to_resume")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_to_resume")

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_goal_to_resume")

        if goal.status == GoalStatus.ACTIVE:
            return get_text(msg, "goal_already_active")

        if goal.status not in {GoalStatus.PAUSED, GoalStatus.BUDGET_LIMITED}:
            return get_text(msg, "goal_cannot_resume", status=goal.status.value)

        await provider.resume_goal(goal.goal_id)
        return get_text(msg, "goal_resumed", objective=goal.objective[:60])

    async def _clear_goal(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_goal_to_clear")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_to_clear")

        goal = await provider.get_active_goal(chat_id)
        if not goal:
            latest = await provider.get_latest_goal(chat_id)
            if latest and latest.status in {
                GoalStatus.PAUSED,
                GoalStatus.BUDGET_LIMITED,
            }:
                goal = latest
            else:
                return get_text(msg, "no_active_goal_to_clear")

        await provider.update_status(goal.goal_id, GoalStatus.CANCELLED)
        return get_text(msg, "goal_cleared", objective=goal.objective[:60])

    async def _set_budget(
        self, msg: InboundMessage, chat_id: str | None, args: str
    ) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_set_first")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_set_first")

        goal = await provider.get_active_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_budget")

        if not args.strip():
            return get_text(msg, "usage_goal_budget")

        try:
            max_turns = int(args.strip())
            if max_turns < 1:
                return get_text(msg, "budget_at_least_one")
        except ValueError:
            return get_text(msg, "invalid_budget")

        await provider.set_budget(
            goal.goal_id,
            GoalBudget(max_turns=max_turns),
        )
        return get_text(msg, "goal_budget_set", max_turns=max_turns)
