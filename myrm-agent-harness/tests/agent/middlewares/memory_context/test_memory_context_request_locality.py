"""The memory block of one model call depends on that call's tools and on nothing an earlier call left behind.

Every model call of a turn rebuilds the block from the same snapshot (or from the context the manager loaded for the
turn), and tool guidance is picked per call from the tools that call binds. If the pick were written into the shared
context, a call that binds fewer tools would still carry guidance for tools it no longer has.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: builds the block on every model call)
- toolkits.memory.tool_guidance::ToolGuidanceItem (POS: a stored rule that applies to one tool)

[POS]
Request-locality guard: the context the middleware reads is never written to.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.toolkits.memory.config import RecallMode
from myrm_agent_harness.toolkits.memory.tool_guidance import ToolGuidanceItem
from tests.support.memory_context_stubs import bound_manager, make_request

_RULE = "Use absolute paths in every bash command"


def _memory_ctx() -> dict[str, object]:
    return {
        "global_profile": {"name": "Li Ming"},
        "raw_tool_guidance_items": [
            ToolGuidanceItem(id="g1", tool_name="bash_tool", rule_text=_RULE, trigger_pattern="relative path"),
        ],
    }


def _manager(memory_ctx: dict[str, object]) -> MagicMock:
    manager = MagicMock()
    manager.recall_mode = RecallMode.HYBRID
    manager.user_id = "u1"
    # The very same dict on every call, as a manager that caches its context would hand out.
    manager.get_context = AsyncMock(return_value=memory_ctx)
    return manager


async def _block_sent_with(
    tool_names: list[str], run_context: dict[str, object], manager: MagicMock, *, turn_id: str | None = None
) -> str:
    request = make_request(
        messages=[SystemMessage(content="identity"), HumanMessage(content="hi", id=turn_id)],
        tools=[SimpleNamespace(name=name) for name in tool_names],
    )
    request.runtime.context = run_context
    with bound_manager(manager):
        await memory_context_middleware.awrap_model_call(request, AsyncMock())
    sent = request.override.call_args.kwargs["messages"]
    return "\n".join(
        str(m.content) for m in sent if isinstance(m, SystemMessage) and "<user_memory_context" in str(m.content)
    )


@pytest.mark.parametrize(
    ("source", "turn_id", "loads"),
    [
        pytest.param("snapshot", None, 0, id="snapshot"),
        pytest.param("fallback", None, 2, id="fallback-loaded-per-call"),
        pytest.param("fallback", "turn-1", 1, id="fallback-loaded-once-per-turn"),
    ],
)
async def test_guidance_picked_for_one_call_never_reaches_the_next(
    source: str, turn_id: str | None, loads: int
) -> None:
    memory_ctx = _memory_ctx()
    pristine = copy.deepcopy(memory_ctx)
    manager = _manager(memory_ctx)
    run_context: dict[str, object] = (
        {"memory_brief_snapshot": {"snapshot_id": "s1", "memory_ctx": memory_ctx}} if source == "snapshot" else {"k": 1}
    )

    with_bash = await _block_sent_with(["bash_tool", "memory_search_tool"], run_context, manager, turn_id=turn_id)
    without_bash = await _block_sent_with(["memory_search_tool"], run_context, manager, turn_id=turn_id)

    assert manager.get_context.await_count == loads
    assert _RULE in with_bash
    assert _RULE not in without_bash
    assert memory_ctx == pristine
