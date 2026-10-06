"""Service managing Agentic Transaction Safety Pillars and Tri-Flow Isolation.

[INPUT]
- myrm_agent_harness.core.security.tri_flow_isolation::TriFlowGuard, EndpointValidator, ZeroPrintCredentialVault

[OUTPUT]
- TriFlowSafetyService, get_tri_flow_safety_service

[POS]
Business service coordinating physical workflow role boundaries, validation, and redaction.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.tri_flow_isolation import (
    DocumentedEndpointSpec,
    EndpointValidationResult,
    EndpointValidator,
    ToolRoleContract,
    TriFlowGuard,
    TriFlowValidationResult,
    WorkflowRole,
    ZeroPrintCredentialVault,
    ZeroPrintSanitizationResult,
)


class TriFlowSafetyService:
    """Coordinates physical workflow role boundaries, zero-guesswork validation,

    and zero-print credential sanitization.
    """

    def __init__(self, enforce_strict_endpoints: bool = True) -> None:
        self._guard = TriFlowGuard()
        self._validator = EndpointValidator(enforce_strict=enforce_strict_endpoints)
        self._vault = ZeroPrintCredentialVault()
        self._seed_default_contracts()

    def _seed_default_contracts(self) -> None:
        """Seed initial default tool contracts for standard tri-flow roles."""
        self._guard.register_tool(
            ToolRoleContract(
                tool_name="web_search",
                allowed_roles=("read_only", "buyer", "seller"),
            )
        )
        self._guard.register_tool(
            ToolRoleContract(
                tool_name="read_file",
                allowed_roles=("read_only", "buyer", "seller"),
            )
        )
        self._guard.register_tool(
            ToolRoleContract(
                tool_name="get_quote",
                allowed_roles=("read_only", "buyer", "seller"),
            )
        )
        self._guard.register_tool(
            ToolRoleContract(
                tool_name="create_order",
                allowed_roles=("buyer",),
                is_financial_transaction=True,
                financial_threshold=50.0,
            )
        )
        self._guard.register_tool(
            ToolRoleContract(
                tool_name="seller_payout",
                allowed_roles=("seller",),
                is_financial_transaction=True,
                requires_hitl_confirmation=True,
            )
        )

    def register_tool_contract(self, contract: ToolRoleContract) -> None:
        """Register custom tool role contract."""
        self._guard.register_tool(contract)

    def validate_tool_call(
        self,
        role: WorkflowRole,
        tool_name: str,
        amount: float = 0.0,
        hitl_confirmed: bool = False,
    ) -> TriFlowValidationResult:
        """Validate if tool call conforms to active workflow role constraints."""
        return self._guard.validate_tool_call(
            current_role=role,
            tool_name=tool_name,
            amount=amount,
            hitl_confirmed=hitl_confirmed,
        )

    def register_endpoint_spec(self, spec: DocumentedEndpointSpec) -> None:
        """Register documented endpoint specification."""
        self._validator.register_endpoint(spec)

    def validate_endpoint_call(
        self,
        service: str,
        path: str,
        method: str = "GET",
        function_name: str | None = None,
    ) -> EndpointValidationResult:
        """Inspect endpoint call to prevent blind probing or guessing."""
        return self._validator.validate_endpoint_call(
            service=service,
            path=path,
            method=method,
            function_name=function_name,
        )

    def sanitize_text(self, text: str) -> ZeroPrintSanitizationResult:
        """Scrub private keys and API tokens from logs, STDOUT, and prompt text."""
        return self._vault.sanitize_text(text)


_singleton_tri_flow_service: TriFlowSafetyService | None = None


def get_tri_flow_safety_service() -> TriFlowSafetyService:
    """Retrieve or initialize singleton TriFlowSafetyService."""
    global _singleton_tri_flow_service
    if _singleton_tri_flow_service is None:
        _singleton_tri_flow_service = TriFlowSafetyService()
    return _singleton_tri_flow_service
