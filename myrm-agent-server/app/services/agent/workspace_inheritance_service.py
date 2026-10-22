"""Service layer for Subagent Workspace Context Inheritance & Prompt Enrichment (Item 56).

[INPUT]
- InspectWorkspaceRulesRequest, EnrichChildPromptRequest.

[OUTPUT]
- InspectWorkspaceRulesResponse, EnrichChildPromptResponse, InheritanceAuditHistoryResponse.

[POS]
- Coordinates rule discovery along the priority chain (.rules > AGENTS.md > README.md),
  budget capping, compact differential summarization, and prompt enrichment.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.schemas.workspace_inheritance import (
    ContextRuleSnippetDTO,
    ContextSourceTypeEnum,
    EnrichChildPromptRequest,
    EnrichChildPromptResponse,
    InheritanceAuditHistoryResponse,
    InheritanceAuditRecordDTO,
    InspectWorkspaceRulesRequest,
    InspectWorkspaceRulesResponse,
    RulePriorityEnum,
    SubagentRoleEnum,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.sub_agents.workspace_inheritance import (
        ContextRuleSnippet,
        InheritanceAuditRecord,
    )

logger = logging.getLogger(__name__)


class WorkspaceInheritanceService:
    """Manages workspace context discovery, token budgeting, and subagent prompt enrichment."""

    def __init__(self) -> None:
        from myrm_agent_harness.agent.sub_agents.workspace_inheritance import (
            SubagentWorkspaceContextEnricher,
            WorkspaceInheritanceConfig,
        )

        self._config = WorkspaceInheritanceConfig(max_context_tokens=2000)
        self._enricher = SubagentWorkspaceContextEnricher(self._config)

    def _convert_snippet_to_dto(self, snippet: ContextRuleSnippet) -> ContextRuleSnippetDTO:
        return ContextRuleSnippetDTO(
            source_type=ContextSourceTypeEnum(snippet.source_type.value),
            file_path=snippet.file_path,
            priority=RulePriorityEnum(snippet.priority.value),
            title=snippet.title,
            content=snippet.content,
            token_count=snippet.token_count,
        )

    def _convert_audit_to_dto(self, record: InheritanceAuditRecord) -> InheritanceAuditRecordDTO:
        return InheritanceAuditRecordDTO(
            audit_id=record.audit_id,
            workspace_root=record.workspace_root,
            subagent_role=SubagentRoleEnum(record.subagent_role.value),
            injected_tokens=record.injected_tokens,
            compacted=record.compacted,
            timestamp=record.timestamp,
            matched_files=list(record.matched_files),
        )

    def inspect_workspace_rules(self, req: InspectWorkspaceRulesRequest) -> InspectWorkspaceRulesResponse:
        """Inspect and parse all available context rules in the workspace following priority chain."""
        snippets = self._enricher.discover_context_snippets(req.workspace_root)
        dto_snippets = [self._convert_snippet_to_dto(s) for s in snippets]
        total_tokens = sum(s.token_count for s in dto_snippets)

        return InspectWorkspaceRulesResponse(
            workspace_root=req.workspace_root,
            snippets=dto_snippets,
            total_snippets=len(dto_snippets),
            estimated_total_tokens=total_tokens,
        )

    def enrich_child_prompt(self, req: EnrichChildPromptRequest) -> EnrichChildPromptResponse:
        """Enrich subagent base prompt with workspace invariants under token budget capping."""
        from myrm_agent_harness.agent.sub_agents.workspace_inheritance import SubagentRole

        role_enum = SubagentRole(req.role.value)
        self._enricher.config.max_context_tokens = req.max_context_tokens

        res = self._enricher.enrich_child_system_prompt(
            base_prompt=req.base_prompt,
            workspace_root=req.workspace_root,
            role=role_enum,
        )

        return EnrichChildPromptResponse(
            original_prompt=res.original_prompt,
            enriched_prompt=res.enriched_prompt,
            injected_token_count=res.injected_token_count,
            is_compacted=res.is_compacted,
            matched_sources=list(res.matched_sources),
            applied_snippets=[self._convert_snippet_to_dto(s) for s in res.applied_snippets],
        )

    def get_audit_history(self) -> InheritanceAuditHistoryResponse:
        """Fetch historical audit log of prompt enrichments."""
        records = self._enricher.get_audit_history()
        dto_records = [self._convert_audit_to_dto(r) for r in records]
        return InheritanceAuditHistoryResponse(
            records=dto_records,
            total=len(dto_records),
        )


_instance: WorkspaceInheritanceService | None = None


def get_workspace_inheritance_service() -> WorkspaceInheritanceService:
    """Retrieve the singleton instance of WorkspaceInheritanceService."""
    global _instance
    if _instance is None:
        _instance = WorkspaceInheritanceService()
    return _instance
