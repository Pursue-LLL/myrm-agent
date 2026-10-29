"""Computer-use tests must never drive the developer's real desktop."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _forbid_real_input_events(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A test that forgets to patch the event post would otherwise press real keys on this machine."""
    if sys.platform != "darwin":
        yield
        return
    try:
        import Quartz
    except ImportError:
        yield
        return

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("test tried to post a real input event to this machine; patch macos_input first")

    monkeypatch.setattr(Quartz, "CGEventPost", refuse)
    monkeypatch.setattr(Quartz, "CGEventPostToPid", refuse)
    yield
