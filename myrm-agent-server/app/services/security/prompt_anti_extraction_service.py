"""Service layer for System Prompt Anti-Extraction, JIT Sharding, and Canary Sentinel Suite.

[INPUT]
- myrm_agent_harness.core.security.prompt_anti_extraction::*
- app.schemas.prompt_anti_extraction::*

[OUTPUT]
- PromptAntiExtractionService, get_prompt_anti_extraction_service

[POS]
Service coordinating JIT prompt sharding, reverse-extraction probe detection, and streaming canary circuit breakers.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.prompt_anti_extraction import (
    AntiExtractionSemanticGuard,
    JITInstructionSharder,
    PromptShard,
    ShardCategory,
    StreamingCanarySentinel,
)

from app.schemas.prompt_anti_extraction import (
    AssemblePromptRequest,
    AssemblePromptResponse,
    DetectExtractionProbeRequest,
    DetectExtractionProbeResponse,
    PromptShardSchema,
    RegisterShardsRequest,
    ScanStreamingChunkRequest,
    ScanStreamingChunkResponse,
    ScrubOutboundRequest,
    ScrubOutboundResponse,
)

logger = logging.getLogger(__name__)


def _to_domain_shard(s: PromptShardSchema) -> PromptShard:
    cat_map = {
        "CORE_BASE": ShardCategory.CORE_BASE,
        "STAGE_RULE": ShardCategory.STAGE_RULE,
        "PRIVATE_CONSTRAINT": ShardCategory.PRIVATE_CONSTRAINT,
    }
    category = cat_map.get(s.category, ShardCategory.CORE_BASE)
    return PromptShard(
        shard_id=s.shard_id,
        category=category,
        content=s.content,
        applicable_stages=list(s.applicable_stages),
        is_confidential=s.is_confidential,
    )


class PromptAntiExtractionService:
    """Service governing JIT modular prompt assembly and outbound leak prevention."""

    def __init__(
        self,
        sharder: JITInstructionSharder | None = None,
        guard: AntiExtractionSemanticGuard | None = None,
        sentinel: StreamingCanarySentinel | None = None,
    ) -> None:
        self._sharder: JITInstructionSharder = sharder or JITInstructionSharder()
        self._guard: AntiExtractionSemanticGuard = guard or AntiExtractionSemanticGuard()
        self._sentinel: StreamingCanarySentinel = sentinel or StreamingCanarySentinel()

    def register_shards(self, req: RegisterShardsRequest) -> AssemblePromptResponse:
        """Register modular prompt shards and return status."""
        for shard_schema in req.shards:
            self._sharder.register_shard(_to_domain_shard(shard_schema))

        assembled = self._sharder.assemble_active_prompt()
        all_shards = self._sharder.list_shards()
        return AssemblePromptResponse(
            assembled_prompt=assembled,
            total_shards_registered=len(all_shards),
        )

    def assemble_prompt(self, req: AssemblePromptRequest) -> AssemblePromptResponse:
        """Assemble minimal necessary active prompt for current execution stage."""
        assembled = self._sharder.assemble_active_prompt(
            current_stage=req.current_stage,
            inject_canary=req.inject_canary,
        )
        all_shards = self._sharder.list_shards()
        return AssemblePromptResponse(
            assembled_prompt=assembled,
            total_shards_registered=len(all_shards),
        )

    def detect_probe(self, req: DetectExtractionProbeRequest) -> DetectExtractionProbeResponse:
        """Detect extraction probing patterns in user text."""
        res = self._guard.detect_extraction_probe(req.user_text)
        return DetectExtractionProbeResponse(
            is_extraction_attempt=res.is_extraction_attempt,
            matched_pattern=res.matched_pattern,
            safe_fallback_response=res.safe_fallback_response,
        )

    def scan_streaming_chunk(self, req: ScanStreamingChunkRequest) -> ScanStreamingChunkResponse:
        """Scan real-time chunk for canary leakage with sub-10ms circuit breaking."""
        res = self._sentinel.scan_chunk(req.chunk, req.canary_token)
        return ScanStreamingChunkResponse(
            canary_detected=res.canary_detected,
            tripped=res.tripped,
            scrubbed_chunk=res.scrubbed_chunk,
            alert_reason=res.alert_reason,
        )

    def scrub_outbound(self, req: ScrubOutboundRequest) -> ScrubOutboundResponse:
        """Scrub canary token and private directive snippets before outbound delivery."""
        scrubbed = self._guard.scrub_outbound_text(
            text=req.text,
            canary_token=req.canary_token,
            confidential_snippets=req.confidential_snippets,
        )
        return ScrubOutboundResponse(scrubbed_text=scrubbed)

    def reset_all(self) -> None:
        """Reset internal state (test isolation)."""
        self._sharder.clear_all()
        self._sentinel.reset()


_INSTANCE: PromptAntiExtractionService | None = None


def get_prompt_anti_extraction_service() -> PromptAntiExtractionService:
    """Return singleton instance of PromptAntiExtractionService."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = PromptAntiExtractionService()
    return _INSTANCE
