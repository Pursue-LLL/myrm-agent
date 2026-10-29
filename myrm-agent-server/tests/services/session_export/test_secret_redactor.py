"""Unit tests for the secret redactor's per-text and merged summaries.

[INPUT] app.services.session_export.secret_redactor
[OUTPUT] Pytest cases: one summary per pattern type however many texts carry it, and no summary entry for a clean text.
[POS] tests/services/session_export/test_secret_redactor.py: Test suite for SecretRedactor aggregation.
"""

from __future__ import annotations

from app.services.session_export.export_types import RedactedPatternDetail, RedactionSummary
from app.services.session_export.secret_redactor import SecretRedactor, secret_redactor

_API_KEY = "sk-abcdef1234567890abcdef123456"
_IP = "192.168.1.150"


def test_a_clean_text_has_an_empty_summary() -> None:
    assert secret_redactor.detect_secrets("nothing to see") == RedactionSummary()


def test_detection_does_not_change_the_text_it_scans() -> None:
    text = f"key {_API_KEY}"

    redacted, summary = SecretRedactor.redact_text(text)

    assert _API_KEY not in redacted
    assert summary.total_redacted == 1
    assert text == f"key {_API_KEY}"


def test_summaries_of_several_texts_merge_into_one_entry_per_pattern() -> None:
    merged = secret_redactor.detect_secrets_in([f"a {_API_KEY}", f"b {_IP}", f"c {_API_KEY} {_IP} {_IP}"])

    assert merged.total_redacted == 5
    assert merged.has_secrets is True
    assert merged.details == [
        RedactedPatternDetail(pattern_type="api_key", count=2, placeholder="[REDACTED_API_KEY]"),
        RedactedPatternDetail(pattern_type="internal_ip", count=3, placeholder="[REDACTED_INTERNAL_IP]"),
    ]


def test_no_texts_merge_into_a_clean_summary() -> None:
    assert secret_redactor.detect_secrets_in([]) == RedactionSummary()
