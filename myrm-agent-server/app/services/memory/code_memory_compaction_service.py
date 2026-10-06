"""
[POS] app/services/memory/code_memory_compaction_service.py
[INPUT] app/schemas/code_memory_compaction.py, myrm_agent_harness.toolkits.memory.compaction
[OUTPUT] CodeMemoryCompactionService, get_code_memory_compaction_service
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.compaction import (
    CodeAbstractionLevel,
    CodeBlockItem,
    CodeMemoryBudgetCompactor,
    CodeSkeletonExtractor,
    CompactionConfig,
)

from app.schemas.code_memory_compaction import (
    CodeCompactionRequest,
    CodeCompactionResponse,
    CompactedBlockOutput,
    SingleSkeletonRequest,
    SingleSkeletonResponse,
)


class CodeMemoryCompactionService:
    """Service managing dynamic code memory compaction and AST skeleton extraction."""

    def __init__(self) -> None:
        self._compactor = CodeMemoryBudgetCompactor()

    def compact(self, req: CodeCompactionRequest) -> CodeCompactionResponse:
        """Compact multiple code snippets to fit strictly within the given token budget."""
        items = [
            CodeBlockItem(
                file_path=item.file_path,
                source_code=item.source_code,
                relevance_score=item.relevance_score,
                language=item.language,
            )
            for item in req.items
        ]

        # Parse minimum abstraction level
        try:
            min_lvl = CodeAbstractionLevel(req.min_level)
        except ValueError:
            min_lvl = CodeAbstractionLevel.L1_SIGNATURES

        config = CompactionConfig(
            token_budget=req.token_budget,
            min_level=min_lvl,
            strip_private_symbols=req.strip_private_symbols,
            tokens_per_char_ratio=req.tokens_per_char_ratio,
        )

        res = self._compactor.compact(items=items, config=config)

        blocks_out = [
            CompactedBlockOutput(
                file_path=b.file_path,
                abstraction_level=str(b.abstraction_level),
                content=b.content,
                original_token_count=b.original_token_count,
                compacted_token_count=b.compacted_token_count,
            )
            for b in res.compacted_blocks
        ]

        return CodeCompactionResponse(
            compacted_blocks=blocks_out,
            total_original_tokens=res.total_original_tokens,
            total_compacted_tokens=res.total_compacted_tokens,
            budget_limit=res.budget_limit,
            compression_ratio=res.compression_ratio,
        )

    def extract_skeleton(self, req: SingleSkeletonRequest) -> SingleSkeletonResponse:
        """Extract structural skeleton or signatures for a single code snippet."""
        try:
            target_level = CodeAbstractionLevel(req.level)
        except ValueError:
            target_level = CodeAbstractionLevel.L1_SIGNATURES

        orig_tok = CodeSkeletonExtractor.estimate_tokens(req.source_code)
        extracted = CodeSkeletonExtractor.extract_skeleton(
            source_code=req.source_code,
            level=target_level,
            strip_private=req.strip_private_symbols,
            language=req.language,
        )
        compact_tok = CodeSkeletonExtractor.estimate_tokens(extracted)

        return SingleSkeletonResponse(
            abstraction_level=str(target_level),
            content=extracted,
            original_token_count=orig_tok,
            compacted_token_count=compact_tok,
        )


_SERVICE_INSTANCE: CodeMemoryCompactionService | None = None


def get_code_memory_compaction_service() -> CodeMemoryCompactionService:
    """Provide singleton instance of CodeMemoryCompactionService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = CodeMemoryCompactionService()
    return _SERVICE_INSTANCE
