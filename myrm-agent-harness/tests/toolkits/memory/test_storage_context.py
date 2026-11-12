"""Tests for load_context rule assembly.

Every active rule feeds the one ``rules`` list in the order the store hands them out (newest first), locked rules
ahead; each carries its source so the brief can tell the agent's own instructions apart, and tool-bound rules are
additionally exposed as guidance items.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory._internal.storage_context import load_context
from myrm_agent_harness.toolkits.memory.types import (
    ProceduralMemory,
    RuleSource,
)


def _relational(rules: list[ProceduralMemory]) -> AsyncMock:
    relational = AsyncMock()
    relational.list_profiles.return_value = []
    relational.list_rules.return_value = rules
    return relational


@pytest.mark.asyncio
async def test_every_rule_feeds_the_one_list_with_its_source() -> None:
    relational = _relational(
        [
            ProceduralMemory(
                content="self instruction",
                trigger="always",
                action="Always write tests first",
                source=RuleSource.AGENT_SELF,
            ),
            ProceduralMemory(content="a", trigger="when A", action="do A", source=RuleSource.USER_EXTRACTED),
        ]
    )

    ctx = await load_context(relational)

    assert ctx["rules"] == [
        {"trigger": "always", "action": "Always write tests first", "source": "agent_self", "user_endorsed": False},
        {"trigger": "when A", "action": "do A", "source": "user_extracted", "user_endorsed": False},
    ]
    assert "agent_instructions" not in ctx


@pytest.mark.asyncio
async def test_locked_rules_come_first_and_each_group_keeps_the_store_order() -> None:
    def rule(action: str, *, locked: bool) -> ProceduralMemory:
        return ProceduralMemory(
            content=action,
            trigger="any task",
            action=action,
            source=RuleSource.USER_EXPLICIT if locked else RuleSource.USER_EXTRACTED,
            is_user_locked=locked,
        )

    relational = _relational(
        [
            rule("newest", locked=False),
            rule("locked newer", locked=True),
            rule("older", locked=False),
            rule("locked older", locked=True),
        ]
    )

    ctx = await load_context(relational)

    assert [r["action"] for r in ctx["rules"]] == ["locked newer", "locked older", "newest", "older"]
    assert [r["user_endorsed"] for r in ctx["rules"]] == [True, True, False, False]


@pytest.mark.asyncio
async def test_tool_bound_rule_is_also_exposed_as_guidance_item() -> None:
    relational = _relational(
        [
            ProceduralMemory(
                content="fetch retry",
                trigger="web_fetch_tool times out",
                action="Retry once with a longer timeout",
                tool_name="web_fetch_tool",
                source=RuleSource.USER_EXTRACTED,
            ),
            ProceduralMemory(content="plain", trigger="always", action="Be concise", source=RuleSource.USER_EXTRACTED),
        ]
    )

    ctx = await load_context(relational)

    items = ctx["raw_tool_guidance_items"]
    assert [(item.tool_name, item.rule_text) for item in items] == [
        ("web_fetch_tool", "Retry once with a longer timeout")
    ]
    assert len(ctx["rules"]) == 2
