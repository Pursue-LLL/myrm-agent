"""The advice of an advisor round stays where it was written, so a provider that checks signed reasoning refuses nothing.

The advisors write for the acting model alone, and the advice never enters the stored conversation. A reasoning block
the provider signed is valid only under the prompt it was written in, so a request that shows the advice followed by
one that does not (or shows it somewhere else) is refused. These cases run the whole shipped stack with the advisor
middleware in it against a provider double that enforces that, once for each fan-out policy.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic, RequestRecord (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::run_signed_loop, signed_loop_session (POS: three turns of the shipped agent in a tool loop against that double)

[POS]
Graph-level guard of where the advisor block stands: in every fan-out policy the advice of a round is carried by each
later request of its run, unchanged and in the same place.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from itertools import pairwise
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from myrm_agent_harness.agent.middlewares.advisor_risk_trigger_router import (
    AdvisorRiskTriggerRouter,
    RiskTriggerDecision,
    RiskTriggerReason,
)
from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import create_moa_advisor_middleware
from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import MoAFanoutMode, MoAOverlayConfig
from tests.support.enforcing_anthropic import EnforcingAnthropic, RequestRecord
from tests.support.signed_tool_loop import PER_TURN, ROUNDS, TURNS, run_signed_loop, signed_loop_session

_NOTE = re.compile(r"ADVISOR-(\d+)")
# The risk policy asks the advisors on the second request of the first turn and the third of the second turn.
_RISKY_CALLS = frozenset({2, 10})


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


class _Advisor(BaseChatModel):
    """A reference model whose every answer is numbered, so one advisor round is told apart from another."""

    model_name: str = "advisor"
    answers: int = 0

    @property
    def _llm_type(self) -> str:
        return "numbered-advisor"

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.answers += 1
        text = f"ADVISOR-{self.answers}: read the file listing before you edit anything."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


class _ScriptedRisk(AdvisorRiskTriggerRouter):
    """Fires on chosen model calls, standing in for the tool-failure and loop-guard telemetry the real router reads."""

    def __init__(self, config: MoAOverlayConfig, *, on_calls: frozenset[int]) -> None:
        super().__init__(config)
        self._on_calls = on_calls
        self._calls = 0

    def evaluate_trigger(
        self, messages: Sequence[BaseMessage] | None = None, current_turn: int = 0
    ) -> RiskTriggerDecision:
        self._calls += 1
        if self._calls in self._on_calls:
            return RiskTriggerDecision(should_trigger=True, reason=RiskTriggerReason.CONSECUTIVE_TOOL_FAILURES)
        return RiskTriggerDecision(should_trigger=False)


async def _run(fanout: MoAFanoutMode, *, streaming: bool = True) -> EnforcingAnthropic:
    config = MoAOverlayConfig(fanout=fanout, every_n=2)
    router = _ScriptedRisk(config, on_calls=_RISKY_CALLS) if fanout == "risk_triggered" else None
    advisors = create_moa_advisor_middleware([_Advisor()], config=config, risk_router=router)
    double = EnforcingAnthropic(tool_rounds=ROUNDS)
    await run_signed_loop(double, streaming=streaming, extra=[advisors])
    return double


def _rounds_shown(record: RequestRecord) -> set[int]:
    """The advisor rounds whose advice the request carries."""
    return {int(number) for number in _NOTE.findall(record.text)}


def _assert_every_block_was_replayed(double: EnforcingAnthropic) -> None:
    """The provider took every request: each one sent back the whole loop's blocks, none of an earlier turn's."""
    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    assert [record.replayed for record in double.accepted] == list(range(PER_TURN)) * TURNS


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_the_advice_of_a_turn_is_read_by_every_request_of_that_turn_and_by_no_other(streaming: bool) -> None:
    double = await _run("user_turn", streaming=streaming)

    _assert_every_block_was_replayed(double)
    shown = [[_rounds_shown(record) for record in turn] for turn in double.turns]
    assert shown == [[{number}] * PER_TURN for number in range(1, TURNS + 1)]


@pytest.mark.asyncio
async def test_every_round_of_a_per_iteration_run_adds_its_advice_and_takes_none_back() -> None:
    double = await _run("per_iteration")

    _assert_every_block_was_replayed(double)
    for index, turn in enumerate(double.turns):
        first_round = index * PER_TURN + 1
        assert [_rounds_shown(record) for record in turn] == [
            set(range(first_round, first_round + requests)) for requests in range(1, PER_TURN + 1)
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fanout", ["every_n", "risk_triggered"])
async def test_advice_asked_for_part_way_through_a_turn_is_carried_by_the_requests_after_it(
    fanout: MoAFanoutMode,
) -> None:
    double = await _run(fanout)

    _assert_every_block_was_replayed(double)
    assert any(_rounds_shown(record) for record in double.accepted)
    for turn in double.turns:
        for earlier, later in pairwise(turn):
            assert _rounds_shown(earlier) <= _rounds_shown(later)
