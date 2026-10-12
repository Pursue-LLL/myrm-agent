"""Service layer for always-on vault secret dynamic redaction.

[INPUT]
- Pydantic schema requests for redaction, streaming scrubbing, and configuration.

[OUTPUT]
- Sanitized outputs, scrubbed chunks, and secret lifecycle responses.

[POS]
- Server security service in app/services/security/vault_secret_redaction_service.py.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.vault_secret_redaction import (
    SecretSourceType,
    SecretStreamScrubber,
    VaultSecretRedactionConfig,
    VaultSecretRedactionFacade,
    get_vault_secret_redaction_facade,
)

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


class VaultSecretRedactionService:
    """Thread-safe business service orchestrating dynamic secret redaction."""

    def __init__(
        self, facade: VaultSecretRedactionFacade | None = None
    ) -> None:
        self._facade: VaultSecretRedactionFacade = (
            facade if facade is not None else get_vault_secret_redaction_facade()
        )
        self._stream_sessions: dict[str, SecretStreamScrubber] = {}
        self._session_lock: threading.Lock = threading.Lock()

    def redact_text(self, req: RedactTextRequest) -> RedactTextResponse:
        """Sanitize raw text string."""
        res = self._facade.redact_text(req.text)
        return RedactTextResponse(
            clean_content=res.clean_content,
            redacted_count=res.redacted_count,
            matched_secrets=res.matched_secrets,
        )

    def redact_tool_return(
        self, req: RedactToolReturnRequest
    ) -> RedactToolReturnResponse:
        """Sanitize tool return text and metadata dictionary."""
        _, text_res = self._facade.redact_tool_return(req.output_text)
        clean_meta_obj, meta_res = self._facade.redact_tool_return(req.metadata)

        clean_metadata: dict[str, str] = {}
        if isinstance(clean_meta_obj, dict):
            for k, v in clean_meta_obj.items():
                clean_metadata[str(k)] = str(v)

        total_redacted = text_res.redacted_count + meta_res.redacted_count
        combined_matched = list(
            dict.fromkeys(text_res.matched_secrets + meta_res.matched_secrets)
        )

        return RedactToolReturnResponse(
            tool_name=req.tool_name,
            clean_output=text_res.clean_content,
            clean_metadata=clean_metadata,
            redacted_count=total_redacted,
            matched_secrets=combined_matched,
        )

    def redact_user_message(
        self, req: RedactUserMessageRequest
    ) -> RedactUserMessageResponse:
        """Sanitize inbound user messages."""
        _, res = self._facade.redact_user_message(req.content)
        return RedactUserMessageResponse(
            user_id=req.user_id,
            clean_content=res.clean_content,
            redacted_count=res.redacted_count,
            matched_secrets=res.matched_secrets,
        )

    def stream_push(self, req: StreamScrubPushRequest) -> StreamScrubResponse:
        """Push an incremental chunk into a stream scrubber session."""
        with self._session_lock:
            if req.session_id not in self._stream_sessions:
                self._stream_sessions[req.session_id] = (
                    self._facade.create_stream_scrubber()
                )
            scrubber = self._stream_sessions[req.session_id]

        emitted = scrubber.push(req.chunk)
        return StreamScrubResponse(
            session_id=req.session_id,
            emitted_chunk=emitted,
            held_back_len=scrubber.held_back_length,
        )

    def stream_flush(
        self, req: StreamScrubFlushRequest
    ) -> StreamScrubResponse:
        """Flush the remaining buffer of a stream scrubber session."""
        with self._session_lock:
            scrubber = self._stream_sessions.pop(req.session_id, None)

        if scrubber is None:
            return StreamScrubResponse(
                session_id=req.session_id,
                emitted_chunk="",
                held_back_len=0,
            )

        flushed = scrubber.flush()
        return StreamScrubResponse(
            session_id=req.session_id,
            emitted_chunk=flushed,
            held_back_len=0,
        )

    def register_secret(
        self, req: RegisterSecretRequest
    ) -> RegisterSecretResponse:
        """Register a secret for active dynamic redaction."""
        src = SecretSourceType.DYNAMIC_CAPTURED
        try:
            src = SecretSourceType(req.source)
        except ValueError:
            src = SecretSourceType.DYNAMIC_CAPTURED

        registered = self._facade.register_secret(
            name=req.name,
            value=req.value,
            source=src,
            mask=req.mask,
        )
        msg = (
            f"Secret '{req.name}' successfully registered."
            if registered
            else f"Secret '{req.name}' was rejected (minimum length required)."
        )
        return RegisterSecretResponse(
            name=req.name, registered=registered, message=msg
        )

    def unregister_secret(self, name: str) -> UnregisterSecretResponse:
        """Remove a secret from dynamic redaction."""
        unregistered = self._facade.unregister_secret(name)
        return UnregisterSecretResponse(name=name, unregistered=unregistered)

    def list_secrets(self) -> SecretListResponse:
        """List names of all currently registered secrets."""
        names = self._facade.list_secret_names()
        return SecretListResponse(secret_names=names, total_count=len(names))

    def get_stats(self) -> RedactionStatsResponse:
        """Retrieve match statistics."""
        stats = self._facade.get_stats()
        total = sum(stats.values())
        return RedactionStatsResponse(stats=stats, total_matches=total)

    def get_config(self) -> RedactionConfigSchema:
        """Retrieve current configuration."""
        cfg = self._facade.get_config()
        return RedactionConfigSchema(
            min_secret_length=cfg.min_secret_length,
            mask_template=cfg.mask_template,
            strip_ansi=cfg.strip_ansi,
            case_sensitive=cfg.case_sensitive,
        )

    def update_config(
        self, req: RedactionConfigUpdateRequest
    ) -> RedactionConfigSchema:
        """Update configuration parameters."""
        cur = self._facade.get_config()
        new_min = (
            req.min_secret_length
            if req.min_secret_length is not None
            else cur.min_secret_length
        )
        new_tpl = (
            req.mask_template
            if req.mask_template is not None
            else cur.mask_template
        )
        new_ansi = (
            req.strip_ansi if req.strip_ansi is not None else cur.strip_ansi
        )
        new_case = (
            req.case_sensitive
            if req.case_sensitive is not None
            else cur.case_sensitive
        )

        updated = VaultSecretRedactionConfig(
            min_secret_length=new_min,
            mask_template=new_tpl,
            strip_ansi=new_ansi,
            case_sensitive=new_case,
        )
        self._facade.update_config(updated)
        return self.get_config()

    def clear(self) -> None:
        """Clear all registered secrets, statistics, and active stream sessions."""
        with self._session_lock:
            self._stream_sessions.clear()
        self._facade.clear()
