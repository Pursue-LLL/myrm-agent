"""REST router for always-on vault secret dynamic redaction endpoints.

[INPUT]
- HTTP requests for text/tool/message sanitization, stream scrubbing, and secret management.

[OUTPUT]
- JSON responses with scrubbed payloads, match metrics, and config states.

[POS]
- Server API router in app/api/security/vault_secret_redaction_router.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.vault_secret_redaction import (
    RedactionConfigSchema,
    RedactionConfigUpdateRequest,
    RedactionStatsResponse,
    RedactTextRequest,
    RedactTextResponse,
    RedactToolReturnRequest,
    RedactToolReturnResponse,
    RedactUserMessageRequest,
    RedactUserMessageResponse,
    RegisterSecretRequest,
    RegisterSecretResponse,
    SecretListResponse,
    StreamScrubFlushRequest,
    StreamScrubPushRequest,
    StreamScrubResponse,
    UnregisterSecretResponse,
)
from app.services.security.vault_secret_redaction_service import (
    VaultSecretRedactionService,
)

router = APIRouter(prefix="/vault-redaction", tags=["vault-redaction"])

_service_instance: VaultSecretRedactionService | None = None


def get_vault_secret_redaction_service() -> VaultSecretRedactionService:
    """Dependency provider for VaultSecretRedactionService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = VaultSecretRedactionService()
    return _service_instance


@router.post("/redact-text", response_model=RedactTextResponse)
def redact_text_endpoint(
    req: RedactTextRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactTextResponse:
    """Scrub raw text string against all registered secrets."""
    return service.redact_text(req)


@router.post("/redact-tool-return", response_model=RedactToolReturnResponse)
def redact_tool_return_endpoint(
    req: RedactToolReturnRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactToolReturnResponse:
    """Scrub tool invocation output and metadata before returning to LLM."""
    return service.redact_tool_return(req)


@router.post("/redact-user-message", response_model=RedactUserMessageResponse)
def redact_user_message_endpoint(
    req: RedactUserMessageRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactUserMessageResponse:
    """Scrub inbound user message content before persistence or LLM ingestion."""
    return service.redact_user_message(req)


@router.post("/stream-scrub/push", response_model=StreamScrubResponse)
def stream_scrub_push_endpoint(
    req: StreamScrubPushRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> StreamScrubResponse:
    """Push an incremental chunk to a stream scrubber session with holdback."""
    return service.stream_push(req)


@router.post("/stream-scrub/flush", response_model=StreamScrubResponse)
def stream_scrub_flush_endpoint(
    req: StreamScrubFlushRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> StreamScrubResponse:
    """Flush the remaining held-back buffer of a stream scrubber session."""
    return service.stream_flush(req)


@router.post("/secrets", response_model=RegisterSecretResponse)
def register_secret_endpoint(
    req: RegisterSecretRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RegisterSecretResponse:
    """Register a new secret into the active dynamic redaction dictionary."""
    return service.register_secret(req)


@router.get("/secrets", response_model=SecretListResponse)
def list_secrets_endpoint(
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> SecretListResponse:
    """List names of currently registered secrets."""
    return service.list_secrets()


@router.delete("/secrets/{name}", response_model=UnregisterSecretResponse)
def unregister_secret_endpoint(
    name: str,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> UnregisterSecretResponse:
    """Remove a secret from the dynamic redaction dictionary."""
    return service.unregister_secret(name)


@router.get("/stats", response_model=RedactionStatsResponse)
def get_stats_endpoint(
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactionStatsResponse:
    """Retrieve redaction match counts per secret."""
    return service.get_stats()


@router.get("/config", response_model=RedactionConfigSchema)
def get_config_endpoint(
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactionConfigSchema:
    """Retrieve current redaction parameters."""
    return service.get_config()


@router.put("/config", response_model=RedactionConfigSchema)
def update_config_endpoint(
    req: RedactionConfigUpdateRequest,
    service: VaultSecretRedactionService = Depends(
        get_vault_secret_redaction_service
    ),
) -> RedactionConfigSchema:
    """Update redaction parameters."""
    return service.update_config(req)
