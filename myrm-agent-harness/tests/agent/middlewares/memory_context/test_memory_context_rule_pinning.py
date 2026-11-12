"""Which stored rules the memory block keeps when its budget cuts the rule list.

A rule reaches the block as ``{"trigger", "action", "source", "user_endorsed"}``, newest first: nothing marks it as a
prohibition, so the action's wording decides. A prohibition is pinned, so the budget cut drops other rules before
it. A positive rule that merely contains "never" ("whenever", "nevertheless", the identifier ``NEVER_EXPIRE``) must
not be pinned: it would crowd out rules that deserve the room more.

[INPUT]
- agent.middlewares.memory_context.memory_context_format::_format_memory_context (POS: renders the block and decides which rules are pinned)

[POS]
Classification and budget guard for the pinned prohibitions of the memory block's rule list.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
    MemoryBlock,
    _format_memory_context,
)

_FILLER_RULES = 100  # about 150 characters each: far more than the block's 10000-character budget


def _stored_rule(trigger: str, action: str) -> dict[str, object]:
    """A rule as the memory store hands it out: no marker says it is a prohibition."""
    return {"trigger": trigger, "action": action, "source": "user_extracted", "user_endorsed": False}


def _block_with_oldest(action: str) -> tuple[MemoryBlock, list[str]]:
    """The block for a store whose oldest rule has ``action``, and the rule lines that reached it.

    The oldest rule is listed last, where an unpinned rule is the first to go when the budget cuts.
    """
    filler = [_stored_rule("filler", f"keep answer {n} " + "x" * 120) for n in range(_FILLER_RULES)]
    block = _format_memory_context({"rules": [*filler, _stored_rule("any task", action)]})
    assert block.text is not None
    return block, [line.removeprefix("- ") for line in block.text.splitlines() if line.startswith("- When:")]


@pytest.mark.parametrize(
    "action",
    [
        pytest.param("never use git push --force", id="never"),
        pytest.param("Never use sudo", id="never-capitalised"),
        pytest.param("NEVER commit secrets", id="never-upper-case"),
        pytest.param("do not run destructive migrations", id="do-not"),
        pytest.param("Do not touch the .env file", id="do-not-capitalised"),
        pytest.param("deleting backups is forbidden", id="forbidden"),
        pytest.param("prohibited: writing outside the workspace", id="prohibited"),
        pytest.param("(never) edit generated files", id="never-after-a-bracket"),
        pytest.param("禁止提交密钥", id="zh-forbid"),
        pytest.param("严禁使用 Any 类型", id="zh-strictly-forbid"),
        pytest.param("不得提交密钥", id="zh-must-not"),
        pytest.param("绝对never使用sudo", id="never-next-to-cjk"),
        pytest.param("永远forbidden这个操作", id="forbidden-next-to-cjk"),
        pytest.param("never, ever commit secrets", id="never-before-a-comma"),
        pytest.param("'never' push to main", id="never-in-quotes"),
        pytest.param("never- push to main", id="never-before-a-dangling-hyphen"),
        pytest.param("deploy--never on friday", id="never-after-a-dash"),
    ],
)
def test_a_prohibition_survives_the_budget_cut_whatever_its_age(action: str) -> None:
    block, lines = _block_with_oldest(action)

    assert f"When: any task → Do: {action}" in lines
    assert block.rules_injected < block.rules_configured, "the filler must make the budget cut rules"


@pytest.mark.parametrize(
    "action",
    [
        pytest.param("ask the user whenever the requirement is unclear", id="whenever"),
        pytest.param("nevertheless keep answers short", id="nevertheless"),
        pytest.param("keep neverending lists short", id="neverending"),
        pytest.param("keep NEVER_EXPIRE as the sentinel constant", id="never-in-a-constant"),
        pytest.param("rename never_expire to keep_forever", id="never-in-an-identifier"),
        pytest.param("prefer prohibited_words over a blocklist", id="prohibited-in-an-identifier"),
        pytest.param("Never2Sleep is the watchdog name", id="never-before-a-digit"),
        pytest.param("never-ending retries are fine", id="never-in-a-hyphenated-compound"),
        pytest.param("allow non-prohibited actions without asking", id="prohibited-after-a-hyphen-prefix"),
        pytest.param("不得不修改配置时，先备份再改", id="zh-have-to"),
        pytest.param("万不得已才使用 sudo", id="zh-no-choice"),
        pytest.param("add tests when behavior changes", id="no-negation"),
        pytest.param("avoid long answers", id="avoid"),
    ],
)
def test_a_positive_rule_is_not_pinned_and_goes_first_when_the_budget_cuts(action: str) -> None:
    _, lines = _block_with_oldest(action)

    assert f"When: any task → Do: {action}" not in lines


def test_the_cut_keeps_every_prohibition_and_drops_the_unpinned_rules_from_the_end() -> None:
    prohibitions = {7: "never touch prod", 55: "禁止提交密钥", _FILLER_RULES - 1: "do not force push"}
    actions = [prohibitions.get(n, f"keep answer {n} " + "x" * 120) for n in range(_FILLER_RULES)]

    block = _format_memory_context({"rules": [_stored_rule("any task", action) for action in actions]})

    assert block.text is not None
    prefix = "- When: any task → Do: "
    kept = [line.removeprefix(prefix) for line in block.text.splitlines() if line.startswith(prefix)]
    assert [action for action in kept if action in prohibitions.values()] == list(prohibitions.values())
    kept_unpinned = [action for action in kept if action not in prohibitions.values()]
    unpinned = [action for action in actions if action not in prohibitions.values()]
    assert kept_unpinned == unpinned[: len(kept_unpinned)]
    assert 0 < len(kept_unpinned) < len(unpinned)
    assert (block.rules_configured, block.rules_injected) == (_FILLER_RULES, len(kept))
    assert "Some lower-priority memory items were truncated" in block.text


def test_the_block_counts_every_rule_it_lists() -> None:
    block = _format_memory_context(
        {
            "rules": [
                _stored_rule("committing", "never use git push --force"),
                _stored_rule("writing code", "add tests whenever behavior changes"),
                _stored_rule("any task", "禁止提交密钥"),
                "not a rule",
            ]
        }
    )

    assert (block.rules_configured, block.rules_injected) == (3, 3)
