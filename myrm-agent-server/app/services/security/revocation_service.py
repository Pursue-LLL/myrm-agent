"""[INPUT]
- myrm_agent_harness.agent.security.lease::TaskLeaseGovernor, RevocationEvent, RevocationSubjectType (POS: 框架层在途长任务微租约与级联熔断中枢)
- app.services.event.app_event_bus::get_event_bus, AppEvent, AppEventType (POS: 业务层 SSE 实时广播总线)

[OUTPUT]
- RevocationService: 业务级在途长任务实时撤权与级联熔断服务

[POS]
连接业务端凭证吊销/智能体停用操作与底层 Harness 运行态微租约总线，
实现 ≤100ms 快速级联强杀（取消异步 Task、强杀沙箱进程、清除上下文残留），并向 SSE 发布广播。
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.agent.security.lease import (
    RevocationEvent,
    RevocationSubjectType,
    TaskLeaseGovernor,
)

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


class RevocationService:
    """Service broadcasting security privilege revocation to in-flight running tasks."""

    _governor: ClassVar[TaskLeaseGovernor | None] = None

    @classmethod
    def get_governor(cls) -> TaskLeaseGovernor:
        """Obtain underlying TaskLeaseGovernor instance."""
        if cls._governor is None:
            cls._governor = TaskLeaseGovernor.get_instance()
        return cls._governor

    @classmethod
    def set_governor(cls, governor: TaskLeaseGovernor | None) -> None:
        """Set or mock underlying governor for testing."""
        cls._governor = governor

    @classmethod
    async def broadcast_revocation(
        cls,
        subject_type: RevocationSubjectType,
        subject_id: str,
        reason: str,
        grace_period_ms: int = 0,
    ) -> int:
        """Broadcast privilege revocation, immediately terminate in-flight tasks, and emit SSE event."""
        event = RevocationEvent(
            subject_type=subject_type,
            subject_id=subject_id,
            reason=reason,
            grace_period_ms=grace_period_ms,
        )

        # 1. Trigger micro-lease invalidation and cascade killing in Harness runtime
        governor = cls.get_governor()
        terminated_count = await governor.revoke_subject(event)

        logger.warning(
            "[REVOCATION_SERVICE] Broadcasted revocation for [%s:%s] (Reason: %s). Terminated %d in-flight tasks.",
            subject_type.value,
            subject_id,
            reason,
            terminated_count,
        )

        # 2. Publish real-time SSE event to web clients
        try:
            bus = get_event_bus()
            bus.publish(
                AppEvent(
                    event_type=AppEventType.REVOCATION_BROADCAST,
                    data={
                        "subject_type": subject_type.value,
                        "subject_id": subject_id,
                        "reason": reason,
                        "revoked_at": event.revoked_at,
                        "terminated_tasks_count": terminated_count,
                    },
                )
            )
        except Exception as exc:
            logger.error("[REVOCATION_SERVICE] Failed to publish SSE revocation broadcast: %s", exc)

        return terminated_count

    @classmethod
    async def revoke_credential(
        cls,
        credential_id: str,
        reason: str = "Credential revoked by user/system",
        grace_period_ms: int = 0,
    ) -> int:
        """Revoke a specific credential and kill any in-flight tasks holding it."""
        return await cls.broadcast_revocation(
            subject_type=RevocationSubjectType.CREDENTIAL,
            subject_id=credential_id,
            reason=reason,
            grace_period_ms=grace_period_ms,
        )

    @classmethod
    async def revoke_agent(
        cls,
        agent_id: str,
        reason: str = "Agent disabled by administrator",
        grace_period_ms: int = 0,
    ) -> int:
        """Disable an agent and forcefully terminate all its active running tasks."""
        return await cls.broadcast_revocation(
            subject_type=RevocationSubjectType.AGENT,
            subject_id=agent_id,
            reason=reason,
            grace_period_ms=grace_period_ms,
        )

    @classmethod
    async def revoke_resource(
        cls,
        resource_id: str,
        reason: str = "Access to resource revoked",
        grace_period_ms: int = 0,
    ) -> int:
        """Revoke access to a specific database, file or API resource."""
        return await cls.broadcast_revocation(
            subject_type=RevocationSubjectType.RESOURCE,
            subject_id=resource_id,
            reason=reason,
            grace_period_ms=grace_period_ms,
        )

    @classmethod
    async def revoke_session(
        cls,
        session_id: str,
        reason: str = "Session aborted by emergency kill switch",
        grace_period_ms: int = 0,
    ) -> int:
        """Forcefully terminate all in-flight tasks within a session."""
        return await cls.broadcast_revocation(
            subject_type=RevocationSubjectType.SESSION,
            subject_id=session_id,
            reason=reason,
            grace_period_ms=grace_period_ms,
        )
