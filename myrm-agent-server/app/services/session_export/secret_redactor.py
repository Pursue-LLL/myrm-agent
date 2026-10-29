"""Secret Redaction Guard for detecting and sanitizing sensitive credentials before export.

[INPUT] export_types.py
[OUTPUT] SecretRedactor: Regex scanner and scrubbing engine returning redacted text and RedactionSummary (one entry per pattern across any number of texts).
[POS] app/services/session_export/secret_redactor.py
"""

import re
from collections.abc import Iterable

from app.services.session_export.export_types import RedactedPatternDetail, RedactionSummary

PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "api_key",
        re.compile(r"\b(sk-[a-zA-Z0-9_\-]{20,}|myrm-[a-zA-Z0-9_\-]{20,}|ghp_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_]{20,})\b"),
        "[REDACTED_API_KEY]",
    ),
    (
        "jwt_token",
        re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
        "[REDACTED_JWT_TOKEN]",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    (
        "secret_assignment",
        re.compile(r"""(?i)\b(password|secret|api_key|access_token)\s*[:=]\s*["']?([^\s"']{8,})["']?"""),
        r'\1: "[REDACTED_SECRET]"',
    ),
    (
        "internal_ip",
        re.compile(r"\b(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
        "[REDACTED_INTERNAL_IP]",
    ),
]


class SecretRedactor:
    """Detects and scrubs high-risk secrets and internal network identifiers."""

    @classmethod
    def redact_text(cls, text: str) -> tuple[str, RedactionSummary]:
        """Perform regex replacements and produce a structured RedactionSummary."""
        current_text = text
        details: list[RedactedPatternDetail] = []
        total_redacted = 0

        for pattern_type, regex, placeholder in PATTERNS:
            matches = list(regex.finditer(current_text))
            count = len(matches)
            if count > 0:
                total_redacted += count
                details.append(
                    RedactedPatternDetail(
                        pattern_type=pattern_type,
                        count=count,
                        placeholder=placeholder if not placeholder.startswith("\\") else "[REDACTED_SECRET]",
                    )
                )
                current_text = regex.sub(placeholder, current_text)

        summary = RedactionSummary(
            total_redacted=total_redacted,
            has_secrets=total_redacted > 0,
            details=details,
        )
        return current_text, summary

    @classmethod
    def detect_secrets(cls, text: str) -> RedactionSummary:
        """Scan text and return summary without modifying the original content."""
        _, summary = cls.redact_text(text)
        return summary

    @classmethod
    def merge_summaries(cls, summaries: Iterable[RedactionSummary]) -> RedactionSummary:
        """Combine summaries into one entry per pattern type, ordered by first appearance."""
        counts: dict[str, int] = {}
        placeholders: dict[str, str] = {}
        for summary in summaries:
            for detail in summary.details:
                counts[detail.pattern_type] = counts.get(detail.pattern_type, 0) + detail.count
                placeholders.setdefault(detail.pattern_type, detail.placeholder)
        total = sum(counts.values())
        return RedactionSummary(
            total_redacted=total,
            has_secrets=total > 0,
            details=[
                RedactedPatternDetail(pattern_type=pattern_type, count=count, placeholder=placeholders[pattern_type])
                for pattern_type, count in counts.items()
            ],
        )

    @classmethod
    def detect_secrets_in(cls, texts: Iterable[str]) -> RedactionSummary:
        """Scan several texts and return one merged summary without modifying any of them."""
        return cls.merge_summaries(cls.detect_secrets(text) for text in texts)


secret_redactor = SecretRedactor()
