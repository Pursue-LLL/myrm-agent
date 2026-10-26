"""The subagent isolation managers accept every call the real ``MemoryManager`` accepts.

``EphemeralMemoryManager`` and ``ReadOnlyMemoryView`` stand in for the global manager inside a
subagent, so a caller written against ``MemoryManager`` (``store(..., _force_pending=True)``,
``delete_memory(..., allow_protected=False)``, ``list_memories(..., sort_by=...)``) must not hit a
``TypeError`` there. Each override therefore keeps the base class parameter names, kinds and
default presence.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.ephemeral import EphemeralMemoryManager, ReadOnlyMemoryView
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

_Shape = list[tuple[str, inspect._ParameterKind, bool]]


def _shape(function: Callable[..., object]) -> _Shape:
    return [
        (parameter.name, parameter.kind, parameter.default is not inspect.Parameter.empty)
        for parameter in inspect.signature(function).parameters.values()
    ]


def _overrides(cls: type[MemoryManager]) -> list[str]:
    return sorted(
        name
        for name, member in vars(cls).items()
        if inspect.isfunction(member)
        and not name.startswith("__")
        and inspect.isfunction(getattr(MemoryManager, name, None))
    )


_CASES = [(cls, name) for cls in (EphemeralMemoryManager, ReadOnlyMemoryView) for name in _overrides(cls)]


@pytest.mark.parametrize(("cls", "name"), _CASES, ids=[f"{cls.__name__}.{name}" for cls, name in _CASES])
def test_override_keeps_the_base_signature(cls: type[MemoryManager], name: str) -> None:
    assert _shape(getattr(cls, name)) == _shape(getattr(MemoryManager, name))


def _parent() -> MagicMock:
    parent = MagicMock()
    parent._namespaces = ["ns"]
    parent._scope = MagicMock()
    parent._config = MagicMock()
    for name in ("search", "get_context", "list_memories", "count_memories"):
        setattr(parent, name, AsyncMock(return_value=[]))
    return parent


class TestIsolationManagersAcceptBaseKeywords:
    @pytest.mark.asyncio
    async def test_ephemeral_accepts_write_flags_and_protection(self) -> None:
        manager = EphemeralMemoryManager(_parent())
        memory = SemanticMemory(id="m1", user_id="u", content="note")

        await manager.store(memory, _bypass_approval=True, _force_pending=True, _scope_prevalidated=True)
        await manager.store_batch([memory], _bypass_approval=True, _force_pending=True)
        assert await manager.set_profile_attribute("k", "v", _force_pending=True) is None
        assert await manager.delete_memory("c", ["m1"], allow_protected=False) == 1

    @pytest.mark.asyncio
    async def test_ephemeral_add_event_keeps_failure_details(self) -> None:
        manager = EphemeralMemoryManager(_parent())

        event = await manager.add_event(
            "deploy failed",
            subtask_phase="verify",
            is_failure_attempt=True,
            failure_reason="timeout",
            negative_lesson="raise the deadline",
            confidence_tier="weak",
        )

        assert (event.subtask_phase, event.is_failure_attempt, event.failure_reason) == ("verify", True, "timeout")
        assert (event.negative_lesson, event.confidence_tier) == ("raise the deadline", "weak")
        assert await manager.get_memory(event.id) is event

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cls", [EphemeralMemoryManager, ReadOnlyMemoryView])
    async def test_reads_forward_the_full_signature_to_the_parent(
        self, cls: type[EphemeralMemoryManager | ReadOnlyMemoryView]
    ) -> None:
        parent = _parent()
        manager = cls(parent)

        await manager.search(
            "q", use_rrf=False, include_raw=True, track_access=False, dynamic_signal_weights={"bm25": 0.2}
        )
        await manager.get_context(include_profile=False, include_rules=False, include_agent_instructions=False)
        await manager.list_memories(MemoryType.SEMANTIC, sort_by="importance", sort_order="asc", tag_filter="t")
        await manager.count_memories(MemoryType.SEMANTIC, tag_filter="t")

        assert parent.search.await_args.kwargs["use_rrf"] is False
        assert parent.search.await_args.kwargs["dynamic_signal_weights"] == {"bm25": 0.2}
        assert parent.get_context.await_args.kwargs["include_profile"] is False
        assert parent.list_memories.await_args.kwargs["sort_by"] == "importance"
        assert parent.count_memories.await_args.kwargs["tag_filter"] == "t"
