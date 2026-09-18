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
_EVOLUTION_SEED_HISTORY = "09-12 10:00|MERGE|prefers dark mode\n09-13 18:30|REPLACE|moved dark mode preference to global scope"

# SemanticMemory embedding 预填维度（bge-m3 = 1024 维）。
# 预填后 store_semantic 跳过 embedding API 调用（storage.py: if memory.embedding
# is None 才 embed），从而在凭据失效期间仍能走真实持久化链路。
_PRESEEDED_EMBEDDING_DIM = 1024

_E2E_EMBEDDING_CONFIG = {
    "provider": "openai_compatible",
    "model": "BAAI/bge-m3",
    # 该 fixture 只服务于本地 E2E 记忆演化 UI 渲染：两条记忆均以预填向量落库
    # （见 _PRESEEDED_EMBEDDING_DIM），store 路径不会真正调用该远端凭据。
    # 因此这里只提供占位 key，避免把任何真实密钥写进仓库。
    "apiKey": "sk-e2e-fixture-embedding-placeholder",
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
    """Local dev/test only: bootstrap retrieval config, then seed a merge-audit memory.

    The seeded memory carries a pre-filled 1024-dim embedding vector so the store
    path skips the external embedding API call (storage.py only embeds when
    ``memory.embedding is None``). This keeps the E2E writable-pipeline validation
    real (sqlite + qdrant persistence + API projection) while remaining stable
    when the configured embedding credential is not externally reachable.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from myrm_agent_harness.toolkits.memory.types import SemanticMemory

    from app.core.memory.adapters.setup import (
        create_memory_manager,
        resolve_context_binding,
    )
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
        # 先以预填向量落库（embedding 非 None → store_semantic 跳过 embedding API），
        # 再补 merge 审计字段二次落库。该 fixture 只验证持久化 + API 投影 + UI 渲染，
        # 因此不需要可用的远端 embedding 凭据。
        base = SemanticMemory(
            content=_EVOLUTION_SEED_CONTENT,
            importance=0.8,
            tags=["e2e-evolution"],
            embedding=[0.0] * _PRESEEDED_EMBEDDING_DIM,
        )
        persisted = await manager.store(base, _bypass_approval=True)
        if not isinstance(persisted, SemanticMemory):
            raise HTTPException(
                status_code=500, detail="seed store returned non-semantic memory"
            )

        seeded = persisted.model_copy(
            update={
                "merge_count": 2,
                "merge_history": _EVOLUTION_SEED_HISTORY,
            },
        )
        persisted = await manager.store(seeded, _bypass_approval=True)

        # 纠正链 fixture：按 correct_memory 的落库语义构造纠正记忆（correction_of 指向
        # 旧记忆），并预填向量走真实 store 链路。不直接调 correct_memory——其内部
        # _store_semantic 会对新记忆调 embedding API，而该 fixture 不含真实远端凭据。
        correction = SemanticMemory(
            content="user prefers dark mode (corrected v1)",
            importance=1.0,
            confidence=0.95,
            tags=["e2e-evolution"],
            embedding=[0.0] * _PRESEEDED_EMBEDDING_DIM,
            correction_of=str(persisted.id),
        )
        corrected = await manager.store(correction, _bypass_approval=True)
        if getattr(corrected, "correction_of", None) != str(persisted.id):
            raise HTTPException(
                status_code=500, detail="correction chain not persisted"
            )

        return {
            "id": str(persisted.id),
            "correction_id": str(corrected.id),
            "status": "seeded",
        }
    finally:
        close = getattr(manager, "close", None) or getattr(manager, "aclose", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
