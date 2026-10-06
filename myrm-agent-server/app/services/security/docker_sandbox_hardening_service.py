"""Service layer for Docker Sandbox 8-Flag Physical Hardening and Host Vault-Proxy Suite.

[INPUT]
myrm_agent_harness.core.security.sandbox_hardening::EightFlagBuilder, EightFlagSandboxConfig, HostVaultProxy
app.schemas.docker_sandbox_hardening::EightFlagConfigRequest, SecretVaultConfig

[OUTPUT]
DockerSandboxHardeningService: Service managing 8-flag Docker command hardening, vault proxy, and lazy lifecycle.

[POS]
Docker 沙箱物理加固与 Vault-Proxy 凭证代理服务层。协调 Harness 物理隔离构建器与沙箱生命周期管理。
"""

from __future__ import annotations

import logging
from typing import ClassVar

from myrm_agent_harness.core.security.sandbox_hardening import (
    EightFlagBuilder,
    EightFlagSandboxConfig,
    HostVaultProxy,
    LazySandboxLifecycleManager,
    NetworkIsolationMode,
    ProvisionStatus,
    VaultProxyRequest,
)

from app.schemas.docker_sandbox_hardening import (
    BuildRunArgsRequest,
    CheckEnvLeakRequest,
    CheckEnvLeakResponse,
    EightFlagConfigRequest,
    HardenedDockerCommandResponse,
    LazyProvisionResponse,
    NetworkIsolationEnum,
    ProvisionStatusEnum,
    RegisterVaultCredentialRequest,
    VaultCredentialMetadataResponse,
    VaultProxyRelayRequest,
    VaultProxyRelayResponse,
    VerifyFlagsRequest,
    VerifyFlagsResponse,
)

logger = logging.getLogger(__name__)


class DockerSandboxHardeningService:
    """Service managing 8-flag Docker command hardening, vault proxy, and lazy lifecycle."""

    _instance: ClassVar[DockerSandboxHardeningService | None] = None

    def __init__(
        self,
        builder: EightFlagBuilder | None = None,
        vault: HostVaultProxy | None = None,
        lifecycle: LazySandboxLifecycleManager | None = None,
    ) -> None:
        self._builder = builder or EightFlagBuilder()
        self._vault = vault or HostVaultProxy()
        self._lifecycle = lifecycle or LazySandboxLifecycleManager(builder=self._builder)

    @classmethod
    def get_instance(cls) -> DockerSandboxHardeningService:
        """Obtain singleton service instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton service instance for test isolation."""
        cls._instance = None

    def _convert_config(
        self, req_cfg: EightFlagConfigRequest | None
    ) -> EightFlagSandboxConfig | None:
        if req_cfg is None:
            return None
        net_mode_map = {
            NetworkIsolationEnum.NONE: NetworkIsolationMode.NONE,
            NetworkIsolationEnum.HOST: NetworkIsolationMode.HOST,
            NetworkIsolationEnum.BRIDGE_RESTRICTED: NetworkIsolationMode.BRIDGE_RESTRICTED,
        }
        return EightFlagSandboxConfig(
            read_only=req_cfg.read_only,
            tmp_size_mb=req_cfg.tmp_size_mb,
            tmp_noexec=req_cfg.tmp_noexec,
            pids_limit=req_cfg.pids_limit,
            cap_drop_all=req_cfg.cap_drop_all,
            no_new_privileges=req_cfg.no_new_privileges,
            user=req_cfg.user,
            network_mode=net_mode_map[req_cfg.network_mode],
            memory_limit=req_cfg.memory_limit,
            cpus_quota=req_cfg.cpus_quota,
            auto_remove=req_cfg.auto_remove,
        )

    def build_run_args(
        self, request: BuildRunArgsRequest
    ) -> HardenedDockerCommandResponse:
        """Construct full hardened docker run argument list."""
        cfg = self._convert_config(request.config)
        builder = EightFlagBuilder(cfg) if cfg is not None else self._builder
        cmd = builder.build_run_args(
            image=request.image,
            command=request.command,
            extra_mounts=request.extra_mounts,
        )
        return HardenedDockerCommandResponse(
            raw_args=cmd.raw_args,
            flags_verified=cmd.flags_verified,
            missing_flags=cmd.missing_flags,
        )

    def verify_flags(self, request: VerifyFlagsRequest) -> VerifyFlagsResponse:
        """Verify that arbitrary docker arguments comply with the 8-flag matrix."""
        verified, missing = self._builder.verify_flags(request.raw_args)
        return VerifyFlagsResponse(
            flags_verified=verified,
            missing_flags=missing,
        )

    def check_env_leak(self, request: CheckEnvLeakRequest) -> CheckEnvLeakResponse:
        """Audit docker environment parameters for plaintext credential leaks."""
        is_safe, leaks = self._builder.check_leak_free_env(request.env_args)
        return CheckEnvLeakResponse(
            is_safe=is_safe,
            detected_leaks=leaks,
        )

    def register_credential(
        self, request: RegisterVaultCredentialRequest
    ) -> VaultCredentialMetadataResponse:
        """Register a credential in host vault."""
        cred = self._vault.register_credential(
            credential_id=request.credential_id,
            target_service=request.target_service,
            secret_value=request.secret_value,
            allowed_domains=request.allowed_domains,
            description=request.description,
        )
        return VaultCredentialMetadataResponse(
            credential_id=cred.credential_id,
            target_service=cred.target_service,
            secret_value="[REDACTED_IN_VAULT]",
            allowed_domains=cred.allowed_domains,
            description=cred.description,
        )

    def list_credentials(self) -> list[VaultCredentialMetadataResponse]:
        """List all credentials with redacted values."""
        entries = self._vault.list_credentials()
        return [
            VaultCredentialMetadataResponse(
                credential_id=e.credential_id,
                target_service=e.target_service,
                secret_value="[REDACTED_IN_VAULT]",
                allowed_domains=e.allowed_domains,
                description=e.description,
            )
            for e in entries
        ]

    def relay_outbound_request(
        self, request: VaultProxyRelayRequest
    ) -> VaultProxyRelayResponse:
        """Process sandbox request through host vault proxy."""
        harness_req = VaultProxyRequest(
            project_id=request.project_id,
            target_url=request.target_url,
            method=request.method,
            credential_id=request.credential_id,
            headers=request.headers,
            body=request.body,
        )
        resp = self._vault.process_outbound_request(harness_req)
        return VaultProxyRelayResponse(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=resp.body,
            credential_injected=resp.credential_injected,
            blocked_reason=resp.blocked_reason,
        )

    def ensure_provisioned(
        self,
        image: str = "ghcr.io/myrm-ai/sandbox-runtime:latest",
        extra_mounts: list[str] | None = None,
    ) -> LazyProvisionResponse:
        """Provision container lazily on demand."""
        cmd = self._lifecycle.ensure_provisioned(image=image, extra_mounts=extra_mounts)
        status_enum = ProvisionStatusEnum(self._lifecycle.status.value)
        return LazyProvisionResponse(
            container_id=self._lifecycle.container_id,
            status=status_enum,
            flags_verified=cmd.flags_verified,
            command_spec=cmd.raw_args,
        )

    def dispose_sandbox(self) -> LazyProvisionResponse:
        """Tear down active sandbox."""
        self._lifecycle.dispose()
        return LazyProvisionResponse(
            container_id=None,
            status=ProvisionStatusEnum.DISPOSED,
            flags_verified=True,
            command_spec=None,
        )

    def get_lifecycle_status(self) -> LazyProvisionResponse:
        """Get current sandbox status."""
        status_enum = ProvisionStatusEnum(self._lifecycle.status.value)
        return LazyProvisionResponse(
            container_id=self._lifecycle.container_id,
            status=status_enum,
            flags_verified=self._lifecycle.status == ProvisionStatus.RUNNING,
            command_spec=None,
        )
