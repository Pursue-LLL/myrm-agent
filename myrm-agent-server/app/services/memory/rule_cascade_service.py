# [POS]: app/services/memory/rule_cascade_service.py
# [INPUT]: app.schemas.rule_cascade, myrm_agent_harness.toolkits.memory
# [OUTPUT]: RuleCascadeService, get_rule_cascade_service

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    CascadedRuleSet,
    DeterministicRuleCascadeLoader,
    DeterministicRuleEntry,
    EvidencePermissionLevel,
    EvidenceScopeKind,
    EvidenceSourceKind,
    FiveDimEvidenceMetadata,
    FiveDimFilterSpec,
    FiveDimPreFilterEngine,
    PreFilteredEvidenceResult,
    TimeDecayCalculator,
)

from app.schemas.rule_cascade import (
    CascadedRuleSetDTO,
    DeterministicRuleEntryDTO,
    FiveDimEvidenceMetadataDTO,
    PreFilteredEvidenceResponse,
    PreFilterEvidenceRequest,
    RegisterRuleRequest,
    RegisterRuleResponse,
)

logger = logging.getLogger(__name__)


def _to_meta_dto(meta: FiveDimEvidenceMetadata) -> FiveDimEvidenceMetadataDTO:
    return FiveDimEvidenceMetadataDTO(
        scope=meta.scope.value,
        scope_path=meta.scope_path,
        source=meta.source.value,
        source_authority=meta.source_authority,
        created_at=meta.created_at,
        half_life_days=meta.half_life_days,
        confidence=meta.confidence,
        permission=meta.permission.value,
    )


def _to_rule_dto(rule: DeterministicRuleEntry) -> DeterministicRuleEntryDTO:
    return DeterministicRuleEntryDTO(
        rule_id=rule.rule_id,
        title=rule.title,
        rule_content=rule.rule_content,
        metadata=_to_meta_dto(rule.metadata),
        is_enforced=rule.is_enforced,
    )


def _to_meta_domain(dto: FiveDimEvidenceMetadataDTO) -> FiveDimEvidenceMetadata:
    scope_map: dict[str, EvidenceScopeKind] = {
        "global": EvidenceScopeKind.GLOBAL,
        "organization": EvidenceScopeKind.ORGANIZATION,
        "workspace": EvidenceScopeKind.WORKSPACE,
        "directory": EvidenceScopeKind.DIRECTORY,
        "file": EvidenceScopeKind.FILE,
    }
    source_map: dict[str, EvidenceSourceKind] = {
        "user_explicit": EvidenceSourceKind.USER_EXPLICIT,
        "tool_verified": EvidenceSourceKind.TOOL_VERIFIED,
        "agent_inferred": EvidenceSourceKind.AGENT_INFERRED,
    }
    perm_map: dict[str, EvidencePermissionLevel] = {
        "public": EvidencePermissionLevel.PUBLIC,
        "workspace_internal": EvidencePermissionLevel.WORKSPACE_INTERNAL,
        "confidential_admin": EvidencePermissionLevel.CONFIDENTIAL_ADMIN,
    }

    created = dto.created_at or datetime.now(UTC).isoformat()
    return FiveDimEvidenceMetadata(
        scope=scope_map.get(dto.scope.lower(), EvidenceScopeKind.WORKSPACE),
        scope_path=dto.scope_path,
        source=source_map.get(dto.source.lower(), EvidenceSourceKind.USER_EXPLICIT),
        source_authority=dto.source_authority,
        created_at=created,
        half_life_days=dto.half_life_days,
        confidence=dto.confidence,
        permission=perm_map.get(dto.permission.lower(), EvidencePermissionLevel.PUBLIC),
    )


def _to_rule_domain(dto: DeterministicRuleEntryDTO) -> DeterministicRuleEntry:
    return DeterministicRuleEntry(
        rule_id=dto.rule_id,
        title=dto.title,
        rule_content=dto.rule_content,
        metadata=_to_meta_domain(dto.metadata),
        is_enforced=dto.is_enforced,
    )


class RuleCascadeService:
    """Service managing deterministic rule cascading and 5-dimensional pre-filtering."""

    def __init__(
        self,
        loader: DeterministicRuleCascadeLoader | None = None,
        filter_engine: FiveDimPreFilterEngine | None = None,
        decay_calc: TimeDecayCalculator | None = None,
    ) -> None:
        self._loader = loader or DeterministicRuleCascadeLoader()
        self._decay = decay_calc or TimeDecayCalculator()
        self._filter_engine = filter_engine or FiveDimPreFilterEngine(decay_calculator=self._decay)

    def register_rule(self, req: RegisterRuleRequest) -> RegisterRuleResponse:
        """Register a deterministic engineering rule."""
        domain_rule = DeterministicRuleEntry(
            rule_id=req.rule_id,
            title=req.title,
            rule_content=req.rule_content,
            metadata=_to_meta_domain(req.metadata),
            is_enforced=req.is_enforced,
        )
        self._loader.register_rule(domain_rule)
        return RegisterRuleResponse(
            is_success=True,
            rule_id=req.rule_id,
            registered_rule=_to_rule_dto(domain_rule),
        )

    def resolve_cascade(self, target_path: str) -> CascadedRuleSetDTO:
        """Resolve hierarchically inherited and overridden rules along target directory path."""
        cascaded: CascadedRuleSet = self._loader.resolve_cascade(target_path)
        return CascadedRuleSetDTO(
            target_path=cascaded.target_path,
            inherited_rules=[_to_rule_dto(r) for r in cascaded.inherited_rules],
            effective_rules_count=cascaded.effective_rules_count,
            sources_breakdown=cascaded.sources_breakdown,
        )

    def filter_evidence(self, req: PreFilterEvidenceRequest) -> PreFilteredEvidenceResponse:
        """Execute physical 5-dimensional pre-filtering before recall."""
        candidates = [_to_rule_domain(c) for c in req.candidates]

        scope_map: dict[str, EvidenceScopeKind] = {
            "global": EvidenceScopeKind.GLOBAL,
            "organization": EvidenceScopeKind.ORGANIZATION,
            "workspace": EvidenceScopeKind.WORKSPACE,
            "directory": EvidenceScopeKind.DIRECTORY,
            "file": EvidenceScopeKind.FILE,
        }
        perm_map: dict[str, EvidencePermissionLevel] = {
            "public": EvidencePermissionLevel.PUBLIC,
            "workspace_internal": EvidencePermissionLevel.WORKSPACE_INTERNAL,
            "confidential_admin": EvidencePermissionLevel.CONFIDENTIAL_ADMIN,
        }

        allowed_scopes: set[EvidenceScopeKind] | None = None
        if req.allowed_scopes:
            allowed_scopes = {
                scope_map[s.lower()]
                for s in req.allowed_scopes
                if s.lower() in scope_map
            }

        required_perm: EvidencePermissionLevel | None = None
        if req.required_permission and req.required_permission.lower() in perm_map:
            required_perm = perm_map[req.required_permission.lower()]

        spec = FiveDimFilterSpec(
            allowed_scopes=allowed_scopes,
            scope_path_prefix=req.scope_path_prefix,
            min_authority=req.min_authority,
            min_confidence=req.min_confidence,
            required_permission=required_perm,
            max_decay_age_days=req.max_decay_age_days,
        )

        result: PreFilteredEvidenceResult = self._filter_engine.filter_evidence(candidates, spec)

        return PreFilteredEvidenceResponse(
            passed_items=[_to_rule_dto(item) for item in result.items],
            total_evaluated=result.total_evaluated,
            passed_count=result.passed_count,
            rejection_reasons=result.rejection_reasons,
        )

    def list_all_rules(self) -> list[DeterministicRuleEntryDTO]:
        """List all currently registered deterministic rules."""
        return [_to_rule_dto(r) for r in self._loader.get_all_rules()]


_instance: RuleCascadeService | None = None


def get_rule_cascade_service() -> RuleCascadeService:
    """Dependency provider for RuleCascadeService singleton."""
    global _instance
    if _instance is None:
        _instance = RuleCascadeService()
    return _instance
