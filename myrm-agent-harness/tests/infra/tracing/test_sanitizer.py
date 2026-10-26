"""Unit tests for the three-layer trace privacy sanitizer.

[TESTS]
- Layer 1: High-risk key detection vs safe namespace prefix whitelist
- Layer 2: Sensitive pattern redaction (Bearer, API Keys, Passwords)
- Layer 3: Long payload bounded truncation with SHA-256 fingerprint preservation
- Single-attribute entry point used by the exporter-boundary privacy guard
"""

from __future__ import annotations

from myrm_agent_harness.infra.tracing.sanitizer import (
    TraceSpanSanitizer,
    sanitize_trace_payload,
)


def test_layer1_key_namespace_allowlist_and_sensitive_key_redaction() -> None:
    sanitizer = TraceSpanSanitizer()

    # Safe namespace prefixes should pass regardless of naming
    assert sanitizer.is_safe_key("gen_ai.request.model") is True
    assert sanitizer.is_safe_key("myrm.agent.id") is True
    assert sanitizer.is_safe_key("tool.call.parameters") is True
    assert sanitizer.is_safe_key("http.status_code") is True

    # High-risk un-namespaced keys should be flagged as unsafe
    assert sanitizer.is_safe_key("user_password") is False
    assert sanitizer.is_safe_key("api_key") is False
    assert sanitizer.is_safe_key("auth_token") is False
    assert sanitizer.is_safe_key("session_secret") is False

    attributes = {
        "gen_ai.request.model": "gpt-4o",
        "raw_user_password": "supersecretpassword123",
        "custom.auth_token": "token-xyz-888",
        "normal_meta": "safe-value",
    }
    sanitized = sanitizer.sanitize_attributes(attributes)
    assert sanitized["gen_ai.request.model"] == "gpt-4o"
    assert sanitized["normal_meta"] == "safe-value"
    assert sanitized["raw_user_password"] == "[REDACTED_SENSITIVE_KEY]"
    assert sanitized["custom.auth_token"] == "[REDACTED_SENSITIVE_KEY]"


def test_layer2_pattern_redaction() -> None:
    sanitizer = TraceSpanSanitizer()

    # Bearer token redaction
    bearer_text = "curl -H 'Authorization: Bearer sk-ant-api03-abcdef1234567890' https://api.anthropic.com"
    redacted = sanitizer.sanitize_string_value(bearer_text)
    assert "sk-ant-api03-abcdef1234567890" not in redacted
    assert "REDAC" in redacted or "Bearer" in redacted

    # OpenAI-like API Key redaction
    openai_text = "Using key sk-proj-1234567890abcdef1234567890 to connect"
    redacted_openai = sanitizer.sanitize_string_value(openai_text)
    assert "sk-proj-1234567890abcdef1234567890" not in redacted_openai


def test_layer3_bounded_truncation_with_sha256() -> None:
    sanitizer = TraceSpanSanitizer(max_value_len=256)

    long_str = "x" * 1000
    res = sanitizer.sanitize_string_value(long_str)
    assert len(res) < 500
    assert "[TRUNCATED:len=1000:sha256=" in res

    # Short string should remain unchanged
    short_str = "This is a concise tool output."
    assert sanitizer.sanitize_string_value(short_str) == short_str


def test_sanitize_trace_payload_recursive() -> None:
    payload = {
        "session_id": "sess-001",
        "api_secret": "raw-key-12345",
        "metadata": {
            "gen_ai.system": "open-perplexity",
            "db_password": "mypassword999",
            "nested_list": [
                "Bearer eyJhbGciOi...",
                {"inner_secret": "val", "safe_val": 42},
            ],
        },
        "massive_body": "A" * 5000,
    }

    sanitized = sanitize_trace_payload(payload)
    assert sanitized["session_id"] == "sess-001"
    assert sanitized["api_secret"] == "[REDACTED_SENSITIVE_KEY]"

    meta = sanitized["metadata"]
    assert isinstance(meta, dict)
    assert meta["gen_ai.system"] == "open-perplexity"
    assert meta["db_password"] == "[REDACTED_SENSITIVE_KEY]"

    nested = meta["nested_list"]
    assert isinstance(nested, list)
    assert "REDACTED" in str(nested[0])
    assert nested[1]["inner_secret"] == "[REDACTED_SENSITIVE_KEY]"
    assert nested[1]["safe_val"] == 42

    massive = sanitized["massive_body"]
    assert isinstance(massive, str)
    assert "[TRUNCATED:len=5000:sha256=" in massive


def test_single_attribute_entry_point_applies_all_three_layers() -> None:
    sanitizer = TraceSpanSanitizer(max_value_len=128)

    # Layer 1: a text value under a sensitive un-namespaced key is replaced, numbers pass through
    assert sanitizer.sanitize_attribute("user_password", "plaintext_secret_123") == "[REDACTED_SENSITIVE_KEY]"
    assert sanitizer.sanitize_attribute("user_password", 7) == 7
    # Layer 2
    assert "secret-token-value" not in str(sanitizer.sanitize_attribute("http.header", "Bearer secret-token-value"))
    # Layer 3
    truncated = sanitizer.sanitize_attribute("gen_ai.request.model", "Z" * 1000)
    assert isinstance(truncated, str) and "[TRUNCATED:len=1000:sha256=" in truncated
