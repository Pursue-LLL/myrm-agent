"""Unit tests for ShellJobRunner."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.runners import NotificationRunner

from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits.cron.runners import ShellJobRunner
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobType,
    Schedule,
    ScheduleKind,
)

_SCHED = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000)
_NOW = datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)


def _job(
    command: str | None = "echo hello",
    *,
    monitor_config: MonitorConfig | None = None,
    timeout_seconds: int = 300,
) -> CronJob:
    return CronJob(
        id="j1",
        name="test",
        job_type=JobType.SHELL,
        command=command,
        monitor_config=monitor_config,
        timeout_seconds=timeout_seconds,
        schedule=_SCHED,
        delivery=DeliveryConfig(channel="none"),
        created_at=_NOW,
        updated_at=_NOW,
    )


@dataclass
class _ExecResult:
    returncode: int
    stdout: str
    stderr: str


@contextmanager
def _exec_mock(
    *, returncode: int = 0, stdout: str = "", stderr: str = "", side_effect: BaseException | None = None
) -> Iterator[AsyncMock]:
    """Let the safety check pass and answer safe_exec with one outcome; yields the safe_exec mock."""
    outcome = None if side_effect else _ExecResult(returncode=returncode, stdout=stdout, stderr=stderr)
    with (
        patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat", return_value=None),
        patch(
            "myrm_agent_harness.toolkits.cron.runners.safe_exec",
            new_callable=AsyncMock,
            return_value=outcome,
            side_effect=side_effect,
        ) as mock,
    ):
        yield mock


class TestShellJobRunner:
    @pytest.fixture
    def runner(self) -> ShellJobRunner:
        return ShellJobRunner()

    async def test_no_command(self, runner: ShellJobRunner) -> None:
        result = await runner.run(_job(command=None))
        assert result.success is False
        assert "requires a command" in (result.error or "")

    async def test_blocked_command(self, runner: ShellJobRunner) -> None:
        with patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat") as mock_threat:
            mock_threat.return_value = type("Threat", (), {"detail": "dangerous", "evidence": "rm -rf"})()
            result = await runner.run(_job(command="rm -rf /"))
            assert result.success is False
            assert "blocked" in (result.error or "")

    async def test_success_exit_0(self, runner: ShellJobRunner) -> None:
        with (
            patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat", return_value=None),
            patch(
                "myrm_agent_harness.toolkits.cron.runners.safe_exec",
                new_callable=AsyncMock,
                return_value=_ExecResult(returncode=0, stdout="hello\n", stderr=""),
            ),
        ):
            result = await runner.run(_job())
            assert result.success is True
            assert result.exit_code == 0
            assert result.output == "hello\n"

    @pytest.mark.parametrize(
        "monitor_config",
        [None, MonitorConfig(monitor_type="set", enabled=False)],
        ids=["no_monitor", "monitor_disabled"],
    )
    async def test_exit_1_is_a_failure_without_monitoring(
        self, runner: ShellJobRunner, monitor_config: MonitorConfig | None
    ) -> None:
        with _exec_mock(returncode=1, stdout="partial output"):
            result = await runner.run(_job(monitor_config=monitor_config))
        assert result.success is False
        assert result.exit_code == 1
        assert result.error == "exit code 1"
        assert result.output == "partial output"

    async def test_exit_1_error_is_the_stderr_when_there_is_one(self, runner: ShellJobRunner) -> None:
        with _exec_mock(returncode=1, stderr="grep: no match"):
            result = await runner.run(_job())
        assert result.success is False
        assert result.error == "grep: no match"

    async def test_exit_1_is_the_change_signal_with_monitoring(self, runner: ShellJobRunner) -> None:
        with _exec_mock(returncode=1, stdout="diff output"):
            result = await runner.run(_job(monitor_config=MonitorConfig(monitor_type="set", enabled=True)))
        assert result.success is True
        assert result.exit_code == 1
        assert result.output == "diff output"

    async def test_failure_exit_2(self, runner: ShellJobRunner) -> None:
        with (
            patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat", return_value=None),
            patch(
                "myrm_agent_harness.toolkits.cron.runners.safe_exec",
                new_callable=AsyncMock,
                return_value=_ExecResult(returncode=2, stdout="", stderr="error msg"),
            ),
        ):
            result = await runner.run(_job())
            assert result.success is False
            assert result.exit_code == 2

    async def test_exit_0_stays_a_success_with_monitoring(self, runner: ShellJobRunner) -> None:
        with _exec_mock(returncode=0, stdout="nothing new"):
            result = await runner.run(_job(monitor_config=MonitorConfig(monitor_type="set", enabled=True)))
        assert result.success is True
        assert result.exit_code == 0

    async def test_failure_without_stderr_names_the_exit_code(self, runner: ShellJobRunner) -> None:
        with _exec_mock(returncode=2):
            result = await runner.run(_job())
        assert result.success is False
        assert result.error == "exit code 2"

    async def test_command_runs_under_the_jobs_own_timeout(self, runner: ShellJobRunner) -> None:
        with _exec_mock(returncode=0) as exec_mock:
            await runner.run(_job(timeout_seconds=600))
        exec_mock.assert_awaited_once_with("echo hello", timeout=600)

    async def test_timeout_message_names_the_jobs_own_limit(self, runner: ShellJobRunner) -> None:
        with _exec_mock(side_effect=TimeoutError()):
            result = await runner.run(_job(timeout_seconds=45))
        assert result.success is False
        assert result.error == "shell command timed out after 45s"
        assert result.exit_code == 124

    async def test_timeout(self, runner: ShellJobRunner) -> None:
        with (
            patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat", return_value=None),
            patch(
                "myrm_agent_harness.toolkits.cron.runners.safe_exec",
                new_callable=AsyncMock,
                side_effect=TimeoutError(),
            ),
        ):
            result = await runner.run(_job())
            assert result.success is False
            assert result.exit_code == 124

    async def test_unexpected_exception(self, runner: ShellJobRunner) -> None:
        with (
            patch("myrm_agent_harness.toolkits.cron.runners.has_block_threat", return_value=None),
            patch(
                "myrm_agent_harness.toolkits.cron.runners.safe_exec",
                new_callable=AsyncMock,
                side_effect=OSError("permission denied"),
            ),
        ):
            result = await runner.run(_job())
            assert result.success is False
            assert "permission denied" in (result.error or "")


class TestNotificationRunner:
    @pytest.fixture
    def runner(self) -> NotificationRunner:
        from myrm_agent_harness.toolkits.cron.runners import NotificationRunner

        return NotificationRunner()

    async def test_delivers_prompt(self, runner: NotificationRunner) -> None:
        job = CronJob(
            id="r1",
            name="reminder",
            job_type=JobType.REMINDER,
            prompt="Stand up now",
            schedule=_SCHED,
            delivery=DeliveryConfig(channel="none"),
            created_at=_NOW,
            updated_at=_NOW,
        )
        result = await runner.run(job)
        assert result.success is True
        assert result.output == "Stand up now"
        assert result.exit_code == 1

    async def test_missing_prompt(self, runner: NotificationRunner) -> None:
        job = CronJob(
            id="r2",
            name="reminder",
            job_type=JobType.REMINDER,
            prompt=None,
            schedule=_SCHED,
            delivery=DeliveryConfig(channel="none"),
            created_at=_NOW,
            updated_at=_NOW,
        )
        result = await runner.run(job)
        assert result.success is False
        assert "prompt" in (result.error or "").lower()
