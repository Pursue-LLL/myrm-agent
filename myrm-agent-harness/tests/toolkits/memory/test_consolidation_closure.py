"""A consolidation result may re-word and re-date what the model read, but never state a number or identifier new.

The closure is deterministic and reads no store. Its coverage is the numbers (separators, ``k`` / ``万`` / ``亿`` and
``%`` folded, dates and times exempt in numeric and month-name spellings, the year a source date writes counted as
stated, whole numbers below one hundred exempt) and the identifiers the two extractors know (ports, addresses, URLs,
variables, paths, versions, UUIDs, hashes); the limits after the parametrized cases are documented behavior, so a
change to any of them has to be deliberate.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.strategies.consolidation_closure import facts_of
from myrm_agent_harness.toolkits.memory.strategies.consolidation_insights import validated_insights
from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import CorrectOp, MergeOp, UpdateContentOp
from myrm_agent_harness.toolkits.memory.strategies.consolidation_ops_filter import filter_and_guard_operations
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import _build_id_map
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


def states_something_new(sources: list[str], candidate: str) -> bool:
    return not facts_of(candidate).beyond(facts_of(*sources)).is_empty


WORDING_OR_FORMAT_ONLY = [
    (
        ["User's monthly rent is 4500 yuan", "Rent is paid on the 5th"],
        "User's monthly rent is 4500 yuan, paid on the 5th",
    ),
    (["Rent is 4,500 yuan"], "Rent is 4500 yuan"),
    (["房租４５００元"], "房租4500元"),
    (["Meeting yesterday", "Agenda: budget"], "Meeting on 2026-11-11 about the budget"),
    (["Salary is 4.5k per month"], "Salary is 4500 per month"),
    (["年收入30万"], "年收入300000元"),
    (["User has two dogs", "One dog is named Rex"], "User has 2 dogs, one named Rex"),
    (["会议下午3点", "地点在三楼"], "会议15:00,地点在3楼"),
    (["User has 2 dogs", "Rex is the older one"], "User has two dogs, Rex the older"),
    (["Paid on the 5th"], "Paid on day 5"),
    (["Savings rate is 35%"], "Savings rate is 0.35"),
    (["Savings rate is 35%"], "Savings rate is 35% of income"),
    (["Uses Python 3.13 and Node 22"], "Uses Python 3.13 with Node 22"),
    (["上个月的会议"], "2026年10月的会议"),
    (["Staging at 10.0.0.5:8080"], "Staging is reachable at 10.0.0.5:8080"),
    (["Release v2.4.1 shipped"], "Release 2.4.1 shipped"),
    (["ports 80, 443"], "ports 80, 443 are open"),
    (["Lease signed 2024-03-01", "Rent is due on the 1st"], "Lease signed March 1, 2024; rent due on the 1st"),
    (["Lease signed 2024-03-01"], "Lease signed in March 2024"),
    (["Lease signed 2024-03-01"], "Lease signed in 2024"),
    (["Joined on 1st of March, 2019"], "Joined on 2019-03-01"),
    (["Meeting yesterday"], "Meeting on Nov. 11th, 2026 at 3:30 PM"),
    (["Meeting yesterday"], "Meeting on 11 November 2026"),
    (["Meeting last month"], "Meeting in October 2026"),
    (["2019年3月入职"], "Joined in 2019"),
]

NEW_NUMBER_OR_IDENTIFIER = [
    (["User's monthly rent is 4500 yuan"], "User's monthly rent is 5400 yuan"),
    (["User pays rent monthly"], "User pays 4500 rent monthly"),
    (["Savings rate is high"], "Savings rate is 35%"),
    (["Rent 4500 yuan", "Utilities 600 yuan"], "Housing cost 5100 yuan"),
    (["Salary is 4.5k per month"], "Salary is 45000 per month"),
    (["Staging uses 10.0.0.5"], "Staging uses 10.0.0.6"),
    (["Release v2.4.1 shipped"], "Release v2.4.2 shipped"),
    (["id 123e4567-e89b-12d3-a456-426614174000"], "id 123e4567-e89b-12d3-a456-426614174999"),
    (["Reads the config file"], "Reads DATABASE_URL from the config file"),
    (["Docs are online"], "Docs are at https://example.com/docs"),
    (["Lease signed 2024-03-01"], "Lease signed in 2025"),
    (["Budget review is next week"], "Marketing 2024 budget review"),
    (["Units sold in March"], "Units sold in Mar 5000"),
]


@pytest.mark.parametrize(("sources", "candidate"), WORDING_OR_FORMAT_ONLY)
def test_a_rewrite_that_changes_only_wording_or_format_states_nothing_new(sources: list[str], candidate: str) -> None:
    assert not states_something_new(sources, candidate)


@pytest.mark.parametrize(("sources", "candidate"), NEW_NUMBER_OR_IDENTIFIER)
def test_a_result_stating_a_number_or_identifier_no_source_states_is_caught(sources: list[str], candidate: str) -> None:
    assert states_something_new(sources, candidate)


def test_known_limit_a_cjk_numeral_rewritten_as_digits_reads_as_new() -> None:
    assert states_something_new(["房租四千五"], "房租4500元")


def test_known_limit_arithmetic_on_whole_numbers_below_one_hundred_is_not_seen() -> None:
    assert not states_something_new(["User has 2 dogs", "User has 1 cat"], "User has 3 pets")


def test_known_limit_a_changed_date_is_not_seen() -> None:
    assert not states_something_new(["Lease signed 2024-03-01"], "Lease signed 2025-03-01")


def _window(*contents: str) -> tuple[list[SemanticMemory], dict[str, str]]:
    memories = [SemanticMemory(content=content) for content in contents]
    return memories, _build_id_map(memories)


def test_a_merge_may_state_only_what_its_own_sources_state() -> None:
    memories, id_map = _window("Rent is 4500 yuan", "Rent is paid on the 5th", "The year-end bonus is 5400 yuan")
    rent, due, _ = (m.id for m in memories)
    drawn_from_a_stranger = MergeOp(source_ids=[rent, due], merged_content="Rent is 5400 yuan, paid on the 5th")
    faithful = MergeOp(source_ids=[rent, due], merged_content="Rent is 4500 yuan, paid on the 5th")

    refused = filter_and_guard_operations([drawn_from_a_stranger], memories, id_map)
    accepted = filter_and_guard_operations([faithful], memories, id_map)

    assert (refused.operations, refused.rejected) == ([], 1)
    assert (accepted.operations, accepted.rejected) == ([faithful], 0)


def test_a_correction_or_rewrite_may_state_anything_the_model_read() -> None:
    memories, id_map = _window("Rent is 4500 yuan", "The year-end bonus is 5400 yuan")
    rent, _ = (m.id for m in memories)
    correction = CorrectOp(memory_id=rent, corrected_content="Rent is 5400 yuan")
    invented = UpdateContentOp(memory_id=rent, new_content="Rent is 6100 yuan")

    assert filter_and_guard_operations([correction], memories, id_map).operations == [correction]
    assert filter_and_guard_operations([invented], memories, id_map).operations == []


def test_an_invented_identifier_is_rejected_not_repaired() -> None:
    memories, id_map = _window("Staging uses 10.0.0.5 for the API", "Staging runs the nightly job")
    first, second = (m.id for m in memories)
    merge = MergeOp(source_ids=[first, second], merged_content="Staging uses 10.0.0.6 for the API and the nightly job")

    result = filter_and_guard_operations([merge], memories, id_map)

    assert (result.operations, result.guard_patched, result.rejected) == ([], 0, 1)


def test_an_insight_may_state_only_what_the_analyzed_memories_state() -> None:
    memories = [SemanticMemory(content="Rent is 4500 yuan"), SemanticMemory(content="Rent is paid on the 5th")]

    kept, rejected = validated_insights(
        ["User budgets around a 4500 yuan rent", "User saves 35% of income every month"], memories
    )

    assert (kept, rejected) == (["User budgets around a 4500 yuan rent"], 1)


def test_no_insights_means_nothing_to_check() -> None:
    assert validated_insights([], [SemanticMemory(content="Rent is 4500 yuan")]) == ([], 0)
