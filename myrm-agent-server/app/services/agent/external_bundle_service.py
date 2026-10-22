"""Service layer for Heterogeneous External Agent Adapter and Subagent Bundle Manager."""

from __future__ import annotations

import os
from typing import List, Optional

from myrm_agent_harness.agent.sub_agents.external_bundle import (
    BatchDispatchTask,
    ExternalAgentBundleRegistry,
    ExternalBundleProfileSpec,
    ExternalSubagentMultiplexer,
    SubagentInstanceRecord,
    SubagentInstanceStatusEnum,
)

from app.schemas.external_bundle import (
    BatchDispatchRequestDTO,
    BatchDispatchResultDTO,
    BundleCatalogResponseDTO,
    ExternalBundleProfileSpecDTO,
    ProbeBundleResponseDTO,
    SingleDispatchRequestDTO,
    SubagentInstanceRecordDTO,
    TerminateInstanceResponseDTO,
)


class ExternalBundleService:
    """Singleton service managing external agent profile bundles and parallel multiplexing."""

    _instance: Optional[ExternalBundleService] = None

    def __init__(self) -> None:
        self.registry = ExternalAgentBundleRegistry()
        self.multiplexer = ExternalSubagentMultiplexer(registry=self.registry)
        # Default workspace base directory
        self._default_workspace_base = "/tmp/myrm-sandbox"

    @classmethod
    def get_instance(cls) -> ExternalBundleService:
        """Retrieve or initialize singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for test isolation."""
        cls._instance = None

    def _resolve_workspace_root(self, session_id: str, custom_override: Optional[str] = None) -> str:
        """Resolve valid workspace directory on disk for session."""
        if custom_override:
            path = os.path.realpath(os.path.abspath(custom_override))
        else:
            path = os.path.realpath(os.path.abspath(f"{self._default_workspace_base}/{session_id}"))
        os.makedirs(path, exist_ok=True)
        return path

    def list_bundles(self) -> BundleCatalogResponseDTO:
        """List all available external agent bundles in registry."""
        bundles = [self._bundle_spec_to_dto(b) for b in self.registry.list_bundles()]
        return BundleCatalogResponseDTO(total_bundles=len(bundles), bundles=bundles)

    def get_bundle(self, bundle_id: str) -> ExternalBundleProfileSpecDTO:
        """Get details for a specific registered bundle."""
        bundle = self.registry.get_bundle(bundle_id)
        return self._bundle_spec_to_dto(bundle)

    def probe_bundle(self, bundle_id: str) -> ProbeBundleResponseDTO:
        """Probe host executable availability for bundle."""
        bundle = self.registry.get_bundle(bundle_id)
        is_installed = self.registry.probe_host_environment(bundle_id)
        return ProbeBundleResponseDTO(
            bundle_id=bundle.bundle_id,
            binary_name=bundle.binary_name,
            is_installed=is_installed,
            version=bundle.version,
        )

    def dispatch_single(
        self,
        session_id: str,
        req: SingleDispatchRequestDTO,
    ) -> SubagentInstanceRecordDTO:
        """Dispatch a single subagent instance asynchronously without blocking."""
        workspace_root = self._resolve_workspace_root(session_id, req.workspace_root)
        task_model = BatchDispatchTask(
            bundle_id=req.task.bundle_id,
            role_label=req.task.role_label,
            task_prompt=req.task.task_prompt,
            target_subdir=req.task.target_subdir,
            timeout_seconds=req.task.timeout_seconds,
        )
        record = self.multiplexer.dispatch_instance(
            session_id=session_id,
            task=task_model,
            workspace_root=workspace_root,
        )
        return self._record_to_dto(record)

    async def dispatch_batch(
        self,
        session_id: str,
        req: BatchDispatchRequestDTO,
    ) -> BatchDispatchResultDTO:
        """Concurrently dispatch multiple external subagent instances in parallel."""
        workspace_root = self._resolve_workspace_root(session_id, req.workspace_root)
        task_models = [
            BatchDispatchTask(
                bundle_id=t.bundle_id,
                role_label=t.role_label,
                task_prompt=t.task_prompt,
                target_subdir=t.target_subdir,
                timeout_seconds=t.timeout_seconds,
            )
            for t in req.tasks
        ]
        batch_result = await self.multiplexer.dispatch_batch(
            session_id=session_id,
            tasks=task_models,
            workspace_root=workspace_root,
        )
        return BatchDispatchResultDTO(
            batch_id=batch_result.batch_id,
            session_id=batch_result.session_id,
            total_dispatched=batch_result.total_dispatched,
            dispatched_instances=[self._record_to_dto(inst) for inst in batch_result.dispatched_instances],
        )

    def list_instances(self, session_id: Optional[str] = None) -> List[SubagentInstanceRecordDTO]:
        """List active and historical subagent instances."""
        instances = self.multiplexer.list_instances(session_id=session_id)
        return [self._record_to_dto(inst) for inst in instances]

    def get_subagent_instance(self, instance_id: str) -> Optional[SubagentInstanceRecordDTO]:
        """Retrieve telemetry record for a specific instance."""
        record = self.multiplexer.get_instance(instance_id)
        return self._record_to_dto(record) if record else None

    def terminate_instance(
        self,
        instance_id: str,
        reason: str = "user_cancelled",
    ) -> TerminateInstanceResponseDTO:
        """Terminate an active subagent instance."""
        record = self.multiplexer.get_instance(instance_id)
        if not record:
            raise ValueError(f"Instance '{instance_id}' not found.")

        terminated = self.multiplexer.terminate_instance(instance_id, reason=reason)
        return TerminateInstanceResponseDTO(
            instance_id=instance_id,
            terminated=terminated,
            status=SubagentInstanceStatusEnum(record.status.value),
            error=record.error,
        )

    @staticmethod
    def _bundle_spec_to_dto(spec: ExternalBundleProfileSpec) -> ExternalBundleProfileSpecDTO:
        return ExternalBundleProfileSpecDTO(
            bundle_id=spec.bundle_id,
            agent_type=spec.agent_type,
            display_name=spec.display_name,
            description=spec.description,
            binary_name=spec.binary_name,
            command_template=spec.command_template,
            capabilities=list(spec.capabilities),
            env_whitelist=list(spec.env_whitelist),
            allowed_roots=list(spec.allowed_roots),
            execution_mode=spec.execution_mode,
            max_concurrency=spec.max_concurrency,
            is_installed=spec.is_installed,
            version=spec.version,
        )

    @staticmethod
    def _record_to_dto(record: SubagentInstanceRecord) -> SubagentInstanceRecordDTO:
        return SubagentInstanceRecordDTO(
            instance_id=record.instance_id,
            bundle_id=record.bundle_id,
            session_id=record.session_id,
            role_label=record.role_label,
            status=record.status,
            pid=record.pid,
            task_prompt=record.task_prompt,
            target_workdir=record.target_workdir,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            exit_code=record.exit_code,
            stdout_chunks=list(record.stdout_chunks),
            artifacts=list(record.artifacts),
            error=record.error,
        )


def get_external_bundle_service() -> ExternalBundleService:
    """FastAPI dependency provider."""
    return ExternalBundleService.get_instance()
