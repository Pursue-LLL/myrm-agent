"""FastAPI router for Docker Sandbox 8-Flag Physical Hardening and Host Vault-Proxy Suite.

[INPUT]
fastapi::APIRouter, status
app.schemas.docker_sandbox_hardening::BuildRunArgsRequest, HardenedDockerCommandResponse, RegisterVaultCredentialRequest
app.services.security.docker_sandbox_hardening_service::DockerSandboxHardeningService

[OUTPUT]
router: APIRouter instance exposing /docker-sandbox-hardening endpoints.

[POS]
Docker 沙箱物理加固与 Vault-Proxy 路由层。暴露 8 标志参数构建、凭证安全中继与沙箱状态校验端点。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.docker_sandbox_hardening import (
    BuildRunArgsRequest,
    CheckEnvLeakRequest,
    CheckEnvLeakResponse,
    HardenedDockerCommandResponse,
    LazyProvisionResponse,
    RegisterVaultCredentialRequest,
    VaultCredentialMetadataResponse,
    VaultProxyRelayRequest,
    VaultProxyRelayResponse,
    VerifyFlagsRequest,
    VerifyFlagsResponse,
)
from app.services.security.docker_sandbox_hardening_service import (
    DockerSandboxHardeningService,
)

router = APIRouter(
    prefix="/docker-sandbox-hardening",
    tags=["Docker Sandbox Hardening Security"],
)


@router.post(
    "/build-args",
    response_model=HardenedDockerCommandResponse,
    status_code=status.HTTP_200_OK,
    summary="Build hardened Docker run arguments complying with 8-flag matrix",
)
def build_run_args(
    request: BuildRunArgsRequest,
) -> HardenedDockerCommandResponse:
    """Build hardened Docker run CLI argument sequence."""
    service = DockerSandboxHardeningService.get_instance()
    return service.build_run_args(request)


@router.post(
    "/verify-flags",
    response_model=VerifyFlagsResponse,
    status_code=status.HTTP_200_OK,
    summary="Audit arbitrary Docker run arguments for 8 physical hardening flags",
)
def verify_flags(
    request: VerifyFlagsRequest,
) -> VerifyFlagsResponse:
    """Verify presence of all 8 physical security flags."""
    service = DockerSandboxHardeningService.get_instance()
    return service.verify_flags(request)


@router.post(
    "/check-env-leak",
    response_model=CheckEnvLeakResponse,
    status_code=status.HTTP_200_OK,
    summary="Check environment parameters for plaintext API tokens or secrets",
)
def check_env_leak(
    request: CheckEnvLeakRequest,
) -> CheckEnvLeakResponse:
    """Audit environment parameters for credential leakage."""
    service = DockerSandboxHardeningService.get_instance()
    return service.check_env_leak(request)


@router.post(
    "/vault/credentials",
    response_model=VaultCredentialMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register sensitive credential into host vault",
)
def register_vault_credential(
    request: RegisterVaultCredentialRequest,
) -> VaultCredentialMetadataResponse:
    """Register credential in host vault."""
    service = DockerSandboxHardeningService.get_instance()
    return service.register_credential(request)


@router.get(
    "/vault/credentials",
    response_model=list[VaultCredentialMetadataResponse],
    summary="List all registered vault credentials with redacted values",
)
def list_vault_credentials() -> list[VaultCredentialMetadataResponse]:
    """List host vault credentials."""
    service = DockerSandboxHardeningService.get_instance()
    return service.list_credentials()


@router.post(
    "/vault/relay",
    response_model=VaultProxyRelayResponse,
    summary="Relay sandbox request through host vault proxy with domain vetting",
)
def relay_outbound_request(
    request: VaultProxyRelayRequest,
) -> VaultProxyRelayResponse:
    """Process outbound request using host-side credential injection."""
    service = DockerSandboxHardeningService.get_instance()
    return service.relay_outbound_request(request)


@router.post(
    "/lifecycle/provision",
    response_model=LazyProvisionResponse,
    summary="Lazily provision hardened sandbox container on demand",
)
def provision_sandbox(
    image: str = "ghcr.io/myrm-ai/sandbox-runtime:latest",
) -> LazyProvisionResponse:
    """Ensure sandbox is dynamically provisioned."""
    service = DockerSandboxHardeningService.get_instance()
    return service.ensure_provisioned(image=image)


@router.post(
    "/lifecycle/dispose",
    response_model=LazyProvisionResponse,
    summary="Dispose active sandbox container cleanly",
)
def dispose_sandbox() -> LazyProvisionResponse:
    """Dispose active sandbox container."""
    service = DockerSandboxHardeningService.get_instance()
    return service.dispose_sandbox()


@router.get(
    "/lifecycle/status",
    response_model=LazyProvisionResponse,
    summary="Query current sandbox lifecycle status",
)
def get_lifecycle_status() -> LazyProvisionResponse:
    """Get current lifecycle status."""
    service = DockerSandboxHardeningService.get_instance()
    return service.get_lifecycle_status()
