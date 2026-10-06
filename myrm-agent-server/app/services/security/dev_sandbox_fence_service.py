"""Service layer for Zero-Production-Write Dev Sandbox and Synthetic Data Fence.

[INPUT]
- Harness DevSandboxFenceEngine and schema request DTOs.

[OUTPUT]
- DevSandboxFenceService providing sandbox inspection, policy enforcement, and fixture management.

[POS]
Service layer bridging HTTP presentation with harness dev sandbox fence engine.
"""

from __future__ import annotations

import logging
from typing import cast

from myrm_agent_harness.core.security.dev_sandbox_fence import (
    DevExecutionMode,
    DevOperationInspection,
    DevSandboxFenceEngine,
    SyntheticDataFixture,
)

from app.schemas.dev_sandbox_fence import (
    DevPolicyResponse,
    DevViolationAlertResponse,
    InspectDevOperationRequest,
    InspectDevOperationResponse,
    RegisterSyntheticFixtureRequest,
    SyntheticFixtureResponse,
)

logger = logging.getLogger(__name__)


class DevSandboxFenceService:
    """Manages dev sandbox policy enforcement, synthetic data redirection, and violation audits."""

    def __init__(self, engine: DevSandboxFenceEngine | None = None) -> None:
        self.engine = engine or DevSandboxFenceEngine()

    def inspect_operation(
        self, req: InspectDevOperationRequest
    ) -> InspectDevOperationResponse:
        """Evaluate a development operation (SQL, Git branch, File path, or DB connection)."""
        op = DevOperationInspection(
            operation_type=req.operation_type,
            target=req.target,
            payload=req.payload,
            session_id=req.session_id,
        )
        res = self.engine.inspect_operation(op)
        return InspectDevOperationResponse(
            allowed=res.allowed,
            violation_type=res.violation_type.value if res.violation_type else None,
            reason=res.reason,
            substituted_target=res.substituted_target,
        )

    def register_fixture(
        self, req: RegisterSyntheticFixtureRequest
    ) -> SyntheticFixtureResponse:
        """Register an approved synthetic data fixture."""
        fixture = SyntheticDataFixture(
            fixture_id=req.fixture_id,
            database_type=req.database_type,
            read_only_uri=req.read_only_uri,
            sample_count=req.sample_count,
            description=req.description,
        )
        self.engine.synthetic_fence.register_fixture(fixture)
        return SyntheticFixtureResponse(
            fixture_id=fixture.fixture_id,
            database_type=fixture.database_type,
            read_only_uri=fixture.read_only_uri,
            sample_count=fixture.sample_count,
            description=fixture.description,
        )

    def unregister_fixture(self, fixture_id: str) -> bool:
        """Unregister a synthetic data fixture."""
        return self.engine.synthetic_fence.unregister_fixture(fixture_id)

    def list_fixtures(self) -> list[SyntheticFixtureResponse]:
        """List all available synthetic data fixtures."""
        fixtures = self.engine.synthetic_fence.list_fixtures()
        return [
            SyntheticFixtureResponse(
                fixture_id=f.fixture_id,
                database_type=f.database_type,
                read_only_uri=f.read_only_uri,
                sample_count=f.sample_count,
                description=f.description,
            )
            for f in fixtures
        ]

    def get_alerts(
        self, session_id: str | None = None
    ) -> list[DevViolationAlertResponse]:
        """Retrieve security violation alerts."""
        alerts = self.engine.get_alerts(session_id)
        return [
            DevViolationAlertResponse(
                alert_id=a.alert_id,
                session_id=a.session_id,
                operation_type=a.operation_type,
                violation_type=a.violation_type.value,
                reason=a.reason,
                target=a.target,
                timestamp=a.timestamp,
            )
            for a in alerts
        ]

    def clear_alerts(self) -> None:
        """Clear all logged violation alerts."""
        self.engine.clear_alerts()

    def get_policy(self) -> DevPolicyResponse:
        """Query active dev sandbox policy and execution mode."""
        p = self.engine.policy
        return DevPolicyResponse(
            allowed_branch_prefixes=list(p.allowed_branch_prefixes),
            blocked_branches=list(p.blocked_branches),
            allowed_write_directories=list(p.allowed_write_directories),
            blocked_sensitive_patterns=list(p.blocked_sensitive_patterns),
            enforce_synthetic_data=p.enforce_synthetic_data,
            mode=self.engine.mode.value,
        )

    def set_mode(self, mode_str: str) -> str:
        """Set dev sandbox execution environment mode."""
        mode = DevExecutionMode(mode_str)
        self.engine.mode = cast(DevExecutionMode, mode)
        return self.engine.mode.value


_singleton_service: DevSandboxFenceService | None = None


def get_dev_sandbox_fence_service() -> DevSandboxFenceService:
    """Retrieve singleton instance of DevSandboxFenceService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = DevSandboxFenceService()
    return _singleton_service
