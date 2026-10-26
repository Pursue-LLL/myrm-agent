"""The MCP endpoint follows the current retrieval settings for every request.

[INPUT]
app.api.mcp.endpoint::_memory_manager_for_agent (POS: per-request MemoryManager for the token's agent)
app.services.agent.platform_config::load_platform_retrieval_configs (POS: WebUI retrieval settings; embedding may be absent)

[OUTPUT]
Each request builds its manager from the embedding setting at that moment.

[POS]
Guards against capturing the embedding config once at import/startup: configuring an embedding model in
Settings must reach the next MCP call without restarting the server, and an unset one must not fail the call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.api.mcp.endpoint import _memory_manager_for_agent


@pytest.mark.asyncio
async def test_each_request_reads_the_current_embedding_setting() -> None:
    configured = EmbeddingConfig(model="BAAI/bge-m3", api_key="sk-unit")
    create = AsyncMock(return_value=MagicMock())

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(side_effect=[(None, None), (configured, None)]),
        ),
        patch("app.services.memory.shared_context.shared_context.resolve_shared_context_ids", new=AsyncMock(return_value=[])),
        patch("app.core.memory.adapters.setup.create_memory_manager", new=create),
    ):
        await _memory_manager_for_agent("agent-1")
        await _memory_manager_for_agent("agent-1")

    assert [call.args[1] for call in create.await_args_list] == [None, configured]
    assert all(call.kwargs == {"approval_required": False} for call in create.await_args_list)
