"""[INPUT] schemas/external_agent_bridge.py, myrm_agent_harness.agent.sub_agents.cli_adapter.
[OUTPUT] ExternalAgentBridgeService: Service layer managing external CLI processes, probes, and verifiable receipts.
[POS] Service coordinator bridging FastAPI HTTP endpoints with the Harness ExternalCliAgentAdapter.
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.agent.sub_agents.cli_adapter import (
    ExternalAgentConfig,
    ExternalCliAgentAdapter,
    ProcessExecutionRequest,
    ProcessReceipt,
)

from app.schemas.external_agent_bridge import (
    ExternalAgentConfigDTO,
    ExternalAgentListResponse,
    ExternalAgentProbeResponse,
    ExternalAgentReceiptsResponse,
    ProcessExecutionRequestDTO,
    ProcessReceiptDTO,
    RegisterExternalAgentRequest,
)


class ExternalAgentBridgeService:
    """Service orchestrating heterogeneous external CLI agents and verifiable execution receipts."""

    _instance: ExternalAgentBridgeService | None = None

    def __init__(self, adapter: ExternalCliAgentAdapter | None = None) -> None:
        self._adapter = adapter or ExternalCliAgentAdapter()

    @classmethod
    def get_instance(cls) -> ExternalAgentBridgeService:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _config_to_dto(config: ExternalAgentConfig) -> ExternalAgentConfigDTO:
        return ExternalAgentConfigDTO(
            agent_id=config.agent_id,
            name=config.name,
            kind=config.kind,
            command=config.command,
            args=list(config.args),
            env=dict(config.env),
            cwd=config.cwd,
            max_turns=config.max_turns,
            timeout_seconds=config.timeout_seconds,
            max_budget_usd=config.max_budget_usd,
            expected_model=config.expected_model,
        )

    @staticmethod
    def _receipt_to_dto(receipt: ProcessReceipt) -> ProcessReceiptDTO:
        return ProcessReceiptDTO(
            execution_id=receipt.execution_id,
            agent_id=receipt.agent_id,
            kind=receipt.kind,
            status=receipt.status,
            exit_code=receipt.exit_code,
            duration_ms=receipt.duration_ms,
            stdout_summary=receipt.stdout_summary,
            stderr_summary=receipt.stderr_summary,
            receipt_hash=receipt.receipt_hash,
            created_at=receipt.created_at,
        )

    def register_agent(self, req: RegisterExternalAgentRequest) -> ExternalAgentConfigDTO:
        """Register or update an external CLI agent lane."""
        config = ExternalAgentConfig(
            agent_id=req.agent_id,
            name=req.name,
            kind=req.kind,
            command=req.command,
            args=list(req.args),
            env=dict(req.env),
            cwd=req.cwd,
            timeout_seconds=req.timeout_seconds,
            expected_model=req.expected_model,
        )
        self._adapter.register_agent(config)
        return self._config_to_dto(config)

    def get_agent(self, agent_id: str) -> ExternalAgentConfigDTO | None:
        """Retrieve external agent configuration."""
        config = self._adapter.get_agent(agent_id)
        if not config:
            return None
        return self._config_to_dto(config)

    def list_agents(self) -> ExternalAgentListResponse:
        """List all registered external CLI agent lanes."""
        configs = self._adapter.list_agents()
        dtos = [self._config_to_dto(c) for c in configs]
        return ExternalAgentListResponse(agents=dtos, total=len(dtos))

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent lane."""
        return self._adapter.unregister_agent(agent_id)

    def probe_agent(self, agent_id: str) -> ExternalAgentProbeResponse | None:
        """Probe executable health in the host environment."""
        config = self._adapter.get_agent(agent_id)
        if not config:
            return None
        is_healthy = self._adapter.probe_health(agent_id)
        return ExternalAgentProbeResponse(
            agent_id=agent_id,
            is_healthy=is_healthy,
            command=config.command,
        )

    def execute_task(
        self,
        agent_id: str,
        req: ProcessExecutionRequestDTO,
    ) -> ProcessReceiptDTO:
        """Dispatch a task to the external CLI agent and return a verifiable receipt."""
        execution_id = req.execution_id or f"exec-{uuid.uuid4().hex[:12]}"
        harness_req = ProcessExecutionRequest(
            execution_id=execution_id,
            input_text=req.input_text,
            turn_index=req.turn_index,
            extra_args=list(req.extra_args),
        )
        receipt = self._adapter.execute(agent_id=agent_id, request=harness_req)
        return self._receipt_to_dto(receipt)

    def get_receipts(self, agent_id: str) -> ExternalAgentReceiptsResponse | None:
        """Fetch receipt history for an external agent."""
        if not self._adapter.get_agent(agent_id):
            return None
        receipts = self._adapter.get_receipts(agent_id)
        dtos = [self._receipt_to_dto(r) for r in receipts]
        return ExternalAgentReceiptsResponse(
            agent_id=agent_id,
            receipts=dtos,
            total=len(dtos),
        )
