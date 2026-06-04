"""Memory manager factory for competitor imports (global namespace).

[INPUT]
ResolvedContextBinding with global-only namespaces.

[OUTPUT]
MemoryManager for import confirm/rollback.

[POS]
Ensures migrated facts land in global scope readable by all agents with global read_scopes.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import MemoryManager

from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
from app.services.agent.platform_config import require_platform_embedding_config


async def create_global_import_memory_manager() -> MemoryManager:
    """Create a MemoryManager scoped to global namespace for migration imports."""

    embedding_cfg = await require_platform_embedding_config()
    binding = resolve_context_binding(
        namespaces=["global"],
        agent_id=None,
        channel_id=None,
        conversation_id=None,
        task_id=None,
    )
    return await create_memory_manager(
        binding,
        embedding_cfg,
        approval_required=False,
    )
