"""Integration test: memory path uses ContextBundle volume."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.context import ContextBundleFacade
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding


@pytest.mark.asyncio
async def test_create_memory_manager_uses_volume_layout_path(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    custom_memory = state_dir / "memory"
    embedding_config = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")

    with patch.multiple(
        "app.config.settings.settings.database",
        state_dir=str(state_dir),
        memory_base_path=str(custom_memory),
        qdrant_path=str(state_dir / "qdrant"),
    ):
        facade = ContextBundleFacade.from_state_dir(state_dir, ensure_layout=True)
        assert facade.memory_path() == custom_memory

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
        assert manager is not None
        assert custom_memory.exists()
