"""Tests for core/channel_bridge/turn_handler.py — _revert_messages."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest


class TestRevertMessages:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_zero(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        result = await _revert_messages("session-1", [])
        assert result.reverted_count == 0
        assert result.not_revertible_count == 0

    @pytest.mark.asyncio
    async def test_counts_reverted_files(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result_1 = _FakeRevertResult(reverted_files=["a.py", "b.py"], warnings=[])
        mock_result_2 = _FakeRevertResult(reverted_files=["c.py"], warnings=[])

        with (
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.revert_message",
                new_callable=AsyncMock,
                side_effect=[mock_result_1, mock_result_2],
            ),
            patch(
                "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            total = await _revert_messages("session-1", ["msg-1", "msg-2"])

        assert total.reverted_count == 3
        assert mock_cleanup.await_count == 2
        mock_cleanup.assert_any_await("session-1", "msg-1")
        mock_cleanup.assert_any_await("session-1", "msg-2")

    @pytest.mark.asyncio
    async def test_notifies_agent_when_files_reverted(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(reverted_files=["a.py", "b.py"], warnings=[])

        with (
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.revert_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.files.revert_agent_notify.notify_agent_of_turn_revert",
            ) as mock_notify,
        ):
            outcome = await _revert_messages("session-1", ["msg-1"])

        assert outcome.reverted_count == 2
        mock_notify.assert_called_once_with(
            session_id="session-1",
            message_id=None,
            reverted_files=["a.py", "b.py"],
        )

    @pytest.mark.asyncio
    async def test_skips_agent_notify_when_nothing_reverted(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(reverted_files=[], warnings=["no snapshots"])

        with (
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.revert_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "app.services.files.revert_agent_notify.notify_agent_of_turn_revert",
            ) as mock_notify,
        ):
            await _revert_messages("session-1", ["msg-1"])

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_cleanup_when_nothing_reverted(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(reverted_files=[], warnings=["no snapshots"])

        with (
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.revert_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            total = await _revert_messages("session-1", ["msg-1"])

        assert total.reverted_count == 0
        mock_cleanup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logs_warnings(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(
            reverted_files=["a.py"],
            warnings=["snapshot missing for b.py"],
        )

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_revert:
            total = await _revert_messages("s1", ["m1"])

        assert total.reverted_count == 1
        mock_revert.assert_awaited_once_with("s1", "m1")

    @pytest.mark.asyncio
    async def test_exception_on_one_message_continues(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        ok_result = _FakeRevertResult(reverted_files=["a.py"], warnings=[])

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("disk full"), ok_result],
        ):
            total = await _revert_messages("s1", ["m-bad", "m-ok"])

        assert total.reverted_count == 1

    @pytest.mark.asyncio
    async def test_counts_not_revertible_files(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeChange:
            path: str
            revertible: bool

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(reverted_files=[], warnings=["not revertible"])

        with (
            patch(
                "app.services.files.revert_hydrate.ensure_session_snapshots_hydrated",
                new_callable=AsyncMock,
            ),
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.get_message_changes",
                new_callable=AsyncMock,
                return_value=[_FakeChange(path="/big.log", revertible=False)],
            ),
            patch(
                "app.core.channel_bridge.turn_handler.RevertService.revert_message",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            outcome = await _revert_messages("s1", ["m1"])

        assert outcome.reverted_count == 0
        assert outcome.not_revertible_count == 1

    @pytest.mark.asyncio
    async def test_all_fail_returns_zero(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("nope"),
        ):
            total = await _revert_messages("s1", ["m1", "m2"])

        assert total.reverted_count == 0
