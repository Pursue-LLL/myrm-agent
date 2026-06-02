"""Shared Context memory health operations.

[INPUT]
app.api.memory.shared_context_schemas::SharedContextMemoryHealthResponse (POS: 共享上下文 API Schema 层)
app.services.memory.shared_context_health::check_shared_context_memory_health (POS: 共享上下文记忆健康服务)

[OUTPUT]
router: Shared Context 记忆依赖健康检查端点

[POS]
共享上下文健康检查 API 操作层。提供 embedding 配置和实时探测状态，避免批准写入时才暴露不可用依赖。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.memory.shared_context_schemas import SharedContextMemoryHealthResponse
from app.services.memory.shared_context_health import check_shared_context_memory_health

router = APIRouter(prefix="/shared-contexts/health")


@router.get("/memory", response_model=SharedContextMemoryHealthResponse)
async def get_shared_context_memory_health(
    probe: bool = Query(False, description="Run a live embedding probe instead of configuration-only validation."),
) -> SharedContextMemoryHealthResponse:
    """Return sanitized Shared Context memory dependency health."""
    health = await check_shared_context_memory_health(probe=probe)
    return SharedContextMemoryHealthResponse(
        ready=health.ready,
        status=health.status,
        model=health.model,
        api_base_configured=health.api_base_configured,
        api_key_configured=health.api_key_configured,
        probed=health.probed,
        reason=health.reason,
        retryable=health.retryable,
        checked_at=health.checked_at,
        vector_dimension=health.vector_dimension,
    )
