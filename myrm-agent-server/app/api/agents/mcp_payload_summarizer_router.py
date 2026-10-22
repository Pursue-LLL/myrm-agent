"""FastAPI router for Heavy MCP Payload Fetch Subagent & Summarizer (Item 44).

[INPUT]
- app.schemas.mcp_payload_summarizer::{
    SummarizePayloadRequest,
    DiagnosePayloadRequest,
  }
- app.services.agent.mcp_payload_summarizer_service::{
    McpPayloadSummarizerService,
    get_mcp_payload_summarizer_service,
  }

[OUTPUT]
- REST endpoints under /agents/mcp-summarizer for payload compression,
  context contamination diagnostics, and preset spec discovery.

[POS]
- HTTP API layer for heavy payload isolation and summarization.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.sub_agents.mcp_summarizer import McpSummarizerError

from app.schemas.mcp_payload_summarizer import (
    DiagnosePayloadRequest,
    SummarizePayloadRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.mcp_payload_summarizer_service import (
    McpPayloadSummarizerService,
    get_mcp_payload_summarizer_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Heavy MCP Payload Summarizer"])


@router.post(
    "/agents/mcp-summarizer/summarize",
    response_model=StandardSuccessResponse,
    summary="Summarize bulky MCP payload into a structured artifact",
)
def summarize_payload_endpoint(
    req: SummarizePayloadRequest,
    service: McpPayloadSummarizerService = Depends(get_mcp_payload_summarizer_service),
) -> StandardSuccessResponse:
    """Restructure bulky raw payload into compact summary artifact saving parent context tokens."""
    try:
        artifact = service.summarize_payload(
            source_tool=req.source_tool,
            raw_payload=req.raw_payload,
            target_dto=req.target,
            artifact_store_path=req.artifact_store_path,
        )
        return create_success_response(artifact.model_dump())
    except McpSummarizerError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err


@router.post(
    "/agents/mcp-summarizer/diagnose",
    response_model=StandardSuccessResponse,
    summary="Diagnose payload size and audit context contamination risks",
)
def diagnose_payload_endpoint(
    req: DiagnosePayloadRequest,
    service: McpPayloadSummarizerService = Depends(get_mcp_payload_summarizer_service),
) -> StandardSuccessResponse:
    """Audit payload size and return contamination severity report with subagent delegation advice."""
    report = service.diagnose_payload(
        raw_payload=req.raw_payload,
        is_isolated_via_subagent=req.is_isolated_via_subagent,
    )
    return create_success_response(report.model_dump())


@router.get(
    "/agents/mcp-summarizer/preset",
    response_model=StandardSuccessResponse,
    summary="Get prebuilt mcp-data-summarizer subagent specification",
)
def get_preset_spec_endpoint(
    service: McpPayloadSummarizerService = Depends(get_mcp_payload_summarizer_service),
) -> StandardSuccessResponse:
    """Discover default configuration and tool whitelist for mcp-data-summarizer subagent."""
    preset = service.get_preset_spec()
    return create_success_response(preset.model_dump())
