"""Integration: expert-export omission codes <-> frontend i18n keys.

The export preview reports *what* stays out of a package (``OmittedKind``) and *why* (``Omit``);
the UI turns both into sentences. A code without a sentence would surface as a raw message key,
so every locale has to cover exactly the codes the server can send.

This test is cross-layer by design: server enums + frontend locales.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest

from app.services.plugins.export_service import Omit, OmittedKind

FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

LOCALE_FILES = ("en.json", "zh.json", "zh-TW.json", "ja.json", "ko.json", "de.json")


@pytest.fixture(params=LOCALE_FILES)
def export_messages(request: pytest.FixtureRequest) -> tuple[str, dict[str, dict[str, str]]]:
    """The ``agent.expertExport`` message tree of one locale."""
    locale_path = FRONTEND_LOCALES_DIR / request.param
    if not locale_path.exists():
        pytest.skip(f"Locale file not found: {locale_path}")
    data: dict[str, dict[str, dict[str, dict[str, str]]]] = json.loads(locale_path.read_text("utf-8"))
    return request.param, data["agent"]["expertExport"]


def test_every_omit_reason_has_exactly_one_sentence(export_messages: tuple[str, dict[str, dict[str, str]]]) -> None:
    locale, messages = export_messages
    sentences = messages["omitReason"]
    expected = {reason.value for reason in Omit}

    assert set(sentences) == expected, f"[{locale}] omitReason keys drifted from the Omit enum"
    assert all(text.strip() for text in sentences.values()), f"[{locale}] empty omitReason translation"


def test_every_omitted_kind_has_exactly_one_label(export_messages: tuple[str, dict[str, dict[str, str]]]) -> None:
    locale, messages = export_messages
    labels = messages["omittedKinds"]

    assert set(labels) == set(get_args(OmittedKind)), f"[{locale}] omittedKinds keys drifted from OmittedKind"
    assert all(text.strip() for text in labels.values()), f"[{locale}] empty omittedKinds translation"
