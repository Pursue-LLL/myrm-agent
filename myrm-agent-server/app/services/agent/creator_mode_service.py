"""[INPUT] SynthesizePresetRequest, VerifyInSandboxRequest, RoamingSyncRequest.
[OUTPUT] CreatorModeService providing natural language preset synthesis, defensive sandbox evaluation, and multi-platform profile roaming.
[POS] Service layer for Creator Mode Guardrailed Preset Synthesizer and Defensive Sandbox (Item 39).
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.creator_mode import (
    AgentPresetDraft,
    AgentPresetSynthesizer,
    CaseEvaluationResult,
    CaseVerdict,
    DefensiveSandboxVerifier,
    DefensiveTestCase,
    RoamingPlatform,
    RoamingSyncRecord,
    SandboxVerificationReport,
    UnifiedProfileRoamingGateway,
)

from app.schemas.creator_mode import (
    AgentPresetDraftDTO,
    CaseEvaluationResultDTO,
    CaseVerdictEnum,
    DefensiveTestCaseDTO,
    RoamingPlatformEnum,
    RoamingSyncRecordDTO,
    RoamingSyncRequest,
    RoamingSyncResponse,
    SandboxVerificationResponse,
    SynthesizePresetRequest,
    VerifyInSandboxRequest,
)

logger = logging.getLogger(__name__)


def _to_draft_domain(dto: AgentPresetDraftDTO) -> AgentPresetDraft:
    return AgentPresetDraft(
        preset_id=dto.preset_id,
        name=dto.name,
        role=dto.role,
        description=dto.description,
        system_prompt=dto.system_prompt,
        allowed_tools=frozenset(dto.allowed_tools),
        denied_tools=frozenset(dto.denied_tools),
        guardrails=dict(dto.guardrails),
        created_at=dto.created_at,
    )


def _to_draft_dto(draft: AgentPresetDraft) -> AgentPresetDraftDTO:
    return AgentPresetDraftDTO(
        preset_id=draft.preset_id,
        name=draft.name,
        role=draft.role,
        description=draft.description,
        system_prompt=draft.system_prompt,
        allowed_tools=sorted(draft.allowed_tools),
        denied_tools=sorted(draft.denied_tools),
        guardrails=dict(draft.guardrails),
        created_at=draft.created_at,
    )


def _to_case_domain(dto: DefensiveTestCaseDTO) -> DefensiveTestCase:
    return DefensiveTestCase(
        case_id=dto.case_id,
        name=dto.name,
        is_exploit=dto.is_exploit,
        prompt_input=dto.prompt_input,
        target_tool=dto.target_tool,
        expected_verdict=CaseVerdict(dto.expected_verdict.value),
    )


def _to_result_dto(res: CaseEvaluationResult) -> CaseEvaluationResultDTO:
    return CaseEvaluationResultDTO(
        case_id=res.case_id,
        name=res.name,
        is_exploit=res.is_exploit,
        passed=res.passed,
        actual_verdict=CaseVerdictEnum(res.actual_verdict.value),
        reason=res.reason,
    )


def _to_report_dto(rep: SandboxVerificationReport) -> SandboxVerificationResponse:
    return SandboxVerificationResponse(
        is_safe=rep.is_safe,
        total_cases=rep.total_cases,
        passed_cases=rep.passed_cases,
        blocked_exploits=rep.blocked_exploits,
        results=[_to_result_dto(r) for r in rep.results],
        summary=rep.summary,
        verified_at=rep.verified_at,
    )


def _to_record_dto(rec: RoamingSyncRecord) -> RoamingSyncRecordDTO:
    return RoamingSyncRecordDTO(
        preset_id=rec.preset_id,
        platform=RoamingPlatformEnum(rec.platform.value),
        target_path=rec.target_path,
        status=rec.status,
        healed=rec.healed,
        timestamp=rec.timestamp,
    )


class CreatorModeService:
    """Service governing natural language preset compilation, sandbox defense validation, and profile roaming."""

    def __init__(
        self,
        synthesizer: AgentPresetSynthesizer | None = None,
        sandbox: DefensiveSandboxVerifier | None = None,
        roaming_gateway: UnifiedProfileRoamingGateway | None = None,
    ) -> None:
        self._synthesizer = synthesizer or AgentPresetSynthesizer()
        self._sandbox = sandbox or DefensiveSandboxVerifier()
        self._roaming_gateway = roaming_gateway or UnifiedProfileRoamingGateway()

    def synthesize_preset(self, req: SynthesizePresetRequest) -> AgentPresetDraftDTO:
        """Synthesize natural language intent into a least-privilege agent draft."""
        forbidden = frozenset(req.custom_forbidden_tools) if req.custom_forbidden_tools else None
        draft = self._synthesizer.synthesize_preset(
            intent=req.intent,
            name=req.name,
            role=req.role,
            custom_forbidden_tools=forbidden,
        )
        return _to_draft_dto(draft)

    def verify_in_sandbox(self, req: VerifyInSandboxRequest) -> SandboxVerificationResponse:
        """Execute defensive sandbox verification battery against the preset draft."""
        draft_domain = _to_draft_domain(req.draft)
        custom_cases = [_to_case_domain(c) for c in req.custom_cases] if req.custom_cases else None
        report = self._sandbox.verify_draft(draft=draft_domain, custom_cases=custom_cases)
        return _to_report_dto(report)

    def sync_roaming(self, req: RoamingSyncRequest) -> RoamingSyncResponse:
        """Broadcast preset across target platforms with automated broken path healing."""
        draft_domain = _to_draft_domain(req.draft)
        platforms = [RoamingPlatform(p.value) for p in req.target_platforms] if req.target_platforms else None
        records = self._roaming_gateway.sync_preset(
            draft=draft_domain,
            target_platforms=platforms,
            legacy_broken_path=req.legacy_broken_path,
        )
        return RoamingSyncResponse(records=[_to_record_dto(r) for r in records])

    def list_roaming_records(self) -> list[RoamingSyncRecordDTO]:
        """List all active multi-platform synchronization records."""
        records = self._roaming_gateway.list_all_records()
        return [_to_record_dto(r) for r in records]

    def resolve_roaming_path(self, preset_id: str, platform: RoamingPlatformEnum) -> str:
        """Resolve canonical path for a preset on a specific platform, auto-healing on miss."""
        return self._roaming_gateway.resolve_preset_path(
            preset_id=preset_id,
            platform=RoamingPlatform(platform.value),
        )


_creator_lock = threading.Lock()
_global_creator_service: CreatorModeService | None = None


def get_creator_mode_service() -> CreatorModeService:
    """Retrieve thread-safe global CreatorModeService singleton."""
    global _global_creator_service
    if _global_creator_service is None:
        with _creator_lock:
            if _global_creator_service is None:
                _global_creator_service = CreatorModeService()
    return _global_creator_service
