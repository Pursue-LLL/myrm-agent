"""[INPUT] AgentRegisterRequest, RecordErrorRequest, and target capability parameters.
[OUTPUT] AgentRosterResponse, ResolveCapabilityResponse, and AgentScopedErrorDTO.
[POS] Service orchestrating AgentOwnedOperationsFabric per session.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.agent_operations import (
    AgentOwnedExecutionContext,
    AgentOwnedOperationsFabric,
    AgentProviderConfig,
    AgentScopedError,
)

from app.schemas.agent_operations import (
    AgentRegisterRequest,
    AgentRosterEntryDTO,
    AgentRosterResponse,
    AgentScopedErrorDTO,
    RecordErrorRequest,
    ResolveCapabilityResponse,
)

logger = logging.getLogger(__name__)


class AgentOperationsService:
    """Service layer managing agent-owned operational fabrics across sessions."""

    def __init__(self) -> None:
        # Default shared fabric + session-specific fabrics
        self._default_fabric = AgentOwnedOperationsFabric()
        self._session_fabrics: Dict[str, AgentOwnedOperationsFabric] = {}

    def _get_fabric(self, session_id: Optional[str] = None) -> AgentOwnedOperationsFabric:
        if not session_id:
            return self._default_fabric
        if session_id not in self._session_fabrics:
            self._session_fabrics[session_id] = AgentOwnedOperationsFabric()
        return self._session_fabrics[session_id]

    def register_agent(self, req: AgentRegisterRequest) -> AgentRosterEntryDTO:
        """Register an agent with owned provider configuration and allowlist."""
        fabric = self._get_fabric(req.session_id)
        provider_cfg = AgentProviderConfig(
            provider_name=req.provider_config.provider_name,
            model_name=req.provider_config.model_name,
            api_base=req.provider_config.api_base,
            temperature=req.provider_config.temperature,
            max_tokens=req.provider_config.max_tokens,
            timeout_seconds=req.provider_config.timeout_seconds,
        )
        context = AgentOwnedExecutionContext(
            agent_id=req.agent_id,
            role=req.role,
            session_id=req.session_id,
            parent_agent_id=req.parent_agent_id,
            provider_config=provider_cfg,
            capabilities=req.capabilities,
            allowlist=req.allowlist,
        )
        fabric.register_agent(context)
        entry = context.to_roster_entry()
        return AgentRosterEntryDTO(
            agent_id=entry.agent_id,
            role=entry.role,
            parent_agent_id=entry.parent_agent_id,
            session_id=entry.session_id,
            provider_model=entry.provider_model,
            capabilities=entry.capabilities,
            allowlist=entry.allowlist,
            error_count=entry.error_count,
            is_healthy=entry.is_healthy,
        )

    def get_roster(self, session_id: Optional[str] = None) -> AgentRosterResponse:
        """Fetch the list-form roster for a specific session or globally."""
        fabric = self._get_fabric(session_id)
        entries = fabric.get_roster(session_id=session_id)
        dtos: List[AgentRosterEntryDTO] = [
            AgentRosterEntryDTO(
                agent_id=e.agent_id,
                role=e.role,
                parent_agent_id=e.parent_agent_id,
                session_id=e.session_id,
                provider_model=e.provider_model,
                capabilities=e.capabilities,
                allowlist=e.allowlist,
                error_count=e.error_count,
                is_healthy=e.is_healthy,
            )
            for e in entries
        ]
        return AgentRosterResponse(agents=dtos, total_count=len(dtos))

    def resolve_capability(
        self,
        agent_id: str,
        target_capability: str,
        session_id: Optional[str] = None,
    ) -> ResolveCapabilityResponse:
        """Resolve whether target capability is permitted within the agent's owned allowlist."""
        fabric = self._get_fabric(session_id)
        is_allowed = fabric.resolve_capability(agent_id, target_capability)
        return ResolveCapabilityResponse(
            agent_id=agent_id,
            target_capability=target_capability,
            is_allowed=is_allowed,
        )

    def record_error(
        self,
        agent_id: str,
        req: RecordErrorRequest,
        session_id: Optional[str] = None,
    ) -> AgentScopedErrorDTO:
        """Inject or record an isolated error into an agent's private error stack."""
        fabric = self._get_fabric(session_id)
        scoped_err = fabric.record_agent_error(
            agent_id=agent_id,
            operation=req.operation,
            error_type=req.error_type,
            message=req.message,
            fatal=req.fatal,
            context=req.context or {},
        )
        return self._to_error_dto(scoped_err)

    def get_agent_errors(
        self,
        agent_id: str,
        session_id: Optional[str] = None,
    ) -> List[AgentScopedErrorDTO]:
        """Fetch all errors isolated in the agent's own error stack."""
        fabric = self._get_fabric(session_id)
        errors = fabric.get_agent_errors(agent_id)
        return [self._to_error_dto(err) for err in errors]

    def clear_agent_errors(
        self,
        agent_id: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Clear errors for a specific agent."""
        fabric = self._get_fabric(session_id)
        fabric.clear_agent_errors(agent_id)

    @staticmethod
    def _to_error_dto(err: AgentScopedError) -> AgentScopedErrorDTO:
        return AgentScopedErrorDTO(
            error_id=err.error_id,
            agent_id=err.agent_id,
            operation=err.operation,
            error_type=err.error_type,
            message=err.message,
            timestamp=err.timestamp,
            fatal=err.fatal,
            context=err.context,
        )


_instance: Optional[AgentOperationsService] = None


def get_agent_operations_service() -> AgentOperationsService:
    """Singleton getter for AgentOperationsService."""
    global _instance
    if _instance is None:
        _instance = AgentOperationsService()
    return _instance
