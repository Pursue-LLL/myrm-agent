"""ChannelGoalCommandHandler — /goal slash command handler.

[INPUT]
- app.channels.types::InboundMessage, app.channels.protocols.goal_command (POS)
- app.services.agent.goal_registry::GoalRegistry, app.services.chat.chat_service::ChatService (POS)

[OUTPUT]
- ChannelGoalCommandHandler: GoalCommandHandler protocol implementation

[POS]
Connects /goal slash commands from IM channels to the Goal engine via GoalRegistry.
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


def _parse_im_goal_text(raw: str) -> tuple[str, list[dict[str, object]]]:
    """Parse IM goal text with optional ``||`` acceptance criteria separator.

    Format: ``objective || criteria1 || criteria2``
    The first segment is the objective; subsequent segments become semantic criteria.
    If no ``||`` is present, the entire string is the objective with no criteria.
    """
    parts = [p.strip() for p in raw.split("||")]
    objective = parts[0]
    criteria: list[dict[str, object]] = []
    for part in parts[1:]:
        if part:
            criteria.append({"type": "semantic", "criteria": part})
    return objective, criteria


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
            select(Chat.id).where(Chat.channel_session_key.like(f"{base_key}%")).order_by(Chat.updated_at.desc()).limit(1)
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
            case GoalSubcommand.CONSTRAINT:
                return await self._manage_constraint(msg, chat_id, args)

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

    async def _set_goal(self, msg: InboundMessage, chat_id: str | None, objective: str) -> str:
        from app.services.agent.goal_registry import GoalRegistry

        if not objective.strip():
            return get_text(msg, "usage_goal")

        parsed_objective, acceptance_criteria = _parse_im_goal_text(objective)

        if not chat_id:
            return get_text(msg, "goal_set", goal=parsed_objective)

        from app.services.agent.goal_registry import check_and_handle_branch_stash

        await check_and_handle_branch_stash(chat_id)
        provider = GoalRegistry.get_or_create_provider(chat_id)
        goal = await provider.create_goal(
            session_id=chat_id,
            objective=parsed_objective,
            acceptance_criteria=acceptance_criteria or None,
        )

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
                lines.append(get_text(msg, "goal_budget_header", parts=" | ".join(parts)))

        if goal.constraints:
            lines.append(get_text(msg, "goal_status_constraints", items=" | ".join(goal.constraints)))

        if goal.acceptance_criteria:
            criteria_items: list[str] = []
            for ac in goal.acceptance_criteria:
                if ac.get("type") == "shell":
                    criteria_items.append(f"[shell] {ac.get('command', '')}")
                else:
                    criteria_items.append(f"[semantic] {ac.get('criteria', '')}")
            lines.append(get_text(msg, "goal_status_criteria", items=" | ".join(criteria_items)))

        if goal.subgoals:
            items = " | ".join(sg.get("text", "") for sg in goal.subgoals)
            lines.append(get_text(msg, "goal_status_subgoals", items=items))

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
                    return get_text(msg, "subgoal_index_out_of_range", index=args.strip())
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

    async def _set_budget(self, msg: InboundMessage, chat_id: str | None, args: str) -> str:
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

    async def _manage_constraint(self, msg: InboundMessage, chat_id: str | None, args: str) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_set_first")

        from app.services.agent.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_set_first")

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_constraint")

        if args.strip().lower() == "clear":
            await provider.update_constraints(goal.goal_id, [])
            return get_text(msg, "goal_constraints_cleared")

        if not args.strip():
            if not goal.constraints:
                return get_text(msg, "no_constraints_set")
            return get_text(msg, "goal_status_constraints", items=" | ".join(goal.constraints))

        updated = (goal.constraints or []) + [args.strip()]
        await provider.update_constraints(goal.goal_id, updated)
        return get_text(msg, "goal_constraint_added", constraint=args.strip())
