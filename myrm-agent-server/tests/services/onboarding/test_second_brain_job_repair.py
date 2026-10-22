"""Tests for the startup repair of a Second Brain wiki-delta job created before its capability fix."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobType

from app.config.settings import settings
from app.services.onboarding.second_brain_job_repair import repair_wiki_delta_job

_NEW_CAPABILITIES = ("file_read", "knowledge_read", "knowledge_write")


def _job(
    *,
    capabilities: tuple[str, ...],
    allowed_roots: tuple[str, ...] = (),
    job_type: JobType = JobType.AGENT,
    agent_id: str | None = "agent-sb",
) -> SimpleNamespace:
    return SimpleNamespace(
        id="job-delta",
        job_type=job_type,
        required_capabilities=capabilities,
        allowed_roots=allowed_roots,
        agent_id=agent_id,
    )


def _manager(job: SimpleNamespace | None) -> SimpleNamespace:
    return SimpleNamespace(get_job=AsyncMock(return_value=job), update_job=AsyncMock())


async def _repair(mgr: SimpleNamespace) -> bool:
    with patch("app.services.onboarding.second_brain_job_repair.get_cron_manager", return_value=mgr):
        return await repair_wiki_delta_job("job-delta", user_id="default")


@pytest.fixture(autouse=True)
def _harness_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.database, "harness_dir", str(tmp_path))


async def test_superseded_declaration_gets_wiki_capabilities_and_vault_root(tmp_path: Path) -> None:
    mgr = _manager(_job(capabilities=("file_write", "file_read")))

    assert await _repair(mgr) is True

    vault = str(tmp_path.resolve() / "wiki" / "agents" / "agent-sb")
    mgr.update_job.assert_awaited_once_with(
        "job-delta",
        "default",
        CronJobPatch(required_capabilities=_NEW_CAPABILITIES, allowed_roots=(vault,)),
    )


async def test_existing_allowed_roots_are_kept() -> None:
    mgr = _manager(_job(capabilities=("file_read", "file_write"), allowed_roots=("/data/my-vault",)))

    assert await _repair(mgr) is True

    patch_arg = mgr.update_job.await_args.args[2]
    assert patch_arg.allowed_roots == ("/data/my-vault",)
    assert patch_arg.required_capabilities == _NEW_CAPABILITIES


@pytest.mark.parametrize(
    "capabilities",
    [
        _NEW_CAPABILITIES,
        ("file_read",),
        ("file_read", "file_write", "net_fetch"),
        (),
    ],
)
async def test_declaration_not_equal_to_the_superseded_one_is_left_alone(capabilities: tuple[str, ...]) -> None:
    mgr = _manager(_job(capabilities=capabilities))

    assert await _repair(mgr) is False

    mgr.update_job.assert_not_awaited()


async def test_repair_is_idempotent() -> None:
    job = _job(capabilities=("file_read", "file_write"))
    mgr = _manager(job)

    assert await _repair(mgr) is True
    job.required_capabilities = _NEW_CAPABILITIES

    assert await _repair(mgr) is False
    assert mgr.update_job.await_count == 1


async def test_missing_or_non_agent_job_is_ignored() -> None:
    assert await _repair(_manager(None)) is False
    router_job = _job(capabilities=("file_read", "file_write"), job_type=JobType.ROUTER)
    mgr = _manager(router_job)

    assert await _repair(mgr) is False
    mgr.update_job.assert_not_awaited()
