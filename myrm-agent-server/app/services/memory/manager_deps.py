"""FastAPI dependencies for MemoryManager injection (api + service handlers).

[INPUT]
app.config.deploy_identity::get_deploy_identity (POS: 部署身份哨兵)
app.core.memory.adapters.setup (POS: MemoryManager 工厂)
app.services.agent.platform_config (POS: 平台 embedding 配置)

[OUTPUT]
get_memory_manager / get_crud_memory_manager / get_optional_memory_manager

[POS]
记忆 HTTP 依赖注入工厂，api.memory.utils 仅 re-export。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine

from fastapi import Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.config.deploy_identity import get_deploy_identity

logger = logging.getLogger(__name__)

_ManagerDep = Callable[..., Coroutine[object, object, MemoryManager]]


def _make_manager_dependency(*, approval_required: bool) -> _ManagerDep:
    """Factory: creates a FastAPI dependency with specific approval setting."""

    async def _dep(
        user_id: str = Depends(get_deploy_identity),
    ) -> MemoryManager:
        try:
            from app.core.memory.adapters.setup import (
                create_memory_manager,
                resolve_context_binding,
            )
            from app.services.agent.platform_config import require_platform_embedding_config

            embedding_cfg = await require_platform_embedding_config()

            return await create_memory_manager(
                resolve_context_binding(
                    namespaces=None,
                    agent_id=None,
                    channel_id=None,
                    conversation_id=None,
                    task_id=None,
                ),
                embedding_cfg,
                approval_required=approval_required,
            )
        except Exception as e:
            logger.warning(f"MemoryManager creation failed: {e}")
            raise HTTPException(
                status_code=503, detail="Memory system unavailable"
            ) from e

    return _dep


get_memory_manager = _make_manager_dependency(approval_required=True)
get_crud_memory_manager = _make_manager_dependency(approval_required=False)


async def get_optional_memory_manager(
    user_id: str = Depends(get_deploy_identity),
) -> MemoryManager | None:
    """Optional dependency that returns None instead of 503 if MemoryManager creation fails."""
    try:
        from app.core.memory.adapters.setup import (
            create_memory_manager,
            resolve_context_binding,
        )
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        return await create_memory_manager(
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
    except Exception as e:
        logger.debug(f"Optional MemoryManager creation failed (graceful): {e}")
        return None
