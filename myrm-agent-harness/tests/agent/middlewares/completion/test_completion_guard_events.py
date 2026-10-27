"""The guard's decisions are recorded in the session event log, by name and count only.

A held-back answer leaves nothing in the conversation or the tool trace, so the event is how a trace tells why a
turn took more model calls than the answer needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log.types import get_persistent_event_types
from myrm_agent_harness.agent.middlewares._session_context import set_event_logger
from myrm_agent_harness.agent.middlewares.completion.completion_directive import BlockReasons
from myrm_agent_harness.agent.middlewares.completion.completion_guard import CompletionGuard, reset_completion_guard
from myrm_agent_harness.agent.middlewares.completion.completion_guard_events import (
    COMPLETION_GUARD_EVENT,
    log_guard_decision,
)
from tests.support.completion_guard_harness import runtime, state, verdict

_REQUEST = "今天最新的 AI 新闻是什么？"
_FROM_MEMORY = "根据我所知，近期 AI 领域的主要进展包括多模态模型与推理能力的提升。"


class RecordingLogger:
    """Stands for the session's EventLogger: keeps what it was asked to log."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def log(self, event_type: str, data: dict[str, object]) -> None:
        self.events.append((event_type, data))


@pytest.fixture
def recorder() -> RecordingLogger:
    reset_completion_guard()
    logger = RecordingLogger()
    set_event_logger(logger)  # type: ignore[arg-type]
    yield logger
    set_event_logger(None)


def test_the_event_type_is_one_the_event_log_persists() -> None:
    assert COMPLETION_GUARD_EVENT in get_persistent_event_types()


class TestBlockReasonNames:
    def test_names_the_checks_that_fired_in_reading_order(self) -> None:
        reasons = BlockReasons(execution_claim="x", evidence="y", ppt_outline="z")

        assert reasons.names() == ("evidence", "execution_claim", "ppt_outline")

    def test_an_unreachable_evidence_demand_is_named_apart_from_a_plain_one(self) -> None:
        assert BlockReasons(evidence="x", evidence_unreachable=True).names() == ("evidence_unreachable",)

    def test_no_reason_means_the_checklist_held_the_answer(self) -> None:
        assert BlockReasons().names() == ("checklist",)


class TestDecisionEvent:
    @pytest.mark.asyncio
    async def test_a_held_back_answer_is_recorded_with_its_reason_and_place_in_the_budget(
        self, recorder: RecordingLogger, tmp_path: Path
    ) -> None:
        guard = CompletionGuard(max_rejections=3)

        await verdict(guard, state(_REQUEST, _FROM_MEMORY), runtime(tmp_path))

        assert recorder.events == [
            (
                "completion_guard",
                {
                    "action": "held_back",
                    "reasons": ["evidence"],
                    "rejection": 1,
                    "max_rejections": 3,
                    "staged_artifacts": 0,
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_the_forced_finish_is_recorded_once_the_budget_is_spent(
        self, recorder: RecordingLogger, tmp_path: Path
    ) -> None:
        guard = CompletionGuard(max_rejections=1)
        messages = state(_REQUEST, _FROM_MEMORY)

        await verdict(guard, messages, runtime(tmp_path))
        await verdict(guard, messages, runtime(tmp_path))

        actions = [(data["action"], data["rejection"]) for _, data in recorder.events]
        assert actions == [("held_back", 1), ("forced_finish", 1)]

    @pytest.mark.asyncio
    async def test_the_event_carries_no_user_content(self, recorder: RecordingLogger, tmp_path: Path) -> None:
        await verdict(CompletionGuard(), state(_REQUEST, _FROM_MEMORY), runtime(tmp_path))

        assert "AI 新闻" not in str(recorder.events)
        assert "多模态" not in str(recorder.events)

    @pytest.mark.asyncio
    async def test_an_answer_that_passes_records_nothing(self, recorder: RecordingLogger, tmp_path: Path) -> None:
        assert (
            await verdict(CompletionGuard(), state("解释一下什么是向量数据库", _FROM_MEMORY), runtime(tmp_path)) is None
        )
        assert recorder.events == []

    @pytest.mark.asyncio
    async def test_a_run_without_an_event_logger_is_held_back_all_the_same(self, tmp_path: Path) -> None:
        reset_completion_guard()
        set_event_logger(None)

        await log_guard_decision(BlockReasons(evidence="x"), rejection=1, max_rejections=3)
        result = await verdict(CompletionGuard(), state(_REQUEST, _FROM_MEMORY), runtime(tmp_path))

        assert result is not None
        assert result["jump_to"] == "model"
