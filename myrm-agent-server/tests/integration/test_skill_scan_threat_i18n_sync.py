"""Integration: skill scanner threat classes <-> frontend i18n keys.

Review cards show each scan finding by its threat class in the user's language. A class without a
name would fall back to the generic "other risk" label, hiding what the scanner actually found, so
every locale has to name exactly the classes the scanner can report.

This test is cross-layer by design: harness scanner vocabulary + frontend locales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.scanning.patterns import ALL_PATTERN_GROUPS

FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

LOCALE_FILES = ("en.json", "zh.json", "zh-TW.json", "ja.json", "ko.json", "de.json")

# Classes reported outside the regex pattern table: Unicode and AST passes in scanning/scanner.py and
# scanning/ast_analyzer.py, the optional LLM audit, and package audits (scanning/package_audit.py).
NON_PATTERN_THREATS = frozenset(
    {
        "invisible_unicode",
        "dangerous_import",
        "ast_parse_error",
        "llm_audit",
        "invalid_manifest",
        "integrity",
        "missing_artifact",
        "empty_artifact",
    }
)

# The card falls back to this class name for a threat it does not know.
FALLBACK_THREAT = "unknown"

SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})


@pytest.fixture(params=LOCALE_FILES)
def scan_risk_copy(request: pytest.FixtureRequest) -> tuple[str, dict[str, dict[str, str]]]:
    """The ``settings.skills.scanRisk`` message tree of one locale."""
    locale_path = FRONTEND_LOCALES_DIR / request.param
    if not locale_path.exists():
        pytest.skip(f"Locale file not found: {locale_path}")
    data: dict[str, dict[str, dict[str, dict[str, dict[str, str]]]]] = json.loads(locale_path.read_text("utf-8"))
    return request.param, data["settings"]["skills"]["scanRisk"]


def test_every_scanner_threat_class_has_exactly_one_name(scan_risk_copy: tuple[str, dict[str, dict[str, str]]]) -> None:
    locale, copy = scan_risk_copy
    scanner_threats = {name for name, _patterns in ALL_PATTERN_GROUPS} | NON_PATTERN_THREATS

    assert set(copy["threat"]) == {*scanner_threats, FALLBACK_THREAT}, f"[{locale}] threat keys drifted from the scanner"
    assert all(text.strip() for text in copy["threat"].values()), f"[{locale}] empty threat translation"


def test_every_severity_is_named(scan_risk_copy: tuple[str, dict[str, dict[str, str]]]) -> None:
    locale, copy = scan_risk_copy

    assert set(copy["severity"]) == SEVERITIES, f"[{locale}] severity keys drifted"
    assert all(text.strip() for text in copy["severity"].values()), f"[{locale}] empty severity translation"
