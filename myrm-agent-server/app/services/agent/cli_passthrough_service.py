"""Service layer for External CLI Subagent Adapter Bridge and Subscription Passthrough."""

from typing import Dict, List, Optional

from myrm_agent_harness.agent.sub_agents.cli_passthrough import (
    CliExecutionResult,
    CliPassthroughScheduler,
    CliProfileBundleRegistry,
    CliSubagentType,
    CliTaskDelegationRequest,
    DelegationPrivacyDisclosure,
    SensitivityLevel,
)

from app.schemas.cli_passthrough import (
    AuditRecordsResponse,
    BundlesListResponse,
    CliDelegationExecuteRequest,
    CliExecutionResultDTO,
    CliProfileBundleDTO,
    CliSubagentTypeEnum,
    PrivacyDisclosureCreateRequest,
    PrivacyDisclosureDTO,
    SensitivityLevelEnum,
    SubscriptionStatusEnum,
)


class CliPassthroughService:
    """Orchestrates discoverable CLI bundles, privacy disclosure gates, and data accounting."""

    def __init__(self, default_workspace_root: str = "/workspace") -> None:
        self.registry = CliProfileBundleRegistry(default_workspace_root=default_workspace_root)
        self.scheduler = CliPassthroughScheduler(registry=self.registry)
        self._disclosures: Dict[str, DelegationPrivacyDisclosure] = {}

    def list_bundles(self) -> BundlesListResponse:
        """List all available CLI subagent bundles and probe environment."""
        bundles = self.registry.list_bundles()
        probes = self.registry.probe_environment()

        dto_list: List[CliProfileBundleDTO] = []
        installed_count = 0

        for b in bundles:
            is_inst = probes.get(b.bundle_id, b.is_installed)
            if is_inst:
                installed_count += 1
            dto_list.append(
                CliProfileBundleDTO(
                    bundle_id=b.bundle_id,
                    cli_type=CliSubagentTypeEnum(b.cli_type.value),
                    display_name=b.display_name,
                    executable_name=b.executable_name,
                    subscription_status=SubscriptionStatusEnum(b.subscription_status.value),
                    account_email_masked=b.account_email_masked,
                    default_flags=list(b.default_flags),
                    timeout_seconds=b.timeout_seconds,
                    allowed_workspace_root=b.allowed_workspace_root,
                    is_installed=is_inst,
                )
            )

        return BundlesListResponse(
            bundles=dto_list,
            total_bundles=len(dto_list),
            probe_installed_count=installed_count,
        )

    def create_privacy_disclosure(
        self, req: PrivacyDisclosureCreateRequest
    ) -> PrivacyDisclosureDTO:
        """Issue a transparent privacy disclosure describing context transfer to third-party vendor."""
        harness_cli = CliSubagentType(req.cli_type.value)
        harness_sensitivity = SensitivityLevel(req.sensitivity_level.value)

        disclosure = self.scheduler.create_privacy_disclosure(
            cli_type=harness_cli,
            context_summary=req.context_summary,
            sensitivity_level=harness_sensitivity,
        )
        self._disclosures[disclosure.disclosure_id] = disclosure

        return self._to_disclosure_dto(disclosure)

    def acknowledge_privacy_disclosure(
        self, disclosure_id: str, user_acknowledged: bool = True
    ) -> PrivacyDisclosureDTO:
        """Record explicit user acknowledgment of data flow terms before delegation."""
        disclosure = self._disclosures.get(disclosure_id)
        if not disclosure:
            raise KeyError(f"Disclosure '{disclosure_id}' not found.")
        disclosure.user_acknowledged = user_acknowledged
        return self._to_disclosure_dto(disclosure)

    def execute_delegated_task(
        self, req: CliDelegationExecuteRequest
    ) -> CliExecutionResultDTO:
        """Execute a headless external CLI task with privacy disclosure gate and workspace check."""
        disclosure = self._disclosures.get(req.disclosure_id)
        if not disclosure:
            raise KeyError(f"Disclosure '{req.disclosure_id}' not found.")

        harness_req = CliTaskDelegationRequest(
            task_id=req.task_id,
            bundle_id=req.bundle_id,
            instruction=req.instruction,
            workspace_path=req.workspace_path,
            disclosure=disclosure,
            context_files=list(req.context_files),
            dry_run=req.dry_run,
        )

        result = self.scheduler.execute_delegated_task(harness_req)
        return self._to_result_dto(result)

    def list_audit_records(self) -> AuditRecordsResponse:
        """Retrieve all tamper-proof egress accounting records."""
        records = self.scheduler.list_audit_records()
        dto_list = [self._to_result_dto(r) for r in records]
        total_tokens = sum(r.tokens_saved_estimate for r in dto_list)

        return AuditRecordsResponse(
            records=dto_list,
            total_records=len(dto_list),
            total_tokens_saved=total_tokens,
        )

    def reset(self) -> None:
        """Reset service state for test isolation."""
        self._disclosures.clear()
        self.scheduler.clear_audit_records()

    def _to_disclosure_dto(self, d: DelegationPrivacyDisclosure) -> PrivacyDisclosureDTO:
        return PrivacyDisclosureDTO(
            disclosure_id=d.disclosure_id,
            cli_type=CliSubagentTypeEnum(d.cli_type.value),
            vendor_name=d.vendor_name,
            data_handling_terms_url=d.data_handling_terms_url,
            context_summary=d.context_summary,
            sensitivity_level=SensitivityLevelEnum(d.sensitivity_level.value),
            user_acknowledged=d.user_acknowledged,
            created_at_utc=d.created_at_utc,
        )

    def _to_result_dto(self, r: CliExecutionResult) -> CliExecutionResultDTO:
        return CliExecutionResultDTO(
            task_id=r.task_id,
            bundle_id=r.bundle_id,
            exit_code=r.exit_code,
            diff_output=r.diff_output,
            structured_summary=r.structured_summary,
            tokens_saved_estimate=r.tokens_saved_estimate,
            tamper_proof_audit_hash=r.tamper_proof_audit_hash,
            egress_accounting_id=r.egress_accounting_id,
            completed_at_utc=r.completed_at_utc,
            file_changes_count=r.file_changes_count,
        )


_GLOBAL_SERVICE: Optional[CliPassthroughService] = None


def get_cli_passthrough_service() -> CliPassthroughService:
    """Retrieve singleton instance of CliPassthroughService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = CliPassthroughService()
    return _GLOBAL_SERVICE
