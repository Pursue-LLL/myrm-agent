"""[INPUT] ComposeSquadBlueprintRequest, MaterializeSquadRequest, session_id.
[OUTPUT] SquadCompositionService managing Phase-1 team synthesis and Phase-2 model-deferred materialization.
[POS] Service layer for Orchestrator Auto Squad Composition & Budgeting Engine (Item 34).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.squad_composition import (
    MaterializedMember,
    MaterializedSquad,
    MemberBlueprint,
    ModelDeferredChoice,
    SquadBlueprint,
    SquadBlueprintComposer,
)

from app.schemas.squad_composition import (
    ComposeSquadBlueprintRequest,
    MaterializedMemberDTO,
    MaterializedSquadResponse,
    MaterializeSquadRequest,
    MemberBlueprintDTO,
    SquadBlueprintResponse,
    SquadRoleTierEnum,
    StopConditionDTO,
)

logger = logging.getLogger(__name__)


def _to_member_blueprint_dto(m: MemberBlueprint) -> MemberBlueprintDTO:
    return MemberBlueprintDTO(
        role_key=m.role_key,
        display_name=m.display_name,
        handle=m.handle,
        role_tier=SquadRoleTierEnum(m.role_tier.value),
        role_description=m.role_description,
        soul_system_prompt=m.soul_system_prompt,
        required_tools=list(m.required_tools),
        required_skills=list(m.required_skills),
        budget_tokens=m.budget_tokens,
        max_cost_usd=m.max_cost_usd,
        stop_condition=StopConditionDTO(
            max_turns=m.stop_condition.max_turns,
            max_tool_calls=m.stop_condition.max_tool_calls,
            allow_failure=m.stop_condition.allow_failure,
        ),
        suggested_model_tier=m.suggested_model_tier,
    )


def _to_blueprint_response(b: SquadBlueprint) -> SquadBlueprintResponse:
    return SquadBlueprintResponse(
        squad_id=b.squad_id,
        goal_description=b.goal_description,
        members=[_to_member_blueprint_dto(m) for m in b.members],
        total_budget_tokens=b.total_budget_tokens,
        total_max_cost_usd=b.total_max_cost_usd,
        max_descendants_per_run=b.max_descendants_per_run,
        created_at=b.created_at,
    )


def _to_materialized_member_dto(m: MaterializedMember) -> MaterializedMemberDTO:
    return MaterializedMemberDTO(
        role_key=m.role_key,
        bot_id=m.bot_id,
        handle=m.handle,
        display_name=m.display_name,
        role_tier=SquadRoleTierEnum(m.role_tier.value),
        selected_model_id=m.selected_model_id,
        allocated_budget_tokens=m.allocated_budget_tokens,
        allocated_max_cost_usd=m.allocated_max_cost_usd,
        system_prompt=m.system_prompt,
        tools=list(m.tools),
        skills=list(m.skills),
        stop_condition=StopConditionDTO(
            max_turns=m.stop_condition.max_turns,
            max_tool_calls=m.stop_condition.max_tool_calls,
            allow_failure=m.stop_condition.allow_failure,
        ),
    )


def _to_materialized_squad_response(m: MaterializedSquad) -> MaterializedSquadResponse:
    return MaterializedSquadResponse(
        squad_id=m.squad_id,
        orchestrator_bot_id=m.orchestrator_bot_id,
        members=[_to_materialized_member_dto(mem) for mem in m.members],
        total_budget_tokens=m.total_budget_tokens,
        total_max_cost_usd=m.total_max_cost_usd,
        status=m.status,
        created_at=m.created_at,
    )


class SquadCompositionService:
    """Service coordinator managing two-phase squad composition and compute budgeting."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blueprints: dict[str, dict[str, SquadBlueprint]] = {}
        self._materialized: dict[str, dict[str, MaterializedSquad]] = {}

    def compose_squad_blueprint(
        self,
        req: ComposeSquadBlueprintRequest,
    ) -> SquadBlueprintResponse:
        """Phase 1: Synthesize multi-agent roster blueprint with SOUL-level system prompts."""
        blueprint = SquadBlueprintComposer.compose_blueprint(
            goal_description=req.goal_description,
            total_budget_tokens=req.total_budget_tokens,
            total_max_cost_usd=req.total_max_cost_usd,
            max_descendants_per_run=req.max_descendants_per_run,
        )

        with self._lock:
            if req.session_id not in self._blueprints:
                self._blueprints[req.session_id] = {}
            self._blueprints[req.session_id][blueprint.squad_id] = blueprint

        logger.info(
            "Synthesized squad blueprint '%s' for session '%s' with %d roles",
            blueprint.squad_id,
            req.session_id,
            len(blueprint.members),
        )
        return _to_blueprint_response(blueprint)

    def get_squad_blueprint(
        self,
        session_id: str,
        squad_id: str,
    ) -> SquadBlueprintResponse | None:
        """Retrieve synthesized team blueprint by squad identifier."""
        with self._lock:
            bp = self._blueprints.get(session_id, {}).get(squad_id)
            return _to_blueprint_response(bp) if bp else None

    def list_squad_blueprints(
        self,
        session_id: str,
    ) -> list[SquadBlueprintResponse]:
        """List all team blueprints in a given session."""
        with self._lock:
            bps = list(self._blueprints.get(session_id, {}).values())
            return [_to_blueprint_response(b) for b in bps]

    def materialize_squad(
        self,
        req: MaterializeSquadRequest,
    ) -> MaterializedSquadResponse:
        """Phase 2: Bind user-confirmed models and instantiate execution squad."""
        with self._lock:
            bp = self._blueprints.get(req.session_id, {}).get(req.squad_id)

        if not bp:
            raise ValueError(f"Squad blueprint '{req.squad_id}' not found in session '{req.session_id}'")

        # Map DTO choices to domain choices
        choices_map: dict[str, ModelDeferredChoice] = {
            c.role_key: ModelDeferredChoice(
                role_key=c.role_key,
                selected_model_id=c.selected_model_id,
                custom_instructions=c.custom_instructions,
            )
            for c in req.model_choices
        }

        materialized = SquadBlueprintComposer.materialize_squad(
            blueprint=bp,
            model_choices=choices_map,
            default_model_id=req.default_model_id,
        )

        with self._lock:
            if req.session_id not in self._materialized:
                self._materialized[req.session_id] = {}
            self._materialized[req.session_id][materialized.squad_id] = materialized

        logger.info(
            "Materialized squad '%s' in session '%s' with %d active bots",
            materialized.squad_id,
            req.session_id,
            len(materialized.members),
        )
        return _to_materialized_squad_response(materialized)

    def get_materialized_squad(
        self,
        session_id: str,
        squad_id: str,
    ) -> MaterializedSquadResponse | None:
        """Fetch instantiated squad state by identifier."""
        with self._lock:
            mat = self._materialized.get(session_id, {}).get(squad_id)
            return _to_materialized_squad_response(mat) if mat else None

    def reset_session(self, session_id: str) -> None:
        """Purge all blueprints and materialized squads for a session."""
        with self._lock:
            self._blueprints.pop(session_id, None)
            self._materialized.pop(session_id, None)


# Global singleton instance
_squad_composition_service = SquadCompositionService()


def get_squad_composition_service() -> SquadCompositionService:
    """Get the singleton instance of SquadCompositionService."""
    return _squad_composition_service
