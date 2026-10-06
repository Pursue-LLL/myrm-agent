"""Service layer for Compound Shell Risk Interceptor and Edge Auxiliary Suite.

[INPUT]
- myrm_agent_harness.core.security.compound_shell_risk::{CompoundCommandFirewall, TripleEdgeAuxiliaryEngine}
- app.schemas.compound_shell_risk::{InspectCommandRequest, CompoundCheckResponse, ScreenCommandRequest, CommandScreeningResponse, GenerateTitleRequest, TitleGenerationResponse, CompactProfileRequest, ProfileCompactionResponse}

[OUTPUT]
- CompoundShellRiskService: singleton service coordinating shell risk firewall and edge helpers.

[POS]
app/services/security service wrapping harness compound shell risk firewall and edge models.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.core.security.compound_shell_risk import (
    CompoundCommandFirewall,
    TripleEdgeAuxiliaryEngine,
)

from app.schemas.compound_shell_risk import (
    CommandRiskLevelEnum,
    CommandScreeningResponse,
    CompactProfileRequest,
    CompoundCheckResponse,
    FirewallVerdictEnum,
    GenerateTitleRequest,
    InspectCommandRequest,
    ProfileCompactionResponse,
    ScreenCommandRequest,
    TitleGenerationResponse,
)

logger = logging.getLogger(__name__)


class CompoundShellRiskService:
    """Service coordinating compound command syntax firewall and sub-second edge auxiliary tasks."""

    _instance: ClassVar[CompoundShellRiskService | None] = None

    def __init__(
        self,
        firewall: CompoundCommandFirewall | None = None,
        edge_engine: TripleEdgeAuxiliaryEngine | None = None,
    ) -> None:
        self._firewall = firewall or CompoundCommandFirewall()
        self._edge_engine = edge_engine or TripleEdgeAuxiliaryEngine()

    @classmethod
    def get_instance(cls) -> CompoundShellRiskService:
        """Obtain singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def inspect_command(self, request: InspectCommandRequest) -> CompoundCheckResponse:
        """Audit command for compound control operators and destructive payloads."""
        res = self._firewall.inspect(request.raw_command)
        return CompoundCheckResponse(
            raw_command=res.raw_command,
            is_compound=res.is_compound,
            operators_found=res.operators_found,
            sub_commands=res.sub_commands,
            verdict=FirewallVerdictEnum(res.verdict.value),
            risk_level=CommandRiskLevelEnum(res.risk_level.value),
            reason=res.reason,
        )

    def screen_command(self, request: ScreenCommandRequest) -> CommandScreeningResponse:
        """Pre-screen command risk in milliseconds on edge."""
        res = self._edge_engine.screen_command(request.command)
        return CommandScreeningResponse(
            command=res.command,
            risk_level=CommandRiskLevelEnum(res.risk_level.value),
            is_dangerous=res.is_dangerous,
            risk_factors=res.risk_factors,
            execution_time_ms=res.execution_time_ms,
            summary=res.summary,
        )

    def generate_title(self, request: GenerateTitleRequest) -> TitleGenerationResponse:
        """Generate session title and tags locally without cloud LLM overhead."""
        res = self._edge_engine.generate_session_title(request.first_turn_text)
        return TitleGenerationResponse(
            title=res.title,
            suggested_tags=res.suggested_tags,
            execution_time_ms=res.execution_time_ms,
        )

    def compact_profile(self, request: CompactProfileRequest) -> ProfileCompactionResponse:
        """Compact user tech stack preferences with 100% local privacy."""
        res = self._edge_engine.compact_user_profile(
            conversation_snippet=request.conversation_snippet,
            existing_profile=request.existing_profile,
        )
        return ProfileCompactionResponse(
            compacted_profile=dict(res.compacted_profile),
            extracted_preferences=res.extracted_preferences,
            execution_time_ms=res.execution_time_ms,
        )
