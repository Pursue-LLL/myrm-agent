"""Markdown chunker business service provider.

[POS]
Singleton service managing sliding window Markdown slicing, incremental diff
indexing, token savings telemetry, and context hydration for Server API endpoints.

[INPUT]
- collections.abc.Sequence
- myrm_agent_harness.toolkits.memory (
    ChunkSourceHydrator,
    ChunkingConfig,
    IncrementalDiffReport,
    IncrementalIndexingPipeline,
    MarkdownChunk,
    MarkdownSlidingWindowChunker,
  )
- app.schemas.markdown_chunker (
    ChunkSliceRequest,
    ChunkSliceResponse,
    ChunkingConfigDTO,
    HydrateRequest,
    HydrateResponse,
    IncrementalDiffReportDTO,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
    MarkdownChunkDTO,
  )

[OUTPUT]
- MarkdownChunkerService, get_markdown_chunker_service
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.toolkits.memory import (
    ChunkingConfig,
    ChunkSourceHydrator,
    IncrementalDiffReport,
    IncrementalIndexingPipeline,
    MarkdownChunk,
    MarkdownSlidingWindowChunker,
)

from app.schemas.markdown_chunker import (
    ChunkingConfigDTO,
    ChunkSliceRequest,
    ChunkSliceResponse,
    HydrateRequest,
    HydrateResponse,
    IncrementalDiffReportDTO,
    IncrementalIndexRequest,
    IncrementalIndexResponse,
    MarkdownChunkDTO,
)


class MarkdownChunkerService:
    """Service orchestrating semantic Markdown slicing, incremental indexing, and hydration."""

    def __init__(self) -> None:
        """Initialize pipeline with default configuration."""
        self._default_config = ChunkingConfig()
        self._pipelines: dict[str, IncrementalIndexingPipeline] = {
            self._config_cache_key(self._default_config): IncrementalIndexingPipeline(
                self._default_config
            )
        }
        self._hydrator = ChunkSourceHydrator()

    @staticmethod
    def _config_cache_key(cfg: ChunkingConfig) -> str:
        """Derive deterministic cache key for chunking configuration."""
        return (
            f"{cfg.target_tokens}:{cfg.overlap_tokens}:"
            f"{cfg.chars_per_token}:{cfg.max_chunk_chars}"
        )

    def _get_pipeline(self, cfg: ChunkingConfig) -> IncrementalIndexingPipeline:
        """Get or create cached incremental pipeline for configuration."""
        key = self._config_cache_key(cfg)
        pipeline = self._pipelines.get(key)
        if pipeline is None:
            pipeline = IncrementalIndexingPipeline(cfg)
            self._pipelines[key] = pipeline
        return pipeline

    @staticmethod
    def _to_harness_config(dto: ChunkingConfigDTO | None) -> ChunkingConfig:
        """Convert DTO config to harness domain configuration model."""
        if dto is None:
            return ChunkingConfig()
        return ChunkingConfig(
            target_tokens=dto.target_tokens,
            overlap_tokens=dto.overlap_tokens,
            chars_per_token=dto.chars_per_token,
            max_chunk_chars=dto.max_chunk_chars,
        )

    @staticmethod
    def _to_chunk_dto(chunk: MarkdownChunk) -> MarkdownChunkDTO:
        """Convert harness domain chunk to DTO."""
        return MarkdownChunkDTO(
            chunk_id=chunk.chunk_id,
            source_path=chunk.source_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            text=chunk.text,
            chunk_hash=chunk.chunk_hash,
            token_estimate=chunk.token_estimate,
            is_truncated=chunk.is_truncated,
        )

    @staticmethod
    def _to_domain_chunk(dto: MarkdownChunkDTO) -> MarkdownChunk:
        """Convert DTO to harness domain chunk."""
        return MarkdownChunk(
            chunk_id=dto.chunk_id,
            source_path=dto.source_path,
            start_line=dto.start_line,
            end_line=dto.end_line,
            char_start=dto.char_start,
            char_end=dto.char_end,
            text=dto.text,
            chunk_hash=dto.chunk_hash,
            token_estimate=dto.token_estimate,
            is_truncated=dto.is_truncated,
        )

    @staticmethod
    def _to_report_dto(report: IncrementalDiffReport) -> IncrementalDiffReportDTO:
        """Convert harness domain diff report to DTO."""
        return IncrementalDiffReportDTO(
            source_path=report.source_path,
            total_chunks=report.total_chunks,
            reused_chunks=report.reused_chunks,
            changed_chunks=report.changed_chunks,
            deleted_chunks=report.deleted_chunks,
            token_savings_pct=report.token_savings_pct,
            status=report.status,
            timestamp=report.timestamp,
        )

    async def slice_markdown(self, request: ChunkSliceRequest) -> ChunkSliceResponse:
        """Slice Markdown content into semantic chunks using sliding window."""
        cfg = self._to_harness_config(request.config)
        chunker = MarkdownSlidingWindowChunker(cfg)
        chunks = chunker.chunk_document(request.content, source_path=request.source_path)
        dtos = [self._to_chunk_dto(c) for c in chunks]
        return ChunkSliceResponse(
            source_path=request.source_path,
            total_chunks=len(dtos),
            chunks=dtos,
        )

    async def incremental_index(
        self, request: IncrementalIndexRequest
    ) -> IncrementalIndexResponse:
        """Execute incremental diff indexing against cached chunks."""
        cfg = self._to_harness_config(request.config)
        pipeline = self._get_pipeline(cfg)

        def _mock_dummy_embedder(texts: Sequence[str]) -> Sequence[list[float]]:
            # Mock dummy vector (1536 dim) for testing pipeline embedding flow
            return [[0.05] * 1536 for _ in texts]

        report, chunks, _ = await pipeline.diff_and_index(
            source_path=request.source_path,
            new_content=request.new_content,
            embedder=_mock_dummy_embedder,
        )
        return IncrementalIndexResponse(
            report=self._to_report_dto(report),
            chunks=[self._to_chunk_dto(c) for c in chunks],
        )

    async def hydrate_context(self, request: HydrateRequest) -> HydrateResponse:
        """Hydrate surrounding context around chunk using line-level pointers."""
        domain_chunk = self._to_domain_chunk(request.chunk)
        hydrated_text = self._hydrator.hydrate_context(
            chunk=domain_chunk,
            full_document=request.full_document,
            window_lines=request.window_lines,
        )
        return HydrateResponse(
            hydrated_text=hydrated_text,
            window_lines=request.window_lines,
            start_line=domain_chunk.start_line,
            end_line=domain_chunk.end_line,
        )


_markdown_chunker_service_instance: MarkdownChunkerService | None = None


def get_markdown_chunker_service() -> MarkdownChunkerService:
    """Dependency injection provider returning singleton service instance."""
    global _markdown_chunker_service_instance
    if _markdown_chunker_service_instance is None:
        _markdown_chunker_service_instance = MarkdownChunkerService()
    return _markdown_chunker_service_instance
