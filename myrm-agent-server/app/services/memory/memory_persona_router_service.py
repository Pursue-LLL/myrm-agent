"""
[POS] app/services/memory/memory_persona_router_service.py
[INPUT] app.schemas.memory_persona_router, myrm_agent_harness.toolkits.memory.persona_router
[OUTPUT] MemoryPersonaRouterService, get_memory_persona_router_service

Singleton service coordinating on-demand persona skill routing and style suppression gating.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.persona_router import (
    AntiPollutionContextRouter,
    PersonaFacet,
    PersonaRoutingDecision,
    StyleSuppressionGate,
)

from app.schemas.memory_persona_router import (
    PersonaFacetDTO,
    RoutePersonaContextRequestDTO,
    RoutePersonaContextResponseDTO,
)


def _to_harness_facet(dto: PersonaFacetDTO) -> PersonaFacet:
    """Convert API PersonaFacetDTO into harness PersonaFacet instance."""
    return PersonaFacet(
        facet_id=dto.facet_id,
        name=dto.name,
        tone_guidance=dto.tone_guidance,
        sample_excerpts=tuple(dto.sample_excerpts),
        target_intents=tuple(dto.target_intents),
        is_default=dto.is_default,
        estimated_tokens=dto.estimated_tokens,
    )


class MemoryPersonaRouterService:
    """Service providing intent-aware persona suppression and on-demand style routing."""

    def __init__(
        self,
        gate: StyleSuppressionGate | None = None,
        router: AntiPollutionContextRouter | None = None,
    ) -> None:
        self._gate = gate or StyleSuppressionGate()
        self._router = router or AntiPollutionContextRouter(gate=self._gate)

    def route_persona_context(
        self, request: RoutePersonaContextRequestDTO
    ) -> RoutePersonaContextResponseDTO:
        """Route user query against candidate facets, enforcing 100% suppression on technical tasks."""
        harness_facets = [_to_harness_facet(dto) for dto in request.facets]
        decision: PersonaRoutingDecision = self._router.route(
            query=request.query,
            facets=harness_facets,
            explicit_facet_id=request.explicit_facet_id,
        )

        return RoutePersonaContextResponseDTO(
            is_suppressed=decision.is_suppressed,
            intent_category=decision.intent_category.value,
            active_facets=list(decision.active_facets),
            injected_content=decision.injected_content,
            tokens_saved_estimate=decision.tokens_saved_estimate,
            decision_reason=decision.decision_reason,
        )


_persona_service_instance: MemoryPersonaRouterService | None = None


def get_memory_persona_router_service() -> MemoryPersonaRouterService:
    """Acquire the singleton instance of MemoryPersonaRouterService."""
    global _persona_service_instance
    if _persona_service_instance is None:
        _persona_service_instance = MemoryPersonaRouterService()
    return _persona_service_instance
