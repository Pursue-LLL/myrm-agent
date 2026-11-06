"""Which stored rules the memory block presents as vetoes, and what a veto line says.

A rule reaches the block as ``{"trigger", "action", "priority", "user_endorsed"}``: nothing marks it as a veto, so the
action's wording decides. A positive rule that merely contains "never" ("whenever", "nevertheless") would be shown to
the model as ``[NEVER] ...``, the opposite of what it says, and a veto that drops its trigger would bind everywhere.

[INPUT]
- agent.middlewares.memory_context.memory_context_format::_format_memory_context, MANDATORY_VETO_TITLE, STABLE_RULES_TITLE (POS: renders the block and classifies its rules)

[POS]
Classification and rendering guard for the VETO section of the memory block.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
    MANDATORY_VETO_TITLE,
    STABLE_RULES_TITLE,
    _format_memory_context,
)


def _stored_rule(trigger: str, action: str, priority: int = 0) -> dict[str, object]:
    """A rule as the memory store hands it out: these four keys and no veto marker."""
    return {"trigger": trigger, "action": action, "priority": priority, "user_endorsed": False}


def _lines(rules: list[dict[str, object]]) -> list[str]:
    block = _format_memory_context({"rules": rules}).text
    assert block is not None
    return [line.removeprefix("- ") for line in block.splitlines() if line.startswith("- ")]


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
    ],
)
def test_a_prohibition_is_presented_as_a_veto(action: str) -> None:
    lines = _lines([_stored_rule("any task", action)])

    assert lines == [f"[NEVER] {action} (Scope: any task)"]


@pytest.mark.parametrize(
    "action",
    [
        pytest.param("ask the user whenever the requirement is unclear", id="whenever"),
        pytest.param("nevertheless keep answers short", id="nevertheless"),
        pytest.param("keep neverending lists short", id="neverending"),
        pytest.param("不得不修改配置时，先备份再改", id="zh-have-to"),
        pytest.param("万不得已才使用 sudo", id="zh-no-choice"),
        pytest.param("add tests when behavior changes", id="no-negation"),
        pytest.param("avoid long answers", id="avoid"),
    ],
)
def test_a_positive_rule_stays_a_behavioral_rule_with_its_trigger(action: str) -> None:
    lines = _lines([_stored_rule("requirement unclear", action)])

    assert lines == [f"When: requirement unclear → Do: {action}"]


def test_the_sections_hold_each_kind_of_rule_and_the_block_counts_them_all() -> None:
    block = _format_memory_context(
        {
            "rules": [
                _stored_rule("committing", "never use git push --force", 10),
                _stored_rule("writing code", "add tests whenever behavior changes"),
                _stored_rule("any task", "禁止提交密钥", 5),
                _stored_rule("review", "check edge cases"),
                _stored_rule("deploying", "do not deploy on friday"),
            ]
        }
    )

    assert block.text is not None
    veto_part, _, rules_part = block.text.partition(f"## {STABLE_RULES_TITLE}")
    assert f"## {MANDATORY_VETO_TITLE}" in veto_part
    assert veto_part.count("[NEVER]") == 3
    assert rules_part.count("- When:") == 2
    assert (block.rules_configured, block.rules_injected) == (5, 5)


@pytest.mark.parametrize(
    ("rule", "scope"),
    [
        pytest.param({"trigger": "committing", "action": "never amend pushed commits"}, "committing", id="trigger"),
        pytest.param({"action": "never amend pushed commits"}, "*", id="no-trigger"),
        pytest.param({"trigger": "", "action": "never amend pushed commits"}, "*", id="empty-trigger"),
        pytest.param(
            {"trigger": "committing", "action": "never amend pushed commits", "tool_name": "bash_tool"},
            "bash_tool",
            id="tool-beats-trigger",
        ),
        pytest.param(
            {"trigger": "committing", "action": "never amend pushed commits", "veto_scope": "git"},
            "git",
            id="explicit-scope-beats-trigger",
        ),
    ],
)
def test_a_veto_applies_where_it_was_stored_for(rule: dict[str, object], scope: str) -> None:
    lines = _lines([rule])

    assert lines == [f"[NEVER] never amend pushed commits (Scope: {scope})"]


@pytest.mark.parametrize(
    "marker",
    [
        pytest.param({"is_veto": True}, id="is_veto"),
        pytest.param({"category": "veto"}, id="category"),
        pytest.param({"category": "VETO"}, id="category-upper-case"),
    ],
)
def test_an_explicitly_marked_veto_needs_no_prohibition_word(marker: dict[str, object]) -> None:
    marked = {"trigger": "any task", "action": "rm -rf /", **marker}

    assert _lines([marked]) == ["[NEVER] rm -rf / (Scope: any task)"]


def test_vetoes_are_ordered_by_priority_then_by_the_order_the_store_handed_them_out() -> None:
    """Stored rules carry no id: an id made from the position would put rule ``10`` before rule ``2``."""
    priority = {3: 1, 11: 1}
    rules = [_stored_rule("any task", f"never touch resource {n}", priority.get(n, 0)) for n in range(12)]

    stored_order = [3, 11, *(n for n in range(12) if n not in priority)]

    assert _lines(rules) == [f"[NEVER] never touch resource {n} (Scope: any task)" for n in stored_order]
