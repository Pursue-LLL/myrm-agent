"""ServerSkillExecutionProvider: sources that are not wired report empty results, not errors."""

from __future__ import annotations

import logging

import pytest

from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider


@pytest.mark.asyncio
async def test_unwired_sources_report_empty_results() -> None:
    provider = ServerSkillExecutionProvider()

    assert await provider.get_all_skill_ids() == []
    assert await provider.get_skill_executions("demo-skill") == []
    assert await provider.count_executions("demo-skill") == 0
    assert await provider.get_skill_metadata("demo-skill") is None


@pytest.mark.asyncio
async def test_looking_up_metadata_is_not_logged_as_an_error(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        await ServerSkillExecutionProvider().get_skill_metadata("demo-skill")

    assert not caplog.records
