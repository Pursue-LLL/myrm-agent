"""Unit smoke tests for desktop approval TextEdit fixture recovery."""

from __future__ import annotations

import subprocess

import pytest

from tests.e2e.desktop_approval import textedit_fixture

_REAL_USER_DOCUMENT_COUNT = textedit_fixture._user_textedit_document_count


@pytest.fixture(autouse=True)
def _reset_textedit_fixture_runtime_state() -> None:
    textedit_fixture._reset_textedit_fixture_runtime_state_for_tests()


@pytest.fixture(autouse=True)
def _no_user_textedit_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise recovery paths; whether the machine's TextEdit holds user documents is its own test."""
    monkeypatch.setattr(textedit_fixture, "_user_textedit_document_count", lambda: 0)


def test_preflight_textedit_foreground_soft_fail_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "activate_textedit_foreground", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_is_frontmost", lambda: False)
    monkeypatch.setattr(textedit_fixture.time, "sleep", lambda _: None)

    assert textedit_fixture.preflight_textedit_foreground(attempts=2, fail_hard=False) is False


def test_textedit_is_frontmost_osascript_timeout_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")

    def _run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, timeout)

    monkeypatch.setattr(textedit_fixture.subprocess, "run", _run)
    assert textedit_fixture.textedit_is_frontmost() is False


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


def test_restart_textedit_fixture_process_force_kills_on_quit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "_signoff_or_desktop_soak_fast_path", lambda: False)
    calls: list[tuple[str, ...]] = []
    prepared: list[bool] = []

    def _run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(args))
        if args == ["osascript", "-e", 'tell application "TextEdit" to quit']:
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(textedit_fixture.subprocess, "run", _run)
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: prepared.append(True))
    monkeypatch.setattr(textedit_fixture.time, "sleep", lambda _: None)

    textedit_fixture.restart_textedit_fixture_process()

    assert calls[0] == ("osascript", "-e", 'tell application "TextEdit" to quit')
    assert ("pkill", "-x", "TextEdit") in calls
    assert prepared == [True]


def test_restart_textedit_fixture_process_signoff_skips_graceful_quit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "_signoff_or_desktop_soak_fast_path", lambda: True)
    kill_calls: list[bool] = []
    prepared: list[bool] = []

    monkeypatch.setattr(
        textedit_fixture,
        "_force_kill_textedit_process",
        lambda **_: kill_calls.append(True),
    )
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: prepared.append(True))
    monkeypatch.setattr(textedit_fixture.time, "sleep", lambda _: None)

    textedit_fixture.restart_textedit_fixture_process()

    assert kill_calls == [True]
    assert prepared == [True]


def test_prepare_textedit_fixture_force_kills_on_seed_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    calls: list[tuple[str, ...]] = []

    def _run(
        args: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(args))
        if args and args[0] == "osascript" and len(args) >= 3 and args[2] == 'tell application "TextEdit"':
            raise subprocess.TimeoutExpired(args, timeout)
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(textedit_fixture.subprocess, "run", _run)

    textedit_fixture.prepare_textedit_fixture()

    assert ("open", "-gj", "-a", "TextEdit") in calls
    assert ("pkill", "-x", "TextEdit") in calls
    assert ("pkill", "-9", "-x", "TextEdit") in calls


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
    assert ax_calls == [4]


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_allows_ax_fallback_when_marker_ready(
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

    await textedit_fixture.ensure_textedit_fixture_ready(attempts=2)
    assert restarts == []


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_skips_ax_rebuild_during_degraded_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_fixture_ready", lambda: True)
    ax_calls: list[bool] = []
    monkeypatch.setattr(
        textedit_fixture,
        "ensure_textedit_ax_ready",
        lambda **_: ax_calls.append(True),
    )

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(textedit_fixture.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(textedit_fixture.asyncio, "sleep", _sleep)
    monkeypatch.setattr(textedit_fixture.time, "monotonic", lambda: 1000.0)

    textedit_fixture._mark_textedit_ax_degraded("ax-empty-after-rebuild")
    await textedit_fixture.ensure_textedit_fixture_ready(attempts=1)
    assert ax_calls == []


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_clears_degraded_state_on_scope_change(
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
    monkeypatch.setattr(textedit_fixture.time, "monotonic", lambda: 1000.0)

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "case_a (call)")
    textedit_fixture._mark_textedit_ax_degraded("ax-empty-after-rebuild")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "case_b (call)")

    await textedit_fixture.ensure_textedit_fixture_ready(attempts=1)
    assert ax_calls == [4]


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_strict_mode_fails_when_degraded_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE", "1")
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_fixture_ready", lambda: True)
    ax_calls: list[bool] = []
    monkeypatch.setattr(
        textedit_fixture,
        "ensure_textedit_ax_ready",
        lambda **_: ax_calls.append(True),
    )

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(textedit_fixture.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(textedit_fixture.asyncio, "sleep", _sleep)
    monkeypatch.setattr(textedit_fixture.time, "monotonic", lambda: 1000.0)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "strict_degraded (call)")
    textedit_fixture._mark_textedit_ax_degraded("ax-empty-after-rebuild")
    with pytest.raises(
        pytest.fail.Exception,
        match="strict fallback mode is enabled",
    ):
        await textedit_fixture.ensure_textedit_fixture_ready(attempts=1)
    assert ax_calls == []


@pytest.mark.asyncio
async def test_ensure_textedit_fixture_ready_strict_mode_fails_when_ax_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE", "1")
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "prepare_textedit_fixture", lambda: None)
    monkeypatch.setattr(textedit_fixture, "textedit_fixture_ready", lambda: True)
    monkeypatch.setattr(textedit_fixture, "ensure_textedit_ax_ready", lambda **_: False)

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(textedit_fixture.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(textedit_fixture.asyncio, "sleep", _sleep)
    with pytest.raises(
        pytest.fail.Exception,
        match="strict mode requires AX-ready fixture",
    ):
        await textedit_fixture.ensure_textedit_fixture_ready(attempts=1)


def _completed(args: list[str], returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode=returncode, stdout=stdout, stderr="")


def test_prepare_textedit_fixture_never_touches_textedit_that_holds_user_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "_user_textedit_document_count", lambda: 2)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        textedit_fixture,
        "_run_command_no_raise",
        lambda args, **_: calls.append(args),
    )

    with pytest.raises(pytest.fail.Exception, match="2 document"):
        textedit_fixture.prepare_textedit_fixture()

    assert calls == []


def test_restart_textedit_fixture_process_never_quits_textedit_that_holds_user_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(textedit_fixture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(textedit_fixture, "_user_textedit_document_count", lambda: 1)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        textedit_fixture,
        "_run_command_no_raise",
        lambda args, **_: calls.append(args),
    )

    with pytest.raises(pytest.fail.Exception, match="1 document"):
        textedit_fixture.restart_textedit_fixture_process()

    assert calls == []


def test_user_textedit_document_count_is_zero_when_textedit_is_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args, returncode=1)

    monkeypatch.setattr(textedit_fixture, "_run_command_no_raise", _run)

    assert _REAL_USER_DOCUMENT_COUNT() == 0
    assert calls == [["pgrep", "-x", "TextEdit"]]


def test_user_textedit_document_count_reports_documents_without_the_fixture_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def _run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return _completed(args, stdout="3\n" if args[0] == "osascript" else "")

    monkeypatch.setattr(textedit_fixture, "_run_command_no_raise", _run)

    assert _REAL_USER_DOCUMENT_COUNT() == 3
    script = " ".join(calls[1])
    assert textedit_fixture.TEXTEDIT_FIXTURE_MARKER in script
    assert 'text of d is not ""' in script


@pytest.mark.parametrize("probe", [None, _completed(["osascript"], returncode=1), _completed(["osascript"], stdout="oops")])
def test_user_textedit_document_count_treats_an_unprovable_probe_as_none(
    monkeypatch: pytest.MonkeyPatch,
    probe: subprocess.CompletedProcess[str] | None,
) -> None:
    """A wedged fixture TextEdit must stay recoverable: only a positive count blocks the run."""
    monkeypatch.setattr(
        textedit_fixture,
        "_run_command_no_raise",
        lambda args, **_: _completed(args) if args[0] == "pgrep" else probe,
    )

    assert _REAL_USER_DOCUMENT_COUNT() == 0
