"""Integration: product labels quoted by LLM diagnostic copy ↔ frontend locale labels.

A diagnostic step such as "Update your API key in Settings > Model Service" only helps when the user finds a screen
with exactly that name. The copy lives in the harness catalogues and the labels in the frontend locales, so a rename
on either side breaks the step silently. Every in-product location the catalogues name is registered here with the
frontend labels it must quote, per locale; a new "A > B" path in a catalogue must be registered before the suite passes.

This test is cross-layer by design: harness diagnostic catalogues + frontend locales.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as harness_i18n

_HARNESS_LOCALES_DIR = Path(harness_i18n.__file__).parent / "locales"
_FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

# Harness catalogue locale -> frontend locale file.
_FRONTEND_FILES = {
    "en": "en.json",
    "zh-CN": "zh.json",
    "zh-TW": "zh-TW.json",
    "ja": "ja.json",
    "ko": "ko.json",
    "de": "de.json",
}

_PATH_SEPARATOR = re.compile(r"\s[>→]\s")


@dataclass(frozen=True)
class _Quote:
    """A catalogue text that names product screens, with the ``settings.*`` frontend labels it must quote."""

    catalogue_key: str
    labels: tuple[str, ...]
    locales: tuple[str, ...] = tuple(_FRONTEND_FILES)


_MODEL_SERVICE = "menu.models"
_TLS_COMPAT = ("menu.preferences", "advancedSettings", "enterpriseTlsCompat")

_QUOTES: tuple[_Quote, ...] = (
    _Quote("custom_endpoint_unreachable_resolution_steps", (_MODEL_SERVICE, "modelService.apiUrl")),
    _Quote("billing_resolution_steps", (_MODEL_SERVICE, "modelService.apiKeys")),
    _Quote("api_key_resolution_steps", (_MODEL_SERVICE,)),
    _Quote("format_error_generic_resolution_steps", (_MODEL_SERVICE,)),
    _Quote("format_error_model_resolution_steps", (_MODEL_SERVICE,)),
    # The German, Japanese and Korean rate-limit steps carry no fallback-model step.
    _Quote(
        "rate_limit_resolution_steps",
        (_MODEL_SERVICE, "menu.defaultModel", "defaultModel.fallbackModel"),
        locales=("en", "zh-CN", "zh-TW"),
    ),
    _Quote("overloaded_resolution_steps", (_MODEL_SERVICE, "menu.defaultModel", "defaultModel.fallbackModel")),
    _Quote("response_format_error_resolution_steps", (_MODEL_SERVICE, "menu.defaultModel", "defaultModel.fallbackModel")),
    _Quote("tls_certificate_resolution_steps", _TLS_COMPAT),
    _Quote("tls_transient_resolution_steps", _TLS_COMPAT),
)


def _text(value: str | list[str]) -> str:
    return " ".join(value) if isinstance(value, list) else value


def _catalogue(locale: str) -> dict[str, str | list[str]]:
    bundle: dict[str, str | list[str]] = json.loads((_HARNESS_LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    return bundle


def _frontend_label(locale: str, dotted_path: str) -> str:
    path = _FRONTEND_LOCALES_DIR / _FRONTEND_FILES[locale]
    if not path.is_file():
        pytest.skip(f"Frontend locale not found: {path}")
    node: object = json.loads(path.read_text("utf-8"))["settings"]
    for part in dotted_path.split("."):
        assert isinstance(node, dict), f"[{locale}] settings.{dotted_path}: {part} is not a section"
        node = node[part]
    assert isinstance(node, str) and node, f"[{locale}] settings.{dotted_path} is not a label"
    return node


_CASES = [(quote, locale) for quote in _QUOTES for locale in quote.locales]


@pytest.mark.parametrize(("quote", "locale"), _CASES, ids=[f"{q.catalogue_key}-{loc}" for q, loc in _CASES])
def test_catalogue_text_quotes_the_frontend_labels(quote: _Quote, locale: str) -> None:
    text = _text(_catalogue(locale)[quote.catalogue_key])

    missing = {label: _frontend_label(locale, label) for label in quote.labels}
    missing = {label: shown for label, shown in missing.items() if shown not in text}

    assert not missing, f"[{locale}] {quote.catalogue_key} does not quote settings.{sorted(missing)}: {missing}\n{text}"


@pytest.mark.parametrize("locale", _FRONTEND_FILES)
def test_every_product_path_in_the_catalogue_is_registered(locale: str) -> None:
    registered = {quote.catalogue_key for quote in _QUOTES}
    unregistered = [
        key for key, value in _catalogue(locale).items() if _PATH_SEPARATOR.search(_text(value)) and key not in registered
    ]

    assert not unregistered, f"[{locale}] catalogue texts naming a path without a registered quote: {unregistered}"
