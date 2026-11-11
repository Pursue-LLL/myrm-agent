"""The instruction of a held-back answer keeps its place for the rest of the run, so signed reasoning replays whole.

The guard's instruction is for the acting model alone and is never stored in the conversation. A reasoning block the
provider signed is valid only under the prompt it was written in, so a request that shows the instruction followed by
one that does not is refused. This case runs the whole shipped stack against a provider double that enforces that, with
a model whose every answer is a draft the guard holds back once.

[INPUT]
- tests.support.enforcing_anthropic::EnforcingAnthropic (POS: a Messages API double that refuses a replay the API would refuse)
- tests.support.signed_tool_loop::run_signed_loop, signed_loop_session (POS: three turns of the shipped agent in a tool loop against that double)
- tests.support.completion_guard_harness::CHECK_MARK (POS: the text every guard rejection starts with)

[POS]
Graph-level guard of where the completion directive stands: from the request that follows the held-back draft on, each
request of the run carries it unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.completion_guard_harness import CHECK_MARK
from tests.support.enforcing_anthropic import EnforcingAnthropic
from tests.support.signed_tool_loop import ROUNDS, run_signed_loop, signed_loop_session

_NEWS = "今天最新的 AI 新闻是什么？"
_FROM_MEMORY = "根据我所知，近期 AI 领域的主要进展包括多模态模型与推理能力的提升。"


@pytest.fixture(autouse=True)
def _session(tmp_path: Path) -> Iterator[None]:
    with signed_loop_session(tmp_path):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "non-stream"])
async def test_the_instruction_of_a_held_back_answer_stays_in_the_run_and_no_replay_is_refused(
    streaming: bool,
) -> None:
    double = EnforcingAnthropic(tool_rounds=ROUNDS, answer=_FROM_MEMORY)

    await run_signed_loop(double, streaming=streaming, prompt=_NEWS)

    assert double.refused == []
    assert all(record.thinking for record in double.accepted)
    for turn in double.turns:
        carries = [CHECK_MARK in record.text for record in turn]
        assert True in carries
        # The first request after the draft is the first to carry the instruction; none after it drops it.
        assert carries.index(True) > 0
        assert all(carries[carries.index(True) :])
