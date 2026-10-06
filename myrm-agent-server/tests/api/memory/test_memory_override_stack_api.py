"""
[POS] tests/api/memory/test_memory_override_stack_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.override_stack_router, app.services.memory.memory_override_stack_service
[OUTPUT] test_override_stack_ephemeral_bypass_api, test_override_stack_explicit_rule_id_bypass_api, test_override_stack_no_conflicts_pass_through_api, test_override_stack_empty_rules_api

Unit test suite for Playbook Dynamic User Override Stack and Ephemeral Bypass Gate API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.override_stack_router import (
    router as memory_override_stack_router,
)
from app.services.memory.memory_override_stack_service import (
    MemoryOverrideStackService,
    get_memory_override_stack_service,
)


@pytest.fixture
def override_stack_test_client() -> Generator[
    tuple[TestClient, MemoryOverrideStackService], None, None
]:
    """Provide isolated TestClient mounting override stack router with a clean service instance."""
    service = MemoryOverrideStackService()

    test_app = FastAPI()
    test_app.include_router(
        memory_override_stack_router, prefix="/api/memory"
    )
    test_app.dependency_overrides[get_memory_override_stack_service] = (
        lambda: service
    )

    with TestClient(test_app) as client:
        yield client, service


def test_override_stack_ephemeral_bypass_api(
    override_stack_test_client: tuple[TestClient, MemoryOverrideStackService],
) -> None:
    """Verify POST /api/memory/override-stack/evaluate temporarily bypasses conflicting rules."""
    client, _ = override_stack_test_client

    payload = {
        "turn_prompt": "本次遗留脚本数据清洗必须使用 lodash 进行深度复制",
        "candidate_rules": [
            {
                "id": "rule_no_lodash",
                "action": "一律使用原生函数，严禁引入 lodash",
                "content": "禁止使用 lodash 库",
                "facets": ["coding"],
                "is_active": True,
            },
            {
                "id": "rule_format_json",
                "action": "统一格式化 JSON 输出",
                "content": "使用 2 空格缩进",
                "facets": ["coding"],
                "is_active": True,
            },
        ],
    }

    res = client.post("/api/memory/override-stack/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["has_conflicts"] is True
    assert data["active_rule_ids"] == ["rule_format_json"]
    assert len(data["bypassed_records"]) == 1
    bypassed = data["bypassed_records"][0]
    assert bypassed["rule_id"] == "rule_no_lodash"
    assert bypassed["bypassed_in_current_turn"] is True
    assert "lodash" in bypassed["bypass_reason"].lower()
    assert "规约单次豁免注记" in data["injected_context_note"]
    assert "rule_no_lodash" in data["injected_context_note"]


def test_override_stack_explicit_rule_id_bypass_api(
    override_stack_test_client: tuple[TestClient, MemoryOverrideStackService],
) -> None:
    """Verify explicit bypass of a specific rule ID relieves the restriction in API."""
    client, _ = override_stack_test_client

    payload = {
        "turn_prompt": "本次测试紧急请跳过规则: rule_deploy_safe，继续构建",
        "candidate_rules": [
            {
                "id": "rule_deploy_safe",
                "action": "生产环境部署必须等待审批",
                "content": "部署安全红线",
                "facets": ["devops"],
                "is_active": True,
            },
            {
                "id": "rule_lint",
                "action": "提交前运行 ruff",
                "content": "代码质量门禁",
                "facets": ["coding"],
                "is_active": True,
            },
        ],
    }

    res = client.post("/api/memory/override-stack/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["has_conflicts"] is True
    assert "rule_deploy_safe" not in data["active_rule_ids"]
    assert "rule_lint" in data["active_rule_ids"]
    assert data["bypassed_records"][0]["rule_id"] == "rule_deploy_safe"


def test_override_stack_no_conflicts_pass_through_api(
    override_stack_test_client: tuple[TestClient, MemoryOverrideStackService],
) -> None:
    """Verify unconflicted prompt preserves all rules without bypass notes."""
    client, _ = override_stack_test_client

    payload = {
        "turn_prompt": "请帮我重构一下函数变量命名",
        "candidate_rules": [
            {
                "id": "rule_1",
                "action": "严禁引入 lodash",
                "content": "禁止 lodash",
                "facets": ["coding"],
                "is_active": True,
            },
        ],
    }

    res = client.post("/api/memory/override-stack/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["has_conflicts"] is False
    assert data["active_rule_ids"] == ["rule_1"]
    assert data["bypassed_records"] == []
    assert data["injected_context_note"] == ""


def test_override_stack_empty_rules_api(
    override_stack_test_client: tuple[TestClient, MemoryOverrideStackService],
) -> None:
    """Verify empty candidate rules list evaluates cleanly."""
    client, _ = override_stack_test_client

    payload = {
        "turn_prompt": "任意普通对话",
        "candidate_rules": [],
    }

    res = client.post("/api/memory/override-stack/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["has_conflicts"] is False
    assert data["active_rule_ids"] == []
    assert data["bypassed_records"] == []
    assert data["injected_context_note"] == ""
