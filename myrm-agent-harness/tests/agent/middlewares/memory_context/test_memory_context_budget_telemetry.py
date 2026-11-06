"""The budget gauge of a reply reads what the model got: characters of the block's budget used, and rules that made it in.

The server forwards the gauge to the UI, which shows ``used / total`` as a percentage and warns when rules were cut.
The gauge therefore has to be a share of one budget (never above 100%), and every rule rendered into the block, veto
rules included, has to count as injected.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: builds the block and publishes the gauge)
- agent.middlewares.memory_context.memory_context_format::MEMORY_BLOCK_BUDGET_CHARS (POS: the budget the gauge is a share of)
- agent.skill_agent.context::get_memory_runtime_budget (POS: the gauge a call leaves for the server)

[POS]
Telemetry guard for the memory block's budget gauge.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import MEMORY_BLOCK_BUDGET_CHARS
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import (
    MemoryRuntimeBudget,
    get_memory_runtime_budget,
)
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request


def _rule(trigger: str, action: str, priority: int = 0) -> dict[str, object]:
    """A rule as the memory store hands it out: these four keys and no veto marker."""
    return {"trigger": trigger, "action": action, "priority": priority, "user_endorsed": False}


async def _gauge_and_block(
    memory_ctx: dict[str, object], *, max_learned_context_chars: int = 2000, model_context_tokens: int | None = None
) -> tuple[MemoryRuntimeBudget | None, str]:
    manager = MagicMock()
    manager.recall_mode = RecallMode.HYBRID
    manager._config = MagicMock(
        max_learned_context_chars=max_learned_context_chars, model_context_tokens=model_context_tokens
    )
    manager.user_id = "u1"
    manager.get_context = AsyncMock(return_value=memory_ctx)
    request = make_request(messages=[SystemMessage(content="identity"), HumanMessage(content="hi")])
    with bound_manager(manager):
        await memory_context_middleware.awrap_model_call(request, AsyncMock())
    sent = request.override.call_args.kwargs["messages"]
    block = next(
        str(m.content) for m in sent if isinstance(m, SystemMessage) and "<user_memory_context" in str(m.content)
    )
    return get_memory_runtime_budget(), block


def _rule_lines(block: str) -> int:
    return sum(1 for line in block.splitlines() if line.startswith(("- When:", "- [NEVER]")))


async def test_a_user_without_memory_has_used_none_of_the_budget() -> None:
    budget, _ = await _gauge_and_block({})

    assert budget == {
        "used": 0,
        "total": MEMORY_BLOCK_BUDGET_CHARS,
        "rulesConfigured": 0,
        "rulesInjected": 0,
        "rulesTruncated": False,
    }


async def test_typical_memory_is_a_small_share_of_the_budget_and_every_rule_counts() -> None:
    memory_ctx: dict[str, object] = {
        "global_profile": {"name": "Li Ming", "role": "backend engineer"},
        "rules": [_rule("committing", "never use git push --force", 10), _rule("writing code", "add type hints")],
    }

    budget, block = await _gauge_and_block(memory_ctx)

    assert budget is not None
    assert budget["total"] == MEMORY_BLOCK_BUDGET_CHARS
    assert 0 < budget["used"] < MEMORY_BLOCK_BUDGET_CHARS // 10
    assert (budget["rulesConfigured"], budget["rulesInjected"], budget["rulesTruncated"]) == (2, 2, False)
    assert _rule_lines(block) == 2


async def test_rules_that_are_all_vetoes_count_as_injected() -> None:
    memory_ctx: dict[str, object] = {
        "rules": [
            _rule("committing", "never use git push --force", 10),
            _rule("any task", "do not touch the .env file", 5),
            _rule("any task", "禁止提交密钥"),
        ]
    }

    budget, block = await _gauge_and_block(memory_ctx)

    assert budget is not None
    assert (budget["rulesConfigured"], budget["rulesInjected"], budget["rulesTruncated"]) == (3, 3, False)
    assert _rule_lines(block) == 3


async def test_entries_that_are_not_rules_are_not_counted_as_configured() -> None:
    memory_ctx: dict[str, object] = {"rules": ["stray text", None, _rule("writing code", "add type hints")]}

    budget, block = await _gauge_and_block(memory_ctx)

    assert budget is not None
    assert (budget["rulesConfigured"], budget["rulesInjected"], budget["rulesTruncated"]) == (1, 1, False)
    assert _rule_lines(block) == 1


async def test_a_heavy_memory_fills_the_budget_without_overflowing_it() -> None:
    memory_ctx: dict[str, object] = {
        "rules": [_rule(f"trigger {i} " + "t" * 40, f"action {i} " + "a" * 40, i) for i in range(160)]
    }

    budget, block = await _gauge_and_block(memory_ctx)

    assert budget is not None
    assert budget["rulesConfigured"] == 160
    assert 0 < budget["rulesInjected"] < 160
    assert budget["rulesTruncated"] is True
    assert 0.9 * MEMORY_BLOCK_BUDGET_CHARS < budget["used"] <= MEMORY_BLOCK_BUDGET_CHARS
    assert budget["rulesInjected"] == _rule_lines(block)


@pytest.mark.parametrize(("max_learned_context_chars", "model_context_tokens"), [(1200, None), (50000, 8000)])
async def test_the_gauge_does_not_depend_on_the_manager_config(
    max_learned_context_chars: int, model_context_tokens: int | None
) -> None:
    budget, _ = await _gauge_and_block(
        {"global_profile": {"name": "Li Ming"}},
        max_learned_context_chars=max_learned_context_chars,
        model_context_tokens=model_context_tokens,
    )

    assert budget is not None
    assert budget["total"] == MEMORY_BLOCK_BUDGET_CHARS
