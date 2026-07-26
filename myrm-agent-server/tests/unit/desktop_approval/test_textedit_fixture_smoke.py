"""Unit smoke tests for desktop approval TextEdit fixture recovery."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval import textedit_fixture


def test_preflight_textedit_foreground_soft_fail_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "activate_textedit_foreground", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_is_frontmost", lambda: False)
    monkeypatch.setattr(textedit_fixture.time, "sleep", lambda _: None)

    assert (
        textedit_fixture.preflight_textedit_foreground(attempts=2, fail_hard=False)
        is False
    )


def test_ensure_textedit_ax_ready_restarts_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        textedit_fixture,
        "preflight_textedit_foreground",
        lambda **_: True,
    )
    probe_results = iter([(False, "ax-empty"), (True, "ax-ready")])
    monkeypatch.setattr(
        textedit_fixture,
        "_probe_textedit_ax_ready",
        lambda: next(probe_results),
    )
    restarted: list[bool] = []
    monkeypatch.setattr(
        textedit_fixture,
        "restart_textedit_fixture_process",
        lambda: restarted.append(True),
    )
    monkeypatch.setattr(textedit_fixture.time, "sleep", lambda _: None)

    assert textedit_fixture.ensure_textedit_ax_ready(attempts=3) is True
    assert len(restarted) == 1


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_passes_when_marker_and_ax_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_fixture_ready", lambda: True)
    ax_calls: list[int] = []

    def _ensure_ax_ready(*, attempts: int = 3) -> bool:
        ax_calls.append(attempts)
        return True

    monkeypatch.setattr(textedit_fixture, "ensure_textedit_ax_ready", _ensure_ax_ready)

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(textedit_fixture.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(textedit_fixture.asyncio, "sleep", _sleep)

    await textedit_fixture.ensure_textedit_fixture_ready(attempts=2)
    assert ax_calls == [2]


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_fails_after_retry_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_fixture_ready", lambda: True)
    monkeypatch.setattr(textedit_fixture, "ensure_textedit_ax_ready", lambda **_: False)
    restarts: list[bool] = []
    monkeypatch.setattr(
        textedit_fixture,
        "restart_textedit_fixture_process",
        lambda: restarts.append(True),
    )

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(textedit_fixture.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(textedit_fixture.asyncio, "sleep", _sleep)

    with pytest.raises(BaseException, match="TextEdit fixture not AX-ready"):
        await textedit_fixture.ensure_textedit_fixture_ready(attempts=2)
    assert len(restarts) == 1
