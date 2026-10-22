"""Service mediating Mixed Fleet Local Brain and Remote Executor orchestration (Item 47).

[INPUT]
- DispatchHandoffRequestSchema, UpdateFleetHeartbeatRequestSchema,
  CompleteRemoteExecutionRequestSchema, FailRemoteExecutionRequestSchema.

[OUTPUT]
- MixedFleetService managing node states, task handoffs, and status synchronization.

[POS]
- Service layer for Mixed Fleet Profile presets.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.mixed_fleet import (
    DispatchHandoffRequest as HarnessDispatchRequest,
)
from myrm_agent_harness.agent.sub_agents.mixed_fleet import (
    FleetNodeSpec,
    FleetStatusSnapshot,
    MixedFleetCoordinator,
    MixedFleetHandoffManifest,
)
from myrm_agent_harness.agent.sub_agents.mixed_fleet import (
    FleetRoleEnum as HarnessRoleEnum,
)

from app.schemas.mixed_fleet import (
    DispatchHandoffRequestSchema,
    FleetExecutionStatusEnum,
    FleetNodeSpecDTO,
    FleetRoleEnum,
    FleetStatusSnapshotResponseDTO,
    MixedFleetHandoffManifestDTO,
    MixedFleetPresetSpecDTO,
)

logger = logging.getLogger(__name__)


def _node_to_dto(node: FleetNodeSpec) -> FleetNodeSpecDTO:
    return FleetNodeSpecDTO(
        node_id=node.node_id,
        role=FleetRoleEnum(node.role.value),
        display_name=node.display_name,
        is_online=node.is_online,
        endpoint_url=node.endpoint_url,
        last_heartbeat=node.last_heartbeat,
        supported_capabilities=list(node.supported_capabilities),
    )


def _manifest_to_dto(manifest: MixedFleetHandoffManifest) -> MixedFleetHandoffManifestDTO:
    return MixedFleetHandoffManifestDTO(
        manifest_id=manifest.manifest_id,
        chat_id=manifest.chat_id,
        source_role=FleetRoleEnum(manifest.source_role.value),
        target_role=FleetRoleEnum(manifest.target_role.value),
        task_instruction=manifest.task_instruction,
        handoff_markdown=manifest.handoff_markdown,
        context_files=list(manifest.context_files),
        execution_status=FleetExecutionStatusEnum(manifest.execution_status.value),
        created_at=manifest.created_at,
        synced_at=manifest.synced_at,
        output_summary=manifest.output_summary,
        error_detail=manifest.error_detail,
    )


def _snapshot_to_dto(snapshot: FleetStatusSnapshot) -> FleetStatusSnapshotResponseDTO:
    active_dto = _manifest_to_dto(snapshot.active_manifest) if snapshot.active_manifest else None
    return FleetStatusSnapshotResponseDTO(
        chat_id=snapshot.chat_id,
        local_brain=_node_to_dto(snapshot.local_brain),
        remote_executor=_node_to_dto(snapshot.remote_executor),
        active_manifest=active_dto,
        total_handoffs=snapshot.total_handoffs,
    )


class MixedFleetService:
    """Service orchestrating Mixed Fleet Local Brain and Remote Executor nodes."""

    def __init__(self) -> None:
        self._coordinator = MixedFleetCoordinator()
        self._lock = threading.RLock()

    def get_fleet_snapshot(self, chat_id: str) -> FleetStatusSnapshotResponseDTO:
        """Retrieve current snapshot of Local Brain and Remote Executor."""
        snapshot = self._coordinator.get_fleet_snapshot(chat_id)
        return _snapshot_to_dto(snapshot)

    def dispatch_to_remote(
        self,
        chat_id: str,
        request: DispatchHandoffRequestSchema,
    ) -> MixedFleetHandoffManifestDTO:
        """Local Brain packages and dispatches task to Remote Executor."""
        harness_req = HarnessDispatchRequest(
            chat_id=chat_id,
            task_instruction=request.task_instruction,
            context_files=request.context_files,
        )
        manifest = self._coordinator.dispatch_to_remote(harness_req)
        logger.info(
            "Dispatched mixed fleet handoff %s from Local Brain to Remote Executor for chat %s",
            manifest.manifest_id,
            chat_id,
        )
        return _manifest_to_dto(manifest)

    def sync_from_remote(
        self,
        chat_id: str,
        manifest_id: str,
    ) -> MixedFleetHandoffManifestDTO:
        """Local Brain pulls the latest status or artifacts from Remote Executor."""
        manifest = self._coordinator.sync_from_remote(
            chat_id=chat_id, manifest_id=manifest_id
        )
        return _manifest_to_dto(manifest)

    def complete_remote_execution(
        self,
        chat_id: str,
        manifest_id: str,
        output_summary: str,
    ) -> MixedFleetHandoffManifestDTO:
        """Mark remote execution as completed."""
        manifest = self._coordinator.get_manifest(manifest_id)
        if manifest.chat_id != chat_id:
            raise KeyError(f"Manifest {manifest_id} does not belong to chat {chat_id}")

        completed = self._coordinator.complete_remote_execution(
            manifest_id=manifest_id, output_summary=output_summary
        )
        return _manifest_to_dto(completed)

    def fail_remote_execution(
        self,
        chat_id: str,
        manifest_id: str,
        error_detail: str,
    ) -> MixedFleetHandoffManifestDTO:
        """Mark remote execution as failed."""
        manifest = self._coordinator.get_manifest(manifest_id)
        if manifest.chat_id != chat_id:
            raise KeyError(f"Manifest {manifest_id} does not belong to chat {chat_id}")

        failed = self._coordinator.fail_remote_execution(
            manifest_id=manifest_id, error_detail=error_detail
        )
        return _manifest_to_dto(failed)

    def update_heartbeat(
        self,
        chat_id: str,
        role: FleetRoleEnum,
        is_online: bool = True,
    ) -> FleetNodeSpecDTO:
        """Update node heartbeat and availability."""
        node = self._coordinator.update_heartbeat(
            chat_id=chat_id,
            role=HarnessRoleEnum(role.value),
            is_online=is_online,
        )
        return _node_to_dto(node)

    def get_preset_spec(self) -> MixedFleetPresetSpecDTO:
        """Return official specification for Mixed Fleet Agent Profile template."""
        return MixedFleetPresetSpecDTO(
            preset_id="preset-mixed-fleet-v1",
            name="混合舰队（Local Brain + Remote Executor）预置模板",
            description="本地知识库/记忆管家与远端 24/7 常驻沙箱执行器协同拓扑",
            local_capabilities=[
                "本地隐私文档检索与向量索引",
                "跨会话长期记忆与偏好管理",
                "任务意图解析与结构化交接 Markdown 编译",
                "本地模型低功耗常驻与交互审查",
            ],
            remote_capabilities=[
                "远端 Gateway/Cloud Sandbox 24/7 不间断运行",
                "高算力长耗时数据抓取、分析与测试编译",
                "无人值守看门狗监控与异常自动捕获",
                "产出结构化工件并回传至 Local Brain",
            ],
            handoff_protocol="基于不可篡改的 MixedFleetHandoffManifest 进行任务交接与结果拉取",
        )


_SERVICE_INSTANCE: MixedFleetService | None = None
_INSTANCE_LOCK = threading.Lock()


def get_mixed_fleet_service() -> MixedFleetService:
    """Get the singleton instance of MixedFleetService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        with _INSTANCE_LOCK:
            if _SERVICE_INSTANCE is None:
                _SERVICE_INSTANCE = MixedFleetService()
    return _SERVICE_INSTANCE
