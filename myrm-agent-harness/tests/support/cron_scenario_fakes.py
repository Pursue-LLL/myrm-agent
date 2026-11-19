"""Fake runners and a recording delivery for the cron real-scenario tests.

[INPUT]
- toolkits.cron.types::CronJob, JobResult (POS: the job a runner receives and the result it returns)

[OUTPUT]
- FakeAgentRunner: an agent runner that returns a fixed response (or a fixed failure) and counts its calls
- FakeShellRunner: a shell runner that returns a fixed output and exit code and counts its calls
- FakeDelivery: a delivery that records every `(job, result)` it is asked to deliver

[POS]
Pytest-only helper shared by the real-scenario lifecycle, delivery-and-tick and tracing tests, which run a real
`InMemoryCronStore`, manager, executor and scheduler against these fakes instead of mocking them.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult


class FakeAgentRunner:
    """Simulates an agent runner that returns a fixed response."""

    def __init__(self, output: str = "Agent completed task", success: bool = True) -> None:
        self._output = output
        self._success = success
        self.call_count = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.call_count += 1
        return JobResult(
            success=self._success,
            output=self._output,
            error=None if self._success else "Agent failed",
        )


class FakeShellRunner:
    """Simulates a shell runner."""

    def __init__(self, output: str = "shell output", exit_code: int = 0) -> None:
        self._output = output
        self._exit_code = exit_code
        self.call_count = 0

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.call_count += 1
        return JobResult(
            success=self._exit_code == 0,
            output=self._output,
            exit_code=self._exit_code,
            error=f"exit code {self._exit_code}" if self._exit_code != 0 else None,
        )


class FakeDelivery:
    """Captures delivered results for assertion."""

    def __init__(self) -> None:
        self.deliveries: list[tuple[CronJob, JobResult]] = []

    async def deliver(self, job: CronJob, result: JobResult) -> None:
        self.deliveries.append((job, result))
