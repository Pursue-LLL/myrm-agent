"""Unit tests for memory guardian policy helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.memory.guardian_policy import (
    MemoryGuardianPolicy,
    ensure_memory_guardian_timezone_initialized,
    is_within_quiet_window,
    resolve_guardian_intervals,
    seconds_until_quiet_window_open,
)


def _ts(hour: int, minute: int = 0) -> float:
    return datetime(2026, 1, 1, hour, minute, tzinfo=UTC).timestamp()


def test_resolve_guardian_intervals_by_frequency_tier() -> None:
    conservative = resolve_guardian_intervals(MemoryGuardianPolicy(frequency_tier="conservative"))
    balanced = resolve_guardian_intervals(MemoryGuardianPolicy(frequency_tier="balanced"))
    aggressive = resolve_guardian_intervals(MemoryGuardianPolicy(frequency_tier="aggressive"))

    assert (conservative.healthy_hours, conservative.unhealthy_hours) == (8, 4)
    assert (balanced.healthy_hours, balanced.unhealthy_hours) == (6, 2)
    assert (aggressive.healthy_hours, aggressive.unhealthy_hours) == (4, 1)


def test_quiet_window_regular_range() -> None:
    policy = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=1,
        quiet_window_end_hour=5,
    )
    assert is_within_quiet_window(policy=policy, now_ts=_ts(2)) is True
    assert is_within_quiet_window(policy=policy, now_ts=_ts(6)) is False


def test_quiet_window_overnight_range() -> None:
    policy = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=22,
        quiet_window_end_hour=6,
    )
    assert is_within_quiet_window(policy=policy, now_ts=_ts(23)) is True
    assert is_within_quiet_window(policy=policy, now_ts=_ts(3)) is True
    assert is_within_quiet_window(policy=policy, now_ts=_ts(12)) is False


def test_seconds_until_quiet_window_open() -> None:
    overnight = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=22,
        quiet_window_end_hour=6,
    )
    regular = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=1,
        quiet_window_end_hour=5,
    )

    assert seconds_until_quiet_window_open(policy=overnight, now_ts=_ts(12)) == 10 * 3600
    assert seconds_until_quiet_window_open(policy=regular, now_ts=_ts(23)) == 2 * 3600
    assert seconds_until_quiet_window_open(policy=regular, now_ts=_ts(2)) == 0


def test_quiet_window_timezone_offset_applied() -> None:
    policy = MemoryGuardianPolicy(
        quiet_window_enabled=True,
        quiet_window_start_hour=0,
        quiet_window_end_hour=2,
        timezone_offset_minutes=480,  # UTC+8
    )
    assert is_within_quiet_window(policy=policy, now_ts=_ts(17, 30)) is True  # local 01:30 next day
    assert is_within_quiet_window(policy=policy, now_ts=_ts(20, 30)) is False  # local 04:30 next day


def test_quiet_window_rejects_identical_start_end_when_enabled() -> None:
    with pytest.raises(ValueError):
        MemoryGuardianPolicy(
            quiet_window_enabled=True,
            quiet_window_start_hour=4,
            quiet_window_end_hour=4,
        )


class _FakeResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> object | None:
        return self._row


class _FakeSession:
    def __init__(self, row: object | None) -> None:
        self.row = row
        self.commit_count = 0

    async def execute(self, *_args: object, **_kwargs: object) -> _FakeResult:
        return _FakeResult(self.row)

    async def commit(self) -> None:
        self.commit_count += 1


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


@pytest.mark.asyncio
async def test_ensure_timezone_initialized_upgrades_server_fallback_with_client_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = MemoryGuardianPolicy(
        timezone_offset_minutes=0,
        timezone_initialized=True,
        timezone_source="server_fallback",
    )
    row = type("Row", (), {"config_value": existing.model_dump(), "version": "v1"})()
    session = _FakeSession(row)
    monkeypatch.setattr(
        "app.services.memory.guardian_policy.get_session_factory",
        lambda: (lambda: _FakeSessionContext(session)),
    )

    updated = await ensure_memory_guardian_timezone_initialized(480, source="client_header")

    assert updated.timezone_offset_minutes == 480
    assert updated.timezone_source == "client_header"
    assert session.commit_count == 1
    assert MemoryGuardianPolicy.model_validate(row.config_value).timezone_offset_minutes == 480


@pytest.mark.asyncio
async def test_ensure_timezone_initialized_does_not_override_manual_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = MemoryGuardianPolicy(
        timezone_offset_minutes=300,
        timezone_initialized=True,
        timezone_source="manual",
    )
    row = type("Row", (), {"config_value": existing.model_dump(), "version": "v1"})()
    session = _FakeSession(row)
    monkeypatch.setattr(
        "app.services.memory.guardian_policy.get_session_factory",
        lambda: (lambda: _FakeSessionContext(session)),
    )

    result = await ensure_memory_guardian_timezone_initialized(480, source="client_header")

    assert result.timezone_offset_minutes == 300
    assert result.timezone_source == "manual"
    assert session.commit_count == 0
