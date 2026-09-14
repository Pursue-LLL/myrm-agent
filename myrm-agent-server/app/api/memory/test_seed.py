"""Local-only memory evolution Chrome E2E seed route.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.config.service::config_service (POS: WebUI retrieval config store)
app.core.memory.adapters.setup::create_memory_manager (POS: real memory pipeline)

[OUTPUT]
seed_memory_evolution_fixture: POST /test/seed-evolution-fixture for Chrome E2E

[POS]
Memory API local test fixture for MemoryDetailSheet evolution history Chrome E2E.
Bootstraps WebUI retrieval embedding config BEFORE creating the memory manager
(dependency-injection would fail fast otherwise), then seeds one semantic memory
carrying merge audit fields through the real memory pipeline.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode

router = APIRouter()

_EVOLUTION_SEED_CONTENT = "E2E evolution seed - user prefers dark mode (v3)"
_EVOLUTION_SEED_HISTORY = (
    "09-12 10:00|MERGE|prefers dark mode\n09-13 18:30|REPLACE|moved dark mode preference to global scope"
)

_E2E_EMBEDDING_CONFIG = {
    "provider": "openai_compatible",
    "model": "BAAI/bge-m3",
    "apiKey": "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz",
    "apiBase": "https://api.siliconflow.cn/v1",
}


async def _ensure_embedding_configured() -> None:
    """Bootstrap WebUI retrieval embedding config when absent (test namespace only)."""
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.services.config.service import config_service

    record = await config_service.get("retrieval")
    value = record.value if record is not None else {}
    if not isinstance(value, dict):
        value = {}
    if isinstance(value.get("embeddingConfig"), dict) and value.get("embeddingConfig"):
        return

    merged = {
        **value,
        "embeddingApplied": True,
        "embeddingAppliedAt": int(time.time() * 1000),
        "embeddingConfig": _E2E_EMBEDDING_CONFIG,
    }
    await config_service.set("retrieval", merged, device_id="e2e-fixture")
    invalidate_user_configs_cache()


@router.post("/test/seed-evolution-fixture", include_in_schema=False)
async def seed_memory_evolution_fixture() -> dict[str, str]:
    """Local dev/test only: bootstrap retrieval config, then seed a merge-audit memory."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from myrm_agent_harness.toolkits.memory.types import SemanticMemory

    from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
    from app.services.agent.platform_config import require_platform_embedding_config

    await _ensure_embedding_configured()

    embedding_cfg = await require_platform_embedding_config()
    manager = await create_memory_manager(
        resolve_context_binding(
            namespaces=None,
            agent_id=None,
            channel_id=None,
            conversation_id=None,
            task_id=None,
        ),
        embedding_cfg,
        approval_required=False,
    )

    try:
        base = await manager.add_knowledge(
            _EVOLUTION_SEED_CONTENT,
            importance=0.8,
            tags=["e2e-evolution"],
        )
        if not isinstance(base, SemanticMemory):
            raise HTTPException(status_code=500, detail="seed add_knowledge returned non-semantic memory")

        seeded = base.model_copy(
            update={
                "merge_count": 2,
                "merge_history": _EVOLUTION_SEED_HISTORY,
            },
        )
        persisted = await manager.store(seeded, _bypass_approval=True)
        return {"id": str(persisted.id), "status": "seeded"}
    finally:
        close = getattr(manager, "close", None) or getattr(manager, "aclose", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result