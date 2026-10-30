"""A rate-limit diagnosis names the wait once: the provider's own, else the generic first step.

The provider's wait (``cooldown_remaining_ms``) is in the message; a static "wait 60 seconds" step next to it would tell
the caller two different waits. Without a provider wait the generic step is the only one, and it comes first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic, engine
from myrm_agent_harness.agent.errors.diagnostics.i18n import LocaleManager, get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as manager_module

_LOCALES = ("en", "zh-CN", "ja", "ko", "de")
_RATE_LIMITED = Exception("429 too many requests")


def _bundled(locale: str) -> dict[str, str | list[str]]:
    path = Path(manager_module.__file__).parent / "locales" / f"{locale}.json"
    bundle: dict[str, str | list[str]] = json.loads(path.read_text(encoding="utf-8"))
    return bundle


@pytest.mark.parametrize("locale", _LOCALES)
def test_without_a_provider_wait_the_generic_wait_step_leads(locale: str) -> None:
    bundle = _bundled(locale)

    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale=locale)

    assert result.resolution_steps == [bundle["rate_limit_wait_step"], *bundle["rate_limit_resolution_steps"]]


@pytest.mark.parametrize("locale", _LOCALES)
def test_with_a_provider_wait_no_generic_wait_step_follows_it(locale: str) -> None:
    bundle = _bundled(locale)

    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale=locale, cooldown_remaining_ms=10_800_000)

    assert "10800" in result.user_message
    assert result.resolution_steps == bundle["rate_limit_resolution_steps"]
    assert bundle["rate_limit_wait_step"] not in result.resolution_steps


@pytest.mark.parametrize("cooldown_remaining_ms", [None, 0, 400])
def test_a_wait_that_rounds_to_nothing_is_not_a_provider_wait(cooldown_remaining_ms: int | None) -> None:
    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="en", cooldown_remaining_ms=cooldown_remaining_ms)

    assert result.resolution_steps[0] == "Wait 60 seconds and retry"


def test_a_locale_without_a_bundle_takes_the_english_steps_and_the_english_wait_step() -> None:
    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="fr")

    assert result.resolution_steps == [
        _bundled("en")["rate_limit_wait_step"],
        *_bundled("en")["rate_limit_resolution_steps"],
    ]


def test_an_empty_locale_takes_the_english_steps_and_the_english_wait_step(monkeypatch: pytest.MonkeyPatch) -> None:
    # An empty locale is not "unset": it resolves like any locale without a bundle, so the wait step and the
    # steps come from the same language instead of the wait step following the detected system locale.
    monkeypatch.setattr(get_locale_manager(), "detect_locale", lambda: "zh-CN")

    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="")

    assert result.resolution_steps == [
        _bundled("en")["rate_limit_wait_step"],
        *_bundled("en")["rate_limit_resolution_steps"],
    ]


def test_a_bundle_without_the_wait_step_keeps_its_steps_as_they_are(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old_steps = ["Retry shortly", "Upgrade the plan"]
    (tmp_path / "en.json").write_text(
        json.dumps({"rate_limit_user_message": "Throttled", "rate_limit_resolution_steps": old_steps}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_LOCALES_DIR", str(tmp_path))
    monkeypatch.setattr(engine, "get_locale_manager", lambda: LocaleManager())

    result = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="en")

    assert result.resolution_steps == old_steps
    assert not any("Missing translation" in step for step in result.resolution_steps)


def test_the_wait_step_is_an_optional_text_of_the_bundle() -> None:
    manager = get_locale_manager()

    assert manager.translate_optional("rate_limit", "wait_step", "en") == "Wait 60 seconds and retry"
    assert manager.translate_optional("rate_limit", "no_such_text", "en") is None
    assert manager.translate_optional("no_such_error", "wait_step", "en") is None
