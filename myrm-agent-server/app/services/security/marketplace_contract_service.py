"""Marketplace Manifest Source Pinning & Capability Contract Service.

[INPUT]
- ValidateManifestRequest, EvaluateAdmissionRequest, UpdateAdmissionPolicyRequest.

[OUTPUT]
- ValidateManifestResponse, EvaluateAdmissionResponse, AdmissionPolicyDto.

[POS]
- Server security service. Wraps harness ManifestContractValidator and MarketplaceAdmissionGate
  to enforce immutable source pinning, capability pre-declaration, and org allowlist policies.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.marketplace_contract import (
    AdmissionPolicy,
    CapabilityContract,
    ManifestContractValidator,
    MarketplaceAdmissionGate,
    MarketplaceContractError,
    MarketplaceManifestItem,
    MarketplaceTier,
    PlatformKind,
)

from app.schemas.marketplace_contract import (
    AdmissionPolicyDto,
    AdmissionVerdictDto,
    CapabilityContractDto,
    EvaluateAdmissionRequest,
    EvaluateAdmissionResponse,
    MarketplaceManifestItemDto,
    UpdateAdmissionPolicyRequest,
    ValidateManifestRequest,
    ValidateManifestResponse,
)

logger = logging.getLogger(__name__)


def _to_domain_manifest(dto: MarketplaceManifestItemDto) -> MarketplaceManifestItem:
    caps = CapabilityContract(
        provides_tools=tuple(dto.capabilities.provides_tools),
        provides_hooks=tuple(dto.capabilities.provides_hooks),
        provides_middleware=tuple(dto.capabilities.provides_middleware),
        requires_env=tuple(dto.capabilities.requires_env),
        declared_mcp_servers=tuple(dto.capabilities.declared_mcp_servers),
    )
    platforms = tuple(PlatformKind(p.lower()) for p in dto.platforms)
    return MarketplaceManifestItem(
        package_id=dto.package_id,
        name=dto.name,
        version=dto.version,
        repo_url=dto.repo_url,
        source_sha=dto.source_sha,
        tier=MarketplaceTier(dto.tier.upper()),
        requires_host=dto.requires_host,
        platforms=platforms,
        capabilities=caps,
        publisher=dto.publisher,
    )


def _to_dto_manifest(domain: MarketplaceManifestItem) -> MarketplaceManifestItemDto:
    caps_dto = CapabilityContractDto(
        provides_tools=list(domain.capabilities.provides_tools),
        provides_hooks=list(domain.capabilities.provides_hooks),
        provides_middleware=list(domain.capabilities.provides_middleware),
        requires_env=list(domain.capabilities.requires_env),
        declared_mcp_servers=list(domain.capabilities.declared_mcp_servers),
    )
    return MarketplaceManifestItemDto(
        package_id=domain.package_id,
        name=domain.name,
        version=domain.version,
        repo_url=domain.repo_url,
        source_sha=domain.source_sha,
        tier=domain.tier.value,
        requires_host=domain.requires_host,
        platforms=[p.value for p in domain.platforms],
        capabilities=caps_dto,
        publisher=domain.publisher,
    )


def _to_domain_policy(dto: AdmissionPolicyDto) -> AdmissionPolicy:
    tiers = tuple(MarketplaceTier(t.upper()) for t in dto.allowed_tiers)
    return AdmissionPolicy(
        allowed_sources=tuple(dto.allowed_sources),
        allowed_tiers=tiers,
        disallowed_capabilities=tuple(dto.disallowed_capabilities),
        enforce_strict_pinning=dto.enforce_strict_pinning,
    )


def _to_dto_policy(domain: AdmissionPolicy) -> AdmissionPolicyDto:
    return AdmissionPolicyDto(
        allowed_sources=list(domain.allowed_sources),
        allowed_tiers=[t.value for t in domain.allowed_tiers],
        disallowed_capabilities=list(domain.disallowed_capabilities),
        enforce_strict_pinning=domain.enforce_strict_pinning,
    )


class MarketplaceContractService:
    """Service governing marketplace package manifest verification and organization admission."""

    def __init__(self) -> None:
        self._validator = ManifestContractValidator()
        self._policy = AdmissionPolicy(enforce_strict_pinning=True)
        self._gate = MarketplaceAdmissionGate(
            policy=self._policy,
            validator=self._validator,
        )

    def validate_manifest(self, req: ValidateManifestRequest) -> ValidateManifestResponse:
        """Validate package manifest source pinning and platform compatibility."""
        try:
            domain_manifest = _to_domain_manifest(req.manifest)
            self._validator.validate_manifest(domain_manifest)
            target_plat = PlatformKind(req.target_platform.lower())
            supported = ManifestContractValidator.is_platform_supported(
                domain_manifest, target_plat
            )
            return ValidateManifestResponse(
                is_valid=True,
                platform_supported=supported,
                error_message=None,
            )
        except (MarketplaceContractError, ValueError) as exc:
            logger.warning("Manifest validation failed for '%s': %s", req.manifest.package_id, exc)
            return ValidateManifestResponse(
                is_valid=False,
                platform_supported=False,
                error_message=str(exc),
            )

    def evaluate_admission(
        self, req: EvaluateAdmissionRequest
    ) -> EvaluateAdmissionResponse:
        """Evaluate package manifest against active organization admission allowlists."""
        domain_manifest = _to_domain_manifest(req.manifest)
        verdict = self._gate.evaluate_manifest(domain_manifest)

        verdict_dto = AdmissionVerdictDto(
            is_admitted=verdict.is_admitted,
            package_id=verdict.package_id,
            reason=verdict.reason,
            violations=list(verdict.violations),
        )
        return EvaluateAdmissionResponse(
            verdict=verdict_dto,
            is_admitted=verdict.is_admitted,
        )

    def get_policy(self) -> AdmissionPolicyDto:
        """Retrieve current organization admission policy."""
        return _to_dto_policy(self._policy)

    def update_policy(self, req: UpdateAdmissionPolicyRequest) -> AdmissionPolicyDto:
        """Update organization admission policy."""
        self._policy = _to_domain_policy(req.policy)
        self._gate.set_policy(self._policy)
        logger.info("Updated organization marketplace admission policy: %s", self._policy)
        return _to_dto_policy(self._policy)


_service_instance: MarketplaceContractService | None = None


def get_marketplace_contract_service() -> MarketplaceContractService:
    """Obtain or initialize singleton MarketplaceContractService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MarketplaceContractService()
    return _service_instance
