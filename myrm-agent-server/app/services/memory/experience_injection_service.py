"""ExperienceInjectionService, get_experience_injection_service.

[POS]
app/services/memory/experience_injection_service.py

[INPUT]
- app.schemas.experience_injection, myrm_agent_harness.toolkits.memory

[OUTPUT]
- ExperienceInjectionService, get_experience_injection_service
"""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    DualNodeFixedCountRetriever,
    ExperienceInjectionConfig,
    ExperienceInjectionEngine,
    ProcedureMemoryEntry,
)

from app.schemas.experience_injection import (
    InjectSkillExperienceRequest,
    InjectSkillExperienceResponseDTO,
    InjectSubagentExperienceRequest,
    InjectSubagentExperienceResponseDTO,
    PreWriteCheckRequest,
    PreWriteCheckResponseDTO,
)

logger = logging.getLogger(__name__)


class ExperienceInjectionService:
    """Application service coordinating precise experience injection across three call sites."""

    def __init__(
        self,
        engine: ExperienceInjectionEngine | None = None,
        retriever: DualNodeFixedCountRetriever | None = None,
    ) -> None:
        if engine is not None:
            self._engine = engine
        else:
            shared_retriever = retriever or DualNodeFixedCountRetriever()
            self._seed_production_experiences(shared_retriever)
            config = ExperienceInjectionConfig(
                agent_memory_enabled=True,
                exp_write_tools_enabled=True,
                max_experiences_per_site=2,
            )
            self._engine = ExperienceInjectionEngine(retriever=shared_retriever, config=config)

    def _seed_production_experiences(self, retriever: DualNodeFixedCountRetriever) -> None:
        """Seed industrial baseline procedure memories."""
        retriever.register(
            ProcedureMemoryEntry(
                entry_id="proc_git_push_safe",
                name="SafeGitBranchPushGuard",
                retrieval_anchor="skill:git_safe_push git push branch production",
                operation_intent="Safely push committed git changes without force-pushing to main",
                preconditions=["Working directory clean", "Unit tests passing"],
                immutable_boundary=["Remote main/master branch history"],
                procedure_steps=["1. Verify git status", "2. Run pre-commit checks", "3. Push branch"],
                write_field_provenance={"commit_hash": "Git rev-parse HEAD"},
                anti_patterns=["Never git push -f to protected main branch"],
                applicability=["git release", "code push"],
                negative_applicability=["local untracked scratchpads"],
            )
        )
        retriever.register(
            ProcedureMemoryEntry(
                entry_id="proc_pre_write_file_guard",
                name="ProtectedPathMutationGuard",
                retrieval_anchor="pre_write:write_file write_file edit_file replace_file_content",
                operation_intent="Enforce immutable boundaries before writing or editing system files",
                preconditions=["Target path is inside the project workspace"],
                immutable_boundary=["/etc", "/var", ".git/objects", "credentials.json"],
                procedure_steps=["1. Canonicalize path", "2. Check immutability", "3. Write safely"],
                write_field_provenance={"audit_id": "UUID4 trace identifier"},
                anti_patterns=["Never overwrite system configuration files"],
                applicability=["file writing", "disk mutation"],
                negative_applicability=["read-only probes"],
            )
        )
        retriever.register(
            ProcedureMemoryEntry(
                entry_id="proc_subagent_task_prep",
                name="SubagentContextHygieneGuideline",
                retrieval_anchor="WorkerAgent subagent delegation subtask execution",
                operation_intent="Ensure delegated subagents run with bounded scopes and clear deliverables",
                preconditions=["Delegated task prompt has clear boundaries"],
                immutable_boundary=["Parent orchestrator global state"],
                procedure_steps=["1. Inject minimal spec", "2. Execute bounded work", "3. Return findings"],
                write_field_provenance={"summary_state": "Subagent handover state"},
                anti_patterns=["Do not spawn unbound background loops"],
                applicability=["subagent spawn", "task delegation"],
                negative_applicability=["monolithic single agent runs"],
            )
        )

    def inject_skill_load(self, req: InjectSkillExperienceRequest) -> InjectSkillExperienceResponseDTO:
        """Site 1: Inject relevant procedure experiences upon loading a skill."""
        result = self._engine.inject_skill_load(
            skill_name=req.skill_name,
            raw_content=req.skill_content,
            agent_id=req.agent_id,
        )
        return InjectSkillExperienceResponseDTO(
            skill_name=req.skill_name,
            status=result.status.value,
            injected_count=len(result.injected_entries),
            enriched_content=result.enriched_content,
            injected_entry_ids=list(result.injected_ids),
        )

    def inject_subagent_spawn(
        self,
        req: InjectSubagentExperienceRequest,
    ) -> InjectSubagentExperienceResponseDTO:
        """Site 2: Inject procedure experiences into subagent prompt before task dispatch."""
        result = self._engine.inject_subagent_spawn(
            subagent_role=req.subagent_role,
            task_prompt=req.task_prompt,
            agent_id=req.agent_id,
        )
        return InjectSubagentExperienceResponseDTO(
            subagent_role=req.subagent_role,
            status=result.status.value,
            injected_count=len(result.injected_entries),
            enriched_prompt=result.enriched_content,
            injected_entry_ids=list(result.injected_ids),
        )

    def pre_write_check(self, req: PreWriteCheckRequest) -> PreWriteCheckResponseDTO:
        """Site 3: Guard mutating tools with immutable boundaries and one-time rollback recommendation."""
        result = self._engine.inject_pre_write(
            tool_name=req.tool_name,
            tool_args=req.tool_args,
            current_context=req.current_context,
            agent_id=req.agent_id,
        )
        return PreWriteCheckResponseDTO(
            tool_name=req.tool_name,
            status=result.status.value,
            rollback_required=result.rollback_required,
            enriched_context=result.enriched_content,
            injected_entry_ids=list(result.injected_ids),
        )

    def reset_message_turn(self) -> None:
        """Reset per-message rollback lock."""
        self._engine.reset_message_turn()


@lru_cache
def get_experience_injection_service() -> ExperienceInjectionService:
    """Singleton provider for ExperienceInjectionService."""
    return ExperienceInjectionService()
