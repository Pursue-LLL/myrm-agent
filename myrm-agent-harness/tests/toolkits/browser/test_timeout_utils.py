"""Unit tests for browser timeout detection helpers."""

import subprocess
import sys

import pytest
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from myrm_agent_harness.toolkits.browser.utils.timeout import is_timeout_error, timeout_error_types


def test_is_timeout_error_recognizes_builtin() -> None:
    assert is_timeout_error(TimeoutError("navigation timed out"))


def test_is_timeout_error_recognizes_patchright() -> None:
    assert is_timeout_error(PlaywrightTimeoutError("page.goto: Timeout 30000ms exceeded"))


def test_is_timeout_error_rejects_other_errors() -> None:
    assert not is_timeout_error(RuntimeError("unexpected failure"))
    assert not is_timeout_error(ConnectionError("connection refused"))
    assert not is_timeout_error(ValueError("bad url"))


def test_timeout_error_types_cover_both_classes() -> None:
    assert timeout_error_types() == (TimeoutError, PlaywrightTimeoutError)


def test_timeout_error_types_fall_back_to_builtin_without_patchright(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "patchright.async_api", None)
    timeout_error_types.cache_clear()
    try:
        assert timeout_error_types() == (TimeoutError,)
        assert is_timeout_error(TimeoutError("x"))
    finally:
        monkeypatch.undo()
        timeout_error_types.cache_clear()


def test_importing_the_browser_toolkit_does_not_load_patchright() -> None:
    """Page types are annotation-only, so the driver must stay unloaded until a session is used."""
    probe = (
        "import sys\n"
        "from myrm_agent_harness.toolkits.browser import BrowserSession\n"
        "assert 'patchright' not in sys.modules, 'patchright was imported eagerly'\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
