"""Tests for the read-only research lease policy of unattended cron runs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from myrm_agent_harness.core.security.readonly_research_sandbox import (
    DEFAULT_READ_ONLY_TOOLS,
    LeaseStatusEnum,
    get_readonly_research_sandbox_facade,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.research_lease import (
    grant_run_lease,
    is_read_only_job,
    release_run_lease,
)


@dataclass
class _FakeAgent:
    approval_session_key: str | None = "cron:job-1"


def _job(*capabilities: str, timeout_seconds: int = 300) -> CronJob:
    return CronJob(  # type: ignore[arg-type]
        id="job-1",
        user_id="user-1",
        name="Research digest",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        status=JobStatus.ACTIVE,
        prompt="Summarise the news.",
        delivery=DeliveryConfig(channel="chat"),
        required_capabilities=capabilities,
        timeout_seconds=timeout_seconds,
    )


@pytest.fixture
def granted_keys() -> Iterator[list[str]]:
    """Leases a test grants live in the process-wide facade, so every one is released afterwards."""
    keys: list[str] = []
    yield keys
    for key in keys:
        release_run_lease(key)


@pytest.mark.parametrize(
    ("capabilities", "expected"),
    [
        ((), True),
        (("file_read",), True),
        (("web_search_tool", "net_fetch", "file_read"), True),
        (("file_read", "file_write"), False),
        (("shell_exec",), False),
        (("code_interpreter",), False),
        (("knowledge_read",), False),
        (("*",), False),
    ],
)
def test_is_read_only_job_accepts_only_capabilities_the_lease_permits(capabilities: tuple[str, ...], expected: bool) -> None:
    assert is_read_only_job(capabilities) is expected


def test_read_only_job_runs_under_a_private_lease(granted_keys: list[str]) -> None:
    agent = _FakeAgent()

    key = grant_run_lease(agent, _job("web_search_tool", "net_fetch", "file_read"), timeout_seconds=300, untrusted=False)

    assert key is not None
    granted_keys.append(key)
    assert key.startswith("cron:job-1:")
    assert agent.approval_session_key == key
    facade = get_readonly_research_sandbox_facade()
    lease = facade.get_lease(key)
    assert lease is not None
    assert lease.status == LeaseStatusEnum.ACTIVE
    assert lease.allowed_tools == DEFAULT_READ_ONLY_TOOLS
    assert facade.evaluate_tool(key, "file_read_tool")[0] is True
    assert facade.evaluate_tool(key, "file_write_tool")[0] is False
    assert facade.evaluate_tool(key, "mcp__mail__send")[0] is False


def test_lease_outlives_the_run_timeout_by_a_grace_period(granted_keys: list[str]) -> None:
    key = grant_run_lease(_FakeAgent(), _job(), timeout_seconds=120, untrusted=False)

    assert key is not None
    granted_keys.append(key)
    lease = get_readonly_research_sandbox_facade().get_lease(key)
    assert lease is not None
    assert lease.expires_at - lease.granted_at == pytest.approx(180.0)


def test_job_declaring_a_mutating_capability_gets_no_lease() -> None:
    agent = _FakeAgent()

    key = grant_run_lease(agent, _job("shell_exec", "file_read"), timeout_seconds=300, untrusted=False)

    assert key is None
    assert agent.approval_session_key == "cron:job-1"
    assert get_readonly_research_sandbox_facade().get_lease("cron:job-1") is None


def test_untrusted_sender_forces_the_lease_even_for_a_mutating_job(granted_keys: list[str]) -> None:
    agent = _FakeAgent()

    key = grant_run_lease(agent, _job("shell_exec", "file_write"), timeout_seconds=300, untrusted=True)

    assert key is not None
    granted_keys.append(key)
    assert agent.approval_session_key == key
    assert get_readonly_research_sandbox_facade().evaluate_tool(key, "bash_code_execute_tool")[0] is False


def test_overlapping_runs_of_one_job_do_not_revoke_each_others_lease(granted_keys: list[str]) -> None:
    facade = get_readonly_research_sandbox_facade()
    owner_agent, stranger_agent = _FakeAgent(), _FakeAgent()
    owner_key = grant_run_lease(owner_agent, _job(), timeout_seconds=300, untrusted=False)
    stranger_key = grant_run_lease(stranger_agent, _job("shell_exec"), timeout_seconds=300, untrusted=True)
    assert owner_key is not None
    assert stranger_key is not None
    assert owner_key != stranger_key
    granted_keys.extend([owner_key, stranger_key])

    release_run_lease(owner_key)

    assert facade.get_lease(owner_key) is None
    stranger_lease = facade.get_lease(stranger_key)
    assert stranger_lease is not None
    assert stranger_lease.status == LeaseStatusEnum.ACTIVE
    assert facade.evaluate_tool(stranger_key, "file_write_tool")[0] is False


def test_release_forgets_the_lease() -> None:
    facade = get_readonly_research_sandbox_facade()
    key = grant_run_lease(_FakeAgent(), _job(), timeout_seconds=300, untrusted=False)
    assert key is not None

    release_run_lease(key)

    assert facade.get_lease(key) is None
    assert facade.evaluate_tool(key, "file_write_tool")[0] is True


def test_release_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    facade = get_readonly_research_sandbox_facade()

    def _boom(_session_id: str) -> None:
        raise RuntimeError("registry down")

    monkeypatch.setattr(facade, "revoke_lease", _boom)

    release_run_lease("cron:job-1:never-granted")
