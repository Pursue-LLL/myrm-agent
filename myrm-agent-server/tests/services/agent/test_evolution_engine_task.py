"""Unit tests for the background ``_run_evolution_task`` execution paths.

Covers the full task body: DB history loading, conversation-text building,
LLM initialization, harness capture, confidence approval, ws broadcast,
and error handling.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.evolution.engine import _run_evolution_task


def _fake_session_factory() -> Callable[[], object]:
    """Return a no-op async context manager factory for the DB session."""

    @asynccontextmanager
    async def _cm() -> AsyncIterator[object]:
        yield MagicMock()

    return _cm


def _history(roles: list[str], contents: list[str]) -> list[MagicMock]:
    messages = []
    for role, content in zip(roles, contents):
        msg = MagicMock()
        msg.role = role
        msg.content = content
        messages.append(msg)
    return messages


def _engine_class(proposal: object | None) -> MagicMock:
    engine_cls = MagicMock()
    engine_cls.return_value.capture_skill_from_trajectory = AsyncMock(return_value=proposal)
    return engine_cls


@pytest.mark.asyncio
async def test_too_short_history_skips_llm_and_capture() -> None:
    """Fewer than 4 persisted messages → task returns without LLM/engine work."""
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory),
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(return_value=_history(["user"], ["hi"])),
        ) as get_messages,
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(),
        ) as get_llm,
        patch(
            "myrm_agent_harness.agent.skills.evolution.core.engine.SkillEvolutionEngine"
        ) as engine_cls,
    ):
        await _run_evolution_task("chat-short", MagicMock())

    get_messages.assert_awaited_once_with("chat-short")
    get_llm.assert_not_called()
    engine_cls.assert_not_called()


@pytest.mark.asyncio
async def test_builds_conversation_text_from_history() -> None:
    """No conversation_text → last-10 history turns are joined and captured."""
    history = _history(
        ["user", "assistant", "user", "assistant"],
        ["question-one", "answer-one", "question-two", "answer-two"],
    )
    engine_cls = _engine_class(None)
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory),
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(return_value=history),
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(),
        ) as get_llm,
        patch(
            "myrm_agent_harness.agent.skills.evolution.core.engine.SkillEvolutionEngine",
            return_value=engine_cls.return_value,
        ) as engine_cls_patch,
        patch("myrm_agent_harness.agent.skills.evolution.db.store.SkillStore"),
    ):
        await _run_evolution_task("chat-full", MagicMock())

    get_llm.assert_awaited_once()
    engine_cls_patch.assert_called_once()
    capture = engine_cls_patch.return_value.capture_skill_from_trajectory
    capture.assert_awaited_once()
    trajectory = capture.call_args.kwargs["trajectory"]
    assert "question-one" in trajectory
    assert "answer-two" in trajectory


@pytest.mark.asyncio
async def test_conversation_text_skips_db_load() -> None:
    """DW-supplied conversation_text bypasses the DB history load."""
    engine_cls = _engine_class(None)
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory) as get_factory,
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(),
        ) as get_messages,
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(),
        ),
        patch(
            "myrm_agent_harness.agent.skills.evolution.core.engine.SkillEvolutionEngine",
            return_value=engine_cls.return_value,
        ) as engine_cls_patch,
        patch("myrm_agent_harness.agent.skills.evolution.db.store.SkillStore"),
    ):
        await _run_evolution_task("chat-dw", MagicMock(), conversation_text="DW outcome text")

    get_factory.assert_not_called()
    get_messages.assert_not_called()
    trajectory = engine_cls_patch.return_value.capture_skill_from_trajectory.call_args.kwargs["trajectory"]
    assert trajectory == "DW outcome text"


@pytest.mark.asyncio
async def test_proposal_none_skips_approval_flow() -> None:
    """No reusable proposal → confidence flow and broadcast are untouched."""
    history = _history(["user", "assistant", "user", "assistant"], ["q1", "a1", "q2", "a2"])
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory),
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(return_value=history),
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(),
        ),
        patch(
            "myrm_agent_harness.agent.skills.evolution.core.engine.SkillEvolutionEngine",
            return_value=_engine_class(None).return_value,
        ),
        patch("myrm_agent_harness.agent.skills.evolution.db.store.SkillStore"),
        patch(
            "app.services.agent.confidence_approval_flow.ConfidenceApprovalFlow"
        ) as flow_cls,
    ):
        await _run_evolution_task("chat-noprop", MagicMock())

    flow_cls.assert_not_called()


@pytest.mark.asyncio
async def test_proposal_processed_and_broadcast() -> None:
    """Reusable proposal → ConfidenceApprovalFlow processed and ws broadcast."""
    history = _history(["user", "assistant", "user", "assistant"], ["q1", "a1", "q2", "a2"])
    proposal = MagicMock()
    proposal.skill_id = "reusable-skill"
    proposal.to_dict.return_value = {"id": "reusable-skill"}
    flow = MagicMock()
    flow.process_evolution = AsyncMock()
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory),
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(return_value=history),
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(),
        ),
        patch(
            "myrm_agent_harness.agent.skills.evolution.core.engine.SkillEvolutionEngine",
            return_value=_engine_class(proposal).return_value,
        ),
        patch("myrm_agent_harness.agent.skills.evolution.db.store.SkillStore"),
        patch(
            "app.services.agent.confidence_approval_flow.ConfidenceApprovalFlow",
            return_value=flow,
        ) as flow_cls,
        patch(
            "app.services.skills.ws_hub.broadcast_proposal",
            new=AsyncMock(),
        ) as broadcast,
    ):
        await _run_evolution_task("chat-prop", MagicMock())

    flow_cls.assert_called_once()
    flow.process_evolution.assert_awaited_once_with(proposal=proposal)
    broadcast.assert_awaited_once_with(proposal.to_dict())


@pytest.mark.asyncio
async def test_exception_is_logged() -> None:
    """Unexpected failure inside the task is caught and logged as error."""
    with (
        patch("app.platform_utils.get_session_factory", side_effect=_fake_session_factory),
        patch(
            "app.services.chat.chat_service.ChatService.get_all_messages",
            new=AsyncMock(side_effect=RuntimeError("db down")),
        ),
        patch("app.services.agent.evolution.engine.logger") as mock_logger,
    ):
        await _run_evolution_task("chat-err", MagicMock())

    mock_logger.error.assert_called_once()
