"""The guardian's background MemoryManager does not require an embedding model.

[INPUT]
app.lifecycle.memory_guardian_ops::create_guardian_memory_manager (POS: manager factory for background maintenance)

[OUTPUT]
The manager is built from the stored retrieval settings; without an embedding it is a
keyword-mode manager and the evolution LLM still reaches it as the consolidation model.

[POS]
Contract of the guardian factory: embedding is optional, a missing evolution LLM only drops
consolidation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager


@pytest.mark.asyncio
async def test_guardian_manager_is_built_without_an_embedding() -> None:
    manager = SimpleNamespace()
    create = AsyncMock(return_value=manager)
    evolution_llm = SimpleNamespace()

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch("app.services.agent.platform_config.load_platform_evolution_llm", new=AsyncMock(return_value=evolution_llm)),
        patch("app.core.memory.adapters.setup.create_memory_manager", new=create),
    ):
        built = await create_guardian_memory_manager()

    assert built is manager
    assert create.await_args.args[1] is None
    assert create.await_args.kwargs["consolidation_llm"] is evolution_llm
    assert create.await_args.kwargs["approval_required"] is False


@pytest.mark.asyncio
async def test_guardian_manager_drops_consolidation_when_the_evolution_llm_is_unavailable() -> None:
    create = AsyncMock(return_value=SimpleNamespace())

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch(
            "app.services.agent.platform_config.load_platform_evolution_llm",
            new=AsyncMock(side_effect=RuntimeError("no evolution model")),
        ),
        patch("app.core.memory.adapters.setup.create_memory_manager", new=create),
    ):
        await create_guardian_memory_manager()

    assert create.await_args.kwargs["consolidation_llm"] is None
