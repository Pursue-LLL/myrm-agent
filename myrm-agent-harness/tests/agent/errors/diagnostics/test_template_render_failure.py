"""A text a host's bundle cannot render gives way to the English one, and the diagnosis keeps its card.

A host registers a language or points ``MYRM_LOCALES_DIR`` at its own bundle; a typo in a template (``{}``, ``{model``)
makes ``str.format`` raise. Without the fallback the exception leaves ``LLMErrorDiagnostic.diagnose`` and both of its
callers drop the card.
"""

from __future__ import annotations

import logging

import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic
from myrm_agent_harness.agent.errors.diagnostics.i18n import LocaleManager, get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as manager_module

_UNRENDERABLE = pytest.mark.parametrize(
    ("template", "error"),
    [
        pytest.param("Retry after {} seconds", IndexError, id="positional-field"),
        pytest.param("{x.nope}", AttributeError, id="unknown-attribute"),
        pytest.param("{model", ValueError, id="unclosed-brace"),
        pytest.param("{x[a]}", TypeError, id="text-subscript"),
    ],
)
_RATE_LIMITED = Exception("429 too many requests")


@pytest.fixture
def manager() -> LocaleManager:
    return get_locale_manager()


def _host_language(manager: LocaleManager, monkeypatch: pytest.MonkeyPatch, *templates: str) -> None:
    """Register language ``xx`` whose rate-limit message is ``templates[0]`` and whose steps are all of ``templates``."""
    bundle = {"rate_limit": {"user_message": templates[0], "resolution_steps": list(templates)}}
    monkeypatch.setitem(manager._translations, "xx", bundle)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == manager_module.__name__ and r.levelno == logging.WARNING]


def _assert_one_warning(caplog: pytest.LogCaptureFixture, error: type[Exception], locale: str = "xx") -> None:
    records = _warnings(caplog)
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert records[0].exc_info[0] is error
    assert f"rate_limit.user_message of locale '{locale}'" in records[0].getMessage()


@_UNRENDERABLE
def test_a_message_the_language_cannot_render_is_answered_in_english(
    template: str,
    error: type[Exception],
    manager: LocaleManager,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _host_language(manager, monkeypatch, template, "unused second step")

    with caplog.at_level(logging.WARNING):
        message = manager.translate("rate_limit", "user_message", "xx")

    assert message == manager.translate("rate_limit", "user_message", "en")
    _assert_one_warning(caplog, error)


@_UNRENDERABLE
def test_an_optional_text_the_language_cannot_render_is_answered_in_english(
    template: str,
    error: type[Exception],
    manager: LocaleManager,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _host_language(manager, monkeypatch, template)

    with caplog.at_level(logging.WARNING):
        text = manager.translate_optional("rate_limit", "user_message", "xx")

    assert text == manager.translate_optional("rate_limit", "user_message", "en")
    _assert_one_warning(caplog, error)


@_UNRENDERABLE
def test_one_step_the_language_cannot_render_sets_the_whole_list_aside(
    template: str,
    error: type[Exception],
    manager: LocaleManager,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _host_language(manager, monkeypatch, "a step that renders", template)

    with caplog.at_level(logging.WARNING):
        steps = manager.translate("rate_limit", "resolution_steps", "xx")

    assert steps == manager.translate("rate_limit", "resolution_steps", "en")
    assert "a step that renders" not in steps
    records = _warnings(caplog)
    assert [r.exc_info[0] for r in records if r.exc_info] == [error]


def test_an_optional_text_that_is_a_step_list_is_left_out(manager: LocaleManager) -> None:
    assert manager.translate_optional("rate_limit", "resolution_steps", "en") is None


def test_a_text_neither_language_can_render_counts_as_missing(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _host_language(manager, monkeypatch, "{}")
    monkeypatch.setitem(manager._translations["en"]["rate_limit"], "user_message", "{model")

    with caplog.at_level(logging.WARNING):
        message = manager.translate("rate_limit", "user_message", "xx")
        optional = manager.translate_optional("rate_limit", "user_message", "xx")

    assert message == "[Missing translation: rate_limit.user_message]"
    assert optional is None
    assert [r.exc_info[0] for r in _warnings(caplog) if r.exc_info] == [IndexError, ValueError, IndexError, ValueError]


def test_english_asked_for_in_english_is_tried_once(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(manager._translations["en"]["rate_limit"], "user_message", "{}")

    with caplog.at_level(logging.WARNING):
        assert manager.translate_optional("rate_limit", "user_message", "en") is None

    _assert_one_warning(caplog, IndexError, locale="en")


def test_the_diagnosis_keeps_its_card_when_the_language_and_its_cooldown_sentence_cannot_render(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        manager._translations,
        "xx",
        {
            "rate_limit": {"user_message": "{x[a]}", "resolution_steps": ["{}"]},
            "_cooldown_hint": {"template": "{duration.nope}"},
        },
    )
    wait_ms = 23_000_000
    english = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="en", cooldown_remaining_ms=wait_ms)

    card = LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale="xx", cooldown_remaining_ms=wait_ms)

    assert card.error_type == english.error_type
    assert (
        card.user_message
        == f"{LLMErrorDiagnostic.diagnose(_RATE_LIMITED, locale='en').user_message} Retry after 23000 seconds."
    )
    assert card.resolution_steps == english.resolution_steps
