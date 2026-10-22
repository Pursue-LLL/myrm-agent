"""[INPUT] AuditTeamScopeRequest, SafeTeamDesignConfigDTO, and chat session IDs.
[OUTPUT] ScopeGuardrailsService providing team permission audit, least-privilege pruning, and config governance.
[POS] Service layer for Orchestrator Scope Guardrails and Safe Team Design Mode (Item 37).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.scope_guardrails import (
    MemberScopeCandidate,
    SafeTeamDesignConfig,
    ScopeGuardrailsEngine,
    ScopeViolationFinding,
)

from app.schemas.scope_guardrails import (
    AuditTeamScopeRequest,
    MemberScopeCandidateDTO,
    SafeTeamDesignConfigDTO,
    ScopeViolationDTO,
    TeamScopeAuditResponse,
    ViolationSeverityEnum,
    ViolationTypeEnum,
)

logger = logging.getLogger(__name__)


def _to_config_domain(dto: SafeTeamDesignConfigDTO) -> SafeTeamDesignConfig:
    return SafeTeamDesignConfig(
        max_fanout_cap=dto.max_fanout_cap,
        require_hitl_for_high_risk=dto.require_hitl_for_high_risk,
        forbidden_tools=frozenset(dto.forbidden_tools),
        role_tool_allowlists={
            k: frozenset(v) for k, v in dto.role_tool_allowlists.items()
        },
    )


def _to_config_dto(cfg: SafeTeamDesignConfig) -> SafeTeamDesignConfigDTO:
    return SafeTeamDesignConfigDTO(
        max_fanout_cap=cfg.max_fanout_cap,
        require_hitl_for_high_risk=cfg.require_hitl_for_high_risk,
        forbidden_tools=sorted(cfg.forbidden_tools),
        role_tool_allowlists={
            k: sorted(v) for k, v in cfg.role_tool_allowlists.items()
        },
    )


def _to_finding_dto(f: ScopeViolationFinding) -> ScopeViolationDTO:
    return ScopeViolationDTO(
        role_key=f.role_key,
        tool_name=f.tool_name,
        violation_type=ViolationTypeEnum(f.violation_type.value),
        severity=ViolationSeverityEnum(f.severity.value),
        recommendation=f.recommendation,
    )


def _to_candidate_domain(dto: MemberScopeCandidateDTO) -> MemberScopeCandidate:
    return MemberScopeCandidate(
        role_key=dto.role_key,
        display_name=dto.display_name,
        requested_tools=list(dto.requested_tools),
    )


class ScopeGuardrailsService:
    """Service governing orchestrator scope guardrails and safe team design verification."""

    def __init__(self, engine: ScopeGuardrailsEngine | None = None) -> None:
        self._engine = engine or ScopeGuardrailsEngine()
        self._lock = threading.RLock()
        self._session_configs: dict[str, SafeTeamDesignConfig] = {}

    def audit_team_scope(
        self,
        req: AuditTeamScopeRequest,
        session_id: str | None = None,
    ) -> TeamScopeAuditResponse:
        """Evaluate candidate squad members against active session or override scope guardrails."""
        with self._lock:
            active_cfg: SafeTeamDesignConfig
            if req.config_override is not None:
                active_cfg = _to_config_domain(req.config_override)
            elif session_id and session_id in self._session_configs:
                active_cfg = self._session_configs[session_id]
            else:
                active_cfg = SafeTeamDesignConfig()

        domain_candidates = [_to_candidate_domain(c) for c in req.candidates]
        result = self._engine.evaluate_team_design(domain_candidates, config=active_cfg)

        return TeamScopeAuditResponse(
            is_safe=result.is_safe,
            sanitized_tools_map=result.sanitized_tools_map,
            violations=[_to_finding_dto(v) for v in result.violations],
            fanout_capped=result.fanout_capped,
            original_member_count=result.original_member_count,
            approved_member_count=result.approved_member_count,
            audit_summary=result.audit_summary,
        )

    def get_active_config(self, session_id: str | None = None) -> SafeTeamDesignConfigDTO:
        """Fetch active safe team design configuration for a chat session."""
        with self._lock:
            if session_id and session_id in self._session_configs:
                return _to_config_dto(self._session_configs[session_id])
            return _to_config_dto(SafeTeamDesignConfig())

    def update_session_config(
        self,
        session_id: str,
        cfg_dto: SafeTeamDesignConfigDTO,
    ) -> SafeTeamDesignConfigDTO:
        """Update or customize safe team design guardrails for a specific session."""
        domain_cfg = _to_config_domain(cfg_dto)
        with self._lock:
            self._session_configs[session_id] = domain_cfg
        logger.info("Updated scope guardrails config for session %s", session_id)
        return _to_config_dto(domain_cfg)

    def reset_session_config(self, session_id: str) -> None:
        """Reset session-specific guardrail overrides to engine defaults."""
        with self._lock:
            self._session_configs.pop(session_id, None)

    def clear_all(self) -> None:
        """Purge all session-specific configurations."""
        with self._lock:
            self._session_configs.clear()


_global_engine = ScopeGuardrailsEngine()
_global_service = ScopeGuardrailsService(_global_engine)


def get_scope_guardrails_service() -> ScopeGuardrailsService:
    """FastAPI dependency provider for ScopeGuardrailsService."""
    return _global_service
