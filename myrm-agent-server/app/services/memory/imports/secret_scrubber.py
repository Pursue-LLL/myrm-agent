"""Sensitive data scrubber for external transcripts and recalled text.

[INPUT]
- re (POS: Python standard regular expression library)

[OUTPUT]
- scrub_sensitive_data: Cleanse API keys, bearer tokens, private keys, and passwords before indexing.

[POS]
Security pipeline module for external transcript recall indexing.
Ensures secrets and credentials from external developer logs are redacted before SQLite/FTS5 write.
"""

from __future__ import annotations

import re

# Pre-compiled high-performance pattern matchers
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Private Key blocks
    (
        re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Common API Keys (OpenAI, Anthropic, Gemini, Stripe)
    (
        re.compile(r"\b(?:sk-[a-zA-Z0-9_\-]{20,}|sk-ant-[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z-_]{35})\b"),
        "[REDACTED_API_KEY]",
    ),
    # GitHub Tokens (Personal access, OAuth, Fine-grained)
    (
        re.compile(r"\bgh[pousr]_[a-zA-Z0-9]{36,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    # AWS Access Key ID
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    # Bearer Tokens
    (
        re.compile(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}"),
        "Bearer [REDACTED_TOKEN]",
    ),
    # Key-value assignment of credentials
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|api_key|access_token|client_secret)\s*[:=]\s*[\"']?([^\s\"'`]{6,})[\"']?"
        ),
        r"\1=[REDACTED_SECRET]",
    ),
]


def scrub_sensitive_data(text: str) -> str:
    """Sanitize secrets, credentials, and tokens from transcript text before persistence."""
    if not text:
        return ""

    sanitized = text
    for pattern, replacement in _PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized
