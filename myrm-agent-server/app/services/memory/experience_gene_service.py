"""
[POS] app/services/memory/experience_gene_service.py
[INPUT] app/schemas/experience_gene.py, myrm_agent_harness.toolkits.memory.evolution
[OUTPUT] ExperienceGeneService, get_experience_gene_service
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.evolution import (
    CausalGeneExtractor,
    ExecutionStepSnapshot,
    ExperienceGene,
    ExperienceGeneLedger,
    MultiTurnTaskTrace,
)

from app.schemas.experience_gene import (
    ExperienceGeneResponse,
    ExtractGeneRequest,
    ExtractGeneResponse,
    GeneAdviceListResponse,
    GeneAdviceRequest,
    GeneLedgerStatsResponse,
    GeneMutationAdviceResponse,
    GenePenalizeRequest,
)


class ExperienceGeneService:
    """Service governing causal gene synthesis, evolution ledger storage, and planning advice."""

    def __init__(self, ledger: ExperienceGeneLedger | None = None) -> None:
        self._ledger = ledger or ExperienceGeneLedger()

    def extract_and_record(self, req: ExtractGeneRequest) -> ExtractGeneResponse:
        """Extract causal gene from multi-turn trace and register or reinforce in ledger."""
        steps = [
            ExecutionStepSnapshot(
                step_index=s.step_index,
                tool_name=s.tool_name,
                tool_input_summary=s.tool_input_summary,
                tool_output_snippet=s.tool_output_snippet,
                is_failure=s.is_failure,
                error_signature=s.error_signature,
            )
            for s in req.trace.steps
        ]
        trace = MultiTurnTaskTrace(
            session_id=req.trace.session_id,
            task_goal=req.trace.task_goal,
            steps=steps,
            success_verified=req.trace.success_verified,
            final_solution_summary=req.trace.final_solution_summary,
        )

        extracted = CausalGeneExtractor.extract_gene(
            trace=trace, domain_tag=req.trace.domain_tag
        )
        if not extracted:
            return ExtractGeneResponse(
                status="no_divergent_gene", gene=None, reinforced=False
            )

        existing_gene = self._ledger.get_gene(extracted.gene_id)
        saved = self._ledger.register_or_reinforce(extracted)
        is_reinforced = existing_gene is not None or saved.proof_count > 1

        return ExtractGeneResponse(
            status="recorded",
            gene=self._serialize_gene(saved),
            reinforced=is_reinforced,
        )

    def get_mutation_advice(self, req: GeneAdviceRequest) -> GeneAdviceListResponse:
        """Synthesize planning advice to steer agents away from dead-ends towards proven solutions."""
        advices = self._ledger.generate_planning_mutation_advice(
            active_signals=req.active_signals,
            min_confidence=req.min_confidence,
            limit=req.limit,
        )
        serialized = [
            GeneMutationAdviceResponse(
                gene_id=a.gene_id,
                matched_signals=a.matched_signals,
                refuted_paths=a.refuted_paths,
                recommended_resolution=a.recommended_resolution,
                confidence=a.confidence,
                polarity=str(a.polarity),
            )
            for a in advices
        ]
        return GeneAdviceListResponse(advices=serialized, total_matched=len(serialized))

    def penalize_gene(self, req: GenePenalizeRequest) -> ExperienceGeneResponse | None:
        """Apply negative feedback penalty when a gene-guided action path fails."""
        updated = self._ledger.penalize_gene(req.gene_id, penalty=req.penalty)
        if not updated:
            return None
        return self._serialize_gene(updated)

    def list_genes(self) -> list[ExperienceGeneResponse]:
        """List all tracked genes ordered by cumulative proof count."""
        genes = self._ledger.list_genes()
        return [self._serialize_gene(g) for g in genes]

    def get_stats(self) -> GeneLedgerStatsResponse:
        """Retrieve aggregated health and evolution metrics of the gene ledger."""
        raw_stats = self._ledger.get_stats()
        return GeneLedgerStatsResponse(
            total_genes=int(raw_stats["total_genes"]),
            avg_confidence=float(raw_stats["avg_confidence"]),
            total_proof_count=int(raw_stats["total_proof_count"]),
        )

    @staticmethod
    def _serialize_gene(g: ExperienceGene) -> ExperienceGeneResponse:
        """Serialize domain ExperienceGene into Pydantic schema."""
        return ExperienceGeneResponse(
            gene_id=g.gene_id,
            trigger_signals=g.trigger_signals,
            hypotheses_refuted=g.hypotheses_refuted,
            proven_resolution=g.proven_resolution,
            polarity=str(g.polarity),
            confidence_score=g.confidence_score,
            proof_count=g.proof_count,
            provenance_session_id=g.provenance_session_id,
            tags=g.tags,
            created_at=g.created_at,
            updated_at=g.updated_at,
        )


_SERVICE_INSTANCE: ExperienceGeneService | None = None


def get_experience_gene_service() -> ExperienceGeneService:
    """Provide singleton instance of ExperienceGeneService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = ExperienceGeneService()
    return _SERVICE_INSTANCE
