"""Integration: readiness / export-refusal codes <-> frontend i18n keys.

The server answers with stable codes (``ReadinessCode``, ``ExportErrorCode``) and English
diagnostics; the UI turns each code into a localized sentence. A code without a sentence degrades
to a generic line with no alert, so every locale has to cover exactly the codes the server can send.

This test is cross-layer by design: server enums + frontend locales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent.readiness import ReadinessCode
from app.services.plugins._export_models import ExportErrorCode

FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
LOCALE_FILES = ("en.json", "zh.json", "zh-TW.json", "ja.json", "ko.json", "de.json")

# The preview-changed refusal is a retry flow with its own copy, not an error sentence.
EXPORT_CODES_WITHOUT_ERROR_SENTENCE = {ExportErrorCode.CHANGED_SINCE_PREVIEW.value}


@pytest.fixture(params=LOCALE_FILES)
def locale(request: pytest.FixtureRequest) -> dict[str, object]:
    return json.loads((FRONTEND_LOCALES_DIR / request.param).read_text(encoding="utf-8"))


def _non_empty_strings(section: dict[str, str]) -> bool:
    return all(isinstance(text, str) and text.strip() for text in section.values())


def test_readiness_reasons_cover_every_server_code(locale: dict[str, object]) -> None:
    reasons = locale["Agent"]["readiness"]["reasons"]  # type: ignore[index]
    assert set(reasons) == {code.value for code in ReadinessCode}
    assert _non_empty_strings(reasons)


def test_export_errors_cover_every_server_code(locale: dict[str, object]) -> None:
    errors = locale["agent"]["expertExport"]["errors"]  # type: ignore[index]
    expected = {code.value for code in ExportErrorCode} - EXPORT_CODES_WITHOUT_ERROR_SENTENCE
    assert expected <= set(errors)
    assert "generic" in errors
    assert _non_empty_strings(errors)
