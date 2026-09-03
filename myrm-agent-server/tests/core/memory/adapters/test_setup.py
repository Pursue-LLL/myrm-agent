from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory.config import (
    AgentMemoryPolicy,
    MemoryScopeLevel,
    MemoryWritePolicy,
)
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import ConflictResolution
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters.setup import (
    _memory_manager_cache,
    create_memory_manager,
    resolve_context_binding,
)


@pytest.fixture(autouse=True)
def _clear_manager_cache():
    _memory_manager_cache.clear()
    yield
    _memory_manager_cache.clear()
    _run_async_teardown(_clear_harness_embedded_stores())


def _run_async_teardown(coro) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


async def _clear_harness_embedded_stores() -> None:
    from myrm_agent_harness.toolkits.vector.qdrant.factory import (
        _embedded_clients,
        clear_embedded_stores,
    )

    await clear_embedded_stores()
    assert _embedded_clients == {}


def _patch_memory_path(path: str):
    """Patch settings.database.memory_base_path and qdrant_path for testing."""
    from unittest.mock import patch as mock_patch

    qdrant_path = str(Path(path) / "vector_store")
    return mock_patch.multiple(
        "app.config.settings.settings.database",
        memory_base_path=path,
        qdrant_path=qdrant_path,
    )


@pytest.mark.asyncio
async def test_create_memory_manager_with_custom_path(tmp_path: Path):
    custom_base_path = tmp_path / "custom_memory_path"

    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(custom_base_path)):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
        )

        assert isinstance(manager, MemoryManager)
        assert custom_base_path.exists()
        assert (custom_base_path / "vector_store").exists()


@pytest.mark.asyncio
async def test_create_memory_manager_default_path(tmp_path: Path):
    default_path = tmp_path / "default_memory"

    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(default_path)):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
        )

        assert isinstance(manager, MemoryManager)
        assert default_path.exists()
        assert (default_path / "vector_store").exists()


@pytest.mark.asyncio
async def test_create_memory_manager_merges_scope_namespaces(tmp_path: Path):
    custom_base_path = tmp_path / "scoped_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(custom_base_path)):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=["global", "agent:builder"],
                agent_id="builder",
                channel_id="telegram",
                conversation_id="chat-123",
                task_id=None,
            ),
            embedding_config=embedding_config,
        )

    assert manager.namespaces == [
        "global",
        "agent:builder",
        "channel:telegram",
        "conversation:chat-123",
    ]
    assert manager.scope.channel_id == "telegram"
    assert manager.scope.conversation_id == "chat-123"


@pytest.mark.asyncio
async def test_create_memory_manager_appends_shared_context_namespaces(tmp_path: Path):
    custom_base_path = tmp_path / "shared_context_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(custom_base_path)):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id="builder",
                channel_id="telegram",
                conversation_id="chat-123",
                task_id=None,
                shared_context_ids=["customer-a", "customer-a", "launch-plan"],
            ),
            embedding_config=embedding_config,
        )

    assert manager.namespaces == [
        "global",
        "agent:builder",
        "channel:telegram",
        "conversation:chat-123",
        "shared:customer-a",
        "shared:launch-plan",
    ]
    assert manager.scope.primary_namespace == "conversation:chat-123"


@pytest.mark.asyncio
async def test_create_memory_manager_applies_binding_memory_policy(tmp_path: Path):
    custom_base_path = tmp_path / "policy_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(custom_base_path)):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id="planner",
                channel_id="telegram",
                conversation_id="chat-123",
                task_id="task-999",
                shared_context_ids=["customer-a"],
                memory_policy=AgentMemoryPolicy(
                    read_scopes=(MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT),
                    write_policy=MemoryWritePolicy.TASK,
                ),
            ),
            embedding_config=embedding_config,
        )

    assert manager.namespaces == [
        "global",
        "agent:planner",
        "shared:customer-a",
    ]
    assert manager.memory_policy is not None
    assert manager.memory_policy.write_policy == MemoryWritePolicy.TASK
    assert manager.scope.primary_namespace == "task:task-999"


@pytest.mark.asyncio
async def test_create_memory_manager_reuses_vector_backend_across_approval_modes(
    tmp_path: Path,
):
    custom_base_path = tmp_path / "shared_backend_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with _patch_memory_path(str(custom_base_path)):
        binding = resolve_context_binding(
            namespaces=None,
            agent_id="builder",
            channel_id="telegram",
            conversation_id="chat-123",
            task_id=None,
        )
        approved_manager = await create_memory_manager(
            binding,
            embedding_config=embedding_config,
            approval_required=True,
        )
        direct_manager = await create_memory_manager(
            binding,
            embedding_config=embedding_config,
            approval_required=False,
        )

    assert approved_manager is not direct_manager
    assert approved_manager._vector is direct_manager._vector
    assert approved_manager.approval_required is True
    assert direct_manager.approval_required is False


@pytest.mark.asyncio
async def test_create_memory_manager_isolated_base_path_skips_global_vector_store(
    tmp_path: Path,
):
    """Explicit base_path (eval isolation) must NOT reuse the global Qdrant volume."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as mock_patch

    custom_base_path = tmp_path / "isolated_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with mock_patch(
        "app.core.retriever.vector.defaults.create_default_vector_store",
        new=AsyncMock(),
    ) as mock_store:
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            base_path=custom_base_path,
        )

    mock_store.assert_not_awaited()
    assert isinstance(manager, MemoryManager)
    assert custom_base_path.exists()
    assert (custom_base_path / "vector_store").exists()


@pytest.mark.asyncio
async def test_create_memory_manager_isolated_base_path_evicts_only_that_volume(
    tmp_path: Path,
):
    """evict_cached_memory_manager removes only the matching base_path manager."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import evict_cached_memory_manager

    iso_a = tmp_path / "iso_a"
    iso_b = tmp_path / "iso_b"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with mock_patch(
        "app.core.retriever.vector.defaults.create_default_vector_store",
        new=AsyncMock(),
    ):
        manager_a = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            base_path=iso_a,
        )
        manager_b = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            base_path=iso_b,
        )

    assert manager_a is not manager_b
    assert len(_memory_manager_cache) == 2

    manager_a.close = AsyncMock()
    await evict_cached_memory_manager(iso_a)

    assert len(_memory_manager_cache) == 1
    manager_a.close.assert_awaited_once()
    assert manager_b in _memory_manager_cache.values()


def test_resolve_context_binding_carries_task_workspace_overlay() -> None:
    binding = resolve_context_binding(
        namespaces=None,
        agent_id="builder",
        channel_id=None,
        conversation_id="chat-1",
        task_id=None,
        task_workspace_root="/tmp/project-a",
    )
    assert binding.agent_overlay is not None
    assert binding.agent_overlay.task_workspace_root == "/tmp/project-a"
    assert binding.agent_overlay.memory_scenes_pinned is True
    assert binding.bundle_id == "default"
    assert binding.schema_version == 1


@pytest.mark.asyncio
async def test_evict_cached_memory_manager_unknown_base_path_noop(
    tmp_path: Path,
) -> None:
    """Evicting a base_path with no cached manager is a quiet no-op."""
    from app.core.memory.adapters.setup import evict_cached_memory_manager

    assert len(_memory_manager_cache) == 0
    await evict_cached_memory_manager(tmp_path / "never_cached")
    assert len(_memory_manager_cache) == 0


@pytest.mark.asyncio
async def test_evict_cached_memory_manager_logs_close_failure(tmp_path: Path) -> None:
    """A manager whose close() raises is logged and still evicted from cache."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import evict_cached_memory_manager

    custom_base_path = tmp_path / "close_failure_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with mock_patch(
        "app.core.retriever.vector.defaults.create_default_vector_store",
        new=AsyncMock(),
    ):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            base_path=custom_base_path,
        )

    manager.close = AsyncMock(side_effect=RuntimeError("close exploded"))
    with mock_patch("app.core.memory.adapters.setup.logger.warning") as mock_warning:
        await evict_cached_memory_manager(custom_base_path)

    mock_warning.assert_called_once()
    assert len(_memory_manager_cache) == 0


@pytest.mark.asyncio
async def test_shutdown_cached_memory_managers_logs_close_failure(
    tmp_path: Path,
) -> None:
    """shutdown gathers close failures without propagating them."""
    from unittest.mock import AsyncMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import shutdown_cached_memory_managers

    custom_base_path = tmp_path / "shutdown_failure_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    with mock_patch(
        "app.core.retriever.vector.defaults.create_default_vector_store",
        new=AsyncMock(),
    ):
        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            base_path=custom_base_path,
        )

    manager.close = AsyncMock(side_effect=RuntimeError("close exploded"))
    with mock_patch("app.core.memory.adapters.setup.logger.warning") as mock_warning:
        await shutdown_cached_memory_managers()

    mock_warning.assert_called_once()
    assert len(_memory_manager_cache) == 0


@pytest.mark.asyncio
async def test_create_memory_tools_for_user_propagates_optional_kwargs(
    tmp_path: Path,
) -> None:
    """Optional tool kwargs are forwarded only when provided."""
    from unittest.mock import AsyncMock, MagicMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import create_memory_tools_for_user

    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )
    fake_manager = MagicMock()
    fake_tools = [MagicMock(), MagicMock()]

    async def _fake_create_manager(*_args: object, **_kwargs: object):
        return fake_manager

    with (
        mock_patch(
            "app.core.memory.adapters.setup.create_memory_manager",
            new=AsyncMock(side_effect=_fake_create_manager),
        ),
        mock_patch(
            "myrm_agent_harness.toolkits.create_memory_tools",
            return_value=fake_tools,
        ) as mock_tools,
    ):
        manager, tools = await create_memory_tools_for_user(
            resolve_context_binding(
                namespaces=None,
                agent_id="builder",
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_config,
            search_policy={"k": "v"},
            search_backends=["qdrant"],
            description_locale="zh",
        )

    assert manager is fake_manager
    assert tools is fake_tools
    call_kwargs = mock_tools.call_args.kwargs
    assert call_kwargs["search_policy"] == {"k": "v"}
    assert call_kwargs["search_backends"] == ["qdrant"]
    assert call_kwargs["description_locale"] == "zh"


@pytest.mark.asyncio
async def test_create_conflict_callback_persists_pending_memory(tmp_path: Path) -> None:
    """The conflict callback writes a PendingMemory row and returns PENDING."""
    from unittest.mock import AsyncMock, MagicMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import create_conflict_callback

    fake_db = MagicMock()
    fake_db.__aenter__ = AsyncMock(return_value=fake_db)
    fake_db.__aexit__ = AsyncMock(return_value=False)
    fake_db.add = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.scalar = AsyncMock(return_value=None)

    ctx = MagicMock(
        new_content="conflicting fact",
        merge_suggestion="merge note",
        accuracy_score=0.8,
        old_memory_id="mem-old-1",
        old_content="old fact",
        importance=0.9,
    )

    with (
        mock_patch(
            "app.database.connection.get_session",
            return_value=fake_db,
        ),
        mock_patch(
            "app.services.memory.ledger.operation_ledger.MemoryOperationLedgerService",
            return_value=AsyncMock(),
        ),
    ):
        callback = create_conflict_callback(agent_id="agent-x")
        result = await callback(ctx)

    assert result == ConflictResolution.PENDING
    fake_db.add.assert_called_once()
    record = fake_db.add.call_args.args[0]
    assert record.agent_id == "agent-x"
    assert record.is_conflict is True
    assert record.status == "pending"
    fake_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_conflict_callback_falls_back_on_db_error(tmp_path: Path) -> None:
    """A DB failure inside the callback falls back to KEEP_OLD."""
    from unittest.mock import AsyncMock, MagicMock
    from unittest.mock import patch as mock_patch

    from app.core.memory.adapters.setup import create_conflict_callback

    fake_db = MagicMock()
    fake_db.__aenter__ = AsyncMock(
        side_effect=RuntimeError("db unavailable"),
    )
    fake_db.__aexit__ = AsyncMock(return_value=False)

    ctx = MagicMock(
        new_content="conflicting fact",
        merge_suggestion="merge note",
        accuracy_score=0.8,
        old_memory_id="mem-old-1",
        old_content="old fact",
        importance=0.9,
    )

    with (
        mock_patch(
            "app.database.connection.get_session",
            return_value=fake_db,
        ),
        mock_patch("app.core.memory.adapters.setup.logger.warning") as mock_warning,
    ):
        callback = create_conflict_callback(agent_id="agent-x")
        result = await callback(ctx)

    assert result == ConflictResolution.KEEP_OLD
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_create_memory_manager_cache_hit_refreshes_consolidation_callback(
    tmp_path: Path,
) -> None:
    custom_base_path = tmp_path / "callback_refresh_memory"
    embedding_config = EmbeddingConfig(
        model="openai/text-embedding-3-small", api_key="sk-test"
    )

    async def _wiki_hook(_stats: object) -> None:
        return None

    binding = resolve_context_binding(
        namespaces=None,
        agent_id="builder",
        channel_id=None,
        conversation_id="chat-callback",
        task_id=None,
    )

    with _patch_memory_path(str(custom_base_path)):
        first = await create_memory_manager(
            binding,
            embedding_config=embedding_config,
            on_consolidation_complete=_wiki_hook,
        )
        second = await create_memory_manager(
            binding,
            embedding_config=embedding_config,
            on_consolidation_complete=None,
        )

    assert first._on_consolidation_complete is None
    assert second._on_consolidation_complete is None


def test_memory_policy_adapter_and_dto_serialization_roundtrip():
    """验证 AgentMemoryPolicyConfig DTO 与 memory_policy 适配器的无损序列化/反序列化。"""
    from app.core.memory.adapters.policy import (
        memory_policy_from_dict,
        memory_policy_to_dict,
    )
    from app.database.dto import AgentMemoryPolicyConfig

    dto = AgentMemoryPolicyConfig(
        agent_id="agent-1",
        read_scopes=[MemoryScopeLevel.GLOBAL, MemoryScopeLevel.TASK],
        write_policy=MemoryWritePolicy.TASK,
        allow_l3_extraction=False,
        auto_cleanup=True,
    )
    payload = dto.model_dump()
    assert payload["allow_l3_extraction"] is False
    assert payload["auto_cleanup"] is True

    policy = memory_policy_from_dict(payload)
    assert policy is not None
    assert policy.agent_id == "agent-1"
    assert policy.read_scopes == (MemoryScopeLevel.GLOBAL, MemoryScopeLevel.TASK)
    assert policy.write_policy == MemoryWritePolicy.TASK
    assert policy.allow_l3_extraction is False
    assert policy.auto_cleanup is True

    serialized = memory_policy_to_dict(policy)
    assert serialized is not None
    assert serialized["allow_l3_extraction"] is False
    assert serialized["auto_cleanup"] is True
    assert serialized["read_scopes"] == ["global", "task"]
    assert serialized["write_policy"] == "task"
