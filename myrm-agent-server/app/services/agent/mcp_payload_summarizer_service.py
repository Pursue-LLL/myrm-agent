"""Service mediating heavy MCP payload summarization and contamination diagnostics (Item 44).

[INPUT]
- SummarizePayloadRequest, DiagnosePayloadRequest.

[OUTPUT]
- McpPayloadSummarizerService orchestrating payload compression,
  artifact generation, and context contamination audits.

[POS]
- Service layer for Heavy MCP Payload Fetch Subagent & Summarizer.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.sub_agents.mcp_summarizer import (
    ContaminationReport,
    HeavyMcpPayloadSummarizer,
    McpContaminationDoctor,
    McpPayloadSummaryArtifact,
    PayloadExtractionTarget,
    SubagentPresetSpec,
)

from app.schemas.mcp_payload_summarizer import (
    ContaminationReportDTO,
    ContaminationRiskLevelEnum,
    McpPayloadSummaryArtifactDTO,
    PayloadExtractionTargetDTO,
    SubagentPresetSpecDTO,
)

logger = logging.getLogger(__name__)


def _target_from_dto(dto: PayloadExtractionTargetDTO | None) -> PayloadExtractionTarget | None:
    if dto is None:
        return None
    return PayloadExtractionTarget(
        required_keys=tuple(dto.required_keys),
        max_summary_tokens=dto.max_summary_tokens,
        strip_raw_binary=dto.strip_raw_binary,
        preserve_markdown_tables=dto.preserve_markdown_tables,
        summarize_nested_lists_limit=dto.summarize_nested_lists_limit,
    )


def _artifact_to_dto(art: McpPayloadSummaryArtifact) -> McpPayloadSummaryArtifactDTO:
    return McpPayloadSummaryArtifactDTO(
        artifact_id=art.artifact_id,
        source_tool_or_mcp=art.source_tool_or_mcp,
        raw_payload_bytes=art.raw_payload_bytes,
        summary_bytes=art.summary_bytes,
        token_saving_ratio=art.token_saving_ratio,
        summary_text=art.summary_text,
        extracted_fields=dict(art.extracted_fields),
        file_reference_path=art.file_reference_path,
        created_at=art.created_at,
    )


def _report_to_dto(rep: ContaminationReport) -> ContaminationReportDTO:
    return ContaminationReportDTO(
        risk_level=ContaminationRiskLevelEnum(rep.risk_level.value),
        payload_bytes=rep.payload_bytes,
        estimated_tokens=rep.estimated_tokens,
        is_isolated_via_subagent=rep.is_isolated_via_subagent,
        remediation_advice=rep.remediation_advice,
        detected_at=rep.detected_at,
    )


class McpPayloadSummarizerService:
    """Thread-safe application service coordinating MCP payload summarization and doctor audits."""

    def __init__(self) -> None:
        self._summarizer = HeavyMcpPayloadSummarizer()
        self._doctor = McpContaminationDoctor()
        self._preset_spec = SubagentPresetSpec()
        self._lock = threading.Lock()

    def summarize_payload(
        self,
        source_tool: str,
        raw_payload: str,
        target_dto: PayloadExtractionTargetDTO | None = None,
        artifact_store_path: str | None = None,
    ) -> McpPayloadSummaryArtifactDTO:
        with self._lock:
            domain_target = _target_from_dto(target_dto)
            artifact = self._summarizer.summarize_payload(
                source_tool=source_tool,
                raw_payload=raw_payload,
                target=domain_target,
                artifact_store_path=artifact_store_path,
            )
            logger.info(
                "Processed MCP summary for '%s' (saved %.1f%% tokens)",
                source_tool,
                artifact.token_saving_ratio * 100.0,
            )
            return _artifact_to_dto(artifact)

    def diagnose_payload(
        self,
        raw_payload: str,
        is_isolated_via_subagent: bool = False,
    ) -> ContaminationReportDTO:
        with self._lock:
            report = self._doctor.diagnose_payload(
                raw_payload=raw_payload,
                is_isolated_via_subagent=is_isolated_via_subagent,
            )
            return _report_to_dto(report)

    def get_preset_spec(self) -> SubagentPresetSpecDTO:
        with self._lock:
            spec = self._preset_spec
            default_target = PayloadExtractionTargetDTO(
                required_keys=list(spec.default_extraction_target.required_keys),
                max_summary_tokens=spec.default_extraction_target.max_summary_tokens,
                strip_raw_binary=spec.default_extraction_target.strip_raw_binary,
                preserve_markdown_tables=spec.default_extraction_target.preserve_markdown_tables,
                summarize_nested_lists_limit=spec.default_extraction_target.summarize_nested_lists_limit,
            )
            return SubagentPresetSpecDTO(
                name=spec.name,
                description=spec.description,
                tools_whitelist=list(spec.tools_whitelist),
                default_extraction_target=default_target,
            )


_global_mcp_summarizer_service = McpPayloadSummarizerService()


def get_mcp_payload_summarizer_service() -> McpPayloadSummarizerService:
    """Retrieve global singleton McpPayloadSummarizerService instance."""
    return _global_mcp_summarizer_service
