"""Tests for cron execution policy (lifecycle guard, tools policy, REST guards)."""

from __future__ import annotations

from typing import Generator
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.core.cron.adapters.lifecycle_guard import (
    assert_cron_job_lifecycle_safe,
    contains_myrm_lifecycle_command,
)
from app.core.cron.adapters.tools_policy import (
    intersect_cron_enabled_builtin_tools,
    normalize_cron_tools_allowed,
)
from app.services.agent.builtin_tool_ids import InvalidBuiltinToolIdsError
from app.services.agent.profile_resolver import apply_agent_baseline_tool_flags, resolve_builtin_tool_flags


class FakeDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        pass


@pytest.fixture
def guarded_cron_client() -> Generator[TestClient, None, None]:
    from app.api.cron.routes import helpers, router

    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=FakeDelivery(), config=CronConfig())
    inner = CronManager(store, scheduler, shell_enabled=True)
    manager = EntitlementGuardedCronManager(inner)

    app = FastAPI()
    app.include_router(router, prefix="/cron")

    with patch.object(helpers, "_get_manager", return_value=manager):
        yield TestClient(app)


class TestLifecycleGuard:
    def test_detects_myrm_restart(self) -> None:
        assert contains_myrm_lifecycle_command("./myrm restart --chrome") is True

    def test_assert_rejects_restart_in_prompt(self) -> None:
        with pytest.raises(ValueError, match="lifecycle commands"):
            assert_cron_job_lifecycle_safe(prompt="Run ./myrm restart nightly", command=None)


class TestToolsPolicy:
    def test_normalize_strips_cron(self) -> None:
        assert normalize_cron_tools_allowed(["web_search", "cron"]) == ("web_search",)

    def test_normalize_rejects_unknown(self) -> None:
        with pytest.raises(InvalidBuiltinToolIdsError):
            normalize_cron_tools_allowed(["web_fetch"])

    def test_intersect_restricts_agent_tools(self) -> None:
        agent_tools = ["web_search", "memory", "wiki", "cron"]
        result = intersect_cron_enabled_builtin_tools(agent_tools, ("web_search",))
        assert result == ["web_search"]

    def test_normalize_keeps_baseline_file_ops(self) -> None:
        assert normalize_cron_tools_allowed(["file_ops"]) == ("file_ops",)

    def test_intersect_includes_baseline_when_allowed(self) -> None:
        result = intersect_cron_enabled_builtin_tools(
            ["web_search", "memory"],
            ("file_ops",),
        )
        assert result == ["file_ops"]

    def test_cron_run_flags_exclude_cron_eager(self) -> None:
        tools = intersect_cron_enabled_builtin_tools(
            ["web_search", "memory", "cron"],
            ("web_search",),
        )
        flags = apply_agent_baseline_tool_flags(resolve_builtin_tool_flags(tools))
        assert flags["enable_cron_eager"] is False
        assert flags["enable_file_ops"] is True


class TestCronExecutionPolicyApi:
    def test_read_it_later_fill_then_create(self, guarded_cron_client: TestClient) -> None:
        fill_resp = guarded_cron_client.post(
            "/cron/blueprints/fill",
            json={"blueprint_id": "read_it_later", "values": {"time": "06:00"}, "locale": "en"},
        )
        assert fill_resp.status_code == 200, fill_resp.text
        fill_data = fill_resp.json()
        assert fill_data["tools_allowed"] == ["file_ops"]

        create_resp = guarded_cron_client.post(
            "/cron",
            json={
                "name": fill_data["name"],
                "job_type": "agent",
                "schedule": fill_data["schedule"],
                "prompt": fill_data["prompt"],
                "tools_allowed": fill_data["tools_allowed"],
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        assert create_resp.json()["tools_allowed"] == ["file_ops"]

    def test_create_rejects_myrm_restart_prompt(self, guarded_cron_client: TestClient) -> None:
        resp = guarded_cron_client.post(
            "/cron",
            json={
                "name": "Bad restart job",
                "job_type": "agent",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                "prompt": "Please run ./myrm restart every night",
            },
        )
        assert resp.status_code == 400
        assert "lifecycle" in resp.json()["detail"].lower()

    def test_patch_tools_allowed_roundtrip(self, guarded_cron_client: TestClient) -> None:
        create_resp = guarded_cron_client.post(
            "/cron",
            json={
                "name": "Tool scope job",
                "job_type": "agent",
                "schedule": {"kind": "cron", "expr": "0 10 * * *"},
                "prompt": "Summarize inbox",
                "tools_allowed": ["web_search"],
            },
        )
        assert create_resp.status_code == 201
        job_id = create_resp.json()["id"]

        patch_resp = guarded_cron_client.patch(
            f"/cron/{job_id}",
            json={"tools_allowed": ["web_search", "memory"]},
        )
        assert patch_resp.status_code == 200
        assert set(patch_resp.json()["tools_allowed"]) == {"web_search", "memory"}

        clear_resp = guarded_cron_client.patch(f"/cron/{job_id}", json={"tools_allowed": []})
        assert clear_resp.status_code == 200
        assert clear_resp.json()["tools_allowed"] == []
