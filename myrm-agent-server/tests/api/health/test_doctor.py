"""System API Integration Tests

测试 /api/v1/health/doctor 端点，验证数据库和 Harness 探针能否真实返回正确健康报告。
Harness 探针注册回归：HookSystem、DesktopControl（见 test_*_probe_in_doctor）。
"""

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")
@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.e2e
def test_system_doctor_endpoint(client: TestClient):
    """测试 /api/v1/system/doctor 能够返回聚合健康报告"""
    response = client.get("/api/v1/health/doctor")

    assert response.status_code == 200, f"Doctor check failed: {response.text}"

    data = response.json()

    # 验证响应结构
    assert "server" in data
    assert "harness" in data
    assert "repair_actions" in data

    server_reports = data["server"]
    harness_reports = data["harness"]

    # 验证 server 侧报告结构
    assert isinstance(server_reports, list)
    # Server层主要检查DLQ等业务组件,不再检查Database (已移至Harness层)

    # 验证 harness 侧报告至少包含我们内置的几个核心探针
    assert isinstance(harness_reports, list)
    assert len(harness_reports) >= 3, "Harness reports should contain built-in probes"

    component_names = [r["component_name"] for r in harness_reports]
    assert "Network" in component_names or "check_network_health" in component_names, (
        "Network/check_network_health probe should be registered"
    )
    assert "WorkspaceStorage" in component_names, "WorkspaceStorage probe should be registered"
    assert "Database" in component_names, "Database probe should be registered in Harness layer"

    # 验证 Database 报告在 Harness 层
    db_report = next((r for r in harness_reports if r["component_name"] == "Database"), None)
    assert db_report is not None, "Database report is missing from harness reports"
    assert db_report["status"] in ["pass", "fail"], "Database report status is invalid"

    # 验证真实测试环境下的默认状态（通常应该是 pass，但也可能因特定环境抛出 fail，这符合真实探测预期）
    for report in harness_reports:
        assert report["status"] in ["pass", "fail", "warn"]
        assert "message" in report
        assert "detail" in report, f"Missing 'detail' field in report for {report['component_name']}"

    # 验证 repair_actions 结构（列表，每个 action 有必需字段）
    repair_actions = data["repair_actions"]
    assert isinstance(repair_actions, list)
    for action in repair_actions:
        assert "action_id" in action
        assert "title" in action
        assert "executable" in action
        assert "risk_level" in action
        assert "reason" in action
        assert "description" in action
        assert "component" in action
        assert "layer" in action
        assert "scope" in action
        assert "expected_effect" in action
        assert "does_not_do" in action
        assert isinstance(action["does_not_do"], list)
        assert action["risk_level"] in ("low", "medium", "high")


@pytest.mark.e2e
def test_repair_action_execute_advisory_only(client: TestClient):
    """Advisory-only repair actions should return not_executable."""
    response = client.post(
        "/api/v1/health/repair-actions/review_runtime_dependency/execute",
        json={"dry_run": False, "confirm": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_executable"
    assert data["changed"] is False
    assert data["action_id"] == "review_runtime_dependency"


@pytest.mark.e2e
def test_repair_action_execute_invalid_action_id(client: TestClient):
    """Invalid action_id should return 422."""
    response = client.post(
        "/api/v1/health/repair-actions/nonexistent_action/execute",
        json={"dry_run": True, "confirm": False},
    )
    assert response.status_code == 422


@pytest.mark.e2e
def test_repair_action_execute_workspace_storage_advisory(client: TestClient):
    """REVIEW_WORKSPACE_STORAGE is advisory, should return not_executable."""
    response = client.post(
        "/api/v1/health/repair-actions/review_workspace_storage/execute",
        json={"dry_run": False, "confirm": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_executable"


@pytest.mark.e2e
def test_doctor_response_layers_independent(client: TestClient):
    """Server and harness reports should be independent lists."""
    response = client.get("/api/v1/health/doctor")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["server"], list)
    assert isinstance(data["harness"], list)
    assert isinstance(data["repair_actions"], list)
    server_components = {r["component_name"] for r in data["server"]}
    harness_components = {r["component_name"] for r in data["harness"]}
    assert not server_components.intersection(harness_components), "Server and Harness should not share components"


@pytest.mark.e2e
def test_hook_system_probe_in_doctor(client: TestClient):
    """HookSystem diagnostic probe should appear in harness reports via doctor API."""
    response = client.get("/api/v1/health/doctor")
    assert response.status_code == 200

    data = response.json()
    harness_reports = data["harness"]
    component_names = [r["component_name"] for r in harness_reports]

    assert "HookSystem" in component_names, (
        f"HookSystem probe missing from doctor response. Found: {component_names}"
    )

    hook_report = next(r for r in harness_reports if r["component_name"] == "HookSystem")
    assert hook_report["status"] in ("pass", "warn", "fail")
    assert "message" in hook_report
    assert hook_report["message"] != ""


@pytest.mark.e2e
def test_desktop_control_probe_in_doctor(client: TestClient):
    """DesktopControl diagnostic probe should appear in harness reports via doctor API."""
    response = client.get("/api/v1/health/doctor")
    assert response.status_code == 200

    data = response.json()
    harness_reports = data["harness"]
    component_names = [r["component_name"] for r in harness_reports]

    assert "DesktopControl" in component_names, (
        f"DesktopControl probe missing from doctor response. Found: {component_names}"
    )

    desktop_report = next(r for r in harness_reports if r["component_name"] == "DesktopControl")
    assert desktop_report["status"] in ("pass", "warn", "fail")
    assert "message" in desktop_report
    assert desktop_report["message"] != ""
    assert desktop_report.get("code") in (
        "OK_DESKTOP_PERMISSIONS",
        "WARN_DESKTOP_PERMISSIONS_MISSING",
        "OK_DESKTOP_SANDBOX_VNC",
        "WARN_DESKTOP_SANDBOX_UNAVAILABLE",
        "ERR_DESKTOP_PERMISSIONS_PROBE",
    )


@pytest.mark.e2e
def test_hook_system_probe_idle_without_executor(client: TestClient):
    """When no HookExecutor is set, HookSystem probe should report 'idle'."""
    from myrm_agent_harness.agent.hooks.executor import get_hook_executor, set_hook_executor

    prev = get_hook_executor()
    set_hook_executor(None)
    try:
        response = client.get("/api/v1/health/doctor")
        assert response.status_code == 200
        hook_report = next(
            r for r in response.json()["harness"] if r["component_name"] == "HookSystem"
        )
        assert hook_report["status"] == "pass"
        assert "idle" in hook_report["message"].lower()
    finally:
        set_hook_executor(prev)


@pytest.mark.e2e
def test_hook_system_probe_with_hooks_registered(client: TestClient):
    """When hooks are registered, HookSystem probe should report healthy with count."""
    from myrm_agent_harness.agent.hooks import (
        CommandHookDefinition,
        HookEvent,
        HookExecutor,
        HookRegistry,
        set_hook_executor,
    )
    from myrm_agent_harness.agent.hooks.executor import get_hook_executor

    prev = get_hook_executor()
    registry = HookRegistry()
    registry.register(HookEvent.PRE_TOOL_USE, CommandHookDefinition(command="echo test"))
    executor = HookExecutor(registry)
    set_hook_executor(executor)
    try:
        response = client.get("/api/v1/health/doctor")
        assert response.status_code == 200
        hook_report = next(
            r for r in response.json()["harness"] if r["component_name"] == "HookSystem"
        )
        assert hook_report["status"] == "pass"
        assert "healthy" in hook_report["message"].lower()
        assert "1 hook(s) active" in hook_report["message"]
        assert hook_report["detail"] is not None
        assert "500ms" in hook_report["detail"]
    finally:
        set_hook_executor(prev)
