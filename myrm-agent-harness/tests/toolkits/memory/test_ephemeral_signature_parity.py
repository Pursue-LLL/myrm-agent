"""The subagent memory view accepts every call the real ``MemoryManager`` accepts.

``ReadOnlyMemoryView`` stands in for the global manager inside a subagent, so a caller written against
``MemoryManager`` (``store(..., _force_pending=True)``, ``delete_memory(..., allow_protected=False)``,
``list_memories(..., sort_by=...)``) must reach the denial or the parent read instead of a ``TypeError``.
Each override therefore keeps the base class parameter names, kinds and default presence, and the view
takes its identity fields from the real parent manager.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType

_Shape = list[tuple[str, inspect._ParameterKind, bool]]


def _shape(function: Callable[..., object]) -> _Shape:
    return [
        (parameter.name, parameter.kind, parameter.default is not inspect.Parameter.empty)
        for parameter in inspect.signature(function).parameters.values()
    ]


def _overrides() -> list[str]:
    own_classes = [klass for klass in ReadOnlyMemoryView.__mro__ if klass not in MemoryManager.__mro__]
    return sorted(
        {
            name
            for klass in own_classes
            for name, member in vars(klass).items()
            if inspect.isfunction(member)
            and not name.startswith("__")
            and inspect.isfunction(getattr(MemoryManager, name, None))
        }
    )


@pytest.mark.parametrize("name", _overrides())
def test_override_keeps_the_base_signature(name: str) -> None:
    assert _shape(getattr(ReadOnlyMemoryView, name)) == _shape(getattr(MemoryManager, name))


def _parent() -> MagicMock:
    parent = MagicMock()
    for name in ("search", "get_context", "list_memories", "count_memories"):
        setattr(parent, name, AsyncMock(return_value=[]))
    return parent


@pytest.mark.asyncio
async def test_reads_forward_the_full_signature_to_the_parent() -> None:
    parent = _parent()
    view = ReadOnlyMemoryView(parent)

    await view.search("q", use_rrf=False, include_raw=True, track_access=False, dynamic_signal_weights={"bm25": 0.2})
    await view.get_context(include_profile=False, include_rules=False, include_agent_instructions=False)
    await view.list_memories(MemoryType.SEMANTIC, sort_by="importance", sort_order="asc", tag_filter="t")
    await view.count_memories(MemoryType.SEMANTIC, tag_filter="t")

    assert parent.search.await_args.kwargs["use_rrf"] is False
    assert parent.search.await_args.kwargs["dynamic_signal_weights"] == {"bm25": 0.2}
    assert parent.get_context.await_args.kwargs["include_profile"] is False
    assert parent.list_memories.await_args.kwargs["sort_by"] == "importance"
    assert parent.count_memories.await_args.kwargs["tag_filter"] == "t"


def test_identity_fields_are_copied_from_the_real_parent() -> None:
    parent = MemoryManager(MemoryConfig(embedding_model="test-model"), user_id="u1", auto_warmup=False)

    view = ReadOnlyMemoryView(parent)

    assert view._user_id == "u1"
    assert view._recall_mode == parent.recall_mode
    assert view._memory_policy is parent.memory_policy
    assert view.namespaces == parent.namespaces
