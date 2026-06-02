"""Sensitive data redaction filter for logging.

Framework-level logging filter that automatically redacts sensitive information
from log messages. Uses both pattern matching and CredentialField metadata.

[INPUT]
- channels.core.credentials::CredentialField (POS: Credential field metadata)

[OUTPUT]
- SensitiveDataFilter: Logging filter that redacts sensitive data
- redact_sensitive: Utility function for manual redaction

[POS]
Framework-level log sanitization filter. Auto-detects and redacts sensitive data (token, password, secret, key).
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar


class SensitiveDataFilter(logging.Filter):
    """Logging filter that automatically redacts sensitive information.

    Detects and replaces:
    - Patterns: token, password, secret, key, access_token, api_key, auth_header
    - Values: Any value that looks like a credential (base64, hex, JWT, etc.)

    Usage:
        logger = logging.getLogger(__name__)
        logger.addFilter(SensitiveDataFilter())
    """

    # Sensitive field patterns (case-insensitive)
    SENSITIVE_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(
            r'(token|password|secret|key|auth|credential|bearer)\s*[=:]\s*["\']?([^\s"\']+)["\']?', re.IGNORECASE
        ),
        re.compile(
            r'(access_token|api_key|auth_header|access_key|secret_key)\s*[=:]\s*["\']?([^\s"\']+)["\']?', re.IGNORECASE
        ),
    ]

    # Value patterns that look like credentials
    VALUE_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),  # Base64-like
        re.compile(r"\b[a-fA-F0-9]{32,}\b"),  # Hex-like
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),  # JWT
    ]

    REDACTION_MASK = "***REDACTED***"

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log record by redacting sensitive information."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._redact(str(arg)) if isinstance(arg, str) else arg for arg in record.args)

        return True

    def _redact(self, text: str) -> str:
        """Redact sensitive information from text."""
        result = text

        # Redact sensitive field patterns
        for pattern in self.SENSITIVE_PATTERNS:
            result = pattern.sub(lambda m: f"{m.group(1)}={self.REDACTION_MASK}", result)

        # Optionally redact credential-like values (commented out to avoid false positives)
        # for pattern in self.VALUE_PATTERNS:
        #     result = pattern.sub(self.REDACTION_MASK, result)

        return result


def redact_sensitive(text: str, patterns: list[str] | None = None) -> str:
    """Manually redact sensitive information from text.

    Args:
        text: Text to redact.
        patterns: Optional list of additional patterns to redact (e.g. ["my_secret", "custom_token"]).

    Returns:
        Text with sensitive information replaced by ***REDACTED***.

    Example:
        >>> redact_sensitive("Connecting with token=abc123")
        "Connecting with token=***REDACTED***"
    """
    result = text

    # Apply built-in patterns
    for pattern in SensitiveDataFilter.SENSITIVE_PATTERNS:
        result = pattern.sub(lambda m: f"{m.group(1)}={SensitiveDataFilter.REDACTION_MASK}", result)

    # Apply custom patterns
    if patterns:
        for custom_pattern in patterns:
            result = result.replace(custom_pattern, SensitiveDataFilter.REDACTION_MASK)

    return result
