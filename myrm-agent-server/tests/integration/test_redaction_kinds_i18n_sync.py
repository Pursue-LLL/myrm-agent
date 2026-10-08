"""Integration: redaction finding kinds <-> frontend i18n keys.

The export preview sends each redaction finding as stable ``SecretKind`` codes and the review
panel turns them into the user's language. A kind without a sentence would surface as a raw
message key, so every locale has to cover exactly the kinds the sanitizer can send.

This test is cross-layer by design: harness enum + frontend locales.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from myrm_agent_harness.agent.skills.security import SecretKind

FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

LOCALE_FILES = ("en.json", "zh.json", "zh-TW.json", "ja.json", "ko.json", "de.json")

# The panel falls back to this sentence for a kind it does not know.
FALLBACK_KIND = "unknown"


@pytest.fixture(params=LOCALE_FILES)
def kind_labels(request: pytest.FixtureRequest) -> tuple[str, dict[str, str]]:
    """The ``common.redactionReview.kinds`` message tree of one locale."""
    locale_path = FRONTEND_LOCALES_DIR / request.param
    if not locale_path.exists():
        pytest.skip(f"Locale file not found: {locale_path}")
    data: dict[str, dict[str, dict[str, dict[str, str]]]] = json.loads(locale_path.read_text("utf-8"))
    return request.param, data["common"]["redactionReview"]["kinds"]


def test_every_secret_kind_has_exactly_one_label(kind_labels: tuple[str, dict[str, str]]) -> None:
    locale, labels = kind_labels

    assert set(labels) == {*get_args(SecretKind), FALLBACK_KIND}, f"[{locale}] kinds keys drifted from SecretKind"
    assert all(text.strip() for text in labels.values()), f"[{locale}] empty kinds translation"
