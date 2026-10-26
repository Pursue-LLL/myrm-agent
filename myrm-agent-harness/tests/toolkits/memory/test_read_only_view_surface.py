"""``ReadOnlyMemoryView`` classifies every public ``MemoryManager`` member: a delegated read or a denied write.

The view is the only memory isolation a child agent gets. An unclassified public method inherits the base
implementation over the view's missing backends: it fails by accident (``AttributeError``) instead of by
policy, and a method that happens to tolerate empty backends would succeed. A new public ``MemoryManager``
member therefore fails here until it is overridden on the view and listed below.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.ephemeral import ReadOnlyMemoryView
from myrm_agent_harness.toolkits.memory.manager import MemoryManager

# Async reads that must reach the parent manager.
_PARENT_READS = frozenset(
    {
        "check_integrity",
        "compute_health_score",
        "count_by_source_chat_id",
        "count_memories",
        "detect_orphan_collections",
        "estimate_reindex",
        "export_all",
        "export_markdown",
        "export_rules_safe",
        "get_context",
        "get_learned_context",
        "get_memory",
        "get_profile_attribute",
        "get_profile_attribute_snapshot",
        "list_memories",
        "list_memory_ids_by_metadata",
        "list_memory_refs_by_metadata",
        "search",
    }
)
# Async members with no parent state to read: a safe empty answer, or nothing to release.
_EMPTY_ANSWERS = frozenset({"close", "count_pending", "end_session", "get_pending", "list_backups", "list_pending"})
# Sync methods: the first two reach the parent, the third only records which memories were cited.
_SYNC_PARENT_READS = frozenset({"begin_session", "get_enabled_types"})
_SYNC_STATE = frozenset({"set_last_cited_memory_ids"})
# Properties answered by the parent's backends.
_PARENT_PROPERTIES = frozenset(
    {"has_graph", "has_relational", "has_vector", "has_vector_store", "last_retrieval_trace", "vector_is_persistent"}
)
# Properties that read fields the view initialises from the parent's public identity accessors.
_IDENTITY_PROPERTIES = frozenset(
    {
        "active_session",
        "approval_required",
        "config",
        "consolidation_llm",
        "last_cited_memory_ids",
        "memory_policy",
        "namespaces",
        "recall_mode",
        "scope",
        "user_id",
    }
)
_CLASSIFIED = (
    _PARENT_READS | _EMPTY_ANSWERS | _SYNC_PARENT_READS | _SYNC_STATE | _PARENT_PROPERTIES | _IDENTITY_PROPERTIES
)


def _public_members() -> dict[str, object]:
    return {
        name: inspect.getattr_static(MemoryManager, name) for name in dir(MemoryManager) if not name.startswith("_")
    }


def _denied_writes() -> list[str]:
    return sorted(
        name
        for name, member in _public_members().items()
        if name not in _CLASSIFIED and inspect.iscoroutinefunction(member)
    )


def _call_arguments(function: object) -> tuple[list[object], dict[str, object]]:
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for parameter in list(inspect.signature(function).parameters.values())[1:]:
        if parameter.default is not inspect.Parameter.empty:
            continue
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[parameter.name] = MagicMock()
        else:
            args.append(MagicMock())
    return args, kwargs


class _Parent(MemoryManager):
    """A parent class of its own, so a patched property is invisible to a view that inherits it unchanged."""


@pytest.fixture
def parent() -> _Parent:
    return _Parent(MemoryConfig(embedding_model="test-model"), user_id="u1", auto_warmup=False)


@pytest.fixture
def view(parent: MemoryManager) -> ReadOnlyMemoryView:
    return ReadOnlyMemoryView(parent)


def test_every_public_member_is_classified() -> None:
    unclassified = sorted(
        name
        for name, member in _public_members().items()
        if name not in _CLASSIFIED and not inspect.iscoroutinefunction(member)
    )
    assert not unclassified, f"Public MemoryManager members the read-only view does not classify: {unclassified}"


def test_classification_names_only_existing_members() -> None:
    stale = sorted(_CLASSIFIED - set(_public_members()))
    assert not stale, f"Classified names that MemoryManager no longer has: {stale}"


def test_every_member_but_identity_is_overridden_on_the_view() -> None:
    own_classes = [klass for klass in ReadOnlyMemoryView.__mro__ if klass not in MemoryManager.__mro__]
    inherited = sorted(
        name
        for name in _public_members()
        if name not in _IDENTITY_PROPERTIES and not any(name in vars(klass) for klass in own_classes)
    )
    assert not inherited, f"Public members the view inherits from MemoryManager unchanged: {inherited}"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", _denied_writes())
async def test_every_other_async_member_is_denied(view: ReadOnlyMemoryView, name: str) -> None:
    args, kwargs = _call_arguments(getattr(MemoryManager, name))

    with pytest.raises(PermissionError, match="READ_ONLY_GLOBAL"):
        await getattr(view, name)(*args, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(_PARENT_READS))
async def test_async_reads_reach_the_parent(parent: MemoryManager, view: ReadOnlyMemoryView, name: str) -> None:
    args, kwargs = _call_arguments(getattr(MemoryManager, name))
    answer = object()

    with patch.object(parent, name, AsyncMock(return_value=answer)) as read:
        assert await getattr(view, name)(*args, **kwargs) is answer

    read.assert_awaited_once()


@pytest.mark.parametrize("name", sorted(_SYNC_PARENT_READS))
def test_sync_reads_reach_the_parent(parent: MemoryManager, view: ReadOnlyMemoryView, name: str) -> None:
    args, kwargs = _call_arguments(getattr(MemoryManager, name))
    answer = object()

    with patch.object(parent, name, MagicMock(return_value=answer)) as read:
        assert getattr(view, name)(*args, **kwargs) is answer

    read.assert_called_once()


@pytest.mark.parametrize("name", sorted(_PARENT_PROPERTIES))
def test_backend_properties_answer_from_the_parent(parent: _Parent, view: ReadOnlyMemoryView, name: str) -> None:
    answer = object()

    with patch.object(_Parent, name, PropertyMock(return_value=answer)):
        assert getattr(view, name) is answer


def test_identity_comes_from_the_parents_public_accessors(parent: MemoryManager, view: ReadOnlyMemoryView) -> None:
    assert view.user_id == parent.user_id == "u1"
    assert view.namespaces == parent.namespaces
    assert view.scope == parent.scope
    assert view.config is parent.config
    assert view.memory_policy is parent.memory_policy
    assert view.recall_mode == parent.recall_mode
    assert view.active_session is None
    assert view.approval_required is False
    assert view.consolidation_llm is None
    assert view.last_cited_memory_ids == []


@pytest.mark.asyncio
async def test_empty_answers_need_no_parent_state(view: ReadOnlyMemoryView) -> None:
    strategy = MagicMock()
    strategy.list_backups = AsyncMock(return_value=[])

    assert await view.end_session() == []
    assert await view.list_pending() == []
    assert await view.get_pending("p1") is None
    assert await view.count_pending() == 0
    assert await view.list_backups(strategy) == []
    await view.close()


def test_cited_ids_are_view_state_not_a_write(view: ReadOnlyMemoryView) -> None:
    view.set_last_cited_memory_ids(["m1"])

    assert view.last_cited_memory_ids == ["m1"]
