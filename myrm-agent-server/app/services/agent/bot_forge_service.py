"""Service layer for Chat-Driven Agent & Team Factory with Builder Safety Envelope."""

from __future__ import annotations

from typing import Dict, Optional

from myrm_agent_harness.agent.sub_agents.bot_forge import (
    BotProfileSpec,
    BuilderAuthority,
    BuilderSafetyEnvelope,
    PipelineExecutionState,
    TeamCompositionSpec,
    VerifiedCreationPipeline,
)

from app.schemas.bot_forge import (
    BotForgeCatalogResponseDTO,
    BotProfileSpecDTO,
    BuilderAuthorityDTO,
    CloneAgentRequestDTO,
    CreationVerificationResultDTO,
    OverlapCheckRequestDTO,
    OverlapCheckResponseDTO,
    OverlapVerdictEnum,
    PipelineExecutionStateDTO,
    PipelineStageEnum,
    ReadinessSeverityEnum,
    RollbackRecordDTO,
    SingleAgentCreationRequestDTO,
    TeamCreationRequestDTO,
    VerificationFindingDTO,
)


class BotForgeService:
    """Manages session-isolated agent creation pipelines and safety boundary verification."""

    _instance: Optional[BotForgeService] = None

    def __init__(self) -> None:
        # session_id -> dict of agent_name: BotProfileSpec
        self._agent_stores: Dict[str, Dict[str, BotProfileSpec]] = {}
        # session_id -> dict of cron_id: expression
        self._cron_stores: Dict[str, Dict[str, str]] = {}
        # session_id -> BuilderAuthority
        self._builders: Dict[str, BuilderAuthority] = {}

    @classmethod
    def get_instance(cls) -> BotForgeService:
        """Get or initialize singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        if cls._instance is not None:
            cls._instance._agent_stores.clear()
            cls._instance._cron_stores.clear()
            cls._instance._builders.clear()
        cls._instance = None

    def get_or_create_builder(
        self,
        session_id: str,
        custom_authority: Optional[BuilderAuthorityDTO] = None,
    ) -> BuilderAuthority:
        """Retrieve existing or configure active builder authority for session."""
        if custom_authority:
            builder = BuilderAuthority(
                builder_name=custom_authority.builder_name,
                allowed_tools=list(custom_authority.allowed_tools),
                allowed_skills=list(custom_authority.allowed_skills),
                allowed_mcps=list(custom_authority.allowed_mcps),
                can_create_agents=custom_authority.can_create_agents,
                max_team_members=custom_authority.max_team_members,
            )
            self._builders[session_id] = builder
            return builder

        if session_id not in self._builders:
            # Default authoritative root builder
            self._builders[session_id] = BuilderAuthority(
                builder_name="lead-orchestrator",
                allowed_tools=["file_read", "file_write", "web_search", "bash_exec", "git_status"],
                allowed_skills=["code_review", "data_analysis", "ast_lint", "doc_writer"],
                allowed_mcps=["github", "sqlite", "brave_search"],
                can_create_agents=True,
                max_team_members=8,
            )
        return self._builders[session_id]

    def get_agent_store(self, session_id: str) -> Dict[str, BotProfileSpec]:
        """Get agent store for session."""
        if session_id not in self._agent_stores:
            self._agent_stores[session_id] = {}
        return self._agent_stores[session_id]

    def get_cron_store(self, session_id: str) -> Dict[str, str]:
        """Get cron routine store for session."""
        if session_id not in self._cron_stores:
            self._cron_stores[session_id] = {}
        return self._cron_stores[session_id]

    def _get_pipeline(
        self,
        session_id: str,
        custom_authority: Optional[BuilderAuthorityDTO] = None,
    ) -> VerifiedCreationPipeline:
        """Instantiate pipeline backed by session-isolated memory stores."""
        builder = self.get_or_create_builder(session_id, custom_authority)
        agent_store = self.get_agent_store(session_id)
        cron_store = self.get_cron_store(session_id)
        return VerifiedCreationPipeline(
            builder=builder,
            agent_store=agent_store,
            cron_store=cron_store,
        )

    def check_overlap(
        self,
        session_id: str,
        req: OverlapCheckRequestDTO,
    ) -> OverlapCheckResponseDTO:
        """Analyze proposed agent name and duty against existing session catalog."""
        agent_store = self.get_agent_store(session_id)
        existing_list = list(agent_store.values())
        verdict, conflict, rec = BuilderSafetyEnvelope.detect_name_and_duty_overlap(
            candidate_name=req.candidate_name,
            candidate_purpose=req.candidate_purpose,
            existing_agents=existing_list,
            duty_similarity_threshold=req.duty_similarity_threshold,
        )
        return OverlapCheckResponseDTO(
            verdict=OverlapVerdictEnum(verdict.value),
            conflicting_name=conflict,
            recommendation=rec,
        )

    def create_agent(
        self,
        session_id: str,
        req: SingleAgentCreationRequestDTO,
        custom_authority: Optional[BuilderAuthorityDTO] = None,
    ) -> PipelineExecutionStateDTO:
        """Run deterministic creation pipeline for a single agent."""
        pipeline = self._get_pipeline(session_id, custom_authority)
        spec = self._dto_to_spec(req.spec)
        state = pipeline.create_single_agent(
            spec=spec,
            is_sandbox=req.is_sandbox,
            allow_overlap=req.allow_overlap,
        )
        return self._state_to_dto(state)

    def create_team(
        self,
        session_id: str,
        req: TeamCreationRequestDTO,
        custom_authority: Optional[BuilderAuthorityDTO] = None,
    ) -> PipelineExecutionStateDTO:
        """Run deterministic creation pipeline for a full team squad."""
        pipeline = self._get_pipeline(session_id, custom_authority)
        lead_spec = self._dto_to_spec(req.team_spec.lead)
        specialist_specs = [self._dto_to_spec(s) for s in req.team_spec.specialists]
        team_spec = TeamCompositionSpec(
            team_name=req.team_spec.team_name,
            team_purpose=req.team_spec.team_purpose,
            lead=lead_spec,
            specialists=specialist_specs,
        )
        state = pipeline.create_team(
            team_spec=team_spec,
            is_sandbox=req.is_sandbox,
            allow_overlap=req.allow_overlap,
        )
        return self._state_to_dto(state)

    def clone_agent(
        self,
        session_id: str,
        req: CloneAgentRequestDTO,
    ) -> PipelineExecutionStateDTO:
        """Clone an existing agent with prompt identity sanitization."""
        agent_store = self.get_agent_store(session_id)
        if req.source_name not in agent_store:
            raise ValueError(f"Source agent '{req.source_name}' not found in session '{session_id}'.")

        source = agent_store[req.source_name]
        sanitized_prompt = BuilderSafetyEnvelope.sanitize_clone_prompt(
            original_name=source.name,
            new_name=req.target_name,
            system_prompt=source.system_prompt,
            original_display_name=source.display_name,
        )
        if req.custom_instructions:
            sanitized_prompt = f"{sanitized_prompt}\n\n[Custom Instructions]\n{req.custom_instructions}"

        cloned_spec = BotProfileSpec(
            name=req.target_name,
            display_name=req.new_display_name or f"{req.target_name.capitalize()}",
            description=source.description,
            system_prompt=sanitized_prompt,
            model=source.model,
            tools=list(source.tools),
            skills=list(source.skills),
            mcp_servers=list(source.mcp_servers),
            cron_routines=list(source.cron_routines),
            role_type=source.role_type,
        )

        pipeline = self._get_pipeline(session_id)
        state = pipeline.create_single_agent(
            spec=cloned_spec,
            allow_overlap=req.allow_overlap,
        )
        return self._state_to_dto(state)

    def list_agents(self, session_id: str) -> BotForgeCatalogResponseDTO:
        """List all provisioned agents in session."""
        agent_store = self.get_agent_store(session_id)
        agents_dto = [self._spec_to_dto(spec) for spec in agent_store.values()]
        return BotForgeCatalogResponseDTO(
            session_id=session_id,
            total_agents=len(agents_dto),
            agents=agents_dto,
        )

    def get_agent(self, session_id: str, name: str) -> Optional[BotProfileSpecDTO]:
        """Get an individual agent by name."""
        agent_store = self.get_agent_store(session_id)
        spec = agent_store.get(name)
        return self._spec_to_dto(spec) if spec else None

    def delete_agent(self, session_id: str, name: str) -> bool:
        """Delete an existing agent from session store."""
        agent_store = self.get_agent_store(session_id)
        if name in agent_store:
            agent_store.pop(name, None)
            return True
        return False

    @staticmethod
    def _dto_to_spec(dto: BotProfileSpecDTO) -> BotProfileSpec:
        return BotProfileSpec(
            name=dto.name,
            display_name=dto.display_name,
            description=dto.description,
            system_prompt=dto.system_prompt,
            model=dto.model,
            tools=list(dto.tools),
            skills=list(dto.skills),
            mcp_servers=list(dto.mcp_servers),
            cron_routines=list(dto.cron_routines),
            role_type=dto.role_type,
        )

    @staticmethod
    def _spec_to_dto(spec: BotProfileSpec) -> BotProfileSpecDTO:
        return BotProfileSpecDTO(
            name=spec.name,
            display_name=spec.display_name,
            description=spec.description,
            system_prompt=spec.system_prompt,
            model=spec.model,
            tools=list(spec.tools),
            skills=list(spec.skills),
            mcp_servers=list(spec.mcp_servers),
            cron_routines=list(spec.cron_routines),
            role_type=spec.role_type,
        )

    @staticmethod
    def _state_to_dto(state: PipelineExecutionState) -> PipelineExecutionStateDTO:
        rollback_dto: Optional[RollbackRecordDTO] = None
        if state.rollback:
            rollback_dto = RollbackRecordDTO(
                target_name=state.rollback.target_name,
                reason=state.rollback.reason,
                reverted_agents=list(state.rollback.reverted_agents),
                reverted_crons=list(state.rollback.reverted_crons),
                timestamp=state.rollback.timestamp,
            )

        verification_dto: Optional[CreationVerificationResultDTO] = None
        if state.verification:
            findings_dto = [
                VerificationFindingDTO(
                    code=f.code,
                    severity=ReadinessSeverityEnum(f.severity.value),
                    message=f.message,
                    next_action=f.next_action,
                )
                for f in state.verification.findings
            ]
            verification_dto = CreationVerificationResultDTO(
                passed=state.verification.passed,
                severity=ReadinessSeverityEnum(state.verification.severity.value),
                findings=findings_dto,
                observed_state={str(k): str(v) for k, v in state.verification.observed_state.items()},
            )

        return PipelineExecutionStateDTO(
            pipeline_id=state.pipeline_id,
            target_name=state.target_name,
            is_team=state.is_team,
            current_stage=PipelineStageEnum(state.current_stage.value),
            created_agents=list(state.created_agents),
            rollback=rollback_dto,
            verification=verification_dto,
            error=state.error,
            started_at=state.started_at,
            completed_at=state.completed_at,
        )


def get_bot_forge_service() -> BotForgeService:
    """FastAPI dependency provider."""
    return BotForgeService.get_instance()
