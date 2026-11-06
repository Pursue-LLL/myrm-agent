"""The block a call injects: its place behind the leading system messages and its content for new and returning users.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: builds the block on every model call)
- agent.skill_agent.context::set_memory_runtime_budget (POS: the channel through which the server reads the budget gauge)

[POS]
Injection guard for the memory-context middleware, and the round trip of the run-context channels it publishes through.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
    MEMORY_BLOCK_BUDGET_CHARS,
    MEMORY_CONTEXT_MARKER,
)
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import (
    get_memory_runtime_budget,
    get_memory_runtime_injection,
    set_memory_runtime_budget,
)
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request


class TestMemoryRuntimeBudgetRoundTrip:
    """The server reads rule fidelity straight off this channel, so the set→get
    round trip must preserve every rule key the middleware publishes."""

    def test_preserves_rule_fidelity_keys(self) -> None:
        set_memory_runtime_budget(
            {
                "used": 512,
                "total": 4096,
                "rulesConfigured": 12,
                "rulesInjected": 7,
                "rulesTruncated": True,
            }
        )
        assert get_memory_runtime_budget() == {
            "used": 512,
            "total": 4096,
            "rulesConfigured": 12,
            "rulesInjected": 7,
            "rulesTruncated": True,
        }

    def test_get_hands_out_a_copy(self) -> None:
        """A caller that edits what it read must not change the stored gauge."""
        set_memory_runtime_budget(
            {"used": 512, "total": 4096, "rulesConfigured": 12, "rulesInjected": 7, "rulesTruncated": True}
        )
        first = get_memory_runtime_budget()
        assert first is not None
        first["used"] = 0
        second = get_memory_runtime_budget()
        assert second is not None
        assert second["used"] == 512

    def test_clamps_injected_to_configured(self) -> None:
        """A truncated section can hold no more items than were configured."""
        set_memory_runtime_budget(
            {
                "used": 10,
                "total": 100,
                "rulesConfigured": 3,
                "rulesInjected": 9,
                "rulesTruncated": False,
            }
        )
        budget = get_memory_runtime_budget()
        assert budget is not None
        assert budget["rulesInjected"] == 3


# ---------------------------------------------------------------------------
# ContextVar integration
# ---------------------------------------------------------------------------


async def test_contextvar_integration():
    from myrm_agent_harness.agent.skill_agent.context import (
        get_memory_manager,
        set_memory_manager,
    )

    assert get_memory_manager() is None

    mock_manager = MagicMock()
    mock_manager.user_id = "test_user"

    set_memory_manager(mock_manager)
    assert get_memory_manager() is mock_manager

    set_memory_manager(None)
    assert get_memory_manager() is None


async def test_context_mode_no_guidance_injection():
    """CONTEXT mode (memory_search_tool not bound) injects context but never tool guidance."""
    handler = AsyncMock()
    req = make_request(tools=[])  # CONTEXT: no memory_search_tool bound

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.CONTEXT
    mock_manager.get_context = AsyncMock(return_value={"global_profile": {"name": "Test"}})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    call_kwargs = req.override.call_args[1]
    injected_messages = call_kwargs["messages"]

    stable_msgs = [
        m for m in injected_messages if isinstance(m, SystemMessage) and MEMORY_CONTEXT_MARKER in str(m.content)
    ]
    assert len(stable_msgs) == 1
    assert "memory_search_tool" not in str(stable_msgs[0].content)
    assert "## Memory Search" not in str(stable_msgs[0].content)
    assert "Citation Requirements" not in str(stable_msgs[0].content)


async def test_injects_context_on_success():
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={"global_profile": {"name": "Test"}})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    call_kwargs = req.override.call_args[1]
    injected_messages = call_kwargs["messages"]

    stable_msgs = [
        m for m in injected_messages if isinstance(m, SystemMessage) and MEMORY_CONTEXT_MARKER in str(m.content)
    ]
    assert len(stable_msgs) == 1
    assert get_memory_runtime_injection() == {
        "state": "applied",
        "source": "fallback",
    }
    budget = get_memory_runtime_budget()
    assert isinstance(budget, dict)
    assert budget["total"] == MEMORY_BLOCK_BUDGET_CHARS
    assert 0 < budget["used"] <= budget["total"]


async def test_reuses_prefetched_snapshot_without_refetch():
    """When stream preflight already produced a snapshot, middleware reuses it."""
    handler = AsyncMock()
    req = make_request(messages=[SystemMessage(content="sys"), HumanMessage(content="hello")])
    req.runtime.context = {
        "memory_brief_snapshot": {
            "snapshot_id": "snap-prefetched",
            "memory_ctx": {"global_profile": {"name": "Snapshot User"}},
        }
    }

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={"global_profile": {"name": "Should not be used"}})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    mock_manager.get_context.assert_not_called()
    mock_manager.get_learned_context.assert_not_called()
    req.override.assert_called_once()
    injected_messages = req.override.call_args[1]["messages"]
    stable_payload = "\n".join(str(m.content) for m in injected_messages if isinstance(m, SystemMessage))
    assert "Snapshot User" in stable_payload
    assert get_memory_runtime_injection() == {
        "state": "applied",
        "source": "snapshot",
    }


async def test_cold_start_injects_discovery_prompt():
    """New users (empty context) get cold start discovery guidance as SystemMessage."""
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    call_kwargs = req.override.call_args[1]
    injected_messages = call_kwargs["messages"]
    cold_msgs = [
        m
        for m in injected_messages
        if isinstance(m, SystemMessage)
        and "Discovery Mode" in str(m.content)
        and MEMORY_CONTEXT_MARKER in str(m.content)
    ]
    assert len(cold_msgs) == 1


async def test_inserts_after_multiple_system_messages():
    """Memory stable block is inserted after contiguous leading SystemMessages."""
    handler = AsyncMock()
    req = make_request(
        messages=[
            SystemMessage(content="System prompt 1"),
            SystemMessage(content="System prompt 2"),
            HumanMessage(content="Hello"),
        ]
    )

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={"global_profile": {"name": "Test"}})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    req.override.assert_called_once()
    call_kwargs = req.override.call_args[1]
    injected = call_kwargs["messages"]
    assert [type(m) for m in injected] == [SystemMessage, SystemMessage, SystemMessage, HumanMessage]
    assert [m.content for m in injected[:2]] == ["System prompt 1", "System prompt 2"]
    assert MEMORY_CONTEXT_MARKER in str(injected[2].content)


async def test_learned_facts_are_never_fetched_or_injected():
    """Learned facts stay out of the prompt prefix: an empty profile gets the cold-start block only."""
    handler = AsyncMock()
    req = make_request(
        messages=[
            SystemMessage(content="sys"),
            HumanMessage(content="Real user"),
        ]
    )

    mock_manager = MagicMock()
    mock_manager.user_id = "u-learned-only"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={})
    mock_manager.get_learned_context = AsyncMock(
        return_value={
            "learned_rules": [{"trigger": "learned-trigger", "action": "learned-action", "content": "x"}],
            "learned_preferences": [],
        }
    )

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    mock_manager.get_learned_context.assert_not_called()
    req.override.assert_called_once()
    injected = req.override.call_args[1]["messages"]
    assert [type(m) for m in injected] == [SystemMessage, SystemMessage, HumanMessage]
    assert "learned-action" not in "\n".join(str(m.content) for m in injected)
    cold_msgs = [
        m
        for m in injected
        if isinstance(m, SystemMessage)
        and "Discovery Mode" in str(m.content)
        and MEMORY_CONTEXT_MARKER in str(m.content)
    ]
    assert len(cold_msgs) == 1
