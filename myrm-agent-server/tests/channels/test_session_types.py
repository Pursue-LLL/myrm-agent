"""Tests for session types — SessionKey, SessionPolicy, compute_daily_epoch."""

from __future__ import annotations

from app.channels.types.session import (
    SessionKey,
    SessionPolicy,
    SessionResetMode,
    compute_daily_epoch,
)


class TestSessionKey:
    def test_to_str_basic(self) -> None:
        key = SessionKey(channel="slack", peer_kind="dm", peer_id="peer1")
        assert key.to_str() == "slack:dm:peer1"

    def test_to_str_with_thread(self) -> None:
        key = SessionKey(
            channel="slack",
            peer_kind="dm",
            peer_id="peer1",
            thread_id="t1",
        )
        assert key.to_str() == "slack:dm:peer1:thread:t1"

    def test_to_str_with_agent(self) -> None:
        key = SessionKey(
            channel="slack",
            peer_kind="dm",
            peer_id="peer1",
            agent_id="a1",
        )
        assert key.to_str() == "slack:dm:peer1:agent:a1"

    def test_to_str_with_thread_and_agent(self) -> None:
        key = SessionKey(
            channel="slack",
            peer_kind="dm",
            peer_id="peer1",
            thread_id="t1",
            agent_id="a1",
        )
        result = key.to_str()
        assert "thread:t1" in result
        assert "agent:a1" in result

    def test_to_str_sanitizes_special_chars(self) -> None:
        key = SessionKey(channel="sl ack", peer_kind="dm", peer_id="pe.er")
        result = key.to_str()
        assert " " not in result
        assert "." not in result

    def test_to_str_lowercases(self) -> None:
        key = SessionKey(channel="SLACK", peer_kind="dm", peer_id="PEER1")
        assert key.to_str() == "slack:dm:peer1"

    def test_parse_basic(self) -> None:
        key = SessionKey.parse("slack:dm:peer1")
        assert key is not None
        assert key.channel == "slack"
        assert key.peer_kind == "dm"
        assert key.peer_id == "peer1"
        assert key.thread_id is None
        assert key.agent_id is None

    def test_parse_with_thread(self) -> None:
        key = SessionKey.parse("slack:dm:peer1:thread:t1")
        assert key is not None
        assert key.thread_id == "t1"

    def test_parse_with_agent(self) -> None:
        key = SessionKey.parse("slack:dm:peer1:agent:a1")
        assert key is not None
        assert key.agent_id == "a1"

    def test_parse_with_thread_and_agent(self) -> None:
        key = SessionKey.parse("slack:dm:peer1:thread:t1:agent:a1")
        assert key is not None
        assert key.thread_id == "t1"
        assert key.agent_id == "a1"

    def test_parse_too_short(self) -> None:
        assert SessionKey.parse("a:b") is None

    def test_parse_empty(self) -> None:
        assert SessionKey.parse("") is None

    def test_roundtrip(self) -> None:
        original = SessionKey(
            channel="slack",
            peer_kind="dm",
            peer_id="peer1",
            thread_id="t1",
            agent_id="a1",
        )
        serialized = original.to_str()
        parsed = SessionKey.parse(serialized)
        assert parsed is not None
        assert parsed.channel == "slack"
        assert parsed.thread_id == "t1"
        assert parsed.agent_id == "a1"


class TestSessionPolicy:
    def test_defaults(self) -> None:
        policy = SessionPolicy()
        assert policy.mode == SessionResetMode.DAILY
        assert policy.daily_reset_hour == 4
        assert policy.idle_minutes == 120
        assert policy.notify_on_reset is True

    def test_custom(self) -> None:
        policy = SessionPolicy(mode=SessionResetMode.IDLE, idle_minutes=30)
        assert policy.mode == SessionResetMode.IDLE
        assert policy.idle_minutes == 30

    def test_notify_on_reset_disabled(self) -> None:
        policy = SessionPolicy(notify_on_reset=False)
        assert policy.notify_on_reset is False

    def test_notify_on_reset_enabled_explicit(self) -> None:
        policy = SessionPolicy(notify_on_reset=True)
        assert policy.notify_on_reset is True


class TestSessionResetMode:
    def test_values(self) -> None:
        assert SessionResetMode.PERSISTENT == "persistent"
        assert SessionResetMode.DAILY == "daily"
        assert SessionResetMode.IDLE == "idle"


class TestComputeDailyEpoch:
    def test_returns_iso_format(self) -> None:
        result = compute_daily_epoch(4)
        assert len(result) == 10
        assert result.count("-") == 2

    def test_same_epoch_within_day(self) -> None:
        r1 = compute_daily_epoch(4)
        r2 = compute_daily_epoch(4)
        assert r1 == r2

    def test_different_reset_hours(self) -> None:
        r0 = compute_daily_epoch(0)
        r23 = compute_daily_epoch(23)
        assert isinstance(r0, str)
        assert isinstance(r23, str)

    def test_epoch_is_valid_date(self) -> None:
        result = compute_daily_epoch(4)
        parts = result.split("-")
        assert len(parts) == 3
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        assert 2020 <= year <= 2030
        assert 1 <= month <= 12
        assert 1 <= day <= 31
