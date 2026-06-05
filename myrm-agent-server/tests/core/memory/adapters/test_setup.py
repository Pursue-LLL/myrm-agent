from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryScopeLevel, MemoryWritePolicy
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding


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

    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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

    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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
async def test_create_memory_manager_reuses_vector_backend_across_approval_modes(tmp_path: Path):
    custom_base_path = tmp_path / "shared_backend_memory"
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

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
