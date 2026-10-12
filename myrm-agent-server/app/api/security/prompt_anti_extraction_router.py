"""FastAPI router for System Prompt Anti-Extraction, JIT Sharding, and Canary Sentinel Suite.

[INPUT]
- RegisterShardsRequest, AssemblePromptRequest, DetectExtractionProbeRequest, ScanStreamingChunkRequest, ScrubOutboundRequest.

[OUTPUT]
- AssemblePromptResponse, DetectExtractionProbeResponse, ScanStreamingChunkResponse, ScrubOutboundResponse.

[POS]
- app.api.security.prompt_anti_extraction_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.prompt_anti_extraction import (
    AssemblePromptRequest,
    AssemblePromptResponse,
    DetectExtractionProbeRequest,
    DetectExtractionProbeResponse,
    RegisterShardsRequest,
    ScanStreamingChunkRequest,
    ScanStreamingChunkResponse,
    ScrubOutboundRequest,
    ScrubOutboundResponse,
)
from app.services.security.prompt_anti_extraction_service import (
    PromptAntiExtractionService,
    get_prompt_anti_extraction_service,
)

router = APIRouter(
    prefix="/security/prompt-anti-extraction",
    tags=["Security - System Prompt Anti-Extraction & JIT Canary Sentinel"],
)


@router.post("/shards/register", response_model=AssemblePromptResponse)
async def register_shards(
    payload: RegisterShardsRequest,
    service: PromptAntiExtractionService = Depends(get_prompt_anti_extraction_service),
) -> AssemblePromptResponse:
    """Register modular prompt shards and return assembled baseline prompt."""
    return service.register_shards(payload)


@router.post("/assemble", response_model=AssemblePromptResponse)
async def assemble_prompt(
    payload: AssemblePromptRequest,
    service: PromptAntiExtractionService = Depends(get_prompt_anti_extraction_service),
) -> AssemblePromptResponse:
    """Dynamically assemble minimal active JIT prompt for the specified execution stage."""
    return service.assemble_prompt(payload)


@router.post("/detect-probe", response_model=DetectExtractionProbeResponse)
async def detect_extraction_probe(
    payload: DetectExtractionProbeRequest,
    service: PromptAntiExtractionService = Depends(get_prompt_anti_extraction_service),
) -> DetectExtractionProbeResponse:
    """Evaluate user input for system prompt extraction or reverse-engineering probes."""
    return service.detect_probe(payload)


@router.post("/scan-stream-chunk", response_model=ScanStreamingChunkResponse)
async def scan_streaming_chunk(
    payload: ScanStreamingChunkRequest,
    service: PromptAntiExtractionService = Depends(get_prompt_anti_extraction_service),
) -> ScanStreamingChunkResponse:
    """Real-time scan outbound streaming chunk for canary leakage with sub-10ms circuit breaking."""
    return service.scan_streaming_chunk(payload)


@router.post("/scrub-outbound", response_model=ScrubOutboundResponse)
async def scrub_outbound_payload(
    payload: ScrubOutboundRequest,
    service: PromptAntiExtractionService = Depends(get_prompt_anti_extraction_service),
) -> ScrubOutboundResponse:
    """Scrub canary token and private directive snippets before outbound tool or subagent dispatch."""
    return service.scrub_outbound(payload)
