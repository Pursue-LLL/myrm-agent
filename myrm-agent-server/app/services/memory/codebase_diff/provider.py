"""Codebase diff fallback service provider for server business logic.

[POS]
Business service provider wrapping harness CodebaseDiffFallbackSuite,
handling DTO transformation, volume tier evaluation, and numstat parsing.

[INPUT]
- myrm_agent_harness.toolkits.memory.codebase_diff_fallback
- app.schemas.codebase_diff

[OUTPUT]
- CodebaseDiffProvider
- get_codebase_diff_provider
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.codebase_diff_fallback import (
    CodebaseDiffFallbackSuite,
    DiffCategory,
    DiffFallbackVerdict,
    DiffFileEntry,
    LargeDiffFallbackConfig,
)

from app.schemas.codebase_diff import (
    DiffFallbackVerdictDTO,
    DiffFileEntryDTO,
    DirectoryAggregateDTO,
    EvaluateDiffRequest,
    LargeDiffFallbackConfigDTO,
)


class CodebaseDiffProvider:
    """Server-side provider managing diff evaluation and fallback diagnostics."""

    def __init__(self) -> None:
        self._default_suite = CodebaseDiffFallbackSuite()

    def evaluate(self, request: EvaluateDiffRequest) -> DiffFallbackVerdictDTO:
        """Evaluates diff entries against configured volume thresholds and guards."""
        suite = self._resolve_suite(request.config)

        # Convert DTOs to harness domain models
        domain_files: list[DiffFileEntry] = [
            self._dto_to_domain_entry(dto) for dto in request.files
        ]

        verdict: DiffFallbackVerdict = suite.process_diff(
            files=domain_files,
            declared_total_files=request.declared_total_files,
            is_api_truncated=request.is_api_truncated,
            commit_message=request.commit_message,
        )

        return self._domain_verdict_to_dto(verdict)

    def parse_numstat(self, numstat_content: str) -> list[DiffFileEntryDTO]:
        """Parses git numstat text into structured entry DTOs."""
        entries: list[DiffFileEntryDTO] = []
        for line in numstat_content.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            domain_entry = CodebaseDiffFallbackSuite.parse_numstat_line(line_str)
            if domain_entry:
                entries.append(self._domain_entry_to_dto(domain_entry))
        return entries

    def _resolve_suite(
        self, config_dto: LargeDiffFallbackConfigDTO | None
    ) -> CodebaseDiffFallbackSuite:
        if config_dto is None:
            return self._default_suite

        cfg = LargeDiffFallbackConfig(
            micro_max_files=config_dto.micro_max_files,
            micro_max_lines=config_dto.micro_max_lines,
            moderate_max_files=config_dto.moderate_max_files,
            moderate_max_lines=config_dto.moderate_max_lines,
            large_max_files=config_dto.large_max_files,
            large_max_lines=config_dto.large_max_lines,
            hard_file_cap=config_dto.hard_file_cap,
            filter_lockfiles_in_moderate=config_dto.filter_lockfiles_in_moderate,
            token_budget=config_dto.token_budget,
        )
        return CodebaseDiffFallbackSuite(cfg)

    @staticmethod
    def _dto_to_domain_entry(dto: DiffFileEntryDTO) -> DiffFileEntry:
        # Match category or fallback to core_code
        try:
            category = DiffCategory(dto.category)
        except ValueError:
            category = DiffCategory.CORE_CODE

        return DiffFileEntry(
            path=dto.path,
            additions=dto.additions,
            deletions=dto.deletions,
            category=category,
            is_generated=dto.is_generated,
            is_renamed=dto.is_renamed,
            old_path=dto.old_path,
            patch_snippet=dto.patch_snippet,
        )

    @staticmethod
    def _domain_entry_to_dto(entry: DiffFileEntry) -> DiffFileEntryDTO:
        return DiffFileEntryDTO(
            path=entry.path,
            additions=entry.additions,
            deletions=entry.deletions,
            category=entry.category.value,
            is_generated=entry.is_generated,
            is_renamed=entry.is_renamed,
            old_path=entry.old_path,
            patch_snippet=entry.patch_snippet,
        )

    @staticmethod
    def _domain_verdict_to_dto(verdict: DiffFallbackVerdict) -> DiffFallbackVerdictDTO:
        aggregates: list[DirectoryAggregateDTO] = [
            DirectoryAggregateDTO(
                directory=aggr.directory,
                file_count=aggr.file_count,
                total_additions=aggr.total_additions,
                total_deletions=aggr.total_deletions,
                primary_category=aggr.primary_category.value,
            )
            for aggr in verdict.directory_aggregates
        ]

        return DiffFallbackVerdictDTO(
            tier=verdict.tier.value,
            total_files=verdict.total_files,
            total_additions=verdict.total_additions,
            total_deletions=verdict.total_deletions,
            is_truncated=verdict.is_truncated,
            truncation_reason=verdict.truncation_reason,
            active_files_count=verdict.active_files_count,
            filtered_noise_files_count=verdict.filtered_noise_files_count,
            directory_aggregates=aggregates,
            summary_text=verdict.summary_text,
            applied_optimizations=verdict.applied_optimizations,
        )


_instance: CodebaseDiffProvider | None = None


def get_codebase_diff_provider() -> CodebaseDiffProvider:
    """Returns singleton instance of CodebaseDiffProvider."""
    global _instance
    if _instance is None:
        _instance = CodebaseDiffProvider()
    return _instance
