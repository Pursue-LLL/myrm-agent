"""[INPUT] NamedSubagentInstanceConfigDTO, SubmitReportRequest, SubmitSettlementRequest, and DrainQueueRequest.
[OUTPUT] FifoQueueEnvelopeDTO, QueueDrainResponse, and QueueStatusResponse.
[POS] Service layer managing Subagent report delivery wakeup and ordered settlement FIFO queues per chat session.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.report_fifo import (
    NamedSubagentInstanceConfig,
    OrderedFifoQueueEnvelope,
    PermissionMode,
    ReportDeliveryMode,
    SubagentReportWakeupCoordinator,
)

from app.schemas.report_fifo import (
    FifoQueueEnvelopeDTO,
    NamedSubagentInstanceConfigDTO,
    QueueDrainResponse,
    QueueStatusResponse,
    SettlementNoticeItemDTO,
    SubagentReportItemDTO,
    SubmitReportRequest,
    SubmitSettlementRequest,
)

logger = logging.getLogger(__name__)


def _to_envelope_dto(envelope: OrderedFifoQueueEnvelope) -> FifoQueueEnvelopeDTO:
    """Convert harness queue envelope to schema DTO."""
    report_dto: Optional[SubagentReportItemDTO] = None
    if envelope.report_payload is not None:
        report_dto = SubagentReportItemDTO(
            report_id=envelope.report_payload.report_id,
            subagent_id=envelope.report_payload.subagent_id,
            task_id=envelope.report_payload.task_id,
            summary=envelope.report_payload.summary,
            content=envelope.report_payload.content,
            delivery_mode=envelope.report_payload.delivery_mode.value,
            severity=envelope.report_payload.severity,
            timestamp=envelope.report_payload.timestamp,
            metadata=envelope.report_payload.metadata,
        )

    settlement_dto: Optional[SettlementNoticeItemDTO] = None
    if envelope.settlement_payload is not None:
        settlement_dto = SettlementNoticeItemDTO(
            settlement_id=envelope.settlement_payload.settlement_id,
            subagent_id=envelope.settlement_payload.subagent_id,
            task_id=envelope.settlement_payload.task_id,
            exit_code=envelope.settlement_payload.exit_code,
            status=envelope.settlement_payload.status,
            summary=envelope.settlement_payload.summary,
            timestamp=envelope.settlement_payload.timestamp,
        )

    return FifoQueueEnvelopeDTO(
        sequence_id=envelope.sequence_id,
        item_type=envelope.item_type.value,
        task_id=envelope.task_id,
        subagent_id=envelope.subagent_id,
        wakes_parent=envelope.wakes_parent,
        urgent_interrupt=envelope.urgent_interrupt,
        timestamp=envelope.timestamp,
        report_payload=report_dto,
        settlement_payload=settlement_dto,
    )


class ReportFifoService:
    """Service layer governing session-isolated report delivery wakeup and FIFO settlement queues."""

    def __init__(self) -> None:
        self._coordinators: Dict[str, SubagentReportWakeupCoordinator] = {}

    def _get_coordinator(self, chat_id: str) -> SubagentReportWakeupCoordinator:
        if chat_id not in self._coordinators:
            self._coordinators[chat_id] = SubagentReportWakeupCoordinator()
        return self._coordinators[chat_id]

    def register_instances(
        self,
        chat_id: str,
        instance_dtos: List[NamedSubagentInstanceConfigDTO],
    ) -> List[NamedSubagentInstanceConfigDTO]:
        """Register or update multi-named subagent instance configurations for a chat session."""
        coord = self._get_coordinator(chat_id)
        registered: List[NamedSubagentInstanceConfigDTO] = []
        for dto in instance_dtos:
            cfg = NamedSubagentInstanceConfig(
                instance_name=dto.instance_name,
                role=dto.role,
                model_name=dto.model_name,
                system_prompt=dto.system_prompt,
                permission_mode=PermissionMode(dto.permission_mode),
                report_delivery=ReportDeliveryMode(dto.report_delivery),
                tools_allowed=dto.tools_allowed,
            )
            coord.register_instance(cfg)
            registered.append(dto)
        return registered

    def submit_report(
        self,
        chat_id: str,
        req: SubmitReportRequest,
    ) -> FifoQueueEnvelopeDTO:
        """Submit a subagent progress report, waking parent step if next-step delivery is set."""
        coord = self._get_coordinator(chat_id)
        delivery_mode = ReportDeliveryMode(req.delivery_mode) if req.delivery_mode else None
        envelope = coord.submit_report(
            instance_name=req.instance_name,
            task_id=req.task_id,
            summary=req.summary,
            content=req.content,
            delivery_mode=delivery_mode,
            severity=req.severity,
            metadata=req.metadata,
        )
        return _to_envelope_dto(envelope)

    def submit_settlement(
        self,
        chat_id: str,
        req: SubmitSettlementRequest,
    ) -> FifoQueueEnvelopeDTO:
        """Submit a task termination settlement notice, strictly ordered behind reports."""
        coord = self._get_coordinator(chat_id)
        envelope = coord.submit_settlement(
            instance_name=req.instance_name,
            task_id=req.task_id,
            exit_code=req.exit_code,
            status=req.status,
            summary=req.summary,
        )
        return _to_envelope_dto(envelope)

    def drain_step_batch(
        self,
        chat_id: str,
        max_items: int = 50,
    ) -> QueueDrainResponse:
        """Drain ordered events at parent agent step boundary in strict FIFO sequence."""
        coord = self._get_coordinator(chat_id)
        drained = coord.drain_step_batch(max_items=max_items)
        drained_dtos = [_to_envelope_dto(e) for e in drained]
        remaining = len(coord.queue)
        summary_rollup = coord.queue.generate_summary_rollup(drained)
        has_urgent = any(e.urgent_interrupt for e in drained)
        return QueueDrainResponse(
            drained_items=drained_dtos,
            remaining_count=remaining,
            urgent_interrupt=has_urgent,
            summary_rollup=summary_rollup,
        )

    def get_status(self, chat_id: str) -> QueueStatusResponse:
        """Fetch queue overview including pending items and registered subagents."""
        coord = self._get_coordinator(chat_id)
        pending_items = [_to_envelope_dto(e) for e in coord.queue.peek_all()]
        return QueueStatusResponse(
            pending_count=len(coord.queue),
            instances_count=len(coord.list_instances()),
            items=pending_items,
        )

    def cleanup_chat(self, chat_id: str) -> bool:
        """Release coordinator and clear FIFO queue resources for a terminated session."""
        if chat_id in self._coordinators:
            coord = self._coordinators.pop(chat_id)
            coord.queue.clear()
            logger.info("Cleaned up report FIFO coordinator for session %s", chat_id)
            return True
        return False


_instance: Optional[ReportFifoService] = None


def get_report_fifo_service() -> ReportFifoService:
    """Singleton getter for ReportFifoService."""
    global _instance
    if _instance is None:
        _instance = ReportFifoService()
    return _instance
