"""Unit tests for VaultSecretRedactionService.

Tests:
- Text scrubbing and secret substitution
- Tool return output and metadata sanitization
- Inbound user message sanitization
- Streaming chunk holdback and flush handling
- Secret lifecycle (register, list, unregister) and stats
- Configuration get and update
"""

from __future__ import annotations

from app.schemas.vault_secret_redaction import (
    RedactionConfigUpdateRequest,
    RedactTextRequest,
    RedactToolReturnRequest,
    RedactUserMessageRequest,
    RegisterSecretRequest,
    StreamScrubFlushRequest,
    StreamScrubPushRequest,
)
from app.services.security.vault_secret_redaction_service import (
    VaultSecretRedactionService,
)


def test_service_secret_lifecycle_and_text_redaction() -> None:
    service = VaultSecretRedactionService()
    service.clear()

    # Register secret
    reg_req = RegisterSecretRequest(
        name="TEST_TOKEN",
        value="super_secret_token_val_123",
        source="dynamic_captured",
    )
    reg_res = service.register_secret(reg_req)
    assert reg_res.registered is True
    assert reg_res.name == "TEST_TOKEN"

    # List secrets
    list_res = service.list_secrets()
    assert "TEST_TOKEN" in list_res.secret_names
    assert list_res.total_count >= 1

    # Redact text
    txt_req = RedactTextRequest(
        text="Executing command with super_secret_token_val_123 in bash."
    )
    txt_res = service.redact_text(txt_req)
    assert "super_secret_token_val_123" not in txt_res.clean_content
    assert "TEST_TOKEN=<REDACTED>" in txt_res.clean_content
    assert txt_res.redacted_count == 1
    assert "TEST_TOKEN" in txt_res.matched_secrets

    # Check stats
    stats_res = service.get_stats()
    assert stats_res.stats.get("TEST_TOKEN") == 1

    # Unregister
    unreg_res = service.unregister_secret("TEST_TOKEN")
    assert unreg_res.unregistered is True
    assert "TEST_TOKEN" not in service.list_secrets().secret_names


def test_service_tool_return_sanitization() -> None:
    service = VaultSecretRedactionService()
    service.clear()
    service.register_secret(
        RegisterSecretRequest(
            name="DB_PASSWD",
            value="mypassword_secret_9988",
        )
    )

    req = RedactToolReturnRequest(
        tool_name="bash_execute",
        output_text="DB connect failed with password mypassword_secret_9988 error",
        metadata={"conn_str": "user=admin;pass=mypassword_secret_9988"},
    )
    res = service.redact_tool_return(req)
    assert "mypassword_secret_9988" not in res.clean_output
    assert "DB_PASSWD=<REDACTED>" in res.clean_output
    assert "mypassword_secret_9988" not in res.clean_metadata.get(
        "conn_str", ""
    )
    assert "DB_PASSWD=<REDACTED>" in res.clean_metadata.get("conn_str", "")
    assert res.redacted_count == 2


def test_service_user_message_sanitization() -> None:
    service = VaultSecretRedactionService()
    service.clear()
    service.register_secret(
        RegisterSecretRequest(
            name="OPENAI_KEY",
            value="sk-proj-test-live-token-12345",
        )
    )

    req = RedactUserMessageRequest(
        user_id="user_alice",
        content="Here is my token: sk-proj-test-live-token-12345",
    )
    res = service.redact_user_message(req)
    assert "sk-proj-test-live-token-12345" not in res.clean_content
    assert "OPENAI_KEY=<REDACTED>" in res.clean_content
    assert res.redacted_count == 1


def test_service_stream_scrubbing() -> None:
    service = VaultSecretRedactionService()
    service.clear()
    secret = "sk-split-stream-token-8877"
    service.register_secret(
        RegisterSecretRequest(
            name="SPLIT_KEY",
            value=secret,
        )
    )

    session_id = "test-stream-sess-1"
    # Chunk 1 with prefix
    res1 = service.stream_push(
        StreamScrubPushRequest(
            session_id=session_id,
            chunk="Token starts: sk-split-stream-",
        )
    )
    assert res1.emitted_chunk == "Token starts: "
    assert res1.held_back_len > 0

    # Chunk 2 completing token
    res2 = service.stream_push(
        StreamScrubPushRequest(
            session_id=session_id,
            chunk="token-8877 completed",
        )
    )
    assert secret not in res2.emitted_chunk
    assert "SPLIT_KEY=<REDACTED>" in res2.emitted_chunk
    assert "completed" in res2.emitted_chunk

    # Flush session
    res3 = service.stream_flush(
        StreamScrubFlushRequest(session_id=session_id)
    )
    assert res3.emitted_chunk == ""


def test_service_config_lifecycle() -> None:
    service = VaultSecretRedactionService()
    cur_cfg = service.get_config()
    assert cur_cfg.min_secret_length >= 3

    up_req = RedactionConfigUpdateRequest(
        min_secret_length=10,
        mask_template="[HIDDEN:{name}]",
    )
    up_cfg = service.update_config(up_req)
    assert up_cfg.min_secret_length == 10
    assert up_cfg.mask_template == "[HIDDEN:{name}]"

    # Reset
    service.update_config(
        RedactionConfigUpdateRequest(
            min_secret_length=8,
            mask_template="{name}=<REDACTED>",
        )
    )
