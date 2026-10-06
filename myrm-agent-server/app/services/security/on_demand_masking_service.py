"""Service layer for On-Demand Credential Materialization and Multi-Encoding Masking."""

from __future__ import annotations

import subprocess

from myrm_agent_harness.core.security.on_demand_masking import (
    CredentialField,
    MultiEncodingSecretMasker,
    OnDemandCredentialResolver,
)

from app.schemas.on_demand_masking import (
    MaskTextRequest,
    MaskTextResponse,
    ResolveAndExecuteRequest,
    ResolveAndExecuteResponse,
)


class OnDemandMaskingService:
    """Service wrapping on-demand resolution and multi-encoding secret masking."""

    def __init__(self) -> None:
        self._resolver = OnDemandCredentialResolver()

    def mask_text(self, request: MaskTextRequest) -> MaskTextResponse:
        """Mask sensitive environment values from text across multiple encodings."""
        masker = MultiEncodingSecretMasker(request.environment)
        masked, labels = masker.mask(request.text)
        return MaskTextResponse(
            masked_text=masked,
            redacted_labels=labels,
            has_redactions=len(labels) > 0,
        )

    def resolve_and_execute(
        self, request: ResolveAndExecuteRequest
    ) -> ResolveAndExecuteResponse:
        """Resolve requested credentials on demand, run command, and mask all outputs."""
        resolver = OnDemandCredentialResolver()

        # Register mock providers from request if provided
        for handle, env_map in request.mock_providers.items():
            fields = [
                CredentialField(key=k, value=v, is_secret=True)
                for k, v in env_map.items()
            ]
            resolver.register_provider(handle, (lambda f=fields: f))

        command_env, masker = resolver.resolve_requested(request.requested_handles)

        # Execute command isolated without shell
        try:
            proc = subprocess.run(  # noqa: S602
                request.command,
                shell=True,
                capture_output=True,
                text=True,
                env=command_env,
                timeout=30,
            )
            raw_stdout = proc.stdout
            raw_stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            raw_stdout = exc.stdout or ""
            raw_stderr = (exc.stderr or "") + "\nCommand timed out."
            exit_code = 124
        except Exception as exc:
            raw_stdout = ""
            raw_stderr = f"Execution error: {str(exc)}"
            exit_code = 1

        masked_stdout, labels_stdout = masker.mask(raw_stdout)
        masked_stderr, labels_stderr = masker.mask(raw_stderr)
        all_labels = sorted(list(set(labels_stdout + labels_stderr)))

        return ResolveAndExecuteResponse(
            command=request.command,
            resolved_env_keys=sorted(list(command_env.keys())),
            masked_stdout=masked_stdout,
            masked_stderr=masked_stderr,
            exit_code=exit_code,
            redacted_labels=all_labels,
        )


_instance: OnDemandMaskingService | None = None


def get_on_demand_masking_service() -> OnDemandMaskingService:
    """Get singleton instance of OnDemandMaskingService."""
    global _instance
    if _instance is None:
        _instance = OnDemandMaskingService()
    return _instance
