"""ChannelGoalCommandHandler — /goal slash command handler.

[INPUT]
- app.channels.types::InboundMessage, app.channels.protocols.goal_command (POS)
- app.services.agent.goals.goal_registry::GoalRegistry, app.services.agent.goals.goal_controls::select_cancellable_goal, stop_goal_turn, wait_for_stopped_turn, can_start_goal_turn (POS)
- goal_handler.chat_resolution::resolve_chat_id, goal_handler.status_view::render_goal_status (POS)

[OUTPUT]
- ChannelGoalCommandHandler: GoalCommandHandler protocol implementation

[POS]
Connects /goal slash commands from IM channels to the Goal engine via GoalRegistry.
"""

from __future__ import annotations

import dataclasses
import time

from myrm_agent_harness.agent.goals.types import GoalBudget, GoalStatus

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.protocols.goal_command import (
    GoalSubcommand,
    SubgoalSubcommand,
)
from app.channels.types import InboundMessage

from .chat_resolution import resolve_chat_id
from .status_view import render_goal_status


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


class ChannelGoalCommandHandler:
    """Handles /goal subcommands by delegating to the GoalProvider."""

    async def handle_goal(
        self,
        msg: InboundMessage,
        subcommand: GoalSubcommand,
        args: str,
    ) -> str:
        chat_id = await resolve_chat_id(msg)

        match subcommand:
            case GoalSubcommand.SET:
                return await self._set_goal(msg, chat_id, args)
            case GoalSubcommand.STATUS:
                return await self._show_status(msg, chat_id)
            case GoalSubcommand.PAUSE:
                return await self._pause_goal(msg, chat_id, args)
            case GoalSubcommand.RESUME:
                return await self._resume_goal(msg, chat_id)
            case GoalSubcommand.CLEAR:
                return await self._clear_goal(msg, chat_id)
            case GoalSubcommand.BUDGET:
                return await self._set_budget(msg, chat_id, args)
            case GoalSubcommand.CONSTRAINT:
                return await self._manage_constraint(msg, chat_id, args)
            case GoalSubcommand.WAIT:
                return await self._wait_goal(msg, chat_id, args)
            case GoalSubcommand.UNWAIT:
                return await self._unwait_goal(msg, chat_id)

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

    async def get_resume_kickoff_message(self, msg: InboundMessage) -> InboundMessage | None:
        from app.services.agent.goals.goal_controls import can_start_goal_turn
        from app.services.agent.goals.goal_registry import GoalRegistry

        chat_id = await resolve_chat_id(msg)
        provider = GoalRegistry.get_provider(chat_id) if chat_id else None
        if chat_id is None or provider is None or not can_start_goal_turn(chat_id):
            return None
        goal = await provider.get_latest_goal(chat_id)
        if goal is None or goal.status is not GoalStatus.ACTIVE:
            return None
        return await self.get_kickoff_message(msg, goal.objective)

    async def _set_goal(self, msg: InboundMessage, chat_id: str | None, objective: str) -> str:
        from app.services.agent.goals.goal_registry import GoalRegistry

        if not objective.strip():
            return get_text(msg, "usage_goal")

        parsed_objective, acceptance_criteria = _parse_im_goal_text(objective)

        if not chat_id:
            return get_text(msg, "goal_set", goal=parsed_objective)

        from app.services.agent.goals.goal_branch_stash import check_and_handle_branch_stash

        await check_and_handle_branch_stash(chat_id)
        provider = GoalRegistry.get_or_create_provider(chat_id)
        source_meta: dict[str, object] = {
            "source_channel": msg.channel,
            "source_chat_id": msg.chat_id or msg.sender_id or "",
            "source_thread_id": msg.thread_id or "",
            "source_locale": resolve_message_locale(msg),
        }
        goal = await provider.create_goal(
            session_id=chat_id,
            objective=parsed_objective,
            acceptance_criteria=acceptance_criteria or None,
            metadata=source_meta,
        )

        if goal.status == GoalStatus.QUEUED:
            return get_text(msg, "goal_queued", goal=goal.objective)
        return get_text(msg, "goal_set", goal=goal.objective)

    async def _show_status(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_goal_is_set")

        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_is_set")

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_goal_is_set")

        return render_goal_status(msg, goal)

    async def _pause_goal(self, msg: InboundMessage, chat_id: str | None, note: str = "") -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_to_pause")

        from app.services.agent.goals.goal_controls import stop_goal_turn
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_to_pause")

        goal = await provider.get_active_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_to_pause")

        await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
        note = note.strip()
        if note:
            await provider.update_metadata(goal.goal_id, {"pause_reason": note})
        stop_goal_turn(chat_id, goal)
        return get_text(msg, "goal_paused", objective=goal.objective[:60])

    async def _wait_goal(self, msg: InboundMessage, chat_id: str | None, reason: str) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_to_pause")

        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_to_pause")

        goal = await provider.get_active_goal(chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_to_pause")

        if not hasattr(provider, "enter_wait"):
            return get_text(msg, "goal_wait_not_supported")

        wait_reason = reason.strip() or "Waiting for external process"
        await provider.enter_wait(goal.goal_id, reason=wait_reason)
        return get_text(msg, "goal_wait", objective=goal.objective[:60], reason=wait_reason[:80])

    async def _unwait_goal(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_to_pause")

        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_active_goal_to_pause")

        goal = await provider.get_latest_goal(chat_id)
        if not goal or goal.status != GoalStatus.WAIT:
            return get_text(msg, "goal_not_waiting")

        if not hasattr(provider, "exit_wait"):
            return get_text(msg, "goal_wait_not_supported")

        await provider.exit_wait(goal.goal_id)
        return get_text(msg, "goal_unwait", objective=goal.objective[:60])

    async def handle_subgoal(
        self,
        msg: InboundMessage,
        subcommand: SubgoalSubcommand,
        args: str,
    ) -> str:
        chat_id = await resolve_chat_id(msg)
        if not chat_id:
            return get_text(msg, "no_active_goal_session")

        from app.services.agent.goals.goal_registry import GoalRegistry

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

        from app.services.agent.goals.goal_controls import note_goal_resumed, wait_for_stopped_turn
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_to_resume")

        goal = await provider.get_latest_goal(chat_id)
        if not goal:
            return get_text(msg, "no_goal_to_resume")

        if goal.status == GoalStatus.ACTIVE:
            return get_text(msg, "goal_active_exists", objective=goal.objective[:60])

        if goal.status not in {GoalStatus.PAUSED, GoalStatus.BUDGET_LIMITED}:
            return get_text(msg, "goal_cannot_resume", status=goal.status.value)

        if not await wait_for_stopped_turn(chat_id):
            return get_text(msg, "goal_resume_stopping")
        await provider.resume_goal(goal.goal_id)
        note_goal_resumed(chat_id)
        return get_text(msg, "goal_resumed", objective=goal.objective[:60])

    async def _clear_goal(self, msg: InboundMessage, chat_id: str | None) -> str:
        if not chat_id:
            return get_text(msg, "no_goal_to_clear")

        from app.services.agent.goals.goal_controls import select_cancellable_goal, stop_goal_turn
        from app.services.agent.goals.goal_registry import GoalRegistry

        provider = GoalRegistry.get_provider(chat_id)
        if not provider:
            return get_text(msg, "no_goal_to_clear")

        goal = await select_cancellable_goal(provider, chat_id)
        if not goal:
            return get_text(msg, "no_active_goal_to_clear")

        await provider.update_status(goal.goal_id, GoalStatus.CANCELLED)
        stop_goal_turn(chat_id, goal)
        return get_text(msg, "goal_cleared", objective=goal.objective[:60])

    async def _set_budget(self, msg: InboundMessage, chat_id: str | None, args: str) -> str:
        if not chat_id:
            return get_text(msg, "no_active_goal_set_first")

        from app.services.agent.goals.goal_registry import GoalRegistry

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

        from app.services.agent.goals.goal_registry import GoalRegistry

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
