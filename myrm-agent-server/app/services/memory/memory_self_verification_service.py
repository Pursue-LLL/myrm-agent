"""
[POS] app/services/memory/memory_self_verification_service.py
[INPUT] app.schemas.memory_self_verification, myrm_agent_harness.toolkits.memory.self_verification
[OUTPUT] MemorySelfVerificationService, get_memory_self_verification_service

Singleton service coordinating memory self-verification diagnostics and benchmarks.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.self_verification import (
    MemorySelfVerificationRunner,
)

from app.schemas.memory_self_verification import (
    FactMutationProbeRequestDTO,
    FactMutationProbeResponseDTO,
    ProceduralAntiDropProbeRequestDTO,
    ProceduralAntiDropProbeResponseDTO,
    RunDiagnosticSuiteRequestDTO,
    RunDiagnosticSuiteResponseDTO,
    ZeroLexicalProbeRequestDTO,
    ZeroLexicalProbeResponseDTO,
)


class MemorySelfVerificationService:
    """Service providing in-place fact mutation tests and zero-lexical recall verification."""

    def __init__(self, runner: MemorySelfVerificationRunner | None = None) -> None:
        self._runner = runner or MemorySelfVerificationRunner()

    def run_fact_mutation_probe(
        self,
        request: FactMutationProbeRequestDTO,
    ) -> FactMutationProbeResponseDTO:
        """Execute in-place fact mutation probe asserting conflict elimination."""
        result = self._runner.run_in_place_mutation_probe(
            entity_key=request.entity_key,
            initial_fact=request.initial_fact,
            updated_fact=request.updated_fact,
        )
        return FactMutationProbeResponseDTO(
            probe_id=result.probe_id,
            entity_key=result.entity_key,
            initial_fact=result.initial_fact,
            updated_fact=result.updated_fact,
            success=result.success,
            retained_fact_count=result.retained_fact_count,
            is_latest_retained=result.is_latest_retained,
            residual_conflict_count=result.residual_conflict_count,
            latency_ms=result.latency_ms,
            details=result.details,
        )

    def run_zero_lexical_probe(
        self,
        request: ZeroLexicalProbeRequestDTO,
    ) -> ZeroLexicalProbeResponseDTO:
        """Execute pure semantic recall probe with zero surface word overlap."""
        result = self._runner.run_zero_lexical_probe(
            query=request.query,
            memory_text=request.memory_text,
            min_similarity_threshold=request.min_similarity_threshold,
        )
        return ZeroLexicalProbeResponseDTO(
            probe_id=result.probe_id,
            query=result.query,
            memory_text=result.memory_text,
            lexical_overlap_ratio=result.lexical_overlap_ratio,
            is_zero_overlap=result.is_zero_overlap,
            cosine_similarity=result.cosine_similarity,
            recalled=result.recalled,
            latency_ms=result.latency_ms,
            details=result.details,
        )

    def run_procedural_anti_drop_probe(
        self,
        request: ProceduralAntiDropProbeRequestDTO,
    ) -> ProceduralAntiDropProbeResponseDTO:
        """Execute procedural routing & anti-silent drop probe."""
        result = self._runner.run_procedural_anti_drop_probe(
            rule_content=request.rule_content,
        )
        return ProceduralAntiDropProbeResponseDTO(
            probe_id=result.probe_id,
            rule_content=result.rule_content,
            routed_track=result.routed_track,
            was_dropped=result.was_dropped,
            is_preserved=result.is_preserved,
            drop_reason=result.drop_reason,
            latency_ms=result.latency_ms,
            details=result.details,
        )

    def run_full_diagnostic_suite(
        self,
        request: RunDiagnosticSuiteRequestDTO,
    ) -> RunDiagnosticSuiteResponseDTO:
        """Execute complete diagnostic suite inside isolated sandbox with guaranteed cleanup."""
        report = self._runner.run_full_diagnostic_suite(
            custom_namespace=request.custom_namespace,
        )
        return RunDiagnosticSuiteResponseDTO(
            report_id=report.report_id,
            sandbox_namespace=report.sandbox_namespace,
            grade=report.grade.value.upper(),
            total_probes=report.total_probes,
            passed_probes=report.passed_probes,
            score=report.score,
            sandbox_cleaned=report.sandbox_cleaned,
            fact_mutation_result=FactMutationProbeResponseDTO(
                probe_id=report.fact_mutation_result.probe_id,
                entity_key=report.fact_mutation_result.entity_key,
                initial_fact=report.fact_mutation_result.initial_fact,
                updated_fact=report.fact_mutation_result.updated_fact,
                success=report.fact_mutation_result.success,
                retained_fact_count=report.fact_mutation_result.retained_fact_count,
                is_latest_retained=report.fact_mutation_result.is_latest_retained,
                residual_conflict_count=report.fact_mutation_result.residual_conflict_count,
                latency_ms=report.fact_mutation_result.latency_ms,
                details=report.fact_mutation_result.details,
            ),
            zero_lexical_result=ZeroLexicalProbeResponseDTO(
                probe_id=report.zero_lexical_result.probe_id,
                query=report.zero_lexical_result.query,
                memory_text=report.zero_lexical_result.memory_text,
                lexical_overlap_ratio=report.zero_lexical_result.lexical_overlap_ratio,
                is_zero_overlap=report.zero_lexical_result.is_zero_overlap,
                cosine_similarity=report.zero_lexical_result.cosine_similarity,
                recalled=report.zero_lexical_result.recalled,
                latency_ms=report.zero_lexical_result.latency_ms,
                details=report.zero_lexical_result.details,
            ),
            procedural_anti_drop_result=ProceduralAntiDropProbeResponseDTO(
                probe_id=report.procedural_anti_drop_result.probe_id,
                rule_content=report.procedural_anti_drop_result.rule_content,
                routed_track=report.procedural_anti_drop_result.routed_track,
                was_dropped=report.procedural_anti_drop_result.was_dropped,
                is_preserved=report.procedural_anti_drop_result.is_preserved,
                drop_reason=report.procedural_anti_drop_result.drop_reason,
                latency_ms=report.procedural_anti_drop_result.latency_ms,
                details=report.procedural_anti_drop_result.details,
            ),
            mean_latency_ms=report.mean_latency_ms,
            summary=report.summary,
        )


_service_instance: MemorySelfVerificationService | None = None


def get_memory_self_verification_service() -> MemorySelfVerificationService:
    """Retrieve singleton instance of MemorySelfVerificationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MemorySelfVerificationService()
    return _service_instance
